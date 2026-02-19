"""
Celery tasks for bulk document ingestion.

Architecture:
    orchestrate_bulk_ingestion   (queue: bulk_orchestrate)
        ├── batch_import_preparsed  (queue: bulk_import)
        ├── batch_import_documents  (queue: bulk_import)
        └── dispatch_processing     (queue: bulk_dispatch)
                └── parsing chain   (queue: parsing)

All tasks use dedicated queues to avoid starving normal operations.
Backpressure is applied via queue depth monitoring to prevent Redis
memory exhaustion during large imports.
"""

import logging
import uuid

from celery import chain, shared_task
from django.apps import apps
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from opencontractserver.bulk_ingestion.constants import (
    BULK_INGESTION_BACKPRESSURE_DELAY,
    BULK_INGESTION_CHECKPOINT_INTERVAL,
    BULK_INGESTION_IMPORT_BATCH_SIZE,
    BULK_INGESTION_MAX_PARSE_QUEUE_DEPTH,
    BULK_INGESTION_PARSE_BATCH_SIZE,
    QUEUE_BULK_DISPATCH,
    QUEUE_BULK_IMPORT,
    QUEUE_BULK_ORCHESTRATE,
    QUEUE_PARSING,
)
from opencontractserver.bulk_ingestion.utils import (
    bulk_create_document_path_permissions,
    bulk_create_document_permissions,
    read_batch_manifest,
    read_jsonl_batch,
    read_staged_file,
    save_thumbnail_from_base64,
)
from opencontractserver.constants.document_processing import (
    DEFAULT_DOCUMENT_PATH_PREFIX,
)
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentProcessingStatus,
)

logger = logging.getLogger(__name__)


def _get_redis_queue_depth(queue_name: str) -> int:
    """
    Get the current depth of a Celery queue in Redis.

    Returns 0 if queue depth cannot be determined (non-Redis broker,
    connection error, etc.) - this disables backpressure gracefully.
    """
    try:
        from django.conf import settings

        import redis

        r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        return r.llen(queue_name)
    except Exception:
        return 0


@shared_task(queue=QUEUE_BULK_ORCHESTRATE)
def orchestrate_preparsed_ingestion(job_id: int):
    """
    Orchestrate import of pre-parsed document bundles.

    Reads the batch manifest, creates BulkIngestionItems for tracking,
    and dispatches batch import tasks for each JSONL batch file.

    Args:
        job_id: The BulkIngestionJob ID.
    """
    BulkIngestionJob = apps.get_model("bulk_ingestion", "BulkIngestionJob")
    BulkIngestionItem = apps.get_model("bulk_ingestion", "BulkIngestionItem")

    job = BulkIngestionJob.objects.get(id=job_id)

    if job.is_terminal:
        logger.warning(f"Job {job_id} is in terminal state {job.status}, skipping")
        return

    try:
        job.status = "importing"
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

        source_config = job.source_config or {}
        manifest_path = source_config.get("manifest_path", "")
        if not manifest_path:
            raise ValueError("source_config.manifest_path is required for pre_parsed ingestion")

        manifest = read_batch_manifest(manifest_path)

        job.total_items = manifest.get("total_documents", 0)
        job.checkpoint_data = {"manifest": manifest_path, "batches_dispatched": 0}
        job.save(update_fields=["total_items", "checkpoint_data"])

        batches = manifest.get("batches", [])
        base_path = manifest.get("base_path", "")

        for i, batch_entry in enumerate(batches):
            batch_filename = batch_entry["filename"]
            if base_path:
                batch_path = f"{base_path}/{batch_filename}"
            else:
                batch_path = batch_filename

            batch_import_preparsed.apply_async(
                args=[job_id, batch_path, i],
                queue=QUEUE_BULK_IMPORT,
            )

        job.checkpoint_data["batches_dispatched"] = len(batches)
        job.save(update_fields=["checkpoint_data"])

        logger.info(
            f"Orchestrated pre-parsed ingestion for job {job_id}: "
            f"{len(batches)} batches, {job.total_items} total documents"
        )

    except Exception as e:
        logger.exception(f"Failed to orchestrate job {job_id}: {e}")
        job.status = "failed"
        job.error_message = str(e)[:1000]
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at"])


