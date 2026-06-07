from __future__ import annotations

import enum
import json
import logging
import traceback
import uuid
from datetime import timedelta
from typing import Any, cast

from celery import shared_task
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pydantic import validate_call

from config import celery_app
from opencontractserver.annotations.compact_json import (
    compact_annotation_json,
    iter_page_annotations,
)
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.constants import (
    MAX_PROCESSING_ERROR_LENGTH,
    MAX_PROCESSING_TRACEBACK_LENGTH,
)
from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.constants.truncation import (
    MAX_DOC_TITLE_FALLBACK_LENGTH,
    MAX_NOTIFICATION_ERROR_LENGTH,
)
from opencontractserver.documents.models import (
    Document,
    DocumentProcessingStatus,
    PendingCorpusImport,
    PendingDocumentAnnotations,
)
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.notifications.signals import (
    broadcast_notification_via_websocket,
)
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.pipeline.utils import (
    get_component_by_name,
    get_components_by_mimetype,
)
from opencontractserver.types.dicts import (
    AnnotationLabelPythonType,
    BoundingBoxPythonType,
    FunsdAnnotationType,
    FunsdTokenType,
    LabelLookupPythonType,
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
    PawlsTokenPythonType,
)
from opencontractserver.types.enums import (
    AnnotationFilterMode,
    LabelType,
    PermissionTypes,
)
from opencontractserver.utils.annotation_anchoring import (
    anchor_annotations,
    report_rawtext_preview,
)
from opencontractserver.utils.compact_pawls import expand_pawls_pages
from opencontractserver.utils.etl import build_document_export, pawls_bbox_to_funsd_box
from opencontractserver.utils.files import split_pdf_into_images
from opencontractserver.utils.importing import import_annotations, import_relationships
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
from opencontractserver.utils.text import truncate

logger = get_task_logger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


# CONSTANT
class TaskStates(str, enum.Enum):
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"
    WARNING = "WARNING"


TEMP_DIR = "./tmp"


def _mark_document_failed(
    document: Document,
    error_msg: str,
    traceback_str: str = "",
    create_notification: bool = True,
) -> None:
    """
    Mark a document as failed WITHOUT unlocking.

    This is called when document processing fails after all retries are exhausted
    or when a permanent (non-transient) error occurs.

    The document remains locked (backend_lock=True) to prevent it from appearing
    ready for use when it's actually in a broken state.

    Args:
        document: The Document instance to mark as failed.
        error_msg: Human-readable error message (truncated to MAX_PROCESSING_ERROR_LENGTH).
        traceback_str: Full traceback string (truncated to MAX_PROCESSING_TRACEBACK_LENGTH).
        create_notification: Whether to create a failure notification.
    """
    document.processing_status = DocumentProcessingStatus.FAILED
    document.processing_error = error_msg[:MAX_PROCESSING_ERROR_LENGTH]
    document.processing_error_traceback = traceback_str[
        :MAX_PROCESSING_TRACEBACK_LENGTH
    ]
    document.processing_finished = timezone.now()
    # NOTE: backend_lock stays True - document is not ready for use
    document.save(
        update_fields=[
            "processing_status",
            "processing_error",
            "processing_error_traceback",
            "processing_finished",
        ]
    )

    logger.warning(
        f"[_mark_document_failed] Document {document.pk} marked as FAILED: {error_msg}"
    )

    if create_notification:
        _create_document_processing_failed_notification(document, error_msg)


@celery_app.task()
def mark_doc_failed_on_chain_error(*args: Any, doc_id: int) -> dict[str, Any]:
    """``link_error`` callback for the document-ingest chain.

    Celery halts a chain when a task *raises* (as opposed to returning a
    failure dict): downstream steps — including ``set_doc_lock_state``, which
    finalizes the document's status — never run, leaving the document frozen
    at ``processing_status=PROCESSING`` + ``backend_lock=True``. The frontend
    then shows it "processing" forever (``ModernDocumentItem`` computes
    ``isProcessing = status != FAILED && backendLock``).

    ``ingest_doc``'s own handlers already mark FAILED for the failures it
    catches; this errback covers the ones it can't — an uncaught raise in any
    chain task (e.g. ``extract_thumbnail``), or a raise from ``ingest_doc``
    itself (worker OOM/SIGKILL mid-task, a DB error inside
    ``_mark_document_failed``). It marks the document FAILED so it never
    appears stuck and the user-facing retry path lights up.

    Celery invokes ``link_error`` callbacks with the failed task's context as
    positional args ``(request, exc, traceback)``; we accept them as ``*args``
    and act only on ``doc_id`` (bound at chain-build time).
    """
    exc = args[1] if len(args) > 1 else (args[0] if args else "unknown error")
    traceback_str = str(args[2]) if len(args) > 2 else ""

    try:
        document = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        logger.warning(
            f"[mark_doc_failed_on_chain_error] doc_id={doc_id} no longer exists."
        )
        return {"status": "error", "doc_id": doc_id, "message": "Document not found"}

    # Idempotent: a terminal state means the chain already resolved (the task
    # marked FAILED before re-raising, or the document actually COMPLETED) —
    # don't clobber it.
    if document.processing_status in (
        DocumentProcessingStatus.FAILED,
        DocumentProcessingStatus.COMPLETED,
    ):
        return {
            "status": "noop",
            "doc_id": doc_id,
            "processing_status": document.processing_status,
        }

    logger.error(
        f"[mark_doc_failed_on_chain_error] Ingest chain failed for document "
        f"{doc_id}; marking FAILED. Error: {exc}"
    )
    _mark_document_failed(
        document,
        error_msg=f"Document ingest pipeline failed: {exc}",
        traceback_str=traceback_str,
    )
    return {"status": "failed", "doc_id": doc_id}


@celery_app.task()
def reconcile_stuck_documents() -> dict[str, int]:
    """Mark documents stuck mid-pipeline as FAILED (periodic safety net).

    A document is "stuck" when its ingest chain halted without reaching a
    terminal state and no error callback fired — e.g. the worker was
    OOM/SIGKILL'd mid-task (Cloud Run scale-down under load), a broker
    message was lost, or the visibility timeout elapsed without an ack. Such
    a document keeps ``processing_status=PROCESSING`` (set at ``ingest_doc``
    start) and ``backend_lock=True``, so the UI shows it "processing" forever.

    ``ingest_doc``'s controlled paths and ``mark_doc_failed_on_chain_error``
    cover failures that surface as exceptions; this sweep is the last line of
    defense for the silent ones. It reclaims any PROCESSING + locked document
    whose ``processing_started`` is older than
    ``settings.DOCUMENT_PROCESSING_STALE_MINUTES`` — comfortably beyond the
    max retry/backoff window so it never races a legitimately-retrying doc —
    and marks it FAILED via :func:`_mark_document_failed` (which also notifies
    the creator and lights up the retry path).
    """
    from django.conf import settings

    cutoff = timezone.now() - timedelta(
        minutes=settings.DOCUMENT_PROCESSING_STALE_MINUTES
    )

    # Cap the per-run batch so a large post-outage backlog can't make a single
    # sweep run past its beat interval and overlap the next invocation. The
    # remainder is reclaimed by subsequent sweeps (stuck docs stay stuck until
    # marked, so nothing is lost). Fetch cap+1 ids only to detect a capped run.
    batch_cap = settings.DOCUMENT_RECONCILE_BATCH_CAP
    stuck_ids = list(
        Document.objects.filter(
            processing_status=DocumentProcessingStatus.PROCESSING,
            backend_lock=True,
            processing_started__lt=cutoff,
        ).values_list("pk", flat=True)[: batch_cap + 1]
    )
    capped = len(stuck_ids) > batch_cap
    if capped:
        stuck_ids = stuck_ids[:batch_cap]
        logger.warning(
            "[reconcile_stuck_documents] Stuck backlog exceeds batch cap "
            f"({batch_cap}); reclaiming the first {batch_cap} this sweep, "
            "remainder deferred to the next run."
        )

    count = 0
    for doc_pk in stuck_ids:
        # Re-fetch + re-check under the same predicate: a late retry may have
        # completed (or another beat tick reclaimed it) between the id scan
        # and now. This is the compare-and-swap guard against double-marking.
        document = Document.objects.filter(
            pk=doc_pk,
            processing_status=DocumentProcessingStatus.PROCESSING,
            backend_lock=True,
            processing_started__lt=cutoff,
        ).first()
        if document is None:
            continue

        _mark_document_failed(
            document,
            error_msg=(
                "Processing did not complete and was reclaimed by the "
                "stuck-document reconciliation sweep "
                f"(no progress for over {settings.DOCUMENT_PROCESSING_STALE_MINUTES} "
                "minutes; the ingest pipeline halted without reaching a "
                "terminal state)."
            ),
        )
        count += 1

    if count:
        logger.warning(
            f"[reconcile_stuck_documents] Marked {count} stuck document(s) FAILED."
        )

    return {"reconciled": count}


