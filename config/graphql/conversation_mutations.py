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




@strawberry.type(name="CreateThreadMutation", description='Create a new discussion thread linked to a corpus and/or document.\n\nSupports three modes:\n- corpus_id only: Thread is linked to corpus (corpus-level discussion)\n- document_id only: Thread is linked to document (standalone document discussion)\n- both corpus_id AND document_id: Thread is linked to both (doc-in-corpus discussion)\n\nSecurity Note: Message content is stored as Markdown from TipTap editor.\nMarkdown is safer than HTML (no script injection), and mention links use\nstandard Markdown syntax [text](url) which is parsed to create database relationships.\nPart of Issue #623 - @ Mentions Feature (Extended)\nPart of Issue #677 - Document Discussions UI Enhancement')
class CreateThreadMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="obj", default=None)


register_type("CreateThreadMutation", CreateThreadMutation, model=None)


@strawberry.type(name="CreateThreadMessageMutation", description='Post a new message to an existing thread.')
class CreateThreadMessageMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="obj", default=None)


register_type("CreateThreadMessageMutation", CreateThreadMessageMutation, model=None)


@strawberry.type(name="ReplyToMessageMutation", description='Create a nested reply to an existing message.')
class ReplyToMessageMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="obj", default=None)


register_type("ReplyToMessageMutation", ReplyToMessageMutation, model=None)


@strawberry.type(name="UpdateMessageMutation", description="Update the content of an existing message.\n\nSecurity Note: Only the message creator or a moderator can edit messages.\nMention links are re-parsed when content is updated.\n\nXSS Prevention Note: The content field contains user-generated markdown text\nthat must be properly escaped when rendered in the frontend to prevent XSS\nattacks. GraphQL's GenericScalar handles JSON serialization safely, but the\nfrontend must use a markdown renderer that sanitizes HTML output.\n\nPart of Issue #686 - Mobile UI for Edit Message Modal")
class UpdateMessageMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="obj", default=None)


register_type("UpdateMessageMutation", UpdateMessageMutation, model=None)


@strawberry.type(name="DeleteConversationMutation", description='Soft delete a conversation/thread.')
class DeleteConversationMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteConversationMutation", DeleteConversationMutation, model=None)


@strawberry.type(name="DeleteMessageMutation", description='Soft delete a message.')
class DeleteMessageMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteMessageMutation", DeleteMessageMutation, model=None)


def _mutate_CreateThreadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:81

    Port of CreateThreadMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateThreadMutation not yet ported — see manifest")


