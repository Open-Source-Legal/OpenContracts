"""Turn a benchmark adapter into a live Corpus + Extract in the database.

The loader is deliberately chatty because it is primarily driven from the
management command, but every helper is callable from Python too so the
test suite can exercise the same code path.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field

from celery import current_app
from django.db import transaction
from django.utils import timezone

from opencontractserver.benchmarks.adapters.base import (
    BaseBenchmarkAdapter,
    BenchmarkDocument,
    BenchmarkTask,
)
from opencontractserver.constants.benchmarks import (
    BENCHMARK_COLUMN_NAME_MAX_LEN,
    BENCHMARK_QUERY_PREVIEW_MAX_LEN,
    BENCHMARK_QUERY_PREVIEW_TRIM_LEN,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentProcessingStatus
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)

_INGEST_POLL_INTERVAL_S = 0.2
_DEFAULT_INGEST_TIMEOUT_S = 300


@dataclass
class LoadedBenchmark:
    """Result of :func:`load_benchmark_into_corpus`.

    Attributes:
        corpus: The newly created :class:`Corpus`.
        extract: The newly created :class:`Extract` linked to the corpus.
        fieldset: The :class:`Fieldset` that owns the generated columns.
        documents_by_key: Map from :attr:`BenchmarkDocument.document_key` to
            its :class:`Document`.  Callers use this to look up which
            document a task's gold spans apply to.
        columns_by_task_id: Map from :attr:`BenchmarkTask.task_id` to the
            :class:`Column` that was created for it.
        datacells: Every datacell created (one per task × task-document).
        gold_by_datacell_id: Per-datacell gold answer / gold spans.  The
            runner and evaluator read from this dict because it's cheaper
            and simpler than hanging sidecar data off Datacell.
        adapter_description: Whatever ``adapter.describe()`` returned.
    """

    corpus: Corpus
    extract: Extract
    fieldset: Fieldset
    documents_by_key: dict[str, Document]
    columns_by_task_id: dict[str, Column]
    datacells: list[Datacell]
    gold_by_datacell_id: dict[int, dict]
    adapter_description: dict = field(default_factory=dict)


@contextmanager
def force_celery_eager():
    """Run enclosed celery tasks synchronously in-process.

    Benchmark ingestion fires ``ingest_doc`` via a celery chain triggered by
    ``post_save`` on :class:`Document`; we want to block until those tasks
    finish so retrieval has something to retrieve.  Rather than polling the
    database, we temporarily force celery into eager mode.  This is safe
    because the management command is a one-off CLI, not a web worker.

    Warning: This mutates the global Celery config for the current process.
    Do not call from a shared worker process or web request handler — only
    from one-off CLIs, notebooks, and test suites.
    """
    conf = current_app.conf
    prev_always_eager = conf.task_always_eager
    prev_eager_propagates = conf.task_eager_propagates
    conf.task_always_eager = True
    conf.task_eager_propagates = True
    try:
        yield
    finally:
        conf.task_always_eager = prev_always_eager
        conf.task_eager_propagates = prev_eager_propagates


def load_benchmark_into_corpus(
    adapter: BaseBenchmarkAdapter,
    *,
    user,
    corpus_title: str | None = None,
    corpus_description: str = "",
    extract_name: str | None = None,
    use_eager_ingestion: bool = True,
    ingest_timeout_seconds: int = _DEFAULT_INGEST_TIMEOUT_S,
) -> LoadedBenchmark:
    """Materialize a benchmark as Corpus + Fieldset + Extract + Datacells.

    The loader does NOT run extraction; it just stages everything so the
    runner can decide which model to hit and whether to probe retrieval.

    Args:
        adapter: Any :class:`BaseBenchmarkAdapter` implementation.
        user: The Django user that will own every created object.  Must
            already exist.
        corpus_title: Title for the new corpus.  Defaults to a timestamped
            name derived from the adapter.
        corpus_description: Free-form description for the corpus.
        extract_name: Name for the new extract.  Defaults to the corpus
            title with a ``" - Extract"`` suffix.
        use_eager_ingestion: If True (the default), wrap ingestion in
            :func:`force_celery_eager` so the sentence-level annotations
            are available synchronously.  The test suite sets this to
            False when it has already configured celery.
        ingest_timeout_seconds: Upper bound on how long to wait for each
            document to reach ``COMPLETED`` after ingestion kicks off.
            Only used when ingestion runs asynchronously.

    Returns:
        A :class:`LoadedBenchmark` describing everything created.
    """
    if user is None:
        raise ValueError("load_benchmark_into_corpus requires a Django user")

    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    adapter_name = adapter.name or type(adapter).__name__
    corpus_title = corpus_title or f"{adapter_name} benchmark {timestamp}"
    extract_name = extract_name or f"{corpus_title} - Extract"

    logger.info(
        "Loading benchmark %s into new corpus %r (user=%s)",
        adapter_name,
        corpus_title,
        user.username,
    )

    corpus = Corpus.objects.create(
        title=corpus_title,
        description=corpus_description,
        creator=user,
    )
    set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.CRUD])

    # Ingest documents ----------------------------------------------------- #
    documents_by_key: dict[str, Document] = {}
    benchmark_documents: list[BenchmarkDocument] = list(adapter.iter_documents())
    logger.info("Ingesting %d documents for %s", len(benchmark_documents), adapter_name)

    ingestion_ctx = force_celery_eager() if use_eager_ingestion else nullcontext()
    with ingestion_ctx:
        for bench_doc in benchmark_documents:
            document = _ingest_benchmark_document(
                corpus=corpus, bench_doc=bench_doc, user=user
            )
            documents_by_key[bench_doc.document_key] = document

        if not use_eager_ingestion:
            # Async pipeline: poll each document until it leaves PENDING/PROCESSING.
            for document in documents_by_key.values():
                _wait_for_document_ready(
                    document_id=document.id, timeout_seconds=ingest_timeout_seconds
                )

    # Create fieldset + columns ------------------------------------------- #
    fieldset = Fieldset.objects.create(
        name=f"{corpus_title} - Fieldset",
        description=f"Generated by benchmark loader for {adapter_name}",
        creator=user,
    )
    set_permissions_for_obj_to_user(user, fieldset, [PermissionTypes.CRUD])

    tasks: list[BenchmarkTask] = list(adapter.iter_tasks())
    logger.info("Creating %d columns for %s", len(tasks), adapter_name)

    columns_by_task_id: dict[str, Column] = {}
    for display_order, task in enumerate(tasks):
        column = Column.objects.create(
            fieldset=fieldset,
            name=_make_column_name(task),
            query=task.query,
            output_type=task.output_type,
            extract_is_list=task.extract_is_list,
            display_order=display_order,
            instructions=_format_instructions(task),
            creator=user,
        )
        set_permissions_for_obj_to_user(user, column, [PermissionTypes.CRUD])
        columns_by_task_id[task.task_id] = column

    # Create extract + datacells ------------------------------------------ #
    extract = Extract.objects.create(
        name=extract_name,
        corpus=corpus,
        fieldset=fieldset,
        creator=user,
    )
    set_permissions_for_obj_to_user(user, extract, [PermissionTypes.CRUD])

    datacells: list[Datacell] = []
    gold_by_datacell_id: dict[int, dict] = {}

    with transaction.atomic():
        for task in tasks:
            column = columns_by_task_id[task.task_id]
            # A task may target multiple documents; attach every one to the
            # extract and create one datacell per (task, document) pair.
            for document_key in task.document_keys:
                document = documents_by_key.get(document_key)
                if document is None:
                    logger.warning(
                        "Task %s references missing document %s; skipping",
                        task.task_id,
                        document_key,
                    )
                    continue
                extract.documents.add(document)

                cell = Datacell.objects.create(
                    extract=extract,
                    column=column,
                    document=document,
                    data_definition=task.output_type,
                    creator=user,
                )
                set_permissions_for_obj_to_user(user, cell, [PermissionTypes.CRUD])
                datacells.append(cell)
                gold_by_datacell_id[cell.id] = {
                    "task_id": task.task_id,
                    "document_key": document_key,
                    "query": task.query,
                    "gold_answer": task.gold_answer,
                    "gold_spans": [
                        list(span) for span in task.gold_spans.get(document_key, ())
                    ],
                    "tags": list(task.tags),
                }

    logger.info(
        "Benchmark %s materialized: corpus=%s extract=%s columns=%d datacells=%d",
        adapter_name,
        corpus.id,
        extract.id,
        len(columns_by_task_id),
        len(datacells),
    )

    return LoadedBenchmark(
        corpus=corpus,
        extract=extract,
        fieldset=fieldset,
        documents_by_key=documents_by_key,
        columns_by_task_id=columns_by_task_id,
        datacells=datacells,
        gold_by_datacell_id=gold_by_datacell_id,
        adapter_description=adapter.describe(),
    )


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _ingest_benchmark_document(
    *, corpus: Corpus, bench_doc: BenchmarkDocument, user
) -> Document:
    """Push a single benchmark document through ``Corpus.import_content``.

    Every document is tagged with a unique benchmark path so repeated loader
    runs don't collide on existing paths inside the corpus.
    """
    unique_path = f"benchmarks/{uuid.uuid4().hex}/{bench_doc.document_key}"
    content_bytes = bench_doc.text.encode("utf-8")
    document, _status, _path_record = corpus.import_content(
        content=content_bytes,
        user=user,
        path=unique_path,
        filename=bench_doc.title,
        file_type="text/plain",
        title=bench_doc.title,
        description=f"Imported by benchmark loader. Source key: {bench_doc.document_key}",
    )
    return document


def _wait_for_document_ready(*, document_id: int, timeout_seconds: int) -> None:
    """Block until the referenced document leaves the PENDING/PROCESSING state.

    Handles the case where a document is deleted mid-poll (`.first()` returns
    ``None``) by returning immediately rather than spinning until timeout.
    """
    deadline = time.monotonic() + max(1, timeout_seconds)
    while time.monotonic() < deadline:
        status = (
            Document.objects.filter(id=document_id)
            .values_list("processing_status", flat=True)
            .first()
        )
        if status is None or status in (
            DocumentProcessingStatus.COMPLETED,
            DocumentProcessingStatus.FAILED,
        ):
            return
        time.sleep(_INGEST_POLL_INTERVAL_S)
    raise TimeoutError(
        f"Document {document_id} did not finish ingestion within {timeout_seconds}s"
    )


_COLUMN_NAME_SANITIZER = re.compile(r"\s+")


def _make_column_name(task: BenchmarkTask) -> str:
    """Build a short, unique column name derived from the task ID and query.

    When the combined name exceeds :data:`BENCHMARK_COLUMN_NAME_MAX_LEN`,
    the query portion is truncated and a suffix derived from the task ID is
    appended to prevent collisions between tasks whose queries share a long
    common prefix.
    """
    base = _COLUMN_NAME_SANITIZER.sub(" ", task.query).strip()
    if len(base) > BENCHMARK_QUERY_PREVIEW_MAX_LEN:
        base = base[:BENCHMARK_QUERY_PREVIEW_TRIM_LEN].rstrip() + "…"
    name = f"{task.task_id} — {base}"
    if len(name) > BENCHMARK_COLUMN_NAME_MAX_LEN:
        # Append a task_id suffix so two tasks with similar queries don't
        # produce identical truncated names.
        suffix = f"…{task.task_id[-6:]}"
        name = name[: BENCHMARK_COLUMN_NAME_MAX_LEN - len(suffix)] + suffix
    return name


def _format_instructions(task: BenchmarkTask) -> str:
    """Build ``Column.instructions`` text so the agent has tag context."""
    parts = [f"Benchmark task ID: {task.task_id}"]
    if task.tags:
        parts.append("Tags: " + ", ".join(task.tags))
    return "\n".join(parts)
