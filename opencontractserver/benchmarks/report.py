"""Serializable benchmark reports.

A report is a thin dataclass so the runner, evaluator, and tests can pass it
around cheaply; it knows how to dump itself to JSON and CSV under a run
directory.  Keeping the report format tiny and explicit makes it easy to diff
two runs with ``git diff`` or ``csv-diff``.
"""

from __future__ import annotations

import csv
import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontractserver.benchmarks.metrics import mean


@dataclass
class TaskResult:
    """Per-datacell metrics and metadata.

    Attributes:
        datacell_id: ID of the datacell this result belongs to.
        task_id: Benchmark task identifier.
        document_key: Adapter-provided document key.
        query: The query that was sent to the extractor.
        prediction: The raw answer string returned by the extraction agent.
        gold_answer: The canonical answer computed from the gold spans.
        retrieved_spans: Top-k character spans from the retrieval probe.
        retrieved_annotation_ids: Parallel annotation IDs, for inspection.
        gold_spans: Gold character spans for this task/document.
        answer_exact_match: SQuAD-style exact match on normalized strings.
        answer_token_f1: SQuAD-style token F1.
        probe_recall_at_k: Fraction of gold spans covered by a single-shot
            top-k vector probe (NOT the retrieval the agent actually used).
        probe_precision_at_k: Fraction of the top-k probe results that hit
            a gold span.
        probe_char_iou: Character-level IoU of probe spans vs. gold.
        extraction_ok: Whether the datacell finished without an error.
        error: Optional error text from the extraction task.
        tags: Adapter-provided tags (subset name, etc.).
    """

    datacell_id: int
    task_id: str
    document_key: str
    query: str
    prediction: str
    gold_answer: str
    retrieved_spans: list[tuple[int, int]]
    retrieved_annotation_ids: list[int]
    gold_spans: list[tuple[int, int]]
    cited_spans: list[tuple[int, int]] = field(default_factory=list)
    citation_count: int = 0
    answer_exact_match: float = 0.0
    answer_token_f1: float = 0.0
    answer_token_recall: float = 0.0
    answer_contains_verbatim_span: float = 0.0
    # ``probe_*`` fields score a standalone single-shot top-k vector search
    # (see :func:`_probe_retrieval_safely`).  This is NOT the retrieval the
    # extraction agent actually used to answer — for that, see
    # ``citation_*`` below, which reads the annotations the agent's
    # similarity_search tool linked to ``Datacell.sources``.
    probe_recall_at_k: float = 0.0
    probe_precision_at_k: float = 0.0
    probe_char_iou: float = 0.0
    citation_span_overlaps_gold: float = 0.0
    citation_text_contains_gold_span: float = 0.0
    extraction_ok: bool = False
    error: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    """Aggregate report for a single benchmark run.

    The report doesn't know about Django; that's the evaluator's job.
    This keeps serialization pure and the object easy to test.
    """

    adapter: dict[str, Any]
    config: dict[str, Any]
    corpus_id: int
    extract_id: int
    task_results: list[TaskResult]
    aggregates: dict[str, int | float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Auto-compute aggregates at init (including the empty-list case)."""
        self.compute_aggregates()

    def compute_aggregates(self) -> None:
        """Refresh :attr:`aggregates` from ``task_results``.

        The aggregates are macro-averaged: every task contributes equally
        regardless of how many documents it spans.  This matches how
        LegalBench-RAG reports numbers at the subset level.
        """
        ok_results = [r for r in self.task_results if r.extraction_ok]
        total = len(self.task_results)
        self.aggregates = {
            # Counts are stored as int; rates/means as float.
            "task_count": total,
            "extraction_success_count": len(ok_results),
            "extraction_success_rate": (len(ok_results) / total) if total else 0.0,
            # Answer metrics are averaged over successful extractions only.
            "answer_exact_match": mean(r.answer_exact_match for r in ok_results),
            "answer_token_f1": mean(r.answer_token_f1 for r in ok_results),
            "answer_token_recall": mean(r.answer_token_recall for r in ok_results),
            "answer_contains_verbatim_span": mean(
                r.answer_contains_verbatim_span for r in ok_results
            ),
            # Citation-based metrics are the HEADLINE retrieval numbers:
            # what the agent actually retrieved and linked to
            # ``Datacell.sources`` during extraction.  Averaged over every
            # task so a failed extraction shows up as zero overlap rather
            # than being silently dropped.
            "citation_coverage_rate": (
                sum(1 for r in self.task_results if r.citation_count > 0) / total
                if total
                else 0.0
            ),
            "avg_citation_count": mean(r.citation_count for r in self.task_results),
            "citation_span_overlaps_gold": mean(
                r.citation_span_overlaps_gold for r in self.task_results
            ),
            "citation_text_contains_gold_span": mean(
                r.citation_text_contains_gold_span for r in self.task_results
            ),
            # Conditional on citations existing — shows quality when grounding succeeds.
            "citation_span_overlaps_gold_given_cited": (
                mean(
                    r.citation_span_overlaps_gold
                    for r in self.task_results
                    if r.citation_count > 0
                )
                if any(r.citation_count > 0 for r in self.task_results)
                else 0.0
            ),
            # Single-shot top-k vector-store probe (NOT what the agent
            # actually retrieved).  Kept as a second axis for debugging
            # retrieval-algorithm changes in isolation; treat as secondary.
            "probe_recall_at_k": mean(
                r.probe_recall_at_k for r in self.task_results
            ),
            "probe_precision_at_k": mean(
                r.probe_precision_at_k for r in self.task_results
            ),
            "probe_char_iou": mean(r.probe_char_iou for r in self.task_results),
        }

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "config": self.config,
            "corpus_id": self.corpus_id,
            "extract_id": self.extract_id,
            "aggregates": self.aggregates,
            "task_results": [
                _task_result_to_dict(result) for result in self.task_results
            ],
        }

    def write(self, run_dir: Path | str) -> Path:
        """Write ``report.json`` and ``report.csv`` under ``run_dir``.

        The directory is created if it does not exist.  Returns the
        directory path so callers can chain additional writes.
        """
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        (run_dir / "report.json").write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        csv_path = run_dir / "report.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "datacell_id",
                    "task_id",
                    "document_key",
                    "extraction_ok",
                    "answer_exact_match",
                    "answer_token_f1",
                    "answer_token_recall",
                    "answer_contains_verbatim_span",
                    "citation_count",
                    "citation_span_overlaps_gold",
                    "citation_text_contains_gold_span",
                    "probe_recall_at_k",
                    "probe_precision_at_k",
                    "probe_char_iou",
                    "prediction",
                    "gold_answer",
                    "tags",
                    "error",
                ]
            )
            for r in self.task_results:
                writer.writerow(
                    [
                        r.datacell_id,
                        r.task_id,
                        r.document_key,
                        int(r.extraction_ok),
                        f"{r.answer_exact_match:.4f}",
                        f"{r.answer_token_f1:.4f}",
                        f"{r.answer_token_recall:.4f}",
                        f"{r.answer_contains_verbatim_span:.4f}",
                        r.citation_count,
                        f"{r.citation_span_overlaps_gold:.4f}",
                        f"{r.citation_text_contains_gold_span:.4f}",
                        f"{r.probe_recall_at_k:.4f}",
                        f"{r.probe_precision_at_k:.4f}",
                        f"{r.probe_char_iou:.4f}",
                        r.prediction,
                        r.gold_answer,
                        ";".join(r.tags),
                        r.error or "",
                    ]
                )
        return run_dir


def _task_result_to_dict(result: TaskResult) -> dict[str, Any]:
    payload = dataclasses.asdict(result)
    # Dataclasses turn tuples into lists — make span lists JSON-friendly.
    payload["retrieved_spans"] = [list(s) for s in result.retrieved_spans]
    payload["gold_spans"] = [list(s) for s in result.gold_spans]
    return payload