def m_create_thread(info: strawberry.Info, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId", description='ID of the corpus for this thread (optional if document_id provided)')] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description", description='Optional description')] = strawberry.UNSET, document_id: Annotated[Optional[str], strawberry.argument(name="documentId", description='ID of the document for this thread (for doc-specific discussions)')] = strawberry.UNSET, initial_message: Annotated[str, strawberry.argument(name="initialMessage", description='Initial message content')] = strawberry.UNSET, title: Annotated[str, strawberry.argument(name="title", description='Title of the thread')] = strawberry.UNSET) -> Optional["CreateThreadMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "description": description, "document_id": document_id, "initial_message": initial_message, "title": title})
    return _mutate_CreateThreadMutation(CreateThreadMutation, None, info, **kwargs)


def _mutate_CreateThreadMessageMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:223

    Port of CreateThreadMessageMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateThreadMessageMutation not yet ported — see manifest")


def m_create_thread_message(info: strawberry.Info, content: Annotated[str, strawberry.argument(name="content", description='Message content')] = strawberry.UNSET, conversation_id: Annotated[str, strawberry.argument(name="conversationId", description='ID of the conversation/thread')] = strawberry.UNSET) -> Optional["CreateThreadMessageMutation"]:
    kwargs = strip_unset({"content": content, "conversation_id": conversation_id})
    return _mutate_CreateThreadMessageMutation(CreateThreadMessageMutation, None, info, **kwargs)


def _mutate_ReplyToMessageMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:321

    Port of ReplyToMessageMutation.mutate
    """
    raise NotImplementedError("_mutate_ReplyToMessageMutation not yet ported — see manifest")


def m_reply_to_message(info: strawberry.Info, content: Annotated[str, strawberry.argument(name="content", description='Reply content')] = strawberry.UNSET, parent_message_id: Annotated[str, strawberry.argument(name="parentMessageId", description='ID of the parent message')] = strawberry.UNSET) -> Optional["ReplyToMessageMutation"]:
    kwargs = strip_unset({"content": content, "parent_message_id": parent_message_id})
    return _mutate_ReplyToMessageMutation(ReplyToMessageMutation, None, info, **kwargs)


def _mutate_UpdateMessageMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:514

    Port of UpdateMessageMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateMessageMutation not yet ported — see manifest")


def m_update_message(info: strawberry.Info, content: Annotated[str, strawberry.argument(name="content", description='New content for the message')] = strawberry.UNSET, message_id: Annotated[strawberry.ID, strawberry.argument(name="messageId", description='ID of the message to update')] = strawberry.UNSET) -> Optional["UpdateMessageMutation"]:
    kwargs = strip_unset({"content": content, "message_id": message_id})
    return _mutate_UpdateMessageMutation(UpdateMessageMutation, None, info, **kwargs)


def _mutate_DeleteConversationMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:433

    Port of DeleteConversationMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteConversationMutation not yet ported — see manifest")


def m_delete_conversation(info: strawberry.Info, conversation_id: Annotated[str, strawberry.argument(name="conversationId", description='ID of the conversation to delete')] = strawberry.UNSET) -> Optional["DeleteConversationMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id})
    return _mutate_DeleteConversationMutation(DeleteConversationMutation, None, info, **kwargs)


def _mutate_DeleteMessageMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:689

    Port of DeleteMessageMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteMessageMutation not yet ported — see manifest")


def m_delete_message(info: strawberry.Info, message_id: Annotated[strawberry.ID, strawberry.argument(name="messageId", description='ID of the message to delete')] = strawberry.UNSET) -> Optional["DeleteMessageMutation"]:
    kwargs = strip_unset({"message_id": message_id})
    return _mutate_DeleteMessageMutation(DeleteMessageMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_thread": strawberry.field(resolver=m_create_thread, name="createThread", description='Create a new discussion thread linked to a corpus and/or document.\n\nSupports three modes:\n- corpus_id only: Thread is linked to corpus (corpus-level discussion)\n- document_id only: Thread is linked to document (standalone document discussion)\n- both corpus_id AND document_id: Thread is linked to both (doc-in-corpus discussion)\n\nSecurity Note: Message content is stored as Markdown from TipTap editor.\nMarkdown is safer than HTML (no script injection), and mention links use\nstandard Markdown syntax [text](url) which is parsed to create database relationships.\nPart of Issue #623 - @ Mentions Feature (Extended)\nPart of Issue #677 - Document Discussions UI Enhancement'),
    "create_thread_message": strawberry.field(resolver=m_create_thread_message, name="createThreadMessage", description='Post a new message to an existing thread.'),
    "reply_to_message": strawberry.field(resolver=m_reply_to_message, name="replyToMessage", description='Create a nested reply to an existing message.'),
    "update_message": strawberry.field(resolver=m_update_message, name="updateMessage", description="Update the content of an existing message.\n\nSecurity Note: Only the message creator or a moderator can edit messages.\nMention links are re-parsed when content is updated.\n\nXSS Prevention Note: The content field contains user-generated markdown text\nthat must be properly escaped when rendered in the frontend to prevent XSS\nattacks. GraphQL's GenericScalar handles JSON serialization safely, but the\nfrontend must use a markdown renderer that sanitizes HTML output.\n\nPart of Issue #686 - Mobile UI for Edit Message Modal"),
    "delete_conversation": strawberry.field(resolver=m_delete_conversation, name="deleteConversation", description='Soft delete a conversation/thread.'),
    "delete_message": strawberry.field(resolver=m_delete_message, name="deleteMessage", description='Soft delete a message.'),
}