def _create_document_processing_failed_notification(
    document: Document, error_msg: str
) -> None:
    """
    Create a notification for document processing failure.

    Notifies the document creator when processing fails.

    Args:
        document: The failed document.
        error_msg: The error message to include in the notification.
    """
    if not document.creator:
        return

    # Get document title for notification
    doc_title = document.title
    if not doc_title and document.description:
        doc_title = truncate(document.description, MAX_DOC_TITLE_FALLBACK_LENGTH)
    if not doc_title:
        doc_title = "Untitled"

    try:
        notification = Notification.objects.create(
            recipient=document.creator,
            notification_type=NotificationTypeChoices.DOCUMENT_PROCESSING_FAILED,
            data={
                "document_id": document.id,
                "document_title": doc_title,
                "error_message": truncate(error_msg, MAX_NOTIFICATION_ERROR_LENGTH),
                "file_type": document.file_type,
            },
        )
        broadcast_notification_via_websocket(notification)
        logger.debug(
            f"[_mark_document_failed] Created DOCUMENT_PROCESSING_FAILED notification "
            f"for {document.creator.username}"
        )
    except Exception as e:
        logger.warning(
            f"[_mark_document_failed] Failed to create failure notification "
            f"for document {document.pk}: {e}"
        )


@celery_app.task()
def set_doc_lock_state(*args, locked: bool, doc_id: int):
    """
    Set the backend lock state for a document.

    When unlocking (locked=False):
    - First checks if processing failed - if so, keeps the document locked
    - If processing succeeded, unlocks and sets status to COMPLETED
    - Triggers corpus actions for all corpuses the document belongs to

    Uses DocumentPath as the source of truth for corpus membership (not M2M).

    See docs/architecture/agent_corpus_actions_design.md for the full architecture.
    """
    from opencontractserver.corpuses.models import CorpusActionTrigger
    from opencontractserver.documents.models import DocumentPath
    from opencontractserver.tasks.corpus_tasks import process_corpus_action

    document = Document.objects.get(pk=doc_id)

    # If unlocking, check if processing actually succeeded
    if not locked:
        if document.processing_status == DocumentProcessingStatus.FAILED:
            # Document failed processing - keep it locked
            logger.warning(
                f"[set_doc_lock_state] Document {doc_id} failed processing, "
                "keeping locked (status=FAILED)"
            )
            return

        # Processing succeeded - set status to COMPLETED
        document.processing_status = DocumentProcessingStatus.COMPLETED

    document.backend_lock = locked
    document.processing_finished = timezone.now()
    document.save(
        update_fields=["backend_lock", "processing_finished", "processing_status"]
    )

    # Trigger corpus actions when unlocking (document is now ready)
    # Query DocumentPath as the source of truth for corpus membership
    if not locked:
        # Find all corpuses this document belongs to via DocumentPath
        corpus_data = list(
            DocumentPath.objects.filter(
                document=document,
                is_current=True,
                is_deleted=False,
            )
            .select_related("corpus__creator")
            .values("corpus_id", "corpus__creator_id")
            .distinct()
        )

        # Create document processing notifications (Issue #624)
        # Notify both document creator and corpus owners
        _create_document_processed_notifications(
            document, [dict(row) for row in corpus_data]
        )

        if not corpus_data:
            logger.debug(
                f"[set_doc_lock_state] Document {doc_id} not in any corpus, "
                "skipping corpus actions"
            )
        else:
            logger.info(
                f"[set_doc_lock_state] Document {doc_id} processing complete, "
                f"triggering actions for {len(corpus_data)} corpus(es)"
            )
            for data in corpus_data:
                process_corpus_action.delay(
                    corpus_id=data["corpus_id"],
                    document_ids=[doc_id],
                    user_id=data["corpus__creator_id"],
                    trigger=CorpusActionTrigger.ADD_DOCUMENT,
                )


def _create_document_processed_notifications(
    document: Document, corpus_data: list[dict[str, Any]]
) -> None:
    """
    Create notifications for document processing completion.

    Notifies both the document creator and all corpus owners.
    Issue #624: Real-time notifications for document processing.
    """
    # Build set of recipients (document creator + corpus owners)
    recipients = set()
    if document.creator:
        recipients.add(document.creator)

    # Add corpus owners from DocumentPath data (bulk fetch to avoid N+1)
    corpus_creator_ids: set[int] = {
        data["corpus__creator_id"]
        for data in corpus_data
        if data.get("corpus__creator_id") is not None
    }
    if corpus_creator_ids:
        corpus_creators = User.objects.filter(pk__in=corpus_creator_ids)
        recipients.update(corpus_creators)

    # Get document title for notification
    doc_title = document.title
    if not doc_title and document.description:
        doc_title = truncate(document.description, MAX_DOC_TITLE_FALLBACK_LENGTH)
    if not doc_title:
        doc_title = "Untitled"

    # Create notification for each recipient
    for recipient in recipients:
        try:
            notification = Notification.objects.create(
                recipient=recipient,
                notification_type=NotificationTypeChoices.DOCUMENT_PROCESSED,
                data={
                    "document_id": document.id,
                    "document_title": doc_title,
                    "page_count": document.page_count,
                    "file_type": document.file_type,
                },
            )
            broadcast_notification_via_websocket(notification)
            logger.debug(
                f"[set_doc_lock_state] Created DOCUMENT_PROCESSED notification "
                f"for {recipient.username}"
            )
        except Exception as e:
            logger.warning(
                f"[set_doc_lock_state] Failed to create document processing "
                f"notification for {recipient}: {e}"
            )


