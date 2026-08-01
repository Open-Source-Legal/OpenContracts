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

import logging
from typing import Annotated

import strawberry
from django.db import transaction
from django.utils import timezone
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.constants.truncation import MAX_DERIVED_MESSAGE_TITLE_CHARS
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.shared.services.base import BaseService
from opencontractserver.tasks.agent_tasks import trigger_agent_responses_for_message
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.mention_parser import (
    link_message_to_resources,
    parse_mentions_from_content,
)
from opencontractserver.utils.permissioning import (
    get_for_user_or_none,
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)


@strawberry.type(
    name="CreateThreadMutation",
    description="Create a new discussion thread linked to a corpus and/or document.\n\nSupports three modes:\n- corpus_id only: Thread is linked to corpus (corpus-level discussion)\n- document_id only: Thread is linked to document (standalone document discussion)\n- both corpus_id AND document_id: Thread is linked to both (doc-in-corpus discussion)\n\nSecurity Note: Message content is stored as Markdown from TipTap editor.\nMarkdown is safer than HTML (no script injection), and mention links use\nstandard Markdown syntax [text](url) which is parsed to create database relationships.\nPart of Issue #623 - @ Mentions Feature (Extended)\nPart of Issue #677 - Document Discussions UI Enhancement",
)
class CreateThreadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateThreadMutation", CreateThreadMutation, model=None)


@strawberry.type(
    name="CreateThreadMessageMutation",
    description="Post a new message to an existing thread.",
)
class CreateThreadMessageMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateThreadMessageMutation", CreateThreadMessageMutation, model=None)


@strawberry.type(
    name="ReplyToMessageMutation",
    description="Create a nested reply to an existing message.",
)
class ReplyToMessageMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("ReplyToMessageMutation", ReplyToMessageMutation, model=None)


@strawberry.type(
    name="UpdateMessageMutation",
    description="Update the content of an existing message.\n\nSecurity Note: Only the message creator or a moderator can edit messages.\nMention links are re-parsed when content is updated.\n\nXSS Prevention Note: The content field contains user-generated markdown text\nthat must be properly escaped when rendered in the frontend to prevent XSS\nattacks. GraphQL's GenericScalar handles JSON serialization safely, but the\nfrontend must use a markdown renderer that sanitizes HTML output.\n\nPart of Issue #686 - Mobile UI for Edit Message Modal",
)
class UpdateMessageMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("UpdateMessageMutation", UpdateMessageMutation, model=None)


@strawberry.type(
    name="SaveMessageToWorkspaceMutation",
    description="Save a chat message to the caller's personal 'My Documents' workspace as a markdown document.",
)
class SaveMessageToWorkspaceMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "SaveMessageToWorkspaceMutation", SaveMessageToWorkspaceMutation, model=None
)


@strawberry.type(
    name="DeleteConversationMutation", description="Soft delete a conversation/thread."
)
class DeleteConversationMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteConversationMutation", DeleteConversationMutation, model=None)


@strawberry.type(name="DeleteMessageMutation", description="Soft delete a message.")
class DeleteMessageMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteMessageMutation", DeleteMessageMutation, model=None)


