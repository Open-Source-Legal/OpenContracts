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
from typing import Annotated, Any, cast

import strawberry
from django.core.cache import cache
from django.db.models import Q
from graphql import GraphQLError
from graphql_relay import from_global_id

from config.graphql import enums
from config.graphql._util import strip_unset
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.relay import (
    get_node_from_global_id,
    resolve_django_connection,
)
from config.graphql.filters import (
    AgentConfigurationFilter,
    BadgeFilter,
    UserBadgeFilter,
)
from config.graphql.social_types import (
    BadgeDistributionType,
    CommunityStatsType,
    CriteriaFieldType,
    CriteriaTypeDefinitionType,
    LeaderboardEntryType,
    LeaderboardType,
)
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.constants.community_stats import COMMUNITY_STATS_CACHE_TTL
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.notifications.models import Notification
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


def _resolve_Query_badges(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:57

    Port of SocialQueryMixin.resolve_badges

    Resolve badges visible to the user.
    """
    return BaseService.filter_visible(
        Badge, info.context.user, request=info.context
    ).select_related("creator", "corpus")


def q_badges(
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
    badge_type: Annotated[
        enums.BadgesBadgeBadgeTypeChoices | None,
        strawberry.argument(name="badgeType"),
    ] = strawberry.UNSET,
    is_auto_awarded: Annotated[
        bool | None, strawberry.argument(name="isAutoAwarded")
    ] = strawberry.UNSET,
    name__contains: Annotated[
        str | None, strawberry.argument(name="name_Contains")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    corpus_id: Annotated[
        str | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[BadgeTypeConnection, strawberry.lazy("config.graphql.social_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "badge_type": badge_type,
            "is_auto_awarded": is_auto_awarded,
            "name__contains": name__contains,
            "name": name,
            "corpus_id": corpus_id,
        }
    )
    resolved = _resolve_Query_badges(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="BadgeType",
        default_manager=Badge._default_manager,
        filterset_class=setup_filterset(BadgeFilter),
        filter_args={
            "badge_type": "badge_type",
            "is_auto_awarded": "is_auto_awarded",
            "name__contains": "name__contains",
            "name": "name",
            "corpus_id": "corpus_id",
        },
    )


def q_badge(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> Annotated[BadgeType, strawberry.lazy("config.graphql.social_types")] | None:
    return get_node_from_global_id(info, id, only_type_name="BadgeType")


def _resolve_Query_user_badges(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:75

    Port of SocialQueryMixin.resolve_user_badges

    Resolve user badge awards with profile privacy filtering.

    SECURITY: Badge visibility follows the recipient's profile visibility.
    Badges are visible if:
    - Recipient's profile is public
    - Requesting user shares corpus membership with recipient (> READ permission)
    - It's the requesting user's own badges
    - For corpus-specific badges: user has access to that corpus
    """
    from opencontractserver.badges.services import BadgeService

    return BadgeService.get_visible_user_badges(info.context.user, request=info.context)


def q_user_badges(
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
    awarded_at__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="awardedAt_Gte")
    ] = strawberry.UNSET,
    awarded_at__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="awardedAt_Lte")
    ] = strawberry.UNSET,
    user_id: Annotated[
        str | None, strawberry.argument(name="userId")
    ] = strawberry.UNSET,
    badge_id: Annotated[
        str | None, strawberry.argument(name="badgeId")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        str | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[UserBadgeTypeConnection, strawberry.lazy("config.graphql.social_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "awarded_at__gte": awarded_at__gte,
            "awarded_at__lte": awarded_at__lte,
            "user_id": user_id,
            "badge_id": badge_id,
            "corpus_id": corpus_id,
        }
    )
    resolved = _resolve_Query_user_badges(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="UserBadgeType",
        default_manager=UserBadge._default_manager,
        filterset_class=setup_filterset(UserBadgeFilter),
        filter_args={
            "awarded_at__gte": "awarded_at__gte",
            "awarded_at__lte": "awarded_at__lte",
            "user_id": "user_id",
            "badge_id": "badge_id",
            "corpus_id": "corpus_id",
        },
    )


def q_user_badge(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[UserBadgeType, strawberry.lazy("config.graphql.social_types")]):
    return get_node_from_global_id(info, id, only_type_name="UserBadgeType")


def _resolve_Query_badge_criteria_types(root, info, scope=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:122

    Port of SocialQueryMixin.resolve_badge_criteria_types

    Resolve available badge criteria types from the registry.

    Args:
        info: GraphQL resolve info
        scope: Optional scope filter ('global', 'corpus', or 'both')

    Returns:
        List of criteria type definitions with their field schemas
    """
    # Get criteria types from registry
    if scope:
        criteria_types = BadgeCriteriaRegistry.for_scope(scope)
    else:
        criteria_types = BadgeCriteriaRegistry.all()

    # Convert dataclass instances to GraphQL type instances (graphene
    # accepted plain dicts here; strawberry's default resolver is
    # getattr-based, so construct the strawberry types instead).
    return [
        CriteriaTypeDefinitionType(
            type_id=ct.type_id,
            name=ct.name,
            description=ct.description,
            scope=ct.scope,
            fields=[
                CriteriaFieldType(
                    name=f.name,
                    label=f.label,
                    field_type=f.field_type,
                    required=f.required,
                    description=f.description,
                    min_value=f.min_value,
                    max_value=f.max_value,
                    allowed_values=f.allowed_values,
                )
                for f in ct.fields
            ],
            implemented=ct.implemented,
        )
        for ct in criteria_types
    ]


def q_badge_criteria_types(
    info: strawberry.Info,
    scope: Annotated[
        str | None,
        strawberry.argument(
            name="scope", description="Filter by scope: 'global', 'corpus', or 'both'"
        ),
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (
            Annotated[
                CriteriaTypeDefinitionType,
                strawberry.lazy("config.graphql.social_types"),
            ]
        )
    ]
):
    kwargs = strip_unset({"scope": scope})
    return _resolve_Query_badge_criteria_types(None, info, **kwargs)


def _resolve_Query_agents(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:174

    Port of SocialQueryMixin.resolve_agents

    Resolve agent configurations visible to the user.
    """
    from opencontractserver.agents.services import AgentConfigurationService

    return AgentConfigurationService.list_visible_agents(
        info.context.user, request=info.context
    )


def q_agents(
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
    scope: Annotated[
        enums.AgentsAgentConfigurationScopeChoices | None,
        strawberry.argument(name="scope"),
    ] = strawberry.UNSET,
    is_active: Annotated[
        bool | None, strawberry.argument(name="isActive")
    ] = strawberry.UNSET,
    name__contains: Annotated[
        str | None, strawberry.argument(name="name_Contains")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    corpus_id: Annotated[
        str | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        AgentConfigurationTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "scope": scope,
            "is_active": is_active,
            "name__contains": name__contains,
            "name": name,
            "corpus_id": corpus_id,
        }
    )
    resolved = _resolve_Query_agents(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AgentConfigurationType",
        default_manager=AgentConfiguration._default_manager,
        filterset_class=setup_filterset(AgentConfigurationFilter),
        filter_args={
            "scope": "scope",
            "is_active": "is_active",
            "name__contains": "name__contains",
            "name": "name",
            "corpus_id": "corpus_id",
        },
    )


def _resolve_Query_agent_configurations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:182

    Port of SocialQueryMixin.resolve_agent_configurations

    Alias for resolve_agents - frontend compatibility.
    """
    from opencontractserver.agents.services import AgentConfigurationService

    return AgentConfigurationService.list_visible_agents(
        info.context.user, request=info.context
    )


def q_agent_configurations(
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
    scope: Annotated[
        enums.AgentsAgentConfigurationScopeChoices | None,
        strawberry.argument(name="scope"),
    ] = strawberry.UNSET,
    is_active: Annotated[
        bool | None, strawberry.argument(name="isActive")
    ] = strawberry.UNSET,
    name__contains: Annotated[
        str | None, strawberry.argument(name="name_Contains")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    corpus_id: Annotated[
        str | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        AgentConfigurationTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "scope": scope,
            "is_active": is_active,
            "name__contains": name__contains,
            "name": name,
            "corpus_id": corpus_id,
        }
    )
    resolved = _resolve_Query_agent_configurations(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AgentConfigurationType",
        default_manager=AgentConfiguration._default_manager,
        filterset_class=setup_filterset(AgentConfigurationFilter),
        filter_args={
            "scope": "scope",
            "is_active": "is_active",
            "name__contains": "name__contains",
            "name": "name",
            "corpus_id": "corpus_id",
        },
    )


def q_agent(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[AgentConfigurationType, strawberry.lazy("config.graphql.agent_types")]
):
    return get_node_from_global_id(info, id, only_type_name="AgentConfigurationType")


def _resolve_Query_available_tools(root, info, category=None, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:221

    Port of SocialQueryMixin.resolve_available_tools

    Resolve available tools for agent configuration.

    This returns the list of tools that can be assigned to agents,
    optionally filtered by category.
    """
    from opencontractserver.llms.tools.tool_registry import (
        get_all_tools,
        get_tools_by_category,
    )

    if category:
        tools = get_tools_by_category(category)
    else:
        tools = get_all_tools()

    # The registry returns camelCase dicts (graphene resolved those via its
    # dict-aware default resolver); strawberry's default resolver is
    # getattr-based, so construct the strawberry types. The type's python
    # field names ARE the camelCase dict keys (``requiresCorpus`` etc.);
    # the dict's ``requiresWritePermission`` key has no GraphQL field and
    # is dropped, exactly as graphene ignored it.
    from config.graphql.agent_types import AvailableToolType, ToolParameterType

    return [
        AvailableToolType(
            name=tool["name"],
            description=tool["description"],
            category=tool["category"],
            requiresCorpus=tool["requiresCorpus"],
            requiresApproval=tool["requiresApproval"],
            parameters=[
                ToolParameterType(
                    name=p["name"],
                    description=p["description"],
                    required=p["required"],
                )
                for p in tool["parameters"]
            ],
        )
        for tool in tools
    ]


def q_available_tools(
    info: strawberry.Info,
    category: Annotated[
        str | None,
        strawberry.argument(
            name="category",
            description="Filter by tool category (search, document, corpus, notes, annotations, coordination)",
        ),
    ] = strawberry.UNSET,
) -> None | (
    list[Annotated[AvailableToolType, strawberry.lazy("config.graphql.agent_types")]]
):
    kwargs = strip_unset({"category": category})
    return _resolve_Query_available_tools(None, info, **kwargs)


def _resolve_Query_available_tool_categories(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:240

    Port of SocialQueryMixin.resolve_available_tool_categories

    Resolve all available tool categories.
    """
    from opencontractserver.llms.tools.tool_registry import ToolCategory

    return [cat.value for cat in ToolCategory]


def q_available_tool_categories(info: strawberry.Info) -> list[str] | None:
    kwargs = strip_unset({})
    return _resolve_Query_available_tool_categories(None, info, **kwargs)


def _resolve_Query_notifications(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:257

    Port of SocialQueryMixin.resolve_notifications

    Resolve notifications for the current user.

    Filters notifications to only show those belonging to the current user.
    Supports filtering by is_read and notification_type via DjangoFilterConnectionField.
    """
    from opencontractserver.notifications.services import NotificationService

    return NotificationService.list_for_user(info.context.user, request=info.context)


def q_notifications(
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
    is_read: Annotated[
        bool | None, strawberry.argument(name="isRead")
    ] = strawberry.UNSET,
    notification_type: Annotated[
        enums.NotificationsNotificationNotificationTypeChoices | None,
        strawberry.argument(name="notificationType"),
    ] = strawberry.UNSET,
    created_at__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="createdAt_Lte")
    ] = strawberry.UNSET,
    created_at__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="createdAt_Gte")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        NotificationTypeConnection, strawberry.lazy("config.graphql.social_types")
    ]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "is_read": is_read,
            "notification_type": notification_type,
            "created_at__lte": created_at__lte,
            "created_at__gte": created_at__gte,
        }
    )
    resolved = _resolve_Query_notifications(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="NotificationType",
        default_manager=Notification._default_manager,
        filterset_class=filterset_factory(
            Notification,
            fields={
                "is_read": ["exact"],
                "notification_type": ["exact"],
                "created_at": ["lte", "gte"],
            },
        ),
        filter_args={
            "is_read": "is_read",
            "notification_type": "notification_type",
            "created_at__lte": "created_at__lte",
            "created_at__gte": "created_at__gte",
        },
    )