@shared_task(
    bind=True,
    autoretry_for=(DocumentParsingError,),
    retry_backoff=60,  # Base delay: 60 seconds
    retry_backoff_max=300,  # Cap at 5 minutes
    retry_jitter=True,  # Add randomness to prevent thundering herd
    retry_kwargs={"max_retries": 3},
)
def ingest_doc(self, user_id: int, doc_id: int) -> dict[str, Any]:
    """
    Ingests a document using the appropriate parser based on the document's MIME type.

    The parser class is determined using get_component_by_name. If there is a dict
    in settings named <parser_name>_kwargs, it is passed to the parser as keyword
    arguments.

    This task uses automatic retry with exponential backoff for transient errors:
    - Up to 3 retries with backoff starting at 60s, capped at 300s
    - Only retries for DocumentParsingError with is_transient=True
    - Permanent errors (is_transient=False) fail immediately

    When all retries are exhausted or a permanent error occurs, the document is
    marked as FAILED and remains locked (not ready for use).

    Args:
        self: Celery task instance (passed automatically when bind=True).
        user_id (int): The ID of the user.
        doc_id (int): The ID of the document to ingest.

    Returns:
        dict: Status information with keys:
            - status: "success" or "failed"
            - doc_id: The document ID
            - error: Error message (only if failed)

    Raises:
        DocumentParsingError: Re-raised for transient errors to trigger Celery retry.
    """
    from opencontractserver.documents.models import DocumentPath
    from opencontractserver.types.enums import PermissionTypes

    logger.info(
        f"[ingest_doc] Ingesting doc {doc_id} for user {user_id} "
        f"(attempt {self.request.retries + 1}/{self.max_retries + 1})"
    )

    # Fetch the document
    try:
        document: Document = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        logger.error(f"Document with id {doc_id} does not exist.")
        return {"status": "failed", "doc_id": doc_id, "error": "Document not found"}

    # Defense-in-depth: even though the enqueueing mutation should have
    # checked permissions, refuse to process a document the supplied
    # user_id has no READ permission on. This blocks the (T-7) class of
    # bug where a future caller forgets to check, and surfaces the misuse
    # via a SECURITY-tagged log line for auditability.
    #
    # Why READ (not UPDATE) here: ingest_doc is enqueued by upload/create
    # mutations (UploadDocument, BulkDocumentUpload) where the caller has
    # just produced the document row, so no UPDATE perm exists yet at the
    # time of the check. The enqueueing mutation already gates on its own
    # CRUD/CREATE rules; this worker-side gate only needs to prove the
    # supplied user_id has *legitimate access* (READ) to the row, which
    # is the minimum bar that catches a forgotten upstream check. The
    # parallel retry_document_processing() path uses UPDATE because it is
    # a user-initiated re-run on an existing doc and the stronger gate
    # is appropriate there.
    User = get_user_model()
    try:
        user_obj = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error(
            f"[SECURITY] [ingest_doc] user_id={user_id} does not exist; "
            f"refusing to process doc_id={doc_id}."
        )
        return {
            "status": "failed",
            "doc_id": doc_id,
            "error": "Invalid user for ingest",
        }
    if not document.user_can(user_obj, PermissionTypes.READ):
        logger.error(
            f"[SECURITY] [ingest_doc] user_id={user_id} lacks READ "
            f"permission on doc_id={doc_id}; refusing to process. "
            "This indicates an enqueueing mutation skipped its permission check."
        )
        return {
            "status": "failed",
            "doc_id": doc_id,
            "error": "User lacks permission for this document",
        }

    # CAML/markdown files are rendered client-side and never parsed.
    # Mark as complete immediately so the pipeline doesn't touch them.
    # NOTE: The post_save signal in documents/signals.py also guards against
    # this, but this check acts as a defensive fallback in case ingest_doc
    # is called directly (e.g., via Celery retry or manual invocation).
    if document.file_type == MARKDOWN_MIME_TYPE:
        document.processing_status = DocumentProcessingStatus.COMPLETED
        document.save(update_fields=["processing_status"])
        logger.info(
            f"[ingest_doc] Skipping ingestion for markdown document {doc_id} "
            "(rendered client-side)"
        )
        return {"status": "success", "doc_id": doc_id}

    # Set processing status to PROCESSING at start of first attempt
    if self.request.retries == 0:
        document.processing_status = DocumentProcessingStatus.PROCESSING
        document.save(update_fields=["processing_status"])

    # Look up corpus from DocumentPath (if document is in a corpus)
    # This ensures structural annotations get the corpus context for proper embeddings
    doc_path = DocumentPath.objects.filter(
        document_id=doc_id, is_current=True, is_deleted=False
    ).first()
    corpus_id = doc_path.corpus_id if doc_path else None
    if corpus_id:
        logger.info(f"[ingest_doc] Document {doc_id} is in corpus {corpus_id}")

    # Get preferred parser from database settings (with fallback to Django settings)
    from opencontractserver.documents.models import PipelineSettings

    pipeline_settings = PipelineSettings.get_instance()
    parser_name: str | None = pipeline_settings.get_preferred_parser(document.file_type)

    if not parser_name:
        error_msg = f"No parser defined for MIME type '{document.file_type}'"
        _mark_document_failed(document, error_msg)
        return {"status": "failed", "doc_id": doc_id, "error": error_msg}

    # Attempt to load parser kwargs from database settings (with fallback)
    from opencontractserver.utils.logging import redact_sensitive_kwargs

    parser_kwargs = pipeline_settings.get_parser_kwargs(parser_name)
    if parser_kwargs:
        logger.debug(
            f"Resolved parser kwargs for '{parser_name}': "
            f"{redact_sensitive_kwargs(parser_kwargs)}"
        )

    # Get the parser class using get_component_by_name
    try:
        parser_class = cast(type[BaseParser], get_component_by_name(parser_name))
        parser_instance = parser_class()
    except ValueError as e:
        error_msg = f"Failed to load parser '{parser_name}': {e}"
        logger.error(error_msg)
        _mark_document_failed(document, error_msg, traceback.format_exc())
        return {"status": "failed", "doc_id": doc_id, "error": error_msg}

    # Call the parser's process_document method
    try:
        parser_instance.process_document(
            user_id, doc_id, corpus_id=corpus_id, **parser_kwargs
        )
        logger.info(
            f"[ingest_doc] Document {doc_id} ingested successfully with '{parser_name}'"
        )
        return {"status": "success", "doc_id": doc_id}

    except DocumentParsingError as e:
        logger.error(
            f"[ingest_doc] DocumentParsingError for document {doc_id}: {e} "
            f"(is_transient={e.is_transient}, retries={self.request.retries}/"
            f"{self.max_retries})"
        )

        # For permanent errors, fail immediately without retry
        if not e.is_transient:
            logger.warning(
                f"[ingest_doc] Permanent error for document {doc_id}, not retrying"
            )
            _mark_document_failed(document, str(e), traceback.format_exc())
            return {"status": "failed", "doc_id": doc_id, "error": str(e)}

        # For transient errors, check if we've exhausted retries
        if self.request.retries >= self.max_retries:
            logger.warning(
                f"[ingest_doc] Max retries ({self.max_retries}) exhausted for "
                f"document {doc_id}"
            )
            _mark_document_failed(document, str(e), traceback.format_exc())
            return {"status": "failed", "doc_id": doc_id, "error": str(e)}

        # Re-raise to trigger Celery retry
        raise

    except Exception as e:
        # Unexpected exception - treat as transient, let Celery retry
        error_msg = f"Unexpected error ingesting document {doc_id}: {e}"
        logger.error(f"[ingest_doc] {error_msg}")

        if self.request.retries >= self.max_retries:
            logger.warning(
                f"[ingest_doc] Max retries ({self.max_retries}) exhausted for "
                f"document {doc_id} after unexpected error"
            )
            _mark_document_failed(document, error_msg, traceback.format_exc())
            return {"status": "failed", "doc_id": doc_id, "error": error_msg}

        # Wrap in DocumentParsingError to trigger retry
        raise DocumentParsingError(error_msg, is_transient=True) from e


@celery_app.task()
@validate_call
def burn_doc_annotations(
    label_lookups: LabelLookupPythonType,
    doc_id: int,
    corpus_id: int,
    analysis_ids: list[int] | None = None,
    annotation_filter_mode: str = "CORPUS_LABELSET_ONLY",
) -> tuple[
    str,
    str,
    OpenContractDocExport | None,
    dict[str, AnnotationLabelPythonType],
    dict[str, AnnotationLabelPythonType],
]:
    """
    Inspects a single Document (doc_id) in corpus (corpus_id) and selects the relevant
    annotations based on the annotation_filter_mode:
      - "CORPUS_LABELSET_ONLY": only annotations that match labels from the corpus
        label set
      - "CORPUS_LABELSET_PLUS_ANALYSES": union of corpus label set + annotations from
        the given analyses
      - "ANALYSES_ONLY": ignore corpus label set and gather only annotations
        belonging to the listed analyses.

    Returns a tuple containing all data needed for packaging:
      (filename, base64-encoded file, doc_export_data, text_labels, doc_labels)

    On failure, ``filename`` and ``base64-encoded file`` are empty strings and
    ``doc_export_data`` is ``None``. Downstream consumers (e.g.
    ``package_annotated_docs``) must skip such entries.
    """
    from opencontractserver.types.enums import AnnotationFilterMode

    # Convert string to enum
    filter_mode_enum = AnnotationFilterMode(annotation_filter_mode)

    return build_document_export(
        label_lookups=label_lookups,
        doc_id=doc_id,
        corpus_id=corpus_id,
        analysis_ids=analysis_ids,
        annotation_filter_mode=filter_mode_enum,
    )


