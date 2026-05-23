"""
GraphQL query mixin for badge, leaderboard, community, notification, and agent queries.
"""

import logging
from typing import Any, cast

import graphene
from django.core.cache import cache
from django.db.models import Q
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField
from graphql import GraphQLError
from graphql_relay import from_global_id

from config.graphql.filters import (
    AgentConfigurationFilter,
    BadgeFilter,
    UserBadgeFilter,
)
from config.graphql.graphene_types import (
    AgentConfigurationType,
    AvailableToolType,
    BadgeDistributionType,
    BadgeType,
    CommunityStatsType,
    CriteriaTypeDefinitionType,
    LeaderboardEntryType,
    LeaderboardMetricEnum,
    LeaderboardScopeEnum,
    LeaderboardType,
    NotificationType,
    UserBadgeType,
    UserType,
)
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

logger = logging.getLogger(__name__)


class SocialQueryMixin:
    """Query fields and resolvers for badge, leaderboard, community, notification, and agent queries."""

    # BADGE RESOLVERS ####################################
    badges = DjangoFilterConnectionField(BadgeType, filterset_class=BadgeFilter)
    badge = relay.Node.Field(BadgeType)

    def resolve_badges(self, info, **kwargs) -> Any:
        """Resolve badges visible to the user."""
        return Badge.objects.visible_to_user(info.context.user).select_related(
            "creator", "corpus"
        )

    def resolve_badge(self, info, **kwargs) -> Any:
        """Resolve a single badge by ID."""
        django_pk = int(from_global_id(kwargs["id"])[1])
        return Badge.objects.visible_to_user(info.context.user).get(id=django_pk)

    user_badges = DjangoFilterConnectionField(
        UserBadgeType, filterset_class=UserBadgeFilter
    )
    user_badge = relay.Node.Field(UserBadgeType)

    def resolve_user_badges(self, info, **kwargs) -> Any:
        """
        Resolve user badge awards with profile privacy filtering.

        SECURITY: Badge visibility follows the recipient's profile visibility.
        Badges are visible if:
        - Recipient's profile is public
        - Requesting user shares corpus membership with recipient (> READ permission)
        - It's the requesting user's own badges
        - For corpus-specific badges: user has access to that corpus
        """
        from opencontractserver.badges.services import BadgeService

        return BadgeService.get_visible_user_badges(
            info.context.user, request=info.context
        )

    def resolve_user_badge(self, info, **kwargs) -> Any:
        """
        Resolve a single user badge by ID with visibility check and IDOR protection.

        SECURITY: Returns same error whether badge doesn't exist or user lacks permission.
        This prevents enumeration attacks.
        """
        from opencontractserver.badges.services import BadgeService

        django_pk = int(from_global_id(kwargs["id"])[1])

        has_permission, user_badge = BadgeService.check_user_badge_visibility(
            info.context.user, django_pk, request=info.context
        )

        if not has_permission:
            # Same error whether doesn't exist or no permission (IDOR protection)
            raise GraphQLError("User badge not found")

        return user_badge

    badge_criteria_types = graphene.List(
        CriteriaTypeDefinitionType,
        scope=graphene.String(
            required=False,
            description="Filter by scope: 'global', 'corpus', or 'both'",
        ),
        description="Get available badge criteria types from the registry",
    )

    def resolve_badge_criteria_types(self, info, scope=None) -> Any:
        """
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

        # Convert dataclass instances to dicts for GraphQL
        return [
            {
                "type_id": ct.type_id,
                "name": ct.name,
                "description": ct.description,
                "scope": ct.scope,
                "fields": [
                    {
                        "name": f.name,
                        "label": f.label,
                        "field_type": f.field_type,
                        "required": f.required,
                        "description": f.description,
                        "min_value": f.min_value,
                        "max_value": f.max_value,
                        "allowed_values": f.allowed_values,
                    }
                    for f in ct.fields
                ],
                "implemented": ct.implemented,
            }
            for ct in criteria_types
        ]

    # AGENT CONFIGURATION QUERIES ########################################
    agents = DjangoFilterConnectionField(
        AgentConfigurationType, filterset_class=AgentConfigurationFilter
    )
    # Alias for frontend compatibility
    agent_configurations = DjangoFilterConnectionField(
        AgentConfigurationType, filterset_class=AgentConfigurationFilter
    )
    agent = relay.Node.Field(AgentConfigurationType)

    def resolve_agents(self, info, **kwargs) -> Any:
        """Resolve agent configurations visible to the user."""
        from opencontractserver.agents.models import AgentConfiguration

        return AgentConfiguration.objects.visible_to_user(
            info.context.user
        ).select_related("creator", "corpus")

    def resolve_agent_configurations(self, info, **kwargs) -> Any:
        """Alias for resolve_agents - frontend compatibility."""
        from opencontractserver.agents.models import AgentConfiguration

        return AgentConfiguration.objects.visible_to_user(
            info.context.user
        ).select_related("creator", "corpus")

    def resolve_agent(self, info, **kwargs) -> Any:
        """Resolve a single agent configuration by ID."""
        from opencontractserver.agents.models import AgentConfiguration

        django_pk = int(from_global_id(kwargs["id"])[1])
        return AgentConfiguration.objects.visible_to_user(info.context.user).get(
            id=django_pk
        )

    # AGENT TOOLS QUERIES ########################################
    available_tools = graphene.List(
        graphene.NonNull(AvailableToolType),
        category=graphene.String(
            description="Filter by tool category (search, document, corpus, notes, annotations, coordination)"
        ),
        description="Get all available tools that can be assigned to agents",
    )

    available_tool_categories = graphene.List(
        graphene.NonNull(graphene.String),
        description="Get all available tool categories",
    )

    def resolve_available_tools(self, info, category=None, **kwargs) -> Any:
        """
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

        return tools

    def resolve_available_tool_categories(self, info, **kwargs) -> Any:
        """Resolve all available tool categories."""
        from opencontractserver.llms.tools.tool_registry import ToolCategory

        return [cat.value for cat in ToolCategory]

    # NOTIFICATION QUERIES ########################################
    notifications = DjangoFilterConnectionField(
        NotificationType,
        description="Get user's notifications (paginated and filterable)",
    )
    notification = relay.Node.Field(NotificationType)

    unread_notification_count = graphene.Int(
        description="Get count of unread notifications for the current user"
    )

    def resolve_notifications(self, info, **kwargs) -> Any:
        """
        Resolve notifications for the current user.

        Filters notifications to only show those belonging to the current user.
        Supports filtering by is_read and notification_type via DjangoFilterConnectionField.
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            return Notification.objects.none()

        return (
            Notification.objects.filter(recipient=user)
            .select_related("actor", "message", "conversation", "recipient")
            .order_by("-created_at")
        )

    def resolve_notification(self, info, **kwargs) -> Any:
        """
        Resolve a single notification by ID.

        Ensures user can only access their own notifications.
        Returns consistent error to prevent IDOR enumeration.
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            raise GraphQLError("Notification not found")

        django_pk = int(from_global_id(kwargs["id"])[1])

        # Use try/except to catch DoesNotExist and return same error
        # This prevents enumeration of valid notification IDs
        try:
            notification = Notification.objects.get(id=django_pk, recipient=user)
        except Notification.DoesNotExist:
            # Same error whether notification doesn't exist or belongs to another user
            raise GraphQLError("Notification not found")

        return notification

    def resolve_unread_notification_count(self, info) -> Any:
        """Get count of unread notifications for the current user."""
        user = info.context.user
        if not user or not user.is_authenticated:
            return 0

        return Notification.objects.filter(recipient=user, is_read=False).count()

    # ENGAGEMENT METRICS & LEADERBOARD QUERIES (Epic #565) ########
    corpus_leaderboard = graphene.List(
        UserType,
        corpus_id=graphene.ID(required=True),
        limit=graphene.Int(default_value=10),
        description="Get top contributors for a specific corpus by reputation",
    )
    global_leaderboard = graphene.List(
        UserType,
        limit=graphene.Int(default_value=10),
        description="Get top contributors globally by reputation",
    )

    def resolve_corpus_leaderboard(self, info, corpus_id, limit=10) -> Any:
        """
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

            # Check if user has access to this corpus
            Corpus.objects.visible_to_user(info.context.user).get(id=corpus_pk)

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

    def resolve_global_leaderboard(self, info, limit=10) -> Any:
        """
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

    # LEADERBOARD QUERIES (Issue #613) ###################
    leaderboard = graphene.Field(
        LeaderboardType,
        metric=graphene.Argument(LeaderboardMetricEnum, required=True),
        scope=graphene.Argument(LeaderboardScopeEnum, default_value="all_time"),
        corpus_id=graphene.ID(),
        limit=graphene.Int(default_value=25),
        description="Get leaderboard for a specific metric and scope",
    )
    community_stats = graphene.Field(
        CommunityStatsType,
        corpus_id=graphene.ID(),
        description="Get overall community engagement statistics",
    )

    def resolve_leaderboard(
        self, info, metric, scope="all_time", corpus_id=None, limit=25
    ) -> Any:
        """
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
                # Verify user has access to this corpus
                Corpus.objects.visible_to_user(info.context.user).get(
                    id=corpus_django_pk
                )
            except Corpus.DoesNotExist:
                raise GraphQLError("Corpus not found or access denied")

        # Get visible users (respect privacy settings)
        users = User.objects.visible_to_user(info.context.user).filter(is_active=True)

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
            visible_conversations = Conversation.objects.visible_to_user(
                info.context.user
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
            thread_query = Conversation.objects.visible_to_user(
                info.context.user
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
            # Count annotations created per user
            annotation_query = Annotation.objects.filter(
                creator__in=users
            ).visible_to_user(info.context.user)

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
                if entry.user.id == current_user.id:
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

    def resolve_community_stats(self, info, corpus_id=None) -> Any:
        """
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
                # Verify user has access to this corpus
                Corpus.objects.visible_to_user(user).get(id=corpus_django_pk)
            except Corpus.DoesNotExist:
                raise GraphQLError("Corpus not found or access denied")

        # Build cache key based on user identity and corpus scope
        user_key = "anon" if user.is_anonymous else f"user:{user.id}"
        corpus_key = f":corpus:{corpus_django_pk}" if corpus_django_pk else ""
        cache_key = f"community_stats:{user_key}{corpus_key}"

        cached = cache.get(cache_key)
        if cached is not None:
            # Reconstruct Graphene types from cached primitives
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

        # Get visible users
        users = User.objects.visible_to_user(user).filter(is_active=True)
        total_users = users.count()

        # Total messages
        # Filter by visible conversations since ChatMessage doesn't
        # inherit conversation visibility
        visible_conversations_stats = Conversation.objects.visible_to_user(user)
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
            message_query.filter(created__gte=week_ago)
            .values("creator")
            .distinct()
            .count()
        )
        active_users_month = (
            message_query.filter(created__gte=month_ago)
            .values("creator")
            .distinct()
            .count()
        )

        # Total threads
        thread_query = Conversation.objects.visible_to_user(user).filter(
            conversation_type="thread"
        )
        if corpus_django_pk:
            thread_query = thread_query.filter(chat_with_corpus_id=corpus_django_pk)
        total_threads = thread_query.count()

        # Total annotations
        annotation_query = Annotation.objects.visible_to_user(user)
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

        # Cache primitive data only — avoids pickling Graphene ObjectTypes
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
