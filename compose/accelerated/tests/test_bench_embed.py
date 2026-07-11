from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import time
from pathlib import Path
from types import ModuleType

import pytest


def _load_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "bench_embed.py"
    spec = importlib.util.spec_from_file_location("bench_embed", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves forward annotations through sys.modules while the
    # class decorator runs, so register this dynamically-loaded module first.
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bench = _load_module()


def test_legal_dataset_is_deterministic_and_exact_length() -> None:
    buckets = bench.parse_bucket_specs("short:8,long:33")
    first = bench.generate_legal_dataset(buckets, texts_per_bucket=3, seed=17)
    again = bench.generate_legal_dataset(buckets, texts_per_bucket=3, seed=17)
    different = bench.generate_legal_dataset(buckets, texts_per_bucket=3, seed=18)

    assert first == again
    assert bench.dataset_sha256(first) == bench.dataset_sha256(again)
    assert bench.dataset_sha256(first) != bench.dataset_sha256(different)
    assert [len(sample.text.split()) for sample in first] == [8, 8, 8, 33, 33, 33]
    assert len({sample.text for sample in first}) == len(first)


def test_validate_payload_accepts_singleton_rows_and_rejects_nan() -> None:
    payload = {
        "embeddings": [
            [[0.5, 0.5, 0.5, 0.5]],
            [[-0.5, 0.5, -0.5, 0.5]],
        ]
    }
    vectors, summary = bench.validate_embedding_payload(
        payload,
        expected_count=2,
        expected_dimension=4,
        min_norm=0.9,
        max_norm=1.1,
    )

    assert vectors[0] == [0.5, 0.5, 0.5, 0.5]
    assert summary.singleton_wrapped_rows == 2
    assert summary.dimension == 4
    assert summary.min_norm == pytest.approx(1.0)

    with pytest.raises(bench.BenchmarkError, match="not finite"):
        bench.validate_embedding_payload(
            {"embeddings": [[0.5, math.nan, 0.5, 0.5]]},
            expected_count=1,
            expected_dimension=4,
            min_norm=0.1,
            max_norm=1.1,
        )


def test_backend_metadata_is_required_and_expected_device_is_checked() -> None:
    metadata = bench.extract_backend_metadata(
        {
            "status": "ready",
            "model": "test-model",
            "accelerator": {
                "effective_backend": "torch",
                "effective_device": "cuda:0",
                "fallback": False,
            },
        }
    )
    spec = bench.EndpointSpec(
        label="candidate",
        base_url="http://example.test",
        api_key=None,
        expected_backend="torch",
        expected_device="cuda",
    )
    bench.verify_backend_metadata(
        spec, metadata, allow_missing=False, allow_fallback=False
    )

    missing = bench.extract_backend_metadata({"status": "ready", "model": "test-model"})
    with pytest.raises(bench.BenchmarkError, match="cannot prove"):
        bench.verify_backend_metadata(
            spec, missing, allow_missing=False, allow_fallback=False
        )

    fallback = bench.extract_backend_metadata(
        {
            "status": "ready",
            "model": "test-model",
            "backend": "torch",
            "device": "cpu",
            "fallback": True,
            "fallback_reason": "CUDA unavailable",
        }
    )
    with pytest.raises(bench.BenchmarkError, match="fallback"):
        bench.verify_backend_metadata(
            bench.EndpointSpec("candidate", "http://example.test", None),
            fallback,
            allow_missing=False,
            allow_fallback=False,
        )


class _FakeEndpointClient:
    """EndpointClient test double that avoids binding sockets in sandboxes."""

    def __init__(self, spec, _timeout_seconds: float):
        self.spec = spec
        self.delay = 0.006 if spec.label == "baseline" else 0.0002

    def readiness(self) -> dict:
        return {
            "status": "ready",
            "model": "fake-legal-model",
            "backend": "torch",
            "device": "cpu" if self.spec.label == "baseline" else "cuda:0",
            "fallback": False,
        }

    def embed(self, texts) -> tuple[dict, float]:
        started = time.perf_counter()
        time.sleep(self.delay)
        # Stable unit vectors, with a sign derived from the text so ordering
        # mistakes would change the candidate/baseline cosine comparison.
        embeddings = []
        for text in texts:
            sign = 1.0 if hashlib.sha256(text.encode()).digest()[0] % 2 else -1.0
            embeddings.append([sign * 0.5, 0.5, sign * 0.5, 0.5])
        return {"embeddings": embeddings}, time.perf_counter() - started


class _MissingMetadataEndpointClient(_FakeEndpointClient):
    def readiness(self) -> dict:
        return {"status": "ready", "model": "fake-legal-model"}


def test_missing_backend_metadata_escape_hatch_is_baseline_only(monkeypatch) -> None:
    monkeypatch.setattr(bench, "EndpointClient", _MissingMetadataEndpointClient)
    args = bench.build_parser().parse_args(
        [
            "--baseline-url",
            "http://baseline.test",
            "--candidate-url",
            "http://candidate.test",
            "--allow-missing-backend-metadata",
            "--expected-dimension",
            "4",
            "--min-norm",
            "0.9",
            "--max-norm",
            "1.1",
        ]
    )

    with pytest.raises(bench.BenchmarkError, match="candidate:.*missing"):
        bench.run_benchmark(args)


def test_benchmark_reports_raw_trials_and_speedup(monkeypatch) -> None:
    monkeypatch.setattr(bench, "EndpointClient", _FakeEndpointClient)
    args = bench.build_parser().parse_args(
        [
            "--baseline-url",
            "http://baseline.test",
            "--candidate-url",
            "http://candidate.test",
            "--baseline-expect-device",
            "cpu",
            "--candidate-expect-device",
            "cuda",
            "--length-buckets",
            "short:8,paragraph:16",
            "--texts-per-bucket",
            "2",
            "--batch-sizes",
            "2",
            "--concurrencies",
            "1",
            "--min-batches-per-worker",
            "1",
            "--warmup-runs",
            "1",
            "--trials",
            "2",
            "--expected-dimension",
            "4",
            "--min-norm",
            "0.9",
            "--max-norm",
            "1.1",
            "--target-speedup",
            "1.1",
        ]
    )
    bench.validate_args(args)
    messages: list[str] = []
    report = bench.run_benchmark(args, emit=messages.append)
    serialized = json.loads(json.dumps(report, sort_keys=True))

    assert report["schema_version"] == 1
    assert serialized["schema_version"] == 1
    assert len(report["dataset"]["sha256"]) == 64
    assert report["endpoints"]["baseline"]["metadata"]["device"] == "cpu"
    assert report["endpoints"]["candidate"]["metadata"]["device"] == "cuda:0"
    assert report["correctness"]["minimum_cosine_similarity"] == pytest.approx(1.0)
    assert len(report["correctness"]["cosine_similarities"]) == 2
    scenario = report["scenarios"][0]
    assert scenario["trial_order"] == [
        ["baseline", "candidate"],
        ["candidate", "baseline"],
    ]
    assert len(scenario["baseline"]["trials"]) == 2
    assert len(scenario["candidate"]["trials"]) == 2
    assert scenario["baseline"]["trials"][0]["request_seconds"]
    assert scenario["candidate"]["trials"][0]["request_seconds"]
    assert scenario["candidate"]["trials"][0]["word_tokens_per_second"] > 0
    assert scenario["comparison"]["median_throughput_speedup"] > 1.1
    assert report["gate"]["meets_target"] is True
    assert any("Correctness:" in message for message in messages)
