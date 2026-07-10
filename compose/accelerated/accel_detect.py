#!/usr/bin/env python3
"""
Runtime accelerator detection for the OpenContracts local-processing images.

Probes the hardware/runtime actually visible inside the container and picks the
best available compute device, falling back to CPU. Used by BOTH the embedder
and the docling parser so one image "just works" on whatever host it lands on:

  * NVIDIA GPU   (CUDA)        -> torch device "cuda"
  * AMD GPU      (ROCm/HIP)    -> torch device "cuda"  (ROCm torch exposes HIP as the "cuda" device)
  * Intel GPU    (Arc/Xe XPU)  -> torch device "xpu"   OR OpenVINO device "GPU"
  * Intel NPU    (AI Boost)    -> OpenVINO device "NPU"
  * Apple MPS                  -> torch device "mps"
  * none                       -> "cpu"

A single image can only carry ONE torch wheel (cuda XOR rocm XOR xpu XOR cpu),
chosen at build time via the ACCEL build-arg. This detector reports what is
USABLE given the installed runtime, so the service routes correctly and degrades
to CPU instead of crashing when the expected accelerator is absent.

CLI:
    python accel_detect.py            # human-readable report
    python accel_detect.py --export   # emit shell `export VAR=...` lines
    python accel_detect.py --env      # emit allow-listed KEY=VALUE lines
    python accel_detect.py --json      # machine-readable
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys


def _torch():
    try:
        import torch  # noqa

        return torch
    except Exception:
        return None


def detect() -> dict:
    """Return a dict describing the best torch + OpenVINO devices available."""
    info: dict = {
        "torch_backend": None,  # cuda | rocm | xpu | mps | cpu | None(no torch)
        "torch_device": "cpu",  # value to pass to torch .to()/SentenceTransformer
        "torch_version": None,
        "ov_devices": [],  # OpenVINO devices: subset of CPU/GPU/NPU
        "ov_accel_device": None,  # best non-CPU OpenVINO device (GPU>NPU) or None
        "gpu_vendor": None,  # nvidia | amd | intel | apple | None
    }

    # --- torch backend ---
    torch = _torch()
    if torch is not None:
        info["torch_version"] = torch.__version__
        try:
            if torch.cuda.is_available():
                # ROCm builds report through the cuda API too; tell them apart
                # via torch.version.hip.
                is_rocm = bool(getattr(torch.version, "hip", None))
                info["torch_backend"] = "rocm" if is_rocm else "cuda"
                info["torch_device"] = "cuda"
                info["gpu_vendor"] = "amd" if is_rocm else "nvidia"
            elif hasattr(torch, "xpu") and torch.xpu.is_available():
                info["torch_backend"] = "xpu"
                info["torch_device"] = "xpu"
                info["gpu_vendor"] = "intel"
            elif (
                getattr(torch.backends, "mps", None)
                and torch.backends.mps.is_available()
            ):
                info["torch_backend"] = "mps"
                info["torch_device"] = "mps"
                info["gpu_vendor"] = "apple"
            else:
                info["torch_backend"] = "cpu"
        except Exception:
            info["torch_backend"] = "cpu"

    # --- OpenVINO devices (Intel CPU/GPU/NPU) ---
    try:
        import openvino as ov  # noqa

        devs = ov.Core().available_devices
        info["ov_devices"] = list(devs)
        # Prefer GPU over NPU for batched throughput.
        for d in ("GPU", "NPU"):
            if any(x == d or x.startswith(d + ".") for x in devs):
                info["ov_accel_device"] = d
                if info["gpu_vendor"] is None and d == "GPU":
                    info["gpu_vendor"] = "intel"
                break
    except Exception:
        pass

    return info


_TORCH_DEVICE_RE = re.compile(r"^(?:cpu|mps|(?:cuda|xpu)(?::\d+)?)$")
_OPENVINO_DEVICE_RE = re.compile(r"^(?:CPU|GPU|NPU)(?:\.\d+)?$")


def _normalize_embedder_preference(prefer: str | None) -> tuple[str, str] | None:
    """Normalize EMBED_ACCEL to an explicit backend/device selection.

    ``None`` means auto-detect. ROCm intentionally maps to torch's ``cuda``
    device because that is the API exposed by ROCm builds of PyTorch.
    """
    value = (prefer or "auto").strip()
    lowered = value.lower()
    if not lowered or lowered == "auto":
        return None

    aliases = {
        "cpu": ("torch", "cpu"),
        "cuda": ("torch", "cuda"),
        "rocm": ("torch", "cuda"),
        "xpu": ("torch", "xpu"),
        "mps": ("torch", "mps"),
        "npu": ("openvino", "NPU"),
    }
    if lowered in aliases:
        return aliases[lowered]

    if ":" not in value:
        raise ValueError(
            "invalid EMBED_ACCEL value "
            f"{value!r}; expected auto, cpu, cuda, rocm, xpu, mps, npu, "
            "torch:<device>, or openvino:<device>"
        )

    backend, device = value.split(":", 1)
    backend = backend.strip().lower()
    device = device.strip()
    if backend == "torch":
        device = device.lower()
        if device == "rocm":
            device = "cuda"
        if not _TORCH_DEVICE_RE.fullmatch(device):
            raise ValueError(f"invalid torch device in EMBED_ACCEL: {device!r}")
        return backend, device
    if backend == "openvino":
        device = device.upper()
        if not _OPENVINO_DEVICE_RE.fullmatch(device):
            raise ValueError(f"invalid OpenVINO device in EMBED_ACCEL: {device!r}")
        return backend, device
    raise ValueError(f"invalid backend in EMBED_ACCEL: {backend!r}")


def choose_embedder(info: dict, prefer: str = "auto") -> tuple[str, str]:
    """Pick (backend, device) for the embedder.

    backend: "torch" or "openvino"; device: torch device or OV device name.

    Policy (prefer="auto") — prefer the highest-throughput compatible GPU:
      NVIDIA/AMD GPU via torch                                     (non-Intel hosts)
      > Intel GPU via OpenVINO
      > Intel NPU via OpenVINO    (when no GPU is visible)
      > Intel GPU via torch-XPU   (if OpenVINO somehow unavailable)
      > Apple MPS > CPU.
    Override with EMBED_ACCEL, e.g. ``cuda``, ``rocm``, ``xpu``,
    ``openvino:GPU``, ``openvino:NPU``, ``torch:xpu``, or ``cpu``.
    """
    forced = _normalize_embedder_preference(prefer)
    if forced is not None:
        return forced

    ov = info.get("ov_devices", [])
    has_npu = any(x == "NPU" or x.startswith("NPU.") for x in ov)
    has_gpu = any(x == "GPU" or x.startswith("GPU.") for x in ov)
    tb = info.get("torch_backend")

    if tb in ("cuda", "rocm"):  # NVIDIA/AMD: torch is the only path
        return "torch", "cuda"
    if has_gpu:
        return "openvino", "GPU"
    if has_npu:
        return "openvino", "NPU"
    if tb == "xpu":  # OpenVINO absent but torch sees the iGPU
        return "torch", "xpu"
    if tb == "mps":
        return "torch", "mps"
    if "CPU" in ov:
        return "openvino", "CPU"
    return "torch", "cpu"


def choose_docling(info: dict, prefer: str = "auto") -> str:
    """Pick the DOCLING_ACCELERATOR_DEVICE (docling uses torch only).

    Returns one of: cuda | xpu | mps | cpu. (docling has no OpenVINO path.)
    """
    forced = (prefer or "auto").strip().lower()
    if forced == "rocm":
        forced = "cuda"
    if forced not in {"auto", "cpu", "cuda", "xpu", "mps"}:
        raise ValueError(
            f"invalid DOCLING_ACCEL value {prefer!r}; expected auto, cpu, "
            "cuda, rocm, xpu, or mps"
        )
    if forced != "auto":
        return forced
    tb = info.get("torch_backend")
    if tb in ("cuda", "rocm"):
        return "cuda"
    if tb == "xpu":
        return "xpu"
    if tb == "mps":
        return "mps"
    return "cpu"


def _device_files() -> dict:
    """Raw device-node presence, useful for diagnostics."""
    return {
        "nvidia": os.path.exists("/dev/nvidiactl") or bool(shutil.which("nvidia-smi")),
        "amd_kfd": os.path.exists("/dev/kfd"),
        "dri_render": os.path.exists("/dev/dri/renderD128"),
        "intel_npu": os.path.exists("/dev/accel/accel0"),
    }


def main(argv: list[str]) -> int:
    prefer_emb = os.getenv("EMBED_ACCEL", "auto")
    prefer_doc = os.getenv("DOCLING_ACCEL", "auto")
    info = detect()
    try:
        eb, ed = choose_embedder(info, prefer_emb)
        dd = choose_docling(info, prefer_doc)
    except ValueError as exc:
        print(f"accelerator configuration error: {exc}", file=sys.stderr)
        return 2
    payload = {
        **info,
        "devices": _device_files(),
        "embedder_backend": eb,
        "embedder_device": ed,
        "docling_device": dd,
    }

    modes = [arg for arg in argv if arg in {"--json", "--export", "--env"}]
    unknown = [arg for arg in argv if arg not in {"--json", "--export", "--env"}]
    if unknown or len(modes) > 1:
        print("usage: accel_detect.py [--json | --export | --env]", file=sys.stderr)
        return 2

    mode = modes[0] if modes else None
    if mode == "--json":
        print(json.dumps(payload, indent=2))
    elif mode == "--export":
        # Retained for operators who source the output manually. The container
        # entrypoint uses --env and never evaluates detector output as shell code.
        print(f"export EMBED_BACKEND={shlex.quote(eb)}")
        print(f"export EMBED_DEVICE={shlex.quote(ed)}")
        print(f"export DOCLING_ACCELERATOR_DEVICE={shlex.quote(dd)}")
    elif mode == "--env":
        # Machine-readable handoff for entrypoint.sh. Values are validated above,
        # and the entrypoint assigns only these three allow-listed keys.
        print(f"EMBED_BACKEND={eb}")
        print(f"EMBED_DEVICE={ed}")
        print(f"DOCLING_ACCELERATOR_DEVICE={dd}")
    else:
        print("=== accelerator detection ===")
        print(f" gpu_vendor      : {info['gpu_vendor']}")
        print(
            f" torch           : {info['torch_version']} (backend={info['torch_backend']})"
        )
        print(f" openvino devices: {info['ov_devices']}")
        print(f" device nodes    : {_device_files()}")
        print(f" -> embedder     : backend={eb} device={ed}")
        print(f" -> docling      : device={dd}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
