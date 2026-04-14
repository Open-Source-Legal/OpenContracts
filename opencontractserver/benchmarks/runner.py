"""End-to-end benchmark runner.

``run_benchmark`` glues the adapter, loader, extract pipeline, retrieval
probe, metrics, and report into a single call.  Callers (management command,
notebooks, tests) just hand it an adapter and a user and get back a
:class:`BenchmarkReport`.
"""

from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from pathlib import Path

from django.utils import timezone

from opencontractserver.benchmarks.adapters.base import BaseBenchmarkAdapter
from opencontractserver.benchmarks.loader import (
    LoadedBenchmark,
    force_celery_eager,
    load_benchmark_into_corpus,
)
from opencontractserver.benchmarks.metrics import (
    char_iou,
    exact_match,
    precision_at_k,
    recall_at_k,
    token_f1,
)
from opencontractserver.benchmarks.report import BenchmarkReport, TaskResult
from opencontractserver.benchmarks.retrieval import (
    RetrievalResult,
    probe_retrieval,
)
from opencontractserver.constants.benchmarks import (
    BENCHMARK_DEFAULT_MODEL,
    BENCHMARK_DEFAULT_TOP_K,
)
from opencontractserver.extracts.models import Datacell
from opencontractserver.tasks.data_extract_tasks import doc_extract_query_task

logger = logging.getLogger(__name__)


def run_benchmark(
    adapter: BaseBenchmarkAdapter,
    *,
    user,
    model: str = BENCHMARK_DEFAULT_MODEL,
    top_k: int = BENCHMARK_DEFAULT_TOP_K,
    run_dir: Path | str | None = None,
    corpus_title: str | None = None,
    run_label: str | None = None,
    use_eager_ingestion: bool = True,
    use_eager_extraction: bool = True,
    write_report: bool = True,
) -> BenchmarkReport:
    """Materialize, execute, evaluate, and (optionally) persist a benchmark run.

    Args:
        adapter: Configured benchmark adapter (e.g. ``LegalBenchRAGAdapter``).
        user: Django user that will own the created objects.
        model: LLM identifier passed to the extraction agent.  Any string
            pydantic-ai accepts is fine (``"openai:gpt-4o"``,
            ``"anthropic:claude-opus-4-6"``, etc.).
        top_k: How many annotations the retrieval probe returns.
        run_dir: Directory to write ``report.json`` / ``report.csv`` /
            ``config.json`` under.  Defaults to
            ``./benchmark_runs/<timestamp>_<adapter>_<model>/``.
        corpus_title: Optional override for the loader's generated corpus
            title.  Useful when reproducing a run.
        run_label: Optional short label that gets stitched into the
            default ``run_dir`` name.
        use_eager_ingestion: Force celery into eager mode while ingesting
            documents so sentence annotations exist before extraction runs.
            Tests and notebooks should leave this on.
        use_eager_extraction: Force celery into eager mode while
            extracting.  Required in non-eager deployments for the same
            reason.
        write_report: When False, skip writing ``report.json`` / ``.csv``
            and just return the in-memory :class:`BenchmarkReport`.  Tests
            use this to avoid touching the filesystem.

    Returns:
        The populated :class:`BenchmarkReport`.
    """
    if not use_eager_extraction:
        raise NotImplementedError(
            "Non-eager extraction is not yet supported because child tasks "
            "dispatched by doc_extract_query_task go to the real broker and "
            "may not finish before _evaluate() runs. "
            "Set use_eager_extraction=True."
        )

    config: dict[str, object] = {
        "model": model,
        "top_k": top_k,
        "run_label": run_label,
        "started_at": timezone.now().isoformat(),
    }

    logger.info(
        "Starting benchmark run: adapter=%s model=%s top_k=%s",
        adapter.name or type(adapter).__name__,
        model,
        top_k,
    )

    loaded = load_benchmark_into_corpus(
        adapter,
        user=user,
        corpus_title=corpus_title,
        use_eager_ingestion=use_eager_ingestion,
    )

    _run_extraction(
        loaded=loaded, model=model, use_eager_extraction=use_eager_extraction
    )
    task_results = _evaluate(loaded=loaded, top_k=top_k, user_id=user.id)

    report = BenchmarkReport(
        adapter=loaded.adapter_description,
        config=dict(config),  # snapshot; avoid aliasing with the mutable local
        corpus_id=loaded.corpus.id,
        extract_id=loaded.extract.id,
        task_results=task_results,
    )
    # compute_aggregates() is auto-called by __post_init__ when
    # task_results is non-empty.
    config["finished_at"] = timezone.now().isoformat()

    if write_report:
        resolved_run_dir = _resolve_run_dir(
            run_dir=run_dir,
            adapter_name=adapter.name or type(adapter).__name__,
            model=model,
            run_label=run_label,
        )
        report.write(resolved_run_dir)
        _write_run_config(
            run_dir=resolved_run_dir,
            adapter_description=loaded.adapter_description,
            config=config,
            corpus_id=loaded.corpus.id,
            extract_id=loaded.extract.id,
            gold_by_datacell_id=loaded.gold_by_datacell_id,
        )
        logger.info("Benchmark report written to %s", resolved_run_dir)

    logger.info(
        "Benchmark run finished: tasks=%d success_rate=%.3f f1=%.3f recall@%d=%.3f",
        int(report.aggregates["task_count"]),
        report.aggregates["extraction_success_rate"],
        report.aggregates["answer_token_f1"],
        top_k,
        report.aggregates["retrieval_recall_at_k"],
    )
    return report


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _run_extraction(
    *, loaded: LoadedBenchmark, model: str, use_eager_extraction: bool
) -> None:
    """Invoke the production extract task for every datacell.

    We intentionally call ``doc_extract_query_task.si(cell.id, …).apply()``
    per cell instead of going through ``run_extract`` so we can pass the
    ``model_override`` kwarg (which ``run_extract``'s celery chord does
    not expose).
    """
    ctx = force_celery_eager() if use_eager_extraction else nullcontext()
    with ctx:
        for cell in loaded.datacells:
            try:
                doc_extract_query_task.apply(
                    args=[cell.id], kwargs={"model_override": model}
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Extract task raised for datacell %s: %s", cell.id, exc
                )


