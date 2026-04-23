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
    contains_verbatim_span,
    exact_match,
    precision_at_k,
    recall_at_k,
    token_f1,
    token_recall,
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
    extraction_concurrency: int = 1,
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
            extracting.  Currently only ``True`` is supported — passing
            ``False`` raises :class:`NotImplementedError` because child
            tasks dispatched by ``doc_extract_query_task`` would be sent
            to the real broker and may not finish before ``_evaluate()``
            runs.
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

    # Transparency: surface the embedder actually in use for retrieval so
    # reviewers do not accidentally evaluate the TestEmbedder stub.  The
    # warning fires loudly when the corpus was frozen against a test
    # embedder, since that is a common silent-fallback footgun when running
    # the harness through the test.yml compose stack.
    embedder_path = (
        loaded.corpus.preferred_embedder or loaded.corpus.created_with_embedder or ""
    )
    config["embedder"] = embedder_path
    config["embedder_created_with"] = loaded.corpus.created_with_embedder or ""
    logger.info(
        "Benchmark corpus embedder: preferred=%s created_with=%s",
        loaded.corpus.preferred_embedder,
        loaded.corpus.created_with_embedder,
    )
    if "TestEmbedder" in embedder_path or "test_embedder" in embedder_path:
        logger.warning(
            "Benchmark corpus is bound to a TEST/fake embedder (%s). "
            "Retrieval metrics will be meaningless. See docs/extract_and_retrieval/"
            "benchmarking.md — configure PipelineSettings.default_embedder and "
            "component_settings before running against real data.",
            embedder_path,
        )

    _run_extraction(
        loaded=loaded,
        model=model,
        use_eager_extraction=use_eager_extraction,
        concurrency=extraction_concurrency,
    )

    task_results = _evaluate(
        loaded=loaded,
        top_k=top_k,
        user_id=user.id,
    )

    report = BenchmarkReport(
        adapter=loaded.adapter_description,
        config=dict(config),  # snapshot; avoid aliasing with the mutable local
        corpus_id=loaded.corpus.id,
        extract_id=loaded.extract.id,
        task_results=task_results,
    )
    # compute_aggregates() is auto-called unconditionally by __post_init__.
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
        "Benchmark run finished: tasks=%d success_rate=%.3f f1=%.3f "
        "citation_span_overlaps_gold=%.3f probe_recall@%d=%.3f",
        int(report.aggregates["task_count"]),
        report.aggregates["extraction_success_rate"],
        report.aggregates["answer_token_f1"],
        report.aggregates["citation_span_overlaps_gold"],
        top_k,
        report.aggregates["probe_recall_at_k"],
    )
    return report


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _run_extraction(
    *,
    loaded: LoadedBenchmark,
    model: str,
    use_eager_extraction: bool,
    concurrency: int = 1,
) -> None:
    """Invoke the production extract task for every datacell.

    With ``concurrency=1`` cells are processed serially (original behavior).
    With ``concurrency > 1`` a ThreadPoolExecutor runs up to N cells in
    parallel. Each thread gets its own event loop via ``asyncio.run`` inside
    the celery task's sync wrapper, so this is safe as long as the remote
    LLM can handle the fan-out.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ctx = force_celery_eager() if use_eager_extraction else nullcontext()

    def _run_one(cell_id: int) -> None:
        doc_extract_query_task.apply(args=[cell_id], kwargs={"model_override": model})

    with ctx:
        if concurrency <= 1:
            for cell in loaded.datacells:
                try:
                    _run_one(cell.id)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception(
                        "Extract task raised for datacell %s: %s", cell.id, exc
                    )
            return

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(_run_one, cell.id): cell.id for cell in loaded.datacells
            }
            for fut in as_completed(futures):
                cell_id = futures[fut]
                try:
                    fut.result()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception(
                        "Extract task raised for datacell %s: %s", cell_id, exc
                    )


def _evaluate(
    *,
    loaded: LoadedBenchmark,
    top_k: int,
    user_id: int,
) -> list[TaskResult]:
    """Compute answer, retrieval, and citation metrics for every datacell."""
    task_results: list[TaskResult] = []

    # Bulk-fetch all datacells in one query to avoid N+1 per-cell SELECTs.
    # Prefetch ``sources`` so we can score the agent's own citations against
    # the gold spans without a second round-trip per cell.
    cell_ids = [c.id for c in loaded.datacells]
    refreshed = {
        c.id: c
        for c in Datacell.objects.select_related("column")
        .prefetch_related("sources")
        .filter(id__in=cell_ids)
    }

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

        # Score the agent's grounded citations linked into
        # ``Datacell.sources``.  This is the TRUE retrieval signal — what
        # the retrieval tools surfaced during extraction — independent of
        # the synthetic top-k probe run by :func:`_probe_retrieval_safely`.
        cited_spans, cited_text = _extract_cited_spans_and_text(cell)

        retrieval = _probe_retrieval_safely(
            corpus_id=loaded.corpus.id,
            document_id=cell.document_id,
            query_text=query,
            top_k=top_k,
            user_id=user_id,
        )

        citation_span_hit = float(
            any(
                max(cs[0], gs[0]) < min(cs[1], gs[1])
                for cs in cited_spans
                for gs in gold_spans
            )
        )
        citation_verbatim_hit = contains_verbatim_span(cited_text, gold_answer)

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
                cited_spans=cited_spans,
                citation_count=len(cited_spans),
                answer_exact_match=exact_match(prediction, gold_answer),
                answer_token_f1=token_f1(prediction, gold_answer),
                answer_token_recall=token_recall(prediction, gold_answer),
                answer_contains_verbatim_span=contains_verbatim_span(
                    prediction, gold_answer
                ),
                probe_recall_at_k=recall_at_k(retrieval.spans, gold_spans, top_k),
                probe_precision_at_k=precision_at_k(retrieval.spans, gold_spans, top_k),
                probe_char_iou=char_iou(retrieval.spans, gold_spans),
                citation_span_overlaps_gold=citation_span_hit,
                citation_text_contains_gold_span=citation_verbatim_hit,
                extraction_ok=extraction_ok,
                error=error,
                tags=tags,
            )
        )

    return task_results


def _extract_cited_spans_and_text(cell) -> tuple[list[tuple[int, int]], str]:
    """Return (citation char spans, concatenated citation text) for ``cell``.

    Citations are the :class:`Annotation` rows the extract pipeline attached
    to ``cell.sources`` after grounding the LLM answer back to the document.
    Each annotation stores ``{"start": int, "end": int}`` in ``json`` (for
    text documents) plus the quoted text in ``raw_text``.  Non-text or
    malformed payloads are skipped silently.
    """
    spans: list[tuple[int, int]] = []
    texts: list[str] = []
    for src in cell.sources.all():
        payload = src.json if isinstance(src.json, dict) else {}
        start = payload.get("start")
        end = payload.get("end")
        if isinstance(start, int) and isinstance(end, int) and end >= start:
            spans.append((start, end))
        if src.raw_text:
            texts.append(src.raw_text)
    return spans, " ".join(texts)


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
