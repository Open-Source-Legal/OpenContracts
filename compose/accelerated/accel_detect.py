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
    python accel_detect.py --export   # emit shell `export VAR=...` lines for an entrypoint
    python accel_detect.py --json      # machine-readable
"""

from __future__ import annotations

import json
import os
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


def choose_embedder(info: dict, prefer: str = "auto") -> tuple[str, str]:
    """Pick (backend, device) for the embedder.

    backend: "torch" or "openvino"; device: torch device or OV device name.

    Policy (prefer="auto") — "embedder uses OpenVINO if available, else XPU":
      NVIDIA/AMD GPU via torch                                     (non-Intel hosts)
      > Intel NPU via OpenVINO    (PREFERRED on Intel: a SEPARATE engine from the
                                   iGPU, so the embedder never contends with the
                                   Docling parser which runs on the iGPU/XPU)
      > Intel GPU via OpenVINO    (if no NPU)
      > Intel GPU via torch-XPU   (if OpenVINO somehow unavailable)
      > Apple MPS > CPU.
    Override with EMBED_ACCEL, e.g. "openvino:GPU", "openvino:NPU", "torch:xpu",
    "cpu".
    """
    if prefer and prefer != "auto":
        if ":" in prefer:  # explicit "backend:device"
            b, d = prefer.split(":", 1)
            return b, d
        if prefer == "cpu":
            return "torch", "cpu"

    ov = info.get("ov_devices", [])
    has_npu = any(x == "NPU" or x.startswith("NPU.") for x in ov)
    has_gpu = any(x == "GPU" or x.startswith("GPU.") for x in ov)
    tb = info.get("torch_backend")

    if tb in ("cuda", "rocm"):  # NVIDIA/AMD: torch is the only path
        return "torch", "cuda"
    if has_npu:  # Intel: NPU first (separate from iGPU)
        return "openvino", "NPU"
    if has_gpu:
        return "openvino", "GPU"
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
    if prefer and prefer != "auto":
        return prefer
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
    eb, ed = choose_embedder(info, prefer_emb)
    dd = choose_docling(info, prefer_doc)
    payload = {
        **info,
        "devices": _device_files(),
        "embedder_backend": eb,
        "embedder_device": ed,
        "docling_device": dd,
    }

    if "--json" in argv:
        print(json.dumps(payload, indent=2))
    elif "--export" in argv:
        # Shell-sourceable: an entrypoint does `eval "$(accel_detect.py --export)"`
        print(f"export EMBED_BACKEND={eb}")
        print(f"export EMBED_DEVICE={ed}")
        print(f"export DOCLING_ACCELERATOR_DEVICE={dd}")
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
