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
import inspect
import logging
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql import enums
from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.filtering import setup_filterset
from config.graphql.core.relay import (
    get_node_from_global_id,
    register_type,
    resolve_django_connection,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.filters import (
    AnalysisFilter,
    AnalyzerFilter,
    ColumnFilter,
    DatacellFilter,
    ExtractFilter,
    FieldsetFilter,
    GremlinEngineFilter,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.constants.extracts import EXTRACT_LIST_MAX_PAGE_SIZE
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


@strawberry.type(name="ExtractDiffType")
class ExtractDiffType:
    extract_a: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="extractA", default=None)
    extract_b: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="extractB", default=None)
    cells: list[ExtractCellDiffType | None] = strawberry.field(
        name="cells", default=None
    )
    summary: ExtractDiffSummaryType = strawberry.field(name="summary", default=None)


register_type("ExtractDiffType", ExtractDiffType, model=None)


@strawberry.type(
    name="ExtractCellDiffType",
    description="One row of the compare grid: same (column, document) on both sides.\n\n``rowKey`` is a stable identifier for the document row across iterations\n(the document's ``version_tree_id`` when available, else its PK). Using\nthe version-tree key lets the UI render a single row even when the two\niterations point at different content versions of the same logical doc.\n``columnKey`` is the column name, which is stable when fieldsets are\ncloned because the clone preserves the name.",
)
class ExtractCellDiffType:
    row_key: str = strawberry.field(name="rowKey", default=None)
    column_key: str = strawberry.field(name="columnKey", default=None)
    document: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(
        name="document",
        description="Representative Document (B side preferred). For DOCUMENT_VERSIONS-axis diffs use documentA / documentB to see the actual version on each side.",
        default=None,
    )
    document_a: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="documentA", default=None)
    document_b: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="documentB", default=None)
    cell_a: None | (
        Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="cellA", default=None)
    cell_b: None | (
        Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="cellB", default=None)
    status: enums.ExtractDiffStatus = strawberry.field(name="status", default=None)
    column_config_changed: bool | None = strawberry.field(
        name="columnConfigChanged",
        description="True when the column on B has a different prompt / instructions / output_type from the column on A (FIELDSET axis).",
        default=None,
    )


register_type("ExtractCellDiffType", ExtractCellDiffType, model=None)


@strawberry.type(
    name="ExtractDiffSummaryType",
    description="Aggregate counts for the diff — used for the heatmap legend.",
)
class ExtractDiffSummaryType:
    unchanged: int = strawberry.field(name="unchanged", default=None)
    changed: int = strawberry.field(name="changed", default=None)
    only_in_a: int = strawberry.field(name="onlyInA", default=None)
    only_in_b: int = strawberry.field(name="onlyInB", default=None)
    total: int = strawberry.field(name="total", default=None)


register_type("ExtractDiffSummaryType", ExtractDiffSummaryType, model=None)


@strawberry.type(
    name="MetadataCompletionStatusType",
    description="Type for metadata completion status information.",
)
class MetadataCompletionStatusType:
    total_fields: int | None = strawberry.field(name="totalFields", default=None)
    filled_fields: int | None = strawberry.field(name="filledFields", default=None)
    missing_fields: int | None = strawberry.field(name="missingFields", default=None)
    percentage: float | None = strawberry.field(name="percentage", default=None)
    missing_required: list[str | None] | None = strawberry.field(
        name="missingRequired", default=None
    )


register_type("MetadataCompletionStatusType", MetadataCompletionStatusType, model=None)