def q_notification(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[NotificationType, strawberry.lazy("config.graphql.social_types")]
):
    return get_node_from_global_id(info, id, only_type_name="NotificationType")


def _resolve_Query_unread_notification_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:289

    Port of SocialQueryMixin.resolve_unread_notification_count

    Get count of unread notifications for the current user.
    """
    from opencontractserver.notifications.services import NotificationService

    return NotificationService.unread_count(info.context.user, request=info.context)


def q_unread_notification_count(info: strawberry.Info) -> int | None:
    kwargs = strip_unset({})
    return _resolve_Query_unread_notification_count(None, info, **kwargs)


def _resolve_Query_corpus_leaderboard(root, info, corpus_id, limit=10):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:308

    Port of SocialQueryMixin.resolve_corpus_leaderboard

    Get top contributors for a corpus by reputation.

    Returns users ordered by corpus-specific reputation score.
    Requires read access to the corpus.

    Epic: #565 - Corpus Engagement Metrics & Analytics
    Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
    """
    from opencontractserver.conversations.models import UserReputation

    try:
        # Get corpus PK from global ID
        _, corpus_pk = from_global_id(corpus_id)

        # Check if user has access to this corpus.
        if (
            BaseService.get_or_none(
                Corpus, corpus_pk, info.context.user, request=info.context
            )
            is None
        ):
            raise Corpus.DoesNotExist

        # Get top users by reputation for this corpus
        # Prefetch user badges to avoid N+1 queries
        top_reputations = (
            UserReputation.objects.filter(corpus_id=corpus_pk)
            .select_related("user")
            .prefetch_related("user__badges__badge")
            .order_by("-reputation_score")[:limit]
        )

        # Return user objects (badges are already prefetched)
        return [rep.user for rep in top_reputations]

    except Corpus.DoesNotExist:
        raise GraphQLError("Corpus not found or access denied")
    except Exception as e:
        logger.error(f"Error resolving corpus leaderboard: {e}")
        return []


