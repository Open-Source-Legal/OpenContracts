"""
GraphQL query mixin for corpus action and execution queries.
"""

import logging
from typing import Any

import graphene
from graphene_django.fields import DjangoConnectionField
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import (
    AgentActionResultType,
    CorpusActionExecutionType,
    CorpusActionTemplateType,
    CorpusActionTrailStatsType,
    CorpusActionType,
    DocumentCorpusActionsType,
)
from opencontractserver.corpuses.models import CorpusAction

logger = logging.getLogger(__name__)


class ActionQueryMixin:
    """Query fields and resolvers for corpus action and execution queries."""

    # CORPUS ACTION TEMPLATE RESOLVERS #####################################
    corpus_action_templates = DjangoConnectionField(
        CorpusActionTemplateType,
        is_active=graphene.Boolean(required=False),
    )

    @login_required
    def resolve_corpus_action_templates(self, info, **kwargs) -> Any:
        """Return available corpus action templates.

        Templates are system-level and read-only — any authenticated user
        can see active templates.
        """
        from opencontractserver.corpuses.models import CorpusActionTemplate

        queryset = CorpusActionTemplate.objects.all()

        is_active = kwargs.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        return queryset.order_by("sort_order", "name")

    # CORPUS ACTION RESOLVERS #####################################
    corpus_actions = DjangoConnectionField(
        CorpusActionType,
        corpus_id=graphene.ID(required=False),
        trigger=graphene.String(required=False),
        disabled=graphene.Boolean(required=False),
    )

    @login_required
    def resolve_corpus_actions(self, info, **kwargs) -> Any:
        """
        Resolver for corpus_actions that returns actions visible to the current user.
        Can be filtered by corpus_id, trigger type, and disabled status.
        """
        user = info.context.user
        queryset = CorpusAction.objects.visible_to_user(user)

        # Filter by corpus if provided
        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            queryset = queryset.filter(corpus_id=corpus_pk)

        # Filter by trigger type if provided
        trigger = kwargs.get("trigger")
        if trigger:
            queryset = queryset.filter(trigger=trigger)

        # Filter by disabled status if provided
        disabled = kwargs.get("disabled")
        if disabled is not None:
            queryset = queryset.filter(disabled=disabled)

        return queryset.order_by("-created")

    # AGENT ACTION RESULT RESOLVERS #####################################
    agent_action_results = DjangoConnectionField(
        AgentActionResultType,
        corpus_action_id=graphene.ID(required=False),
        document_id=graphene.ID(required=False),
        status=graphene.String(required=False),
    )

    @login_required
    def resolve_agent_action_results(self, info, **kwargs) -> Any:
        """
        Resolver for agent_action_results that returns results visible to the current user.
        Can be filtered by corpus_action_id, document_id, and status.
        """
        from opencontractserver.agents.models import AgentActionResult
        from opencontractserver.corpuses.models import CorpusAction

        user = info.context.user
        queryset = AgentActionResult.objects.visible_to_user(user)

        # Filter by corpus_action if provided (with access check)
        corpus_action_id = kwargs.get("corpus_action_id")
        if corpus_action_id:
            corpus_action_pk = from_global_id(corpus_action_id)[1]
            # Defense-in-depth: verify user has access to this corpus action
            if (
                not CorpusAction.objects.visible_to_user(user)
                .filter(pk=corpus_action_pk)
                .exists()
            ):
                return queryset.none()
            queryset = queryset.filter(corpus_action_id=corpus_action_pk)

        # Filter by document if provided
        document_id = kwargs.get("document_id")
        if document_id:
            document_pk = from_global_id(document_id)[1]
            queryset = queryset.filter(document_id=document_pk)

        # Filter by status if provided
        status = kwargs.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by("-created")

    # CORPUS ACTION EXECUTION QUERIES ##############################################
    corpus_action_executions = DjangoConnectionField(
        CorpusActionExecutionType,
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=False),
        corpus_action_id=graphene.ID(required=False),
        status=graphene.String(required=False),
        action_type=graphene.String(required=False),
        since=graphene.DateTime(required=False),
    )

    @login_required
    def resolve_corpus_action_executions(self, info, **kwargs) -> Any:
        """
        Resolver for corpus_action_executions that returns executions visible to
        the current user.

        Can be filtered by corpus_id, document_id, corpus_action_id, status,
        action_type, and since (datetime).
        """
        from opencontractserver.corpuses.models import Corpus, CorpusActionExecution
        from opencontractserver.documents.models import Document

        user = info.context.user
        queryset = CorpusActionExecution.objects.visible_to_user(user)

        # Filter by corpus if provided (with access check)
        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            corpus_pk = int(from_global_id(corpus_id)[1])
            # Defense-in-depth: verify user has access to this corpus
            if not Corpus.objects.visible_to_user(user).filter(pk=corpus_pk).exists():
                return queryset.none()
            queryset = queryset.for_corpus(corpus_pk)

        # Filter by document if provided (with access check)
        document_id = kwargs.get("document_id")
        if document_id:
            document_pk = int(from_global_id(document_id)[1])
            # Defense-in-depth: verify user has access to this document
            if (
                not Document.objects.visible_to_user(user)
                .filter(pk=document_pk)
                .exists()
            ):
                return queryset.none()
            queryset = queryset.for_document(document_pk)

        # Filter by corpus_action if provided (with access check)
        corpus_action_id = kwargs.get("corpus_action_id")
        if corpus_action_id:
            from opencontractserver.corpuses.models import CorpusAction

            corpus_action_pk = from_global_id(corpus_action_id)[1]
            # Defense-in-depth: verify user has access to this corpus action
            if (
                not CorpusAction.objects.visible_to_user(user)
                .filter(pk=corpus_action_pk)
                .exists()
            ):
                return queryset.none()
            queryset = queryset.filter(corpus_action_id=corpus_action_pk)

        # Filter by status if provided
        status = kwargs.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # Filter by action_type if provided
        action_type = kwargs.get("action_type")
        if action_type:
            queryset = queryset.by_type(action_type)

        # Filter by since datetime if provided
        since = kwargs.get("since")
        if since:
            queryset = queryset.filter(queued_at__gte=since)

        return queryset.select_related("corpus_action", "document", "corpus").order_by(
            "-queued_at"
        )

    # CORPUS ACTION TRAIL STATS #####################################
    corpus_action_trail_stats = graphene.Field(
        CorpusActionTrailStatsType,
        corpus_id=graphene.ID(required=True),
        since=graphene.DateTime(required=False),
    )

    @login_required
    def resolve_corpus_action_trail_stats(self, info, corpus_id, since=None) -> Any:
        """
        Resolver for corpus_action_trail_stats that returns aggregated statistics
        for corpus action executions.
        """
        from django.db.models import Avg, Count, F, Q

        from opencontractserver.corpuses.models import Corpus, CorpusActionExecution

        user = info.context.user
        corpus_pk = int(from_global_id(corpus_id)[1])

        # Defense-in-depth: verify user has access to this corpus
        if not Corpus.objects.visible_to_user(user).filter(pk=corpus_pk).exists():
            return CorpusActionTrailStatsType(
                total_executions=0,
                completed=0,
                failed=0,
                running=0,
                queued=0,
                skipped=0,
                avg_duration_seconds=None,
                fieldset_count=0,
                analyzer_count=0,
                agent_count=0,
            )

        queryset = CorpusActionExecution.objects.visible_to_user(user)
        queryset = queryset.for_corpus(corpus_pk)

        if since:
            queryset = queryset.filter(queued_at__gte=since)

        stats = queryset.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            failed=Count("id", filter=Q(status="failed")),
            running=Count("id", filter=Q(status="running")),
            queued=Count("id", filter=Q(status="queued")),
            skipped=Count("id", filter=Q(status="skipped")),
            avg_duration=Avg(
                F("completed_at") - F("started_at"),
                filter=Q(completed_at__isnull=False, started_at__isnull=False),
            ),
            fieldset_count=Count("id", filter=Q(action_type="fieldset")),
            analyzer_count=Count("id", filter=Q(action_type="analyzer")),
            agent_count=Count("id", filter=Q(action_type="agent")),
        )

        return CorpusActionTrailStatsType(
            total_executions=stats["total"],
            completed=stats["completed"],
            failed=stats["failed"],
            running=stats["running"],
            queued=stats["queued"],
            skipped=stats["skipped"],
            avg_duration_seconds=(
                stats["avg_duration"].total_seconds() if stats["avg_duration"] else None
            ),
            fieldset_count=stats["fieldset_count"],
            analyzer_count=stats["analyzer_count"],
            agent_count=stats["agent_count"],
        )

    # DOCUMENT CORPUS ACTIONS RESOLVER #####################################
    document_corpus_actions = graphene.Field(
        DocumentCorpusActionsType,
        document_id=graphene.ID(required=True),
        corpus_id=graphene.ID(required=False),
    )

    def resolve_document_corpus_actions(self, info, document_id, corpus_id=None) -> Any:
        """
        Resolve document actions (corpus actions, extracts, analysis rows) with proper
        permission filtering.

        SECURITY: Uses DocumentActionsQueryOptimizer which follows the least-privilege model:
        - Document permissions are primary
        - Corpus permissions are secondary
        - Effective permission = MIN(document_permission, corpus_permission)

        This prevents unauthorized access to document-related data.
        """
        from opencontractserver.documents.query_optimizer import (
            DocumentActionsQueryOptimizer,
        )

        user = info.context.user

        # Guard against empty strings - from_global_id('') returns ('', '')
        document_pk = from_global_id(document_id)[1] if document_id else None
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None

        # Validate document_id is required and not empty
        if not document_pk:
            raise GraphQLError("documentId is required and must be a valid ID")

        # Use centralized permission-aware optimizer
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=user,
            document_id=int(document_pk),
            corpus_id=int(corpus_pk) if corpus_pk else None,
        )

        return DocumentCorpusActionsType(
            corpus_actions=actions["corpus_actions"],
            extracts=actions["extracts"],
            analysis_rows=actions["analysis_rows"],
        )
