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
    # LegalBench-RAG-compatible char-level metrics on the probe spans.
    # ``probe_char_recall`` / ``probe_char_precision`` use the
    # paper-faithful formulas (per-pair overlap accumulation, no
    # merging — see ``metrics.char_recall_paper`` /
    # ``metrics.char_precision_paper``) so our headline numbers can
    # be quoted against the paper without a "near-the-same-formula"
    # caveat. Equivalence against a vendored copy of upstream
    # ``QAResult`` is enforced in
    # ``test_benchmarks.TestUpstreamEquivalence``.
    #
    # ``*_merged`` variants are the merged-spans cross-doc formulas
    # (mathematically more sensible, no double-counting). They are
    # kept as a sanity column — for paragraph / sliding-window
    # chunkers where retrieved spans don't overlap each other, the
    # two variants are identical to within rounding.
    probe_char_recall: float = 0.0
    probe_char_precision: float = 0.0
    probe_char_recall_merged: float = 0.0
    probe_char_precision_merged: float = 0.0
    # Same char-level metrics, but applied to the spans the agent
    # **actually cited** (``Datacell.sources``).  This is the OC-specific
    # "what the production pipeline delivered" number — not comparable
    # to LB-RAG, which has no agent loop.
    citation_char_recall: float = 0.0
    citation_char_precision: float = 0.0
    citation_span_overlaps_gold: float = 0.0
    citation_text_contains_gold_span: float = 0.0
    # LLM token usage, summed across every ``ModelResponse`` in the cell's
    # captured message history (``Datacell.llm_call_log``).  ``None`` means
    # no usage was reported by the provider (either because extraction
    # failed before any call, or the model/provider didn't return usage in
    # the serialised messages).  ``llm_requests`` counts how many model
    # calls the agent made for this cell — useful for spotting when tool
    # loops blow up request counts even if per-call tokens stay low.
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    llm_requests: int = 0
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
    # ``aggregates`` is heterogeneous: most keys are scalar (int/float),
    # but ``per_subset`` is a nested dict of per-subset metric dicts.
    # Widening the value type to ``Any`` keeps the schema honest without
    # forcing every consumer through a runtime type-narrow.
    aggregates: dict[str, Any] = field(default_factory=dict)
    # Populated by :meth:`write` so callers (e.g. the management command)
    # can surface the path where ``report.json`` / ``report.csv`` landed
    # without re-deriving it.
    run_dir: Path | None = None

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
            "probe_recall_at_k": mean(r.probe_recall_at_k for r in self.task_results),
            "probe_precision_at_k": mean(
                r.probe_precision_at_k for r in self.task_results
            ),
            "probe_char_iou": mean(r.probe_char_iou for r in self.task_results),
            # LegalBench-RAG-parity char-level numbers (probe + citation).
            # The probe columns are the apples-to-apples comparison with
            # their paper; the citation columns measure the full
            # agent-plus-grounding pipeline.
            "probe_char_recall": mean(r.probe_char_recall for r in self.task_results),
            "probe_char_precision": mean(
                r.probe_char_precision for r in self.task_results
            ),
            "probe_char_recall_merged": mean(
                r.probe_char_recall_merged for r in self.task_results
            ),
            "probe_char_precision_merged": mean(
                r.probe_char_precision_merged for r in self.task_results
            ),
            "citation_char_recall": mean(
                r.citation_char_recall for r in self.task_results
            ),
            "citation_char_precision": mean(
                r.citation_char_precision for r in self.task_results
            ),
            # LLM token usage.  Totals are summed across every task (not just
            # successful ones) so a run that fails late still shows the cost.
            # Per-task means are computed over tasks that actually reported
            # usage, so a zero-usage adapter doesn't drag the mean to 0.
            **_usage_aggregates(self.task_results),
            # Per-subset breakdown + equal-weight macro-average.  LegalBench-RAG
            # reports per-subset recall/precision and a macro avg weighted 0.25
            # each across the 4 subsets; this gives us direct parity when
            # multiple subsets are loaded (otherwise the per-subset block just
            # echoes the overall numbers).
            "per_subset": _per_subset_aggregates(self.task_results),
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
                    "probe_char_recall",
                    "probe_char_precision",
                    "probe_char_recall_merged",
                    "probe_char_precision_merged",
                    "citation_char_recall",
                    "citation_char_precision",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "llm_requests",
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
                        f"{r.probe_char_recall:.4f}",
                        f"{r.probe_char_precision:.4f}",
                        f"{r.probe_char_recall_merged:.4f}",
                        f"{r.probe_char_precision_merged:.4f}",
                        f"{r.citation_char_recall:.4f}",
                        f"{r.citation_char_precision:.4f}",
                        "" if r.input_tokens is None else r.input_tokens,
                        "" if r.output_tokens is None else r.output_tokens,
                        "" if r.total_tokens is None else r.total_tokens,
                        r.llm_requests,
                        r.prediction,
                        r.gold_answer,
                        ";".join(r.tags),
                        r.error or "",
                    ]
                )
        self.run_dir = run_dir
        return run_dir


