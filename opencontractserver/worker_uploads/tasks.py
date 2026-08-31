"""
Celery tasks for processing staged worker document uploads.

The batch processor drains the WorkerDocumentUpload staging table using
SELECT ... FOR UPDATE SKIP LOCKED, so multiple workers can process
concurrently without conflicts.

All tasks run on the 'worker_uploads' queue to preserve capacity on the
default queue for regular user operations.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile, File
from django.db import transaction
from django.utils import timezone

from opencontractserver.annotations.models import (
    EMBEDDING_DIMENSIONS,
    Annotation,
    AnnotationLabel,
    Embedding,
)
from opencontractserver.constants.document_processing import (
    MAX_UPLOAD_ERROR_MESSAGE_LENGTH,
)
from opencontractserver.corpuses.models import CorpusFolder
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentProcessingStatus,
)
from opencontractserver.extracts.services.metadata import MetadataService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.compact_pawls import compact_pawls_pages
from opencontractserver.utils.importing import (
    import_annotations,
    import_relationships,
    load_or_create_labels,
)
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
from opencontractserver.utils.structural_sets import create_structural_annotation_set
from opencontractserver.utils.subtree_groups import build_subtree_groups_for_document
from opencontractserver.worker_uploads.models import (
    UploadStatus,
    WorkerAuthoritySectionBatch,
    WorkerDocumentUpload,
)

logger = logging.getLogger(__name__)

# Maximum length for sanitized filenames
_MAX_FILENAME_LENGTH = 200

# Dimension -> field name mapping, derived from the Embedding model's
# authoritative EMBEDDING_DIMENSIONS list so new dimensions propagate automatically.
_VECTOR_FIELD_MAP = {dim: f"vector_{dim}" for dim, _ in EMBEDDING_DIMENSIONS}

# Validate that every entry in _VECTOR_FIELD_MAP corresponds to an actual
# Embedding model field. Catches dimension/field mismatches at import time
# rather than silently dropping embeddings at runtime.
assert all(
    hasattr(Embedding, f) for f in _VECTOR_FIELD_MAP.values()
), "EMBEDDING_DIMENSIONS has entries without matching Embedding model fields"


@shared_task(
    bind=True,
    queue="worker_uploads",
    max_retries=0,
    # Redundant since the global default became acks_late=True (Issue #1493),
    # but kept as an explicit declaration of intent: this task in particular
    # MUST redeliver on worker death so pending uploads aren't dropped.
    acks_late=True,
)
def process_pending_uploads(self: Any) -> dict[str, int]:
    """
    Drain a batch of PENDING uploads from the staging table.

    Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple instances can
    run concurrently. After processing a batch, re-enqueues itself
    if more PENDING rows exist.

    Returns:
        Summary dict with counts of processed, succeeded, and failed.
    """
    result = {"claimed": 0, "succeeded": 0, "failed": 0}

    # Claim a batch of PENDING uploads atomically
    with transaction.atomic():
        pending_ids = list(
            WorkerDocumentUpload.objects.select_for_update(skip_locked=True)
            .filter(status=UploadStatus.PENDING)
            .order_by("created")
            .values_list("id", flat=True)[: settings.WORKER_UPLOAD_BATCH_SIZE]
        )

        if not pending_ids:
            logger.debug("process_pending_uploads: no pending uploads found.")
            return result

        # Mark as PROCESSING
        WorkerDocumentUpload.objects.filter(id__in=pending_ids).update(
            status=UploadStatus.PROCESSING,
            processing_started=timezone.now(),
        )

    result["claimed"] = len(pending_ids)
    logger.info(f"process_pending_uploads: claimed {len(pending_ids)} uploads.")

    # Process each upload in its own transaction for isolation
    for upload_id in pending_ids:
        try:
            _process_single_upload(upload_id)
            result["succeeded"] += 1
        except Exception as e:
            logger.error(
                f"process_pending_uploads: upload {upload_id} failed: {e}",
                exc_info=True,
            )
            _fail_upload(upload_id, str(e)[:MAX_UPLOAD_ERROR_MESSAGE_LENGTH])
            result["failed"] += 1

    # Re-enqueue if there are more pending uploads
    remaining = WorkerDocumentUpload.objects.filter(
        status=UploadStatus.PENDING
    ).exists()
    if remaining:
        process_pending_uploads.apply_async(
            queue="worker_uploads",
            countdown=1,  # Brief pause to avoid tight loop
            ignore_result=True,
        )

    logger.info(f"process_pending_uploads: batch result={result}")
    return result


@shared_task(queue="worker_uploads")
def recover_stalled_uploads() -> dict[str, int]:
    """
    Reset uploads stuck in PROCESSING beyond the configured timeout.

    Uses SELECT ... FOR UPDATE SKIP LOCKED to avoid resetting uploads that
    are actively being processed (row-locked by the batch processor). Each
    row is reset individually with a compare-and-swap on processing_started
    to prevent races where an upload is legitimately re-claimed between the
    select and the update.
    """
    cutoff = timezone.now() - timedelta(minutes=settings.WORKER_UPLOAD_STALE_MINUTES)
    count = 0

    with transaction.atomic():
        stalled = list(
            WorkerDocumentUpload.objects.select_for_update(skip_locked=True)
            .filter(
                status=UploadStatus.PROCESSING,
                processing_started__lt=cutoff,
            )
            .values_list("id", "processing_started")
        )

        for upload_id, original_started in stalled:
            # Compare-and-swap: only reset if processing_started hasn't changed
            # since we read it, preventing double-processing races.
            updated = WorkerDocumentUpload.objects.filter(
                id=upload_id,
                status=UploadStatus.PROCESSING,
                processing_started=original_started,
            ).update(
                status=UploadStatus.PENDING,
                processing_started=None,
            )
            count += updated

    # Same sweep for authority-section batches, same compare-and-swap.
    batch_count = 0
    with transaction.atomic():
        stalled_batches = list(
            WorkerAuthoritySectionBatch.objects.select_for_update(skip_locked=True)
            .filter(
                status=UploadStatus.PROCESSING,
                processing_started__lt=cutoff,
            )
            .values_list("id", "processing_started")
        )

        for batch_id, original_started in stalled_batches:
            updated = WorkerAuthoritySectionBatch.objects.filter(
                id=batch_id,
                status=UploadStatus.PROCESSING,
                processing_started=original_started,
            ).update(
                status=UploadStatus.PENDING,
                processing_started=None,
            )
            batch_count += updated

    if count or batch_count:
        logger.info(
            f"recover_stalled_uploads: reset {count} stalled upload(s), "
            f"{batch_count} stalled section batch(es)."
        )

    return {"recovered": count, "recovered_section_batches": batch_count}


def _process_single_upload(upload_id: UUID) -> None:
    """
    Process one WorkerDocumentUpload: create Document, annotations,
    embeddings, and add to the target corpus.

    Runs inside its own transaction. On success, marks COMPLETED.
    On failure, the caller catches the exception and marks FAILED.
    """
    upload = WorkerDocumentUpload.objects.select_related(
        "corpus",
        "corpus__creator",
        "corpus_access_token",
        "corpus_access_token__worker_account",
    ).get(id=upload_id)

    metadata = upload.metadata
    corpus = upload.corpus

    # Defensive re-check of required fields. The serializer validates these at
    # upload time, but metadata lives in a JSONField and could theoretically be
    # modified between staging and processing (e.g., admin edit, migration).
    required_fields = ["title", "content", "pawls_file_content", "page_count"]
    missing = [f for f in required_fields if f not in metadata]
    if missing:
        raise ValueError(f"Missing required metadata fields: {', '.join(missing)}")

    # Documents uploaded via workers are owned by the corpus creator,
    # not the service account, so they inherit the correct permissions
    # and appear naturally in the corpus owner's workspace.
    user = corpus.creator
    if user is None:
        raise ValueError(
            f"Corpus {corpus.id} has no creator; cannot process worker upload."
        )
    if not user.is_active:
        raise ValueError(
            f"Corpus {corpus.id} creator (user {user.id}) is inactive; "
            f"cannot process worker upload."
        )

    # Guardian permission writes use the default DB connection, so they
    # participate in the same transaction.atomic() block and roll back on failure.
    with transaction.atomic():
        # 1. Create the standalone Document
        # Sanitize the title — strip null bytes (which Postgres rejects) and
        # path traversal characters from worker-supplied input.
        raw_title = metadata.get("title", "document") or "document"
        safe_title = raw_title.replace("\x00", "")
        doc_filename = re.sub(r"[^\w \-.]", "_", safe_title)
        # Collapse consecutive dots to prevent path traversal remnants
        doc_filename = re.sub(r"\.{2,}", ".", doc_filename)
        doc_filename = (
            doc_filename.strip().lstrip(".")[:_MAX_FILENAME_LENGTH] or "document"
        )
        if "." not in doc_filename:
            doc_filename += ".pdf"

        pawls_content = metadata.get("pawls_file_content", [])
        text_content = metadata.get("content", "")

        pawls_file = ContentFile(
            json.dumps(compact_pawls_pages(pawls_content)).encode("utf-8"),
            name="pawls_tokens.json",
        )
        txt_file = ContentFile(
            text_content.encode("utf-8"),
            name="extracted_text.txt",
        )

        # Optional structured metadata calculated by the remote worker's
        # pre-processing stage (e.g. jurisdiction, parsed dates, contract
        # number). Stored verbatim on Document.custom_meta. Only applied when
        # provided so non-enriched uploads keep the field's default.
        custom_meta = metadata.get("custom_meta")

        create_kwargs: dict[str, Any] = {
            "title": safe_title,
            "description": metadata.get("description", ""),
            "pdf_file": File(upload.file, doc_filename),
            "pawls_parse_file": pawls_file,
            "txt_extract_file": txt_file,
            "file_type": metadata.get("file_type", "application/pdf"),
            "page_count": metadata.get("page_count", len(pawls_content)),
            "backend_lock": True,
            "creator": user,
            # Mark as already processed — worker did the processing
            "processing_started": timezone.now(),
            "processing_status": DocumentProcessingStatus.COMPLETED,
        }
        if custom_meta is not None:
            create_kwargs["custom_meta"] = custom_meta

        # Open the uploaded file
        upload.file.open("rb")
        try:
            doc = Document.objects.create(**create_kwargs)
        finally:
            upload.file.close()

        set_permissions_for_obj_to_user(user, doc, [PermissionTypes.ALL])

        # 2. Prepare labels (auto-create any that don't exist)
        labelset = corpus.label_set
        label_lookup, doc_label_lookup = _prepare_labels(metadata, user.id, labelset)

        # 3. Add document to corpus — returns the corpus-linked Document
        # record (not the original standalone doc). All subsequent annotations,
        # labels, relationships, and embeddings must reference corpus_doc so
        # queries filtering by (document, corpus) resolve correctly.
        target_path = metadata.get("target_path")
        corpus_doc, _status, _doc_path = corpus.add_document(
            document=doc,
            user=user,
            path=target_path,
        )

        # add_document creates a corpus-isolated COPY; make sure the worker's
        # structured metadata is present on the copy users actually see.
        if custom_meta is not None and corpus_doc.custom_meta != custom_meta:
            corpus_doc.custom_meta = custom_meta
            corpus_doc.save(update_fields=["custom_meta"])

        # 4. Import document-level labels
        for doc_label_name in metadata.get("doc_labels", []):
            label_obj = doc_label_lookup.get(doc_label_name)
            if label_obj:
                annot = Annotation.objects.create(
                    annotation_label=label_obj,
                    document=corpus_doc,
                    corpus=corpus,
                    creator_id=user.id,
                )
                set_permissions_for_obj_to_user(user, annot, [PermissionTypes.ALL])

        # 5. Import text annotations.
        # When the worker shipped pre-computed embeddings it OWNS the embedding
        # layer, so suppress the server-side batch-embedding dispatch that
        # import_annotations would otherwise fire (re-embedding here both wastes
        # the target's embedder and defeats the point of offloading enrichment
        # to the remote worker). When no embeddings are supplied, fall back to
        # the default behaviour and let the server embed.
        embeddings_data = metadata.get("embeddings")
        annot_id_map = import_annotations(
            user_id=user.id,
            doc_obj=corpus_doc,
            corpus_obj=corpus,
            annotations_data=metadata.get("labelled_text", []),
            label_lookup=label_lookup,
            dispatch_embeddings=not bool(embeddings_data),
        )

        # 6. Import relationships
        if metadata.get("relationships"):
            import_relationships(
                user_id=user.id,
                doc_obj=corpus_doc,
                corpus_obj=corpus,
                relationships_data=metadata["relationships"],
                label_lookup=label_lookup,
                annotation_id_map=annot_id_map,
            )

        # 7. Store pre-computed embeddings
        if embeddings_data:
            _store_embeddings(
                embeddings_data=embeddings_data,
                corpus_doc=corpus_doc,
                annot_id_map=annot_id_map,
                user=user,
            )

        # 7.5. Materialise the structural layer exactly as the parser pipeline
        # does (save_parsed_data): build subtree-group relationships from the
        # structural parent-child tree, then migrate structural annotations and
        # relationships into a StructuralAnnotationSet (document=NULL,
        # structural_set=set). This is what makes a remotely-parsed document a
        # FAITHFUL mirror: structural annotations resolve through the same
        # structural-set join the rest of the platform relies on
        # (AnnotationService.get_document_annotations), instead of lingering as
        # plain per-document annotations.
        build_subtree_groups_for_document(document=corpus_doc, user_id=user.id)
        create_structural_annotation_set(
            corpus_doc,
            user,
            parser_name=metadata.get("parser_name") or "Remote Worker",
            parser_version=metadata.get("parser_version") or "1.0",
        )

        # 7.6. Structured metadata (datacells) — the corpus Column/Datacell
        # metadata system (what the UI calls document metadata, successor to the
        # old "metadata annotations"). Each entry get-or-creates a manual-entry
        # Column in the corpus metadata schema and sets the document's value. A
        # type mismatch raises (Datacell.clean) and fails the upload, surfacing
        # the bad value rather than silently dropping it.
        for md in metadata.get("metadata", []) or []:
            MetadataService.upsert_document_metadata(
                corpus=corpus,
                document=corpus_doc,
                user=user,
                column_name=md["column_name"],
                data_type=md["data_type"],
                value=md.get("value"),
                validation_config=md.get("validation_config"),
            )

        # 8. Place in target folder if specified
        target_folder_path = metadata.get("target_folder_path")
        if target_folder_path:
            _assign_to_folder(corpus, corpus_doc, target_folder_path, user)

        # 9. Unlock the original document
        doc.backend_lock = False
        doc.save(update_fields=["backend_lock"])

        # 10. Mark upload as completed and clean up staging file
        upload.status = UploadStatus.COMPLETED
        upload.result_document = corpus_doc
        upload.processing_finished = timezone.now()
        upload.save(update_fields=["status", "result_document", "processing_finished"])

    # Generate the document thumbnail after commit. The worker-upload metadata
    # carries no thumbnail, but the source file IS stored, so the server can
    # regenerate Document.icon the same way the parser pipeline does. This is a
    # standalone task (NOT the ingest chain), so it only thumbnails — it never
    # re-parses the already-processed document. Dispatched post-commit so the
    # row is visible to the worker.
    try:
        from opencontractserver.tasks.doc_tasks import extract_thumbnail

        extract_thumbnail.apply_async(kwargs={"doc_id": corpus_doc.id})
    except Exception:
        logger.warning(
            f"Failed to dispatch thumbnail generation for upload {upload_id}",
            exc_info=True,
        )

    # Clean up staging file after successful commit
    if upload.file:
        try:
            upload.file.delete(save=False)
        except Exception:
            logger.warning(
                f"Failed to delete staging file for upload {upload_id}",
                exc_info=True,
            )

    logger.info(
        f"Worker upload {upload_id} processed: doc={corpus_doc.id} "
        f"in corpus={corpus.id}"
    )


def _prepare_labels(
    metadata: dict[str, Any],
    user_id: int,
    labelset: Any,
) -> tuple[dict[str, AnnotationLabel], dict[str, AnnotationLabel]]:
    """
    Load or create text and document labels from the upload metadata.
    Returns (label_lookup, doc_label_lookup).
    """
    text_labels = metadata.get("text_labels", {})
    doc_labels_defs = metadata.get("doc_labels_definitions", {})

    existing_text = load_or_create_labels(
        user_id=user_id,
        labelset_obj=labelset,
        label_data_dict=text_labels,
        existing_labels={},
    )

    existing_doc = load_or_create_labels(
        user_id=user_id,
        labelset_obj=labelset,
        label_data_dict=doc_labels_defs,
        existing_labels={},
    )

    label_lookup = {**existing_text, **existing_doc}

    # existing_doc is already keyed by label name from metadata, so use it
    # directly. Rebuilding via label.text could mismatch if the stored
    # AnnotationLabel.text differs from the metadata key.
    return label_lookup, existing_doc


def _store_embeddings(
    embeddings_data: dict[str, Any],
    corpus_doc: Any,
    annot_id_map: dict[str | int, int],
    user: Any,
) -> None:
    """
    Store pre-computed embeddings from the worker.

    Determines the correct vector_* field based on embedding dimension,
    then bulk-creates Embedding records.
    """
    embedder_path = embeddings_data.get("embedder_path", "")
    if not embedder_path:
        logger.warning("embeddings.embedder_path is empty, skipping embedding storage.")
        return

    # Document embedding
    doc_embedding = embeddings_data.get("document_embedding")
    if doc_embedding:
        _store_single_embedding(
            vector=doc_embedding,
            embedder_path=embedder_path,
            document=corpus_doc,
            creator=user,
        )

    # Annotation embeddings
    annot_embeddings = embeddings_data.get("annotation_embeddings", {})
    embeddings_to_create = []
    for old_annot_id, vector in annot_embeddings.items():
        new_pk = annot_id_map.get(old_annot_id) or annot_id_map.get(str(old_annot_id))
        if not new_pk:
            # A supplied annotation embedding whose id does not map to a created
            # annotation is dropped — surface it (a worker that ships embeddings
            # keyed by a stale/duplicate id loses that vector silently otherwise).
            logger.warning(
                f"Skipping embedding for unmapped annotation id "
                f"{old_annot_id!r} (not in annotation_id_map)."
            )
            continue

        field_name = _get_vector_field(len(vector))
        if not field_name:
            logger.warning(
                f"Unsupported embedding dimension {len(vector)} for annotation "
                f"{old_annot_id}, skipping."
            )
            continue

        emb = Embedding(
            annotation_id=new_pk,
            embedder_path=embedder_path,
            creator_id=user.id,
        )
        setattr(emb, field_name, vector)
        embeddings_to_create.append(emb)

    if embeddings_to_create:
        Embedding.objects.bulk_create(embeddings_to_create)
        logger.info(
            f"Stored {len(embeddings_to_create)} annotation embeddings "
            f"(embedder={embedder_path})"
        )


def _store_single_embedding(
    vector: list[float],
    embedder_path: str,
    document: Any = None,
    annotation: Any = None,
    creator: Any = None,
) -> Embedding | None:
    """Store a single embedding, determining the correct vector field by dimension."""
    field_name = _get_vector_field(len(vector))
    if not field_name:
        logger.warning(f"Unsupported embedding dimension {len(vector)}, skipping.")
        return None

    defaults = {field_name: vector}
    if creator is not None:
        defaults["creator"] = creator

    # Use update_or_create to handle duplicates gracefully
    emb, created = Embedding.objects.update_or_create(
        embedder_path=embedder_path,
        document=document,
        annotation=annotation,
        defaults=defaults,
    )
    return emb


def _get_vector_field(dimension: int) -> str | None:
    """Map an embedding dimension to the corresponding Embedding model field."""
    return _VECTOR_FIELD_MAP.get(dimension)


def _fail_upload(upload_id: UUID, error_message: str) -> None:
    """Mark an upload as FAILED and clean up its staging file."""
    upload = WorkerDocumentUpload.objects.filter(id=upload_id).first()
    if upload is None:
        return
    upload.status = UploadStatus.FAILED
    upload.error_message = error_message
    upload.processing_finished = timezone.now()
    upload.save(update_fields=["status", "error_message", "processing_finished"])

    if upload.file:
        try:
            upload.file.delete(save=False)
        except Exception:
            logger.warning(
                f"Failed to delete staging file for upload {upload_id}",
                exc_info=True,
            )


def _assign_to_folder(
    corpus: Any, corpus_doc: Any, folder_path: str, user: Any
) -> None:
    """
    Assign a document to a folder within the corpus, creating the folder
    hierarchy if needed.
    """
    # Build folder hierarchy from path components
    parts = [p.strip() for p in folder_path.strip("/").split("/") if p.strip()]
    if not parts:
        return

    parent = None
    for part_name in parts:
        folder, _created = CorpusFolder.objects.get_or_create(
            corpus=corpus,
            name=part_name,
            parent=parent,
            defaults={
                "creator": user,
            },
        )
        parent = folder

    # Update the DocumentPath to point to this folder
    doc_path = DocumentPath.objects.filter(
        corpus=corpus,
        document=corpus_doc,
        is_current=True,
    ).first()

    if doc_path and parent:
        doc_path.folder = parent
        doc_path.save(update_fields=["folder"])


def _json_safe_bootstrap_report(result: dict[str, Any]) -> dict[str, Any]:
    """Strip the bootstrap result down to JSON-safe report fields.

    ``document_ids`` can be large and the relink summary shape varies
    (inline dict vs {"queued": True, "task_id": ...}); keep the counts and
    the relink marker, drop the id list.
    """
    report = {k: v for k, v in result.items() if k != "document_ids"}
    report["document_count"] = len(result.get("document_ids", []))
    return report


@shared_task(
    bind=True,
    queue="worker_uploads",
    max_retries=0,
    acks_late=True,
)
def process_pending_section_batches(self: Any) -> dict[str, int]:
    """Drain staged authority-section batches into bootstrap_authority_corpus.

    One batch at a time under SELECT ... FOR UPDATE SKIP LOCKED (batches are
    coarse units — one push can carry hundreds of sections — so per-row
    claiming is the right granularity, unlike the document drain's batching),
    capped at WORKER_AUTHORITY_SECTION_BATCH_CAP batches per execution with a
    self re-enqueue while more remain. The cap is what keeps a backlog (after
    downtime, or several harvesters pushing at once) from tying up the single
    worker_uploads slot long enough to starve recover_stalled_uploads —
    process_pending_uploads bounds itself the same way.

    Ownership mirrors the document drain: created/updated documents belong to
    the CORPUS CREATOR, not the worker service user — the token represents
    delegated write access to that corpus. relink_async=True so a large batch
    never holds this worker while every citing corpus re-links.
    """
    from opencontractserver.enrichment.authorities import (
        bootstrap_authority_corpus,
        parse_section_spec,
    )
    from opencontractserver.enrichment.services.authority_equivalence_ingest import (
        upsert_equivalence,
    )

    processed = {"completed": 0, "failed": 0}
    cap = settings.WORKER_AUTHORITY_SECTION_BATCH_CAP
    claimed = 0
    while cap <= 0 or claimed < cap:
        with transaction.atomic():
            batch = (
                # of=("self",): corpus_access_token is NULLABLE, so the
                # select_related join is a LEFT OUTER JOIN and Postgres
                # refuses FOR UPDATE on its nullable side — lock only the
                # batch row itself.
                WorkerAuthoritySectionBatch.objects.select_for_update(
                    skip_locked=True, of=("self",)
                )
                .select_related(
                    "corpus_access_token__worker_account", "corpus__creator"
                )
                .filter(status=UploadStatus.PENDING)
                .order_by("created")
                .first()
            )
            if batch is None:
                break
            batch.status = UploadStatus.PROCESSING
            batch.processing_started = timezone.now()
            batch.save(update_fields=["status", "processing_started"])
        claimed += 1
        try:
            token = batch.corpus_access_token
            if token is None:
                raise ValueError(
                    "Corpus access token was deleted before this batch drained; "
                    "re-push under a live token."
                )
            # Re-validate the token AT DRAIN TIME, not only at push time.
            # Revoking a token (the normal soft-deactivate path) is how an
            # operator stops a misbehaving harvester, and authority-section
            # push has a strictly larger blast radius than document upload —
            # it creates/versions documents and relinks every citing corpus.
            # Letting already-staged batches execute past revocation would
            # make the revocation ineffective for exactly the operation that
            # most needs it. ``is_valid`` is the same predicate
            # WorkerTokenAuthentication enforces on the push path (token
            # active, account active, not expired); worker_account is
            # select_related above, so this costs no extra query.
            if not token.is_valid:
                raise ValueError(
                    "Corpus access token was revoked or expired before this "
                    "batch drained; re-push under a live token."
                )
            if not token.can_push_authority_sections:
                raise ValueError(
                    "Corpus access token no longer carries the "
                    "authority-section push capability; re-push under a token "
                    "minted with --allow-authority-sections."
                )
            creator = batch.corpus.creator
            if creator is None or not creator.is_active:
                raise ValueError(
                    f"Corpus {batch.corpus_id} has no active creator; cannot "
                    "bootstrap authority sections."
                )
            sections, aliases = parse_section_spec(
                batch.payload, label=f"batch {batch.id}"
            )
            result = bootstrap_authority_corpus(
                creator_id=creator.id,
                corpus_title=batch.corpus.title,
                corpus_id=batch.corpus_id,
                sections=sections,
                aliases=aliases,
                relink=True,
                relink_async=True,
            )
            # Record the bootstrap outcome BEFORE the equivalence loop. By
            # this point real Document rows have been created/versioned, so a
            # later equivalence failure must not erase the evidence of that:
            # the batch would go FAILED carrying only an equivalence error,
            # and nothing re-queues a FAILED batch (recover_stalled_uploads
            # only reclaims stalled PROCESSING rows). The report is saved on
            # both the success and the failure path below.
            batch.report = {"bootstrap": _json_safe_bootstrap_report(result)}
            eq_outcomes: dict[str, int] = {}
            for row in batch.payload.get("equivalences", []):
                outcome = upsert_equivalence(
                    from_key=row["from_key"],
                    to_key=row["to_key"],
                    source=f"worker:{token.worker_account.name}",
                    confidence=1.0,
                    note=row.get("note"),
                )
                eq_outcomes[outcome] = eq_outcomes.get(outcome, 0) + 1
            batch.report["equivalences"] = eq_outcomes
            batch.status = UploadStatus.COMPLETED
            processed["completed"] += 1
        except (
            Exception
        ) as exc:  # noqa: BLE001 — batch isolation: one bad batch must not stall the queue
            logger.exception(f"Authority-section batch {batch.id} failed")
            batch.status = UploadStatus.FAILED
            batch.error_message = str(exc)[:MAX_UPLOAD_ERROR_MESSAGE_LENGTH]
            processed["failed"] += 1
        batch.processing_finished = timezone.now()
        batch.save(
            update_fields=[
                "status",
                "report",
                "error_message",
                "processing_finished",
            ]
        )

    # Yield back to the scheduler between capped runs so a large backlog can't
    # monopolise the worker_uploads queue (mirrors process_pending_uploads).
    if WorkerAuthoritySectionBatch.objects.filter(status=UploadStatus.PENDING).exists():
        process_pending_section_batches.apply_async(
            queue="worker_uploads",
            countdown=1,  # Brief pause to avoid a tight loop
            ignore_result=True,
        )
    return processed
