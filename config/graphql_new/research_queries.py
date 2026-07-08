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
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums

from opencontractserver.research.models import ResearchReport


def q_research_report(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["ResearchReportType", strawberry.lazy("config.graphql_new.research_types")]]:
    return get_node_from_global_id(info, id, only_type_name="ResearchReportType")


def _resolve_Query_research_reports(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:50

    Port of ResearchQueryMixin.resolve_research_reports
    """
    raise NotImplementedError("_resolve_Query_research_reports not yet ported — see manifest")


def q_research_reports(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, status: Annotated[Optional[str], strawberry.argument(name="status")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["ResearchReportTypeConnection", strawberry.lazy("config.graphql_new.research_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "status": status, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_research_reports(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ResearchReportType", default_manager=ResearchReport._default_manager, )


def _resolve_Query_research_report_by_slug(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:84

    Port of ResearchQueryMixin.resolve_research_report_by_slug
    """
    raise NotImplementedError("_resolve_Query_research_report_by_slug not yet ported — see manifest")


def q_research_report_by_slug(info: strawberry.Info, slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET) -> Optional[Annotated["ResearchReportType", strawberry.lazy("config.graphql_new.research_types")]]:
    kwargs = strip_unset({"slug": slug})
    return _resolve_Query_research_report_by_slug(None, info, **kwargs)



QUERY_FIELDS = {
    "research_report": strawberry.field(resolver=q_research_report, name="researchReport"),
    "research_reports": strawberry.field(resolver=q_research_reports, name="researchReports"),
    "research_report_by_slug": strawberry.field(resolver=q_research_report_by_slug, name="researchReportBySlug", description='Fetch a single research report by its unique slug. The deep-research completion chat message links to /research/{slug}, so the frontend resolves that route through this field. Creator-only visibility (returns null for non-owners or unknown slugs — IDOR-safe).'),
}