def _task_result_to_dict(result: TaskResult) -> dict[str, Any]:
    payload = dataclasses.asdict(result)
    # Dataclasses turn tuples into lists — make span lists JSON-friendly.
    payload["retrieved_spans"] = [list(s) for s in result.retrieved_spans]
    payload["gold_spans"] = [list(s) for s in result.gold_spans]
    return payload


# --------------------------------------------------------------------------- #
# LLM usage extraction
# --------------------------------------------------------------------------- #

# pydantic-ai serialises ``Usage`` with a `kind` discriminator and spells
# the token fields differently depending on version.  Accept every known
# spelling so the parser works across 0.0.x / 0.2.x / 0.3.x without
# pinning.  Missing fields stay at ``None`` and simply don't get summed.
_USAGE_INPUT_KEYS = ("input_tokens", "request_tokens", "prompt_tokens")
_USAGE_OUTPUT_KEYS = ("output_tokens", "response_tokens", "completion_tokens")
_USAGE_TOTAL_KEYS = ("total_tokens",)


def extract_usage_from_llm_log(llm_log: str | None) -> dict[str, int | None]:
    """Sum token usage across every ``ModelResponse`` in a captured log.

    ``llm_log`` is the raw JSON string produced by
    ``ModelMessagesTypeAdapter.dump_json(messages)`` in
    ``doc_extract_query_task``.  Response messages (``kind == "response"``)
    carry a ``usage`` sub-object with token counts.  We walk the list and
    sum ``input_tokens`` / ``output_tokens`` / ``total_tokens``.

    Returns a dict with ``input_tokens`` / ``output_tokens`` / ``total_tokens``
    (``None`` if no response reported that field) and ``llm_requests`` (the
    number of response messages).
    """
    empty = {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "llm_requests": 0,
    }
    if not llm_log:
        return empty
    try:
        messages = json.loads(llm_log)
    except (ValueError, TypeError):
        return empty
    if not isinstance(messages, list):
        return empty

    requests = 0
    totals: dict[str, int | None] = {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }

    def _pick(usage: dict, keys: tuple[str, ...]) -> int | None:
        for k in keys:
            v = usage.get(k)
            if isinstance(v, int):
                return v
        return None

    def _accumulate(dest_key: str, value: int | None) -> None:
        if value is None:
            return
        current = totals[dest_key]
        totals[dest_key] = value if current is None else current + value

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("kind") != "response":
            continue
        requests += 1
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        _accumulate("input_tokens", _pick(usage, _USAGE_INPUT_KEYS))
        _accumulate("output_tokens", _pick(usage, _USAGE_OUTPUT_KEYS))
        _accumulate("total_tokens", _pick(usage, _USAGE_TOTAL_KEYS))

    # If provider reported input/output but not total, derive it so the
    # headline ``total_tokens`` column is never silently missing when the
    # other two are present.
    if totals["total_tokens"] is None and (
        totals["input_tokens"] is not None or totals["output_tokens"] is not None
    ):
        totals["total_tokens"] = (totals["input_tokens"] or 0) + (
            totals["output_tokens"] or 0
        )

    return {**totals, "llm_requests": requests}


