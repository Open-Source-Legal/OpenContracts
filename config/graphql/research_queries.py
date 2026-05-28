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


class ResearchQueryMixin:
    """Query fields for deep-research reports."""

    research_report = relay.Node.Field(ResearchReportType)

    def resolve_research_report(self, info, **kwargs) -> Any:
        django_pk = int(from_global_id(kwargs["id"])[1])
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
            qs = qs.filter(corpus_id=int(from_global_id(corpus_id)[1]))
        status = kwargs.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-created")
