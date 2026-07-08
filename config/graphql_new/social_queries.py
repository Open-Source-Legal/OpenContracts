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

from config.graphql.filters import AgentConfigurationFilter
from config.graphql.filters import BadgeFilter
from config.graphql.filters import UserBadgeFilter
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.badges.models import Badge
from opencontractserver.badges.models import UserBadge
from opencontractserver.notifications.models import Notification


def _resolve_Query_badges(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:57

    Port of SocialQueryMixin.resolve_badges
    """
    raise NotImplementedError("_resolve_Query_badges not yet ported — see manifest")


def q_badges(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, badge_type: Annotated[Optional[enums.BadgesBadgeBadgeTypeChoices], strawberry.argument(name="badgeType")] = strawberry.UNSET, is_auto_awarded: Annotated[Optional[bool], strawberry.argument(name="isAutoAwarded")] = strawberry.UNSET, name__contains: Annotated[Optional[str], strawberry.argument(name="name_Contains")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["BadgeTypeConnection", strawberry.lazy("config.graphql_new.social_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "badge_type": badge_type, "is_auto_awarded": is_auto_awarded, "name__contains": name__contains, "name": name, "corpus_id": corpus_id})
    resolved = _resolve_Query_badges(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="BadgeType", default_manager=Badge._default_manager, filterset_class=setup_filterset(BadgeFilter), filter_args={"badge_type": "badge_type", "is_auto_awarded": "is_auto_awarded", "name__contains": "name__contains", "name": "name", "corpus_id": "corpus_id"}, )


def q_badge(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["BadgeType", strawberry.lazy("config.graphql_new.social_types")]]:
    return get_node_from_global_id(info, id, only_type_name="BadgeType")


def _resolve_Query_user_badges(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:75

    Port of SocialQueryMixin.resolve_user_badges
    """
    raise NotImplementedError("_resolve_Query_user_badges not yet ported — see manifest")


def q_user_badges(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, awarded_at__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="awardedAt_Gte")] = strawberry.UNSET, awarded_at__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="awardedAt_Lte")] = strawberry.UNSET, user_id: Annotated[Optional[str], strawberry.argument(name="userId")] = strawberry.UNSET, badge_id: Annotated[Optional[str], strawberry.argument(name="badgeId")] = strawberry.UNSET, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["UserBadgeTypeConnection", strawberry.lazy("config.graphql_new.social_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "awarded_at__gte": awarded_at__gte, "awarded_at__lte": awarded_at__lte, "user_id": user_id, "badge_id": badge_id, "corpus_id": corpus_id})
    resolved = _resolve_Query_user_badges(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserBadgeType", default_manager=UserBadge._default_manager, filterset_class=setup_filterset(UserBadgeFilter), filter_args={"awarded_at__gte": "awarded_at__gte", "awarded_at__lte": "awarded_at__lte", "user_id": "user_id", "badge_id": "badge_id", "corpus_id": "corpus_id"}, )


def q_user_badge(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["UserBadgeType", strawberry.lazy("config.graphql_new.social_types")]]:
    return get_node_from_global_id(info, id, only_type_name="UserBadgeType")


def _resolve_Query_badge_criteria_types(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:122

    Port of SocialQueryMixin.resolve_badge_criteria_types
    """
    raise NotImplementedError("_resolve_Query_badge_criteria_types not yet ported — see manifest")


def q_badge_criteria_types(info: strawberry.Info, scope: Annotated[Optional[str], strawberry.argument(name="scope", description="Filter by scope: 'global', 'corpus', or 'both'")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["CriteriaTypeDefinitionType", strawberry.lazy("config.graphql_new.social_types")]]]]:
    kwargs = strip_unset({"scope": scope})
    return _resolve_Query_badge_criteria_types(None, info, **kwargs)


def _resolve_Query_agents(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:174

    Port of SocialQueryMixin.resolve_agents
    """
    raise NotImplementedError("_resolve_Query_agents not yet ported — see manifest")


def q_agents(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, scope: Annotated[Optional[enums.AgentsAgentConfigurationScopeChoices], strawberry.argument(name="scope")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET, name__contains: Annotated[Optional[str], strawberry.argument(name="name_Contains")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["AgentConfigurationTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "scope": scope, "is_active": is_active, "name__contains": name__contains, "name": name, "corpus_id": corpus_id})
    resolved = _resolve_Query_agents(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentConfigurationType", default_manager=AgentConfiguration._default_manager, filterset_class=setup_filterset(AgentConfigurationFilter), filter_args={"scope": "scope", "is_active": "is_active", "name__contains": "name__contains", "name": "name", "corpus_id": "corpus_id"}, )


def _resolve_Query_agent_configurations(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:182

    Port of SocialQueryMixin.resolve_agent_configurations
    """
    raise NotImplementedError("_resolve_Query_agent_configurations not yet ported — see manifest")


def q_agent_configurations(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, scope: Annotated[Optional[enums.AgentsAgentConfigurationScopeChoices], strawberry.argument(name="scope")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET, name__contains: Annotated[Optional[str], strawberry.argument(name="name_Contains")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["AgentConfigurationTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "scope": scope, "is_active": is_active, "name__contains": name__contains, "name": name, "corpus_id": corpus_id})
    resolved = _resolve_Query_agent_configurations(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentConfigurationType", default_manager=AgentConfiguration._default_manager, filterset_class=setup_filterset(AgentConfigurationFilter), filter_args={"scope": "scope", "is_active": "is_active", "name__contains": "name__contains", "name": "name", "corpus_id": "corpus_id"}, )


def q_agent(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["AgentConfigurationType", strawberry.lazy("config.graphql_new.agent_types")]]:
    return get_node_from_global_id(info, id, only_type_name="AgentConfigurationType")


def _resolve_Query_available_tools(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:221

    Port of SocialQueryMixin.resolve_available_tools
    """
    raise NotImplementedError("_resolve_Query_available_tools not yet ported — see manifest")


def q_available_tools(info: strawberry.Info, category: Annotated[Optional[str], strawberry.argument(name="category", description='Filter by tool category (search, document, corpus, notes, annotations, coordination)')] = strawberry.UNSET) -> Optional[list[Annotated["AvailableToolType", strawberry.lazy("config.graphql_new.agent_types")]]]:
    kwargs = strip_unset({"category": category})
    return _resolve_Query_available_tools(None, info, **kwargs)


def _resolve_Query_available_tool_categories(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:240

    Port of SocialQueryMixin.resolve_available_tool_categories
    """
    raise NotImplementedError("_resolve_Query_available_tool_categories not yet ported — see manifest")


def q_available_tool_categories(info: strawberry.Info) -> Optional[list[str]]:
    kwargs = strip_unset({})
    return _resolve_Query_available_tool_categories(None, info, **kwargs)


def _resolve_Query_notifications(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:257

    Port of SocialQueryMixin.resolve_notifications
    """
    raise NotImplementedError("_resolve_Query_notifications not yet ported — see manifest")


def q_notifications(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, is_read: Annotated[Optional[bool], strawberry.argument(name="isRead")] = strawberry.UNSET, notification_type: Annotated[Optional[enums.NotificationsNotificationNotificationTypeChoices], strawberry.argument(name="notificationType")] = strawberry.UNSET, created_at__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Lte")] = strawberry.UNSET, created_at__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Gte")] = strawberry.UNSET) -> Optional[Annotated["NotificationTypeConnection", strawberry.lazy("config.graphql_new.social_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "is_read": is_read, "notification_type": notification_type, "created_at__lte": created_at__lte, "created_at__gte": created_at__gte})
    resolved = _resolve_Query_notifications(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NotificationType", default_manager=Notification._default_manager, filterset_class=filterset_factory(Notification, fields={'is_read': ['exact'], 'notification_type': ['exact'], 'created_at': ['lte', 'gte']}), filter_args={"is_read": "is_read", "notification_type": "notification_type", "created_at__lte": "created_at__lte", "created_at__gte": "created_at__gte"}, )


def q_notification(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["NotificationType", strawberry.lazy("config.graphql_new.social_types")]]:
    return get_node_from_global_id(info, id, only_type_name="NotificationType")


def _resolve_Query_unread_notification_count(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:289

    Port of SocialQueryMixin.resolve_unread_notification_count
    """
    raise NotImplementedError("_resolve_Query_unread_notification_count not yet ported — see manifest")


def q_unread_notification_count(info: strawberry.Info) -> Optional[int]:
    kwargs = strip_unset({})
    return _resolve_Query_unread_notification_count(None, info, **kwargs)


def _resolve_Query_corpus_leaderboard(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:308

    Port of SocialQueryMixin.resolve_corpus_leaderboard
    """
    raise NotImplementedError("_resolve_Query_corpus_leaderboard not yet ported — see manifest")


def q_corpus_leaderboard(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 10) -> Optional[list[Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]]]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "limit": limit})
    return _resolve_Query_corpus_leaderboard(None, info, **kwargs)


def _resolve_Query_global_leaderboard(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:351

    Port of SocialQueryMixin.resolve_global_leaderboard
    """
    raise NotImplementedError("_resolve_Query_global_leaderboard not yet ported — see manifest")


def q_global_leaderboard(info: strawberry.Info, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 10) -> Optional[list[Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]]]]:
    kwargs = strip_unset({"limit": limit})
    return _resolve_Query_global_leaderboard(None, info, **kwargs)


def _resolve_Query_leaderboard(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:396

    Port of SocialQueryMixin.resolve_leaderboard
    """
    raise NotImplementedError("_resolve_Query_leaderboard not yet ported — see manifest")


def q_leaderboard(info: strawberry.Info, metric: Annotated[enums.LeaderboardMetricEnum, strawberry.argument(name="metric")] = strawberry.UNSET, scope: Annotated[Optional[enums.LeaderboardScopeEnum], strawberry.argument(name="scope")] = enums.LeaderboardScopeEnum.ALL_TIME, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[Annotated["LeaderboardType", strawberry.lazy("config.graphql_new.social_types")]]:
    kwargs = strip_unset({"metric": metric, "scope": scope, "corpus_id": corpus_id, "limit": limit})
    return _resolve_Query_leaderboard(None, info, **kwargs)


def _resolve_Query_community_stats(root, info, **kwargs):
    """PORT: config/graphql/social_queries.py:634

    Port of SocialQueryMixin.resolve_community_stats
    """
    raise NotImplementedError("_resolve_Query_community_stats not yet ported — see manifest")


def q_community_stats(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["CommunityStatsType", strawberry.lazy("config.graphql_new.social_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_community_stats(None, info, **kwargs)



QUERY_FIELDS = {
    "badges": strawberry.field(resolver=q_badges, name="badges"),
    "badge": strawberry.field(resolver=q_badge, name="badge"),
    "user_badges": strawberry.field(resolver=q_user_badges, name="userBadges"),
    "user_badge": strawberry.field(resolver=q_user_badge, name="userBadge"),
    "badge_criteria_types": strawberry.field(resolver=q_badge_criteria_types, name="badgeCriteriaTypes", description='Get available badge criteria types from the registry'),
    "agents": strawberry.field(resolver=q_agents, name="agents"),
    "agent_configurations": strawberry.field(resolver=q_agent_configurations, name="agentConfigurations"),
    "agent": strawberry.field(resolver=q_agent, name="agent"),
    "available_tools": strawberry.field(resolver=q_available_tools, name="availableTools", description='Get all available tools that can be assigned to agents'),
    "available_tool_categories": strawberry.field(resolver=q_available_tool_categories, name="availableToolCategories", description='Get all available tool categories'),
    "notifications": strawberry.field(resolver=q_notifications, name="notifications", description="Get user's notifications (paginated and filterable)"),
    "notification": strawberry.field(resolver=q_notification, name="notification"),
    "unread_notification_count": strawberry.field(resolver=q_unread_notification_count, name="unreadNotificationCount", description='Get count of unread notifications for the current user'),
    "corpus_leaderboard": strawberry.field(resolver=q_corpus_leaderboard, name="corpusLeaderboard", description='Get top contributors for a specific corpus by reputation'),
    "global_leaderboard": strawberry.field(resolver=q_global_leaderboard, name="globalLeaderboard", description='Get top contributors globally by reputation'),
    "leaderboard": strawberry.field(resolver=q_leaderboard, name="leaderboard", description='Get leaderboard for a specific metric and scope'),
    "community_stats": strawberry.field(resolver=q_community_stats, name="communityStats", description='Get overall community engagement statistics'),
}