def _per_subset_aggregates(
    results: list[TaskResult],
) -> dict[str, dict[str, float | int]]:
    """Break aggregates out by subset tag and emit a LegalBench-RAG-style
    equal-weight macro average.

    The LegalBench-RAG paper weights each of the four subsets at 0.25
    regardless of how many tasks each contributes (``benchmark.py`` line
    13-18).  We mirror that: compute per-subset means for the char-level
    headline metrics, then average those per-subset means across the
    subsets actually present in the run.  That keeps our overall number
    directly comparable to theirs even when we slice or sample.

    The subset name is taken from ``TaskResult.tags[0]`` — our
    ``LegalBenchRAGAdapter`` stamps the subset there at load time.  Tasks
    with no tag land in a synthetic ``"_untagged"`` bucket so they still
    show up, but they're excluded from the macro average to keep it
    comparable to LB-RAG's by-subset weighting.
    """
    by_subset: dict[str, list[TaskResult]] = {}
    for r in results:
        subset = r.tags[0] if r.tags else "_untagged"
        by_subset.setdefault(subset, []).append(r)

    def _subset_block(rs: list[TaskResult]) -> dict[str, float | int]:
        return {
            "task_count": len(rs),
            "extraction_success_rate": (
                sum(1 for r in rs if r.extraction_ok) / len(rs) if rs else 0.0
            ),
            "probe_char_recall": mean(r.probe_char_recall for r in rs),
            "probe_char_precision": mean(r.probe_char_precision for r in rs),
            "citation_char_recall": mean(r.citation_char_recall for r in rs),
            "citation_char_precision": mean(r.citation_char_precision for r in rs),
            "answer_token_f1": mean(r.answer_token_f1 for r in rs),
        }

    per_subset = {subset: _subset_block(rs) for subset, rs in by_subset.items()}

    named_subsets = [s for s in per_subset if s != "_untagged"]
    if named_subsets:
        per_subset["_macro_avg"] = {
            "subset_count": len(named_subsets),
            "probe_char_recall": mean(
                per_subset[s]["probe_char_recall"] for s in named_subsets
            ),
            "probe_char_precision": mean(
                per_subset[s]["probe_char_precision"] for s in named_subsets
            ),
            "citation_char_recall": mean(
                per_subset[s]["citation_char_recall"] for s in named_subsets
            ),
            "citation_char_precision": mean(
                per_subset[s]["citation_char_precision"] for s in named_subsets
            ),
            "answer_token_f1": mean(
                per_subset[s]["answer_token_f1"] for s in named_subsets
            ),
        }
    return per_subset


def _usage_aggregates(results: list[TaskResult]) -> dict[str, int | float]:
    """Build the usage slice of :attr:`BenchmarkReport.aggregates`.

    Totals are summed across every result (failed extractions still cost
    tokens up to the point of failure).  Means are computed only over
    results that reported that specific token dimension, so a provider
    that only reports ``total_tokens`` doesn't zero-out the mean for
    ``input_tokens``.
    """
    total_in = total_out = total_total = 0
    n_in = n_out = n_total = 0
    total_requests = 0
    for r in results:
        total_requests += r.llm_requests
        if r.input_tokens is not None:
            total_in += r.input_tokens
            n_in += 1
        if r.output_tokens is not None:
            total_out += r.output_tokens
            n_out += 1
        if r.total_tokens is not None:
            total_total += r.total_tokens
            n_total += 1
    task_count = len(results)
    return {
        "input_tokens_sum": total_in,
        "output_tokens_sum": total_out,
        "total_tokens_sum": total_total,
        "llm_requests_sum": total_requests,
        "input_tokens_mean": (total_in / n_in) if n_in else 0.0,
        "output_tokens_mean": (total_out / n_out) if n_out else 0.0,
        "total_tokens_mean": (total_total / n_total) if n_total else 0.0,
        "llm_requests_mean": ((total_requests / task_count) if task_count else 0.0),
    }
