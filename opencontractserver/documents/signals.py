from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from celery import chain
from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
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
