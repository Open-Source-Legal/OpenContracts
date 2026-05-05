from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from celery import chain
from django.apps import apps
from django.conf import settings
from django.db import connections, transaction
from django.db.models import FileField
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import Signal
from django.utils import timezone

from config.telemetry import record_event
from opencontractserver.tasks.doc_tasks import (
    extract_thumbnail,
    ingest_doc,
    set_doc_lock_state,
)
from opencontractserver.tasks.embeddings_task import calculate_embedding_for_doc_text

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document, DocumentPath

logger = logging.getLogger(__name__)

# Custom signal fired when document processing (parsing, thumbnailing) completes.
# This is used to defer corpus actions until documents are fully ready.
# Provides: document (Document instance), user_id (int)
document_processing_complete = Signal()

# Static dispatch UID for document creation signal
DOC_CREATE_UID = "process_doc_on_create_atomic"


# Kicks off document processing pipeline - including thumbnail extraction, ingestion,
# and unlocking the document
def process_doc_on_create_atomic(
    sender: type[Document],
    instance: Document,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Signal handler to process a document after it is created.
    Initiates a chain of tasks to extract a thumbnail, ingest the document,
    and unlock the document.

    Args:
        sender: The model class.
        instance: The instance being saved.
        created (bool): True if a new record was created.
        **kwargs: Additional keyword arguments.
    """
    if created and not instance.processing_started:

        # CAML/markdown files are rendered client-side and need no
        # server-side processing (no parsing, thumbnailing, or embedding).
        from opencontractserver.constants.document_processing import (
            MARKDOWN_MIME_TYPE,
        )

        if instance.file_type == MARKDOWN_MIME_TYPE:
            from opencontractserver.documents.models import DocumentProcessingStatus

            instance.processing_started = timezone.now()
            instance.processing_status = DocumentProcessingStatus.COMPLETED
            instance.backend_lock = False
            instance.save(
                update_fields=[
                    "processing_started",
                    "processing_status",
                    "backend_lock",
                ]
            )
            logger.info(
                f"Skipping pipeline for markdown document {instance.id} "
                "(rendered client-side)"
            )
            return

        ingest_tasks = []

        # Add the thumbnail extraction task
        ingest_tasks.append(extract_thumbnail.si(doc_id=instance.id))

        # Add the ingestion task
        ingest_tasks.append(
            ingest_doc.si(
                user_id=instance.creator.id,
                doc_id=instance.id,
            )
        )

        # Removed embedding calculation from document creation
        # Embeddings will now be calculated only when document is linked to a corpus

        # Add the task to unlock the document
        ingest_tasks.append(set_doc_lock_state.si(locked=False, doc_id=instance.id))

        # Update the processing_started timestamp
        instance.processing_started = timezone.now()
        instance.save()

        # Send tasks to Celery for asynchronous execution
        transaction.on_commit(lambda: chain(*ingest_tasks).apply_async())

        record_event(
            "document_uploaded", {"user_id": instance.creator.id, "env": settings.MODE}
        )


# Static dispatch UID for DocumentPath signal
DOC_PATH_CREATE_UID = "process_doc_on_document_path_create"


def process_doc_on_document_path_create(
    sender: type[DocumentPath],
    instance: DocumentPath,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Signal handler to trigger document text embeddings when a DocumentPath is created.

    This is triggered when documents are added to corpuses via the modern API.
    It handles document text embedding using the corpus's preferred embedder.

    Note: Structural annotation embeddings are handled by
    StructuralAnnotationSet.duplicate() which is called during corpus.add_document().

    Args:
        sender: The DocumentPath model class.
        instance: The DocumentPath instance being saved.
        created (bool): True if a new record was created.
        **kwargs: Additional keyword arguments.
    """
    # Only process newly created, current paths
    if not created or not instance.is_current:
        return

    # Skip if document is still being processed (backend_lock=True)
    # Document text embedding will be triggered when processing completes
    # via annotation signals
    document = instance.document
    if document.backend_lock:
        logger.debug(
            f"Skipping document embedding for DocumentPath {instance.id} - "
            f"document {document.id} still processing (backend_lock=True)"
        )
        return

    corpus = instance.corpus
    doc_id = document.id

    # Queue document text embedding task with corpus context
    # This uses the dual embedding strategy: default + corpus-specific if different
    transaction.on_commit(
        lambda: calculate_embedding_for_doc_text.delay(
            doc_id=doc_id, corpus_id=corpus.id
        )
    )
    logger.info(
        f"Queued document text embedding for doc {doc_id} via DocumentPath "
        f"in corpus {corpus.id}"
    )


DOC_DELETE_CAPTURE_SS_UID = "capture_structural_set_id_pre_delete"
DOC_DELETE_GC_SS_UID = "gc_orphan_structural_set_post_delete"
DOC_DELETE_CAPTURE_BLOBS_UID = "capture_blob_paths_pre_delete"
DOC_DELETE_SCHEDULE_BLOB_GC_UID = "schedule_blob_gc_post_delete"

# Per-DB-connection accumulator keys for batched blob cleanup. Both are
# attributes set directly on the connection object so they share its
# transactional lifetime (cleared automatically when the connection is
# closed by the test runner between tests).
_PENDING_BLOB_CLEANUP_KEY = "_oc_pending_blob_cleanup_paths"
_BLOB_CLEANUP_SCHEDULED_KEY = "_oc_blob_cleanup_on_commit_registered"


def _capture_structural_set_id(sender, instance, **kwargs):
    """Stash the structural_annotation_set_id on the instance before delete.

    Django sets ``instance.structural_annotation_set_id`` to ``None`` after
    deletion, so we have to record it pre_delete to inspect it post_delete.
    """
    instance._structural_set_id_at_delete = instance.structural_annotation_set_id


def _capture_blob_paths_pre_delete(sender, instance, **kwargs):
    """Capture every populated FileField blob path before the row is gone.

    Issue #1492: when a Document is deleted we want to reclaim its file
    blobs from storage — but only if no other Document still references
    them (corpus-isolated copies created by ``Corpus.add_document`` share
    blob paths by design, see issue #1464). We record the candidate
    paths pre-delete and let the matching ``post_delete`` handler fold
    them into a per-transaction set that fires a single Celery task on
    commit.

    The field list is derived from ``_meta`` so adding a new ``FileField``
    on Document automatically extends coverage (parity with
    ``Document.safe_delete_field_blob`` and
    ``DocumentManager.unique_blob_paths``).
    """
    paths: list[str] = []
    for field in instance._meta.get_fields():
        if not isinstance(field, FileField):
            continue
        value = getattr(instance, field.name, None)
        if value and value.name:
            paths.append(value.name)
    instance._captured_blob_paths = paths


def _schedule_blob_cleanup_post_delete(sender, instance, using, **kwargs):
    """Schedule async cleanup of blobs that may have been orphaned.

    Per-instance signals fire for both ``Model.delete()`` and
    ``QuerySet.delete()`` once the model has signal listeners, so this
    handler covers both deletion paths uniformly. To avoid spawning one
    Celery task per Document on bulk delete, we accumulate paths into a
    connection-level set and register a single ``transaction.on_commit``
    callback per transaction that fires one task with all collected
    paths.

    Transaction safety: ``on_commit`` callbacks do not fire on rollback,
    so a failed/rolled-back Document deletion never reaches the storage
    layer.
    """
    paths = getattr(instance, "_captured_blob_paths", None)
    if not paths:
        return

    connection = connections[using]

    pending = getattr(connection, _PENDING_BLOB_CLEANUP_KEY, None)
    if pending is None:
        pending = set()
        setattr(connection, _PENDING_BLOB_CLEANUP_KEY, pending)
    pending.update(paths)

    if getattr(connection, _BLOB_CLEANUP_SCHEDULED_KEY, False):
        # Another Document delete in this transaction already registered
        # the on_commit hook — just contribute paths to the shared set.
        return
    setattr(connection, _BLOB_CLEANUP_SCHEDULED_KEY, True)

    def _flush_blob_cleanup() -> None:
        collected = getattr(connection, _PENDING_BLOB_CLEANUP_KEY, set())
        # Reset state regardless of payload so a subsequent transaction
        # starts from a clean slate even if dispatch raises.
        setattr(connection, _PENDING_BLOB_CLEANUP_KEY, set())
        setattr(connection, _BLOB_CLEANUP_SCHEDULED_KEY, False)
        if not collected:
            return
        from opencontractserver.tasks.cleanup_tasks import (
            cleanup_orphaned_document_blobs_task,
        )
        # ``sorted`` makes task arguments deterministic (helps tests +
        # idempotent retries); ``list`` because Celery JSON-serialises.
        cleanup_orphaned_document_blobs_task.delay(sorted(collected))

    transaction.on_commit(_flush_blob_cleanup, using=using)


def _gc_orphan_structural_set(sender, instance, **kwargs):
    """Delete the StructuralAnnotationSet (and its annotations + relationships)
    when the last Document referencing it is deleted.

    Multiple Documents can share one ``StructuralAnnotationSet`` (keyed by
    content_hash) so that documents with identical content don't re-parse.
    The reverse FK has ``on_delete=PROTECT`` to stop accidental set-deletion
    while a Document still references it, but it doesn't trigger cleanup
    when the LAST Document referencing the set goes away. Without this
    handler, sets and their annotations leak indefinitely — see the
    benchmark-harness contamination incident in PR #1380's audit thread.
    """
    set_id = getattr(instance, "_structural_set_id_at_delete", None)
    if set_id is None:
        return
    StructuralAnnotationSet = apps.get_model("annotations", "StructuralAnnotationSet")
    Document = apps.get_model("documents", "Document")
    if Document.objects.filter(structural_annotation_set_id=set_id).exists():
        return
    try:
        StructuralAnnotationSet.objects.filter(pk=set_id).delete()
    except Exception:
        # GC failures must not break the calling Document.delete(). Log
        # loudly so an orphan that survives this path gets cleaned up by
        # the management command instead.
        logger.exception(
            "Failed to GC orphan StructuralAnnotationSet %s after Document "
            "%s deletion",
            set_id,
            instance.pk,
        )


def connect_corpus_document_signals() -> None:
    """
    Connect signals for corpus-document relationships.

    Connects the DocumentPath post_save signal which triggers document text
    embedding when a document is added to a corpus via DocumentPath creation.

    Called during Django app initialization.
    """
    DocumentPath = apps.get_model("documents", "DocumentPath")

    # DocumentPath creation triggers document text embedding
    post_save.connect(
        process_doc_on_document_path_create,
        sender=DocumentPath,
        dispatch_uid=DOC_PATH_CREATE_UID,
    )

    # Document deletion: GC the StructuralAnnotationSet if it becomes
    # orphaned. Two-phase via pre_delete + post_delete because Django
    # nulls out the FK before post_delete fires.
    Document = apps.get_model("documents", "Document")
    pre_delete.connect(
        _capture_structural_set_id,
        sender=Document,
        dispatch_uid=DOC_DELETE_CAPTURE_SS_UID,
    )
    post_delete.connect(
        _gc_orphan_structural_set,
        sender=Document,
        dispatch_uid=DOC_DELETE_GC_SS_UID,
    )

    # Document deletion (#1492): capture FileField blob paths pre_delete
    # and schedule async storage cleanup post_delete via on_commit.
    pre_delete.connect(
        _capture_blob_paths_pre_delete,
        sender=Document,
        dispatch_uid=DOC_DELETE_CAPTURE_BLOBS_UID,
    )
    post_delete.connect(
        _schedule_blob_cleanup_post_delete,
        sender=Document,
        dispatch_uid=DOC_DELETE_SCHEDULE_BLOB_GC_UID,
    )