def _mutate_CreateThreadMutation(
    payload_cls,
    root,
    info,
    title,
    initial_message,
    corpus_id=None,
    document_id=None,
    description=None,
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:81

    Port of CreateThreadMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="10/h")
    @transaction.atomic
    def mutate(
        root,
        info,
        title,
        initial_message,
        corpus_id=None,
        document_id=None,
        description=None,
    ):
        ok = False
        obj = None
        message = ""

        try:
            user = info.context.user
            corpus = None
            document = None

            # At least one of corpus_id or document_id must be provided
            if not corpus_id and not document_id:
                return payload_cls(
                    ok=False,
                    message="Either corpus_id or document_id (or both) must be provided",
                    obj=None,
                )

            # Resolve corpus / document if provided. Both go through
            # ``get_for_user_or_none`` so missing pk and inaccessible pk
            # converge on the same response per the Phase D IDOR contract.
            # ``from_global_id`` can raise a bare ``Exception`` (via
            # ``binascii.Error``) on malformed base64 — catch it so a bad
            # id surfaces through the unified IDOR-safe envelope rather
            # than the generic "Failed to create thread" outer handler.
            if corpus_id:
                try:
                    corpus_pk = from_global_id(corpus_id)[1]
                except Exception:
                    return payload_cls(
                        ok=False,
                        message="You do not have permission to create threads in this corpus",
                        obj=None,
                    )
                corpus = get_for_user_or_none(Corpus, corpus_pk, user)
                if corpus is None:
                    return payload_cls(
                        ok=False,
                        message="You do not have permission to create threads in this corpus",
                        obj=None,
                    )

            if document_id:
                try:
                    document_pk = from_global_id(document_id)[1]
                except Exception:
                    return payload_cls(
                        ok=False,
                        message="You do not have permission to create threads for this document",
                        obj=None,
                    )
                document = get_for_user_or_none(Document, document_pk, user)
                if document is None:
                    return payload_cls(
                        ok=False,
                        message="You do not have permission to create threads for this document",
                        obj=None,
                    )

            # Create the conversation with THREAD type
            conversation = Conversation.objects.create(
                title=title,
                description=description or "",
                conversation_type="thread",
                chat_with_corpus=corpus,
                chat_with_document=document,
                creator=user,
            )

            # Set permissions for the creator
            set_permissions_for_obj_to_user(
                user,
                conversation,
                [PermissionTypes.CRUD],
                is_new=True,
                request=info.context,
            )

            # Create the initial message
            chat_message = ChatMessage.objects.create(
                conversation=conversation,
                msg_type=MessageTypeChoices.HUMAN,
                content=initial_message,
                creator=user,
            )

            # Parse and link mentioned resources (documents, annotations, etc.)
            try:
                mentioned_ids = parse_mentions_from_content(initial_message)
                link_result = link_message_to_resources(chat_message, mentioned_ids)
                logger.debug(
                    f"Thread {conversation.pk} initial message linked: {link_result}"
                )

                # Trigger agent responses if any agents were mentioned
                if link_result.get("agents_linked", 0) > 0:
                    trigger_agent_responses_for_message.delay(
                        message_id=chat_message.pk,
                        user_id=user.pk,
                    )
                    logger.debug(
                        f"Triggered agent responses for message {chat_message.pk}"
                    )
            except Exception as e:
                # Don't fail the whole mutation if mention parsing fails
                logger.error(f"Error parsing mentions in initial message: {e}")

            ok = True
            message = "Thread created successfully"
            obj = conversation

        except Exception as e:
            logger.error(f"Error creating thread: {e}")
            message = "Failed to create thread"

        return payload_cls(ok=ok, message=message, obj=obj)

    return mutate(
        root,
        info,
        title=title,
        initial_message=initial_message,
        corpus_id=corpus_id,
        document_id=document_id,
        description=description,
    )


def m_create_thread(
    info: strawberry.Info,
    corpus_id: Annotated[
        str | None,
        strawberry.argument(
            name="corpusId",
            description="ID of the corpus for this thread (optional if document_id provided)",
        ),
    ] = strawberry.UNSET,
    description: Annotated[
        str | None,
        strawberry.argument(name="description", description="Optional description"),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str | None,
        strawberry.argument(
            name="documentId",
            description="ID of the document for this thread (for doc-specific discussions)",
        ),
    ] = strawberry.UNSET,
    initial_message: Annotated[
        str,
        strawberry.argument(
            name="initialMessage", description="Initial message content"
        ),
    ] = strawberry.UNSET,
    title: Annotated[
        str, strawberry.argument(name="title", description="Title of the thread")
    ] = strawberry.UNSET,
) -> CreateThreadMutation | None:
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "description": description,
            "document_id": document_id,
            "initial_message": initial_message,
            "title": title,
        }
    )
    return _mutate_CreateThreadMutation(CreateThreadMutation, None, info, **kwargs)


