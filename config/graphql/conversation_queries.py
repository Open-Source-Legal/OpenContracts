"""
GraphQL query mixin for conversation, message, and moderation queries.
"""

import logging
from datetime import timedelta
from typing import Any, Optional

import graphene
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.filters import ConversationFilter, ModerationActionFilter
from config.graphql.graphene_types import (
    ConversationType,
    MessageType,
    ModerationActionType,
    ModerationMetricsType,
)
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageTypeChoices,
    ModerationAction,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


class ConversationQueryMixin:
    """Query fields and resolvers for conversation, message, and moderation queries."""

    # CONVERSATION RESOLVERS #####################################
    conversations = DjangoFilterConnectionField(
        ConversationType,
        filterset_class=ConversationFilter,
        description="Retrieve conversations, optionally filtered by document_id or corpus_id",
    )

    def resolve_conversations(self, info, **kwargs) -> Any:
        """
        Resolver to fetch Conversations along with their Messages.

        Anonymous users can see public conversations.
        Authenticated users see public conversations, their own, or explicitly shared.

        Args:
            info: GraphQL execution info.
            **kwargs: Filter arguments passed through DjangoFilterConnectionField

        Returns:
            QuerySet[Conversation]: Filtered queryset of conversations
        """
        return (
            BaseService.filter_visible(
                Conversation, info.context.user, request=info.context
            )
            .select_related("creator", "chat_with_corpus", "chat_with_corpus__creator")
            .prefetch_related(
                Prefetch(
                    "chat_messages",
                    queryset=ChatMessage.objects.order_by("created_at"),
                )
            )
            .order_by("-created")
        )

    conversation = relay.Node.Field(ConversationType)

    # CONVERSATION SEARCH RESOLVERS #######################################
    search_conversations = relay.ConnectionField(
        "config.graphql.graphene_types.ConversationConnection",
        query=graphene.String(required=True, description="Search query text"),
        corpus_id=graphene.ID(required=False, description="Filter by corpus ID"),
        document_id=graphene.ID(required=False, description="Filter by document ID"),
        conversation_type=graphene.String(
            required=False, description="Filter by conversation type (chat/thread)"
        ),
        top_k=graphene.Int(
            default_value=100,
            description="Maximum number of results to fetch from vector store",
        ),
        description="Search conversations using vector similarity with pagination",
    )

    def resolve_search_conversations(
        self,
        info,
        query,
        corpus_id=None,
        document_id=None,
        conversation_type=None,
        top_k=100,
        **kwargs,
    ) -> Any:
        """
        Search conversations using vector similarity with cursor-based pagination.

        Anonymous users can search public conversations.
        Authenticated users can search public, their own, or explicitly shared conversations.

        Args:
            info: GraphQL execution info
            query: Search query text
            corpus_id: Optional corpus ID filter
            document_id: Optional document ID filter
            conversation_type: Optional conversation type filter
            top_k: Maximum results to fetch from vector store (default 100)
            **kwargs: Pagination args (first, after, last, before) handled by ConnectionField

        Returns:
            Connection with edges and pageInfo for pagination
        """
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (
            CoreConversationVectorStore,
            VectorSearchQuery,
        )

        # Convert global IDs to database IDs
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None
        document_pk = from_global_id(document_id)[1] if document_id else None

        # Get embedder path from settings if no corpus specified
        embedder_path = None
        if not corpus_pk and not document_id:
            # Use default embedder from settings
            from django.conf import settings

            embedder_path = getattr(settings, "DEFAULT_EMBEDDER_PATH", None)
            if not embedder_path:
                # If still no embedder available, raise clear error
                raise ValueError(
                    "Either corpus_id, document_id, or DEFAULT_EMBEDDER_PATH setting is required"
                )

        # Handle anonymous users
        user_id = (
            None
            if not info.context.user or info.context.user.is_anonymous
            else info.context.user.id
        )

        # Create vector store
        vector_store = CoreConversationVectorStore(
            user_id=user_id,
            corpus_id=corpus_pk,
            document_id=document_pk,
            conversation_type=conversation_type,
            embedder_path=embedder_path,
        )

        # Create search query
        search_query = VectorSearchQuery(
            query_text=query,
            similarity_top_k=top_k,
        )

        # Perform search (sync in GraphQL context)
        results = vector_store.search(search_query)

        # Extract conversations from results and return as queryset-like list
        # ConnectionField will handle pagination automatically
        conversations = [result.conversation for result in results]
        return conversations

    search_messages = graphene.List(
        "config.graphql.graphene_types.MessageType",
        query=graphene.String(required=True, description="Search query text"),
        corpus_id=graphene.ID(required=False, description="Filter by corpus ID"),
        conversation_id=graphene.ID(
            required=False, description="Filter by conversation ID"
        ),
        msg_type=graphene.String(
            required=False, description="Filter by message type (HUMAN/LLM/SYSTEM)"
        ),
        top_k=graphene.Int(default_value=10, description="Number of results to return"),
        description="Search messages using vector similarity",
    )

    @login_required
    def resolve_search_messages(
        self, info, query, corpus_id=None, conversation_id=None, msg_type=None, top_k=10
    ) -> Any:
        """
        Search messages using vector similarity.

        Args:
            info: GraphQL execution info
            query: Search query text
            corpus_id: Optional corpus ID filter
            conversation_id: Optional conversation ID filter
            msg_type: Optional message type filter
            top_k: Number of results to return

        Returns:
            List[ChatMessage]: List of matching messages
        """
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (
            CoreChatMessageVectorStore,
            VectorSearchQuery,
        )

        # Convert global IDs to database IDs
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None
        conversation_pk = (
            from_global_id(conversation_id)[1] if conversation_id else None
        )

        # Get embedder path from settings if no corpus specified
        embedder_path = None
        if not corpus_pk and not conversation_pk:
            # Use default embedder from settings
            from django.conf import settings

            embedder_path = getattr(settings, "DEFAULT_EMBEDDER_PATH", None)
            if not embedder_path:
                # If still no embedder available, raise clear error
                raise ValueError(
                    "Either corpus_id, conversation_id, or DEFAULT_EMBEDDER_PATH setting is required"
                )

        # Create vector store
        vector_store = CoreChatMessageVectorStore(
            user_id=info.context.user.id,
            corpus_id=corpus_pk,
            conversation_id=conversation_pk,
            msg_type=msg_type,
            embedder_path=embedder_path,
        )

        # Create search query
        search_query = VectorSearchQuery(
            query_text=query,
            similarity_top_k=top_k,
        )

        # Perform search (sync in GraphQL context)
        results = vector_store.search(search_query)

        # Extract messages from results
        return [result.message for result in results]

    # CHAT MESSAGE RESOLVERS #####################################
    chat_messages = graphene.Field(
        graphene.List(MessageType),
        conversation_id=graphene.ID(required=True),
        order_by=graphene.String(required=False),
    )

    @login_required
    def resolve_chat_messages(
        self,
        info: graphene.ResolveInfo,
        conversation_id: str,
        order_by: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """
        Resolver for fetching ChatMessage objects with optional filters.

        Args:
            info (graphene.ResolveInfo): GraphQL resolve info
            conversation_id (Optional[str]): Global Relay ID for Conversation filter
            order_by (Optional[str]): Field to order by. Defaults to "-created_at"
                Supported fields: created_at, -created_at, msg_type, -msg_type,
                modified, -modified
            **kwargs: Additional filter arguments

        Returns:
            QuerySet[ChatMessage]: Filtered and ordered chat messages
        """
        queryset = BaseService.filter_visible(
            ChatMessage, info.context.user, request=info.context
        )

        # Apply conversation filter if provided
        conversation_pk = from_global_id(conversation_id)[1]
        queryset = queryset.filter(conversation_id=conversation_pk)

        # Apply ordering
        valid_order_fields = {
            "created_at",
            "-created_at",
            "msg_type",
            "-msg_type",
            "modified",
            "-modified",
        }

        order_field = order_by if order_by in valid_order_fields else "created_at"
        queryset = queryset.order_by(order_field)

        return queryset

    chat_message = relay.Node.Field(MessageType)

    # User messages query for profile/activity feeds
    user_messages = graphene.Field(
        graphene.List(MessageType),
        creator_id=graphene.ID(required=True),
        first=graphene.Int(required=False, default_value=10),
        msg_type=graphene.String(required=False),
        order_by=graphene.String(required=False),
        description="Get messages created by a specific user, with optional filtering and pagination",
    )

    @login_required
    def resolve_user_messages(
        self,
        info: graphene.ResolveInfo,
        creator_id: str,
        first: int = 10,
        msg_type: Optional[str] = None,
        order_by: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """
        Resolver for fetching ChatMessage objects by creator for user profiles.

        Args:
            info (graphene.ResolveInfo): GraphQL resolve info
            creator_id (str): Global Relay ID for User
            first (int): Number of messages to return (default 10)
            msg_type (Optional[str]): Filter by message type (HUMAN, AI_AGENT, SYSTEM)
            order_by (Optional[str]): Field to order by. Defaults to "-created"

        Returns:
            QuerySet[ChatMessage]: Filtered and ordered chat messages
        """
        queryset = (
            BaseService.filter_visible(
                ChatMessage, info.context.user, request=info.context
            )
            .select_related("conversation", "creator")
            .prefetch_related("votes")
        )

        # Apply creator filter
        creator_pk = from_global_id(creator_id)[1]
        queryset = queryset.filter(creator_id=creator_pk)

        # Apply msg_type filter if provided
        if msg_type:
            # Validate msg_type against MessageTypeChoices
            valid_types = [choice.value for choice in MessageTypeChoices]
            if msg_type in valid_types:
                queryset = queryset.filter(msg_type=msg_type)

        # Apply ordering
        valid_order_fields = {
            "created",
            "-created",
            "modified",
            "-modified",
        }

        order_field = order_by if order_by in valid_order_fields else "-created"
        queryset = queryset.order_by(order_field)

        # Limit results
        return queryset[:first]

    @login_required
    def resolve_chat_message(self, info: graphene.ResolveInfo, **kwargs) -> ChatMessage:
        """
        Resolver for fetching a single ChatMessage by global Relay ID.

        Args:
            info (graphene.ResolveInfo): GraphQL resolve info.
            **kwargs: Any additional keyword arguments passed from the GraphQL query.

        Returns:
            ChatMessage: A single ChatMessage object visible to the current user.

        Raises:
            ChatMessage.DoesNotExist: If the object doesn't exist or is inaccessible.
        """
        django_pk = from_global_id(kwargs["id"])[1]
        obj = BaseService.get_or_none(
            ChatMessage, django_pk, info.context.user, request=info.context
        )
        if obj is None:
            raise ChatMessage.DoesNotExist("ChatMessage matching query does not exist.")
        return obj

    # MODERATION QUERIES ##################################################
    moderation_actions = DjangoFilterConnectionField(
        ModerationActionType,
        filterset_class=ModerationActionFilter,
        corpus_id=graphene.ID(),
        thread_id=graphene.ID(),
        moderator_id=graphene.ID(),
        action_types=graphene.List(graphene.String),
        automated_only=graphene.Boolean(),
        description="Query moderation action audit logs with filtering",
    )

    @login_required
    def resolve_moderation_actions(
        self,
        info,
        corpus_id=None,
        thread_id=None,
        moderator_id=None,
        action_types=None,
        automated_only=None,
        **kwargs,
    ) -> Any:
        """
        Resolve moderation action audit logs with optional filters.

        Permissions:
            - Superusers: can see all actions
            - Corpus owners: can see actions on their corpuses
            - Moderators: can see actions on corpuses they moderate

        Performance:
            Uses select_related for conversation, corpus, message, and moderator
            to avoid N+1 queries. Results are ordered by created descending.

        Args:
            corpus_id: Filter to specific corpus (global ID)
            thread_id: Filter to specific thread/conversation (global ID)
            moderator_id: Filter to specific moderator (global ID)
            action_types: List of action types to include (e.g., ["lock_thread"])
            automated_only: If True, only show automated actions (no moderator)
        """
        user = info.context.user

        # Start with base queryset
        qs = ModerationAction.objects.select_related(
            "conversation",
            "conversation__chat_with_corpus",
            "message",
            "moderator",
        )

        # Filter by corpus ownership or moderator status (unless superuser)
        if not user.is_superuser:
            qs = qs.filter(
                Q(conversation__chat_with_corpus__creator=user)
                | Q(conversation__chat_with_corpus__moderators__user=user)
            ).distinct()

        # Apply optional filters
        if corpus_id:
            corpus_pk = int(from_global_id(corpus_id)[1])
            qs = qs.filter(conversation__chat_with_corpus_id=corpus_pk)

        if thread_id:
            thread_pk = from_global_id(thread_id)[1]
            qs = qs.filter(conversation_id=thread_pk)

        if moderator_id:
            moderator_pk = int(from_global_id(moderator_id)[1])
            qs = qs.filter(moderator_id=moderator_pk)

        if action_types:
            qs = qs.filter(action_type__in=action_types)

        if automated_only:
            qs = qs.filter(moderator__isnull=True)

        return qs.order_by("-created")

    moderation_action = graphene.Field(
        ModerationActionType,
        id=graphene.ID(required=True),
        description="Get a specific moderation action by ID",
    )

    @login_required
    def resolve_moderation_action(self, info, id) -> Any:
        """
        Resolve a single moderation action by ID.

        Permissions (delegated to ``Conversation.can_moderate``):
            - Superusers: can see any action
            - Conversation creator: can see actions on their conversations
            - Corpus owner / designated moderator (when chat_with_corpus is set)
            - Document owner (when chat_with_document is set)
            - Returns None if user lacks permission (prevents ID enumeration)

        Closes #1594: previously the resolver short-circuited to ``return
        action`` whenever ``conversation.chat_with_corpus`` was ``None``,
        leaking document-only and orphaned moderation actions to any
        authenticated user. We now route every case through
        ``Conversation.can_moderate``, which is the canonical authorization
        helper used by the moderation mutations themselves.

        Args:
            id: Global ID of the moderation action
        """
        user = info.context.user
        pk = from_global_id(id)[1]

        try:
            action = ModerationAction.objects.select_related(
                "conversation",
                "conversation__chat_with_corpus",
                "conversation__chat_with_document",
                "message",
                "moderator",
            ).get(pk=pk)
        except ModerationAction.DoesNotExist:
            return None

        # Superusers always see every action, including the rare orphan
        # rows where ``conversation`` itself is NULL (the FK is nullable for
        # historical reasons; in practice every real action has one).
        if user.is_superuser:
            return action

        if action.conversation is None:
            # No conversation context → no per-action gate to evaluate
            # safely. Fail closed to mirror the list resolver, which never
            # surfaces these to non-superusers either.
            return None

        if not action.conversation.can_moderate(user):
            return None

        return action

    moderation_metrics = graphene.Field(
        ModerationMetricsType,
        corpus_id=graphene.ID(required=True),
        time_range_hours=graphene.Int(default_value=24),
        description="Get moderation metrics for a corpus",
    )

    @login_required
    def resolve_moderation_metrics(self, info, corpus_id, time_range_hours=24) -> Any:
        """
        Resolve aggregated moderation metrics for a corpus.

        Computes summary statistics of moderation activity including total actions,
        automated vs manual breakdown, per-type counts, and threshold alerts.

        Permissions:
            - Superusers: can see metrics for any corpus
            - Corpus owners/moderators: can see metrics for their corpuses

        Performance:
            Uses database aggregation (Count) to compute metrics efficiently
            without loading all action records into memory.

        Args:
            corpus_id: Global ID of the corpus
            time_range_hours: Number of hours to look back (default: 24)

        Returns:
            ModerationMetricsType with counts, rates, and threshold warnings
        """
        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
        except Corpus.DoesNotExist:
            return None

        # Check permission via the canonical Corpus.user_can_moderate helper
        if not corpus.user_can_moderate(user):
            return None

        end_time = timezone.now()
        start_time = end_time - timedelta(hours=time_range_hours)

        # Get actions in time range
        actions = ModerationAction.objects.filter(
            conversation__chat_with_corpus=corpus,
            created__gte=start_time,
            created__lte=end_time,
        )

        total = actions.count()
        automated = actions.filter(moderator__isnull=True).count()
        manual = total - automated

        # Actions by type
        by_type = dict(
            actions.values("action_type")
            .annotate(count=Count("id"))
            .values_list("action_type", "count")
        )

        # Hourly rate
        hourly_rate = total / time_range_hours if time_range_hours > 0 else 0

        # Threshold check for high activity warning
        from opencontractserver.constants.moderation import (
            MODERATION_HOURLY_RATE_THRESHOLD,
        )

        exceeded_types = [
            action_type
            for action_type, count in by_type.items()
            if count / time_range_hours > MODERATION_HOURLY_RATE_THRESHOLD
        ]

        return {
            "total_actions": total,
            "automated_actions": automated,
            "manual_actions": manual,
            "actions_by_type": by_type,
            "hourly_action_rate": round(hourly_rate, 2),
            "is_above_threshold": len(exceeded_types) > 0,
            "threshold_exceeded_types": exceeded_types,
            "time_range_hours": time_range_hours,
            "start_time": start_time,
            "end_time": end_time,
        }
