"""
GraphQL mutations for thread support in conversations.

This module provides mutations for creating and managing discussion threads:
- CreateThreadMutation: Create new thread conversation
- CreateThreadMessageMutation: Post message to thread
- ReplyToMessageMutation: Create nested reply
- DeleteConversationMutation: Soft delete thread
- DeleteMessageMutation: Soft delete message
"""

import logging

import graphene
from django.db import transaction
from django.utils import timezone
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import ConversationType, MessageType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.tasks.agent_tasks import trigger_agent_responses_for_message
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.mention_parser import (
    link_message_to_resources,
    parse_mentions_from_content,
)
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


class CreateThreadMutation(graphene.Mutation):
    """
    Create a new discussion thread linked to a corpus and/or document.

    Supports three modes:
    - corpus_id only: Thread is linked to corpus (corpus-level discussion)
    - document_id only: Thread is linked to document (standalone document discussion)
    - both corpus_id AND document_id: Thread is linked to both (doc-in-corpus discussion)

    Security Note: Message content is stored as Markdown from TipTap editor.
    Markdown is safer than HTML (no script injection), and mention links use
    standard Markdown syntax [text](url) which is parsed to create database relationships.
    Part of Issue #623 - @ Mentions Feature (Extended)
    Part of Issue #677 - Document Discussions UI Enhancement
    """

    class Arguments:
        corpus_id = graphene.String(
            required=False,
            description="ID of the corpus for this thread (optional if document_id provided)",
        )
        document_id = graphene.String(
            required=False,
            description="ID of the document for this thread (for doc-specific discussions)",
        )
        title = graphene.String(required=True, description="Title of the thread")
        description = graphene.String(
            required=False, description="Optional description"
        )
        initial_message = graphene.String(
            required=True, description="Initial message content"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ConversationType)

    @login_required
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
    ) -> "CreateThreadMutation":
        ok = False
        obj = None
        message = ""

        try:
            user = info.context.user
            corpus = None
            document = None

            # At least one of corpus_id or document_id must be provided
            if not corpus_id and not document_id:
                return CreateThreadMutation(
                    ok=False,
                    message="Either corpus_id or document_id (or both) must be provided",
                    obj=None,
                )

            # Resolve corpus if provided -- use visible_to_user() to prevent
            # IDOR enumeration (same error for missing vs no-permission).
            if corpus_id:
                corpus_pk = from_global_id(corpus_id)[1]
                try:
                    corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
                except Corpus.DoesNotExist:
                    return CreateThreadMutation(
                        ok=False,
                        message="You do not have permission to create threads in this corpus",
                        obj=None,
                    )

            # Resolve document if provided -- use visible_to_user() to
            # prevent IDOR enumeration.
            if document_id:
                document_pk = from_global_id(document_id)[1]
                try:
                    document = Document.objects.visible_to_user(user).get(
                        pk=document_pk
                    )
                except Document.DoesNotExist:
                    return CreateThreadMutation(
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
            set_permissions_for_obj_to_user(user, conversation, [PermissionTypes.CRUD])

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

        return CreateThreadMutation(ok=ok, message=message, obj=obj)


class CreateThreadMessageMutation(graphene.Mutation):
    """Post a new message to an existing thread."""

    class Arguments:
        conversation_id = graphene.String(
            required=True, description="ID of the conversation/thread"
        )
        content = graphene.String(required=True, description="Message content")

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(MessageType)

    @login_required
    @graphql_ratelimit(rate="30/m")
    def mutate(root, info, conversation_id, content) -> "CreateThreadMessageMutation":
        ok = False
        obj = None
        message = ""

        try:
            user = info.context.user
            conversation_pk = from_global_id(conversation_id)[1]
            # Use visible_to_user() to prevent IDOR enumeration
            try:
                conversation = Conversation.objects.visible_to_user(user).get(
                    pk=conversation_pk
                )
            except Conversation.DoesNotExist:
                return CreateThreadMessageMutation(
                    ok=False,
                    message="Cannot post in this thread",
                    obj=None,
                )

            # Check if conversation is locked (only after verifying user has access)
            if conversation.is_locked:
                return CreateThreadMessageMutation(
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
            set_permissions_for_obj_to_user(user, chat_message, [PermissionTypes.CRUD])

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

        return CreateThreadMessageMutation(ok=ok, message=message, obj=obj)


class ReplyToMessageMutation(graphene.Mutation):
    """Create a nested reply to an existing message."""

    class Arguments:
        parent_message_id = graphene.String(
            required=True, description="ID of the parent message"
        )
        content = graphene.String(required=True, description="Reply content")

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(MessageType)

    @login_required
    @graphql_ratelimit(rate="30/m")
    def mutate(root, info, parent_message_id, content) -> "ReplyToMessageMutation":
        ok = False
        obj = None
        message = ""

        try:
            user = info.context.user
            parent_pk = from_global_id(parent_message_id)[1]

            # Use .visible_to_user() pattern to prevent enumeration
            try:
                parent_message = ChatMessage.objects.visible_to_user(user).get(
                    pk=parent_pk
                )
            except ChatMessage.DoesNotExist:
                return ReplyToMessageMutation(
                    ok=False,
                    message="You do not have permission to reply to this message",
                    obj=None,
                )

            conversation = parent_message.conversation

            # SECURITY: Check permissions FIRST to prevent information disclosure
            # about locked thread status via different error messages (IDOR prevention).
            # Uses same generic message for both permission denied and locked states.
            if not user_has_permission_for_obj(
                user, conversation, PermissionTypes.READ
            ):
                return ReplyToMessageMutation(
                    ok=False,
                    message="Cannot reply in this thread",
                    obj=None,
                )

            # Check if conversation is locked (only after verifying user has access)
            if conversation.is_locked:
                return ReplyToMessageMutation(
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
            set_permissions_for_obj_to_user(user, reply_message, [PermissionTypes.CRUD])

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

        return ReplyToMessageMutation(ok=ok, message=message, obj=obj)


class DeleteConversationMutation(graphene.Mutation):
    """Soft delete a conversation/thread."""

    class Arguments:
        conversation_id = graphene.String(
            required=True, description="ID of the conversation to delete"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, conversation_id) -> "DeleteConversationMutation":
        ok = False
        message = ""

        try:
            user = info.context.user
            conversation_pk = from_global_id(conversation_id)[1]

            # Use .visible_to_user() pattern to prevent IDOR enumeration
            # Returns same error whether object doesn't exist or user lacks permission
            try:
                conversation = Conversation.objects.visible_to_user(user).get(
                    pk=conversation_pk
                )
            except Conversation.DoesNotExist:
                return DeleteConversationMutation(
                    ok=False,
                    message="You do not have permission to delete this conversation",
                )

            # Check if user has permission to delete
            has_delete_permission = user_has_permission_for_obj(
                user, conversation, PermissionTypes.DELETE
            )
            is_moderator = conversation.can_moderate(user)

            if not has_delete_permission and not is_moderator:
                return DeleteConversationMutation(
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

        return DeleteConversationMutation(ok=ok, message=message)


class UpdateMessageMutation(graphene.Mutation):
    """
    Update the content of an existing message.

    Security Note: Only the message creator or a moderator can edit messages.
    Mention links are re-parsed when content is updated.

    XSS Prevention Note: The content field contains user-generated markdown text
    that must be properly escaped when rendered in the frontend to prevent XSS
    attacks. GraphQL's GenericScalar handles JSON serialization safely, but the
    frontend must use a markdown renderer that sanitizes HTML output.

    Part of Issue #686 - Mobile UI for Edit Message Modal
    """

    class Arguments:
        message_id = graphene.ID(
            required=True, description="ID of the message to update"
        )
        content = graphene.String(
            required=True, description="New content for the message"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(MessageType)

    @login_required
    @graphql_ratelimit(rate="30/m")
    @transaction.atomic
    def mutate(root, info, message_id, content) -> "UpdateMessageMutation":
        ok = False
        obj = None
        message = ""

        try:
            user = info.context.user
            message_pk = from_global_id(message_id)[1]

            # Validate content is not empty (matches frontend validation)
            if not content or not content.strip():
                return UpdateMessageMutation(
                    ok=False,
                    message="Message content cannot be empty",
                    obj=None,
                )

            # Use visible_to_user() which now includes moderator access
            # (moderators can see all messages in conversations they moderate)
            # This prevents IDOR enumeration while properly handling moderator access.
            #
            # NOTE: We do not use select_for_update() here because:
            # 1. visible_to_user() uses DISTINCT, which is incompatible with FOR UPDATE
            # 2. select_related() with nullable FKs uses outer joins, also incompatible
            # The @transaction.atomic decorator provides sufficient transactional integrity
            # for message editing, which is not a high-concurrency operation.
            #
            # Use select_related() to avoid N+1 queries when accessing conversation/corpus
            # for mention parsing and moderator checks.
            try:
                chat_message = (
                    ChatMessage.objects.visible_to_user(user)
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
                    return UpdateMessageMutation(
                        ok=False,
                        message="You do not have permission to edit this message",
                        obj=None,
                    )

            # Check if user has permission to update (CRUD includes update)
            # Moderators can always edit messages in conversations they moderate
            has_update_permission = user_has_permission_for_obj(
                user, chat_message, PermissionTypes.CRUD
            )
            is_moderator = chat_message.conversation.can_moderate(user)

            if not has_update_permission and not is_moderator:
                return UpdateMessageMutation(
                    ok=False,
                    message="You do not have permission to edit this message",
                    obj=None,
                )

            # Check if conversation is locked
            if chat_message.conversation.is_locked:
                return UpdateMessageMutation(
                    ok=False,
                    message="This thread is locked",
                    obj=None,
                )

            # Check if message is deleted
            if chat_message.deleted_at:
                return UpdateMessageMutation(
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

        return UpdateMessageMutation(ok=ok, message=message, obj=obj)


class DeleteMessageMutation(graphene.Mutation):
    """Soft delete a message."""

    class Arguments:
        message_id = graphene.ID(
            required=True, description="ID of the message to delete"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, message_id) -> "DeleteMessageMutation":
        ok = False
        message = ""

        try:
            user = info.context.user
            message_pk = from_global_id(message_id)[1]

            # Use .visible_to_user() pattern to prevent IDOR enumeration
            # Returns same error whether object doesn't exist or user lacks permission
            try:
                chat_message = ChatMessage.objects.visible_to_user(user).get(
                    pk=message_pk
                )
            except ChatMessage.DoesNotExist:
                return DeleteMessageMutation(
                    ok=False,
                    message="You do not have permission to delete this message",
                )

            # Check if user has permission to delete
            has_delete_permission = user_has_permission_for_obj(
                user, chat_message, PermissionTypes.DELETE
            )
            is_moderator = chat_message.conversation.can_moderate(user)

            if not has_delete_permission and not is_moderator:
                return DeleteMessageMutation(
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

        return DeleteMessageMutation(ok=ok, message=message)
