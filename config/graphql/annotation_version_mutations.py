"""Mutations for reviewing human annotations across a document version-up.

``carryForwardAnnotation`` re-approves or corrects a stale annotation by
creating an ordinary successor annotation on the new version and recording an
``AnnotationVersionDecision``; ``dropStaleAnnotation`` records that it no longer
applies. Both go through ``AnnotationVersionReviewService`` (permission:
UPDATE on the target document). Design:
``docs/architecture/reference-web-versioning.md`` (change 5).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated

import strawberry

from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.relay import register_type
from config.graphql.core.scalars import GenericScalar
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.annotations.services import AnnotationVersionReviewService
from opencontractserver.documents.models import Document
from opencontractserver.shared.services.base import BaseService
from opencontractserver.utils.ids import from_global_id

if TYPE_CHECKING:
    from config.graphql.annotation_types import AnnotationType

logger = logging.getLogger(__name__)

_NOT_FOUND = "Annotation or document not found"


@strawberry.type(
    name="CarryForwardAnnotation",
    description=(
        "Carry a human annotation from a superseded document version onto its "
        "successor. Creates an ordinary annotation on the target version and "
        "records the decision: REAPPROVED when text and label are unchanged, "
        "CORRECTED otherwise.\n\nPermission requirements:\n- READ on the "
        "annotation\n- UPDATE on the target document"
    ),
)
class CarryForwardAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    decision: str | None = strawberry.field(
        name="decision",
        description="REAPPROVED or CORRECTED when ok.",
        default=None,
    )
    successor: None | (
        Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="successor", default=None)


register_type("CarryForwardAnnotation", CarryForwardAnnotation, model=None)


@strawberry.type(
    name="DropStaleAnnotation",
    description=(
        "Record that a human annotation from a superseded document version no "
        "longer applies on its successor (decision DROPPED).\n\nPermission "
        "requirements:\n- READ on the annotation\n- UPDATE on the target document"
    ),
)
class DropStaleAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DropStaleAnnotation", DropStaleAnnotation, model=None)


def _load_pair(info, annotation_id: str, target_document_id: str):
    """IDOR-safe lookup of both rows; ``None`` for either collapses missing
    and invisible into one answer. The annotation lives on a superseded
    version, which ``Annotation.objects.visible_to_user`` hides by design, so
    it goes through the review service's own MIN(document, corpus) gate."""
    try:
        annotation_pk = from_global_id(annotation_id)[1]
        document_pk = from_global_id(target_document_id)[1]
    except Exception:
        return None, None
    annotation = AnnotationVersionReviewService.get_reviewable_annotation(
        info.context.user, annotation_pk, request=info.context
    )
    document = BaseService.get_or_none(
        Document, document_pk, info.context.user, request=info.context
    )
    return annotation, document


def _mutate_CarryForwardAnnotation(payload_cls, root, info, **kwargs):
    @login_required
    def mutate(
        root,
        info,
        annotation_id,
        target_document_id,
        json,
        page,
        annotation_type,
        raw_text,
        annotation_label_id=None,
    ) -> CarryForwardAnnotation:
        annotation, document = _load_pair(info, annotation_id, target_document_id)
        if annotation is None or document is None:
            return CarryForwardAnnotation(ok=False, message=_NOT_FOUND)
        label = None
        if annotation_label_id:
            try:
                label_pk = from_global_id(annotation_label_id)[1]
            except Exception:
                return CarryForwardAnnotation(ok=False, message="Label not found")
            label = BaseService.get_or_none(
                AnnotationLabel, label_pk, info.context.user, request=info.context
            )
            if label is None:
                return CarryForwardAnnotation(ok=False, message="Label not found")
        if not isinstance(json, dict):
            return CarryForwardAnnotation(
                ok=False, message="json must be an annotation payload object"
            )
        decision, error = AnnotationVersionReviewService.carry_forward(
            info.context.user,
            annotation,
            document,
            json=json,
            page=int(page),
            annotation_type=annotation_type,
            raw_text=raw_text or "",
            annotation_label=label,
            request=info.context,
        )
        if error:
            return CarryForwardAnnotation(ok=False, message=error)
        return CarryForwardAnnotation(
            ok=True,
            message="Annotation carried forward",
            decision=decision.decision,
            successor=decision.successor,
        )

    return mutate(root, info, **kwargs)


