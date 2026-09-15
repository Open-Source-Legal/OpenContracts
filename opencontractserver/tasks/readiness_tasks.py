"""Bounded embedding repair, using the normal embedding task implementations."""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from opencontractserver.annotations.models import StructuralAnnotationSet
from opencontractserver.documents.models import Document, EmbeddingRepair
from opencontractserver.documents.readiness import (
    REPAIR_BATCH_SIZE,
    assess_document,
    document_annotations,
    repair_authorized,
)
from opencontractserver.tasks.embeddings_task import (
    calculate_embedding_for_doc_text,
    calculate_embeddings_for_annotation_batch,
)
from opencontractserver.utils.embedding_identity import valid_embeddings

logger = logging.getLogger(__name__)


@shared_task(soft_time_limit=540, time_limit=600)
def repair_document_embeddings(job_id):
    if not EmbeddingRepair.objects.filter(pk=job_id, status="queued").update(
        status="running"
    ):
        return
    job = EmbeddingRepair.objects.select_related(
        "corpus", "requested_by", "worker_token__worker_account__user"
    ).get(pk=job_id)
    try:
        with transaction.atomic():
            document = Document.objects.select_for_update().get(pk=job.document_id)
            if not repair_authorized(
                document, job.corpus, job.requested_by, job.worker_token
            ):
                raise PermissionError("Repair authorization changed")
            # Corpus copies share these vectors. Serialize repairs across copies,
            # then recheck coverage so the second repair preserves the first's work.
            if document.structural_annotation_set_id:
                StructuralAnnotationSet.objects.select_for_update().get(
                    pk=document.structural_annotation_set_id
                )
            before = assess_document(document, job.corpus)
            if (
                before["state"] == "unavailable"
                or before["generation"] != job.generation
            ):
                raise ValueError("generation_changed")
            identity = before["embedding"]
            valid = valid_embeddings(
                identity["path"], identity["dimension"], identity["configuration"]
            )
            needs_doc = (
                before["coverage"]["documents"]["eligible"]
                > before["coverage"]["documents"]["valid"]
            )
            annotation_ids = list(
                document_annotations(document, job.corpus)
                .exclude(
                    pk__in=valid.filter(annotation_id__isnull=False).values(
                        "annotation_id"
                    )
                )
                .order_by("pk")
                .values_list("pk", flat=True)[: REPAIR_BATCH_SIZE - int(needs_doc)]
            )
            job.attempted = len(annotation_ids) + int(needs_doc)
            if needs_doc:
                try:
                    with transaction.atomic():
                        calculate_embedding_for_doc_text.apply(
                            kwargs={
                                "doc_id": document.pk,
                                "embedder_path": identity["path"],
                            },
                            throw=True,
                        )
                except Exception:
                    logger.exception(
                        "Document embedding repair failed: %s", document.pk
                    )
                    job.errors.append("document_embedding_failed")
            if annotation_ids:
                try:
                    with transaction.atomic():
                        calculate_embeddings_for_annotation_batch.apply(
                            kwargs={
                                "annotation_ids": annotation_ids,
                                "embedder_path": identity["path"],
                            },
                            throw=True,
                        )
                except Exception:
                    logger.exception(
                        "Annotation embedding repair failed: %s", document.pk
                    )
                    job.errors.append("annotation_batch_failed")
            # Count stored, valid results; a task returning normally can still
            # contain partial failures or vectors of the wrong dimension.
            job.succeeded = valid.filter(annotation_id__in=annotation_ids).count()
            if needs_doc:
                job.succeeded += int(valid.filter(document=document).exists())
            job.failed = job.attempted - job.succeeded
            job.status = "failed" if job.failed else "completed"
            if job.failed:
                job.errors.append("embedding_results_missing_or_invalid")
    except Exception:
        logger.exception("Embedding repair batch failed: %s", job_id)
        job.status = "failed"
        job.failed = job.attempted
        job.succeeded = 0
        job.errors.append("repair_failed_or_generation_changed")
    job.finished = timezone.now()
    job.save()
