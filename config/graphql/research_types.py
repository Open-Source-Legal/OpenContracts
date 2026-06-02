"""GraphQL type for ``ResearchReport`` (deep-research jobs)."""

from typing import Any

import graphene
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType

from config.graphql.annotation_types import AnnotationType
from config.graphql.base import CountableConnection
from config.graphql.document_types import DocumentType
from opencontractserver.research.models import ResearchReport


class ResearchReportType(DjangoObjectType):
    """Deep-research job + final report.

    Permissions are intentionally **creator-only** in v1 — there is no
    sharing surface (no `is_public`, no `object_shared_with`), so we
    skip `AnnotatePermissionsForReadMixin` (which assumes guardian
    permission tables that ``ResearchReport`` does not allocate, and
    would silently swallow the resulting AttributeError as ``[]``).
    The custom ``my_permissions`` resolver below mirrors what the mixin
    would return for the creator's own row.
    """

    findings = GenericScalar()
    citations = GenericScalar()
    tool_call_log = GenericScalar()
    model_usage = GenericScalar()
    warnings = GenericScalar()

    duration_seconds = graphene.Float(
        description="Seconds between start and completion (null if not finished)."
    )

    my_permissions = graphene.List(
        graphene.String,
        description="Action verbs the calling user is allowed on this report.",
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

    def resolve_my_permissions(self, info) -> list[str]:
        """Return creator-only permissions; v1 has no sharing surface."""
        user = getattr(info.context, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return []
        # Scoped admin access (2026-05): superusers are computed like a normal
        # user — no synthetic full-permission grant. A report is visible (and
        # editable) only to its creator in v1.
        if self.creator_id == getattr(user, "id", None):
            # Creator sees their own report end-to-end; cancel routes
            # through the dedicated mutation, not a guardian grant.
            return [
                "read_researchreport",
                "update_researchreport",
                "remove_researchreport",
            ]
        return []

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
