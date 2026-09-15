"""Search readiness is an observation, separate from an upload receipt.

Corpus callers paginate documents. Coverage is aggregated in SQL; repair only
materializes one bounded batch. No readiness or repair path invokes a parser.
"""

import hashlib
import json
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from opencontractserver.annotations.models import Annotation
from opencontractserver.constants.search import DIM_TO_FIELD_MAP
from opencontractserver.corpuses.services.corpus_service import CorpusService
from opencontractserver.documents.models import (
    Document,
    DocumentProcessingStatus,
    EmbeddingRepair,
    PipelineSettings,
)
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.utils import get_component_by_name
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.embedding_identity import (
    embedding_configuration,
    valid_embeddings,
)

REPAIR_BATCH_SIZE = 100
MAX_TEXT_BYTES = 16 * 1024 * 1024
REPAIR_TIMEOUT = timedelta(minutes=15)
logger = logging.getLogger(__name__)


class ReadinessUnavailable(ValueError):
    """An intentional, safe diagnostic code for readiness callers."""


def effective_embedder(corpus=None, *, path=None):
    pipeline = PipelineSettings.get_instance(use_cache=False)
    path = (
        path
        or (corpus.preferred_embedder if corpus else None)
        or pipeline.default_embedder
    )
    if not path or not pipeline.is_component_enabled(path):
        raise ReadinessUnavailable("embedder_unavailable")
    try:
        component = get_component_by_name(path)
    except (ValueError, LookupError, ImportError):
        raise ReadinessUnavailable("embedder_configuration_unavailable") from None
    if not issubclass(component, BaseEmbedder):
        raise ReadinessUnavailable("invalid_embedder")
    embedder = component(component_settings=pipeline.get_full_component_settings(path))
    if embedder.vector_size not in DIM_TO_FIELD_MAP:
        raise ReadinessUnavailable("unsupported_dimension")
    return path, embedder.vector_size, embedding_configuration(embedder)


def generation(document, configuration):
    values = [
        configuration,
        document.pk,
        str(document.processing_started),
        str(document.processing_finished),
        document.processing_status,
        document.structural_annotation_set_id,
        document.txt_extract_file.name or "",
        document.pawls_parse_file.name or "",
    ]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def document_annotations(document, corpus=None):
    scope = Q(document=document)
    if document.structural_annotation_set_id:
        scope |= Q(
            structural=True, structural_set_id=document.structural_annotation_set_id
        )
    annotations = (
        CorpusService.annotations_in_corpus(corpus)
        if corpus
        else Annotation.objects.all()
    )
    return annotations.filter(scope).exclude(
        Q(raw_text__isnull=True) | Q(raw_text__regex=r"^\s*$")
    )


def document_has_text(document):
    """Inspect a bounded artifact, distinguishing empty text from unavailable text."""
    if not document.txt_extract_file.name:
        raise ReadinessUnavailable("text_artifact_missing")
    with document.txt_extract_file.open("rb") as stream:
        content = stream.read(MAX_TEXT_BYTES + 1)
    if len(content) > MAX_TEXT_BYTES:
        raise ReadinessUnavailable("text_artifact_exceeds_status_limit")
    return bool(content.decode("utf-8").strip())


def repair_progress(document):
    job = EmbeddingRepair.objects.filter(document=document).first()
    if job is None:
        return None
    status = job.status
    if (
        status in ("queued", "running")
        and job.requested < timezone.now() - REPAIR_TIMEOUT
    ):
        status = "stalled"
    return {
        "id": job.pk,
        "generation": job.generation,
        "status": status,
        "attempted": job.attempted,
        "succeeded": job.succeeded,
        "failed": job.failed,
        "errors": job.errors,
    }


