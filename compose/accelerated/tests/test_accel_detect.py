import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ACCEL_DIR = Path(__file__).resolve().parents[1]
DETECTOR_PATH = ACCEL_DIR / "accel_detect.py"
ENTRYPOINT_PATH = ACCEL_DIR / "entrypoint.sh"

_spec = importlib.util.spec_from_file_location("oc_accel_detect", DETECTOR_PATH)
accel_detect = importlib.util.module_from_spec(_spec)
sys.modules["oc_accel_detect"] = accel_detect
_spec.loader.exec_module(accel_detect)


def _info(torch_backend="cpu", ov_devices=None):
    return {
        "torch_backend": torch_backend,
        "torch_device": "cuda" if torch_backend in {"cuda", "rocm"} else "cpu",
        "ov_devices": ov_devices or [],
    }


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        (_info("cuda", ["CPU"]), ("torch", "cuda")),
        (_info("rocm", ["CPU"]), ("torch", "cuda")),
        (_info("xpu", ["CPU", "GPU", "NPU"]), ("openvino", "GPU")),
        (_info("cpu", ["CPU", "GPU"]), ("openvino", "GPU")),
        (_info("xpu", []), ("torch", "xpu")),
        (_info("cpu", ["CPU"]), ("openvino", "CPU")),
        (_info("cpu", []), ("torch", "cpu")),
    ],
)
def test_auto_embedder_routing(info, expected):
    assert accel_detect.choose_embedder(info) == expected


@pytest.mark.parametrize(
    ("preference", "expected"),
    [
        ("cpu", ("torch", "cpu")),
        ("cuda", ("torch", "cuda")),
        ("rocm", ("torch", "cuda")),
        ("xpu", ("torch", "xpu")),
        ("npu", ("openvino", "NPU")),
        (" torch:cuda:1 ", ("torch", "cuda:1")),
        ("torch:rocm", ("torch", "cuda")),
        ("openvino:gpu.1", ("openvino", "GPU.1")),
    ],
)
def test_forced_embedder_aliases_are_normalized(preference, expected):
    assert accel_detect.choose_embedder(_info(), preference) == expected


@pytest.mark.parametrize(
    "preference",
    ["bogus", "cuda;echo unsafe", "torch:bogus", "openvino:cuda", "other:cpu"],
)
def test_invalid_embedder_preferences_are_rejected(preference):
    with pytest.raises(ValueError, match="invalid"):
        accel_detect.choose_embedder(_info(), preference)


def test_docling_rocm_alias_uses_torch_cuda_device():
    assert accel_detect.choose_docling(_info(), "rocm") == "cuda"


def test_invalid_docling_preference_is_rejected():
    with pytest.raises(ValueError, match="invalid DOCLING_ACCEL"):
        accel_detect.choose_docling(_info(), "openvino:GPU")


def test_env_output_is_plain_allowlisted_assignments(monkeypatch, capsys):
    monkeypatch.setattr(accel_detect, "detect", lambda: _info("rocm", ["CPU"]))
    monkeypatch.setattr(accel_detect, "_device_files", lambda: {})
    monkeypatch.setenv("EMBED_ACCEL", "rocm")
    monkeypatch.setenv("DOCLING_ACCEL", "rocm")

    assert accel_detect.main(["--env"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "EMBED_BACKEND=torch",
        "EMBED_DEVICE=cuda",
        "DOCLING_ACCELERATOR_DEVICE=cuda",
    ]


def test_cli_returns_configuration_error_for_invalid_override(monkeypatch, capsys):
    monkeypatch.setattr(accel_detect, "detect", lambda: _info())
    monkeypatch.setenv("EMBED_ACCEL", "not-a-device")

    assert accel_detect.main(["--env"]) == 2
    assert "accelerator configuration error" in capsys.readouterr().err


def test_entrypoint_does_not_evaluate_detector_values(tmp_path):
    sentinel = tmp_path / "should-not-exist"
    fake_detector = tmp_path / "detector.py"
    fake_detector.write_text(
        "import sys\n"
        "if '--env' in sys.argv:\n"
        "    print('EMBED_BACKEND=torch')\n"
        f"    print('EMBED_DEVICE=cpu; touch {sentinel}')\n"
        "    print('DOCLING_ACCELERATOR_DEVICE=cpu')\n",
        encoding="utf-8",
    )
    env = {**os.environ, "ACCEL_DETECT": str(fake_detector)}
    result = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT_PATH),
            "python3",
            "-c",
            "import os; print(os.environ['EMBED_DEVICE'])",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.splitlines()[-1] == f"cpu; touch {sentinel}"
    assert not sentinel.exists()


def test_entrypoint_rejects_invalid_accelerator_configuration():
    env = {
        **os.environ,
        "ACCEL_DETECT": str(DETECTOR_PATH),
        "EMBED_ACCEL": "not-a-device",
    }
    result = subprocess.run(
        ["bash", str(ENTRYPOINT_PATH), "true"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 2
    assert "refusing to start" in result.stderr
