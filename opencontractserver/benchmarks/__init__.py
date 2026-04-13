"""Benchmark harness for evaluating OpenContracts against external RAG datasets.

This package provides building blocks to:

1. Ingest an external benchmark dataset (e.g. LegalBench-RAG) as an
   OpenContracts :class:`~opencontractserver.corpuses.models.Corpus`.
2. Run the production extract-grid pipeline against the benchmark's queries
   using a configurable LLM model.
3. Probe OpenContracts' retrieval layer independently of the answer-extraction
   path so retrieval quality can be measured.
4. Compute standard RAG metrics (recall/precision/F1 over character spans for
   retrieval; SQuAD-style token F1 and exact match for answers).
5. Emit a per-task and aggregate report as JSON and CSV for downstream
   comparison.

The public entry points are :func:`run_benchmark` (Python API) and the
``run_benchmark`` Django management command.
"""

from opencontractserver.benchmarks.adapters.base import (
    BaseBenchmarkAdapter,
    BenchmarkDocument,
    BenchmarkTask,
)
from opencontractserver.benchmarks.adapters.legalbench_rag import LegalBenchRAGAdapter
from opencontractserver.benchmarks.report import BenchmarkReport, TaskResult
from opencontractserver.benchmarks.runner import run_benchmark

__all__ = [
    "BaseBenchmarkAdapter",
    "BenchmarkDocument",
    "BenchmarkReport",
    "BenchmarkTask",
    "LegalBenchRAGAdapter",
    "TaskResult",
    "run_benchmark",
]