def _mutate_CreateThreadMessageMutation(
    payload_cls, root, info, content, conversation_id
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:223

    Port of CreateThreadMessageMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateThreadMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="30/m")
    def mutate(root, info, conversation_id, content):
        ok = False
        obj = None
        message = ""

        try:
            user = info.context.user
            # ``from_global_id`` can raise a bare ``Exception`` (via
            # ``binascii.Error``) on malformed base64 — catch it so a bad
            # id surfaces through the unified IDOR-safe envelope.
            try:
                conversation_pk = from_global_id(conversation_id)[1]
            except Exception:
                return payload_cls(
                    ok=False,
                    message="Cannot post in this thread",
                    obj=None,
                )
            conversation = get_for_user_or_none(Conversation, conversation_pk, user)
            if conversation is None:
                return payload_cls(
                    ok=False,
                    message="Cannot post in this thread",
                    obj=None,
                )

            # Check if conversation is locked (only after verifying user has access)
            if conversation.is_locked:
                return payload_cls(
                    ok=False,
                    message="This thread is locked",
                    obj=None,
                )

            # Create the message
            chat_message = ChatMessage.objects.create(
                conversation=conversation,
                msg_type=MessageTypeChoices.HUMAN,
                content=content,
                creator=user,
            )

            # Set permissions for the creator
            set_permissions_for_obj_to_user(
                user,
                chat_message,
                [PermissionTypes.CRUD],
                is_new=True,
                request=info.context,
            )

            # Parse and link mentioned resources (documents, annotations, etc.)
            try:
                mentioned_ids = parse_mentions_from_content(content)
                link_result = link_message_to_resources(chat_message, mentioned_ids)
                logger.debug(f"Message {chat_message.pk} linked: {link_result}")

                # Trigger agent responses if any agents were mentioned
                if link_result.get("agents_linked", 0) > 0:
                    trigger_agent_responses_for_message.delay(
                        message_id=chat_message.pk,
                        user_id=user.pk,
                    )
                    logger.debug(
                        f"Triggered agent responses for message {chat_message.pk}"
                    )
            except Exception as e:
                # Don't fail the whole mutation if mention parsing fails
                logger.error(f"Error parsing mentions in message: {e}")

            ok = True
            message = "Message posted successfully"
            obj = chat_message

        except Conversation.DoesNotExist:
            message = "You do not have permission to post in this thread"
        except Exception as e:
            logger.error(f"Error creating message: {e}")
            message = "Failed to create message"

        return payload_cls(ok=ok, message=message, obj=obj)

    return mutate(root, info, conversation_id=conversation_id, content=content)


def m_create_thread_message(
    info: strawberry.Info,
    content: Annotated[
        str, strawberry.argument(name="content", description="Message content")
    ] = strawberry.UNSET,
    conversation_id: Annotated[
        str,
        strawberry.argument(
            name="conversationId", description="ID of the conversation/thread"
        ),
    ] = strawberry.UNSET,
) -> CreateThreadMessageMutation | None:
    kwargs = strip_unset({"content": content, "conversation_id": conversation_id})
    return _mutate_CreateThreadMessageMutation(
        CreateThreadMessageMutation, None, info, **kwargs
    )


