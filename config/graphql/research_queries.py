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

from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.relay import (
    get_node_from_global_id,
    resolve_django_connection,
)
from opencontractserver.research.models import ResearchReport
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import JobStatus


def _decode_global_pk(global_id: str) -> int | None:
    """Decode a relay global id to its integer pk, or ``None`` if malformed.

    Mirrors ``search_queries.py``'s defensive pattern so a hand-crafted /
    base64-garbage id returns the IDOR-safe "not found" branch instead of
    surfacing a 500.
    """
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, UnicodeDecodeError, IndexError):
        return None


def q_research_report(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[ResearchReportType, strawberry.lazy("config.graphql.research_types")]
):
    return get_node_from_global_id(info, id, only_type_name="ResearchReportType")


@login_required
def _resolve_Query_research_reports(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:50

    Port of ResearchQueryMixin.resolve_research_reports
    """
    qs = BaseService.filter_visible(
        ResearchReport, info.context.user, request=info.context
    ).select_related("corpus", "creator", "conversation")
    corpus_id = kwargs.get("corpus_id")
    if corpus_id:
        corpus_pk = _decode_global_pk(corpus_id)
        if corpus_pk is None:
            return qs.none()
        qs = qs.filter(corpus_id=corpus_pk)
    status = kwargs.get("status")
    if status:
        # Reject unknown status values up front so the API surfaces
        # bad input as ``[]`` deterministically (instead of silently
        # for some inputs and a 500 for others).
        valid_statuses = {choice[0] for choice in JobStatus.choices()}
        if status not in valid_statuses:
            return qs.none()
        qs = qs.filter(status=status)
    return qs.order_by("-created")


def q_research_reports(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    status: Annotated[
        str | None, strawberry.argument(name="status")
    ] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
) -> None | (
    Annotated[
        ResearchReportTypeConnection, strawberry.lazy("config.graphql.research_types")
    ]
):
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "status": status,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_research_reports(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="ResearchReportType",
        default_manager=ResearchReport._default_manager,
    )


@login_required
def _resolve_Query_research_report_by_slug(root, info, slug, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:84

    Port of ResearchQueryMixin.resolve_research_report_by_slug
    """
    return (
        BaseService.filter_visible(
            ResearchReport, info.context.user, request=info.context
        )
        .filter(slug=slug)
        .first()
    )


def q_research_report_by_slug(
    info: strawberry.Info,
    slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET,
) -> None | (
    Annotated[ResearchReportType, strawberry.lazy("config.graphql.research_types")]
):
    kwargs = strip_unset({"slug": slug})
    return _resolve_Query_research_report_by_slug(None, info, **kwargs)


QUERY_FIELDS = {
    "research_report": strawberry.field(
        resolver=q_research_report, name="researchReport"
    ),
    "research_reports": strawberry.field(
        resolver=q_research_reports, name="researchReports"
    ),
    "research_report_by_slug": strawberry.field(
        resolver=q_research_report_by_slug,
        name="researchReportBySlug",
        description="Fetch a single research report by its unique slug. The deep-research completion chat message links to /research/{slug}, so the frontend resolves that route through this field. Creator-only visibility (returns null for non-owners or unknown slugs — IDOR-safe).",
    ),
}
