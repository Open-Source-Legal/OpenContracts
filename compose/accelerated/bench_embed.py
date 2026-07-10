#!/usr/bin/env python3
"""Reproducible HTTP benchmark for the vector-embedder service.

The benchmark compares a baseline endpoint with a candidate endpoint using the
same deterministic legal-text corpus. It deliberately separates correctness
checks from timed work: both services must report their effective backend and
device, return finite vectors with the expected shape and norm, and preserve
cosine similarity before throughput measurements begin.

Example::

    python compose/accelerated/bench_embed.py \
        --baseline-url http://localhost:8015 \
        --candidate-url http://localhost:8014 \
        --baseline-expect-device cpu \
        --candidate-expect-device cuda \
        --json-out /tmp/embed-benchmark.json

The service's ``/health/ready`` response must expose ``backend`` and ``device``
metadata by default. Use ``--allow-missing-backend-metadata`` only for a legacy
baseline that cannot expose those fields; doing so weakens the evidence because
a silent accelerator-to-CPU fallback can no longer be detected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import threading
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

SCHEMA_VERSION = 1
DEFAULT_BUCKETS = "short:32,paragraph:128,long:512,multichunk:1024"
DEFAULT_BATCH_SIZES = "1,8,32,100"
DEFAULT_CONCURRENCIES = "1,2"

# Kept as individual whitespace tokens so generated samples have exact,
# inspectable lengths without requiring the model tokenizer on the benchmark
# host. The report calls these ``word_tokens`` rather than model tokens.
LEGAL_WORDS = (
    "whereas",
    "party",
    "agreement",
    "effective",
    "date",
    "shall",
    "represent",
    "warrant",
    "covenant",
    "perform",
    "obligation",
    "material",
    "breach",
    "notice",
    "confidential",
    "information",
    "intellectual",
    "property",
    "license",
    "consideration",
    "payment",
    "invoice",
    "indemnify",
    "liability",
    "damages",
    "termination",
    "survive",
    "governing",
    "law",
    "jurisdiction",
    "arbitration",
    "assignment",
    "successor",
    "affiliate",
    "consent",
    "reasonable",
    "commercially",
    "available",
    "document",
    "schedule",
    "exhibit",
    "amendment",
    "waiver",
    "remedy",
    "exclusive",
    "execution",
    "counterpart",
    "electronic",
    "signature",
    "enforceable",
    "provision",
    "severable",
    "entire",
    "understanding",
    "disclose",
    "required",
    "regulatory",
    "authority",
    "compliance",
    "applicable",
    "statute",
    "claim",
    "defense",
    "settlement",
)


class BenchmarkError(RuntimeError):
    """Raised when benchmark evidence would be invalid or incomplete."""


@dataclass(frozen=True)
class BucketSpec:
    name: str
    word_tokens: int


@dataclass(frozen=True)
class TextSample:
    sample_id: str
    bucket: str
    word_tokens: int
    text: str


@dataclass(frozen=True)
class EndpointSpec:
    label: str
    base_url: str
    api_key: str | None
    expected_backend: str | None = None
    expected_device: str | None = None


@dataclass(frozen=True)
class BackendMetadata:
    status: str | None
    model: str | None
    backend: str | None
    device: str | None
    fallback: bool | None
    fallback_reason: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class ValidationSummary:
    count: int
    dimension: int
    min_norm: float
    max_norm: float
    mean_norm: float
    singleton_wrapped_rows: int


class EndpointClient:
    """Thread-local persistent HTTP sessions for one benchmark endpoint."""

    def __init__(self, spec: EndpointSpec, timeout_seconds: float):
        self.spec = spec
        self.timeout_seconds = timeout_seconds
        self._local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({"Content-Type": "application/json"})
            if self.spec.api_key:
                session.headers["X-API-Key"] = self.spec.api_key
            self._local.session = session
        return session

    def readiness(self) -> dict[str, Any]:
        url = f"{self.spec.base_url.rstrip('/')}/health/ready"
        try:
            response = self._session().get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise BenchmarkError(
                f"{self.spec.label}: readiness request failed for {url}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise BenchmarkError(
                f"{self.spec.label}: /health/ready returned non-object JSON"
            )
        return payload

    def embed(self, texts: Sequence[str]) -> tuple[dict[str, Any], float]:
        url = f"{self.spec.base_url.rstrip('/')}/embeddings/batch"
        started = time.perf_counter_ns()
        try:
            response = self._session().post(
                url,
                json={"texts": list(texts)},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise BenchmarkError(
                f"{self.spec.label}: embedding request failed for {url}: {exc}"
            ) from exc
        elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
        if not isinstance(payload, dict):
            raise BenchmarkError(
                f"{self.spec.label}: /embeddings/batch returned non-object JSON"
            )
        return payload, elapsed


def parse_bucket_specs(value: str) -> list[BucketSpec]:
    specs: list[BucketSpec] = []
    seen: set[str] = set()
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        try:
            name, raw_size = part.split(":", 1)
            size = int(raw_size)
        except (ValueError, TypeError) as exc:
            raise argparse.ArgumentTypeError(
                f"invalid length bucket {part!r}; expected name:positive_integer"
            ) from exc
        name = name.strip()
        if not name or size <= 0:
            raise argparse.ArgumentTypeError(
                f"invalid length bucket {part!r}; expected name:positive_integer"
            )
        if name in seen:
            raise argparse.ArgumentTypeError(f"duplicate length bucket name: {name}")
        seen.add(name)
        specs.append(BucketSpec(name=name, word_tokens=size))
    if not specs:
        raise argparse.ArgumentTypeError("at least one length bucket is required")
    return specs


def parse_positive_int_list(value: str) -> list[int]:
    try:
        numbers = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected comma-separated positive integers, got {value!r}"
        ) from exc
    if not numbers or any(number <= 0 for number in numbers):
        raise argparse.ArgumentTypeError(
            f"expected comma-separated positive integers, got {value!r}"
        )
    if len(numbers) != len(set(numbers)):
        raise argparse.ArgumentTypeError(f"duplicate values are not allowed: {value!r}")
    return numbers


def generate_legal_dataset(
    bucket_specs: Sequence[BucketSpec], texts_per_bucket: int, seed: int
) -> list[TextSample]:
    """Create exact-length, deterministic, distinct legal-text samples."""
    if texts_per_bucket <= 0:
        raise ValueError("texts_per_bucket must be positive")
    rng = random.Random(seed)
    samples: list[TextSample] = []
    for bucket_index, bucket in enumerate(bucket_specs):
        for sample_index in range(texts_per_bucket):
            sample_id = f"{bucket.name}-{sample_index:04d}"
            # A unique first token prevents every repeated sample from being
            # byte-identical while keeping the requested length exact.
            words = [f"section-{bucket_index + 1}-{sample_index + 1}"]
            offset = rng.randrange(len(LEGAL_WORDS))
            stride = 1 + 2 * rng.randrange(max(1, len(LEGAL_WORDS) // 2))
            while len(words) < bucket.word_tokens:
                position = len(words) - 1
                words.append(
                    LEGAL_WORDS[(offset + position * stride) % len(LEGAL_WORDS)]
                )
            text = " ".join(words)
            if len(text.split()) != bucket.word_tokens:  # defensive invariant
                raise AssertionError("generated text length drifted")
            samples.append(
                TextSample(
                    sample_id=sample_id,
                    bucket=bucket.name,
                    word_tokens=bucket.word_tokens,
                    text=text,
                )
            )
    return samples


def dataset_sha256(samples: Sequence[TextSample]) -> str:
    canonical = [
        {
            "sample_id": sample.sample_id,
            "bucket": sample.bucket,
            "word_tokens": sample.word_tokens,
            "text": sample.text,
        }
        for sample in samples
    ]
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _metadata_sources(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield payload
    for key in ("accelerator", "runtime", "embedding", "embedder"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            yield nested


def _first_scalar(sources: Iterable[dict[str, Any]], keys: Sequence[str]) -> str | None:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                rendered = str(value).strip()
                if rendered:
                    return rendered
            if isinstance(value, dict):
                nested = value.get("name") or value.get("type")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return None


def extract_backend_metadata(payload: dict[str, Any]) -> BackendMetadata:
    sources = list(_metadata_sources(payload))
    backend = _first_scalar(
        sources,
        (
            "effective_backend",
            "embedder_backend",
            "embedding_backend",
            "backend",
        ),
    )
    device = _first_scalar(
        sources,
        (
            "effective_device",
            "embedder_device",
            "embedding_device",
            "device",
        ),
    )
    status = _first_scalar(sources, ("status",))
    model = _first_scalar(sources, ("model", "embedding_model"))

    fallback: bool | None = None
    fallback_reason: str | None = None
    for source in sources:
        for key in ("fallback", "fell_back", "using_fallback"):
            if isinstance(source.get(key), bool):
                fallback = source[key]
                break
        reason = source.get("fallback_reason")
        if isinstance(reason, str) and reason.strip():
            fallback_reason = reason.strip()
            if fallback is None:
                fallback = True
        if fallback is not None or fallback_reason is not None:
            break

    return BackendMetadata(
        status=status,
        model=model,
        backend=backend,
        device=device,
        fallback=fallback,
        fallback_reason=fallback_reason,
        raw=payload,
    )


def _metadata_matches(actual: str, expected: str) -> bool:
    actual_normalized = actual.strip().casefold()
    expected_normalized = expected.strip().casefold()
    return actual_normalized == expected_normalized or expected_normalized in {
        part.strip()
        for part in actual_normalized.replace("/", ":").split(":")
        if part.strip()
    }


def verify_backend_metadata(
    spec: EndpointSpec,
    metadata: BackendMetadata,
    *,
    allow_missing: bool,
    allow_fallback: bool,
) -> None:
    if metadata.status is not None and metadata.status.casefold() != "ready":
        raise BenchmarkError(
            f"{spec.label}: readiness status is {metadata.status!r}, expected 'ready'"
        )
    missing = [
        name
        for name, value in (("backend", metadata.backend), ("device", metadata.device))
        if not value
    ]
    if missing and not allow_missing:
        raise BenchmarkError(
            f"{spec.label}: /health/ready is missing {', '.join(missing)} metadata; "
            "cannot prove which compute device served the benchmark"
        )
    if metadata.fallback is True and not allow_fallback:
        reason = f" ({metadata.fallback_reason})" if metadata.fallback_reason else ""
        raise BenchmarkError(
            f"{spec.label}: service reports accelerator fallback{reason}; refusing "
            "to benchmark an unintended backend"
        )
    if spec.expected_backend:
        if not metadata.backend:
            raise BenchmarkError(
                f"{spec.label}: expected backend {spec.expected_backend!r}, but none "
                "was reported"
            )
        if not _metadata_matches(metadata.backend, spec.expected_backend):
            raise BenchmarkError(
                f"{spec.label}: backend {metadata.backend!r} does not match expected "
                f"{spec.expected_backend!r}"
            )
    if spec.expected_device:
        if not metadata.device:
            raise BenchmarkError(
                f"{spec.label}: expected device {spec.expected_device!r}, but none "
                "was reported"
            )
        if not _metadata_matches(metadata.device, spec.expected_device):
            raise BenchmarkError(
                f"{spec.label}: device {metadata.device!r} does not match expected "
                f"{spec.expected_device!r}"
            )


def validate_embedding_payload(
    payload: dict[str, Any],
    *,
    expected_count: int,
    expected_dimension: int,
    min_norm: float,
    max_norm: float,
) -> tuple[list[list[float]], ValidationSummary]:
    rows = payload.get("embeddings")
    if not isinstance(rows, list):
        raise BenchmarkError("response is missing an embeddings array")
    if len(rows) != expected_count:
        raise BenchmarkError(
            f"response returned {len(rows)} embeddings for {expected_count} texts"
        )

    vectors: list[list[float]] = []
    norms: list[float] = []
    wrapped = 0
    for row_index, raw_row in enumerate(rows):
        if not isinstance(raw_row, list):
            raise BenchmarkError(f"embedding row {row_index} is not an array")
        row = raw_row
        if len(row) == 1 and isinstance(row[0], list):
            row = row[0]
            wrapped += 1
        if len(row) != expected_dimension:
            raise BenchmarkError(
                f"embedding row {row_index} has dimension {len(row)}, expected "
                f"{expected_dimension}"
            )
        vector: list[float] = []
        for value_index, value in enumerate(row):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BenchmarkError(
                    f"embedding row {row_index} value {value_index} is not numeric"
                )
            numeric = float(value)
            if not math.isfinite(numeric):
                raise BenchmarkError(
                    f"embedding row {row_index} value {value_index} is not finite"
                )
            vector.append(numeric)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm < min_norm or norm > max_norm:
            raise BenchmarkError(
                f"embedding row {row_index} norm {norm:.6f} is outside "
                f"[{min_norm:.6f}, {max_norm:.6f}]"
            )
        vectors.append(vector)
        norms.append(norm)

    if not norms:
        raise BenchmarkError("response did not contain any embeddings")
    summary = ValidationSummary(
        count=len(vectors),
        dimension=expected_dimension,
        min_norm=min(norms),
        max_norm=max(norms),
        mean_norm=statistics.fmean(norms),
        singleton_wrapped_rows=wrapped,
    )
    return vectors, summary


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise BenchmarkError(
            f"cannot compare vectors with dimensions {len(left)} and {len(right)}"
        )
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise BenchmarkError("cannot compare zero-norm vectors")
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _summary_to_dict(summary: ValidationSummary) -> dict[str, Any]:
    return {
        "count": summary.count,
        "dimension": summary.dimension,
        "min_norm": summary.min_norm,
        "max_norm": summary.max_norm,
        "mean_norm": summary.mean_norm,
        "singleton_wrapped_rows": summary.singleton_wrapped_rows,
    }


def _metadata_to_dict(metadata: BackendMetadata) -> dict[str, Any]:
    return {
        "status": metadata.status,
        "model": metadata.model,
        "backend": metadata.backend,
        "device": metadata.device,
        "fallback": metadata.fallback,
        "fallback_reason": metadata.fallback_reason,
        "raw": metadata.raw,
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("cannot calculate a percentile of an empty sequence")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _expand_samples_for_scenario(
    samples: Sequence[TextSample],
    *,
    batch_size: int,
    concurrency: int,
    min_batches_per_worker: int,
) -> list[TextSample]:
    minimum = batch_size * concurrency * min_batches_per_worker
    target = max(len(samples), minimum)
    target = math.ceil(target / batch_size) * batch_size
    return [samples[index % len(samples)] for index in range(target)]


def _make_batches(
    samples: Sequence[TextSample], batch_size: int, rotation: int
) -> list[list[str]]:
    if samples:
        offset = rotation % len(samples)
        ordered = list(samples[offset:]) + list(samples[:offset])
    else:  # pragma: no cover - generation always produces samples
        ordered = []
    return [
        [sample.text for sample in ordered[index : index + batch_size]]
        for index in range(0, len(ordered), batch_size)
    ]


def _execute_trial(
    client: EndpointClient,
    batches: Sequence[Sequence[str]],
    *,
    concurrency: int,
    executor: ThreadPoolExecutor | None,
    expected_dimension: int,
    min_norm: float,
    max_norm: float,
) -> dict[str, Any]:
    total_word_tokens = sum(len(text.split()) for batch in batches for text in batch)
    started = time.perf_counter_ns()
    responses: list[tuple[int, dict[str, Any], float]] = []
    if concurrency == 1:
        for index, batch in enumerate(batches):
            payload, request_seconds = client.embed(batch)
            responses.append((index, payload, request_seconds))
    else:
        if executor is None:  # pragma: no cover - caller invariant
            raise AssertionError("parallel trial requires an executor")
        future_to_index = {
            executor.submit(client.embed, batch): index
            for index, batch in enumerate(batches)
        }
        try:
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                payload, request_seconds = future.result()
                responses.append((index, payload, request_seconds))
        except Exception:
            for future in future_to_index:
                future.cancel()
            raise
    wall_seconds = (time.perf_counter_ns() - started) / 1_000_000_000

    # Validation happens after the measured wall interval so the benchmark does
    # not accidentally measure Python norm calculations instead of HTTP/model
    # throughput. JSON download and decoding remain inside each request timer.
    total_vectors = 0
    min_observed_norm = math.inf
    max_observed_norm = -math.inf
    wrapped_rows = 0
    for index, payload, _request_seconds in sorted(responses):
        _vectors, summary = validate_embedding_payload(
            payload,
            expected_count=len(batches[index]),
            expected_dimension=expected_dimension,
            min_norm=min_norm,
            max_norm=max_norm,
        )
        total_vectors += summary.count
        min_observed_norm = min(min_observed_norm, summary.min_norm)
        max_observed_norm = max(max_observed_norm, summary.max_norm)
        wrapped_rows += summary.singleton_wrapped_rows

    request_seconds = [item[2] for item in sorted(responses)]
    return {
        "wall_seconds": wall_seconds,
        "texts": total_vectors,
        "texts_per_second": total_vectors / wall_seconds,
        "word_tokens": total_word_tokens,
        "word_tokens_per_second": total_word_tokens / wall_seconds,
        "request_seconds": request_seconds,
        "request_count": len(request_seconds),
        "validation": {
            "min_norm": min_observed_norm,
            "max_norm": max_observed_norm,
            "singleton_wrapped_rows": wrapped_rows,
        },
    }


def _build_scenario_result(
    *,
    batch_size: int,
    concurrency: int,
    expanded_count: int,
    batches_per_trial: int,
    warmups: list[dict[str, Any]],
    measured: list[dict[str, Any]],
) -> dict[str, Any]:
    throughputs = [trial["texts_per_second"] for trial in measured]
    token_throughputs = [trial["word_tokens_per_second"] for trial in measured]
    request_latencies = [
        latency for trial in measured for latency in trial["request_seconds"]
    ]
    return {
        "batch_size": batch_size,
        "concurrency": concurrency,
        "texts_per_trial": expanded_count,
        "batches_per_trial": batches_per_trial,
        "warmups": warmups,
        "trials": measured,
        "summary": {
            "median_texts_per_second": statistics.median(throughputs),
            "mean_texts_per_second": statistics.fmean(throughputs),
            "min_texts_per_second": min(throughputs),
            "max_texts_per_second": max(throughputs),
            "median_word_tokens_per_second": statistics.median(token_throughputs),
            "mean_word_tokens_per_second": statistics.fmean(token_throughputs),
            "request_latency_p50_seconds": _percentile(request_latencies, 0.50),
            "request_latency_p95_seconds": _percentile(request_latencies, 0.95),
        },
    }


def benchmark_pair_scenario(
    baseline_client: EndpointClient,
    candidate_client: EndpointClient,
    samples: Sequence[TextSample],
    *,
    batch_size: int,
    concurrency: int,
    min_batches_per_worker: int,
    warmup_runs: int,
    trials: int,
    expected_dimension: int,
    min_norm: float,
    max_norm: float,
) -> tuple[dict[str, Any], dict[str, Any], list[list[str]]]:
    expanded = _expand_samples_for_scenario(
        samples,
        batch_size=batch_size,
        concurrency=concurrency,
        min_batches_per_worker=min_batches_per_worker,
    )
    clients = {"baseline": baseline_client, "candidate": candidate_client}
    executors = {
        label: ThreadPoolExecutor(max_workers=concurrency) if concurrency > 1 else None
        for label in clients
    }
    warmups: dict[str, list[dict[str, Any]]] = {
        "baseline": [],
        "candidate": [],
    }
    measured: dict[str, list[dict[str, Any]]] = {
        "baseline": [],
        "candidate": [],
    }
    trial_orders: list[list[str]] = []
    try:
        for run_index in range(warmup_runs):
            batches = _make_batches(expanded, batch_size, rotation=run_index)
            order = (
                ("baseline", "candidate")
                if run_index % 2 == 0
                else ("candidate", "baseline")
            )
            for label in order:
                warmups[label].append(
                    _execute_trial(
                        clients[label],
                        batches,
                        concurrency=concurrency,
                        executor=executors[label],
                        expected_dimension=expected_dimension,
                        min_norm=min_norm,
                        max_norm=max_norm,
                    )
                )
        for trial_index in range(trials):
            batches = _make_batches(
                expanded,
                batch_size,
                rotation=warmup_runs + trial_index,
            )
            order = (
                ["baseline", "candidate"]
                if trial_index % 2 == 0
                else ["candidate", "baseline"]
            )
            trial_orders.append(order)
            for label in order:
                measured[label].append(
                    _execute_trial(
                        clients[label],
                        batches,
                        concurrency=concurrency,
                        executor=executors[label],
                        expected_dimension=expected_dimension,
                        min_norm=min_norm,
                        max_norm=max_norm,
                    )
                )
    finally:
        for executor in executors.values():
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)

    batches_per_trial = len(_make_batches(expanded, batch_size, rotation=0))
    baseline_result = _build_scenario_result(
        batch_size=batch_size,
        concurrency=concurrency,
        expanded_count=len(expanded),
        batches_per_trial=batches_per_trial,
        warmups=warmups["baseline"],
        measured=measured["baseline"],
    )
    candidate_result = _build_scenario_result(
        batch_size=batch_size,
        concurrency=concurrency,
        expanded_count=len(expanded),
        batches_per_trial=batches_per_trial,
        warmups=warmups["candidate"],
        measured=measured["candidate"],
    )
    return baseline_result, candidate_result, trial_orders


def compare_scenarios(
    baseline: dict[str, Any], candidate: dict[str, Any], target_speedup: float
) -> dict[str, Any]:
    baseline_trials = baseline["trials"]
    candidate_trials = candidate["trials"]
    paired_speedups = [
        candidate_trial["texts_per_second"] / baseline_trial["texts_per_second"]
        for baseline_trial, candidate_trial in zip(baseline_trials, candidate_trials)
    ]
    baseline_median = baseline["summary"]["median_texts_per_second"]
    candidate_median = candidate["summary"]["median_texts_per_second"]
    speedup = candidate_median / baseline_median
    return {
        "median_throughput_speedup": speedup,
        "paired_trial_speedups": paired_speedups,
        "median_paired_trial_speedup": statistics.median(paired_speedups),
        "target_speedup": target_speedup,
        "meets_target": speedup >= target_speedup,
    }


def preflight_endpoint(
    client: EndpointClient,
    samples: Sequence[TextSample],
    *,
    allow_missing_backend_metadata: bool,
    allow_fallback: bool,
    expected_dimension: int,
    min_norm: float,
    max_norm: float,
) -> tuple[BackendMetadata, list[list[float]], ValidationSummary]:
    metadata = extract_backend_metadata(client.readiness())
    verify_backend_metadata(
        client.spec,
        metadata,
        allow_missing=allow_missing_backend_metadata,
        allow_fallback=allow_fallback,
    )
    validation_samples: list[TextSample] = []
    seen_buckets: set[str] = set()
    for sample in samples:
        if sample.bucket not in seen_buckets:
            validation_samples.append(sample)
            seen_buckets.add(sample.bucket)
    payload, _elapsed = client.embed([sample.text for sample in validation_samples])
    vectors, summary = validate_embedding_payload(
        payload,
        expected_count=len(validation_samples),
        expected_dimension=expected_dimension,
        min_norm=min_norm,
        max_norm=max_norm,
    )
    return metadata, vectors, summary


def run_benchmark(
    args: argparse.Namespace, emit: Callable[[str], None] | None = None
) -> dict[str, Any]:
    emit = emit or (lambda _message: None)
    samples = generate_legal_dataset(
        args.length_buckets, args.texts_per_bucket, args.seed
    )
    dataset_hash = dataset_sha256(samples)
    baseline_spec = EndpointSpec(
        label="baseline",
        base_url=args.baseline_url,
        api_key=(
            args.baseline_api_key if args.baseline_api_key is not None else args.api_key
        ),
        expected_backend=args.baseline_expect_backend,
        expected_device=args.baseline_expect_device,
    )
    candidate_spec = EndpointSpec(
        label="candidate",
        base_url=args.candidate_url,
        api_key=(
            args.candidate_api_key
            if args.candidate_api_key is not None
            else args.api_key
        ),
        expected_backend=args.candidate_expect_backend,
        expected_device=args.candidate_expect_device,
    )
    baseline_client = EndpointClient(baseline_spec, args.timeout)
    candidate_client = EndpointClient(candidate_spec, args.timeout)

    emit(
        f"Dataset: {len(samples)} texts, sha256={dataset_hash}, "
        f"buckets={','.join(f'{b.name}:{b.word_tokens}' for b in args.length_buckets)}"
    )
    baseline_meta, baseline_vectors, baseline_validation = preflight_endpoint(
        baseline_client,
        samples,
        allow_missing_backend_metadata=args.allow_missing_backend_metadata,
        allow_fallback=args.allow_fallback,
        expected_dimension=args.expected_dimension,
        min_norm=args.min_norm,
        max_norm=args.max_norm,
    )
    candidate_meta, candidate_vectors, candidate_validation = preflight_endpoint(
        candidate_client,
        samples,
        # The compatibility escape hatch is intentionally baseline-only. A
        # candidate without effective backend/device metadata cannot prove that
        # the requested accelerator served the timed requests.
        allow_missing_backend_metadata=False,
        allow_fallback=args.allow_fallback,
        expected_dimension=args.expected_dimension,
        min_norm=args.min_norm,
        max_norm=args.max_norm,
    )
    emit(
        f"Baseline: backend={baseline_meta.backend or 'unknown'} "
        f"device={baseline_meta.device or 'unknown'} model={baseline_meta.model or 'unknown'}"
    )
    emit(
        f"Candidate: backend={candidate_meta.backend or 'unknown'} "
        f"device={candidate_meta.device or 'unknown'} model={candidate_meta.model or 'unknown'}"
    )

    if (
        baseline_meta.model
        and candidate_meta.model
        and baseline_meta.model != candidate_meta.model
        and not args.allow_model_mismatch
    ):
        raise BenchmarkError(
            f"model mismatch: baseline={baseline_meta.model!r}, "
            f"candidate={candidate_meta.model!r}"
        )

    similarities = [
        cosine_similarity(baseline_vector, candidate_vector)
        for baseline_vector, candidate_vector in zip(
            baseline_vectors, candidate_vectors
        )
    ]
    if not args.skip_cosine_check and min(similarities) < args.min_cosine:
        raise BenchmarkError(
            f"candidate vector cosine similarity fell below {args.min_cosine:.6f}: "
            f"minimum={min(similarities):.6f}"
        )
    emit(
        f"Correctness: dim={args.expected_dimension}, "
        f"cosine min/mean={min(similarities):.6f}/"
        f"{statistics.fmean(similarities):.6f}"
    )

    scenarios: list[dict[str, Any]] = []
    for batch_size in args.batch_sizes:
        for concurrency in args.concurrencies:
            emit(f"Running batch={batch_size}, concurrency={concurrency} ...")
            baseline_result, candidate_result, trial_order = benchmark_pair_scenario(
                baseline_client,
                candidate_client,
                samples,
                batch_size=batch_size,
                concurrency=concurrency,
                min_batches_per_worker=args.min_batches_per_worker,
                warmup_runs=args.warmup_runs,
                trials=args.trials,
                expected_dimension=args.expected_dimension,
                min_norm=args.min_norm,
                max_norm=args.max_norm,
            )
            comparison = compare_scenarios(
                baseline_result, candidate_result, args.target_speedup
            )
            emit(
                f"  baseline={baseline_result['summary']['median_texts_per_second']:.2f} "
                f"texts/s candidate="
                f"{candidate_result['summary']['median_texts_per_second']:.2f} "
                f"texts/s speedup={comparison['median_throughput_speedup']:.2f}x"
            )
            scenarios.append(
                {
                    "batch_size": batch_size,
                    "concurrency": concurrency,
                    "trial_order": trial_order,
                    "baseline": baseline_result,
                    "candidate": candidate_result,
                    "comparison": comparison,
                }
            )

    gate_batch_size = max(args.batch_sizes)
    gate_concurrency = max(args.concurrencies)
    gate_scenario = next(
        scenario
        for scenario in scenarios
        if scenario["batch_size"] == gate_batch_size
        and scenario["concurrency"] == gate_concurrency
    )
    gate = {
        "batch_size": gate_batch_size,
        "concurrency": gate_concurrency,
        **gate_scenario["comparison"],
    }
    emit(
        f"Gate scenario batch={gate_batch_size}, concurrency={gate_concurrency}: "
        f"{gate['median_throughput_speedup']:.2f}x vs {args.target_speedup:.2f}x "
        f"target ({'PASS' if gate['meets_target'] else 'BELOW TARGET'})"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "dataset": {
            "sha256": dataset_hash,
            "seed": args.seed,
            "texts_per_bucket": args.texts_per_bucket,
            "text_count": len(samples),
            "buckets": [
                {"name": bucket.name, "word_tokens": bucket.word_tokens}
                for bucket in args.length_buckets
            ],
            "sample_ids": [sample.sample_id for sample in samples],
        },
        "config": {
            "batch_sizes": args.batch_sizes,
            "concurrencies": args.concurrencies,
            "min_batches_per_worker": args.min_batches_per_worker,
            "warmup_runs": args.warmup_runs,
            "trials": args.trials,
            "timeout_seconds": args.timeout,
            "expected_dimension": args.expected_dimension,
            "min_norm": args.min_norm,
            "max_norm": args.max_norm,
            "min_cosine": args.min_cosine,
            "cosine_check_skipped": args.skip_cosine_check,
            "target_speedup": args.target_speedup,
            "allow_missing_backend_metadata": args.allow_missing_backend_metadata,
            "allow_fallback": args.allow_fallback,
            "allow_model_mismatch": args.allow_model_mismatch,
        },
        "endpoints": {
            "baseline": {
                "url": baseline_spec.base_url,
                "metadata": _metadata_to_dict(baseline_meta),
                "preflight_validation": _summary_to_dict(baseline_validation),
            },
            "candidate": {
                "url": candidate_spec.base_url,
                "metadata": _metadata_to_dict(candidate_meta),
                "preflight_validation": _summary_to_dict(candidate_validation),
            },
        },
        "correctness": {
            "cosine_similarities": similarities,
            "minimum_cosine_similarity": min(similarities),
            "mean_cosine_similarity": statistics.fmean(similarities),
        },
        "scenarios": scenarios,
        "gate": gate,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare baseline and candidate vector-embedder HTTP throughput."
    )
    parser.add_argument("--baseline-url", required=True)
    parser.add_argument("--candidate-url", required=True)
    parser.add_argument(
        "--api-key",
        default=os.getenv("VECTOR_EMBEDDER_API_KEY", "abc123"),
        help="API key used for both endpoints unless an endpoint override is set.",
    )
    parser.add_argument("--baseline-api-key", default=None)
    parser.add_argument("--candidate-api-key", default=None)
    parser.add_argument("--baseline-expect-backend")
    parser.add_argument("--baseline-expect-device")
    parser.add_argument("--candidate-expect-backend")
    parser.add_argument("--candidate-expect-device")
    parser.add_argument(
        "--allow-missing-backend-metadata",
        action="store_true",
        help=(
            "Allow a legacy baseline readiness response without backend/device "
            "fields; candidate metadata remains mandatory."
        ),
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow a readiness response that reports accelerator fallback.",
    )
    parser.add_argument("--allow-model-mismatch", action="store_true")
    parser.add_argument(
        "--length-buckets",
        type=parse_bucket_specs,
        default=parse_bucket_specs(DEFAULT_BUCKETS),
        metavar="NAME:WORDS,...",
    )
    parser.add_argument("--texts-per-bucket", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260709)
    parser.add_argument(
        "--batch-sizes",
        type=parse_positive_int_list,
        default=parse_positive_int_list(DEFAULT_BATCH_SIZES),
    )
    parser.add_argument(
        "--concurrencies",
        type=parse_positive_int_list,
        default=parse_positive_int_list(DEFAULT_CONCURRENCIES),
    )
    parser.add_argument("--min-batches-per-worker", type=int, default=2)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--expected-dimension", type=int, default=384)
    parser.add_argument("--min-norm", type=float, default=0.1)
    parser.add_argument("--max-norm", type=float, default=1.1)
    parser.add_argument("--min-cosine", type=float, default=0.99)
    parser.add_argument("--skip-cosine-check", action="store_true")
    parser.add_argument("--target-speedup", type=float, default=25.0)
    parser.add_argument(
        "--fail-below-target",
        action="store_true",
        help="Exit non-zero when the largest batch/concurrency scenario misses target.",
    )
    parser.add_argument(
        "--json-out",
        metavar="PATH",
        help="Write the full report to PATH, or '-' for stdout.",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    positive_fields = (
        "texts_per_bucket",
        "min_batches_per_worker",
        "trials",
        "timeout",
        "expected_dimension",
        "max_norm",
        "target_speedup",
    )
    for field in positive_fields:
        if getattr(args, field) <= 0:
            raise BenchmarkError(f"--{field.replace('_', '-')} must be positive")
    if args.warmup_runs < 0:
        raise BenchmarkError("--warmup-runs cannot be negative")
    if args.min_norm < 0 or args.min_norm >= args.max_norm:
        raise BenchmarkError("norm bounds must satisfy 0 <= min-norm < max-norm")
    if not -1.0 <= args.min_cosine <= 1.0:
        raise BenchmarkError("--min-cosine must be between -1 and 1")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        human_stream = sys.stderr if args.json_out == "-" else sys.stdout

        def emit(message: str) -> None:
            if not args.quiet:
                print(message, file=human_stream, flush=True)

        report = run_benchmark(args, emit=emit)
        if args.json_out:
            rendered = json.dumps(report, indent=2, sort_keys=True)
            if args.json_out == "-":
                print(rendered)
            else:
                output_path = Path(args.json_out)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rendered + "\n", encoding="utf-8")
                emit(f"JSON report: {output_path}")
        if args.fail_below_target and not report["gate"]["meets_target"]:
            return 1
        return 0
    except BenchmarkError as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