def _mutate_ReplyToMessageMutation(payload_cls, root, info, content, parent_message_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:321

    Port of ReplyToMessageMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateThreadMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="30/m")
    def mutate(root, info, parent_message_id, content):
        ok = False
        obj = None
        message = ""

        try:
            user = info.context.user
            # ``from_global_id`` can raise a bare ``Exception`` (via
            # ``binascii.Error``) on malformed base64 — catch it so a bad
            # id surfaces through the unified IDOR-safe envelope.
            try:
                parent_pk = from_global_id(parent_message_id)[1]
            except Exception:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to reply to this message",
                    obj=None,
                )

            parent_message = get_for_user_or_none(ChatMessage, parent_pk, user)
            if parent_message is None:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to reply to this message",
                    obj=None,
                )

            conversation = parent_message.conversation

            # SECURITY: Check permissions FIRST to prevent information disclosure
            # about locked thread status via different error messages (IDOR prevention).
            # Uses same generic message for both permission denied and locked states.
            if BaseService.require_permission(
                conversation, user, PermissionTypes.READ, request=info.context
            ):
                return payload_cls(
                    ok=False,
                    message="Cannot reply in this thread",
                    obj=None,
                )

            # Check if conversation is locked (only after verifying user has access)
            if conversation.is_locked:
                return payload_cls(
                    ok=False,
                    message="This thread is locked",
                    obj=None,
                )

            # Create the reply message
            reply_message = ChatMessage.objects.create(
                conversation=conversation,
                msg_type=MessageTypeChoices.HUMAN,
                content=content,
                parent_message=parent_message,
                creator=user,
            )

            # Set permissions for the creator
            set_permissions_for_obj_to_user(
                user,
                reply_message,
                [PermissionTypes.CRUD],
                is_new=True,
                request=info.context,
            )

            # Parse and link mentioned resources (documents, annotations, etc.)
            try:
                mentioned_ids = parse_mentions_from_content(content)
                link_result = link_message_to_resources(reply_message, mentioned_ids)
                logger.debug(f"Reply {reply_message.pk} linked: {link_result}")

                # Trigger agent responses if any agents were mentioned
                if link_result.get("agents_linked", 0) > 0:
                    trigger_agent_responses_for_message.delay(
                        message_id=reply_message.pk,
                        user_id=user.pk,
                    )
                    logger.debug(
                        f"Triggered agent responses for reply {reply_message.pk}"
                    )
            except Exception as e:
                # Don't fail the whole mutation if mention parsing fails
                logger.error(f"Error parsing mentions in reply: {e}")

            ok = True
            message = "Reply posted successfully"
            obj = reply_message

        except ChatMessage.DoesNotExist:
            message = "You do not have permission to reply in this thread"
        except Exception as e:
            logger.error(f"Error creating reply: {e}")
            message = "Failed to create reply"

        return payload_cls(ok=ok, message=message, obj=obj)

    return mutate(root, info, parent_message_id=parent_message_id, content=content)


def m_reply_to_message(
    info: strawberry.Info,
    content: Annotated[
        str, strawberry.argument(name="content", description="Reply content")
    ] = strawberry.UNSET,
    parent_message_id: Annotated[
        str,
        strawberry.argument(
            name="parentMessageId", description="ID of the parent message"
        ),
    ] = strawberry.UNSET,
) -> ReplyToMessageMutation | None:
    kwargs = strip_unset({"content": content, "parent_message_id": parent_message_id})
    return _mutate_ReplyToMessageMutation(ReplyToMessageMutation, None, info, **kwargs)