@shared_task(
    queue=QUEUE_BULK_IMPORT,
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def batch_import_preparsed(self, job_id: int, batch_path: str, batch_index: int = 0):
    """
    Import a batch of pre-parsed documents from a JSONL file.

    This is the critical performance path. For each document:
    1. Creates Document record (bypassing post_save signals via bulk_create)
    2. Saves pre-parsed data (annotations, relationships, structural sets)
    3. Creates DocumentPath for corpus linkage
    4. Creates permissions in bulk

    Documents are marked COMPLETED immediately since parsing was done offline.
    Only embedding tasks are dispatched to Celery.

    Args:
        job_id: The BulkIngestionJob ID.
        batch_path: Path to the JSONL batch file in staging storage.
        batch_index: Index of this batch (for checkpoint tracking).
    """
    BulkIngestionJob = apps.get_model("bulk_ingestion", "BulkIngestionJob")
    BulkIngestionItem = apps.get_model("bulk_ingestion", "BulkIngestionItem")

    job = BulkIngestionJob.objects.get(id=job_id)

    if job.is_terminal:
        logger.warning(f"Job {job_id} is in terminal state, skipping batch {batch_index}")
        return

    try:
        bundles = read_jsonl_batch(batch_path)
    except FileNotFoundError:
        logger.error(f"Batch file not found: {batch_path}")
        BulkIngestionJob.objects.filter(id=job_id).update(
            failed_count=F("failed_count") + 1
        )
        return

    corpus = job.corpus
    user = job.creator
    source_config = job.source_config or {}
    pdf_storage_path = source_config.get("pdf_storage_path", "")
    skip_thumbnails = source_config.get("skip_thumbnails", False)

    # Phase 1: Bulk create Documents
    documents_to_create = []
    bundle_map = []  # Parallel list to track bundle-document pairs

    for bundle in bundles:
        # Skip parse failures recorded in the bundle
        if bundle.get("error"):
            _record_item_failure(
                job_id, bundle.get("external_id", "unknown"), bundle["error"]
            )
            BulkIngestionJob.objects.filter(id=job_id).update(
                failed_count=F("failed_count") + 1
            )
            continue

        external_id = bundle.get("external_id", "")
        parsed_data = bundle.get("parsed_data", {})
        pdf_hash = bundle.get("pdf_sha256", "")

        custom_meta = bundle.get("custom_meta", {})
        custom_meta.update(
            {
                "parser_name": bundle.get("parser_name", ""),
                "parser_version": bundle.get("parser_version", ""),
                "parsed_at": bundle.get("parsed_at", ""),
            }
        )

        doc = Document(
            title=parsed_data.get("title", external_id),
            description=parsed_data.get("description", ""),
            file_type="application/pdf",
            pdf_file_hash=pdf_hash,
            page_count=parsed_data.get("page_count", 0),
            version_tree_id=uuid.uuid4(),
            is_current=True,
            creator=user,
            slug=external_id.lower().replace(".", "-"),
            custom_meta=custom_meta,
            # Mark as already processed — bypass the ingest signal chain
            processing_started=timezone.now(),
            processing_finished=timezone.now(),
            processing_status=DocumentProcessingStatus.COMPLETED,
            backend_lock=False,
        )
        documents_to_create.append(doc)
        bundle_map.append(bundle)

    if not documents_to_create:
        logger.info(f"No valid documents in batch {batch_path}, skipping")
        return

    # Bulk create documents — Django does NOT fire post_save signals
    # for bulk_create, so the ingest chain is bypassed entirely
    with transaction.atomic():
        created_docs = Document.objects.bulk_create(
            documents_to_create,
            batch_size=BULK_INGESTION_IMPORT_BATCH_SIZE,
        )

        # Bulk create DocumentPaths
        doc_paths = []
        for doc, bundle in zip(created_docs, bundle_map):
            ext_id = bundle.get("external_id", "")
            doc_paths.append(
                DocumentPath(
                    document=doc,
                    corpus=corpus,
                    path=f"{DEFAULT_DOCUMENT_PATH_PREFIX}/{ext_id}",
                    version_number=1,
                    is_current=True,
                    is_deleted=False,
                    creator=user,
                )
            )

        created_paths = DocumentPath.objects.bulk_create(
            doc_paths,
            batch_size=BULK_INGESTION_IMPORT_BATCH_SIZE,
        )

        # Bulk create permissions
        bulk_create_document_permissions(created_docs, user)
        bulk_create_document_path_permissions(created_paths, user)

        # Create BulkIngestionItem records for tracking
        items_to_create = []
        for doc, bundle in zip(created_docs, bundle_map):
            items_to_create.append(
                BulkIngestionItem(
                    job=job,
                    external_id=bundle.get("external_id", ""),
                    source_url=bundle.get("source_url", ""),
                    staged_path=bundle.get("source_filename", ""),
                    document=doc,
                    status="imported",
                    file_type="application/pdf",
                    content_hash=bundle.get("pdf_sha256", ""),
                )
            )
        BulkIngestionItem.objects.bulk_create(
            items_to_create,
            batch_size=BULK_INGESTION_IMPORT_BATCH_SIZE,
            ignore_conflicts=True,
        )

    # Update job progress
    BulkIngestionJob.objects.filter(id=job_id).update(
        imported_count=F("imported_count") + len(created_docs)
    )

    # Phase 2: Save parsed data for each document (creates annotations, etc.)
    # This calls into BaseParser.save_parsed_data() which handles:
    #   - Saving txt_extract_file and pawls_parse_file
    #   - Creating structural annotations and relationships
    #   - Creating StructuralAnnotationSet
    from opencontractserver.pipeline.parsers.pre_parsed_stub import PreParsedParserStub

    parser = PreParsedParserStub()
    parsed_success = 0

    for doc, bundle in zip(created_docs, bundle_map):
        parsed_data = bundle.get("parsed_data", {})
        external_id = bundle.get("external_id", "")

        try:
            # Attach PDF file from staging if available
            _attach_pdf_from_staging(doc, bundle, pdf_storage_path)

            # Save thumbnail if included in bundle
            if not skip_thumbnails and bundle.get("thumbnail_base64"):
                save_thumbnail_from_base64(
                    doc,
                    bundle["thumbnail_base64"],
                    bundle.get("thumbnail_format", "png"),
                )

            # Save parsed data (annotations, relationships, structural set)
            if parsed_data.get("labelled_text") or parsed_data.get("content"):
                parser.save_parsed_data(
                    user_id=user.id,
                    doc_id=doc.id,
                    open_contracts_data=parsed_data,
                    corpus_id=corpus.id,
                )

            parsed_success += 1

        except Exception as e:
            logger.error(f"Failed to save parsed data for {external_id}: {e}")
            Document.objects.filter(id=doc.id).update(
                processing_status=DocumentProcessingStatus.FAILED,
                processing_error=str(e)[:1000],
            )
            BulkIngestionItem.objects.filter(
                job_id=job_id, external_id=external_id
            ).update(status="failed", error_message=str(e)[:1000])
            BulkIngestionJob.objects.filter(id=job_id).update(
                failed_count=F("failed_count") + 1
            )

    # Update parsed count
    BulkIngestionJob.objects.filter(id=job_id).update(
        parsed_count=F("parsed_count") + parsed_success
    )

    # Phase 3: Dispatch embedding tasks with backpressure
    skip_embeddings = source_config.get("skip_embeddings", False)
    if not skip_embeddings:
        for doc in created_docs:
            if doc.processing_status == DocumentProcessingStatus.COMPLETED:
                dispatch_embedding_with_backpressure.apply_async(
                    args=[doc.id, corpus.id, job_id],
                    queue=QUEUE_BULK_DISPATCH,
                )

    # Update checkpoint
    if bundle_map:
        last_ext_id = bundle_map[-1].get("external_id", "")
        BulkIngestionJob.objects.filter(id=job_id).update(
            last_processed_external_id=last_ext_id
        )

    logger.info(
        f"Batch {batch_index} complete for job {job_id}: "
        f"{len(created_docs)} imported, {parsed_success} parsed"
    )

    # Check if job is complete
    _check_job_completion(job_id)


@shared_task(queue=QUEUE_BULK_IMPORT, bind=True, max_retries=2, default_retry_delay=30)
def batch_import_documents(
    self, job_id: int, item_ids: list[int],
):
    """
    Import a batch of already-downloaded documents into the database.

    For non-pre-parsed ingestion: documents have been downloaded and staged,
    now need Document/DocumentPath creation and parsing dispatch.

    Args:
        job_id: The BulkIngestionJob ID.
        item_ids: List of BulkIngestionItem IDs to process.
    """
    BulkIngestionJob = apps.get_model("bulk_ingestion", "BulkIngestionJob")
    BulkIngestionItem = apps.get_model("bulk_ingestion", "BulkIngestionItem")

    job = BulkIngestionJob.objects.get(id=job_id)

    if job.is_terminal:
        return

    items = list(
        BulkIngestionItem.objects.filter(
            id__in=item_ids, status="downloaded"
        )
    )

    corpus = job.corpus
    user = job.creator
    documents_to_create = []
    valid_items = []

    for item in items:
        try:
            content = read_staged_file(item.staged_path)
        except FileNotFoundError:
            item.status = "failed"
            item.error_message = f"Staged file not found: {item.staged_path}"
            item.save(update_fields=["status", "error_message"])
            BulkIngestionJob.objects.filter(id=job_id).update(
                failed_count=F("failed_count") + 1
            )
            continue

        import hashlib

        content_hash = hashlib.sha256(content).hexdigest()

        doc = Document(
            title=item.external_id,
            description="",
            file_type=item.file_type or "application/pdf",
            pdf_file=ContentFile(content, name=f"{item.external_id}.pdf"),
            pdf_file_hash=content_hash,
            version_tree_id=uuid.uuid4(),
            is_current=True,
            creator=user,
            slug=item.external_id.lower().replace(".", "-"),
            # Do NOT set processing_started — this allows signal to fire
            # for normal parsing pipeline, or we suppress and dispatch manually
            backend_lock=True,
            processing_status=DocumentProcessingStatus.PENDING,
        )
        documents_to_create.append(doc)
        valid_items.append(item)

    if not documents_to_create:
        return

    with transaction.atomic():
        created_docs = Document.objects.bulk_create(
            documents_to_create,
            batch_size=BULK_INGESTION_IMPORT_BATCH_SIZE,
        )

        doc_paths = []
        for doc, item in zip(created_docs, valid_items):
            doc_paths.append(
                DocumentPath(
                    document=doc,
                    corpus=corpus,
                    path=f"{DEFAULT_DOCUMENT_PATH_PREFIX}/{item.external_id}",
                    version_number=1,
                    is_current=True,
                    is_deleted=False,
                    creator=user,
                )
            )

        created_paths = DocumentPath.objects.bulk_create(
            doc_paths,
            batch_size=BULK_INGESTION_IMPORT_BATCH_SIZE,
        )

        bulk_create_document_permissions(created_docs, user)
        bulk_create_document_path_permissions(created_paths, user)

        for doc, item in zip(created_docs, valid_items):
            item.document = doc
            item.content_hash = doc.pdf_file_hash
            item.status = "imported"
        BulkIngestionItem.objects.bulk_update(
            valid_items, ["document", "content_hash", "status"],
            batch_size=BULK_INGESTION_IMPORT_BATCH_SIZE,
        )

    BulkIngestionJob.objects.filter(id=job_id).update(
        imported_count=F("imported_count") + len(created_docs)
    )

    # Dispatch parsing tasks with backpressure
    for doc in created_docs:
        dispatch_processing_with_backpressure.apply_async(
            args=[doc.id, user.id, job_id],
            queue=QUEUE_BULK_DISPATCH,
        )

    logger.info(
        f"Batch import complete for job {job_id}: {len(created_docs)} documents created"
    )


@shared_task(queue=QUEUE_BULK_DISPATCH)
def dispatch_processing_with_backpressure(
    doc_id: int, user_id: int, job_id: int,
):
    """
    Dispatch the standard parsing chain for a document with backpressure.

    Checks the parsing queue depth before dispatching. If the queue is too
    deep, re-queues itself with a delay to avoid overwhelming Redis.

    Args:
        doc_id: Document ID to process.
        user_id: User ID who initiated the import.
        job_id: BulkIngestionJob ID for progress tracking.
    """
    from opencontractserver.tasks.doc_tasks import (
        extract_thumbnail,
        ingest_doc,
        set_doc_lock_state,
    )

    queue_depth = _get_redis_queue_depth(QUEUE_PARSING)
    if queue_depth > BULK_INGESTION_MAX_PARSE_QUEUE_DEPTH:
        # Re-queue with delay
        dispatch_processing_with_backpressure.apply_async(
            args=[doc_id, user_id, job_id],
            countdown=BULK_INGESTION_BACKPRESSURE_DELAY,
            queue=QUEUE_BULK_DISPATCH,
        )
        return

    # Mark document as processing
    Document.objects.filter(id=doc_id).update(
        processing_started=timezone.now(),
        processing_status=DocumentProcessingStatus.PROCESSING,
    )

    # Queue the standard processing chain on the parsing queue
    chain(
        extract_thumbnail.si(doc_id=doc_id),
        ingest_doc.si(user_id=user_id, doc_id=doc_id),
        set_doc_lock_state.si(locked=False, doc_id=doc_id),
        _mark_item_parsed.si(doc_id=doc_id, job_id=job_id),
    ).apply_async()


@shared_task(queue=QUEUE_BULK_DISPATCH)
def dispatch_embedding_with_backpressure(
    doc_id: int, corpus_id: int, job_id: int,
):
    """
    Dispatch embedding generation for a document with backpressure.

    Args:
        doc_id: Document ID to embed.
        corpus_id: Corpus ID for embedder selection.
        job_id: BulkIngestionJob ID for progress tracking.
    """
    from opencontractserver.bulk_ingestion.constants import (
        BULK_INGESTION_MAX_EMBED_QUEUE_DEPTH,
    )

    queue_depth = _get_redis_queue_depth("embedding")
    if queue_depth > BULK_INGESTION_MAX_EMBED_QUEUE_DEPTH:
        dispatch_embedding_with_backpressure.apply_async(
            args=[doc_id, corpus_id, job_id],
            countdown=BULK_INGESTION_BACKPRESSURE_DELAY,
            queue=QUEUE_BULK_DISPATCH,
        )
        return

    from opencontractserver.tasks.embeddings_task import (
        calculate_embedding_for_doc_text,
    )

    # Queue embedding and follow up with progress tracking
    chain(
        calculate_embedding_for_doc_text.si(doc_id=doc_id, corpus_id=corpus_id),
        _mark_item_embedded.si(doc_id=doc_id, job_id=job_id),
    ).apply_async()


@shared_task
def _mark_item_parsed(doc_id: int, job_id: int):
    """Update progress counters after a document is parsed."""
    BulkIngestionJob = apps.get_model("bulk_ingestion", "BulkIngestionJob")
    BulkIngestionItem = apps.get_model("bulk_ingestion", "BulkIngestionItem")

    BulkIngestionItem.objects.filter(
        job_id=job_id, document_id=doc_id
    ).update(status="parsed")

    BulkIngestionJob.objects.filter(id=job_id).update(
        parsed_count=F("parsed_count") + 1
    )

    _check_job_completion(job_id)


@shared_task
def _mark_item_embedded(doc_id: int, job_id: int):
    """Update progress counters after a document embedding is generated."""
    BulkIngestionJob = apps.get_model("bulk_ingestion", "BulkIngestionJob")
    BulkIngestionItem = apps.get_model("bulk_ingestion", "BulkIngestionItem")

    BulkIngestionItem.objects.filter(
        job_id=job_id, document_id=doc_id
    ).update(status="completed")

    BulkIngestionJob.objects.filter(id=job_id).update(
        embedded_count=F("embedded_count") + 1
    )

    _check_job_completion(job_id)


@shared_task(queue=QUEUE_BULK_ORCHESTRATE)
def resume_bulk_ingestion(job_id: int):
    """
    Resume a paused or partially-failed bulk ingestion job.

    Scans for items in intermediate states and re-dispatches appropriate
    tasks. Idempotent — safe to call multiple times.

    Args:
        job_id: The BulkIngestionJob ID to resume.
    """
    BulkIngestionJob = apps.get_model("bulk_ingestion", "BulkIngestionJob")
    BulkIngestionItem = apps.get_model("bulk_ingestion", "BulkIngestionItem")

    job = BulkIngestionJob.objects.get(id=job_id)
    if job.is_terminal:
        logger.warning(f"Cannot resume terminal job {job_id} (status={job.status})")
        return

    job.status = "processing"
    job.save(update_fields=["status"])

    corpus = job.corpus
    user = job.creator

    # Re-dispatch parsing for imported but un-parsed documents
    imported_items = BulkIngestionItem.objects.filter(
        job_id=job_id, status="imported"
    ).select_related("document")

    for item in imported_items.iterator(chunk_size=100):
        if item.document_id:
            if job.parsing_strategy == "pre_parsed":
                # For pre-parsed, dispatch embedding directly
                dispatch_embedding_with_backpressure.apply_async(
                    args=[item.document_id, corpus.id, job_id],
                    queue=QUEUE_BULK_DISPATCH,
                )
            else:
                dispatch_processing_with_backpressure.apply_async(
                    args=[item.document_id, user.id, job_id],
                    queue=QUEUE_BULK_DISPATCH,
                )

    # Re-dispatch embeddings for parsed but un-embedded documents
    parsed_items = BulkIngestionItem.objects.filter(
        job_id=job_id, status="parsed"
    ).select_related("document")

    for item in parsed_items.iterator(chunk_size=100):
        if item.document_id:
            dispatch_embedding_with_backpressure.apply_async(
                args=[item.document_id, corpus.id, job_id],
                queue=QUEUE_BULK_DISPATCH,
            )

    total_resumed = imported_items.count() + parsed_items.count()
    logger.info(f"Resumed job {job_id}: {total_resumed} items re-dispatched")


@shared_task(queue=QUEUE_BULK_ORCHESTRATE)
def pause_bulk_ingestion(job_id: int):
    """
    Pause a running bulk ingestion job.

    Sets job status to PAUSED. Already-dispatched tasks will complete,
    but no new batches will be dispatched. Resume with resume_bulk_ingestion.

    Args:
        job_id: The BulkIngestionJob ID to pause.
    """
    BulkIngestionJob = apps.get_model("bulk_ingestion", "BulkIngestionJob")

    updated = BulkIngestionJob.objects.filter(
        id=job_id,
        status__in=["importing", "processing", "downloading"],
    ).update(status="paused")

    if updated:
        logger.info(f"Paused bulk ingestion job {job_id}")
    else:
        logger.warning(f"Could not pause job {job_id} (not in active state)")


def _attach_pdf_from_staging(document, bundle: dict, pdf_storage_path: str):
    """
    Attach the source PDF to a document from staging storage.

    Looks for the PDF at the staging path, then saves it to the
    document's pdf_file field.
    """
    source_filename = bundle.get("source_filename", "")
    if not source_filename:
        return

    # Build full path to PDF in staging
    if pdf_storage_path:
        pdf_path = f"{pdf_storage_path}/{source_filename}"
    else:
        pdf_path = source_filename

    try:
        pdf_content = read_staged_file(pdf_path)
        document.pdf_file.save(source_filename, ContentFile(pdf_content), save=True)
    except FileNotFoundError:
        logger.warning(
            f"PDF not found at {pdf_path} for doc {document.id}, "
            f"document will have no PDF file attached"
        )


def _record_item_failure(job_id: int, external_id: str, error_msg: str):
    """Record a failed item in the BulkIngestionItem table."""
    BulkIngestionItem = apps.get_model("bulk_ingestion", "BulkIngestionItem")

    BulkIngestionItem.objects.update_or_create(
        job_id=job_id,
        external_id=external_id,
        defaults={
            "status": "failed",
            "error_message": error_msg[:1000],
        },
    )


def _check_job_completion(job_id: int):
    """
    Check if all items in a job are in terminal states and update job status.
    """
    BulkIngestionJob = apps.get_model("bulk_ingestion", "BulkIngestionJob")
    BulkIngestionItem = apps.get_model("bulk_ingestion", "BulkIngestionItem")

    job = BulkIngestionJob.objects.get(id=job_id)
    if job.is_terminal:
        return

    total = job.total_items
    if total == 0:
        return

    terminal_count = BulkIngestionItem.objects.filter(
        job_id=job_id,
        status__in=["completed", "failed", "skipped"],
    ).count()

    if terminal_count >= total:
        failed = BulkIngestionItem.objects.filter(
            job_id=job_id, status="failed"
        ).count()

        if failed == total:
            final_status = "failed"
        else:
            final_status = "completed"

        BulkIngestionJob.objects.filter(id=job_id).update(
            status=final_status,
            completed_at=timezone.now(),
        )
        logger.info(
            f"Job {job_id} {final_status}: "
            f"{terminal_count} items processed, {failed} failed"
        )