@celery_app.task()
def convert_doc_to_funsd(
    user_id: int,
    doc_id: int,
    corpus_id: int,
    analysis_ids: list[int] | None = None,
    annotation_filter_mode: str = AnnotationFilterMode.CORPUS_LABELSET_ONLY.value,
) -> tuple[int, dict[int, list[FunsdAnnotationType]], list[tuple[int, str, str]]]:
    def pawls_token_to_funsd_token(pawls_token: PawlsTokenPythonType) -> FunsdTokenType:
        pawls_xleft = pawls_token["x"]
        pawls_ybottom = pawls_token["y"]
        pawls_ytop = pawls_xleft + pawls_token["width"]
        pawls_xright = pawls_ybottom + pawls_token["height"]
        funsd_token: FunsdTokenType = {
            "text": pawls_token["text"],
            # In FUNSD, this must be serialzied to list but that's done by json.dumps and tuple has better typing
            # control (fixed length, positional datatypes, etc.)
            "box": (pawls_xleft, pawls_ytop, pawls_xright, pawls_ybottom),
        }
        return funsd_token

    doc = Document.objects.get(id=doc_id)

    annotation_map: dict[int, list[FunsdAnnotationType]] = {}

    # Modify the annotation query to respect filter mode
    doc_annotations = Annotation.objects.filter(document_id=doc_id, corpus_id=corpus_id)

    if annotation_filter_mode == AnnotationFilterMode.ANALYSES_ONLY.value:
        if analysis_ids:
            doc_annotations = doc_annotations.filter(analysis_id__in=analysis_ids)
        else:
            doc_annotations = Annotation.objects.none()
    elif (
        annotation_filter_mode
        == AnnotationFilterMode.CORPUS_LABELSET_PLUS_ANALYSES.value
    ):
        label_pks_in_corpus = (
            Annotation.objects.filter(corpus_id=corpus_id)
            .values_list("annotation_label_id", flat=True)
            .distinct()
        )
        if analysis_ids:
            doc_annotations = doc_annotations.filter(
                Q(annotation_label_id__in=label_pks_in_corpus)
                | Q(analysis_id__in=analysis_ids)
            )
        else:
            doc_annotations = doc_annotations.filter(
                annotation_label_id__in=label_pks_in_corpus
            )
    else:  # CORPUS_LABELSET_ONLY
        label_pks_in_corpus = (
            Annotation.objects.filter(corpus_id=corpus_id)
            .values_list("annotation_label_id", flat=True)
            .distinct()
        )
        doc_annotations = doc_annotations.filter(
            annotation_label_id__in=label_pks_in_corpus
        )

    token_annotations = doc_annotations.filter(
        annotation_label__label_type=TOKEN_LABEL,
    ).order_by("page")

    if not doc.pawls_parse_file.name or not doc.pdf_file.name:
        raise ValueError(f"Document {doc_id} is missing pawls_parse_file or pdf_file")
    file_object = default_storage.open(doc.pawls_parse_file.name)
    pawls_tokens = expand_pawls_pages(json.loads(file_object.read().decode("utf-8")))

    pdf_object = default_storage.open(doc.pdf_file.name)
    pdf_bytes = pdf_object.read()
    pdf_images = split_pdf_into_images(
        pdf_bytes, storage_path=f"user_{user_id}/pdf_page_images"
    )
    pdf_images_and_data = list(
        zip(
            [doc_id for _ in range(len(pdf_images))],
            pdf_images,
            ["PNG" for _ in range(len(pdf_images))],
        )
    )
    logger.info(f"convert_doc_to_funsd() - pdf_images: {pdf_images}")

    # NOTE: Assumes at most one annotation per page per Annotation object.
    # Multi-page annotations store per-page JSON keyed by page number, and
    # the FUNSD export iterates those keys independently.
    for annotation in token_annotations:

        base_id = f"{annotation.id}"

        """

        FUNSD format description from paper:

        Each form is encoded in a JSON file. We represent a form
        as a list of semantic entities that are interlinked. A semantic
        entity represents a group of words that belong together from
        a semantic and spatial standpoint. Each semantic entity is de-
        scribed by a unique identifier, a label (i.e., question, answer,
        header or other), a bounding box, a list of links with other
        entities, and a list of words. Each word is represented by its
        textual content and its bounding box. All the bounding boxes
        are represented by their coordinates following the schema
        box = [xlef t, ytop, xright, ybottom]. The links are directed
        and formatted as [idf rom, idto], where id represents the
        semantic entity identifier. The dataset statistics are shown in
        Table I. Even with a limited number of annotated documents,
        we obtain a large number of word-level annotations (> 30k)

         {
            "box": [
                446,
                257,
                461,
                267
            ],
            "text": "cc:",
            "label": "question",
            "words": [
                {
                    "box": [
                        446,
                        257,
                        461,
                        267
                    ],
                    "text": "cc:"
                }
            ],
            "linking": [
                [
                    1,
                    20
                ]
            ],
            "id": 1
        },
        """

        label = annotation.annotation_label

        for page_data in iter_page_annotations(
            annotation.json, raw_text=annotation.raw_text or ""
        ):
            expanded_tokens = []
            for token_index in page_data.token_indices:
                token = pawls_tokens[page_data.page_index]["tokens"][token_index]
                expanded_tokens.append(pawls_token_to_funsd_token(token))

            funsd_annotation: FunsdAnnotationType = {
                "id": f"{base_id}-{page_data.page_index}",
                "linking": [],  # Relationship linking is not yet wired into FUNSD export
                "text": page_data.raw_text,
                "box": pawls_bbox_to_funsd_box(
                    cast(BoundingBoxPythonType, page_data.bounds)
                ),
                "label": f"{label.text}",
                "words": expanded_tokens,
                "parent_id": None,
            }

            page = page_data.page_index
            if page in annotation_map:
                annotation_map[page].append(funsd_annotation)
            else:
                annotation_map[page] = [funsd_annotation]

    return doc_id, annotation_map, pdf_images_and_data


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def extract_thumbnail(self, doc_id: int) -> None:
    """
    Extracts a thumbnail for a document using a thumbnail generator based on the document's file type.
    The generator is selected from the pipeline thumbnailers that support the document's MIME type.

    This Celery task will retry up to 3 times (with a 60-second wait between attempts)
    in case of transient errors or exceptions.

    Args:
        self: Celery task instance (passed automatically when bind=True).
        doc_id (int): The ID of the document to process.

    Returns:
        None
    """
    logger.info(f"[extract_thumbnail] Extracting thumbnail for doc {doc_id}")

    # Fetch the document
    try:
        document: Document = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        logger.error(f"Document with id {doc_id} does not exist.")
        return

    file_type: str = document.file_type

    # CAML/markdown files have no visual content to thumbnail.
    # Defensive check - the signal in documents/signals.py prevents the
    # pipeline from being queued, but this guards against direct calls.
    if file_type == MARKDOWN_MIME_TYPE:
        logger.info(f"[extract_thumbnail] Skipping thumbnail for markdown doc {doc_id}")
        return

    # Check for preferred thumbnailer in database settings first
    from opencontractserver.documents.models import PipelineSettings

    pipeline_settings = PipelineSettings.get_instance()
    preferred_thumbnailer = pipeline_settings.get_preferred_thumbnailer(file_type)

    thumbnailer_class: type[BaseThumbnailGenerator] | None = None

    if preferred_thumbnailer:
        # Try to load the preferred thumbnailer
        try:
            thumbnailer_class = cast(
                type[BaseThumbnailGenerator],
                get_component_by_name(preferred_thumbnailer),
            )
            logger.info(
                f"Using preferred thumbnailer '{preferred_thumbnailer}' for doc {doc_id}"
            )
        except ValueError:
            logger.warning(
                f"Preferred thumbnailer '{preferred_thumbnailer}' not found, "
                "falling back to auto-discovery"
            )

    if not thumbnailer_class:
        # Fall back to auto-discovered thumbnailers for the MIME type.
        # ``get_components_by_mimetype`` accepts either a ``FileTypeEnum`` or a
        # raw MIME string (and resolves the latter via
        # ``FileTypeEnum.from_mimetype`` internally), so passing ``file_type``
        # directly is correct — wrapping with ``FileTypeEnum(file_type)``
        # would raise ``ValueError`` because the enum members are short
        # labels (``"pdf"``, ``"txt"``), not MIME strings.
        components = get_components_by_mimetype(file_type)
        thumbnailers = components.get("thumbnailers", [])

        if not thumbnailers:
            logger.error(f"No thumbnailer found for file type '{file_type}'.")
            return

        # Use the first available thumbnailer
        thumbnailer_class = cast(type[BaseThumbnailGenerator], thumbnailers[0])
        logger.info(
            f"Using auto-discovered thumbnailer '{thumbnailer_class.__name__}' "
            f"for doc {doc_id}"
        )

    try:
        thumbnailer: BaseThumbnailGenerator = thumbnailer_class()
        thumbnail_file = thumbnailer.generate_thumbnail(doc_id)
        if thumbnail_file:
            logger.info(
                f"[extract_thumbnail] Thumbnail extracted and saved for doc {doc_id}"
            )
        else:
            logger.error(
                f"[extract_thumbnail] Thumbnail generation failed for doc {doc_id}"
            )
    except Exception as e:
        logger.error(
            f"[extract_thumbnail] Failed to extract thumbnail for doc {doc_id}: {e}"
        )
        # Raise for Celery to attempt retries
        raise


