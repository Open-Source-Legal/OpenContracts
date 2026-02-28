from __future__ import annotations

import enum
import json
import logging
import traceback
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone
from pydantic import validate_call

from config import celery_app
from opencontractserver.annotations.models import TOKEN_LABEL, Annotation
from opencontractserver.constants import (
    MAX_PROCESSING_ERROR_LENGTH,
    MAX_PROCESSING_TRACEBACK_LENGTH,
)
from opencontractserver.constants.truncation import (
    MAX_DOC_TITLE_FALLBACK_LENGTH,
    MAX_NOTIFICATION_ERROR_LENGTH,
)
from opencontractserver.documents.models import Document, DocumentProcessingStatus
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.notifications.signals import (
    broadcast_notification_via_websocket,
)
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.pipeline.utils import (
    get_component_by_name,
    get_components_by_mimetype,
)
from opencontractserver.types.dicts import (
    AnnotationLabelPythonType,
    FunsdAnnotationType,
    FunsdTokenType,
    LabelLookupPythonType,
    OpenContractDocExport,
    PawlsTokenPythonType,
)
from opencontractserver.types.enums import AnnotationFilterMode
from opencontractserver.utils.etl import build_document_export, pawls_bbox_to_funsd_box
from opencontractserver.utils.files import split_pdf_into_images
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
        _create_document_processed_notifications(document, corpus_data)

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
    document: Document, corpus_data: list[dict]
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
    corpus_creator_ids = {
        data.get("corpus__creator_id")
        for data in corpus_data
        if data.get("corpus__creator_id")
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
        parser_class = get_component_by_name(parser_name)
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
    str | None,
    str | None,
    OpenContractDocExport | None,
    dict[str | int, AnnotationLabelPythonType],
    dict[str | int, AnnotationLabelPythonType],
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
) -> tuple[int, dict[int | str, list[dict[str, Any]]], list[tuple[int, str, str]]]:
    def pawls_token_to_funsd_token(pawls_token: PawlsTokenPythonType) -> FunsdTokenType:
        pawls_xleft = pawls_token["x"]
        pawls_ybottom = pawls_token["y"]
        pawls_ytop = pawls_xleft + pawls_token["width"]
        pawls_xright = pawls_ybottom + pawls_token["height"]
        funsd_token = {
            "text": pawls_token["text"],
            # In FUNSD, this must be serialzied to list but that's done by json.dumps and tuple has better typing
            # control (fixed length, positional datatypes, etc.)
            "box": (pawls_xleft, pawls_ytop, pawls_xright, pawls_ybottom),
        }
        return funsd_token

    doc = Document.objects.get(id=doc_id)

    annotation_map: dict[int, list[dict]] = {}

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

    file_object = default_storage.open(doc.pawls_parse_file.name)
    pawls_tokens = json.loads(file_object.read().decode("utf-8"))

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

        annot_json = annotation.json
        label = annotation.annotation_label

        for page in annot_json.keys():

            page_annot_json = annot_json[page]
            page_token_refs = page_annot_json["tokensJsons"]

            expanded_tokens = []
            for token_ref in page_token_refs:
                page_index = token_ref["pageIndex"]
                token_index = token_ref["tokenIndex"]
                token = pawls_tokens[page_index]["tokens"][token_index]

                # Convert token from PAWLS to FUNSD format (simple but annoying transforming done via function
                # defined above)
                expanded_tokens.append(pawls_token_to_funsd_token(token))

            funsd_annotation: FunsdAnnotationType = {
                "id": f"{base_id}-{page}",
                "linking": [],  # Relationship linking is not yet wired into FUNSD export
                "text": page_annot_json["rawText"],
                "box": pawls_bbox_to_funsd_box(page_annot_json["bounds"]),
                "label": f"{label.text}",
                "words": expanded_tokens,
            }

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

    # Check for preferred thumbnailer in database settings first
    from opencontractserver.documents.models import PipelineSettings

    pipeline_settings = PipelineSettings.get_instance()
    preferred_thumbnailer = pipeline_settings.get_preferred_thumbnailer(file_type)

    thumbnailer_class = None

    if preferred_thumbnailer:
        # Try to load the preferred thumbnailer
        try:
            thumbnailer_class = get_component_by_name(preferred_thumbnailer)
            logger.info(
                f"Using preferred thumbnailer '{preferred_thumbnailer}' for doc {doc_id}"
            )
        except ValueError:
            logger.warning(
                f"Preferred thumbnailer '{preferred_thumbnailer}' not found, "
                "falling back to auto-discovery"
            )

    if not thumbnailer_class:
        # Fall back to auto-discovered thumbnailers for the MIME type
        components = get_components_by_mimetype(file_type)
        thumbnailers = components.get("thumbnailers", [])

        if not thumbnailers:
            logger.error(f"No thumbnailer found for file type '{file_type}'.")
            return

        # Use the first available thumbnailer
        thumbnailer_class = thumbnailers[0]
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

    logger.info(
        f"[retry_document_processing] Manual retry requested for doc {doc_id} "
        f"by user {user_id}"
    )

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

    # Re-trigger the processing pipeline
    chain(
        extract_thumbnail.si(doc_id=doc_id),
        ingest_doc.si(user_id=user_id, doc_id=doc_id),
        set_doc_lock_state.si(locked=False, doc_id=doc_id),
    ).apply_async()

    return {
        "status": "queued",
        "doc_id": doc_id,
        "message": "Document reprocessing has been queued",
    }