@strawberry.type(
    name="DocumentMetadataResultType",
    description="Type for batch metadata query results - groups datacells by document.",
)
class DocumentMetadataResultType:
    document_id: strawberry.ID | None = strawberry.field(
        name="documentId", description="The document's global ID", default=None
    )
    datacells: None | (
        list[
            None
            | (Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")])
        ]
    ) = strawberry.field(
        name="datacells",
        description="Metadata datacells for this document",
        default=None,
    )


register_type("DocumentMetadataResultType", DocumentMetadataResultType, model=None)


def q_fieldset(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[FieldsetType, strawberry.lazy("config.graphql.extract_types")]):
    return get_node_from_global_id(info, id, only_type_name="FieldsetType")


def _resolve_Query_fieldsets(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:146

    Port of ExtractQueryMixin.resolve_fieldsets
    """
    return BaseService.filter_visible(Fieldset, info.context.user, request=info.context)


def q_fieldsets(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    name__contains: Annotated[
        str | None, strawberry.argument(name="name_Contains")
    ] = strawberry.UNSET,
    description__contains: Annotated[
        str | None, strawberry.argument(name="description_Contains")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[FieldsetTypeConnection, strawberry.lazy("config.graphql.extract_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "name": name,
            "name__contains": name__contains,
            "description__contains": description__contains,
        }
    )
    resolved = _resolve_Query_fieldsets(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="FieldsetType",
        default_manager=Fieldset._default_manager,
        filterset_class=setup_filterset(FieldsetFilter),
        filter_args={
            "name": "name",
            "name__contains": "name__contains",
            "description__contains": "description__contains",
        },
    )


def q_column(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> Annotated[ColumnType, strawberry.lazy("config.graphql.extract_types")] | None:
    return get_node_from_global_id(info, id, only_type_name="ColumnType")


def _resolve_Query_columns(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:164

    Port of ExtractQueryMixin.resolve_columns
    """
    return BaseService.filter_visible(Column, info.context.user, request=info.context)


def q_columns(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    query__contains: Annotated[
        str | None, strawberry.argument(name="query_Contains")
    ] = strawberry.UNSET,
    match_text__contains: Annotated[
        str | None, strawberry.argument(name="matchText_Contains")
    ] = strawberry.UNSET,
    output_type: Annotated[
        str | None, strawberry.argument(name="outputType")
    ] = strawberry.UNSET,
    limit_to_label: Annotated[
        str | None, strawberry.argument(name="limitToLabel")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[ColumnTypeConnection, strawberry.lazy("config.graphql.extract_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "query__contains": query__contains,
            "match_text__contains": match_text__contains,
            "output_type": output_type,
            "limit_to_label": limit_to_label,
        }
    )
    resolved = _resolve_Query_columns(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="ColumnType",
        default_manager=Column._default_manager,
        filterset_class=setup_filterset(ColumnFilter),
        filter_args={
            "query__contains": "query__contains",
            "match_text__contains": "match_text__contains",
            "output_type": "output_type",
            "limit_to_label": "limit_to_label",
        },
    )


def q_extract(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]):
    return get_node_from_global_id(info, id, only_type_name="ExtractType")


def _resolve_Query_extracts(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:189

    Port of ExtractQueryMixin.resolve_extracts
    """
    from opencontractserver.extracts.services import ExtractService

    corpus_id = kwargs.get("corpus_id")
    if corpus_id:
        corpus_django_pk = int(from_global_id(corpus_id)[1])
    else:
        corpus_django_pk = None

    return ExtractService.get_visible_extracts(
        info.context.user, corpus_id=corpus_django_pk, context=info.context
    )


def q_extracts(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    corpus_action__isnull: Annotated[
        bool | None, strawberry.argument(name="corpusAction_Isnull")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    name__contains: Annotated[
        str | None, strawberry.argument(name="name_Contains")
    ] = strawberry.UNSET,
    created__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="created_Lte")
    ] = strawberry.UNSET,
    created__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="created_Gte")
    ] = strawberry.UNSET,
    started__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="started_Lte")
    ] = strawberry.UNSET,
    started__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="started_Gte")
    ] = strawberry.UNSET,
    finished__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="finished_Lte")
    ] = strawberry.UNSET,
    finished__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="finished_Gte")
    ] = strawberry.UNSET,
    corpus: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpus")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[ExtractTypeConnection, strawberry.lazy("config.graphql.extract_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "corpus_action__isnull": corpus_action__isnull,
            "name": name,
            "name__contains": name__contains,
            "created__lte": created__lte,
            "created__gte": created__gte,
            "started__lte": started__lte,
            "started__gte": started__gte,
            "finished__lte": finished__lte,
            "finished__gte": finished__gte,
            "corpus": corpus,
        }
    )
    resolved = _resolve_Query_extracts(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="ExtractType",
        default_manager=Extract._default_manager,
        filterset_class=setup_filterset(ExtractFilter),
        filter_args={
            "corpus_action__isnull": "corpus_action__isnull",
            "name": "name",
            "name__contains": "name__contains",
            "created__lte": "created__lte",
            "created__gte": "created__gte",
            "started__lte": "started__lte",
            "started__gte": "started__gte",
            "finished__lte": "finished__lte",
            "finished__gte": "finished__gte",
            "corpus": "corpus",
        },
        # ``max_limit`` must match (or exceed) the frontend ``EXTRACT_PAGINATION``
        # page size — Graphene silently clamps to this value and otherwise
        # pages never advance past the cap (the bug fixed in PR #1602).
        max_limit=EXTRACT_LIST_MAX_PAGE_SIZE,
    )


@login_required
def _resolve_Query_compare_extracts(root, info, extract_a_id, extract_b_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:210

    Port of ExtractQueryMixin.resolve_compare_extracts
    """
    from opencontractserver.extracts.diff import diff_extracts, summarise
    from opencontractserver.extracts.services import ExtractService

    user = info.context.user
    a_pk = int(from_global_id(extract_a_id)[1])
    b_pk = int(from_global_id(extract_b_id)[1])

    # Permission check leverages the same optimizer the extract node
    # resolver uses, so visibility rules stay consistent.
    a_ok, extract_a = ExtractService.check_extract_permission(
        user, a_pk, context=info.context
    )
    b_ok, extract_b = ExtractService.check_extract_permission(
        user, b_pk, context=info.context
    )
    if not (a_ok and b_ok and extract_a and extract_b):
        return None

    cells_a = ExtractService.get_extract_datacells(extract_a, user, document_id=None)
    cells_b = ExtractService.get_extract_datacells(extract_b, user, document_id=None)

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
                # ``diff_extracts`` returns plain status strings; coerce to
                # the strawberry enum member (graphene accepted the raw
                # value — serialized output is identical).
                status=enums.ExtractDiffStatus(d.status),
                column_config_changed=d.column_config_changed,
            )
            for d in diffs
        ],
        summary=ExtractDiffSummaryType(**summarise(diffs)),
    )


def q_compare_extracts(
    info: strawberry.Info,
    extract_a_id: Annotated[
        strawberry.ID, strawberry.argument(name="extractAId")
    ] = strawberry.UNSET,
    extract_b_id: Annotated[
        strawberry.ID, strawberry.argument(name="extractBId")
    ] = strawberry.UNSET,
) -> ExtractDiffType | None:
    kwargs = strip_unset({"extract_a_id": extract_a_id, "extract_b_id": extract_b_id})
    return _resolve_Query_compare_extracts(None, info, **kwargs)


def q_datacell(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")]):
    return get_node_from_global_id(info, id, only_type_name="DatacellType")


def _resolve_Query_datacells(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:272

    Port of ExtractQueryMixin.resolve_datacells
    """
    return BaseService.filter_visible(Datacell, info.context.user, request=info.context)


def q_datacells(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    data_definition: Annotated[
        str | None, strawberry.argument(name="dataDefinition")
    ] = strawberry.UNSET,
    started__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="started_Lte")
    ] = strawberry.UNSET,
    started__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="started_Gte")
    ] = strawberry.UNSET,
    completed__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="completed_Lte")
    ] = strawberry.UNSET,
    completed__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="completed_Gte")
    ] = strawberry.UNSET,
    failed__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="failed_Lte")
    ] = strawberry.UNSET,
    failed__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="failed_Gte")
    ] = strawberry.UNSET,
    in_corpus_with_id: Annotated[
        str | None, strawberry.argument(name="inCorpusWithId")
    ] = strawberry.UNSET,
    for_document_with_id: Annotated[
        str | None, strawberry.argument(name="forDocumentWithId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[DatacellTypeConnection, strawberry.lazy("config.graphql.extract_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "data_definition": data_definition,
            "started__lte": started__lte,
            "started__gte": started__gte,
            "completed__lte": completed__lte,
            "completed__gte": completed__gte,
            "failed__lte": failed__lte,
            "failed__gte": failed__gte,
            "in_corpus_with_id": in_corpus_with_id,
            "for_document_with_id": for_document_with_id,
        }
    )
    resolved = _resolve_Query_datacells(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="DatacellType",
        default_manager=Datacell._default_manager,
        filterset_class=setup_filterset(DatacellFilter),
        filter_args={
            "data_definition": "data_definition",
            "started__lte": "started__lte",
            "started__gte": "started__gte",
            "completed__lte": "completed__lte",
            "completed__gte": "completed__gte",
            "failed__lte": "failed__lte",
            "failed__gte": "failed__gte",
            "in_corpus_with_id": "in_corpus_with_id",
            "for_document_with_id": "for_document_with_id",
        },
    )


@login_required
def _resolve_Query_registered_extract_tasks(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:280

    Port of ExtractQueryMixin.resolve_registered_extract_tasks
    """
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


def q_registered_extract_tasks(info: strawberry.Info) -> GenericScalar | None:
    kwargs = strip_unset({})
    return _resolve_Query_registered_extract_tasks(None, info, **kwargs)


def _resolve_Query_document_metadata_datacells(root, info, document_id, corpus_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:325

    Get metadata datacells for a document using MetadataService.
    """
    from opencontractserver.extracts.services import MetadataService

    user = info.context.user
    local_doc_id = int(from_global_id(document_id)[1])
    local_corpus_id = int(from_global_id(corpus_id)[1])

    return MetadataService.get_document_metadata(
        user, local_doc_id, local_corpus_id, manual_only=True
    )


def q_document_metadata_datacells(
    info: strawberry.Info,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")])
    ]
):
    kwargs = strip_unset({"document_id": document_id, "corpus_id": corpus_id})
    return _resolve_Query_document_metadata_datacells(None, info, **kwargs)


def _resolve_Query_metadata_completion_status_v2(root, info, document_id, corpus_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:337

    Get metadata completion status using MetadataService.
    """
    from opencontractserver.extracts.services import MetadataService

    user = info.context.user
    local_doc_id = int(from_global_id(document_id)[1])
    local_corpus_id = int(from_global_id(corpus_id)[1])

    status = MetadataService.get_metadata_completion_status(
        user, local_doc_id, local_corpus_id
    )
    if status is None:
        return None
    # The service returns a plain dict (graphene's default resolver read dict
    # keys); strawberry resolves attributes, so construct the helper type.
    return MetadataCompletionStatusType(**status)


def q_metadata_completion_status_v2(
    info: strawberry.Info,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> MetadataCompletionStatusType | None:
    kwargs = strip_unset({"document_id": document_id, "corpus_id": corpus_id})
    return _resolve_Query_metadata_completion_status_v2(None, info, **kwargs)


def _resolve_Query_documents_metadata_datacells_batch(
    root, info, document_ids, corpus_id
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:351

    Get metadata datacells for multiple documents using MetadataService.

    This batch query solves the N+1 problem when loading metadata for a grid view.
    Uses the centralized MetadataService which applies proper permission
    filtering: Effective Permission = MIN(document_permission, corpus_permission)
    """
    from opencontractserver.extracts.services import MetadataService

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
    datacells_by_doc = MetadataService.get_documents_metadata_batch(
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
                DocumentMetadataResultType(
                    document_id=global_id,
                    datacells=datacells_by_doc[local_doc_id],
                )
            )

    return results


def q_documents_metadata_datacells_batch(
    info: strawberry.Info,
    document_ids: Annotated[
        list[strawberry.ID | None], strawberry.argument(name="documentIds")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> list[DocumentMetadataResultType | None] | None:
    kwargs = strip_unset({"document_ids": document_ids, "corpus_id": corpus_id})
    return _resolve_Query_documents_metadata_datacells_batch(None, info, **kwargs)


def q_gremlin_engine(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[GremlinEngineType_READ, strawberry.lazy("config.graphql.extract_types")]
):
    return get_node_from_global_id(info, id, only_type_name="GremlinEngineType_READ")


def _resolve_Query_gremlin_engines(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:421

    Port of ExtractQueryMixin.resolve_gremlin_engines
    """
    return BaseService.filter_visible(
        GremlinEngine, info.context.user, request=info.context
    )


def q_gremlin_engines(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    url: Annotated[str | None, strawberry.argument(name="url")] = strawberry.UNSET,
) -> None | (
    Annotated[
        GremlinEngineType_READConnection,
        strawberry.lazy("config.graphql.extract_types"),
    ]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "url": url,
        }
    )
    resolved = _resolve_Query_gremlin_engines(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="GremlinEngineType_READ",
        default_manager=GremlinEngine._default_manager,
        filterset_class=setup_filterset(GremlinEngineFilter),
        filter_args={"url": "url"},
    )


def q_analyzer(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[AnalyzerType, strawberry.lazy("config.graphql.extract_types")]):
    return get_node_from_global_id(info, id, only_type_name="AnalyzerType")


def _resolve_Query_analyzers(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:449

    Port of ExtractQueryMixin.resolve_analyzers
    """
    return BaseService.filter_visible(Analyzer, info.context.user, request=info.context)


def q_analyzers(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    id__contains: Annotated[
        strawberry.ID | None, strawberry.argument(name="id_Contains")
    ] = strawberry.UNSET,
    id: Annotated[
        strawberry.ID | None, strawberry.argument(name="id")
    ] = strawberry.UNSET,
    description__contains: Annotated[
        str | None, strawberry.argument(name="description_Contains")
    ] = strawberry.UNSET,
    disabled: Annotated[
        bool | None, strawberry.argument(name="disabled")
    ] = strawberry.UNSET,
    analyzer_id: Annotated[
        str | None, strawberry.argument(name="analyzerId")
    ] = strawberry.UNSET,
    hosted_by_gremlin_engine_id: Annotated[
        str | None, strawberry.argument(name="hostedByGremlinEngineId")
    ] = strawberry.UNSET,
    used_in_analysis_ids: Annotated[
        str | None, strawberry.argument(name="usedInAnalysisIds")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[AnalyzerTypeConnection, strawberry.lazy("config.graphql.extract_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "id__contains": id__contains,
            "id": id,
            "description__contains": description__contains,
            "disabled": disabled,
            "analyzer_id": analyzer_id,
            "hosted_by_gremlin_engine_id": hosted_by_gremlin_engine_id,
            "used_in_analysis_ids": used_in_analysis_ids,
        }
    )
    resolved = _resolve_Query_analyzers(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AnalyzerType",
        default_manager=Analyzer._default_manager,
        filterset_class=setup_filterset(AnalyzerFilter),
        filter_args={
            "id__contains": "id__contains",
            "id": "id",
            "description__contains": "description__contains",
            "disabled": "disabled",
            "analyzer_id": "analyzer_id",
            "hosted_by_gremlin_engine_id": "hosted_by_gremlin_engine_id",
            "used_in_analysis_ids": "used_in_analysis_ids",
        },
    )


def q_analysis(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]):
    return get_node_from_global_id(info, id, only_type_name="AnalysisType")


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
def _resolve_Query_analyses(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/extract_queries.py:471

    Port of ExtractQueryMixin.resolve_analyses
    """
    from opencontractserver.analyzer.services import AnalysisService

    corpus_id = kwargs.get("corpus_id")
    if corpus_id:
        corpus_django_pk = int(from_global_id(corpus_id)[1])
    else:
        corpus_django_pk = None

    return AnalysisService.get_visible_analyses(
        info.context.user, corpus_id=corpus_django_pk, context=info.context
    )


def q_analyses(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    analyzed_corpus__isnull: Annotated[
        bool | None, strawberry.argument(name="analyzedCorpus_Isnull")
    ] = strawberry.UNSET,
    analysis_started__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="analysisStarted_Gte")
    ] = strawberry.UNSET,
    analysis_started__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="analysisStarted_Lte")
    ] = strawberry.UNSET,
    analysis_completed__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="analysisCompleted_Gte")
    ] = strawberry.UNSET,
    analysis_completed__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="analysisCompleted_Lte")
    ] = strawberry.UNSET,
    status: Annotated[
        enums.AnalyzerAnalysisStatusChoices | None,
        strawberry.argument(name="status"),
    ] = strawberry.UNSET,
    analyzer__task_name__in: Annotated[
        list[str | None] | None, strawberry.argument(name="analyzer_TaskName_In")
    ] = strawberry.UNSET,
    received_callback_results: Annotated[
        bool | None, strawberry.argument(name="receivedCallbackResults")
    ] = strawberry.UNSET,
    analyzed_corpus_id: Annotated[
        str | None, strawberry.argument(name="analyzedCorpusId")
    ] = strawberry.UNSET,
    analyzed_document_id: Annotated[
        str | None, strawberry.argument(name="analyzedDocumentId")
    ] = strawberry.UNSET,
    search_text: Annotated[
        str | None, strawberry.argument(name="searchText")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[AnalysisTypeConnection, strawberry.lazy("config.graphql.extract_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "analyzed_corpus__isnull": analyzed_corpus__isnull,
            "analysis_started__gte": analysis_started__gte,
            "analysis_started__lte": analysis_started__lte,
            "analysis_completed__gte": analysis_completed__gte,
            "analysis_completed__lte": analysis_completed__lte,
            "status": status,
            "analyzer__task_name__in": analyzer__task_name__in,
            "received_callback_results": received_callback_results,
            "analyzed_corpus_id": analyzed_corpus_id,
            "analyzed_document_id": analyzed_document_id,
            "search_text": search_text,
        }
    )
    resolved = _resolve_Query_analyses(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AnalysisType",
        default_manager=Analysis._default_manager,
        filterset_class=setup_filterset(AnalysisFilter),
        filter_args={
            "analyzed_corpus__isnull": "analyzed_corpus__isnull",
            "analysis_started__gte": "analysis_started__gte",
            "analysis_started__lte": "analysis_started__lte",
            "analysis_completed__gte": "analysis_completed__gte",
            "analysis_completed__lte": "analysis_completed__lte",
            "status": "status",
            "analyzer__task_name__in": "analyzer__task_name__in",
            "received_callback_results": "received_callback_results",
            "analyzed_corpus_id": "analyzed_corpus_id",
            "analyzed_document_id": "analyzed_document_id",
            "search_text": "search_text",
        },
    )


QUERY_FIELDS = {
    "fieldset": strawberry.field(resolver=q_fieldset, name="fieldset"),
    "fieldsets": strawberry.field(resolver=q_fieldsets, name="fieldsets"),
    "column": strawberry.field(resolver=q_column, name="column"),
    "columns": strawberry.field(resolver=q_columns, name="columns"),
    "extract": strawberry.field(resolver=q_extract, name="extract"),
    "extracts": strawberry.field(resolver=q_extracts, name="extracts"),
    "compare_extracts": strawberry.field(
        resolver=q_compare_extracts,
        name="compareExtracts",
        description="Cell-level diff between two iterations of the same extract series.",
    ),
    "datacell": strawberry.field(resolver=q_datacell, name="datacell"),
    "datacells": strawberry.field(resolver=q_datacells, name="datacells"),
    "registered_extract_tasks": strawberry.field(
        resolver=q_registered_extract_tasks, name="registeredExtractTasks"
    ),
    "document_metadata_datacells": strawberry.field(
        resolver=q_document_metadata_datacells,
        name="documentMetadataDatacells",
        description="Get metadata datacells for a document in a corpus",
    ),
    "metadata_completion_status_v2": strawberry.field(
        resolver=q_metadata_completion_status_v2,
        name="metadataCompletionStatusV2",
        description="Get metadata completion status for a document using column/datacell system",
    ),
    "documents_metadata_datacells_batch": strawberry.field(
        resolver=q_documents_metadata_datacells_batch,
        name="documentsMetadataDatacellsBatch",
        description="Get metadata datacells for multiple documents in a single query (batch)",
    ),
    "gremlin_engine": strawberry.field(resolver=q_gremlin_engine, name="gremlinEngine"),
    "gremlin_engines": strawberry.field(
        resolver=q_gremlin_engines, name="gremlinEngines"
    ),
    "analyzer": strawberry.field(resolver=q_analyzer, name="analyzer"),
    "analyzers": strawberry.field(resolver=q_analyzers, name="analyzers"),
    "analysis": strawberry.field(resolver=q_analysis, name="analysis"),
    "analyses": strawberry.field(resolver=q_analyses, name="analyses"),
}