def q_corpus_leaderboard(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = 10,
) -> None | (
    list[Annotated[UserType, strawberry.lazy("config.graphql.user_types")] | None]
):
    kwargs = strip_unset({"corpus_id": corpus_id, "limit": limit})
    return _resolve_Query_corpus_leaderboard(None, info, **kwargs)


def _resolve_Query_global_leaderboard(root, info, limit=10):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:351

    Port of SocialQueryMixin.resolve_global_leaderboard

    Get top contributors globally by reputation.

    Returns users ordered by global reputation score.
    Attaches _reputation_global to each user to avoid N+1 queries
    when resolving reputationGlobal on UserType.

    Epic: #565 - Corpus Engagement Metrics & Analytics
    Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
    """
    from opencontractserver.conversations.models import UserReputation

    # Get top users by global reputation (corpus__isnull=True)
    # Prefetch user badges to avoid N+1 queries when frontend requests userBadges
    top_reputations = (
        UserReputation.objects.filter(corpus__isnull=True)
        .select_related("user")
        .prefetch_related("user__badges__badge")
        .order_by("-reputation_score")[:limit]
    )

    # Attach reputation score to user objects to avoid N+1 queries
    users = []
    for rep in top_reputations:
        # Dynamic attribute consumed downstream by the userReputation resolver.
        setattr(rep.user, "_reputation_global", rep.reputation_score)
        users.append(rep.user)
    return users


def q_global_leaderboard(
    info: strawberry.Info,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = 10,
) -> None | (
    list[Annotated[UserType, strawberry.lazy("config.graphql.user_types")] | None]
):
    kwargs = strip_unset({"limit": limit})
    return _resolve_Query_global_leaderboard(None, info, **kwargs)


def _resolve_Query_leaderboard(
    root, info, metric, scope="all_time", corpus_id=None, limit=25
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:396

    Port of SocialQueryMixin.resolve_leaderboard

    Get leaderboard for a specific metric and scope.

    Issue: #613 - Create leaderboard and community stats dashboard
    Epic: #572 - Social Features Epic

    Args:
        metric: The metric to rank by (BADGES, MESSAGES, THREADS, ANNOTATIONS, REPUTATION)
        scope: Time period (ALL_TIME, MONTHLY, WEEKLY)
        corpus_id: Optional corpus ID for corpus-specific leaderboards
        limit: Maximum number of entries to return (default 25)

    Returns:
        LeaderboardType with ranked entries
    """
    from datetime import timedelta

    from django.contrib.auth import get_user_model
    from django.db.models import Count
    from django.utils import timezone

    from opencontractserver.annotations.models import Annotation

    User = get_user_model()

    # Calculate date cutoff based on scope
    cutoff_date = None
    if scope == "weekly":
        cutoff_date = timezone.now() - timedelta(days=7)
    elif scope == "monthly":
        cutoff_date = timezone.now() - timedelta(days=30)

    # Get corpus if specified
    corpus_django_pk: int | None = None
    if corpus_id:
        try:
            corpus_django_pk = int(from_global_id(corpus_id)[1])
            # Verify user has access to this corpus.
            if (
                BaseService.get_or_none(
                    Corpus,
                    corpus_django_pk,
                    info.context.user,
                    request=info.context,
                )
                is None
            ):
                raise Corpus.DoesNotExist
        except Corpus.DoesNotExist:
            raise GraphQLError("Corpus not found or access denied")

    # Get visible users (respect privacy settings)
    users = BaseService.filter_visible(
        User, info.context.user, request=info.context
    ).filter(is_active=True)

    # Build query based on metric
    entries = []
    current_user = info.context.user

    if metric == "badges":
        # Count badges per user (UserBadge imported at top level)
        badge_query = UserBadge.objects.filter(user__in=users)
        if cutoff_date:
            badge_query = badge_query.filter(awarded_at__gte=cutoff_date)
        if corpus_django_pk:
            badge_query = badge_query.filter(
                Q(corpus_id=corpus_django_pk) | Q(corpus__isnull=True)
            )

        # ``.values().annotate()`` returns dicts at runtime; django-stubs
        # types the QuerySet as model instances, so cast to surface the
        # actual shape to mypy.
        user_badge_counts: list[dict[str, Any]] = list(
            cast(
                "Any",
                badge_query.values("user")
                .annotate(count=Count("id"))
                .order_by("-count")[:limit],
            )
        )

        for idx, item in enumerate(user_badge_counts, start=1):
            user = User.objects.get(id=item["user"])
            entries.append(
                LeaderboardEntryType(
                    user=user,
                    rank=idx,
                    score=item["count"],
                    badge_count=item["count"],
                )
            )

    elif metric == "messages":
        # Count messages per user
        # Filter by visible conversations since ChatMessage doesn't inherit conversation visibility
        visible_conversations = BaseService.filter_visible(
            Conversation, info.context.user, request=info.context
        )

        message_query = ChatMessage.objects.filter(
            creator__in=users,
            msg_type=MessageTypeChoices.HUMAN,
            conversation__in=visible_conversations,
        )

        if cutoff_date:
            message_query = message_query.filter(created__gte=cutoff_date)
        if corpus_django_pk:
            message_query = message_query.filter(
                conversation__chat_with_corpus_id=corpus_django_pk
            )

        user_message_counts: list[dict[str, Any]] = list(
            cast(
                "Any",
                message_query.values("creator")
                .annotate(count=Count("id"))
                .order_by("-count")[:limit],
            )
        )

        for idx, item in enumerate(user_message_counts, start=1):
            user = User.objects.get(id=item["creator"])
            entries.append(
                LeaderboardEntryType(
                    user=user,
                    rank=idx,
                    score=item["count"],
                    message_count=item["count"],
                )
            )

    elif metric == "threads":
        # Count threads created per user
        thread_query = BaseService.filter_visible(
            Conversation, info.context.user, request=info.context
        ).filter(creator__in=users, conversation_type="thread")

        if cutoff_date:
            thread_query = thread_query.filter(created__gte=cutoff_date)
        if corpus_django_pk:
            thread_query = thread_query.filter(chat_with_corpus_id=corpus_django_pk)

        user_thread_counts: list[dict[str, Any]] = list(
            cast(
                "Any",
                thread_query.values("creator")
                .annotate(count=Count("id"))
                .order_by("-count")[:limit],
            )
        )

        for idx, item in enumerate(user_thread_counts, start=1):
            user = User.objects.get(id=item["creator"])
            entries.append(
                LeaderboardEntryType(
                    user=user,
                    rank=idx,
                    score=item["count"],
                    thread_count=item["count"],
                )
            )

    elif metric == "annotations":
        # Count annotations created per user (visibility via service layer).
        annotation_query = BaseService.filter_visible(
            Annotation, info.context.user, request=info.context
        ).filter(creator__in=users)

        if cutoff_date:
            annotation_query = annotation_query.filter(created__gte=cutoff_date)
        if corpus_django_pk:
            annotation_query = annotation_query.filter(
                document__corpus__id=corpus_django_pk
            )

        user_annotation_counts = (
            annotation_query.values("creator")
            .annotate(count=Count("id"))
            .order_by("-count")[:limit]
        )

        for idx, item in enumerate(user_annotation_counts, start=1):
            user = User.objects.get(id=item["creator"])
            entries.append(
                LeaderboardEntryType(
                    user=user,
                    rank=idx,
                    score=item["count"],
                    annotation_count=item["count"],
                )
            )

    elif metric == "reputation":
        # Get reputation scores
        from opencontractserver.conversations.models import UserReputation

        rep_query = UserReputation.objects.filter(user__in=users)
        if corpus_django_pk:
            rep_query = rep_query.filter(corpus_id=corpus_django_pk)
        else:
            rep_query = rep_query.filter(corpus__isnull=True)

        top_reps = rep_query.select_related("user").order_by("-reputation_score")[
            :limit
        ]

        for idx, rep in enumerate(top_reps, start=1):
            entries.append(
                LeaderboardEntryType(
                    user=rep.user,
                    rank=idx,
                    score=rep.reputation_score,
                    reputation=rep.reputation_score,
                )
            )

    # Find current user's rank
    current_user_rank = None
    if current_user and current_user.is_authenticated:
        for entry in entries:
            if entry.user.id == current_user.id:  # type: ignore[union-attr]
                current_user_rank = entry.rank
                break

    return LeaderboardType(
        metric=metric,
        scope=scope,
        corpus_id=corpus_id,
        total_users=len(entries),
        entries=entries,
        current_user_rank=current_user_rank,
    )


