import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
ACCEL_DIR = ROOT / "compose" / "accelerated"
COMMON = ACCEL_DIR / "accel.override.yml"
REMOTE_COMMON = ROOT / "scripts" / "remote_ingest" / "remote_worker.accel.yml"
EMBEDDER_DOCKERFILE = ACCEL_DIR / "embedder" / "Dockerfile"
DOCLING_DOCKERFILE = ACCEL_DIR / "docling" / "Dockerfile"


def _load(name):
    with (ACCEL_DIR / name).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _service(document, name="vector-embedder"):
    return document["services"][name]


def test_accelerated_dockerfiles_use_published_torch_26_indexes():
    embedder_dockerfile = EMBEDDER_DOCKERFILE.read_text(encoding="utf-8")
    docling_dockerfile = DOCLING_DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG TORCH_VERSION=2.6.0" in embedder_dockerfile
    for dockerfile in (embedder_dockerfile, docling_dockerfile):
        assert "https://download.pytorch.org/whl/cu124" in dockerfile
        assert "https://download.pytorch.org/whl/rocm6.2.4" in dockerfile
        assert "https://download.pytorch.org/whl/xpu" in dockerfile
        assert "https://download.pytorch.org/whl/cpu" in dockerfile
        assert "Unsupported ACCEL=${ACCEL}" in dockerfile


def test_common_override_is_cpu_safe():
    common = _load("accel.override.yml")
    for name in ("docling-parser", "vector-embedder"):
        service = _service(common, name)
        assert service["build"]["args"]["ACCEL"] == "cpu"
        assert "devices" not in service
        assert "group_add" not in service
        assert "deploy" not in service


def test_cpu_overlay_has_no_host_device_contract():
    cpu = _load("accel.cpu.yml")
    for name in ("docling-parser", "vector-embedder"):
        service = _service(cpu, name)
        assert service["build"]["args"]["ACCEL"] == "cpu"
        assert "devices" not in service
        assert "group_add" not in service
        assert "deploy" not in service


def test_intel_overlay_uses_dri_without_requiring_an_npu():
    intel = _load("accel.intel.yml")
    assert _service(intel)["build"]["args"]["ACCEL"] == "auto"
    for name in ("docling-parser", "vector-embedder"):
        service = _service(intel, name)
        assert service["devices"] == ["/dev/dri:/dev/dri"]
        assert "/dev/accel" not in json.dumps(service)

    npu = _load("accel.intel-npu.yml")
    assert _service(npu)["devices"] == ["/dev/accel:/dev/accel"]
    embedder_environment = _service(intel)["environment"]
    assert embedder_environment["EMBED_ACCEL"].endswith("openvino:GPU}")
    assert embedder_environment["REQUIRE_ACCELERATOR"].endswith("true}")


def test_nvidia_overlay_uses_runtime_gpu_reservations_only():
    nvidia = _load("accel.nvidia.yml")
    for name in ("docling-parser", "vector-embedder"):
        service = _service(nvidia, name)
        assert service["build"]["args"]["ACCEL"] == "cuda"
        assert "devices" not in service
        reservation = service["deploy"]["resources"]["reservations"]["devices"]
        assert reservation == [
            {"driver": "nvidia", "count": "all", "capabilities": ["gpu"]}
        ]
    assert _service(nvidia)["environment"]["EMBED_ACCEL"].endswith("cuda}")
    assert _service(nvidia)["environment"]["REQUIRE_ACCELERATOR"].endswith("true}")


def test_amd_overlay_has_complete_rocm_device_contract():
    amd = _load("accel.amd.yml")
    for name in ("docling-parser", "vector-embedder"):
        service = _service(amd, name)
        assert service["build"]["args"]["ACCEL"] == "rocm"
        assert service["devices"] == ["/dev/kfd:/dev/kfd", "/dev/dri:/dev/dri"]
        assert service["cap_add"] == ["SYS_PTRACE"]
        assert service["security_opt"] == ["seccomp=unconfined"]
    assert _service(amd)["environment"]["EMBED_ACCEL"].endswith("rocm}")
    assert _service(amd)["environment"]["REQUIRE_ACCELERATOR"].endswith("true}")


def _render(*overlays, common=COMMON, project_directory=ROOT):
    if not shutil.which("docker"):
        pytest.skip("docker CLI is not installed")
    compose_version = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
    )
    if compose_version.returncode != 0:
        pytest.skip("docker compose plugin is not installed")
    env = {
        **os.environ,
        "RENDER_GID": "123",
        "VIDEO_GID": "124",
    }
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(project_directory),
        "-f",
        str(common),
    ]
    for overlay in overlays:
        command.extend(["-f", str(ACCEL_DIR / overlay)])
    command.extend(["config", "--format", "json"])
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("overlay", "image", "build_accel", "device_sources"),
    [
        ("accel.cpu.yml", "oc-embedder:cpu", "cpu", []),
        ("accel.intel.yml", "oc-embedder:intel", "auto", ["/dev/dri"]),
        ("accel.nvidia.yml", "oc-embedder:cuda", "cuda", []),
        (
            "accel.amd.yml",
            "oc-embedder:rocm",
            "rocm",
            ["/dev/kfd", "/dev/dri"],
        ),
    ],
)
def test_vendor_overlays_render_with_docker_compose(
    overlay, image, build_accel, device_sources
):
    rendered = _service(_render(overlay))
    assert rendered["image"] == image
    assert rendered["build"]["args"]["ACCEL"] == build_accel
    assert [
        device["source"] for device in rendered.get("devices", [])
    ] == device_sources


def test_intel_npu_overlay_adds_device_without_replacing_dri():
    rendered = _service(_render("accel.intel.yml", "accel.intel-npu.yml"))
    assert [device["source"] for device in rendered["devices"]] == [
        "/dev/dri",
        "/dev/accel",
    ]


@pytest.mark.parametrize(
    ("overlay", "build_accel"),
    [
        ("accel.cpu.yml", "cpu"),
        ("accel.intel.yml", "auto"),
        ("accel.nvidia.yml", "cuda"),
        ("accel.amd.yml", "rocm"),
    ],
)
def test_vendor_overlays_are_reusable_by_remote_worker(overlay, build_accel):
    rendered = _service(
        _render(
            overlay,
            common=REMOTE_COMMON,
            project_directory=ROOT / "scripts" / "remote_ingest",
        )
    )
    assert rendered["build"]["context"] == str(ACCEL_DIR)
    assert rendered["build"]["args"]["ACCEL"] == build_accel
