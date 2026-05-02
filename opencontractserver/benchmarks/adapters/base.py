"""Adapter-base types shared by every benchmark implementation.

The adapter is deliberately tiny: it just normalizes whatever on-disk layout
a benchmark uses into two flat iterators.  Everything downstream (loader,
runner, evaluator) operates on these normalized objects so new benchmarks can
be slotted in without touching unrelated code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchmarkDocument:
    """A single document that should be ingested into the benchmark corpus.

    ``document_key`` is a stable, human-readable identifier (typically the
    benchmark's on-disk file path).  The loader uses it to deduplicate and to
    link tasks to documents.  ``text`` is the raw UTF-8 text — crucially,
    character offsets in a :class:`BenchmarkTask` are expected to be offsets
    **into this exact string**, so adapters must not transform it.
    """

    document_key: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkTask:
    """A single benchmark test case.

    A task becomes exactly one :class:`~opencontractserver.extracts.models.Column`
    in the generated :class:`~opencontractserver.extracts.models.Fieldset` and
    produces one :class:`~opencontractserver.extracts.models.Datacell` per
    referenced document when the runner executes.

    Attributes:
        task_id: Stable identifier unique within the benchmark run.  Used as
            the cache key for gold data and (sanitized) as the Column name.
        query: Natural-language query sent to the extraction agent.
        document_keys: Documents this task is scoped to.  For retrieval-style
            benchmarks this is usually a single document per test case; a
            corpus-wide task can target ``None`` → every document.
        gold_spans: Character-offset ground truth grouped by document key.
            Maps ``document_key`` → list of ``(start, end)`` tuples where
            ``start``/``end`` are half-open byte-offset bounds into the
            corresponding :attr:`BenchmarkDocument.text`.
        gold_answer: Pre-computed canonical answer string.  For LegalBench-RAG
            this is the concatenation of the gold snippet slices.  Used by
            the answer metric (SQuAD-style token F1 / exact match).
        output_type: Python type name passed to the extract Column.  Defaults
            to ``"str"`` because most benchmarks frame tasks as free-form
            text answers.
        extract_is_list: Whether the answer is expected to be a list.
        tags: Free-form tags pulled from the benchmark (e.g. subset name).
    """

    task_id: str
    query: str
    document_keys: tuple[str, ...]
    gold_spans: dict[str, tuple[tuple[int, int], ...]]
    gold_answer: str
    output_type: str = "str"
    extract_is_list: bool = False
    tags: tuple[str, ...] = ()


class BaseBenchmarkAdapter(ABC):
    """Abstract benchmark adapter.

    Subclasses know the layout of one specific benchmark (LegalBench-RAG,
    CUAD, MAUD, ...) and yield normalized :class:`BenchmarkDocument` and
    :class:`BenchmarkTask` objects.  The adapter is responsible for nothing
    else — no database, no celery, no extract pipeline.
    """

    #: Short machine-friendly name (used in filenames / corpus slugs).
    name: str = ""

    @abstractmethod
    def iter_documents(self) -> Iterable[BenchmarkDocument]:
        """Yield every document that any task references.

        Implementations should yield each document at most once.  The loader
        will ingest them into the generated corpus in the order they're
        emitted.
        """

    @abstractmethod
    def iter_tasks(self) -> Iterable[BenchmarkTask]:
        """Yield every benchmark test case."""

    def describe(self) -> dict[str, Any]:
        """Return a serializable description of this adapter configuration.

        The default implementation just echoes the adapter name; subclasses
        override this to include paths, subset filters, seed, etc.  The
        returned dict is written verbatim into the run's ``config.json``.
        """
        return {"adapter": self.name or type(self).__name__}
