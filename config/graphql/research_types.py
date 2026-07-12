"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import datetime
from typing import Annotated

import strawberry

from config.graphql import enums
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql.core.filtering import setup_filterset
from config.graphql.core.relay import (
    Node,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_visible_fk,
)
from config.graphql.core.scalars import GenericScalar, JSONString
from config.graphql.filters import AnnotationFilter
from opencontractserver.research.models import ResearchReport


def _resolve_ResearchReportType_duration_seconds(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/research_types.py:52

    Port of ResearchReportType.resolve_duration_seconds
    """
    return root.duration_seconds


def _resolve_ResearchReportType_my_permissions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/research_types.py:55

    Port of ResearchReportType.resolve_my_permissions
    """
    # Return creator-only permissions; v1 has no sharing surface.
    user = getattr(info.context, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    # Scoped admin access (2026-05): superusers are computed like a normal
    # user — no synthetic full-permission grant. A report is visible (and
    # editable) only to its creator in v1.
    if root.creator_id == getattr(user, "id", None):
        # Creator sees their own report end-to-end; cancel routes
        # through the dedicated mutation, not a guardian grant.
        return [
            "read_researchreport",
            "update_researchreport",
            "remove_researchreport",
        ]
    return []


def _resolve_ResearchReportType_full_source_annotation_list(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/research_types.py:73

    Port of ResearchReportType.resolve_full_source_annotation_list
    """
    return root.source_annotations.all()


def _resolve_ResearchReportType_full_source_document_list(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/research_types.py:76

    Port of ResearchReportType.resolve_full_source_document_list
    """
    return root.source_documents.all()


@strawberry.type(
    name="ResearchReportType",
    description="Deep-research job + final report.\n\nPermissions are intentionally **creator-only** in v1 — there is no\nsharing surface (no `is_public`, no `object_shared_with`), so we\nskip `AnnotatePermissionsForReadMixin` (which assumes guardian\npermission tables that ``ResearchReport`` does not allocate, and\nwould silently swallow the resulting AttributeError as ``[]``).\nThe custom ``my_permissions`` resolver below mirrors what the mixin\nwould return for the creator's own row.",
)
class ResearchReportType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    corpus: Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")] = (
        strawberry.field(name="corpus", default=None)
    )

    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))

    @strawberry.field(name="slug")
    def slug(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "slug", None))

    @strawberry.field(name="prompt", description="The user's research task")
    def prompt(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "prompt", None))

    @strawberry.field(name="status")
    def status(
        self, info: strawberry.Info
    ) -> enums.ResearchResearchReportStatusChoices:
        return coerce_enum(
            enums.ResearchResearchReportStatusChoices, getattr(self, "status", None)
        )

    started_at: datetime.datetime | None = strawberry.field(
        name="startedAt", default=None
    )
    completed_at: datetime.datetime | None = strawberry.field(
        name="completedAt", default=None
    )
    last_progress_at: datetime.datetime | None = strawberry.field(
        name="lastProgressAt", default=None
    )

    @strawberry.field(name="errorMessage")
    def error_message(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "error_message", None))

    cancel_requested: bool = strawberry.field(name="cancelRequested", default=None)
    max_steps: int = strawberry.field(name="maxSteps", default=None)
    step_count: int = strawberry.field(name="stepCount", default=None)

    @strawberry.field(
        name="content",
        description="Rendered final markdown report with footnote citations",
    )
    def content(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "content", None))

    @strawberry.field(
        name="plan",
        description="The agent's living high-level plan. Re-injected into the system prompt at the start of every run so the original task and strategy survive context compaction and worker restarts.",
    )
    def plan(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "plan", None))

    memory: JSONString = strawberry.field(
        name="memory",
        description="Durable key->entry memory store the agent writes to offload content beyond the context window. Each entry is {content, updated_at}. Survives compaction and worker restarts.",
        default=None,
    )
    findings: GenericScalar | None = strawberry.field(name="findings", default=None)
    citations: GenericScalar | None = strawberry.field(name="citations", default=None)
    tool_call_log: GenericScalar | None = strawberry.field(
        name="toolCallLog", default=None
    )
    model_usage: GenericScalar | None = strawberry.field(
        name="modelUsage", default=None
    )
    warnings: GenericScalar | None = strawberry.field(name="warnings", default=None)

    @strawberry.field(
        name="sourceAnnotations", description="Annotations cited in the final report"
    )
    def source_annotations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "source_annotations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(
        name="sourceDocuments",
        description="Documents touched (vector-search hits, summaries loaded, etc.)",
    )
    def source_documents(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentTypeConnection, strawberry.lazy("config.graphql.document_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "source_documents", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentType",
        )

    @strawberry.field(
        name="conversation",
        description="Chat conversation that kicked this off, if any",
    )
    def conversation(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ):
        return resolve_visible_fk(self, info, "conversation_id", "ConversationType")

    originating_message: None | (
        Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")]
    ) = strawberry.field(
        name="originatingMessage",
        description="User chat message that triggered this run, if any",
        default=None,
    )

    @strawberry.field(
        name="durationSeconds",
        description="Seconds between start and completion (null if not finished).",
    )
    def duration_seconds(self, info: strawberry.Info) -> float | None:
        kwargs = strip_unset({})
        return _resolve_ResearchReportType_duration_seconds(self, info, **kwargs)

    @strawberry.field(
        name="myPermissions",
        description="Action verbs the calling user is allowed on this report.",
    )
    def my_permissions(self, info: strawberry.Info) -> list[str | None] | None:
        kwargs = strip_unset({})
        return _resolve_ResearchReportType_my_permissions(self, info, **kwargs)

    @strawberry.field(
        name="fullSourceAnnotationList",
        description="Annotations cited in the final report (creator-only in v1).",
    )
    def full_source_annotation_list(
        self, info: strawberry.Info
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    AnnotationType, strawberry.lazy("config.graphql.annotation_types")
                ]
            )
        ]
    ):
        kwargs = strip_unset({})
        return _resolve_ResearchReportType_full_source_annotation_list(
            self, info, **kwargs
        )

    @strawberry.field(
        name="fullSourceDocumentList",
        description="Documents touched by the research run.",
    )
    def full_source_document_list(
        self, info: strawberry.Info
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    DocumentType, strawberry.lazy("config.graphql.document_types")
                ]
            )
        ]
    ):
        kwargs = strip_unset({})
        return _resolve_ResearchReportType_full_source_document_list(
            self, info, **kwargs
        )


def _get_node_ResearchReportType(info, pk):
    """PORT: config.graphql.research_types.ResearchReportType.get_node

    Port of ResearchReportType.get_node
    """
    # Permission-checked node resolution.
    from opencontractserver.shared.services.base import BaseService

    obj = BaseService.get_or_none(
        ResearchReport, int(pk), info.context.user, request=info.context
    )
    return obj


register_type(
    "ResearchReportType",
    ResearchReportType,
    model=ResearchReport,
    get_node=_get_node_ResearchReportType,
)


ResearchReportTypeConnection = make_connection_types(
    ResearchReportType,
    type_name="ResearchReportTypeConnection",
    countable=True,
    pdf_page_aware=False,
)
