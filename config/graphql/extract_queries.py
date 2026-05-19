"""
GraphQL query mixin for extract, fieldset, column, and datacell queries.

Also contains helper types MetadataCompletionStatusType and DocumentMetadataResultType
which are used by extract/metadata queries.
"""

import inspect
import logging
from typing import Any

import graphene
from django.conf import settings
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django.filter import DjangoFilterConnectionField
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.document_types import DocumentType
from config.graphql.filters import (
    AnalysisFilter,
    AnalyzerFilter,
    ColumnFilter,
    DatacellFilter,
    ExtractFilter,
    FieldsetFilter,
    GremlinEngineFilter,
)
from config.graphql.graphene_types import (
    AnalysisType,
    AnalyzerType,
    ColumnType,
    DatacellType,
    ExtractType,
    FieldsetType,
    GremlinEngineType_READ,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.analyzer.models import Analyzer, GremlinEngine
from opencontractserver.constants.extracts import EXTRACT_LIST_MAX_PAGE_SIZE
from opencontractserver.extracts.models import Column, Datacell, Fieldset

logger = logging.getLogger(__name__)


class MetadataCompletionStatusType(graphene.ObjectType):
    """Type for metadata completion status information."""

    total_fields = graphene.Int()
    filled_fields = graphene.Int()
    missing_fields = graphene.Int()
    percentage = graphene.Float()
    missing_required = graphene.List(graphene.String)


# ---------------------------------------------------------------------------
# Extract iteration diff types
# ---------------------------------------------------------------------------


class ExtractDiffStatus(graphene.Enum):
    """Cell-level diff result between two iterations of the same extract."""

    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    ONLY_IN_A = "ONLY_IN_A"
    ONLY_IN_B = "ONLY_IN_B"


class ExtractCellDiffType(graphene.ObjectType):
    """One row of the compare grid: same (column, document) on both sides.

    ``rowKey`` is a stable identifier for the document row across iterations
    (the document's ``version_tree_id`` when available, else its PK). Using
    the version-tree key lets the UI render a single row even when the two
    iterations point at different content versions of the same logical doc.
    ``columnKey`` is the column name, which is stable when fieldsets are
    cloned because the clone preserves the name.
    """

    row_key = graphene.String(required=True)
    column_key = graphene.String(required=True)
    document = graphene.Field(
        DocumentType,
        description="Representative Document (B side preferred). For "
        "DOCUMENT_VERSIONS-axis diffs use documentA / documentB to see "
        "the actual version on each side.",
    )
    document_a = graphene.Field(DocumentType)
    document_b = graphene.Field(DocumentType)
    cell_a = graphene.Field(DatacellType)
    cell_b = graphene.Field(DatacellType)
    status = graphene.Field(ExtractDiffStatus, required=True)
    column_config_changed = graphene.Boolean(
        description="True when the column on B has a different prompt / "
        "instructions / output_type from the column on A (FIELDSET axis)."
    )


class ExtractDiffSummaryType(graphene.ObjectType):
    """Aggregate counts for the diff — used for the heatmap legend."""

    unchanged = graphene.Int(required=True)
    changed = graphene.Int(required=True)
    only_in_a = graphene.Int(required=True)
    only_in_b = graphene.Int(required=True)
    total = graphene.Int(required=True)


class ExtractDiffType(graphene.ObjectType):
    extract_a = graphene.Field(ExtractType)
    extract_b = graphene.Field(ExtractType)
    cells = graphene.List(ExtractCellDiffType, required=True)
    summary = graphene.Field(ExtractDiffSummaryType, required=True)


class DocumentMetadataResultType(graphene.ObjectType):
    """Type for batch metadata query results - groups datacells by document."""

    document_id = graphene.ID(description="The document's global ID")
    datacells = graphene.List(
        DatacellType, description="Metadata datacells for this document"
    )


class ExtractQueryMixin:
    """Query fields and resolvers for extract, fieldset, column, datacell, and analyzer queries."""

    fieldset = relay.Node.Field(FieldsetType)

    def resolve_fieldset(self, info, **kwargs) -> Any:
        django_pk = int(from_global_id(kwargs["id"])[1])
        return Fieldset.objects.visible_to_user(info.context.user).get(id=django_pk)

    fieldsets = DjangoFilterConnectionField(
        FieldsetType, filterset_class=FieldsetFilter
    )

    def resolve_fieldsets(self, info, **kwargs) -> Any:
        return Fieldset.objects.visible_to_user(info.context.user)

    column = relay.Node.Field(ColumnType)

    def resolve_column(self, info, **kwargs) -> Any:
        django_pk = int(from_global_id(kwargs["id"])[1])
        return Column.objects.visible_to_user(info.context.user).get(id=django_pk)

    columns = DjangoFilterConnectionField(ColumnType, filterset_class=ColumnFilter)

    def resolve_columns(self, info, **kwargs) -> Any:
        return Column.objects.visible_to_user(info.context.user)

    extract = relay.Node.Field(ExtractType)

    def resolve_extract(self, info, **kwargs) -> Any:
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        django_pk = from_global_id(kwargs["id"])[1]
        has_perm, extract = ExtractQueryOptimizer.check_extract_permission(
            info.context.user, int(django_pk), context=info.context
        )
        return extract if has_perm else None

    # ``max_limit`` must match (or exceed) the frontend ``EXTRACT_PAGINATION``
    # page size — Graphene silently clamps to this value and otherwise pages
    # never advance past the cap (the bug fixed in PR #1602).
    extracts = DjangoFilterConnectionField(
        ExtractType,
        filterset_class=ExtractFilter,
        max_limit=EXTRACT_LIST_MAX_PAGE_SIZE,
    )

    def resolve_extracts(self, info, **kwargs) -> Any:
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            corpus_django_pk = int(from_global_id(corpus_id)[1])
        else:
            corpus_django_pk = None

        return ExtractQueryOptimizer.get_visible_extracts(
            info.context.user, corpus_id=corpus_django_pk, context=info.context
        )

    compare_extracts = graphene.Field(
        ExtractDiffType,
        extract_a_id=graphene.ID(required=True),
        extract_b_id=graphene.ID(required=True),
        description="Cell-level diff between two iterations of the same extract series.",
    )

    @login_required
    def resolve_compare_extracts(self, info, extract_a_id, extract_b_id) -> Any:
        from opencontractserver.annotations.query_optimizer import (
            ExtractQueryOptimizer,
        )
        from opencontractserver.extracts.diff import diff_extracts, summarise

        user = info.context.user
        a_pk = int(from_global_id(extract_a_id)[1])
        b_pk = int(from_global_id(extract_b_id)[1])

        # Permission check leverages the same optimizer the extract node
        # resolver uses, so visibility rules stay consistent.
        a_ok, extract_a = ExtractQueryOptimizer.check_extract_permission(
            user, a_pk, context=info.context
        )
        b_ok, extract_b = ExtractQueryOptimizer.check_extract_permission(
            user, b_pk, context=info.context
        )
        if not (a_ok and b_ok and extract_a and extract_b):
            return None

        cells_a = ExtractQueryOptimizer.get_extract_datacells(
            extract_a, user, document_id=None
        )
        cells_b = ExtractQueryOptimizer.get_extract_datacells(
            extract_b, user, document_id=None
        )

        diffs = diff_extracts(extract_a, extract_b, cells_a=cells_a, cells_b=cells_b)
        return ExtractDiffType(
            extract_a=extract_a,
            extract_b=extract_b,
            cells=[
                ExtractCellDiffType(
                    row_key=d.row_key,
                    column_key=d.column_key,
                    document=d.document,
                    document_a=d.document_a,
                    document_b=d.document_b,
                    cell_a=d.cell_a,
                    cell_b=d.cell_b,
                    status=d.status,
                    column_config_changed=d.column_config_changed,
                )
                for d in diffs
            ],
            summary=ExtractDiffSummaryType(**summarise(diffs)),
        )

    datacell = relay.Node.Field(DatacellType)

    def resolve_datacell(self, info, **kwargs) -> Any:
        django_pk = int(from_global_id(kwargs["id"])[1])
        return Datacell.objects.visible_to_user(info.context.user).get(id=django_pk)

    datacells = DjangoFilterConnectionField(
        DatacellType, filterset_class=DatacellFilter
    )

    def resolve_datacells(self, info, **kwargs) -> Any:
        return Datacell.objects.visible_to_user(info.context.user)

    registered_extract_tasks = graphene.Field(GenericScalar)

    @login_required
    def resolve_registered_extract_tasks(self, info, **kwargs) -> Any:
        from config import celery_app

        tasks = {}

        # Try to get tasks from the app instance
        # Get tasks from the app instance
        try:
            for task_name, task in celery_app.tasks.items():
                if not task_name.startswith("celery."):
                    docstring = inspect.getdoc(task.run) or "No docstring available"
                    tasks[task_name] = docstring

        except AttributeError as e:
            logger.warning(f"Couldn't get tasks from app instance: {str(e)}")

        # Filter out Celery's internal tasks
        return {
            task: description
            for task, description in tasks.items()
            if task.startswith("opencontractserver.tasks.data_extract_tasks")
        }

    # METADATA QUERIES (Column/Datacell based) ################################
    document_metadata_datacells = graphene.List(
        DatacellType,
        document_id=graphene.ID(required=True),
        corpus_id=graphene.ID(required=True),
        description="Get metadata datacells for a document in a corpus",
    )

    metadata_completion_status_v2 = graphene.Field(
        MetadataCompletionStatusType,
        document_id=graphene.ID(required=True),
        corpus_id=graphene.ID(required=True),
        description="Get metadata completion status for a document using column/datacell system",
    )

    documents_metadata_datacells_batch = graphene.List(
        DocumentMetadataResultType,
        document_ids=graphene.List(graphene.ID, required=True),
        corpus_id=graphene.ID(required=True),
        description="Get metadata datacells for multiple documents in a single query (batch)",
    )

    def resolve_document_metadata_datacells(self, info, document_id, corpus_id) -> Any:
        """Get metadata datacells for a document using MetadataQueryOptimizer."""
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        user = info.context.user
        local_doc_id = int(from_global_id(document_id)[1])
        local_corpus_id = int(from_global_id(corpus_id)[1])

        return MetadataQueryOptimizer.get_document_metadata(
            user, local_doc_id, local_corpus_id, manual_only=True
        )

    def resolve_metadata_completion_status_v2(
        self, info, document_id, corpus_id
    ) -> Any:
        """Get metadata completion status using MetadataQueryOptimizer."""
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        user = info.context.user
        local_doc_id = int(from_global_id(document_id)[1])
        local_corpus_id = int(from_global_id(corpus_id)[1])

        return MetadataQueryOptimizer.get_metadata_completion_status(
            user, local_doc_id, local_corpus_id
        )

    def resolve_documents_metadata_datacells_batch(
        self, info, document_ids, corpus_id
    ) -> Any:
        """
        Get metadata datacells for multiple documents using MetadataQueryOptimizer.

        This batch query solves the N+1 problem when loading metadata for a grid view.
        Uses the centralized MetadataQueryOptimizer which applies proper permission
        filtering: Effective Permission = MIN(document_permission, corpus_permission)
        """
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        user = info.context.user
        local_corpus_id = int(from_global_id(corpus_id)[1])

        # Convert global IDs to local IDs (single pass)
        local_doc_ids: list[int] = []
        local_id_by_global: dict[str, int] = {}  # global_id -> local_id
        for global_id in document_ids:
            local_id_int = int(from_global_id(global_id)[1])
            local_doc_ids.append(local_id_int)
            local_id_by_global[global_id] = local_id_int

        # Use optimizer to get batch metadata with proper permissions
        datacells_by_doc = MetadataQueryOptimizer.get_documents_metadata_batch(
            user,
            local_doc_ids,
            local_corpus_id,
            manual_only=True,
            context=info.context,
        )

        # Build response - maintain order of requested document_ids
        # The optimizer returns a dict with keys for all readable documents,
        # so we only include documents the user has permission to read
        results = []
        for global_id in document_ids:
            local_doc_id = local_id_by_global[global_id]

            # Only include documents that are in the result (user has permission)
            if local_doc_id in datacells_by_doc:
                results.append(
                    {
                        "document_id": global_id,
                        "datacells": datacells_by_doc[local_doc_id],
                    }
                )

        return results

    # CONDITIONAL ANALYZER FIELDS #####################################
    # These are conditionally defined based on settings.USE_ANALYZER
    if settings.USE_ANALYZER:

        # GREMLIN ENGINE RESOLVERS #####################################
        gremlin_engine = relay.Node.Field(GremlinEngineType_READ)

        def resolve_gremlin_engine(self, info, **kwargs) -> Any:
            django_pk = int(from_global_id(kwargs["id"])[1])
            return GremlinEngine.objects.visible_to_user(info.context.user).get(
                id=django_pk
            )

        gremlin_engines = DjangoFilterConnectionField(
            GremlinEngineType_READ, filterset_class=GremlinEngineFilter
        )

        def resolve_gremlin_engines(self, info, **kwargs) -> Any:
            return GremlinEngine.objects.visible_to_user(info.context.user)

        # ANALYZER RESOLVERS #####################################
        analyzer = relay.Node.Field(AnalyzerType)

        def resolve_analyzer(self, info, **kwargs) -> Any:

            if kwargs.get("id", None) is not None:
                django_pk = from_global_id(kwargs["id"])[1]
            elif kwargs.get("analyzerId", None) is not None:
                django_pk = kwargs["analyzerId"]
            else:
                return None

            return Analyzer.objects.visible_to_user(info.context.user).get(id=django_pk)

        analyzers = DjangoFilterConnectionField(
            AnalyzerType, filterset_class=AnalyzerFilter
        )

        def resolve_analyzers(self, info, **kwargs) -> Any:
            return Analyzer.objects.visible_to_user(info.context.user)

        # ANALYSIS RESOLVERS #####################################
        analysis = relay.Node.Field(AnalysisType)

        def resolve_analysis(self, info, **kwargs) -> Any:
            from opencontractserver.annotations.query_optimizer import (
                AnalysisQueryOptimizer,
            )

            django_pk = from_global_id(kwargs["id"])[1]
            has_perm, analysis = AnalysisQueryOptimizer.check_analysis_permission(
                info.context.user, int(django_pk), context=info.context
            )
            return analysis if has_perm else None

        analyses = DjangoFilterConnectionField(
            AnalysisType, filterset_class=AnalysisFilter
        )

        @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
        def resolve_analyses(self, info, **kwargs) -> Any:
            from opencontractserver.annotations.query_optimizer import (
                AnalysisQueryOptimizer,
            )

            corpus_id = kwargs.get("corpus_id")
            if corpus_id:
                corpus_django_pk = int(from_global_id(corpus_id)[1])
            else:
                corpus_django_pk = None

            return AnalysisQueryOptimizer.get_visible_analyses(
                info.context.user, corpus_id=corpus_django_pk, context=info.context
            )