@shared_task
def retry_document_processing(user_id: int, doc_id: int) -> dict[str, Any]:
    """
    Re-attempt processing for a failed document (manual trigger).

    This task is used when automatic retries have been exhausted due to transient
    infrastructure issues that are later resolved. Users can manually trigger
    reprocessing via the GraphQL API.

    The task:
    1. Verifies the document is in FAILED state
    2. Resets the processing state (status=PENDING, clears error fields)
    3. Re-triggers the document processing pipeline (thumbnail + ingest + unlock)

    Args:
        user_id (int): The ID of the user requesting the retry.
        doc_id (int): The ID of the document to reprocess.

    Returns:
        dict: Status information with keys:
            - status: "queued" (success) or "error"
            - doc_id: The document ID
            - message: Status message
    """
    from celery import chain

    from opencontractserver.types.enums import PermissionTypes

    logger.info(
        f"[retry_document_processing] Manual retry requested for doc {doc_id} "
        f"by user {user_id}"
    )

    # Defense-in-depth permission check (companion to T-7 fix in ingest_doc).
    # The retry GraphQL mutation should have already authorized this, but a
    # task that mutates state must not trust upstream callers blindly.
    User = get_user_model()
    try:
        user_obj = User.objects.get(pk=user_id)
        document_obj = Document.objects.get(pk=doc_id)
    except User.DoesNotExist:
        logger.error(
            "[SECURITY] [retry_document_processing] user_id=%s does "
            "not exist; refusing to retry doc_id=%s.",
            user_id,
            doc_id,
        )
        return {
            "status": "error",
            "doc_id": doc_id,
            "message": "Invalid user for retry",
        }
    except Document.DoesNotExist:
        # Log at WARNING (not ERROR): a missing document on retry is more
        # likely a benign race (admin deleted it between mutation enqueue
        # and worker pickup) than an attack. Logging it gives ops visibility
        # if a sequential-id probe ever shows up in the wild.
        logger.warning(
            "[retry_document_processing] doc_id=%s does not exist; "
            "refusing to retry on behalf of user_id=%s.",
            doc_id,
            user_id,
        )
        return {
            "status": "error",
            "doc_id": doc_id,
            "message": "Document not found",
        }
    if not document_obj.user_can(user_obj, PermissionTypes.UPDATE):
        logger.error(
            f"[SECURITY] [retry_document_processing] user_id={user_id} "
            f"lacks UPDATE permission on doc_id={doc_id}; refusing to retry."
        )
        return {
            "status": "error",
            "doc_id": doc_id,
            "message": "User lacks permission to retry this document",
        }

    # Atomic update: only reset if document is in FAILED state
    # This prevents race conditions if user clicks retry multiple times
    updated_count = Document.objects.filter(
        pk=doc_id,
        processing_status=DocumentProcessingStatus.FAILED,
    ).update(
        processing_status=DocumentProcessingStatus.PENDING,
        processing_error="",
        processing_error_traceback="",
        processing_started=timezone.now(),
        processing_finished=None,
        backend_lock=True,  # Lock document during reprocessing
    )

    if updated_count == 0:
        # Either document doesn't exist or isn't in FAILED state
        try:
            document = Document.objects.get(pk=doc_id)
            return {
                "status": "error",
                "doc_id": doc_id,
                "message": (
                    f"Document is not in failed state "
                    f"(current status: {document.processing_status})"
                ),
            }
        except Document.DoesNotExist:
            return {
                "status": "error",
                "doc_id": doc_id,
                "message": "Document not found",
            }

    logger.info(
        f"[retry_document_processing] Reset document {doc_id} state, "
        "triggering reprocessing pipeline"
    )

    # Re-trigger the processing pipeline. link_error marks the document FAILED
    # if any task in the chain raises (halting the chain before
    # set_doc_lock_state finalizes status), so a failed retry can't strand the
    # doc back in PROCESSING.
    chain(
        extract_thumbnail.si(doc_id=doc_id),
        ingest_doc.si(user_id=user_id, doc_id=doc_id),
        set_doc_lock_state.si(locked=False, doc_id=doc_id),
    ).apply_async(link_error=mark_doc_failed_on_chain_error.s(doc_id=doc_id))

    return {
        "status": "queued",
        "doc_id": doc_id,
        "message": "Document reprocessing has been queued",
    }


@celery_app.task()
def remap_pending_annotations(
    *args, doc_id: int, run_id: str | uuid.UUID | None = None
) -> dict[str, Any]:
    """Anchor a document's PendingDocumentAnnotations onto pipeline output.

    Runs AFTER ``ingest_doc`` in the import chain, so PAWLs / text layer exist.
    No-op when there is no matching pending row.

    ``run_id`` scopes processing to a single ingestion run. The standard
    post_save chain calls with ``run_id=None`` ("apply every PENDING row for
    this doc") — correct because rows are created in the same transaction as the
    document, before the on_commit chain runs. An explicit caller can pass a run
    id to apply only that run's deferred set even when unrelated PENDING rows
    exist for the doc.

    ``*args`` absorbs the previous chain task's return value. Every dispatch site
    uses ``.si()`` (immutable signature), so ``*args`` is always empty in
    practice; it is retained only so a future caller wiring this with ``.s()``
    does not break on the upstream task's positional return.

    Processes *all* matching PENDING rows for the document, not just the first: a
    retry or a bug could leave more than one PENDING row, and a single-row
    implementation would silently orphan the extras forever (review finding #2).
    """
    qs = PendingDocumentAnnotations.objects.filter(
        document_id=doc_id, status=PendingDocumentAnnotations.Status.PENDING
    )
    if run_id is not None:
        qs = qs.filter(ingestion_run_id=run_id)
    pending_rows = list(qs.order_by("id"))
    if not pending_rows:
        return {"doc_id": doc_id, "skipped": "no pending annotations"}

    # Load the document ONCE for the whole batch (review finding #1). Every row
    # targets the same document, so re-fetching it per row was wasted work and —
    # worse — if the document were deleted partway through the loop the later
    # rows would raise an unhandled ``Document.DoesNotExist`` and stay PENDING
    # forever. Resolving it up front means a deleted document fails *all* rows
    # cleanly instead of orphaning the tail.
    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        logger.warning(
            "remap_pending_annotations: document %s no longer exists; "
            "failing %s pending row(s).",
            doc_id,
            len(pending_rows),
        )
        for pending in pending_rows:
            pending.status = PendingDocumentAnnotations.Status.FAILED
            pending.report = [{"error": f"document {doc_id} no longer exists"}]
            try:
                pending.save(update_fields=["status", "report"])
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "remap_pending_annotations: could not mark pending row %s "
                    "FAILED after document %s vanished.",
                    pending.pk,
                    doc_id,
                )
        # The rows are handled (FAILED), so a run gated on them must still get a
        # chance to finalize for its surviving documents.
        _trigger_corpus_import_finalize(pending_rows)
        return {"doc_id": doc_id, "failed": "document does not exist"}

    # Label lookups are keyed by the corpus' label_set; rows for one document
    # normally share a corpus, so cache per label_set_id rather than rebuilding
    # the queryset for every row (review finding #2). Keyed by label_set_id (not
    # corpus) so the rare multi-corpus batch is still correct.
    label_cache: dict[Any, tuple[dict[str, Any], dict[str, Any]]] = {}
    per_row = [
        _remap_one_pending_row(pending, doc, label_cache) for pending in pending_rows
    ]

    # Relationship fan-in trigger (reingest-import mode). Collect the distinct
    # non-null ingestion_run_ids of the rows just handled and give each a chance
    # to finalize its corpus import. Two-stage guard: the ``is not None`` filter
    # short-circuits ordinary single-doc uploads (run_id is NULL) before any
    # query, and ``_maybe_finalize_corpus_import`` itself is a no-op when no
    # ``PendingCorpusImport`` coordination row exists for the run (a
    # relationship-free reingest run mints a run id but no row).
    _trigger_corpus_import_finalize(pending_rows)

    if len(per_row) == 1:
        return per_row[0]
    # Multiple PENDING rows for one document: aggregate so none is orphaned.
    return {
        "doc_id": doc_id,
        "rows_processed": len(per_row),
        "results": per_row,
    }


