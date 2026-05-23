"""GraphQL type definitions for extract and analysis types."""

from typing import Any

import graphene
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType
from graphql_relay import from_global_id

from config.graphql.annotation_types import AnnotationLabelType, AnnotationType
from config.graphql.base import CountableConnection
from config.graphql.document_types import DocumentType
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.constants.extracts import MAX_FULL_DATACELL_LIST_LIMIT
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset


class ColumnType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    validation_config = GenericScalar()
    default_value = GenericScalar()

    class Meta:
        model = Column
        interfaces = [relay.Node]
        connection_class = CountableConnection


class FieldsetType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    in_use = graphene.Boolean(
        description="True if the fieldset is used in any extract that has started."
    )
    full_column_list = graphene.List(ColumnType)
    column_count = graphene.Int(
        description=(
            "Number of columns in this fieldset. Use instead of "
            "`fullColumnList { id }` when only the count is needed — list-view "
            "queries pay for full Column rows otherwise."
        )
    )

    class Meta:
        model = Fieldset
        interfaces = [relay.Node]
        connection_class = CountableConnection

    def resolve_in_use(self, info) -> bool:
        """
        Returns True if the fieldset is used in any extract that has started.
        """
        return self.extracts.filter(started__isnull=False).exists()

    def resolve_full_column_list(self, info) -> Any:
        return self.columns.all()

    def resolve_column_count(self, info) -> int:
        # Reads the ``fieldset__columns`` prefetch populated by
        # ``ExtractQueryOptimizer`` to avoid N+1 COUNTs on the list view.
        # No per-column permission filter — columns inherit fieldset
        # visibility, matching ``resolve_full_column_list``.
        cache = getattr(self, "_prefetched_objects_cache", {})
        if "columns" in cache:
            return len(cache["columns"])
        return self.columns.count()


class DatacellType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    data = GenericScalar()
    corrected_data = GenericScalar()
    full_source_list = graphene.List(AnnotationType)

    def resolve_full_source_list(self, info) -> Any:
        return self.sources.all()

    class Meta:
        model = Datacell
        interfaces = [relay.Node]
        connection_class = CountableConnection


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
    # Inline import to avoid circular dependency with the annotations module.
    # TODO: Move ExtractQueryOptimizer to a standalone module so this becomes
    # a top-level import (tracked as part of issue #1256 follow-ups).
    from opencontractserver.annotations.query_optimizer import (
        ExtractQueryOptimizer,
    )

    return ExtractQueryOptimizer.get_extract_datacells(
        extract, user, document_id=None
    ).order_by("document_id", "column_id", "id")