def _mutate_UpdateMessageMutation(payload_cls, root, info, content, message_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:514

    Port of UpdateMessageMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateThreadMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="30/m")
    @transaction.atomic
    def mutate(root, info, message_id, content):
        ok = False
        obj = None
        message = ""

        try:
            user = info.context.user
            message_pk = from_global_id(message_id)[1]

            # Validate content is not empty (matches frontend validation)
            if not content or not content.strip():
                return payload_cls(
                    ok=False,
                    message="Message content cannot be empty",
                    obj=None,
                )

            # Use the service-layer visibility filter (which includes moderator
            # access). This prevents IDOR enumeration while properly handling
            # moderator access.
            #
            # NOTE: We do not use select_for_update() here because:
            # 1. The visibility filter uses DISTINCT, which is incompatible
            #    with FOR UPDATE
            # 2. select_related() with nullable FKs uses outer joins, also
            #    incompatible
            # The @transaction.atomic decorator provides sufficient transactional
            # integrity for message editing, which is not a high-concurrency
            # operation.
            #
            # Use select_related() to avoid N+1 queries when accessing
            # conversation/corpus for mention parsing and moderator checks.
            try:
                chat_message = (
                    BaseService.filter_visible(ChatMessage, user, request=info.context)
                    .select_related(
                        "conversation",
                        "conversation__chat_with_corpus",
                        "conversation__chat_with_document",
                        "creator",
                    )
                    .get(pk=message_pk)
                )
            except ChatMessage.DoesNotExist:
                # Check if this is a deleted message that user should be able to see
                # (to give proper "message is deleted" error instead of generic permission error)
                candidate = ChatMessage.all_objects.filter(pk=message_pk).first()
                if candidate and (
                    candidate.creator == user
                    or candidate.conversation.can_moderate(user)
                ):
                    chat_message = candidate
                else:
                    return payload_cls(
                        ok=False,
                        message="You do not have permission to edit this message",
                        obj=None,
                    )

            # Check if user has permission to update (CRUD includes update)
            # Moderators can always edit messages in conversations they moderate.
            has_update_permission = BaseService.user_has(
                chat_message, user, PermissionTypes.CRUD, request=info.context
            )
            is_moderator = chat_message.conversation.can_moderate(user)

            if not has_update_permission and not is_moderator:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to edit this message",
                    obj=None,
                )

            # Check if conversation is locked
            if chat_message.conversation.is_locked:
                return payload_cls(
                    ok=False,
                    message="This thread is locked",
                    obj=None,
                )

            # Check if message is deleted
            if chat_message.deleted_at:
                return payload_cls(
                    ok=False,
                    message="Cannot edit a deleted message",
                    obj=None,
                )

            # Parse mentions FIRST (before modifying database) to avoid race condition
            # where parsing fails after mentions are cleared, leaving message with no mentions
            mention_parse_success = True
            mentioned_ids = {}
            try:
                mentioned_ids = parse_mentions_from_content(content)
            except (AttributeError, KeyError, TypeError, ValueError) as e:
                # Don't fail the whole mutation if mention parsing fails
                # These are the expected exceptions from parsing logic
                mention_parse_success = False
                logger.warning(
                    f"Error parsing mentions in updated message {chat_message.pk}: "
                    f"{type(e).__name__}: {e}"
                )

            # Now atomically update content and clear all mention-related fields
            chat_message.content = content
            chat_message.source_document = None
            chat_message.save(update_fields=["content", "source_document", "modified"])

            # Clear M2M relationships (these don't require save())
            chat_message.source_annotations.clear()
            chat_message.mentioned_agents.clear()

            # Link new mentions (only if parsing succeeded)
            if mention_parse_success and mentioned_ids:
                try:
                    link_result = link_message_to_resources(chat_message, mentioned_ids)
                    logger.debug(
                        f"Updated message {chat_message.pk} links: {link_result}"
                    )

                    # Trigger agent responses if any agents were mentioned
                    # NOTE: This triggers for ALL mentioned agents, including previously
                    # mentioned ones. This means editing "@agent hello" to "@agent goodbye"
                    # will trigger a new agent response. This is intentional to ensure
                    # agents respond to updated context, but may result in multiple responses
                    # if users repeatedly edit messages with the same mentions.
                    if link_result.get("agents_linked", 0) > 0:
                        trigger_agent_responses_for_message.delay(
                            message_id=chat_message.pk,
                            user_id=user.pk,
                        )
                        logger.debug(
                            f"Triggered agent responses for updated message {chat_message.pk}"
                        )
                except (AttributeError, KeyError, TypeError, ValueError) as e:
                    # Don't fail the whole mutation if mention linking fails
                    # These are the expected exceptions from linking logic
                    mention_parse_success = False
                    logger.warning(
                        f"Error linking mentions in updated message {chat_message.pk}: "
                        f"{type(e).__name__}: {e}"
                    )

            ok = True
            # Provide feedback if mentions failed to parse (UX improvement)
            if mention_parse_success:
                message = "Message updated successfully"
            else:
                message = (
                    "Message updated, but some mentions may not have been recognized"
                )
            obj = chat_message

        except Exception as e:
            logger.error(f"Error updating message: {type(e).__name__}: {e}")
            message = "Failed to update message"

        return payload_cls(ok=ok, message=message, obj=obj)

    return mutate(root, info, message_id=message_id, content=content)


