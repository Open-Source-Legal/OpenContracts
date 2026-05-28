"""GraphQL type for ``ResearchReport`` (deep-research jobs)."""

from typing import Any

import graphene
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType

from config.graphql.annotation_types import AnnotationType
from config.graphql.base import CountableConnection
from config.graphql.document_types import DocumentType
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.research.models import ResearchReport


class ResearchReportType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """Deep-research job + final report."""

    findings = GenericScalar()
    citations = GenericScalar()
    tool_call_log = GenericScalar()
    model_usage = GenericScalar()
    warnings = GenericScalar()

    duration_seconds = graphene.Float(
        description="Seconds between start and completion (null if not finished)."
    )

    full_source_annotation_list = graphene.List(
        AnnotationType,
        description="Annotations cited in the final report (creator-only in v1).",
    )
    full_source_document_list = graphene.List(
        DocumentType,
        description="Documents touched by the research run.",
    )

    def resolve_duration_seconds(self, info) -> Any:
        return self.duration_seconds

    def resolve_full_source_annotation_list(self, info) -> Any:
        return self.source_annotations.all()

    def resolve_full_source_document_list(self, info) -> Any:
        return self.source_documents.all()

    @classmethod
    def get_node(cls, info, id) -> Any:
        """Permission-checked node resolution."""
        from opencontractserver.shared.services.base import BaseService

        obj = BaseService.get_or_none(
            ResearchReport, int(id), info.context.user, request=info.context
        )
        return obj

    class Meta:
        model = ResearchReport
        interfaces = [relay.Node]
        connection_class = CountableConnection