def q_leaderboard(
    info: strawberry.Info,
    metric: Annotated[
        enums.LeaderboardMetricEnum, strawberry.argument(name="metric")
    ] = strawberry.UNSET,
    scope: Annotated[
        enums.LeaderboardScopeEnum | None, strawberry.argument(name="scope")
    ] = enums.LeaderboardScopeEnum.ALL_TIME,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = 25,
) -> None | (
    Annotated[LeaderboardType, strawberry.lazy("config.graphql.social_types")]
):
    kwargs = strip_unset(
        {"metric": metric, "scope": scope, "corpus_id": corpus_id, "limit": limit}
    )
    return _resolve_Query_leaderboard(None, info, **kwargs)


def _resolve_Query_community_stats(root, info, corpus_id=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_queries.py:634

    Port of SocialQueryMixin.resolve_community_stats

    Get overall community engagement statistics.

    Issue: #613 - Create leaderboard and community stats dashboard
    Epic: #572 - Social Features Epic

    Uses Django cache with a short TTL to avoid re-running 7+ COUNT
    queries on every landing page load. Cache is keyed by user type
    (anonymous vs authenticated user ID) and optional corpus_id.

    Args:
        corpus_id: Optional corpus ID for corpus-specific stats

    Returns:
        CommunityStatsType with engagement metrics
    """
    from datetime import timedelta

    from django.contrib.auth import get_user_model
    from django.db.models import Count
    from django.utils import timezone

    from opencontractserver.annotations.models import Annotation

    User = get_user_model()
    user = info.context.user

    # Get corpus if specified
    corpus_django_pk: int | None = None
    if corpus_id:
        try:
            corpus_django_pk = int(from_global_id(corpus_id)[1])
            # Verify user has access to this corpus.
            if (
                BaseService.get_or_none(
                    Corpus, corpus_django_pk, user, request=info.context
                )
                is None
            ):
                raise Corpus.DoesNotExist
        except Corpus.DoesNotExist:
            raise GraphQLError("Corpus not found or access denied")

    # Build cache key based on user identity and corpus scope
    user_key = "anon" if user.is_anonymous else f"user:{user.id}"
    corpus_key = f":corpus:{corpus_django_pk}" if corpus_django_pk else ""
    cache_key = f"community_stats:{user_key}{corpus_key}"

    cached = cache.get(cache_key)
    if cached is not None:
        # Reconstruct GraphQL types from cached primitives
        badge_distribution = []
        if cached.get("badge_distribution"):
            badge_ids = [b["badge_id"] for b in cached["badge_distribution"]]
            badges_by_id = Badge.objects.in_bulk(badge_ids) if badge_ids else {}
            badge_distribution = [
                BadgeDistributionType(
                    badge=badges_by_id[b["badge_id"]],
                    award_count=b["award_count"],
                    unique_recipients=b["unique_recipients"],
                )
                for b in cached["badge_distribution"]
                if b["badge_id"] in badges_by_id
            ]
        return CommunityStatsType(
            total_users=cached["total_users"],
            total_messages=cached["total_messages"],
            total_threads=cached["total_threads"],
            total_annotations=cached["total_annotations"],
            total_badges_awarded=cached["total_badges_awarded"],
            badge_distribution=badge_distribution,
            messages_this_week=cached["messages_this_week"],
            messages_this_month=cached["messages_this_month"],
            active_users_this_week=cached["active_users_this_week"],
            active_users_this_month=cached["active_users_this_month"],
        )

    # Calculate date cutoffs
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Get visible users (service-layer visibility).
    users = BaseService.filter_visible(User, user, request=info.context).filter(
        is_active=True
    )
    total_users = users.count()

    # Total messages
    # Filter by visible conversations since ChatMessage doesn't
    # inherit conversation visibility.
    visible_conversations_stats = BaseService.filter_visible(
        Conversation, user, request=info.context
    )
    message_query = ChatMessage.objects.filter(
        msg_type=MessageTypeChoices.HUMAN,
        conversation__in=visible_conversations_stats,
    )
    if corpus_django_pk:
        message_query = message_query.filter(
            conversation__chat_with_corpus_id=corpus_django_pk
        )
    total_messages = message_query.count()
    messages_this_week = message_query.filter(created__gte=week_ago).count()
    messages_this_month = message_query.filter(created__gte=month_ago).count()

    # Active users (users who posted messages)
    active_users_week = (
        message_query.filter(created__gte=week_ago).values("creator").distinct().count()
    )
    active_users_month = (
        message_query.filter(created__gte=month_ago)
        .values("creator")
        .distinct()
        .count()
    )

    # Total threads
    thread_query = BaseService.filter_visible(
        Conversation, user, request=info.context
    ).filter(conversation_type="thread")
    if corpus_django_pk:
        thread_query = thread_query.filter(chat_with_corpus_id=corpus_django_pk)
    total_threads = thread_query.count()

    # Total annotations
    annotation_query = BaseService.filter_visible(
        Annotation, user, request=info.context
    )
    if corpus_django_pk:
        annotation_query = annotation_query.filter(
            document__corpus__id=corpus_django_pk
        )
    total_annotations = annotation_query.count()

    # Total badges awarded
    badge_query = UserBadge.objects.all()
    if corpus_django_pk:
        badge_query = badge_query.filter(
            Q(corpus_id=corpus_django_pk) | Q(corpus__isnull=True)
        )
    total_badges_awarded = badge_query.count()

    # Badge distribution - batch-load badges to avoid N+1
    badge_distribution = []
    badge_stats: list[dict[str, Any]] = list(
        cast(
            "Any",
            badge_query.values("badge")
            .annotate(
                award_count=Count("id"),
                unique_recipients=Count("user", distinct=True),
            )
            .order_by("-award_count")[:10],
        )
    )

    if badge_stats:
        badge_ids = [stat["badge"] for stat in badge_stats]
        badges_by_id = Badge.objects.in_bulk(badge_ids)
        for stat in badge_stats:
            badge_obj = badges_by_id.get(stat["badge"])
            if badge_obj:
                badge_distribution.append(
                    BadgeDistributionType(
                        badge=badge_obj,
                        award_count=stat["award_count"],
                        unique_recipients=stat["unique_recipients"],
                    )
                )

    # Cache primitive data only — avoids pickling GraphQL ObjectTypes
    # and Django model instances, which is fragile with Redis/Memcached.
    cache_payload = {
        "total_users": total_users,
        "total_messages": total_messages,
        "total_threads": total_threads,
        "total_annotations": total_annotations,
        "total_badges_awarded": total_badges_awarded,
        "badge_distribution": [
            {
                "badge_id": stat["badge"],
                "award_count": stat["award_count"],
                "unique_recipients": stat["unique_recipients"],
            }
            for stat in badge_stats
        ],
        "messages_this_week": messages_this_week,
        "messages_this_month": messages_this_month,
        "active_users_this_week": active_users_week,
        "active_users_this_month": active_users_month,
    }
    cache.set(cache_key, cache_payload, COMMUNITY_STATS_CACHE_TTL)

    return CommunityStatsType(
        total_users=total_users,
        total_messages=total_messages,
        total_threads=total_threads,
        total_annotations=total_annotations,
        total_badges_awarded=total_badges_awarded,
        badge_distribution=badge_distribution,
        messages_this_week=messages_this_week,
        messages_this_month=messages_this_month,
        active_users_this_week=active_users_week,
        active_users_this_month=active_users_month,
    )


def q_community_stats(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[CommunityStatsType, strawberry.lazy("config.graphql.social_types")]
):
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_community_stats(None, info, **kwargs)


QUERY_FIELDS = {
    "badges": strawberry.field(resolver=q_badges, name="badges"),
    "badge": strawberry.field(resolver=q_badge, name="badge"),
    "user_badges": strawberry.field(resolver=q_user_badges, name="userBadges"),
    "user_badge": strawberry.field(resolver=q_user_badge, name="userBadge"),
    "badge_criteria_types": strawberry.field(
        resolver=q_badge_criteria_types,
        name="badgeCriteriaTypes",
        description="Get available badge criteria types from the registry",
    ),
    "agents": strawberry.field(resolver=q_agents, name="agents"),
    "agent_configurations": strawberry.field(
        resolver=q_agent_configurations, name="agentConfigurations"
    ),
    "agent": strawberry.field(resolver=q_agent, name="agent"),
    "available_tools": strawberry.field(
        resolver=q_available_tools,
        name="availableTools",
        description="Get all available tools that can be assigned to agents",
    ),
    "available_tool_categories": strawberry.field(
        resolver=q_available_tool_categories,
        name="availableToolCategories",
        description="Get all available tool categories",
    ),
    "notifications": strawberry.field(
        resolver=q_notifications,
        name="notifications",
        description="Get user's notifications (paginated and filterable)",
    ),
    "notification": strawberry.field(resolver=q_notification, name="notification"),
    "unread_notification_count": strawberry.field(
        resolver=q_unread_notification_count,
        name="unreadNotificationCount",
        description="Get count of unread notifications for the current user",
    ),
    "corpus_leaderboard": strawberry.field(
        resolver=q_corpus_leaderboard,
        name="corpusLeaderboard",
        description="Get top contributors for a specific corpus by reputation",
    ),
    "global_leaderboard": strawberry.field(
        resolver=q_global_leaderboard,
        name="globalLeaderboard",
        description="Get top contributors globally by reputation",
    ),
    "leaderboard": strawberry.field(
        resolver=q_leaderboard,
        name="leaderboard",
        description="Get leaderboard for a specific metric and scope",
    ),
    "community_stats": strawberry.field(
        resolver=q_community_stats,
        name="communityStats",
        description="Get overall community engagement statistics",
    ),
}