def m_update_message(
    info: strawberry.Info,
    content: Annotated[
        str,
        strawberry.argument(name="content", description="New content for the message"),
    ] = strawberry.UNSET,
    message_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="messageId", description="ID of the message to update"
        ),
    ] = strawberry.UNSET,
) -> UpdateMessageMutation | None:
    kwargs = strip_unset({"content": content, "message_id": message_id})
    return _mutate_UpdateMessageMutation(UpdateMessageMutation, None, info, **kwargs)


def _mutate_DeleteConversationMutation(payload_cls, root, info, conversation_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:433

    Port of DeleteConversationMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateThreadMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, conversation_id):
        ok = False
        message = ""

        try:
            user = info.context.user
            # ``from_global_id`` can raise a bare ``Exception`` (via
            # ``binascii.Error``) on malformed base64 — catch it so a bad
            # id surfaces through the unified IDOR-safe envelope.
            try:
                conversation_pk = from_global_id(conversation_id)[1]
            except Exception:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to delete this conversation",
                )

            conversation = get_for_user_or_none(Conversation, conversation_pk, user)
            if conversation is None:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to delete this conversation",
                )

            # Check if user has permission to delete via the service layer.
            has_delete_permission = BaseService.user_has(
                conversation, user, PermissionTypes.DELETE, request=info.context
            )
            is_moderator = conversation.can_moderate(user)

            if not has_delete_permission and not is_moderator:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to delete this conversation",
                )

            # Soft delete the conversation
            conversation.deleted_at = timezone.now()
            conversation.save(update_fields=["deleted_at"])

            ok = True
            message = "Conversation deleted successfully"

        except Conversation.DoesNotExist:
            message = "You do not have permission to delete this conversation"
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}")
            message = "Failed to delete conversation"

        return payload_cls(ok=ok, message=message)

    return mutate(root, info, conversation_id=conversation_id)


def m_delete_conversation(
    info: strawberry.Info,
    conversation_id: Annotated[
        str,
        strawberry.argument(
            name="conversationId", description="ID of the conversation to delete"
        ),
    ] = strawberry.UNSET,
) -> DeleteConversationMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id})
    return _mutate_DeleteConversationMutation(
        DeleteConversationMutation, None, info, **kwargs
    )


def _mutate_DeleteMessageMutation(payload_cls, root, info, message_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:689

    Port of DeleteMessageMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateThreadMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, message_id):
        ok = False
        message = ""

        try:
            user = info.context.user
            # ``from_global_id`` can raise a bare ``Exception`` (via
            # ``binascii.Error``) on malformed base64 — catch it so a bad
            # id surfaces through the unified IDOR-safe envelope.
            try:
                message_pk = from_global_id(message_id)[1]
            except Exception:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to delete this message",
                )

            chat_message = get_for_user_or_none(ChatMessage, message_pk, user)
            if chat_message is None:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to delete this message",
                )

            # Check if user has permission to delete via service layer.
            has_delete_permission = BaseService.user_has(
                chat_message, user, PermissionTypes.DELETE, request=info.context
            )
            is_moderator = chat_message.conversation.can_moderate(user)

            if not has_delete_permission and not is_moderator:
                return payload_cls(
                    ok=False,
                    message="You do not have permission to delete this message",
                )

            # Soft delete the message
            chat_message.deleted_at = timezone.now()
            chat_message.save(update_fields=["deleted_at"])

            ok = True
            message = "Message deleted successfully"

        except ChatMessage.DoesNotExist:
            message = "You do not have permission to delete this message"
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            message = "Failed to delete message"

        return payload_cls(ok=ok, message=message)

    return mutate(root, info, message_id=message_id)