def assess_document(document, corpus=None):
    result = {
        "schema_version": 1,
        "document_id": document.pk,
        "state": "outstanding",
        "generation": None,
        "reasons": [],
        "processing_status": document.processing_status,
        "processing_error": " ".join(document.processing_error.split())[:1000],
        "required_stages": [
            "parsing",
            "annotations",
            "document_embedding",
            "annotation_embeddings",
        ],
        "optional_artifacts": {"thumbnail": bool(document.icon.name)},
        "repair": repair_progress(document),
    }
    try:
        path, dimension, configuration = effective_embedder(corpus)
        result["embedding"] = {
            "path": path,
            "dimension": dimension,
            "configuration": configuration,
        }
        result["generation"] = generation(document, configuration)
        has_text = document_has_text(document)
        annotations = document_annotations(document, corpus)
        eligible = annotations.count()
        missing = CorpusService.count_annotations_missing_embeddings(
            corpus,
            path,
            dimension=dimension,
            configuration=configuration,
            annotations=annotations,
        )
        doc_valid = int(
            has_text
            and valid_embeddings(path, dimension, configuration)
            .filter(document=document)
            .exists()
        )
        result["coverage"] = {
            "documents": {"eligible": int(has_text), "valid": doc_valid},
            "annotations": {"eligible": eligible, "valid": eligible - missing},
        }
        reasons = result["reasons"]
        if document.processing_status != DocumentProcessingStatus.COMPLETED:
            reasons.append(f"parsing_{document.processing_status}")
        pending = document.pending_annotations.exclude(status="done")
        if pending.exists():
            reasons.append("annotations_outstanding")
        if has_text and not doc_valid:
            reasons.append("document_embedding_missing_or_invalid")
        if missing:
            reasons.append("annotation_embeddings_missing_or_invalid")
        if (
            document.processing_status == DocumentProcessingStatus.FAILED
            or pending.filter(status="failed").exists()
        ):
            result["state"] = "failed"
        elif not reasons:
            result["state"] = "ready"
        elif (
            result["repair"]
            and result["repair"]["generation"] == result["generation"]
            and result["repair"]["status"] in ("failed", "stalled")
        ):
            result["state"] = "failed"
            reasons.append("embedding_repair_failed")
        # A concurrent parse/configuration change invalidates this observation.
        fresh = Document.objects.get(pk=document.pk)
        if generation(fresh, effective_embedder(corpus)[2]) != result["generation"]:
            result["state"] = "unavailable"
            reasons.append("generation_changed")
    except (OSError, ValueError, LookupError, UnicodeError) as exc:
        logger.warning(
            "Readiness unavailable for document %s", document.pk, exc_info=True
        )
        result["state"] = "unavailable"
        if isinstance(exc, ReadinessUnavailable):
            reason = str(exc)
        elif isinstance(exc, FileNotFoundError):
            reason = "text_artifact_missing"
        elif isinstance(exc, UnicodeError):
            reason = "text_artifact_invalid_utf8"
        elif isinstance(exc, OSError):
            reason = "text_storage_unavailable"
        else:
            reason = "embedder_configuration_unavailable"
        result["reasons"].append(reason)
    return result


def repair_authorized(document, corpus, user, token=None):
    if not user.is_active:
        return False
    if token:
        from opencontractserver.worker_uploads.models import WorkerDocumentUpload

        return (
            token.is_valid
            and token.corpus_id == getattr(corpus, "pk", None)
            and WorkerDocumentUpload.objects.filter(
                result_document=document, corpus_access_token=token
            ).exists()
        )
    return all(
        BaseService.user_has(obj, user, permission)
        for obj in (document, corpus)
        if obj is not None
        for permission in (PermissionTypes.READ, PermissionTypes.UPDATE)
    )


def request_repair(document, corpus=None, *, user, token=None):
    from opencontractserver.tasks.readiness_tasks import repair_document_embeddings

    with transaction.atomic():
        document = Document.objects.select_for_update().get(pk=document.pk)
        if not repair_authorized(document, corpus, user, token):
            raise PermissionError("Repair is not authorized")
        assessment = assess_document(document, corpus)
        progress = assessment["repair"]
        if progress and progress["status"] in ("queued", "running"):
            return assessment
        if (
            assessment["state"] in ("ready", "unavailable")
            or document.processing_status != DocumentProcessingStatus.COMPLETED
        ):
            return assessment
        if all(
            item["eligible"] == item["valid"]
            for item in assessment["coverage"].values()
        ):
            return assessment
        job, _ = EmbeddingRepair.objects.update_or_create(
            document=document,
            defaults={
                "corpus": corpus,
                "requested_by": user,
                "worker_token": token,
                "generation": assessment["generation"],
                "status": "queued",
                "requested": timezone.now(),
                "finished": None,
                "attempted": 0,
                "succeeded": 0,
                "failed": 0,
                "errors": [],
            },
        )

        def dispatch():
            try:
                repair_document_embeddings.delay(job.pk)
            except Exception:
                EmbeddingRepair.objects.filter(pk=job.pk, status="queued").update(
                    status="failed", errors=["dispatch_failed"], finished=timezone.now()
                )

        transaction.on_commit(dispatch)
        assessment["repair"] = repair_progress(document)
        return assessment
