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

from config.graphql.filters import AnnotationFilter
from opencontractserver.agents.models import AgentActionResult
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import ChatMessage
from opencontractserver.conversations.models import Conversation
from opencontractserver.conversations.models import ModerationAction
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.notifications.models import Notification


def _resolve_ConversationType_conversation_type(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:473

    Port of ConversationType.resolve_conversation_type
    """
    raise NotImplementedError("_resolve_ConversationType_conversation_type not yet ported — see manifest")


def _resolve_ConversationType_all_messages(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:470

    Port of ConversationType.resolve_all_messages
    """
    raise NotImplementedError("_resolve_ConversationType_all_messages not yet ported — see manifest")


def _resolve_ConversationType_user_vote(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:479

    Port of ConversationType.resolve_user_vote
    """
    raise NotImplementedError("_resolve_ConversationType_user_vote not yet ported — see manifest")


@strawberry.type(name="ConversationType")
class ConversationType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="title", description='Optional title for the conversation')
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="description", description='Optional description for the conversation')
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    created_at: datetime.datetime = strawberry.field(name="createdAt", description='Timestamp when the conversation was created', default=None)
    updated_at: datetime.datetime = strawberry.field(name="updatedAt", description='Timestamp when the conversation was last updated', default=None)
    @strawberry.field(name="conversationType", description='Type of conversation (chat or thread)')
    def conversation_type(self, info: strawberry.Info) -> Optional[enums.ConversationTypeEnum]:
        kwargs = strip_unset({})
        return _resolve_ConversationType_conversation_type(self, info, **kwargs)
    deleted_at: Optional[datetime.datetime] = strawberry.field(name="deletedAt", description='Timestamp when the conversation was soft-deleted', default=None)
    is_locked: bool = strawberry.field(name="isLocked", description='Whether the thread is locked (prevents new messages)', default=None)
    locked_at: Optional[datetime.datetime] = strawberry.field(name="lockedAt", description='Timestamp when the thread was locked', default=None)
    locked_by: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="lockedBy", description='Moderator who locked the thread', default=None)
    is_pinned: bool = strawberry.field(name="isPinned", description='Whether the thread is pinned (appears at top of list)', default=None)
    pinned_at: Optional[datetime.datetime] = strawberry.field(name="pinnedAt", description='Timestamp when the thread was pinned', default=None)
    pinned_by: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="pinnedBy", description='Moderator who pinned the thread', default=None)
    upvote_count: int = strawberry.field(name="upvoteCount", description='Cached count of upvotes for this conversation/thread', default=None)
    downvote_count: int = strawberry.field(name="downvoteCount", description='Cached count of downvotes for this conversation/thread', default=None)
    chat_with_corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="chatWithCorpus", description='The corpus to which this conversation belongs', default=None)
    chat_with_document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="chatWithDocument", description='The document to which this conversation belongs', default=None)
    @strawberry.field(name="compactionSummary", description='Summary of compacted (older) messages.  Empty when no compaction has occurred.')
    def compaction_summary(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "compaction_summary", None))
    compacted_before_message_id: Optional[BigInt] = strawberry.field(name="compactedBeforeMessageId", description='ID of the last message that was folded into compaction_summary.  Messages with id <= this value are excluded from LLM context (but kept in the DB).  Stored as a plain integer (not a ForeignKey) so the id__gt filter remains valid even if the cutoff message is deleted.', default=None)
    memory_curated: bool = strawberry.field(name="memoryCurated", description='Whether this conversation has been curated for corpus memory.', default=None)
    @strawberry.field(name="corpusActionExecutions", description='The thread that triggered this execution (for thread-based actions)')
    def corpus_action_executions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "corpus_action_executions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="chatMessages", description='The conversation to which this chat message belongs')
    def chat_messages(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "MessageTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "chat_messages", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="MessageType", )
    @strawberry.field(name="moderationActions", description='The conversation that was moderated')
    def moderation_actions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "ModerationActionTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "moderation_actions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ModerationActionType", )
    @strawberry.field(name="notifications", description='Related conversation/thread if applicable')
    def notifications(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, is_read: Annotated[Optional[bool], strawberry.argument(name="isRead")] = strawberry.UNSET, notification_type: Annotated[Optional[enums.NotificationsNotificationNotificationTypeChoices], strawberry.argument(name="notificationType")] = strawberry.UNSET, created_at__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Lte")] = strawberry.UNSET, created_at__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Gte")] = strawberry.UNSET) -> Annotated["NotificationTypeConnection", strawberry.lazy("config.graphql.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "is_read": is_read, "notification_type": notification_type, "created_at__lte": created_at__lte, "created_at__gte": created_at__gte})
        resolved = getattr(self, "notifications", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NotificationType", filterset_class=filterset_factory(Notification, fields={'is_read': ['exact'], 'notification_type': ['exact'], 'created_at': ['lte', 'gte']}), filter_args={"is_read": "is_read", "notification_type": "notification_type", "created_at__lte": "created_at__lte", "created_at__gte": "created_at__gte"}, )
    @strawberry.field(name="corpusActionResults", description='Conversation record containing the full agent interaction')
    def corpus_action_results(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.AgentsAgentActionResultStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["AgentActionResultTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "creator__id": creator__id})
        resolved = getattr(self, "corpus_action_results", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentActionResultType", filterset_class=filterset_factory(AgentActionResult, fields={'id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "creator__id": "creator__id"}, )
    @strawberry.field(name="triggeredAgentActionResults", description='Thread that triggered this agent action (for thread-based triggers)')
    def triggered_agent_action_results(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.AgentsAgentActionResultStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["AgentActionResultTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "creator__id": creator__id})
        resolved = getattr(self, "triggered_agent_action_results", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentActionResultType", filterset_class=filterset_factory(AgentActionResult, fields={'id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "creator__id": "creator__id"}, )
    @strawberry.field(name="researchReports", description='Chat conversation that kicked this off, if any')
    def research_reports(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ResearchReportTypeConnection", strawberry.lazy("config.graphql.research_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "research_reports", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ResearchReportType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="allMessages")
    def all_messages(self, info: strawberry.Info) -> Optional[list[Optional["MessageType"]]]:
        kwargs = strip_unset({})
        return _resolve_ConversationType_all_messages(self, info, **kwargs)
    @strawberry.field(name="userVote", description="Current user's vote on this conversation: 'UPVOTE', 'DOWNVOTE', or null")
    def user_vote(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_ConversationType_user_vote(self, info, **kwargs)


def _get_queryset_ConversationType(queryset, info):
    """PORT: config.graphql.conversation_types.ConversationType.get_queryset

    Port of ConversationType.get_queryset
    """
    raise NotImplementedError("_get_queryset_ConversationType not yet ported — see manifest")


def _get_node_ConversationType(info, pk):
    """PORT: config.graphql.conversation_types.ConversationType.get_node

    Port of ConversationType.get_node
    """
    raise NotImplementedError("_get_node_ConversationType not yet ported — see manifest")


register_type("ConversationType", ConversationType, model=Conversation, get_queryset=_get_queryset_ConversationType, get_node=_get_node_ConversationType)


ConversationTypeConnection = make_connection_types(ConversationType, type_name="ConversationTypeConnection", countable=True, pdf_page_aware=False)


ConversationConnection = make_connection_types(ConversationType, type_name="ConversationConnection", countable=True, pdf_page_aware=False)


def _resolve_MessageType_msg_type(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:399

    Port of MessageType.resolve_msg_type
    """
    raise NotImplementedError("_resolve_MessageType_msg_type not yet ported — see manifest")


def _resolve_MessageType_agent_type(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:408

    Port of MessageType.resolve_agent_type
    """
    raise NotImplementedError("_resolve_MessageType_agent_type not yet ported — see manifest")


def _resolve_MessageType_agent_configuration(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:414

    Port of MessageType.resolve_agent_configuration
    """
    raise NotImplementedError("_resolve_MessageType_agent_configuration not yet ported — see manifest")


def _resolve_MessageType_mentioned_resources(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:438

    Port of MessageType.resolve_mentioned_resources
    """
    raise NotImplementedError("_resolve_MessageType_mentioned_resources not yet ported — see manifest")


def _resolve_MessageType_user_vote(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:418

    Port of MessageType.resolve_user_vote
    """
    raise NotImplementedError("_resolve_MessageType_user_vote not yet ported — see manifest")


@strawberry.type(name="MessageType")
class MessageType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    conversation: "ConversationType" = strawberry.field(name="conversation", description='The conversation to which this chat message belongs', default=None)
    @strawberry.field(name="msgType", description='The type of message (SYSTEM, HUMAN, or LLM)')
    def msg_type(self, info: strawberry.Info) -> enums.ConversationsChatMessageMsgTypeChoices:
        kwargs = strip_unset({})
        return _resolve_MessageType_msg_type(self, info, **kwargs)
    @strawberry.field(name="agentType", description='Type of agent that generated this message')
    def agent_type(self, info: strawberry.Info) -> Optional[enums.AgentTypeEnum]:
        kwargs = strip_unset({})
        return _resolve_MessageType_agent_type(self, info, **kwargs)
    @strawberry.field(name="agentConfiguration", description='Agent configuration that generated this message')
    def agent_configuration(self, info: strawberry.Info) -> Optional[Annotated["AgentConfigurationType", strawberry.lazy("config.graphql.agent_types")]]:
        kwargs = strip_unset({})
        return _resolve_MessageType_agent_configuration(self, info, **kwargs)
    parent_message: Optional["MessageType"] = strawberry.field(name="parentMessage", description='Parent message for threaded replies', default=None)
    @strawberry.field(name="content", description='The textual content of the chat message')
    def content(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "content", None))
    data: Optional[GenericScalar] = strawberry.field(name="data", default=None)
    created_at: datetime.datetime = strawberry.field(name="createdAt", description='Timestamp when the chat message was created', default=None)
    deleted_at: Optional[datetime.datetime] = strawberry.field(name="deletedAt", description='Timestamp when the message was soft-deleted', default=None)
    source_document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="sourceDocument", description='A document that this chat message is based on', default=None)
    @strawberry.field(name="sourceAnnotations", description='Annotations that this chat message is based on')
    def source_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "source_annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="createdAnnotations", description='Annotations that this chat message created')
    def created_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "created_annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="mentionedAgents", description='Agents mentioned in this message that should respond')
    def mentioned_agents(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, scope: Annotated[Optional[enums.AgentsAgentConfigurationScopeChoices], strawberry.argument(name="scope")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET, corpus: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus")] = strawberry.UNSET) -> Annotated["AgentConfigurationTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "scope": scope, "is_active": is_active, "corpus": corpus})
        resolved = getattr(self, "mentioned_agents", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentConfigurationType", filterset_class=filterset_factory(AgentConfiguration, fields={'scope': ['exact'], 'is_active': ['exact'], 'corpus': ['exact']}), filter_args={"scope": "scope", "is_active": "is_active", "corpus": "corpus"}, )
    @strawberry.field(name="state", description='Lifecycle state of the message for quick filtering')
    def state(self, info: strawberry.Info) -> enums.ConversationsChatMessageStateChoices:
        return coerce_enum(enums.ConversationsChatMessageStateChoices, getattr(self, "state", None))
    upvote_count: int = strawberry.field(name="upvoteCount", description='Cached count of upvotes for this message', default=None)
    downvote_count: int = strawberry.field(name="downvoteCount", description='Cached count of downvotes for this message', default=None)
    @strawberry.field(name="corpusActionExecutions", description='The message that triggered this execution (for NEW_MESSAGE trigger)')
    def corpus_action_executions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "corpus_action_executions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="replies", description='Parent message for threaded replies')
    def replies(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "MessageTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "replies", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="MessageType", )
    @strawberry.field(name="moderationActions", description='The message that was moderated')
    def moderation_actions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "ModerationActionTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "moderation_actions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ModerationActionType", )
    @strawberry.field(name="notifications", description='Related message if applicable')
    def notifications(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, is_read: Annotated[Optional[bool], strawberry.argument(name="isRead")] = strawberry.UNSET, notification_type: Annotated[Optional[enums.NotificationsNotificationNotificationTypeChoices], strawberry.argument(name="notificationType")] = strawberry.UNSET, created_at__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Lte")] = strawberry.UNSET, created_at__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Gte")] = strawberry.UNSET) -> Annotated["NotificationTypeConnection", strawberry.lazy("config.graphql.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "is_read": is_read, "notification_type": notification_type, "created_at__lte": created_at__lte, "created_at__gte": created_at__gte})
        resolved = getattr(self, "notifications", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NotificationType", filterset_class=filterset_factory(Notification, fields={'is_read': ['exact'], 'notification_type': ['exact'], 'created_at': ['lte', 'gte']}), filter_args={"is_read": "is_read", "notification_type": "notification_type", "created_at__lte": "created_at__lte", "created_at__gte": "created_at__gte"}, )
    @strawberry.field(name="triggeredAgentActionResults", description='Message that triggered this agent action (for NEW_MESSAGE trigger)')
    def triggered_agent_action_results(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.AgentsAgentActionResultStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["AgentActionResultTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "creator__id": creator__id})
        resolved = getattr(self, "triggered_agent_action_results", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentActionResultType", filterset_class=filterset_factory(AgentActionResult, fields={'id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "creator__id": "creator__id"}, )
    @strawberry.field(name="triggeredResearchReports", description='User chat message that triggered this run, if any')
    def triggered_research_reports(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ResearchReportTypeConnection", strawberry.lazy("config.graphql.research_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "triggered_research_reports", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ResearchReportType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="mentionedResources", description='Corpuses and documents mentioned in this message using @ syntax. Only includes resources visible to the requesting user.')
    def mentioned_resources(self, info: strawberry.Info) -> Optional[list[Optional["MentionedResourceType"]]]:
        kwargs = strip_unset({})
        return _resolve_MessageType_mentioned_resources(self, info, **kwargs)
    @strawberry.field(name="userVote", description="Current user's vote on this message: 'UPVOTE', 'DOWNVOTE', or null")
    def user_vote(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_MessageType_user_vote(self, info, **kwargs)


register_type("MessageType", MessageType, model=ChatMessage)


MessageTypeConnection = make_connection_types(MessageType, type_name="MessageTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_ModerationActionType_corpus_id(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:569

    Port of ModerationActionType.resolve_corpus_id
    """
    raise NotImplementedError("_resolve_ModerationActionType_corpus_id not yet ported — see manifest")


def _resolve_ModerationActionType_is_automated(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:575

    Port of ModerationActionType.resolve_is_automated
    """
    raise NotImplementedError("_resolve_ModerationActionType_is_automated not yet ported — see manifest")


def _resolve_ModerationActionType_can_rollback(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:579

    Port of ModerationActionType.resolve_can_rollback
    """
    raise NotImplementedError("_resolve_ModerationActionType_can_rollback not yet ported — see manifest")


@strawberry.type(name="ModerationActionType", description='GraphQL type for ModerationAction audit records.')
class ModerationActionType(Node):
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    conversation: Optional["ConversationType"] = strawberry.field(name="conversation", description='The conversation that was moderated', default=None)
    message: Optional["MessageType"] = strawberry.field(name="message", description='The message that was moderated', default=None)
    @strawberry.field(name="actionType", description='Type of moderation action taken')
    def action_type(self, info: strawberry.Info) -> enums.ConversationsModerationActionActionTypeChoices:
        return coerce_enum(enums.ConversationsModerationActionActionTypeChoices, getattr(self, "action_type", None))
    moderator: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="moderator", description='Moderator who took this action', default=None)
    @strawberry.field(name="reason", description='Optional reason for the moderation action')
    def reason(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "reason", None))
    @strawberry.field(name="corpusId", description='Corpus ID if action is on a corpus thread')
    def corpus_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        kwargs = strip_unset({})
        return _resolve_ModerationActionType_corpus_id(self, info, **kwargs)
    @strawberry.field(name="isAutomated", description='Whether this was an automated action')
    def is_automated(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_ModerationActionType_is_automated(self, info, **kwargs)
    @strawberry.field(name="canRollback", description='Whether this action can be rolled back')
    def can_rollback(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_ModerationActionType_can_rollback(self, info, **kwargs)


register_type("ModerationActionType", ModerationActionType, model=ModerationAction)


ModerationActionTypeConnection = make_connection_types(ModerationActionType, type_name="ModerationActionTypeConnection", countable=False, pdf_page_aware=False)


@strawberry.type(name="MentionedResourceType", description='Represents a corpus, document, annotation, or agent mentioned in a message.\n\nMention patterns:\n  @corpus:legal-contracts\n  @document:contract-template\n  @corpus:legal-contracts/document:contract-template\n  [text](/d/.../doc?ann=id) -> Annotation mention via markdown link\n  [text](/agents/{slug}) -> Global agent mention via markdown link\n  [text](/c/.../agents/{slug}) -> Corpus-scoped agent mention via markdown link\n\nFor annotations, includes full metadata for rich tooltip display.\nPermission-safe: Only returns resources visible to the requesting user.')
class MentionedResourceType:
    type: str = strawberry.field(name="type", description='Resource type: "corpus", "document", "annotation", or "agent"', default=None)
    id: strawberry.ID = strawberry.field(name="id", description='Global ID of the resource', default=None)
    slug: Optional[str] = strawberry.field(name="slug", description='URL-safe slug (null for annotations)', default=None)
    title: str = strawberry.field(name="title", description='Display title of the resource', default=None)
    url: str = strawberry.field(name="url", description='Frontend URL path to navigate to the resource', default=None)
    corpus: Optional["MentionedResourceType"] = strawberry.field(name="corpus", description='Parent corpus context (for documents within a corpus)', default=None)
    raw_text: Optional[str] = strawberry.field(name="rawText", description='Full annotation text content', default=None)
    annotation_label: Optional[str] = strawberry.field(name="annotationLabel", description="Annotation label name (e.g., 'Section Header', 'Definition')", default=None)
    document: Optional["MentionedResourceType"] = strawberry.field(name="document", description='Parent document (for annotations)', default=None)


register_type("MentionedResourceType", MentionedResourceType, model=None)


@strawberry.type(name="ModerationMetricsType", description='Aggregated moderation metrics for monitoring.')
class ModerationMetricsType:
    total_actions: Optional[int] = strawberry.field(name="totalActions", default=None)
    automated_actions: Optional[int] = strawberry.field(name="automatedActions", default=None)
    manual_actions: Optional[int] = strawberry.field(name="manualActions", default=None)
    actions_by_type: Optional[GenericScalar] = strawberry.field(name="actionsByType", default=None)
    hourly_action_rate: Optional[float] = strawberry.field(name="hourlyActionRate", default=None)
    is_above_threshold: Optional[bool] = strawberry.field(name="isAboveThreshold", default=None)
    threshold_exceeded_types: Optional[list[Optional[str]]] = strawberry.field(name="thresholdExceededTypes", default=None)
    time_range_hours: Optional[int] = strawberry.field(name="timeRangeHours", default=None)
    start_time: Optional[datetime.datetime] = strawberry.field(name="startTime", default=None)
    end_time: Optional[datetime.datetime] = strawberry.field(name="endTime", default=None)


register_type("ModerationMetricsType", ModerationMetricsType, model=None)


def q_conversation(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional["ConversationType"]:
    return get_node_from_global_id(info, id, only_type_name="ConversationType")



QUERY_FIELDS = {
    "conversation": strawberry.field(resolver=q_conversation, name="conversation"),
}
