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
from datetime import timedelta
from typing import Annotated

import strawberry
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from graphql_relay import from_global_id

from config.graphql import enums
from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.filtering import setup_filterset
from config.graphql.core.relay import (
    get_node_from_global_id,
    resolve_django_connection,
)
from config.graphql.filters import ConversationFilter, ModerationActionFilter
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageTypeChoices,
    ModerationAction,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


def _resolve_Query_conversations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_queries.py:46

    Port of ConversationQueryMixin.resolve_conversations
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


def q_conversations(
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
    created_at__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="createdAt_Gte")
    ] = strawberry.UNSET,
    created_at__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="createdAt_Lte")
    ] = strawberry.UNSET,
    conversation_type: Annotated[
        enums.ConversationTypeEnum | None,
        strawberry.argument(name="conversationType"),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str | None, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        str | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    has_corpus: Annotated[
        bool | None, strawberry.argument(name="hasCorpus")
    ] = strawberry.UNSET,
    has_document: Annotated[
        bool | None, strawberry.argument(name="hasDocument")
    ] = strawberry.UNSET,
    title__contains: Annotated[
        str | None, strawberry.argument(name="title_Contains")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        ConversationTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "created_at__gte": created_at__gte,
            "created_at__lte": created_at__lte,
            "conversation_type": conversation_type,
            "document_id": document_id,
            "corpus_id": corpus_id,
            "has_corpus": has_corpus,
            "has_document": has_document,
            "title__contains": title__contains,
        }
    )
    resolved = _resolve_Query_conversations(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="ConversationType",
        default_manager=Conversation._default_manager,
        filterset_class=setup_filterset(ConversationFilter),
        filter_args={
            "created_at__gte": "created_at__gte",
            "created_at__lte": "created_at__lte",
            "conversation_type": "conversation_type",
            "document_id": "document_id",
            "corpus_id": "corpus_id",
            "has_corpus": "has_corpus",
            "has_document": "has_document",
            "title__contains": "title__contains",
        },
    )


def _resolve_Query_search_conversations(
    root,
    info,
    query,
    corpus_id=None,
    document_id=None,
    conversation_type=None,
    top_k=100,
    **kwargs,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_queries.py:96

    Port of ConversationQueryMixin.resolve_search_conversations
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


def q_search_conversations(
    info: strawberry.Info,
    query: Annotated[
        str, strawberry.argument(name="query", description="Search query text")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(name="corpusId", description="Filter by corpus ID"),
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(name="documentId", description="Filter by document ID"),
    ] = strawberry.UNSET,
    conversation_type: Annotated[
        str | None,
        strawberry.argument(
            name="conversationType",
            description="Filter by conversation type (chat/thread)",
        ),
    ] = strawberry.UNSET,
    top_k: Annotated[
        int | None,
        strawberry.argument(
            name="topK",
            description="Maximum number of results to fetch from vector store",
        ),
    ] = 100,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
) -> None | (
    Annotated[
        ConversationConnection, strawberry.lazy("config.graphql.conversation_types")
    ]
):
    kwargs = strip_unset(
        {
            "query": query,
            "corpus_id": corpus_id,
            "document_id": document_id,
            "conversation_type": conversation_type,
            "top_k": top_k,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_search_conversations(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="ConversationType",
        default_manager=Conversation._default_manager,
    )


@login_required
def _resolve_Query_search_messages(
    root, info, query, corpus_id=None, conversation_id=None, msg_type=None, top_k=10
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:190

    Port of ConversationQueryMixin.resolve_search_messages
    """
    from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (
        CoreChatMessageVectorStore,
        VectorSearchQuery,
    )

    # Convert global IDs to database IDs
    corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None
    conversation_pk = from_global_id(conversation_id)[1] if conversation_id else None

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


def q_search_messages(
    info: strawberry.Info,
    query: Annotated[
        str, strawberry.argument(name="query", description="Search query text")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(name="corpusId", description="Filter by corpus ID"),
    ] = strawberry.UNSET,
    conversation_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="conversationId", description="Filter by conversation ID"
        ),
    ] = strawberry.UNSET,
    msg_type: Annotated[
        str | None,
        strawberry.argument(
            name="msgType", description="Filter by message type (HUMAN/LLM/SYSTEM)"
        ),
    ] = strawberry.UNSET,
    top_k: Annotated[
        int | None,
        strawberry.argument(name="topK", description="Number of results to return"),
    ] = 10,
) -> None | (
    list[
        None
        | (Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")])
    ]
):
    kwargs = strip_unset(
        {
            "query": query,
            "corpus_id": corpus_id,
            "conversation_id": conversation_id,
            "msg_type": msg_type,
            "top_k": top_k,
        }
    )
    return _resolve_Query_search_messages(None, info, **kwargs)


@login_required
def _resolve_Query_chat_messages(root, info, conversation_id, order_by=None, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:260

    Port of ConversationQueryMixin.resolve_chat_messages
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


def q_chat_messages(
    info: strawberry.Info,
    conversation_id: Annotated[
        strawberry.ID, strawberry.argument(name="conversationId")
    ] = strawberry.UNSET,
    order_by: Annotated[
        str | None, strawberry.argument(name="orderBy")
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")])
    ]
):
    kwargs = strip_unset({"conversation_id": conversation_id, "order_by": order_by})
    return _resolve_Query_chat_messages(None, info, **kwargs)


def q_chat_message(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")]
):
    return get_node_from_global_id(info, id, only_type_name="MessageType")


@login_required
def _resolve_Query_user_messages(
    root, info, creator_id, first=10, msg_type=None, order_by=None, **kwargs
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:317

    Port of ConversationQueryMixin.resolve_user_messages
    """
    queryset = (
        BaseService.filter_visible(ChatMessage, info.context.user, request=info.context)
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


def q_user_messages(
    info: strawberry.Info,
    creator_id: Annotated[
        strawberry.ID, strawberry.argument(name="creatorId")
    ] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = 10,
    msg_type: Annotated[
        str | None, strawberry.argument(name="msgType")
    ] = strawberry.UNSET,
    order_by: Annotated[
        str | None, strawberry.argument(name="orderBy")
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")])
    ]
):
    kwargs = strip_unset(
        {
            "creator_id": creator_id,
            "first": first,
            "msg_type": msg_type,
            "order_by": order_by,
        }
    )
    return _resolve_Query_user_messages(None, info, **kwargs)


@login_required
def _resolve_Query_moderation_actions(
    root,
    info,
    corpus_id=None,
    thread_id=None,
    moderator_id=None,
    action_types=None,
    automated_only=None,
    **kwargs,
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:408

    Port of ConversationQueryMixin.resolve_moderation_actions
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


def q_moderation_actions(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    thread_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="threadId")
    ] = strawberry.UNSET,
    moderator_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="moderatorId")
    ] = strawberry.UNSET,
    action_types: Annotated[
        list[str | None] | None, strawberry.argument(name="actionTypes")
    ] = strawberry.UNSET,
    automated_only: Annotated[
        bool | None, strawberry.argument(name="automatedOnly")
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
    action_type: Annotated[
        enums.ConversationsModerationActionActionTypeChoices | None,
        strawberry.argument(name="actionType"),
    ] = strawberry.UNSET,
    action_type__in: Annotated[
        list[enums.ConversationsModerationActionActionTypeChoices | None] | None,
        strawberry.argument(name="actionType_In"),
    ] = strawberry.UNSET,
    created__gte: Annotated[
        datetime.datetime | None, strawberry.argument(name="created_Gte")
    ] = strawberry.UNSET,
    created__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="created_Lte")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        ModerationActionTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]
):
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "thread_id": thread_id,
            "moderator_id": moderator_id,
            "action_types": action_types,
            "automated_only": automated_only,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "action_type": action_type,
            "action_type__in": action_type__in,
            "created__gte": created__gte,
            "created__lte": created__lte,
        }
    )
    resolved = _resolve_Query_moderation_actions(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="ModerationActionType",
        default_manager=ModerationAction._default_manager,
        filterset_class=setup_filterset(ModerationActionFilter),
        filter_args={
            "action_type": "action_type",
            "action_type__in": "action_type__in",
            "created__gte": "created__gte",
            "created__lte": "created__lte",
        },
    )