def m_delete_message(
    info: strawberry.Info,
    message_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="messageId", description="ID of the message to delete"
        ),
    ] = strawberry.UNSET,
) -> DeleteMessageMutation | None:
    kwargs = strip_unset({"message_id": message_id})
    return _mutate_DeleteMessageMutation(DeleteMessageMutation, None, info, **kwargs)


def _resolve_message_pk(message_id) -> int | None:
    """Accept either a relay global ID or a raw primary key.

    The same ``messageId`` field carries two formats depending on where the
    message came from: history loaded over GraphQL is a relay global ID
    (``CorpusChat.tsx`` ``messageId: msg.id``), while a message streamed over
    the agent WebSocket is the raw integer pk (``messageId: data.message_id``).
    Decoding blindly turns the raw form into an empty string and then a
    ``ValueError`` deep in the ORM, which is exactly what a freshly streamed
    answer — the most likely thing a user wants to save — would hit.

    Returns ``None`` for anything unusable so the caller can answer with the
    same "not found" it uses for invisible messages, rather than 500-ing.
    """
    try:
        decoded = from_global_id(message_id)[1]
    except Exception:
        decoded = None
    if decoded and str(decoded).isdigit():
        return int(decoded)
    raw = str(message_id or "")
    if raw.isdigit():
        return int(raw)
    return None


def _default_saved_message_title(chat_message) -> str:
    """Best-effort title from the message body's first meaningful line."""
    for raw_line in (chat_message.content or "").splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if not line:
            continue
        # Drop obvious markdown emphasis so the title is not "**Summary**".
        line = line.replace("*", "").replace("`", "").strip()
        if line:
            if len(line) > MAX_DERIVED_MESSAGE_TITLE_CHARS:
                line = line[:MAX_DERIVED_MESSAGE_TITLE_CHARS].rstrip() + "…"
            return line
    return f"Saved chat message {chat_message.pk}"


def _saved_message_markdown(chat_message, title: str) -> str:
    """Compose the file: provenance header, then the message verbatim.

    The header matters more here than for a research report: a chat answer read
    six months later, outside the thread that produced it, otherwise gives no
    indication of what it was answering or which corpus it drew on.
    """
    conversation = chat_message.conversation
    corpus = getattr(conversation, "chat_with_corpus", None) if conversation else None
    created = chat_message.created or timezone.now()

    header = [f"# {title}", ""]
    if corpus is not None:
        header.append(f"- **Corpus:** {corpus.title}")
    if conversation is not None and conversation.title:
        header.append(f"- **Conversation:** {conversation.title}")
    header.append(f"- **Saved from chat:** {created.date().isoformat()}")
    header.extend(["", "---", ""])
    return "\n".join(header) + "\n" + (chat_message.content or "")


def _mutate_SaveMessageToWorkspaceMutation(
    payload_cls, root, info, message_id, title, folder_name
):
    """Save one chat message into the caller's personal workspace.

    A chat answer is otherwise unsaved: unlike a research report it has no
    durable artifact, so the moment the conversation scrolls away the analysis
    is only findable by re-reading the thread. This files it as a markdown
    document the user owns, in their own corpus, optionally under a folder.
    """
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="30/m")
    def mutate(root, info, message_id, title, folder_name):
        from opencontractserver.corpuses.services import WorkspaceService

        user = info.context.user
        message_pk = _resolve_message_pk(message_id)
        if message_pk is None:
            return payload_cls(ok=False, message="Message not found", obj=None)

        # Same IDOR-safe lookup the edit/delete mutations use: an invisible
        # message and a nonexistent one must be indistinguishable.
        try:
            chat_message = (
                BaseService.filter_visible(ChatMessage, user, request=info.context)
                .select_related("conversation")
                .get(pk=message_pk)
            )
        except ChatMessage.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Message not found",
                obj=None,
            )

        content = (chat_message.content or "").strip()
        if not content:
            return payload_cls(
                ok=False,
                message="This message has no content to save.",
                obj=None,
            )

        resolved_title = (title or "").strip() or _default_saved_message_title(
            chat_message
        )

        try:
            document = WorkspaceService.save_markdown(
                user=user,
                title=resolved_title,
                content=_saved_message_markdown(chat_message, resolved_title),
                folder_name=(folder_name or "").strip() or None,
            )
        except Exception:
            logger.exception(
                "Failed to save chat message %s to the workspace of user %s",
                chat_message.pk,
                user.pk,
            )
            return payload_cls(
                ok=False,
                message="Could not save this message to your workspace.",
                obj=None,
            )

        return payload_cls(
            ok=True,
            message=f"Saved to My Documents as '{resolved_title}'.",
            obj=document,
        )

    return mutate(root, info, message_id, title, folder_name)