def _mutate_DropStaleAnnotation(payload_cls, root, info, **kwargs):
    @login_required
    def mutate(root, info, annotation_id, target_document_id) -> DropStaleAnnotation:
        annotation, document = _load_pair(info, annotation_id, target_document_id)
        if annotation is None or document is None:
            return DropStaleAnnotation(ok=False, message=_NOT_FOUND)
        _, error = AnnotationVersionReviewService.drop(
            info.context.user, annotation, document, request=info.context
        )
        if error:
            return DropStaleAnnotation(ok=False, message=error)
        return DropStaleAnnotation(ok=True, message="Annotation dropped")

    return mutate(root, info, **kwargs)


def m_carry_forward_annotation(
    info: strawberry.Info,
    annotation_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="annotationId",
            description="The human annotation on the superseded version.",
        ),
    ] = strawberry.UNSET,
    target_document_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="targetDocumentId",
            description="The direct successor version to carry it onto.",
        ),
    ] = strawberry.UNSET,
    json: Annotated[
        GenericScalar,
        strawberry.argument(
            name="json",
            description=(
                "Annotation payload on the new version: {start, end, text} for "
                "SPAN_LABEL or the PAWLs token payload for TOKEN_LABEL (typically "
                "the proposedJson from annotationVersionReview)."
            ),
        ),
    ] = strawberry.UNSET,
    page: Annotated[
        int, strawberry.argument(name="page", description="Page of the payload.")
    ] = strawberry.UNSET,
    annotation_type: Annotated[
        str,
        strawberry.argument(
            name="annotationType", description="SPAN_LABEL or TOKEN_LABEL."
        ),
    ] = strawberry.UNSET,
    raw_text: Annotated[
        str,
        strawberry.argument(name="rawText", description="Text covered by the payload."),
    ] = strawberry.UNSET,
    annotation_label_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="annotationLabelId",
            description="Override label; defaults to the original annotation's label.",
        ),
    ] = strawberry.UNSET,
) -> CarryForwardAnnotation | None:
    kwargs = strip_unset(
        {
            "annotation_id": annotation_id,
            "target_document_id": target_document_id,
            "json": json,
            "page": page,
            "annotation_type": annotation_type,
            "raw_text": raw_text,
            "annotation_label_id": annotation_label_id,
        }
    )
    return _mutate_CarryForwardAnnotation(CarryForwardAnnotation, None, info, **kwargs)


def m_drop_stale_annotation(
    info: strawberry.Info,
    annotation_id: Annotated[
        strawberry.ID, strawberry.argument(name="annotationId")
    ] = strawberry.UNSET,
    target_document_id: Annotated[
        strawberry.ID, strawberry.argument(name="targetDocumentId")
    ] = strawberry.UNSET,
) -> DropStaleAnnotation | None:
    kwargs = strip_unset(
        {"annotation_id": annotation_id, "target_document_id": target_document_id}
    )
    return _mutate_DropStaleAnnotation(DropStaleAnnotation, None, info, **kwargs)


MUTATION_FIELDS = {
    "carry_forward_annotation": strawberry.field(
        resolver=m_carry_forward_annotation,
        name="carryForwardAnnotation",
        description=(
            "Re-approve or correct a stale human annotation on the next document "
            "version (creates the successor annotation and records the decision)."
        ),
    ),
    "drop_stale_annotation": strawberry.field(
        resolver=m_drop_stale_annotation,
        name="dropStaleAnnotation",
        description="Record that a stale human annotation no longer applies on the next document version.",
    ),
}
