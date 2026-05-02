"""Benchmark adapters.

Each adapter translates an on-disk benchmark dataset into normalized
:class:`BenchmarkDocument` and :class:`BenchmarkTask` objects that the loader
and runner consume.  Adding support for a new benchmark is just a matter of
subclassing :class:`BaseBenchmarkAdapter` and yielding the right data.

Adapters must remain Django-free — no model/ORM imports allowed.  They only
parse on-disk files and yield plain dataclasses so they can be tested and
used outside the Django app registry lifecycle.
"""

from opencontractserver.benchmarks.adapters.base import (
    BaseBenchmarkAdapter,
    BenchmarkDocument,
    BenchmarkTask,
)
from opencontractserver.benchmarks.adapters.legalbench_rag import LegalBenchRAGAdapter

__all__ = [
    "BaseBenchmarkAdapter",
    "BenchmarkDocument",
    "BenchmarkTask",
    "LegalBenchRAGAdapter",
]
