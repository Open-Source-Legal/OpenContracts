"""GraphQL queries for deep-research reports."""

from typing import Any

import graphene
from graphene import relay
from graphene_django.fields import DjangoConnectionField
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.research_types import ResearchReportType
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


class ResearchQueryMixin:
    """Query fields for deep-research reports."""

    research_report = relay.Node.Field(ResearchReportType)

    @login_required
    def resolve_research_report(self, info, **kwargs) -> Any:
        django_pk = _decode_global_pk(kwargs["id"])
        if django_pk is None:
            return None
        return BaseService.get_or_none(
            ResearchReport, django_pk, info.context.user, request=info.context
        )

    research_reports = DjangoConnectionField(
        ResearchReportType,
        corpus_id=graphene.ID(required=False),
        status=graphene.String(required=False),
    )

    @login_required
    def resolve_research_reports(self, info, **kwargs) -> Any:
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

    research_report_by_slug = graphene.Field(
        ResearchReportType,
        slug=graphene.String(required=True),
        description=(
            "Fetch a single research report by its unique slug. The "
            "deep-research completion chat message links to /research/{slug}, "
            "so the frontend resolves that route through this field. "
            "Creator-only visibility (returns null for non-owners or unknown "
            "slugs — IDOR-safe)."
        ),
    )

    @login_required
    def resolve_research_report_by_slug(self, info, slug) -> Any:
        return (
            BaseService.filter_visible(
                ResearchReport, info.context.user, request=info.context
            )
            .filter(slug=slug)
            .first()
        )
