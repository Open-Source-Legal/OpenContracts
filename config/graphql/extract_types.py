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
from typing import Annotated, Any

import strawberry
from graphql_relay import from_global_id

from config.graphql import enums
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.relay import (
    Node,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_visible_fk,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.filters import AnnotationFilter
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.constants.extracts import MAX_FULL_DATACELL_LIST_LIMIT
from opencontractserver.corpuses.models import CorpusAction, CorpusActionExecution
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.notifications.models import Notification
from opencontractserver.shared.services.base import BaseService


def _get_datacell_qs(extract, user) -> Any:
    """Return the permission-filtered, deterministically ordered queryset.

    Note: this is a module-level function because Graphene-Django resolvers
    receive the Django model instance as ``self``, not the GraphQL type.

    Graphene-Django creates a fresh model instance per resolved object per
    request, so both ``resolve_full_datacell_list`` and ``resolve_datacell_count``
    call this with the same ``(extract, user)`` pair within a single query.
    The queryset itself is lazy (no DB hit until evaluated), so constructing
    it twice is cheap.
    """
    # Imported inside the function rather than at module scope to keep this
    # GraphQL type module's import graph flat.
    from opencontractserver.extracts.services import ExtractService

    return ExtractService.get_extract_datacells(
        extract, user, document_id=None
    ).order_by("document_id", "column_id", "id")


def _resolve_AnalyzerType_icon(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:275

    Port of AnalyzerType.resolve_icon
    """
    return "" if not root.icon else info.context.build_absolute_uri(root.icon.url)


def _resolve_AnalyzerType_analyzer_id(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:261

    Port of AnalyzerType.resolve_analyzer_id
    """
    return root.id.__str__()


def _resolve_AnalyzerType_full_label_list(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:272

    Port of AnalyzerType.resolve_full_label_list
    """
    return root.annotation_labels.all()


@strawberry.type(name="AnalyzerType")
class AnalyzerType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    manifest: GenericScalar | None = strawberry.field(name="manifest", default=None)

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    disabled: bool = strawberry.field(name="disabled", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)

    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_AnalyzerType_icon(self, info, **kwargs)

    host_gremlin: GremlinEngineType_WRITE | None = strawberry.field(
        name="hostGremlin", default=None
    )

    @strawberry.field(name="taskName")
    def task_name(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "task_name", None))

    input_schema: GenericScalar | None = strawberry.field(
        name="inputSchema",
        description="JSONSchema describing the analyzer's expected input if provided.",
        default=None,
    )

    @strawberry.field(name="corpusactionSet")
    def corpusaction_set(
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
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        name: Annotated[
            str | None, strawberry.argument(name="name")
        ] = strawberry.UNSET,
        name__icontains: Annotated[
            str | None, strawberry.argument(name="name_Icontains")
        ] = strawberry.UNSET,
        name__istartswith: Annotated[
            str | None, strawberry.argument(name="name_Istartswith")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        fieldset__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="fieldset_Id")
        ] = strawberry.UNSET,
        analyzer__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analyzer_Id")
        ] = strawberry.UNSET,
        agent_config__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="agentConfig_Id")
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
        source_template__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="sourceTemplate_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "name": name,
                "name__icontains": name__icontains,
                "name__istartswith": name__istartswith,
                "corpus__id": corpus__id,
                "fieldset__id": fieldset__id,
                "analyzer__id": analyzer__id,
                "agent_config__id": agent_config__id,
                "trigger": trigger,
                "creator__id": creator__id,
                "source_template__id": source_template__id,
            }
        )
        resolved = getattr(self, "corpusaction_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionType",
            filterset_class=filterset_factory(
                CorpusAction,
                fields={
                    "id": ["exact"],
                    "name": ["exact", "icontains", "istartswith"],
                    "corpus__id": ["exact"],
                    "fieldset__id": ["exact"],
                    "analyzer__id": ["exact"],
                    "agent_config__id": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                    "source_template__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "name": "name",
                "name__icontains": "name__icontains",
                "name__istartswith": "name__istartswith",
                "corpus__id": "corpus__id",
                "fieldset__id": "fieldset__id",
                "analyzer__id": "analyzer__id",
                "agent_config__id": "agent_config__id",
                "trigger": "trigger",
                "creator__id": "creator__id",
                "source_template__id": "source_template__id",
            },
        )

    @strawberry.field(name="annotationLabels")
    def annotation_labels(
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
        AnnotationLabelTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
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
        resolved = getattr(self, "annotation_labels", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationLabelType",
        )

    @strawberry.field(name="relationshipSet")
    def relationship_set(
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
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
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
        resolved = getattr(self, "relationship_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="labelsetSet")
    def labelset_set(
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
        LabelSetTypeConnection, strawberry.lazy("config.graphql.annotation_types")
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
        resolved = getattr(self, "labelset_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="LabelSetType",
        )

    @strawberry.field(name="analysisSet")
    def analysis_set(
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
    ) -> AnalysisTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "analysis_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalysisType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(name="analyzerId")
    def analyzer_id(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_AnalyzerType_analyzer_id(self, info, **kwargs)

    @strawberry.field(name="fullLabelList")
    def full_label_list(self, info: strawberry.Info) -> None | (
        list[
            None
            | (
                Annotated[
                    AnnotationLabelType,
                    strawberry.lazy("config.graphql.annotation_types"),
                ]
            )
        ]
    ):
        kwargs = strip_unset({})
        return _resolve_AnalyzerType_full_label_list(self, info, **kwargs)


def _get_node_AnalyzerType(info, pk):
    """Permission-aware node resolution for the singular ``analyzer(id:)`` field
    (IDOR guard). Mirrors the graphene ``BaseService.get_or_none(Analyzer, ...)``
    resolver; without it ``get_node_from_global_id`` would fall back to an
    UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        Analyzer, pk, info.context.user, request=info.context
    )


register_type(
    "AnalyzerType", AnalyzerType, model=Analyzer, get_node=_get_node_AnalyzerType
)


AnalyzerTypeConnection = make_connection_types(
    AnalyzerType,
    type_name="AnalyzerTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(name="GremlinEngineType_WRITE")
class GremlinEngineType_WRITE(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="url")
    def url(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "url", None))

    last_synced: datetime.datetime | None = strawberry.field(
        name="lastSynced", default=None
    )
    install_started: datetime.datetime | None = strawberry.field(
        name="installStarted", default=None
    )
    install_completed: datetime.datetime | None = strawberry.field(
        name="installCompleted", default=None
    )
    is_public: bool = strawberry.field(name="isPublic", default=None)

    @strawberry.field(name="analyzerSet")
    def analyzer_set(
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
    ) -> AnalyzerTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "analyzer_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalyzerType",
        )

    @strawberry.field(name="apiKey")
    def api_key(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "api_key", None))

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("GremlinEngineType_WRITE", GremlinEngineType_WRITE, model=GremlinEngine)


