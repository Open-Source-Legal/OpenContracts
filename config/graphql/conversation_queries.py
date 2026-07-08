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
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

from config.graphql.filters import ConversationFilter
from config.graphql.filters import ModerationActionFilter
from opencontractserver.conversations.models import Conversation
from opencontractserver.conversations.models import ModerationAction


def _resolve_Query_conversations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_queries.py:46

    Port of ConversationQueryMixin.resolve_conversations
    """
    raise NotImplementedError("_resolve_Query_conversations not yet ported — see manifest")


def q_conversations(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, created_at__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Gte")] = strawberry.UNSET, created_at__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Lte")] = strawberry.UNSET, conversation_type: Annotated[Optional[enums.ConversationTypeEnum], strawberry.argument(name="conversationType")] = strawberry.UNSET, document_id: Annotated[Optional[str], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId")] = strawberry.UNSET, has_corpus: Annotated[Optional[bool], strawberry.argument(name="hasCorpus")] = strawberry.UNSET, has_document: Annotated[Optional[bool], strawberry.argument(name="hasDocument")] = strawberry.UNSET, title__contains: Annotated[Optional[str], strawberry.argument(name="title_Contains")] = strawberry.UNSET) -> Optional[Annotated["ConversationTypeConnection", strawberry.lazy("config.graphql.conversation_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "created_at__gte": created_at__gte, "created_at__lte": created_at__lte, "conversation_type": conversation_type, "document_id": document_id, "corpus_id": corpus_id, "has_corpus": has_corpus, "has_document": has_document, "title__contains": title__contains})
    resolved = _resolve_Query_conversations(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ConversationType", default_manager=Conversation._default_manager, filterset_class=setup_filterset(ConversationFilter), filter_args={"created_at__gte": "created_at__gte", "created_at__lte": "created_at__lte", "conversation_type": "conversation_type", "document_id": "document_id", "corpus_id": "corpus_id", "has_corpus": "has_corpus", "has_document": "has_document", "title__contains": "title__contains"}, )


def _resolve_Query_search_conversations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_queries.py:96

    Port of ConversationQueryMixin.resolve_search_conversations
    """
    raise NotImplementedError("_resolve_Query_search_conversations not yet ported — see manifest")