def _trigger_corpus_import_finalize(
    handled_rows: list[PendingDocumentAnnotations],
) -> None:
    """Give each handled row's import run a chance to finalize its fan-in.

    See ``_maybe_finalize_corpus_import`` for the exactly-once guarantee. The
    ``ingestion_run_id is not None`` filter is the first guard stage (ordinary
    uploads skip here before any query).
    """
    run_ids = {
        row.ingestion_run_id for row in handled_rows if row.ingestion_run_id is not None
    }
    for run_id in run_ids:
        _maybe_finalize_corpus_import(run_id)


def _wire_pending_relationships(
    rel_specs: list[dict],
    annot_id_map: dict[Any, int],
    doc: Document,
    corpus: Any,
    user_id: int,
    report: list[dict],
) -> tuple[int, int]:
    """Wire a pending row's annotation-to-annotation relationships.

    ``rel_specs`` are the verbatim sidecar relationship dicts (each carrying a
    label plus ``source_annotation_ids`` / ``target_annotation_ids`` that
    reference the sidecar's own annotation ids). ``annot_id_map`` is the
    export-local-id -> new-Annotation-pk map returned by ``import_annotations``;
    only annotations that anchored AND whose label resolved appear in it, so an
    endpoint can legitimately be missing.

    Each relationship's endpoints are resolved against ``annot_id_map`` and the
    unresolved ones dropped. A relationship that keeps a usable label and at
    least one resolved source AND one resolved target is imported — its
    ``RELATIONSHIP_LABEL`` is auto-created in the corpus labelset if absent,
    mirroring the document-to-document ``relationships.csv`` path. Everything
    else is dropped with a ``report`` entry so the loss is never silent.

    Returns ``(created, dropped)``.
    """
    if not rel_specs:
        return 0, 0

    if corpus is None:
        # No corpus -> no labelset to host the RELATIONSHIP_LABEL (and the
        # annotations themselves all failed for the same reason). Drop every
        # relationship with a clear reason rather than raising.
        for spec in rel_specs:
            report.append(
                {
                    "id": spec.get("id"),
                    "rawText": "",
                    "dropped": True,
                    "reason": "relationship skipped — pending row has no corpus",
                }
            )
        return 0, len(rel_specs)

    # ``import_annotations`` keys the map by the raw export-local id (often an
    # int); a sidecar relationship may reference the same id as a str. Accept
    # both forms so an int/str mismatch doesn't spuriously drop an endpoint.
    resolvable: dict[Any, int] = dict(annot_id_map)
    for old_id, new_pk in annot_id_map.items():
        resolvable.setdefault(str(old_id), new_pk)

    rel_label_lookup: dict[str, Any] = {}
    importable: list[dict] = []
    dropped = 0
    for spec in rel_specs:
        label_name = spec.get("relationshipLabel") or spec.get("label")
        source_ids = spec.get("source_annotation_ids") or []
        target_ids = spec.get("target_annotation_ids") or []
        resolved_sources = [i for i in source_ids if i in resolvable]
        resolved_targets = [i for i in target_ids if i in resolvable]

        if not label_name or not resolved_sources or not resolved_targets:
            dropped += 1
            if not label_name:
                reason = "relationship missing label"
            elif not resolved_sources and not resolved_targets:
                reason = (
                    "relationship endpoints unresolved — neither source nor "
                    "target annotation survived anchoring"
                )
            elif not resolved_sources:
                reason = "relationship has no resolvable source annotation"
            else:
                reason = "relationship has no resolvable target annotation"
            report.append(
                {
                    "id": spec.get("id"),
                    "rawText": "",
                    "dropped": True,
                    "reason": reason,
                }
            )
            continue

        if label_name not in rel_label_lookup:
            rel_label_lookup[label_name] = corpus.ensure_label_and_labelset(
                label_text=label_name,
                creator_id=user_id,
                label_type=LabelType.RELATIONSHIP_LABEL,
            )

        importable.append(
            {
                "id": spec.get("id"),
                "relationshipLabel": label_name,
                "source_annotation_ids": resolved_sources,
                "target_annotation_ids": resolved_targets,
                # Producer relationships are never structural — structural
                # relationships are regenerated by the parser (the same rule the
                # anchor step applies to structural annotations).
                "structural": False,
            }
        )

    if importable:
        import_relationships(
            user_id=user_id,
            doc_obj=doc,
            corpus_obj=corpus,
            relationships_data=cast(
                list[OpenContractsRelationshipPythonType], importable
            ),
            label_lookup=rel_label_lookup,
            annotation_id_map=resolvable,
        )

    return len(importable), dropped