GremlinEngineType_WRITEConnection = make_connection_types(
    GremlinEngineType_WRITE,
    type_name="GremlinEngineType_WRITEConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_ExtractType_full_datacell_list(root, info, limit=None, offset=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:178

    Port of ExtractType.resolve_full_datacell_list
    """
    qs = _get_datacell_qs(root, info.context.user)

    # Guard against negative offset — Django does not support negative
    # indexing on querysets and would raise AssertionError.
    start = max(0, offset) if offset is not None else 0

    if limit is not None:
        # Clamp to [0, MAX_FULL_DATACELL_LIST_LIMIT] so callers cannot
        # bypass the intended payload cap via the GraphQL API.
        limit = max(0, min(limit, MAX_FULL_DATACELL_LIST_LIMIT))
        return qs[start : start + limit]
    # No limit supplied: always apply the server cap regardless of offset
    # so every code path (no-args, offset-only, limit+offset) is bounded.
    return qs[start : start + MAX_FULL_DATACELL_LIST_LIMIT]


def _resolve_ExtractType_full_document_list(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:226

    Port of ExtractType.resolve_full_document_list
    """
    from opencontractserver.extracts.services import ExtractService

    # Bulk visibility filter (no per-document N+1); superusers are computed
    # like a normal user (scoped admin access, 2026-05) — no all-documents
    # branch. Routed through the service per CLAUDE.md rule 7.
    return list(ExtractService.get_visible_documents(root, info.context.user))


def _resolve_ExtractType_document_count(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:200

    Port of ExtractType.resolve_document_count
    """
    # Mirrors the per-document permission filter applied by
    # ``resolve_full_document_list`` so the count never exceeds the list
    # length the same viewer would observe (effective permission is
    # ``MIN(document, corpus)`` per CLAUDE.md). Reads from the prefetch
    # populated by ``ExtractService.get_visible_extracts`` to avoid
    # the per-extract SQL N+1; the in-Python permission loop is still
    # ``O(n_docs)`` per row — acceptable while extracts stay small.
    # ``_prefetched_objects_cache`` is a Django private API; the
    # ``count()``/``all()`` fallback keeps the resolver correct if the
    # prefetch is missing.
    from opencontractserver.types.enums import PermissionTypes

    # Scoped admin access (2026-05): superusers are computed like a normal
    # user — they count only the documents in this extract they can READ,
    # via the same per-doc filter below (no blanket all-documents branch).
    cache = getattr(root, "_prefetched_objects_cache", {})
    documents = cache["documents"] if "documents" in cache else root.documents.all()
    return sum(
        1
        for doc in documents
        if BaseService.user_has(
            doc, info.context.user, PermissionTypes.READ, request=info.context
        )
    )


def _resolve_ExtractType_datacell_count(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:194

    Port of ExtractType.resolve_datacell_count
    """
    # N+1 warning: issues a COUNT(*) in addition to the main list query
    # per ExtractType instance. Safe for the single-extract embed query;
    # add a DataLoader before exposing this field on list queries.
    return _get_datacell_qs(root, info.context.user).count()


def _resolve_ExtractType_iteration_axis(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:240

    Port of ExtractType.resolve_iteration_axis
    """
    parent = root.parent_extract
    if parent is None:
        return None
    # Compare cheap signals first. Sets compared by PK to avoid hitting
    # the DB more than necessary; if iteration has fewer/more docs we
    # treat that as DOCUMENT_VERSIONS too.
    if root.fieldset_id != parent.fieldset_id:
        return "FIELDSET"
    own_doc_ids = set(root.documents.values_list("id", flat=True))
    parent_doc_ids = set(parent.documents.values_list("id", flat=True))
    if own_doc_ids != parent_doc_ids:
        return "DOCUMENT_VERSIONS"
    if (root.model_config or {}) != (parent.model_config or {}):
        return "MODEL"
    return None


def _resolve_ExtractType_full_iteration_list(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:234

    Port of ExtractType.resolve_full_iteration_list
    """
    # Permission filter is handled by ExtractService for the
    # individual iteration view; here we return all direct children
    # (FK is set, parent is visible by definition).
    return root.iterations.all().order_by("created", "id")


@strawberry.type(name="ExtractType")
class ExtractType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="corpus")
    def corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "corpus_id", "CorpusType")

    @strawberry.field(name="documents")
    def documents(
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
        resolved = getattr(self, "documents", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentType",
        )

    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))

    fieldset: FieldsetType = strawberry.field(name="fieldset", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    started: datetime.datetime | None = strawberry.field(name="started", default=None)
    finished: datetime.datetime | None = strawberry.field(name="finished", default=None)

    @strawberry.field(name="error")
    def error(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "error", None))

    corpus_action: None | (
        Annotated[CorpusActionType, strawberry.lazy("config.graphql.agent_types")]
    ) = strawberry.field(name="corpusAction", default=None)
    parent_extract: ExtractType | None = strawberry.field(
        name="parentExtract",
        description="Extract this iteration was forked from. Null for the root of an iteration series.",
        default=None,
    )
    model_config: GenericScalar | None = strawberry.field(
        name="modelConfig",
        description="Captured model/run configuration for this iteration.",
        default=None,
    )

    @strawberry.field(name="rows")
    def rows(
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
        DocumentAnalysisRowTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
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
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentAnalysisRowType",
        )

    @strawberry.field(
        name="executionRecords",
        description="Extract created (for fieldset actions only)",
    )
    def execution_records(
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
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.CorpusesCorpusActionExecutionStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        action_type: Annotated[
            enums.CorpusesCorpusActionExecutionActionTypeChoices | None,
            strawberry.argument(name="actionType"),
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionExecutionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionExecutionTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus__id": corpus__id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "action_type": action_type,
                "trigger": trigger,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "execution_records", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionExecutionType",
            filterset_class=filterset_factory(
                CorpusActionExecution,
                fields={
                    "id": ["exact"],
                    "corpus__id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "action_type": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus__id": "corpus__id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "action_type": "action_type",
                "trigger": "trigger",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(
        name="createdRelationships",
        description="If set, this relationship is private to the extract that created it",
    )
    def created_relationships(
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
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
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
        resolved = getattr(self, "created_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(
        name="createdAnnotations",
        description="If set, this annotation is private to the extract that created it",
    )
    def created_annotations(
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
        resolved = getattr(self, "created_annotations", None)
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
        name="iterations",
        description="Extract this iteration was forked from. Null for the root of an iteration series.",
    )
    def iterations(
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
    ) -> ExtractTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "iterations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ExtractType",
        )

    @strawberry.field(name="extractedDatacells")
    def extracted_datacells(
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
    ) -> DatacellTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "extracted_datacells", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(name="fullDatacellList")
    def full_datacell_list(
        self,
        info: strawberry.Info,
        limit: Annotated[
            int | None,
            strawberry.argument(
                name="limit",
                description="Maximum number of datacells to return. Clamped to the server maximum of 500 even when omitted; callers that need all cells must paginate using `offset`.",
            ),
        ] = strawberry.UNSET,
        offset: Annotated[
            int | None,
            strawberry.argument(
                name="offset",
                description="Number of datacells to skip before applying `limit`. Use together with `limit` for client-driven pagination.",
            ),
        ] = strawberry.UNSET,
    ) -> list[DatacellType | None] | None:
        kwargs = strip_unset({"limit": limit, "offset": offset})
        return _resolve_ExtractType_full_datacell_list(self, info, **kwargs)

    @strawberry.field(name="fullDocumentList")
    def full_document_list(
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
        return _resolve_ExtractType_full_document_list(self, info, **kwargs)

    @strawberry.field(
        name="documentCount",
        description="Number of documents associated with this extract. Use instead of `fullDocumentList { id }` when only the count is needed — the full-list resolver runs a per-row permission check that turns into an N+1 on list pages.",
    )
    def document_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_ExtractType_document_count(self, info, **kwargs)

    @strawberry.field(
        name="datacellCount",
        description="Total number of datacells in this extract visible to the current user, ignoring any `limit`/`offset` applied to `fullDatacellList`. Use together with `fullDatacellList(limit: ...)` to display 'showing N of M' indicators when the payload is bounded.",
    )
    def datacell_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_ExtractType_datacell_count(self, info, **kwargs)

    @strawberry.field(
        name="iterationAxis",
        description="Best-effort axis label inferred from the iteration relationship: 'MODEL' if model_config differs from parent, 'FIELDSET' if fieldset differs, 'DOCUMENT_VERSIONS' if doc set differs, else null. Useful for badging the Iterations tab.",
    )
    def iteration_axis(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_ExtractType_iteration_axis(self, info, **kwargs)

    @strawberry.field(
        name="fullIterationList",
        description="Direct iterations forked from this extract (one level deep). Walk recursively for the full subtree.",
    )
    def full_iteration_list(
        self, info: strawberry.Info
    ) -> list[ExtractType | None] | None:
        kwargs = strip_unset({})
        return _resolve_ExtractType_full_iteration_list(self, info, **kwargs)


def _get_node_ExtractType(info, pk):
    """PORT: config.graphql.extract_types.ExtractType.get_node

    Port of ExtractType.get_node — override the default node resolution to
    apply permission checks.
    """
    from opencontractserver.extracts.services import ExtractService

    has_perm, extract = ExtractService.check_extract_permission(
        info.context.user, int(pk), context=info.context
    )
    return extract if has_perm else None


register_type("ExtractType", ExtractType, model=Extract, get_node=_get_node_ExtractType)


ExtractTypeConnection = make_connection_types(
    ExtractType, type_name="ExtractTypeConnection", countable=True, pdf_page_aware=False
)


def _resolve_FieldsetType_in_use(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:51

    Returns True if the fieldset is used in any extract that has started.
    """
    return root.extracts.filter(started__isnull=False).exists()


def _resolve_FieldsetType_full_column_list(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:57

    Port of FieldsetType.resolve_full_column_list
    """
    return root.columns.all()


def _resolve_FieldsetType_column_count(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:60

    Port of FieldsetType.resolve_column_count
    """
    # Reads the ``fieldset__columns`` prefetch populated by
    # ``ExtractService`` to avoid N+1 COUNTs on the list view.
    # No per-column permission filter — columns inherit fieldset
    # visibility, matching ``resolve_full_column_list``.
    cache = getattr(root, "_prefetched_objects_cache", {})
    if "columns" in cache:
        return len(cache["columns"])
    return root.columns.count()


@strawberry.type(name="FieldsetType")
class FieldsetType(Node):
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

    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    @strawberry.field(
        name="corpus",
        description="If set, this fieldset defines the metadata schema for the corpus",
    )
    def corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "corpus_id", "CorpusType")

    @strawberry.field(name="corpusactionSet")
    def corpusaction_set(
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
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        name: Annotated[
            str | None, strawberry.argument(name="name")
        ] = strawberry.UNSET,
        name__icontains: Annotated[
            str | None, strawberry.argument(name="name_Icontains")
        ] = strawberry.UNSET,
        name__istartswith: Annotated[
            str | None, strawberry.argument(name="name_Istartswith")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        fieldset__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="fieldset_Id")
        ] = strawberry.UNSET,
        analyzer__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analyzer_Id")
        ] = strawberry.UNSET,
        agent_config__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="agentConfig_Id")
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
        source_template__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="sourceTemplate_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "name": name,
                "name__icontains": name__icontains,
                "name__istartswith": name__istartswith,
                "corpus__id": corpus__id,
                "fieldset__id": fieldset__id,
                "analyzer__id": analyzer__id,
                "agent_config__id": agent_config__id,
                "trigger": trigger,
                "creator__id": creator__id,
                "source_template__id": source_template__id,
            }
        )
        resolved = getattr(self, "corpusaction_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionType",
            filterset_class=filterset_factory(
                CorpusAction,
                fields={
                    "id": ["exact"],
                    "name": ["exact", "icontains", "istartswith"],
                    "corpus__id": ["exact"],
                    "fieldset__id": ["exact"],
                    "analyzer__id": ["exact"],
                    "agent_config__id": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                    "source_template__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "name": "name",
                "name__icontains": "name__icontains",
                "name__istartswith": "name__istartswith",
                "corpus__id": "corpus__id",
                "fieldset__id": "fieldset__id",
                "analyzer__id": "analyzer__id",
                "agent_config__id": "agent_config__id",
                "trigger": "trigger",
                "creator__id": "creator__id",
                "source_template__id": "source_template__id",
            },
        )

    @strawberry.field(name="columns")
    def columns(
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
    ) -> ColumnTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "columns", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ColumnType",
        )

    @strawberry.field(name="extracts")
    def extracts(
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
    ) -> ExtractTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "extracts", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ExtractType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(
        name="inUse",
        description="True if the fieldset is used in any extract that has started.",
    )
    def in_use(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_FieldsetType_in_use(self, info, **kwargs)

    @strawberry.field(name="fullColumnList")
    def full_column_list(self, info: strawberry.Info) -> list[ColumnType | None] | None:
        kwargs = strip_unset({})
        return _resolve_FieldsetType_full_column_list(self, info, **kwargs)

    @strawberry.field(
        name="columnCount",
        description="Number of columns in this fieldset. Use instead of `fullColumnList { id }` when only the count is needed — list-view queries pay for full Column rows otherwise.",
    )
    def column_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_FieldsetType_column_count(self, info, **kwargs)


def _get_node_FieldsetType(info, pk):
    """Permission-aware node resolution for the singular ``fieldset(id:)``
    field (IDOR guard). Returns None when absent OR not visible, matching the
    graphene ``BaseService.get_or_none`` resolver; without it
    ``get_node_from_global_id`` would fall back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        Fieldset, pk, info.context.user, request=info.context
    )


register_type(
    "FieldsetType", FieldsetType, model=Fieldset, get_node=_get_node_FieldsetType
)


FieldsetTypeConnection = make_connection_types(
    FieldsetType,
    type_name="FieldsetTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(name="ColumnType")
class ColumnType(Node):
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

    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))

    fieldset: FieldsetType = strawberry.field(name="fieldset", default=None)

    @strawberry.field(name="query")
    def query(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "query", None))

    @strawberry.field(name="matchText")
    def match_text(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "match_text", None))

    @strawberry.field(name="mustContainText")
    def must_contain_text(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "must_contain_text", None))

    @strawberry.field(name="outputType")
    def output_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "output_type", None))

    @strawberry.field(name="limitToLabel")
    def limit_to_label(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "limit_to_label", None))

    @strawberry.field(name="instructions")
    def instructions(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "instructions", None))

    extract_is_list: bool = strawberry.field(name="extractIsList", default=None)

    @strawberry.field(name="taskName")
    def task_name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "task_name", None))

    @strawberry.field(
        name="dataType", description="Structured data type for manual entry fields"
    )
    def data_type(
        self, info: strawberry.Info
    ) -> enums.ExtractsColumnDataTypeChoices | None:
        return coerce_enum(
            enums.ExtractsColumnDataTypeChoices, getattr(self, "data_type", None)
        )

    validation_config: GenericScalar | None = strawberry.field(
        name="validationConfig", default=None
    )
    is_manual_entry: bool = strawberry.field(
        name="isManualEntry",
        description="True for manual metadata, False for extraction",
        default=None,
    )
    default_value: GenericScalar | None = strawberry.field(
        name="defaultValue", default=None
    )

    @strawberry.field(
        name="helpText", description="Help text to display for manual entry fields"
    )
    def help_text(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "help_text", None))

    display_order: int = strawberry.field(
        name="displayOrder",
        description="Order in which to display manual entry fields",
        default=None,
    )

    @strawberry.field(name="extractedDatacells")
    def extracted_datacells(
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
    ) -> DatacellTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "extracted_datacells", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_node_ColumnType(info, pk):
    """Permission-aware node resolution for the singular ``column(id:)`` field
    (IDOR guard). Returns None when absent OR not visible, matching the graphene
    ``BaseService.get_or_none`` resolver; without it ``get_node_from_global_id``
    would fall back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(Column, pk, info.context.user, request=info.context)


register_type("ColumnType", ColumnType, model=Column, get_node=_get_node_ColumnType)


ColumnTypeConnection = make_connection_types(
    ColumnType, type_name="ColumnTypeConnection", countable=True, pdf_page_aware=False
)


def _resolve_DatacellType_full_source_list(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:76

    Port of DatacellType.resolve_full_source_list
    """
    return root.sources.all()


