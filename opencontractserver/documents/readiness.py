"""Search readiness is an observation, separate from an upload receipt.

Corpus callers paginate documents. Coverage is aggregated in SQL; repair only
materializes one bounded batch. No readiness or repair path invokes a parser.
"""

import hashlib
import json
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from opencontractserver.annotations.models import Annotation
from opencontractserver.constants.readiness import (
    MAX_TEXT_BYTES,
    REPAIR_TIMEOUT,
)
from opencontractserver.constants.search import DIM_TO_FIELD_MAP
from opencontractserver.corpuses.services.corpus_service import CorpusService
from opencontractserver.documents.models import (
    Document,
    DocumentProcessingStatus,
    EmbeddingRepair,
    PipelineSettings,
)
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.settings_schema import ConfigurationError
from opencontractserver.pipeline.utils import get_component_by_name
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.embedding_identity import (
    embeddable_annotations,
    embedding_configuration,
    valid_embeddings,
)
from opencontractserver.utils.public_errors import PublicError

logger = logging.getLogger(__name__)


class ReadinessUnavailable(PublicError):
    """An intentional, safe diagnostic code for readiness callers."""

    default_code = "readiness_unavailable"
    public_codes = frozenset(
        {
            "document_deleted",
            "embedder_configuration_unavailable",
            "embedder_unavailable",
            "invalid_embedder",
            "text_artifact_exceeds_status_limit",
            "text_artifact_missing",
            "unsupported_dimension",
        }
    )


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
    try:
        # Passing settings makes construction strict: a required setting that
        # is unset raises rather than producing a half-configured embedder.
        embedder = component(
            component_settings=pipeline.get_full_component_settings(path)
        )
    except ConfigurationError:
        raise ReadinessUnavailable("embedder_configuration_unavailable") from None
    if embedder.vector_size not in DIM_TO_FIELD_MAP:
        raise ReadinessUnavailable("unsupported_dimension")
    configuration = embedding_configuration(embedder)
    if not configuration:
        raise ReadinessUnavailable("embedder_configuration_unavailable")
    return path, embedder.vector_size, configuration


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
    return embeddable_annotations(annotations.filter(scope))


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


def unavailable(document, corpus, reason):
    """The minimal observation for a document whose assessment did not run."""
    return {
        "schema_version": 1,
        "document_id": document.pk,
        "corpus_id": corpus.pk if corpus else None,
        "state": "unavailable",
        "generation": None,
        "reasons": [reason],
    }


def assess_documents(documents, corpus):
    """Assess a page of documents without letting one of them fail the page.

    The corpus embedder is resolved once for the whole page; if that fails,
    every document reports the reason through its own assessment.
    """
    try:
        embedder = effective_embedder(corpus)
    except ReadinessUnavailable as exc:
        return [
            unavailable(document, corpus, exc.public_code) for document in documents
        ]
    results = []
    for document in documents:
        try:
            results.append(assess_document(document, corpus, embedder=embedder))
        except Exception:
            logger.exception("Readiness assessment failed for document %s", document.pk)
            results.append(unavailable(document, corpus, "assessment_failed"))
    return results


def assess_document(document, corpus=None, *, embedder=None):
    """Observe one document; ``embedder`` is an ``effective_embedder`` result."""
    result = {
        "schema_version": 1,
        "document_id": document.pk,
        "corpus_id": corpus.pk if corpus else None,
        "state": "outstanding",
        "generation": None,
        "reasons": [],
        "processing_status": document.processing_status,
        # Stored parser errors can contain paths, credentials and tracebacks.
        "processing_error": (
            "document_processing_failed" if document.processing_error else ""
        ),
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
        path, dimension, configuration = embedder or effective_embedder(corpus)
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
        pending = set(
            document.pending_annotations.exclude(status="done")
            .values_list("status", flat=True)
            .distinct()
        )
        if pending:
            reasons.append("annotations_outstanding")
        if has_text and not doc_valid:
            reasons.append("document_embedding_missing_or_invalid")
        if missing:
            reasons.append("annotation_embeddings_missing_or_invalid")
        if (
            document.processing_status == DocumentProcessingStatus.FAILED
            or "failed" in pending
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
        # A concurrent re-parse invalidates this observation. Configuration
        # changes are not re-checked here: the generation already carries the
        # configuration, so the next observation reports a new generation and
        # a queued repair refuses to run against the old one.
        fresh = Document.objects.filter(pk=document.pk).first()
        if fresh is None:
            raise ReadinessUnavailable("document_deleted")
        if generation(fresh, configuration) != result["generation"]:
            result["state"] = "unavailable"
            reasons.append("generation_changed")
    except (OSError, ValueError, LookupError, UnicodeError) as exc:
        logger.warning(
            "Readiness unavailable for document %s", document.pk, exc_info=True
        )
        result["state"] = "unavailable"
        if isinstance(exc, ReadinessUnavailable):
            reason = exc.public_code
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
        from opencontractserver.worker_uploads.upload_recovery import receipts_for_token

        return (
            token.is_valid
            and token.corpus_id == getattr(corpus, "pk", None)
            and receipts_for_token(token).filter(result_document=document).exists()
        )
    return all(
        BaseService.user_has(obj, user, permission)
        for obj in (document, corpus)
        if obj is not None
        for permission in (PermissionTypes.READ, PermissionTypes.UPDATE)
    )


def request_repair(document, corpus=None, *, user, token=None):
    from opencontractserver.tasks.readiness_tasks import repair_document_embeddings

    # A running batch holds the document lock during inference. Repeated
    # requests can observe its progress without waiting for that lock.
    progress = repair_progress(document)
    if progress and progress["status"] in ("queued", "running"):
        if not repair_authorized(document, corpus, user, token):
            raise PermissionError("Repair is not authorized")
        return assess_document(document, corpus)
    with transaction.atomic():
        locked = Document.objects.select_for_update().filter(pk=document.pk).first()
        if locked is None:
            return unavailable(document, corpus, "document_deleted")
        document = locked
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
