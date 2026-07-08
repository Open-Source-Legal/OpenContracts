"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

from config.graphql.filters import AnalysisFilter
from config.graphql.filters import AnalyzerFilter
from config.graphql.filters import ColumnFilter
from config.graphql.filters import DatacellFilter
from config.graphql.filters import ExtractFilter
from config.graphql.filters import FieldsetFilter
from config.graphql.filters import GremlinEngineFilter
from opencontractserver.analyzer.models import Analysis
from opencontractserver.analyzer.models import Analyzer
from opencontractserver.analyzer.models import GremlinEngine
from opencontractserver.extracts.models import Column
from opencontractserver.extracts.models import Datacell
from opencontractserver.extracts.models import Extract
from opencontractserver.extracts.models import Fieldset


@strawberry.type(name="ExtractDiffType")
class ExtractDiffType:
    extract_a: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="extractA", default=None)
    extract_b: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="extractB", default=None)
    cells: list[Optional["ExtractCellDiffType"]] = strawberry.field(name="cells", default=None)
    summary: "ExtractDiffSummaryType" = strawberry.field(name="summary", default=None)


register_type("ExtractDiffType", ExtractDiffType, model=None)


@strawberry.type(name="ExtractCellDiffType", description="One row of the compare grid: same (column, document) on both sides.\n\n``rowKey`` is a stable identifier for the document row across iterations\n(the document's ``version_tree_id`` when available, else its PK). Using\nthe version-tree key lets the UI render a single row even when the two\niterations point at different content versions of the same logical doc.\n``columnKey`` is the column name, which is stable when fieldsets are\ncloned because the clone preserves the name.")
class ExtractCellDiffType:
    row_key: str = strawberry.field(name="rowKey", default=None)
    column_key: str = strawberry.field(name="columnKey", default=None)
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="document", description='Representative Document (B side preferred). For DOCUMENT_VERSIONS-axis diffs use documentA / documentB to see the actual version on each side.', default=None)
    document_a: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="documentA", default=None)
    document_b: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="documentB", default=None)
    cell_a: Optional[Annotated["DatacellType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="cellA", default=None)
    cell_b: Optional[Annotated["DatacellType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="cellB", default=None)
    status: enums.ExtractDiffStatus = strawberry.field(name="status", default=None)
    column_config_changed: Optional[bool] = strawberry.field(name="columnConfigChanged", description='True when the column on B has a different prompt / instructions / output_type from the column on A (FIELDSET axis).', default=None)


register_type("ExtractCellDiffType", ExtractCellDiffType, model=None)


@strawberry.type(name="ExtractDiffSummaryType", description='Aggregate counts for the diff — used for the heatmap legend.')
class ExtractDiffSummaryType:
    unchanged: int = strawberry.field(name="unchanged", default=None)
    changed: int = strawberry.field(name="changed", default=None)
    only_in_a: int = strawberry.field(name="onlyInA", default=None)
    only_in_b: int = strawberry.field(name="onlyInB", default=None)
    total: int = strawberry.field(name="total", default=None)


register_type("ExtractDiffSummaryType", ExtractDiffSummaryType, model=None)


@strawberry.type(name="MetadataCompletionStatusType", description='Type for metadata completion status information.')
class MetadataCompletionStatusType:
    total_fields: Optional[int] = strawberry.field(name="totalFields", default=None)
    filled_fields: Optional[int] = strawberry.field(name="filledFields", default=None)
    missing_fields: Optional[int] = strawberry.field(name="missingFields", default=None)
    percentage: Optional[float] = strawberry.field(name="percentage", default=None)
    missing_required: Optional[list[Optional[str]]] = strawberry.field(name="missingRequired", default=None)


register_type("MetadataCompletionStatusType", MetadataCompletionStatusType, model=None)


@strawberry.type(name="DocumentMetadataResultType", description='Type for batch metadata query results - groups datacells by document.')
class DocumentMetadataResultType:
    document_id: Optional[strawberry.ID] = strawberry.field(name="documentId", description="The document's global ID", default=None)
    datacells: Optional[list[Optional[Annotated["DatacellType", strawberry.lazy("config.graphql.extract_types")]]]] = strawberry.field(name="datacells", description='Metadata datacells for this document', default=None)


register_type("DocumentMetadataResultType", DocumentMetadataResultType, model=None)


def q_fieldset(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["FieldsetType", strawberry.lazy("config.graphql.extract_types")]]:
    return get_node_from_global_id(info, id, only_type_name="FieldsetType")


def _resolve_Query_fieldsets(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:146

    Port of ExtractQueryMixin.resolve_fieldsets
    """
    raise NotImplementedError("_resolve_Query_fieldsets not yet ported — see manifest")


def q_fieldsets(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, name__contains: Annotated[Optional[str], strawberry.argument(name="name_Contains")] = strawberry.UNSET, description__contains: Annotated[Optional[str], strawberry.argument(name="description_Contains")] = strawberry.UNSET) -> Optional[Annotated["FieldsetTypeConnection", strawberry.lazy("config.graphql.extract_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "name": name, "name__contains": name__contains, "description__contains": description__contains})
    resolved = _resolve_Query_fieldsets(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="FieldsetType", default_manager=Fieldset._default_manager, filterset_class=setup_filterset(FieldsetFilter), filter_args={"name": "name", "name__contains": "name__contains", "description__contains": "description__contains"}, )


def q_column(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["ColumnType", strawberry.lazy("config.graphql.extract_types")]]:
    return get_node_from_global_id(info, id, only_type_name="ColumnType")


def _resolve_Query_columns(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:164

    Port of ExtractQueryMixin.resolve_columns
    """
    raise NotImplementedError("_resolve_Query_columns not yet ported — see manifest")


def q_columns(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, query__contains: Annotated[Optional[str], strawberry.argument(name="query_Contains")] = strawberry.UNSET, match_text__contains: Annotated[Optional[str], strawberry.argument(name="matchText_Contains")] = strawberry.UNSET, output_type: Annotated[Optional[str], strawberry.argument(name="outputType")] = strawberry.UNSET, limit_to_label: Annotated[Optional[str], strawberry.argument(name="limitToLabel")] = strawberry.UNSET) -> Optional[Annotated["ColumnTypeConnection", strawberry.lazy("config.graphql.extract_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "query__contains": query__contains, "match_text__contains": match_text__contains, "output_type": output_type, "limit_to_label": limit_to_label})
    resolved = _resolve_Query_columns(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ColumnType", default_manager=Column._default_manager, filterset_class=setup_filterset(ColumnFilter), filter_args={"query__contains": "query__contains", "match_text__contains": "match_text__contains", "output_type": "output_type", "limit_to_label": "limit_to_label"}, )


def q_extract(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["ExtractType", strawberry.lazy("config.graphql.extract_types")]]:
    return get_node_from_global_id(info, id, only_type_name="ExtractType")


def _resolve_Query_extracts(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:189

    Port of ExtractQueryMixin.resolve_extracts
    """
    raise NotImplementedError("_resolve_Query_extracts not yet ported — see manifest")


def q_extracts(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, corpus_action__isnull: Annotated[Optional[bool], strawberry.argument(name="corpusAction_Isnull")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, name__contains: Annotated[Optional[str], strawberry.argument(name="name_Contains")] = strawberry.UNSET, created__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="created_Lte")] = strawberry.UNSET, created__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="created_Gte")] = strawberry.UNSET, started__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="started_Lte")] = strawberry.UNSET, started__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="started_Gte")] = strawberry.UNSET, finished__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="finished_Lte")] = strawberry.UNSET, finished__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="finished_Gte")] = strawberry.UNSET, corpus: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus")] = strawberry.UNSET) -> Optional[Annotated["ExtractTypeConnection", strawberry.lazy("config.graphql.extract_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "corpus_action__isnull": corpus_action__isnull, "name": name, "name__contains": name__contains, "created__lte": created__lte, "created__gte": created__gte, "started__lte": started__lte, "started__gte": started__gte, "finished__lte": finished__lte, "finished__gte": finished__gte, "corpus": corpus})
    resolved = _resolve_Query_extracts(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ExtractType", default_manager=Extract._default_manager, filterset_class=setup_filterset(ExtractFilter), filter_args={"corpus_action__isnull": "corpus_action__isnull", "name": "name", "name__contains": "name__contains", "created__lte": "created__lte", "created__gte": "created__gte", "started__lte": "started__lte", "started__gte": "started__gte", "finished__lte": "finished__lte", "finished__gte": "finished__gte", "corpus": "corpus"}, )


def _resolve_Query_compare_extracts(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:209

    Port of ExtractQueryMixin.resolve_compare_extracts
    """
    raise NotImplementedError("_resolve_Query_compare_extracts not yet ported — see manifest")


def q_compare_extracts(info: strawberry.Info, extract_a_id: Annotated[strawberry.ID, strawberry.argument(name="extractAId")] = strawberry.UNSET, extract_b_id: Annotated[strawberry.ID, strawberry.argument(name="extractBId")] = strawberry.UNSET) -> Optional["ExtractDiffType"]:
    kwargs = strip_unset({"extract_a_id": extract_a_id, "extract_b_id": extract_b_id})
    return _resolve_Query_compare_extracts(None, info, **kwargs)


def q_datacell(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["DatacellType", strawberry.lazy("config.graphql.extract_types")]]:
    return get_node_from_global_id(info, id, only_type_name="DatacellType")


def _resolve_Query_datacells(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:272

    Port of ExtractQueryMixin.resolve_datacells
    """
    raise NotImplementedError("_resolve_Query_datacells not yet ported — see manifest")


def q_datacells(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, data_definition: Annotated[Optional[str], strawberry.argument(name="dataDefinition")] = strawberry.UNSET, started__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="started_Lte")] = strawberry.UNSET, started__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="started_Gte")] = strawberry.UNSET, completed__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="completed_Lte")] = strawberry.UNSET, completed__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="completed_Gte")] = strawberry.UNSET, failed__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="failed_Lte")] = strawberry.UNSET, failed__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="failed_Gte")] = strawberry.UNSET, in_corpus_with_id: Annotated[Optional[str], strawberry.argument(name="inCorpusWithId")] = strawberry.UNSET, for_document_with_id: Annotated[Optional[str], strawberry.argument(name="forDocumentWithId")] = strawberry.UNSET) -> Optional[Annotated["DatacellTypeConnection", strawberry.lazy("config.graphql.extract_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "data_definition": data_definition, "started__lte": started__lte, "started__gte": started__gte, "completed__lte": completed__lte, "completed__gte": completed__gte, "failed__lte": failed__lte, "failed__gte": failed__gte, "in_corpus_with_id": in_corpus_with_id, "for_document_with_id": for_document_with_id})
    resolved = _resolve_Query_datacells(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", default_manager=Datacell._default_manager, filterset_class=setup_filterset(DatacellFilter), filter_args={"data_definition": "data_definition", "started__lte": "started__lte", "started__gte": "started__gte", "completed__lte": "completed__lte", "completed__gte": "completed__gte", "failed__lte": "failed__lte", "failed__gte": "failed__gte", "in_corpus_with_id": "in_corpus_with_id", "for_document_with_id": "for_document_with_id"}, )


def _resolve_Query_registered_extract_tasks(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:279

    Port of ExtractQueryMixin.resolve_registered_extract_tasks
    """
    raise NotImplementedError("_resolve_Query_registered_extract_tasks not yet ported — see manifest")


def q_registered_extract_tasks(info: strawberry.Info) -> Optional[GenericScalar]:
    kwargs = strip_unset({})
    return _resolve_Query_registered_extract_tasks(None, info, **kwargs)


def _resolve_Query_document_metadata_datacells(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:325

    Port of ExtractQueryMixin.resolve_document_metadata_datacells
    """
    raise NotImplementedError("_resolve_Query_document_metadata_datacells not yet ported — see manifest")


def q_document_metadata_datacells(info: strawberry.Info, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["DatacellType", strawberry.lazy("config.graphql.extract_types")]]]]:
    kwargs = strip_unset({"document_id": document_id, "corpus_id": corpus_id})
    return _resolve_Query_document_metadata_datacells(None, info, **kwargs)


def _resolve_Query_metadata_completion_status_v2(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:337

    Port of ExtractQueryMixin.resolve_metadata_completion_status_v2
    """
    raise NotImplementedError("_resolve_Query_metadata_completion_status_v2 not yet ported — see manifest")


def q_metadata_completion_status_v2(info: strawberry.Info, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional["MetadataCompletionStatusType"]:
    kwargs = strip_unset({"document_id": document_id, "corpus_id": corpus_id})
    return _resolve_Query_metadata_completion_status_v2(None, info, **kwargs)


def _resolve_Query_documents_metadata_datacells_batch(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:351

    Port of ExtractQueryMixin.resolve_documents_metadata_datacells_batch
    """
    raise NotImplementedError("_resolve_Query_documents_metadata_datacells_batch not yet ported — see manifest")


def q_documents_metadata_datacells_batch(info: strawberry.Info, document_ids: Annotated[list[Optional[strawberry.ID]], strawberry.argument(name="documentIds")] = strawberry.UNSET, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Optional["DocumentMetadataResultType"]]]:
    kwargs = strip_unset({"document_ids": document_ids, "corpus_id": corpus_id})
    return _resolve_Query_documents_metadata_datacells_batch(None, info, **kwargs)


def q_gremlin_engine(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["GremlinEngineType_READ", strawberry.lazy("config.graphql.extract_types")]]:
    return get_node_from_global_id(info, id, only_type_name="GremlinEngineType_READ")


def _resolve_Query_gremlin_engines(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:421

    Port of ExtractQueryMixin.resolve_gremlin_engines
    """
    raise NotImplementedError("_resolve_Query_gremlin_engines not yet ported — see manifest")


def q_gremlin_engines(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, url: Annotated[Optional[str], strawberry.argument(name="url")] = strawberry.UNSET) -> Optional[Annotated["GremlinEngineType_READConnection", strawberry.lazy("config.graphql.extract_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "url": url})
    resolved = _resolve_Query_gremlin_engines(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="GremlinEngineType_READ", default_manager=GremlinEngine._default_manager, filterset_class=setup_filterset(GremlinEngineFilter), filter_args={"url": "url"}, )


def q_analyzer(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["AnalyzerType", strawberry.lazy("config.graphql.extract_types")]]:
    return get_node_from_global_id(info, id, only_type_name="AnalyzerType")


def _resolve_Query_analyzers(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:449

    Port of ExtractQueryMixin.resolve_analyzers
    """
    raise NotImplementedError("_resolve_Query_analyzers not yet ported — see manifest")


def q_analyzers(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id__contains: Annotated[Optional[strawberry.ID], strawberry.argument(name="id_Contains")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, description__contains: Annotated[Optional[str], strawberry.argument(name="description_Contains")] = strawberry.UNSET, disabled: Annotated[Optional[bool], strawberry.argument(name="disabled")] = strawberry.UNSET, analyzer_id: Annotated[Optional[str], strawberry.argument(name="analyzerId")] = strawberry.UNSET, hosted_by_gremlin_engine_id: Annotated[Optional[str], strawberry.argument(name="hostedByGremlinEngineId")] = strawberry.UNSET, used_in_analysis_ids: Annotated[Optional[str], strawberry.argument(name="usedInAnalysisIds")] = strawberry.UNSET) -> Optional[Annotated["AnalyzerTypeConnection", strawberry.lazy("config.graphql.extract_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id__contains": id__contains, "id": id, "description__contains": description__contains, "disabled": disabled, "analyzer_id": analyzer_id, "hosted_by_gremlin_engine_id": hosted_by_gremlin_engine_id, "used_in_analysis_ids": used_in_analysis_ids})
    resolved = _resolve_Query_analyzers(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalyzerType", default_manager=Analyzer._default_manager, filterset_class=setup_filterset(AnalyzerFilter), filter_args={"id__contains": "id__contains", "id": "id", "description__contains": "description__contains", "disabled": "disabled", "analyzer_id": "analyzer_id", "hosted_by_gremlin_engine_id": "hosted_by_gremlin_engine_id", "used_in_analysis_ids": "used_in_analysis_ids"}, )


def q_analysis(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]]:
    return get_node_from_global_id(info, id, only_type_name="AnalysisType")


def _resolve_Query_analyses(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:470

    Port of ExtractQueryMixin.resolve_analyses
    """
    raise NotImplementedError("_resolve_Query_analyses not yet ported — see manifest")


def q_analyses(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, analyzed_corpus__isnull: Annotated[Optional[bool], strawberry.argument(name="analyzedCorpus_Isnull")] = strawberry.UNSET, analysis_started__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="analysisStarted_Gte")] = strawberry.UNSET, analysis_started__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="analysisStarted_Lte")] = strawberry.UNSET, analysis_completed__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="analysisCompleted_Gte")] = strawberry.UNSET, analysis_completed__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="analysisCompleted_Lte")] = strawberry.UNSET, status: Annotated[Optional[enums.AnalyzerAnalysisStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, analyzer__task_name__in: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="analyzer_TaskName_In")] = strawberry.UNSET, received_callback_results: Annotated[Optional[bool], strawberry.argument(name="receivedCallbackResults")] = strawberry.UNSET, analyzed_corpus_id: Annotated[Optional[str], strawberry.argument(name="analyzedCorpusId")] = strawberry.UNSET, analyzed_document_id: Annotated[Optional[str], strawberry.argument(name="analyzedDocumentId")] = strawberry.UNSET, search_text: Annotated[Optional[str], strawberry.argument(name="searchText")] = strawberry.UNSET) -> Optional[Annotated["AnalysisTypeConnection", strawberry.lazy("config.graphql.extract_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "analyzed_corpus__isnull": analyzed_corpus__isnull, "analysis_started__gte": analysis_started__gte, "analysis_started__lte": analysis_started__lte, "analysis_completed__gte": analysis_completed__gte, "analysis_completed__lte": analysis_completed__lte, "status": status, "analyzer__task_name__in": analyzer__task_name__in, "received_callback_results": received_callback_results, "analyzed_corpus_id": analyzed_corpus_id, "analyzed_document_id": analyzed_document_id, "search_text": search_text})
    resolved = _resolve_Query_analyses(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalysisType", default_manager=Analysis._default_manager, filterset_class=setup_filterset(AnalysisFilter), filter_args={"analyzed_corpus__isnull": "analyzed_corpus__isnull", "analysis_started__gte": "analysis_started__gte", "analysis_started__lte": "analysis_started__lte", "analysis_completed__gte": "analysis_completed__gte", "analysis_completed__lte": "analysis_completed__lte", "status": "status", "analyzer__task_name__in": "analyzer__task_name__in", "received_callback_results": "received_callback_results", "analyzed_corpus_id": "analyzed_corpus_id", "analyzed_document_id": "analyzed_document_id", "search_text": "search_text"}, )



QUERY_FIELDS = {
    "fieldset": strawberry.field(resolver=q_fieldset, name="fieldset"),
    "fieldsets": strawberry.field(resolver=q_fieldsets, name="fieldsets"),
    "column": strawberry.field(resolver=q_column, name="column"),
    "columns": strawberry.field(resolver=q_columns, name="columns"),
    "extract": strawberry.field(resolver=q_extract, name="extract"),
    "extracts": strawberry.field(resolver=q_extracts, name="extracts"),
    "compare_extracts": strawberry.field(resolver=q_compare_extracts, name="compareExtracts", description='Cell-level diff between two iterations of the same extract series.'),
    "datacell": strawberry.field(resolver=q_datacell, name="datacell"),
    "datacells": strawberry.field(resolver=q_datacells, name="datacells"),
    "registered_extract_tasks": strawberry.field(resolver=q_registered_extract_tasks, name="registeredExtractTasks"),
    "document_metadata_datacells": strawberry.field(resolver=q_document_metadata_datacells, name="documentMetadataDatacells", description='Get metadata datacells for a document in a corpus'),
    "metadata_completion_status_v2": strawberry.field(resolver=q_metadata_completion_status_v2, name="metadataCompletionStatusV2", description='Get metadata completion status for a document using column/datacell system'),
    "documents_metadata_datacells_batch": strawberry.field(resolver=q_documents_metadata_datacells_batch, name="documentsMetadataDatacellsBatch", description='Get metadata datacells for multiple documents in a single query (batch)'),
    "gremlin_engine": strawberry.field(resolver=q_gremlin_engine, name="gremlinEngine"),
    "gremlin_engines": strawberry.field(resolver=q_gremlin_engines, name="gremlinEngines"),
    "analyzer": strawberry.field(resolver=q_analyzer, name="analyzer"),
    "analyzers": strawberry.field(resolver=q_analyzers, name="analyzers"),
    "analysis": strawberry.field(resolver=q_analysis, name="analysis"),
    "analyses": strawberry.field(resolver=q_analyses, name="analyses"),
}