@strawberry.type(name="DatacellType")
class DatacellType(Node):
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
    extract: ExtractType | None = strawberry.field(name="extract", default=None)
    column: ColumnType = strawberry.field(name="column", default=None)
    document: Annotated[
        DocumentType, strawberry.lazy("config.graphql.document_types")
    ] = strawberry.field(name="document", default=None)

    @strawberry.field(name="sources")
    def sources(
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
        resolved = getattr(self, "sources", None)
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

    data: GenericScalar | None = strawberry.field(name="data", default=None)

    @strawberry.field(name="dataDefinition")
    def data_definition(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "data_definition", None))

    started: datetime.datetime | None = strawberry.field(name="started", default=None)
    completed: datetime.datetime | None = strawberry.field(
        name="completed", default=None
    )
    failed: datetime.datetime | None = strawberry.field(name="failed", default=None)

    @strawberry.field(name="stacktrace")
    def stacktrace(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "stacktrace", None))

    approved_by: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="approvedBy", default=None)
    rejected_by: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="rejectedBy", default=None)
    corrected_data: GenericScalar | None = strawberry.field(
        name="correctedData", default=None
    )

    @strawberry.field(
        name="llmCallLog",
        description="Captured LLM message history for debugging extraction issues",
    )
    def llm_call_log(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "llm_call_log", None))

    @strawberry.field(name="rows")
    def rows(
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
        DocumentAnalysisRowTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
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
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentAnalysisRowType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(name="fullSourceList")
    def full_source_list(
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
        return _resolve_DatacellType_full_source_list(self, info, **kwargs)


def _get_node_DatacellType(info, pk):
    """Permission-aware node resolution for the singular ``datacell(id:)`` field
    (IDOR guard). The graphene resolver used ``BaseService.get_or_none(Datacell,
    ...)``; returns None when absent OR not visible so extraction results no
    longer leak across corpora/documents the caller cannot access. Without this
    hook, ``get_node_from_global_id`` falls back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        Datacell, pk, info.context.user, request=info.context
    )


register_type(
    "DatacellType", DatacellType, model=Datacell, get_node=_get_node_DatacellType
)


DatacellTypeConnection = make_connection_types(
    DatacellType,
    type_name="DatacellTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_AnalysisType_full_annotation_list(root, info, document_id=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_types.py:305

    Port of AnalysisType.resolve_full_annotation_list
    """
    from opencontractserver.analyzer.services import AnalysisService

    if document_id is not None:
        document_pk = int(from_global_id(document_id)[1])
    else:
        document_pk = None

    return AnalysisService.get_analysis_annotations(
        root, info.context.user, document_id=document_pk
    )


@strawberry.type(name="AnalysisType")
class AnalysisType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    analyzer: AnalyzerType = strawberry.field(name="analyzer", default=None)

    @strawberry.field(name="callbackTokenHash")
    def callback_token_hash(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "callback_token_hash", None))

    @strawberry.field(name="receivedCallbackFile")
    def received_callback_file(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "received_callback_file", None))

    @strawberry.field(name="analyzedCorpus")
    def analyzed_corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "analyzed_corpus_id", "CorpusType")

    corpus_action: None | (
        Annotated[CorpusActionType, strawberry.lazy("config.graphql.agent_types")]
    ) = strawberry.field(name="corpusAction", default=None)

    @strawberry.field(name="importLog")
    def import_log(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "import_log", None))

    @strawberry.field(name="analyzedDocuments")
    def analyzed_documents(
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
        resolved = getattr(self, "analyzed_documents", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentType",
        )

    @strawberry.field(name="errorMessage")
    def error_message(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "error_message", None))

    @strawberry.field(name="errorTraceback")
    def error_traceback(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "error_traceback", None))

    @strawberry.field(name="resultMessage")
    def result_message(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "result_message", None))

    analysis_started: datetime.datetime | None = strawberry.field(
        name="analysisStarted", default=None
    )
    analysis_completed: datetime.datetime | None = strawberry.field(
        name="analysisCompleted", default=None
    )

    @strawberry.field(name="status")
    def status(self, info: strawberry.Info) -> enums.AnalyzerAnalysisStatusChoices:
        return coerce_enum(
            enums.AnalyzerAnalysisStatusChoices, getattr(self, "status", None)
        )

    @strawberry.field(name="rows")
    def rows(
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
        DocumentAnalysisRowTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
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
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentAnalysisRowType",
        )

    @strawberry.field(
        name="executionRecords",
        description="Analysis created (for analyzer actions only)",
    )
    def execution_records(
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
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.CorpusesCorpusActionExecutionStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        action_type: Annotated[
            enums.CorpusesCorpusActionExecutionActionTypeChoices | None,
            strawberry.argument(name="actionType"),
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionExecutionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionExecutionTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus__id": corpus__id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "action_type": action_type,
                "trigger": trigger,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "execution_records", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionExecutionType",
            filterset_class=filterset_factory(
                CorpusActionExecution,
                fields={
                    "id": ["exact"],
                    "corpus__id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "action_type": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus__id": "corpus__id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "action_type": "action_type",
                "trigger": "trigger",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(name="relationships")
    def relationships(
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
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
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
        resolved = getattr(self, "relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(
        name="createdRelationships",
        description="If set, this relationship is private to the analysis that created it",
    )
    def created_relationships(
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
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
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
        resolved = getattr(self, "created_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="annotations")
    def annotations(
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
        resolved = getattr(self, "annotations", None)
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
        name="createdAnnotations",
        description="If set, this annotation is private to the analysis that created it",
    )
    def created_annotations(
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
        resolved = getattr(self, "created_annotations", None)
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

    @strawberry.field(name="createdReferences")
    def created_references(
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
        CorpusReferenceTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
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
        resolved = getattr(self, "created_references", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusReferenceType",
        )

    @strawberry.field(
        name="notifications", description="Related analysis job, if applicable."
    )
    def notifications(
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
        is_read: Annotated[
            bool | None, strawberry.argument(name="isRead")
        ] = strawberry.UNSET,
        notification_type: Annotated[
            enums.NotificationsNotificationNotificationTypeChoices | None,
            strawberry.argument(name="notificationType"),
        ] = strawberry.UNSET,
        created_at__lte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Lte")
        ] = strawberry.UNSET,
        created_at__gte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Gte")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NotificationTypeConnection, strawberry.lazy("config.graphql.social_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "is_read": is_read,
                "notification_type": notification_type,
                "created_at__lte": created_at__lte,
                "created_at__gte": created_at__gte,
            }
        )
        resolved = getattr(self, "notifications", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NotificationType",
            filterset_class=filterset_factory(
                Notification,
                fields={
                    "is_read": ["exact"],
                    "notification_type": ["exact"],
                    "created_at": ["lte", "gte"],
                },
            ),
            filter_args={
                "is_read": "is_read",
                "notification_type": "notification_type",
                "created_at__lte": "created_at__lte",
                "created_at__gte": "created_at__gte",
            },
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(name="fullAnnotationList")
    def full_annotation_list(
        self,
        info: strawberry.Info,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
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
        kwargs = strip_unset({"document_id": document_id})
        return _resolve_AnalysisType_full_annotation_list(self, info, **kwargs)


def _get_node_AnalysisType(info, pk):
    """PORT: config.graphql.extract_types.AnalysisType.get_node

    Port of AnalysisType.get_node — override the default node resolution to
    apply permission checks.
    """
    from opencontractserver.analyzer.services import AnalysisService

    has_perm, analysis = AnalysisService.check_analysis_permission(
        info.context.user, int(pk), context=info.context
    )
    return analysis if has_perm else None


register_type(
    "AnalysisType", AnalysisType, model=Analysis, get_node=_get_node_AnalysisType
)


AnalysisTypeConnection = make_connection_types(
    AnalysisType,
    type_name="AnalysisTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(name="GremlinEngineType_READ")
class GremlinEngineType_READ(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="url")
    def url(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "url", None))

    last_synced: datetime.datetime | None = strawberry.field(
        name="lastSynced", default=None
    )
    install_started: datetime.datetime | None = strawberry.field(
        name="installStarted", default=None
    )
    install_completed: datetime.datetime | None = strawberry.field(
        name="installCompleted", default=None
    )
    is_public: bool = strawberry.field(name="isPublic", default=None)

    @strawberry.field(name="analyzerSet")
    def analyzer_set(
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
    ) -> AnalyzerTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "analyzer_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalyzerType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_node_GremlinEngineType_READ(info, pk):
    """Permission-aware node resolution for the singular ``gremlinEngine(id:)``
    field (IDOR guard). Mirrors the graphene ``BaseService.get_or_none(
    GremlinEngine, ...)`` resolver; without it ``get_node_from_global_id`` would
    fall back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        GremlinEngine, pk, info.context.user, request=info.context
    )


register_type(
    "GremlinEngineType_READ",
    GremlinEngineType_READ,
    model=GremlinEngine,
    get_node=_get_node_GremlinEngineType_READ,
)


GremlinEngineType_READConnection = make_connection_types(
    GremlinEngineType_READ,
    type_name="GremlinEngineType_READConnection",
    countable=True,
    pdf_page_aware=False,
)