def _remap_one_pending_row(
    pending: PendingDocumentAnnotations,
    doc: Document,
    label_cache: dict[Any, tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    """Anchor and import a single ``PendingDocumentAnnotations`` row.

    ``doc`` is resolved once by the caller and shared across rows;
    ``label_cache`` memoises ``(label_lookup, doc_label_lookup)`` per
    label_set_id so the label queryset is not rebuilt for every row.
    """
    doc_id = doc.pk
    corpus = pending.corpus
    user_id = pending.creator_id
    payload = pending.payload or {}
    dumb_anns = payload.get("annotations", []) or []
    doc_label_names = payload.get("doc_labels", []) or []
    rel_specs = payload.get("relationships", []) or []

    is_pdf = (doc.file_type or "").lower() == "application/pdf"
    pawls: list[dict] = []
    content = ""
    try:
        if is_pdf and doc.pawls_parse_file:
            doc.pawls_parse_file.seek(0)
            pawls = expand_pawls_pages(
                json.loads(doc.pawls_parse_file.read().decode("utf-8"))
            )
        if doc.txt_extract_file:
            doc.txt_extract_file.seek(0)
            content = doc.txt_extract_file.read().decode("utf-8")
    except Exception as exc:
        pending.status = PendingDocumentAnnotations.Status.FAILED
        pending.report = [{"error": f"could not read doc layers: {exc}"}]
        # Guard the status save itself (review finding #3): if the DB connection
        # is wedged the save can also raise, which would otherwise leave the row
        # stuck PENDING with no trace. Log so the failure is at least visible.
        try:
            pending.save(update_fields=["status", "report"])
        except Exception:
            logger.exception(
                "remap_pending_annotations: failed to mark pending row %s FAILED "
                "after a doc-layer read error on doc %s.",
                pending.pk,
                doc_id,
            )
        return {"doc_id": doc_id, "failed": str(exc)}

    anchored, report = anchor_annotations(
        dumb_anns, is_pdf=is_pdf, pawls=pawls, content=content
    )

    # Persist annotation_json in the canonical compact v2 encoding (``{"v": 2,
    # "p": {...}}`` with range-encoded token indices) — the same shape the
    # parser writes for structural annotations, so remapped and parser-produced
    # annotations are stored consistently. ``anchor_annotations`` returns the
    # explicit verbose shape; we compact it here at the storage boundary. Span
    # annotations (``{start, end, text}``) are returned unchanged by the encoder.
    for a in anchored:
        a["annotation_json"] = compact_annotation_json(a.get("annotation_json"))

    # Build label_lookup keyed by lbl.text — exactly as import_annotations
    # looks up: ``label_name = annotation_data["annotationLabel"]``;
    # ``label_obj = label_lookup.get(label_name)``. Memoised per label_set_id in
    # ``label_cache`` so a multi-row batch doesn't rebuild the queryset per row.
    label_set_id = corpus.label_set_id if corpus is not None else None
    if corpus is None:
        # Diagnostic: with no corpus there is no labelset, so ``label_lookup``
        # is built empty and EVERY annotation is dropped with "label not found
        # in corpus labelset". The row will (correctly) end up FAILED, but the
        # report alone reads like a bad labels.json rather than a missing
        # corpus. Surface the real root cause for whoever inspects the row.
        logger.warning(
            "remap_pending_annotations: pending row %s for doc %s has no "
            "corpus; label lookup will be empty and all annotations will be "
            "dropped.",
            pending.pk,
            doc_id,
        )
    cached = label_cache.get(label_set_id)
    if cached is None:
        label_lookup = {}
        doc_label_lookup = {}
        if label_set_id:
            for lbl in AnnotationLabel.objects.filter(
                included_in_labelset=label_set_id
            ):
                label_lookup[lbl.text] = lbl
                if lbl.label_type == DOC_TYPE_LABEL:
                    doc_label_lookup[lbl.text] = lbl
        cached = (label_lookup, doc_label_lookup)
        label_cache[label_set_id] = cached
    label_lookup, doc_label_lookup = cached

    # Atomicity (review finding #3): create the annotations AND flip the row's
    # status in one transaction. If the status/id_map save failed after
    # ``import_annotations`` committed its rows, the annotations would be live but
    # the pending row would stay PENDING — and the next retry of
    # ``remap_pending_annotations`` would re-run ``import_annotations`` and create
    # duplicates. Wrapping both writes closes that window: a failure rolls the
    # annotations back too, so the retry starts clean.
    with transaction.atomic():
        # Concurrent-retry guard (review finding #2): Celery is at-least-once, so
        # a duplicated task (or a manual admin replay) could run two copies of
        # this remap for the same PENDING row. Re-fetch the row FOR UPDATE with
        # SKIP LOCKED and re-assert it is still PENDING before importing. If a
        # sibling worker already holds the lock (``None``) or has already flipped
        # the status, we bail without calling ``import_annotations`` — otherwise
        # both workers would create duplicate annotations, since each one's
        # ``transaction.atomic()`` commits independently.
        locked = (
            PendingDocumentAnnotations.objects.select_for_update(skip_locked=True)
            .filter(pk=pending.pk)
            .first()
        )
        if locked is None or locked.status != PendingDocumentAnnotations.Status.PENDING:
            logger.info(
                "remap_pending_annotations: pending row %s for doc %s already "
                "claimed/processed by a concurrent run; skipping.",
                pending.pk,
                doc_id,
            )
            return {"doc_id": doc_id, "skipped": "claimed by concurrent run"}

        # Creates one Annotation per anchored item whose label resolves (and wires
        # parent relationships + dispatches embeddings as a side effect). The
        # return map (export-local id -> new Annotation pk) drives the
        # annotation-to-annotation relationship wiring below and is persisted on
        # the row's ``id_map`` so the mapping survives without a backfill.
        annot_id_map = import_annotations(
            user_id=user_id,
            doc_obj=doc,
            corpus_obj=corpus,
            annotations_data=cast(list[OpenContractsAnnotationPythonType], anchored),
            label_lookup=label_lookup,
        )
        # JSON object keys are strings; export-local ids may be int or str.
        pending.id_map = {
            str(old_id): new_pk for old_id, new_pk in annot_id_map.items()
        }

        # Wire intra-document annotation-to-annotation relationships now that the
        # annotation id_map exists. Sharing the annotation import's atomic block
        # means a relationship failure rolls the annotations back too, and the
        # concurrent-retry guard above prevents a duplicated task from
        # double-creating. Endpoints that did not survive anchoring are dropped
        # and recorded on ``report`` (never silently).
        relationships_created, relationships_dropped = _wire_pending_relationships(
            rel_specs, annot_id_map, doc, corpus, user_id, report
        )

        # ------------------------------------------------------------------
        # Close the label-resolution silent-failure gap.
        #
        # import_annotations() SILENTLY SKIPS any anchored annotation whose
        # ``annotationLabel`` is not in ``label_lookup`` (e.g. the producer's
        # labels.json declared the label wrong / not at all). Without the
        # bookkeeping below, the remap would report status=DONE even when an
        # annotation was anchored but then dropped at import for an unresolved
        # label — a real, invisible loss. We detect every anchored annotation
        # whose label is unresolvable, append a ``dropped`` report entry citing
        # the missing label, and surface the count in the return dict.
        # ------------------------------------------------------------------
        resolvable_labels = set(label_lookup)
        label_unresolved = 0
        for a in anchored:
            label_name = a.get("annotationLabel")
            if label_name not in resolvable_labels:
                label_unresolved += 1
                report.append(
                    {
                        "id": a.get("id"),
                        "rawText": report_rawtext_preview(a.get("rawText")),
                        "dropped": True,
                        "reason": (
                            f"label '{label_name}' not found in corpus labelset"
                        ),
                    }
                )

        doc_labels_created = 0
        doc_labels_unresolved = 0
        for name in doc_label_names:
            label_obj = doc_label_lookup.get(name)
            if label_obj:
                annot_obj = Annotation.objects.create(
                    annotation_label=label_obj,
                    annotation_type=DOC_TYPE_LABEL,
                    document=doc,
                    corpus=corpus,
                    creator_id=user_id,
                )
                set_permissions_for_obj_to_user(
                    user_id, annot_obj, [PermissionTypes.ALL], is_new=True
                )
                doc_labels_created += 1
            else:
                # Parity with the token-label gap above: never drop a doc-label
                # silently. Record it so an unresolved labels.json entry is
                # visible.
                doc_labels_unresolved += 1
                report.append(
                    {
                        "id": None,
                        "rawText": "",
                        "dropped": True,
                        "reason": f"doc_label '{name}' not found in corpus labelset",
                    }
                )

        # ``import_annotations`` creates one Annotation per anchored item whose
        # label resolves, so the number actually created is ``len(anchored)``
        # minus the unresolved-label drops. We deliberately do NOT use
        # ``len(annot_id_map)`` here: that map only contains entries for
        # annotations that carried an export-local ``id`` (importing.py only
        # records ``old_id`` when non-None), so id-less-but-successfully-created
        # annotations would be miscounted as zero and wrongly flip the row to
        # FAILED.
        raw_created = len(anchored) - label_unresolved
        if raw_created < 0:
            # Should be impossible: ``label_unresolved`` is counted over the same
            # ``anchored`` list, so it can never exceed ``len(anchored)``. If a
            # future bookkeeping change makes it negative, clamp to 0 (so the row
            # is correctly marked FAILED below rather than a silent DONE) and
            # shout.
            logger.warning(
                "remap_pending_annotations: negative created count for doc %s "
                "(anchored=%s, label_unresolved=%s); clamping to 0",
                doc_id,
                len(anchored),
                label_unresolved,
            )
        created = max(0, raw_created)
        # Nothing landed but the producer DID ask for something to land (some
        # annotation/doc-label was dropped) → a real failure, not a silent DONE.
        # This covers BOTH failure modes uniformly:
        #   * anchored but every one dropped at import for an unresolved label
        #     (``anchored`` non-empty, ``created == 0``), and
        #   * every annotation failed to anchor in the first place (geometry
        #     miss + rawText not found), so ``anchored == []`` — the previous
        #     ``anchored and created == 0`` guard short-circuited to DONE here
        #     and mis-reported a total anchor failure as success.
        # An empty payload (nothing requested, nothing dropped) stays DONE.
        # ``relationships_created`` is folded in so a sidecar that landed only
        # relationships (no new annotations — e.g. all endpoints already
        # existed) is not mis-marked FAILED. In practice relationships need
        # freshly-anchored annotations, so this is belt-and-suspenders.
        nothing_landed = (
            created == 0 and doc_labels_created == 0 and relationships_created == 0
        )
        any_dropped = any(r.get("dropped") for r in report)
        if nothing_landed and any_dropped:
            pending.status = PendingDocumentAnnotations.Status.FAILED
        else:
            pending.status = PendingDocumentAnnotations.Status.DONE
        pending.report = report
        pending.save(update_fields=["status", "report", "id_map"])
    return {
        "doc_id": doc_id,
        "status": pending.status,
        "anchored": created,
        "dropped": sum(1 for r in report if r.get("dropped")),
        "label_unresolved": label_unresolved,
        "doc_labels": doc_labels_created,
        "doc_labels_unresolved": doc_labels_unresolved,
        "relationships": relationships_created,
        "relationships_dropped": relationships_dropped,
    }


def _maybe_finalize_corpus_import(run_id: str | uuid.UUID) -> None:
    """Exactly-once trigger for a reingest-import's relationship fan-in.

    Called from two observers — the post-loop call in ``_import_corpus`` (once
    every pending row is enumerated and the coordination row is ``READY``) and
    from ``remap_pending_annotations`` after each document's remap completes.
    Whoever both sees the run complete (no ``PENDING`` rows remain) *and* wins
    the ``select_for_update(skip_locked=True)`` lock on the ``READY`` row flips
    it to ``FINALIZING`` and dispatches ``finalize_corpus_import_relationships``
    exactly once — robust to the post-loop / last-remap race and to Celery
    at-least-once redelivery.

    A no-op when no coordination row exists for ``run_id`` (relationship-free
    runs mint a run id but no row), when the row is not yet ``READY`` (still
    enumerating), when another observer already claimed it (status moved past
    ``READY``), or when ``PENDING`` rows for the run still remain.
    """
    with transaction.atomic():
        row = (
            PendingCorpusImport.objects.select_for_update(skip_locked=True)
            .filter(import_run_id=run_id, status=PendingCorpusImport.Status.READY)
            .first()
        )
        if row is None:
            # Absent, not enumerated yet, or already claimed by another observer.
            return
        remaining = PendingDocumentAnnotations.objects.filter(
            ingestion_run_id=run_id,
            status=PendingDocumentAnnotations.Status.PENDING,
        ).exists()
        if remaining:
            # Not all docs done; the lock releases on block exit and a later
            # observer (the last remap) will re-attempt the claim.
            return
        row.status = PendingCorpusImport.Status.FINALIZING
        row.save(update_fields=["status", "updated_at"])

    transaction.on_commit(
        lambda: finalize_corpus_import_relationships.delay(str(run_id))
    )


@shared_task
def finalize_corpus_import_relationships(run_id: str) -> dict[str, Any]:
    """Wire a reingest-import run's corpus-level relationships after all remaps.

    Aggregates every ``DONE`` ``PendingDocumentAnnotations.id_map`` for the run
    (export-local annotation id -> new Annotation pk), rebuilds the
    ``(text, label_type)`` label lookup from the corpus labelset, and calls the
    existing ``_import_v2_relationships`` — which already skips structural
    relationships and drops endpoints missing from the map, so partial remaps
    degrade gracefully.

    Idempotent / retry-safe (Celery is at-least-once): accepts the row only in a
    re-runnable state (``FINALIZING`` from a normal dispatch, or ``FAILED`` from
    a prior attempt that errored mid-wiring); any other state (``DONE``,
    missing) is a no-op so a stray redelivery after success never double-wires.
    The wiring + ``DONE`` flip run in one ``transaction.atomic()`` so a crash
    before ``DONE`` rolls the partial relationship writes back and the retry
    starts clean.
    """
    # Lazy import to avoid a tasks <-> tasks import cycle at module load.
    from opencontractserver.tasks.import_tasks_v2 import _import_v2_relationships

    row = PendingCorpusImport.objects.filter(import_run_id=run_id).first()
    if row is None:
        return {"run_id": run_id, "skipped": "no coordination row"}
    if row.status not in (
        PendingCorpusImport.Status.FINALIZING,
        PendingCorpusImport.Status.FAILED,
    ):
        return {"run_id": run_id, "skipped": f"status {row.status}"}

    try:
        with transaction.atomic():
            # Re-claim FOR UPDATE so two concurrent finalizers can't both wire.
            locked = (
                PendingCorpusImport.objects.select_for_update()
                .filter(import_run_id=run_id)
                .first()
            )
            if locked is None or locked.status not in (
                PendingCorpusImport.Status.FINALIZING,
                PendingCorpusImport.Status.FAILED,
            ):
                return {"run_id": run_id, "skipped": "already finalized"}
            locked.status = PendingCorpusImport.Status.FINALIZING
            locked.save(update_fields=["status", "updated_at"])

            corpus = locked.corpus

            # Aggregate the per-document id_maps recorded by each remap. Only
            # ``id_map`` is needed, so pull it with ``values_list`` rather than
            # hydrating each row's full ``payload`` JSON (cheaper, and matters if
            # the fan-in is later reused for large bulk-ZIP imports — §9).
            aggregated_id_map: dict[str, int] = {}
            for row_id_map in PendingDocumentAnnotations.objects.filter(
                ingestion_run_id=run_id,
                status=PendingDocumentAnnotations.Status.DONE,
            ).values_list("id_map", flat=True):
                for old_id, new_pk in (row_id_map or {}).items():
                    aggregated_id_map[str(old_id)] = new_pk

            # Rebuild the (text, label_type)-keyed label lookup from the corpus
            # labelset — relationship labels are present (the export writes
            # RELATIONSHIP_LABEL into text_labels).
            label_lookup_by_text: dict[tuple[str, str], AnnotationLabel] = {}
            if corpus.label_set_id:
                for lbl in AnnotationLabel.objects.filter(
                    included_in_labelset=corpus.label_set_id
                ):
                    label_lookup_by_text[(lbl.text, lbl.label_type)] = lbl

            _import_v2_relationships(
                locked.relationships_payload or [],
                corpus,
                cast("dict[str | int, int]", aggregated_id_map),
                label_lookup_by_text,
                locked.creator,
            )

            locked.status = PendingCorpusImport.Status.DONE
            locked.report = {
                "relationships_in_payload": len(locked.relationships_payload or []),
                "id_map_size": len(aggregated_id_map),
            }
            locked.save(update_fields=["status", "report", "updated_at"])
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "finalize_corpus_import_relationships failed for run %s: %s",
            run_id,
            exc,
            exc_info=True,
        )
        # ``updated_at`` is ``auto_now`` but bulk ``.update()`` bypasses it;
        # stamp it so the admin panel surfaces recently-failed runs (§9).
        PendingCorpusImport.objects.filter(import_run_id=run_id).update(
            status=PendingCorpusImport.Status.FAILED,
            report={"error": str(exc)},
            updated_at=timezone.now(),
        )
        return {"run_id": run_id, "failed": str(exc)}

    return {
        "run_id": run_id,
        "status": PendingCorpusImport.Status.DONE,
        "id_map_size": len(aggregated_id_map),
    }
