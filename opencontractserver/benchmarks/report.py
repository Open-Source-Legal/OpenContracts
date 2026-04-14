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
        retrieval_recall_at_k: Fraction of gold spans covered by top-k.
        retrieval_precision_at_k: Fraction of top-k that hit a gold span.
        retrieval_char_iou: Character-level IoU over flattened spans.
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
    answer_exact_match: float
    answer_token_f1: float
    retrieval_recall_at_k: float
    retrieval_precision_at_k: float
    retrieval_char_iou: float
    extraction_ok: bool
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
            # Retrieval is independent of extraction success; average over
            # all tasks so a failed extraction doesn't hide a retrieval miss.
            "retrieval_recall_at_k": mean(
                r.retrieval_recall_at_k for r in self.task_results
            ),
            "retrieval_precision_at_k": mean(
                r.retrieval_precision_at_k for r in self.task_results
            ),
            "retrieval_char_iou": mean(r.retrieval_char_iou for r in self.task_results),
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
                    "retrieval_recall_at_k",
                    "retrieval_precision_at_k",
                    "retrieval_char_iou",
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
                        f"{r.retrieval_recall_at_k:.4f}",
                        f"{r.retrieval_precision_at_k:.4f}",
                        f"{r.retrieval_char_iou:.4f}",
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