@login_required
def _resolve_Query_moderation_action(root, info, id, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:482

    Port of ConversationQueryMixin.resolve_moderation_action
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


def q_moderation_action(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
) -> None | (
    Annotated[
        ModerationActionType, strawberry.lazy("config.graphql.conversation_types")
    ]
):
    kwargs = strip_unset({"id": id})
    return _resolve_Query_moderation_action(None, info, **kwargs)


@login_required
def _resolve_Query_moderation_metrics(
    root, info, corpus_id, time_range_hours=24, **kwargs
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:542

    Port of ConversationQueryMixin.resolve_moderation_metrics
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

    from config.graphql.conversation_types import ModerationMetricsType

    return ModerationMetricsType(
        total_actions=total,
        automated_actions=automated,
        manual_actions=manual,
        actions_by_type=by_type,
        hourly_action_rate=round(hourly_rate, 2),
        is_above_threshold=len(exceeded_types) > 0,
        threshold_exceeded_types=exceeded_types,
        time_range_hours=time_range_hours,
        start_time=start_time,
        end_time=end_time,
    )


def q_moderation_metrics(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    time_range_hours: Annotated[
        int | None, strawberry.argument(name="timeRangeHours")
    ] = 24,
) -> None | (
    Annotated[
        ModerationMetricsType, strawberry.lazy("config.graphql.conversation_types")
    ]
):
    kwargs = strip_unset({"corpus_id": corpus_id, "time_range_hours": time_range_hours})
    return _resolve_Query_moderation_metrics(None, info, **kwargs)


QUERY_FIELDS = {
    "conversations": strawberry.field(
        resolver=q_conversations,
        name="conversations",
        description="Retrieve conversations, optionally filtered by document_id or corpus_id",
    ),
    "search_conversations": strawberry.field(
        resolver=q_search_conversations,
        name="searchConversations",
        description="Search conversations using vector similarity with pagination",
    ),
    "search_messages": strawberry.field(
        resolver=q_search_messages,
        name="searchMessages",
        description="Search messages using vector similarity",
    ),
    "chat_messages": strawberry.field(resolver=q_chat_messages, name="chatMessages"),
    "chat_message": strawberry.field(resolver=q_chat_message, name="chatMessage"),
    "user_messages": strawberry.field(
        resolver=q_user_messages,
        name="userMessages",
        description="Get messages created by a specific user, with optional filtering and pagination",
    ),
    "moderation_actions": strawberry.field(
        resolver=q_moderation_actions,
        name="moderationActions",
        description="Query moderation action audit logs with filtering",
    ),
    "moderation_action": strawberry.field(
        resolver=q_moderation_action,
        name="moderationAction",
        description="Get a specific moderation action by ID",
    ),
    "moderation_metrics": strawberry.field(
        resolver=q_moderation_metrics,
        name="moderationMetrics",
        description="Get moderation metrics for a corpus",
    ),
}