def _evaluate(*, loaded: LoadedBenchmark, top_k: int, user_id: int) -> list[TaskResult]:
    """Compute answer and retrieval metrics for every datacell."""
    task_results: list[TaskResult] = []

    # Bulk-fetch all datacells in one query to avoid N+1 per-cell SELECTs.
    cell_ids = [c.id for c in loaded.datacells]
    refreshed = {c.id: c for c in Datacell.objects.filter(id__in=cell_ids)}

    for cell in loaded.datacells:
        cell = refreshed.get(cell.id, cell)
        gold_entry = loaded.gold_by_datacell_id.get(cell.id, {})
        gold_answer = gold_entry.get("gold_answer", "")
        gold_spans_raw = gold_entry.get("gold_spans", [])
        gold_spans: list[tuple[int, int]] = [
            (int(s[0]), int(s[1])) for s in gold_spans_raw if len(s) == 2
        ]
        tags = list(gold_entry.get("tags", []))
        query = gold_entry.get("query", cell.column.query or "")
        document_key = gold_entry.get("document_key", "")

        prediction = _extract_prediction_string(cell)
        extraction_ok = cell.failed is None and cell.completed is not None
        error = cell.stacktrace if cell.failed is not None else None

        retrieval = _probe_retrieval_safely(
            corpus_id=loaded.corpus.id,
            document_id=cell.document_id,
            query_text=query,
            top_k=top_k,
            user_id=user_id,
        )

        task_results.append(
            TaskResult(
                datacell_id=cell.id,
                task_id=gold_entry.get("task_id", ""),
                document_key=document_key,
                query=query,
                prediction=prediction,
                gold_answer=gold_answer,
                retrieved_spans=list(retrieval.spans),
                retrieved_annotation_ids=list(retrieval.annotation_ids),
                gold_spans=gold_spans,
                answer_exact_match=exact_match(prediction, gold_answer),
                answer_token_f1=token_f1(prediction, gold_answer),
                retrieval_recall_at_k=recall_at_k(retrieval.spans, gold_spans, top_k),
                retrieval_precision_at_k=precision_at_k(
                    retrieval.spans, gold_spans, top_k
                ),
                retrieval_char_iou=char_iou(retrieval.spans, gold_spans),
                extraction_ok=extraction_ok,
                error=error,
                tags=tags,
            )
        )

    return task_results


def _probe_retrieval_safely(
    *,
    corpus_id: int,
    document_id: int,
    query_text: str,
    top_k: int,
    user_id: int,
) -> RetrievalResult:
    """Swallow retrieval errors so a broken probe can't tank the whole run."""
    try:
        return probe_retrieval(
            corpus_id=corpus_id,
            document_id=document_id,
            query_text=query_text,
            top_k=top_k,
            user_id=user_id,
        )
    except Exception as exc:
        logger.warning(
            "Retrieval probe failed for document %s: %s",
            document_id,
            exc,
        )
        return RetrievalResult(annotation_ids=[], spans=[], similarity_scores=[])


def _extract_prediction_string(cell: Datacell) -> str:
    """Coerce a datacell's extracted value to a string for F1 comparison.

    ``Datacell.data`` is a JSON dict written by ``doc_extract_query_task``.
    The extraction result is nested under the ``"data"`` key, i.e.
    ``{"data": <value>}`` where ``<value>`` is whatever the structured-
    response agent returned (typically a string, list, or dict).
    """
    data = cell.data or {}
    payload = data.get("data") if isinstance(data, dict) else None
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (list, tuple)):
        return " ".join(str(item) for item in payload)
    if isinstance(payload, dict):
        return json.dumps(payload, ensure_ascii=False)
    return str(payload)


def _resolve_run_dir(
    *,
    run_dir: Path | str | None,
    adapter_name: str,
    model: str,
    run_label: str | None,
) -> Path:
    if run_dir is not None:
        return Path(run_dir)
    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    safe_model = model.replace("/", "-").replace(":", "-")
    label = f"_{run_label}" if run_label else ""
    return (
        Path.cwd()
        / "benchmark_runs"
        / f"{timestamp}_{adapter_name}{label}_{safe_model}"
    )


def _write_run_config(
    *,
    run_dir: Path,
    adapter_description: dict,
    config: dict,
    corpus_id: int,
    extract_id: int,
    gold_by_datacell_id: dict,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "adapter": adapter_description,
                "config": config,
                "corpus_id": corpus_id,
                "extract_id": extract_id,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "gold.json").write_text(
        json.dumps(
            {str(k): v for k, v in gold_by_datacell_id.items()},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
