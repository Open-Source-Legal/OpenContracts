"""GraphQL surface for reviewing annotations carried onto a new document version."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Annotated

import strawberry
from django.core.exceptions import ValidationError
from graphql import GraphQLError

from config.graphql.core.scalars import GenericScalar
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.annotations.services.version_review import (
    AnnotationVersionReviewService as Review,
)
from opencontractserver.utils.ids import from_global_id

if TYPE_CHECKING:
    from config.graphql.annotation_types import AnnotationType
    from config.graphql.user_types import UserType


@strawberry.enum
class AnnotationVersionState(Enum):
    AUTO = "AUTO"
    STALE = "STALE"
    REAPPROVED = "REAPPROVED"
    CORRECTED = "CORRECTED"
    DROPPED = "DROPPED"


@strawberry.type
class AnnotationVersionReview:
    annotation: Annotated[
        "AnnotationType", strawberry.lazy("config.graphql.annotation_types")
    ]
    state: AnnotationVersionState
    successor: (
        Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]
        | None
    ) = None
    reviewed_by: (
        Annotated["UserType", strawberry.lazy("config.graphql.user_types")] | None
    ) = None
    reviewed_at: datetime | None = None


def _pk(value, type_name):
    kind, pk = from_global_id(value)
    if kind != type_name or not pk.isdigit():
        raise GraphQLError("Invalid review identifier.")
    return int(pk)


def _row(decision):
    return AnnotationVersionReview(
        annotation=decision.annotation,
        state=AnnotationVersionState(decision.decision),
        successor=decision.successor,
        reviewed_by=decision.reviewer,
        reviewed_at=decision.reviewed_at,
    )


def q_annotation_version_review(
    info: strawberry.Info, document_id: strawberry.ID, corpus_id: strawberry.ID
) -> list[AnnotationVersionReview]:
    return [
        _row(decision)
        for decision in Review.review(
            info.context.user,
            _pk(document_id, "DocumentType"),
            _pk(corpus_id, "CorpusType"),
        )
    ]


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_LIGHT"), group="mutate")
def _write_gate(root, info):
    return None


def _decide(
    info,
    annotation_id,
    target_document_id,
    *,
    drop=False,
    placement=None,
    annotation_label_id=None
):
    _write_gate(None, info)
    args = (
        info.context.user,
        _pk(annotation_id, "AnnotationType"),
        _pk(target_document_id, "DocumentType"),
    )
    try:
        decision = (
            Review.drop(*args)
            if drop
            else Review.carry_forward(
                *args,
                placement=placement,
                label_id=(
                    _pk(annotation_label_id, "AnnotationLabelType")
                    if annotation_label_id
                    else None
                ),
            )
        )
    except ValidationError as exc:
        raise GraphQLError(" ".join(exc.messages)) from None
    # Both ends of the decision changed state for this request.
    states = getattr(info.context, "_annotation_version_states", {})
    states.pop((decision.annotation.document_id, decision.annotation.corpus_id), None)
    states.pop((decision.target_document_id, decision.annotation.corpus_id), None)
    return _row(decision)


def m_carry_forward_annotation(
    info: strawberry.Info,
    annotation_id: strawberry.ID,
    target_document_id: strawberry.ID,
    placement: GenericScalar | None = None,  # type: ignore[valid-type]
    annotation_label_id: strawberry.ID | None = None,
) -> AnnotationVersionReview:
    return _decide(
        info,
        annotation_id,
        target_document_id,
        placement=placement,
        annotation_label_id=annotation_label_id,
    )


def m_drop_stale_annotation(
    info: strawberry.Info,
    annotation_id: strawberry.ID,
    target_document_id: strawberry.ID,
) -> AnnotationVersionReview:
    return _decide(info, annotation_id, target_document_id, drop=True)


QUERY_FIELDS = {
    "annotation_version_review": strawberry.field(resolver=q_annotation_version_review)
}
MUTATION_FIELDS = {
    "carry_forward_annotation": strawberry.field(resolver=m_carry_forward_annotation),
    "drop_stale_annotation": strawberry.field(resolver=m_drop_stale_annotation),
}