def m_save_message_to_workspace(
    info: strawberry.Info,
    message_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="messageId", description="ID of the message to save"),
    ] = strawberry.UNSET,
    title: Annotated[
        str | None,
        strawberry.argument(
            name="title",
            description="Document title. Defaults to a title derived from the message.",
        ),
    ] = strawberry.UNSET,
    folder_name: Annotated[
        str | None,
        strawberry.argument(
            name="folderName",
            description="Optional folder in My Documents; created if it does not exist.",
        ),
    ] = strawberry.UNSET,
) -> SaveMessageToWorkspaceMutation | None:
    kwargs = strip_unset(
        {"message_id": message_id, "title": title, "folder_name": folder_name}
    )
    kwargs.setdefault("title", None)
    kwargs.setdefault("folder_name", None)
    return _mutate_SaveMessageToWorkspaceMutation(
        SaveMessageToWorkspaceMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_thread": strawberry.field(
        resolver=m_create_thread,
        name="createThread",
        description="Create a new discussion thread linked to a corpus and/or document.\n\nSupports three modes:\n- corpus_id only: Thread is linked to corpus (corpus-level discussion)\n- document_id only: Thread is linked to document (standalone document discussion)\n- both corpus_id AND document_id: Thread is linked to both (doc-in-corpus discussion)\n\nSecurity Note: Message content is stored as Markdown from TipTap editor.\nMarkdown is safer than HTML (no script injection), and mention links use\nstandard Markdown syntax [text](url) which is parsed to create database relationships.\nPart of Issue #623 - @ Mentions Feature (Extended)\nPart of Issue #677 - Document Discussions UI Enhancement",
    ),
    "create_thread_message": strawberry.field(
        resolver=m_create_thread_message,
        name="createThreadMessage",
        description="Post a new message to an existing thread.",
    ),
    "reply_to_message": strawberry.field(
        resolver=m_reply_to_message,
        name="replyToMessage",
        description="Create a nested reply to an existing message.",
    ),
    "update_message": strawberry.field(
        resolver=m_update_message,
        name="updateMessage",
        description="Update the content of an existing message.\n\nSecurity Note: Only the message creator or a moderator can edit messages.\nMention links are re-parsed when content is updated.\n\nXSS Prevention Note: The content field contains user-generated markdown text\nthat must be properly escaped when rendered in the frontend to prevent XSS\nattacks. GraphQL's GenericScalar handles JSON serialization safely, but the\nfrontend must use a markdown renderer that sanitizes HTML output.\n\nPart of Issue #686 - Mobile UI for Edit Message Modal",
    ),
    "save_message_to_workspace": strawberry.field(
        resolver=m_save_message_to_workspace,
        name="saveMessageToWorkspace",
        description="Save a chat message to the caller's personal 'My Documents' workspace as a markdown document, optionally inside a folder.",
    ),
    "delete_conversation": strawberry.field(
        resolver=m_delete_conversation,
        name="deleteConversation",
        description="Soft delete a conversation/thread.",
    ),
    "delete_message": strawberry.field(
        resolver=m_delete_message,
        name="deleteMessage",
        description="Soft delete a message.",
    ),
}