class ExtractType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    full_datacell_list = graphene.List(
        DatacellType,
        limit=graphene.Int(
            description=(
                "Maximum number of datacells to return. Clamped to the server "
                f"maximum of {MAX_FULL_DATACELL_LIST_LIMIT} even when omitted; "
                "callers that need all cells must paginate using `offset`."
            )
        ),
        offset=graphene.Int(
            description=(
                "Number of datacells to skip before applying `limit`. Use together "
                "with `limit` for client-driven pagination."
            )
        ),
    )
    full_document_list = graphene.List(DocumentType)
    document_count = graphene.Int(
        description=(
            "Number of documents associated with this extract. Use instead of "
            "`fullDocumentList { id }` when only the count is needed — the "
            "full-list resolver runs a per-row permission check that turns "
            "into an N+1 on list pages."
        )
    )
    datacell_count = graphene.Int(
        description=(
            "Total number of datacells in this extract visible to the current "
            "user, ignoring any `limit`/`offset` applied to `fullDatacellList`. "
            "Use together with `fullDatacellList(limit: ...)` to display "
            "'showing N of M' indicators when the payload is bounded."
        )
    )
    # ``model_config`` is a JSONField on the model — expose it as GenericScalar
    # so the camelCased ``modelConfig`` field returns the captured run config.
    model_config = GenericScalar(
        description="Captured model/run configuration for this iteration."
    )
    iteration_axis = graphene.String(
        description=(
            "Best-effort axis label inferred from the iteration relationship: "
            "'MODEL' if model_config differs from parent, 'FIELDSET' if fieldset "
            "differs, 'DOCUMENT_VERSIONS' if doc set differs, else null. Useful "
            "for badging the Iterations tab."
        )
    )
    full_iteration_list = graphene.List(
        lambda: ExtractType,
        description=(
            "Direct iterations forked from this extract (one level deep). "
            "Walk recursively for the full subtree."
        ),
    )

    @classmethod
    def get_node(cls, info, id) -> Any:
        """
        Override the default node resolution to apply permission checks.
        """
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        has_perm, extract = ExtractQueryOptimizer.check_extract_permission(
            info.context.user, int(id), context=info.context
        )
        return extract if has_perm else None

    class Meta:
        model = Extract
        interfaces = [relay.Node]
        connection_class = CountableConnection

    def resolve_full_datacell_list(self, info, limit=None, offset=None) -> Any:
        qs = _get_datacell_qs(self, info.context.user)

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

    def resolve_datacell_count(self, info) -> int:
        # N+1 warning: issues a COUNT(*) in addition to the main list query
        # per ExtractType instance. Safe for the single-extract embed query;
        # add a DataLoader before exposing this field on list queries.
        return _get_datacell_qs(self, info.context.user).count()

    def resolve_document_count(self, info) -> int:
        # Mirrors the per-document permission filter applied by
        # ``resolve_full_document_list`` so the count never exceeds the list
        # length the same viewer would observe (effective permission is
        # ``MIN(document, corpus)`` per CLAUDE.md). Reads from the prefetch
        # populated by ``ExtractQueryOptimizer.get_visible_extracts`` to avoid
        # the per-extract SQL N+1; the in-Python permission loop is still
        # ``O(n_docs)`` per row — acceptable while extracts stay small.
        # ``_prefetched_objects_cache`` is a Django private API; the
        # ``count()``/``all()`` fallback keeps the resolver correct if the
        # prefetch is missing.
        from opencontractserver.types.enums import PermissionTypes

        if info.context.user.is_superuser:
            cache = getattr(self, "_prefetched_objects_cache", {})
            if "documents" in cache:
                return len(cache["documents"])
            return self.documents.count()

        cache = getattr(self, "_prefetched_objects_cache", {})
        documents = cache["documents"] if "documents" in cache else self.documents.all()
        return sum(
            1
            for doc in documents
            if doc.user_can(
                info.context.user, PermissionTypes.READ, request=info.context
            )
        )

    def resolve_full_document_list(self, info) -> Any:
        from opencontractserver.types.enums import PermissionTypes

        # Filter to only documents user can read
        if info.context.user.is_superuser:
            return self.documents.all()

        readable_docs = []
        for doc in self.documents.all():
            if doc.user_can(
                info.context.user, PermissionTypes.READ, request=info.context
            ):
                readable_docs.append(doc)
        return readable_docs

    def resolve_full_iteration_list(self, info) -> Any:
        # Permission filter is handled by ExtractQueryOptimizer for the
        # individual iteration view; here we return all direct children
        # (FK is set, parent is visible by definition).
        return self.iterations.all().order_by("created", "id")

    def resolve_iteration_axis(self, info) -> Any:
        parent = self.parent_extract
        if parent is None:
            return None
        # Compare cheap signals first. Sets compared by PK to avoid hitting
        # the DB more than necessary; if iteration has fewer/more docs we
        # treat that as DOCUMENT_VERSIONS too.
        if self.fieldset_id != parent.fieldset_id:
            return "FIELDSET"
        own_doc_ids = set(self.documents.values_list("id", flat=True))
        parent_doc_ids = set(parent.documents.values_list("id", flat=True))
        if own_doc_ids != parent_doc_ids:
            return "DOCUMENT_VERSIONS"
        if (self.model_config or {}) != (parent.model_config or {}):
            return "MODEL"
        return None


class AnalyzerType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    analyzer_id = graphene.String()

    def resolve_analyzer_id(self, info) -> Any:
        return self.id.__str__()

    input_schema = GenericScalar(
        description="JSONSchema describing the analyzer's expected input if provided."
    )

    manifest = GenericScalar()

    full_label_list = graphene.List(AnnotationLabelType)

    def resolve_full_label_list(self, info) -> Any:
        return self.annotation_labels.all()

    def resolve_icon(self, info) -> Any:
        return "" if not self.icon else info.context.build_absolute_uri(self.icon.url)

    class Meta:
        model = Analyzer
        interfaces = [relay.Node]
        connection_class = CountableConnection


class GremlinEngineType_READ(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = GremlinEngine
        exclude = ("api_key",)
        interfaces = [relay.Node]
        connection_class = CountableConnection


class GremlinEngineType_WRITE(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = GremlinEngine
        interfaces = [relay.Node]
        connection_class = CountableConnection


class AnalysisType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    full_annotation_list = graphene.List(
        AnnotationType,
        document_id=graphene.ID(),
    )

    def resolve_full_annotation_list(self, info, document_id=None) -> Any:
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
        )

        if document_id is not None:
            document_pk = int(from_global_id(document_id)[1])
        else:
            document_pk = None

        return AnalysisQueryOptimizer.get_analysis_annotations(
            self, info.context.user, document_id=document_pk
        )

    @classmethod
    def get_node(cls, info, id) -> Any:
        """
        Override the default node resolution to apply permission checks.
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
        )

        has_perm, analysis = AnalysisQueryOptimizer.check_analysis_permission(
            info.context.user, int(id), context=info.context
        )
        return analysis if has_perm else None

    class Meta:
        model = Analysis
        interfaces = [relay.Node]
        connection_class = CountableConnection