def q_search_conversations(info: strawberry.Info, query: Annotated[str, strawberry.argument(name="query", description='Search query text')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Filter by corpus ID')] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId", description='Filter by document ID')] = strawberry.UNSET, conversation_type: Annotated[Optional[str], strawberry.argument(name="conversationType", description='Filter by conversation type (chat/thread)')] = strawberry.UNSET, top_k: Annotated[Optional[int], strawberry.argument(name="topK", description='Maximum number of results to fetch from vector store')] = 100, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["ConversationConnection", strawberry.lazy("config.graphql.conversation_types")]]:
    kwargs = strip_unset({"query": query, "corpus_id": corpus_id, "document_id": document_id, "conversation_type": conversation_type, "top_k": top_k, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_search_conversations(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ConversationType", default_manager=Conversation._default_manager, )


def _resolve_Query_search_messages(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:190

    Port of ConversationQueryMixin.resolve_search_messages
    """
    raise NotImplementedError("_resolve_Query_search_messages not yet ported — see manifest")


def q_search_messages(info: strawberry.Info, query: Annotated[str, strawberry.argument(name="query", description='Search query text')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Filter by corpus ID')] = strawberry.UNSET, conversation_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="conversationId", description='Filter by conversation ID')] = strawberry.UNSET, msg_type: Annotated[Optional[str], strawberry.argument(name="msgType", description='Filter by message type (HUMAN/LLM/SYSTEM)')] = strawberry.UNSET, top_k: Annotated[Optional[int], strawberry.argument(name="topK", description='Number of results to return')] = 10) -> Optional[list[Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]]]]:
    kwargs = strip_unset({"query": query, "corpus_id": corpus_id, "conversation_id": conversation_id, "msg_type": msg_type, "top_k": top_k})
    return _resolve_Query_search_messages(None, info, **kwargs)


def _resolve_Query_chat_messages(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:260

    Port of ConversationQueryMixin.resolve_chat_messages
    """
    raise NotImplementedError("_resolve_Query_chat_messages not yet ported — see manifest")


def q_chat_messages(info: strawberry.Info, conversation_id: Annotated[strawberry.ID, strawberry.argument(name="conversationId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]]]]:
    kwargs = strip_unset({"conversation_id": conversation_id, "order_by": order_by})
    return _resolve_Query_chat_messages(None, info, **kwargs)


def q_chat_message(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]]:
    return get_node_from_global_id(info, id, only_type_name="MessageType")


def _resolve_Query_user_messages(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:317

    Port of ConversationQueryMixin.resolve_user_messages
    """
    raise NotImplementedError("_resolve_Query_user_messages not yet ported — see manifest")


def q_user_messages(info: strawberry.Info, creator_id: Annotated[strawberry.ID, strawberry.argument(name="creatorId")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = 10, msg_type: Annotated[Optional[str], strawberry.argument(name="msgType")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]]]]:
    kwargs = strip_unset({"creator_id": creator_id, "first": first, "msg_type": msg_type, "order_by": order_by})
    return _resolve_Query_user_messages(None, info, **kwargs)


def _resolve_Query_moderation_actions(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:408

    Port of ConversationQueryMixin.resolve_moderation_actions
    """
    raise NotImplementedError("_resolve_Query_moderation_actions not yet ported — see manifest")


def q_moderation_actions(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, thread_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="threadId")] = strawberry.UNSET, moderator_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="moderatorId")] = strawberry.UNSET, action_types: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="actionTypes")] = strawberry.UNSET, automated_only: Annotated[Optional[bool], strawberry.argument(name="automatedOnly")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, action_type: Annotated[Optional[enums.ConversationsModerationActionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, action_type__in: Annotated[Optional[list[Optional[enums.ConversationsModerationActionActionTypeChoices]]], strawberry.argument(name="actionType_In")] = strawberry.UNSET, created__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="created_Gte")] = strawberry.UNSET, created__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="created_Lte")] = strawberry.UNSET) -> Optional[Annotated["ModerationActionTypeConnection", strawberry.lazy("config.graphql.conversation_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "thread_id": thread_id, "moderator_id": moderator_id, "action_types": action_types, "automated_only": automated_only, "offset": offset, "before": before, "after": after, "first": first, "last": last, "action_type": action_type, "action_type__in": action_type__in, "created__gte": created__gte, "created__lte": created__lte})
    resolved = _resolve_Query_moderation_actions(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ModerationActionType", default_manager=ModerationAction._default_manager, filterset_class=setup_filterset(ModerationActionFilter), filter_args={"action_type": "action_type", "action_type__in": "action_type__in", "created__gte": "created__gte", "created__lte": "created__lte"}, )


def _resolve_Query_moderation_action(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:482

    Port of ConversationQueryMixin.resolve_moderation_action
    """
    raise NotImplementedError("_resolve_Query_moderation_action not yet ported — see manifest")


def q_moderation_action(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional[Annotated["ModerationActionType", strawberry.lazy("config.graphql.conversation_types")]]:
    kwargs = strip_unset({"id": id})
    return _resolve_Query_moderation_action(None, info, **kwargs)


def _resolve_Query_moderation_metrics(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:542

    Port of ConversationQueryMixin.resolve_moderation_metrics
    """
    raise NotImplementedError("_resolve_Query_moderation_metrics not yet ported — see manifest")


def q_moderation_metrics(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, time_range_hours: Annotated[Optional[int], strawberry.argument(name="timeRangeHours")] = 24) -> Optional[Annotated["ModerationMetricsType", strawberry.lazy("config.graphql.conversation_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "time_range_hours": time_range_hours})
    return _resolve_Query_moderation_metrics(None, info, **kwargs)



QUERY_FIELDS = {
    "conversations": strawberry.field(resolver=q_conversations, name="conversations", description='Retrieve conversations, optionally filtered by document_id or corpus_id'),
    "search_conversations": strawberry.field(resolver=q_search_conversations, name="searchConversations", description='Search conversations using vector similarity with pagination'),
    "search_messages": strawberry.field(resolver=q_search_messages, name="searchMessages", description='Search messages using vector similarity'),
    "chat_messages": strawberry.field(resolver=q_chat_messages, name="chatMessages"),
    "chat_message": strawberry.field(resolver=q_chat_message, name="chatMessage"),
    "user_messages": strawberry.field(resolver=q_user_messages, name="userMessages", description='Get messages created by a specific user, with optional filtering and pagination'),
    "moderation_actions": strawberry.field(resolver=q_moderation_actions, name="moderationActions", description='Query moderation action audit logs with filtering'),
    "moderation_action": strawberry.field(resolver=q_moderation_action, name="moderationAction", description='Get a specific moderation action by ID'),
    "moderation_metrics": strawberry.field(resolver=q_moderation_metrics, name="moderationMetrics", description='Get moderation metrics for a corpus'),
}
