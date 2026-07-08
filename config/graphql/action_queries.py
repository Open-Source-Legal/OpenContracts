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
import logging
from typing import Annotated

import strawberry
from graphql import GraphQLError
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.relay import (
    resolve_django_connection,
)
from opencontractserver.agents.models import AgentActionResult
from opencontractserver.corpuses.models import (
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTemplate,
)
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


@login_required
def _resolve_Query_corpus_action_templates(root, info, **kwargs):
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


def q_corpus_action_templates(
    info: strawberry.Info,
    is_active: Annotated[
        bool | None, strawberry.argument(name="isActive")
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
        CorpusActionTemplateTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]
):
    kwargs = strip_unset(
        {
            "is_active": is_active,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_corpus_action_templates(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="CorpusActionTemplateType",
        default_manager=CorpusActionTemplate._default_manager,
    )


@login_required
def _resolve_Query_corpus_actions(root, info, **kwargs):
    """
    Resolver for corpus_actions that returns actions visible to the current user.
    Can be filtered by corpus_id, trigger type, and disabled status.
    """
    user = info.context.user
    queryset = BaseService.filter_visible(CorpusAction, user, request=info.context)

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


def q_corpus_actions(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    trigger: Annotated[
        str | None, strawberry.argument(name="trigger")
    ] = strawberry.UNSET,
    disabled: Annotated[
        bool | None, strawberry.argument(name="disabled")
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
    Annotated[CorpusActionTypeConnection, strawberry.lazy("config.graphql.agent_types")]
):
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "trigger": trigger,
            "disabled": disabled,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_corpus_actions(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="CorpusActionType",
        default_manager=CorpusAction._default_manager,
    )


@login_required
def _resolve_Query_agent_action_results(root, info, **kwargs):
    """
    Resolver for agent_action_results that returns results visible to the current user.
    Can be filtered by corpus_action_id, document_id, and status.
    """
    from opencontractserver.agents.services import AgentActionResultService

    user = info.context.user

    corpus_action_id = kwargs.get("corpus_action_id")
    corpus_action_pk = (
        int(from_global_id(corpus_action_id)[1]) if corpus_action_id else None
    )
    document_id = kwargs.get("document_id")
    document_pk = int(from_global_id(document_id)[1]) if document_id else None
    status = kwargs.get("status")

    return AgentActionResultService.list_visible_results(
        user,
        corpus_action_id=corpus_action_pk,
        document_id=document_pk,
        status=status,
        request=info.context,
    )


def q_agent_action_results(
    info: strawberry.Info,
    corpus_action_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusActionId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="documentId")
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
        AgentActionResultTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]
):
    kwargs = strip_unset(
        {
            "corpus_action_id": corpus_action_id,
            "document_id": document_id,
            "status": status,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_agent_action_results(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AgentActionResultType",
        default_manager=AgentActionResult._default_manager,
    )


@login_required
def _resolve_Query_corpus_action_executions(root, info, **kwargs):
    """
    Resolver for corpus_action_executions that returns executions visible to
    the current user.

    Can be filtered by corpus_id, document_id, corpus_action_id, status,
    action_type, and since (datetime).
    """
    from opencontractserver.corpuses.models import Corpus, CorpusActionExecution
    from opencontractserver.documents.models import Document

    user = info.context.user
    queryset = BaseService.filter_visible(
        CorpusActionExecution, user, request=info.context
    )

    # Filter by corpus if provided (with access check)
    corpus_id = kwargs.get("corpus_id")
    if corpus_id:
        corpus_pk = int(from_global_id(corpus_id)[1])
        # Defense-in-depth: verify user has access to this corpus
        if (
            not BaseService.filter_visible(Corpus, user, request=info.context)
            .filter(pk=corpus_pk)
            .exists()
        ):
            return queryset.none()
        queryset = queryset.for_corpus(corpus_pk)

    # Filter by document if provided (with access check)
    document_id = kwargs.get("document_id")
    if document_id:
        document_pk = int(from_global_id(document_id)[1])
        # Defense-in-depth: verify user has access to this document
        if (
            not BaseService.filter_visible(Document, user, request=info.context)
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
            not BaseService.filter_visible(CorpusAction, user, request=info.context)
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


def q_corpus_action_executions(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    corpus_action_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusActionId")
    ] = strawberry.UNSET,
    status: Annotated[
        str | None, strawberry.argument(name="status")
    ] = strawberry.UNSET,
    action_type: Annotated[
        str | None, strawberry.argument(name="actionType")
    ] = strawberry.UNSET,
    since: Annotated[
        datetime.datetime | None, strawberry.argument(name="since")
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
        CorpusActionExecutionTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]
):
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "document_id": document_id,
            "corpus_action_id": corpus_action_id,
            "status": status,
            "action_type": action_type,
            "since": since,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_corpus_action_executions(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="CorpusActionExecutionType",
        default_manager=CorpusActionExecution._default_manager,
    )


@login_required
def _resolve_Query_corpus_action_trail_stats(root, info, corpus_id, since=None):
    """
    Resolver for corpus_action_trail_stats that returns aggregated statistics
    for corpus action executions.
    """
    from django.db.models import Avg, Count, F, Q

    from config.graphql.agent_types import CorpusActionTrailStatsType
    from opencontractserver.corpuses.models import Corpus, CorpusActionExecution

    user = info.context.user
    corpus_pk = int(from_global_id(corpus_id)[1])

    # Defense-in-depth: verify user has access to this corpus
    if (
        not BaseService.filter_visible(Corpus, user, request=info.context)
        .filter(pk=corpus_pk)
        .exists()
    ):
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

    queryset = BaseService.filter_visible(
        CorpusActionExecution, user, request=info.context
    )
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


def q_corpus_action_trail_stats(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    since: Annotated[
        datetime.datetime | None, strawberry.argument(name="since")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[CorpusActionTrailStatsType, strawberry.lazy("config.graphql.agent_types")]
):
    kwargs = strip_unset({"corpus_id": corpus_id, "since": since})
    return _resolve_Query_corpus_action_trail_stats(None, info, **kwargs)


def _resolve_Query_document_corpus_actions(root, info, document_id, corpus_id=None):
    """
    Resolve document actions (corpus actions, extracts, analysis rows) with proper
    permission filtering.

    SECURITY: Uses DocumentActionsService which follows the least-privilege model:
    - Document permissions are primary
    - Corpus permissions are secondary
    - Effective permission = MIN(document_permission, corpus_permission)

    This prevents unauthorized access to document-related data.
    """
    from config.graphql.document_types import DocumentCorpusActionsType
    from opencontractserver.documents.services import DocumentActionsService

    user = info.context.user

    # Guard against empty strings - from_global_id('') returns ('', '')
    document_pk = from_global_id(document_id)[1] if document_id else None
    corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None

    # Validate document_id is required and not empty
    if not document_pk:
        raise GraphQLError("documentId is required and must be a valid ID")

    # Use centralized permission-aware service
    actions = DocumentActionsService.get_document_actions(
        user=user,
        document_id=int(document_pk),
        corpus_id=int(corpus_pk) if corpus_pk else None,
        request=info.context,
    )

    return DocumentCorpusActionsType(
        corpus_actions=actions["corpus_actions"],
        extracts=actions["extracts"],
        analysis_rows=actions["analysis_rows"],
    )


def q_document_corpus_actions(
    info: strawberry.Info,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        DocumentCorpusActionsType, strawberry.lazy("config.graphql.document_types")
    ]
):
    kwargs = strip_unset({"document_id": document_id, "corpus_id": corpus_id})
    return _resolve_Query_document_corpus_actions(None, info, **kwargs)


QUERY_FIELDS = {
    "corpus_action_templates": strawberry.field(
        resolver=q_corpus_action_templates, name="corpusActionTemplates"
    ),
    "corpus_actions": strawberry.field(resolver=q_corpus_actions, name="corpusActions"),
    "agent_action_results": strawberry.field(
        resolver=q_agent_action_results, name="agentActionResults"
    ),
    "corpus_action_executions": strawberry.field(
        resolver=q_corpus_action_executions, name="corpusActionExecutions"
    ),
    "corpus_action_trail_stats": strawberry.field(
        resolver=q_corpus_action_trail_stats, name="corpusActionTrailStats"
    ),
    "document_corpus_actions": strawberry.field(
        resolver=q_document_corpus_actions, name="documentCorpusActions"
    ),
}
