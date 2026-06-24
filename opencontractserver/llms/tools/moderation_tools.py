"""
Moderation tools for thread and message management.

These tools allow agents to:
1. Read thread/message context for moderation decisions
2. Take moderation actions (lock/pin/delete with proper audit logging)
3. Post agent messages to threads

All moderation actions use existing model methods which handle:
- Permission checking (can_moderate)
- Audit logging (ModerationAction creation)
- Proper state management

## Permission Model for Automated Actions

When tools are called by agents (automated corpus actions), the `moderator_id`
should be a user with moderation rights on the thread's corpus. The model
methods enforce permission checks via `can_moderate()` which grants access to:
- Superusers
- Thread creator
- Corpus owner
- Designated corpus moderators

For automated actions triggered by corpus actions, the corpus owner (who
configured the action) inherently has moderation rights, so passing their
user ID as moderator_id will always succeed. If a different user ID is passed,
the action will fail with PermissionError if they lack moderation rights.
This is intentional fail-closed security behavior.
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


# Default limit for thread messages retrieval
DEFAULT_THREAD_MESSAGE_LIMIT = 20


# --------------------------------------------------------------------------- #
# Context Retrieval Tools (Read-only, no approval needed)
# --------------------------------------------------------------------------- #


def get_thread_context(thread_id: int) -> dict[str, Any]:
    """
    Get thread metadata and status.

    Args:
        thread_id: Primary key of the Conversation (thread)

    Returns:
        Dictionary with thread metadata including title, creator, lock/pin status
    """
    from opencontractserver.conversations.models import Conversation

    try:
        thread = Conversation.objects.select_related(
            "creator",
            "chat_with_corpus",
            "chat_with_document",
            "locked_by",
            "pinned_by",
        ).get(pk=thread_id)
    except Conversation.DoesNotExist:
        raise ValueError(f"Thread with id={thread_id} does not exist.")

    return {
        "id": thread.id,
        "title": thread.title,
        "description": thread.description or "",
        "creator_id": thread.creator_id,
        "creator_username": thread.creator.username if thread.creator else None,
        "created_at": thread.created_at.isoformat(),
        "is_locked": thread.is_locked,
        "locked_at": thread.locked_at.isoformat() if thread.locked_at else None,
        "locked_by_username": thread.locked_by.username if thread.locked_by else None,
        "is_pinned": thread.is_pinned,
        "pinned_at": thread.pinned_at.isoformat() if thread.pinned_at else None,
        "pinned_by_username": thread.pinned_by.username if thread.pinned_by else None,
        "corpus_id": thread.chat_with_corpus_id,
        "corpus_title": (
            thread.chat_with_corpus.title if thread.chat_with_corpus else None
        ),
        "document_id": thread.chat_with_document_id,
        "document_title": (
            thread.chat_with_document.title if thread.chat_with_document else None
        ),
        "message_count": thread.chat_messages.count(),
        "is_deleted": thread.deleted_at is not None,
    }


async def aget_thread_context(thread_id: int) -> dict[str, Any]:
    """Async version of get_thread_context."""
    return await sync_to_async(get_thread_context, thread_sensitive=False)(thread_id)


def get_thread_messages(
    thread_id: int,
    limit: int = DEFAULT_THREAD_MESSAGE_LIMIT,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """
    Retrieve recent messages from a thread.

    Args:
        thread_id: Primary key of the Conversation (thread)
        limit: Maximum messages to return (most recent first)
        include_deleted: Whether to include soft-deleted messages

    Returns:
        List of message dictionaries with content, author, timestamps, votes
    """
    from opencontractserver.conversations.models import ChatMessage, Conversation

    try:
        thread = Conversation.objects.get(pk=thread_id)
    except Conversation.DoesNotExist:
        raise ValueError(f"Thread with id={thread_id} does not exist.")

    if include_deleted:
        messages_qs = ChatMessage.all_objects.filter(conversation=thread)
    else:
        messages_qs = ChatMessage.objects.filter(conversation=thread)

    messages_qs = messages_qs.select_related("creator").order_by("-created_at")[:limit]

    return [
        {
            "id": msg.id,
            "content": msg.content,
            "msg_type": msg.msg_type,
            "creator_id": msg.creator_id,
            "creator_username": msg.creator.username if msg.creator else None,
            "created_at": msg.created_at.isoformat(),
            "is_deleted": msg.deleted_at is not None,
            "upvote_count": msg.upvote_count,
            "downvote_count": msg.downvote_count,
            "parent_message_id": msg.parent_message_id,
        }
        for msg in messages_qs
    ]


async def aget_thread_messages(
    thread_id: int,
    limit: int = DEFAULT_THREAD_MESSAGE_LIMIT,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """Async version of get_thread_messages."""
    return await sync_to_async(get_thread_messages, thread_sensitive=False)(
        thread_id=thread_id,
        limit=limit,
        include_deleted=include_deleted,
    )


def get_message_content(message_id: int) -> dict[str, Any]:
    """
    Get full content and metadata for a specific message.

    Args:
        message_id: Primary key of the ChatMessage

    Returns:
        Dictionary with full message content and metadata
    """
    from opencontractserver.conversations.models import ChatMessage

    try:
        msg = ChatMessage.all_objects.select_related(
            "creator", "conversation", "parent_message"
        ).get(pk=message_id)
    except ChatMessage.DoesNotExist:
        raise ValueError(f"Message with id={message_id} does not exist.")

    return {
        "id": msg.id,
        "content": msg.content,
        "msg_type": msg.msg_type,
        "creator_id": msg.creator_id,
        "creator_username": msg.creator.username if msg.creator else None,
        "thread_id": msg.conversation_id,
        "thread_title": msg.conversation.title,
        "created_at": msg.created_at.isoformat(),
        "is_deleted": msg.deleted_at is not None,
        "deleted_at": msg.deleted_at.isoformat() if msg.deleted_at else None,
        "upvote_count": msg.upvote_count,
        "downvote_count": msg.downvote_count,
        "parent_message_id": msg.parent_message_id,
        "reply_count": msg.replies.count(),
    }


async def aget_message_content(message_id: int) -> dict[str, Any]:
    """Async version of get_message_content."""
    return await sync_to_async(get_message_content, thread_sensitive=False)(message_id)


# --------------------------------------------------------------------------- #
# Moderation Action Tools (require approval when not pre-authorized)
# --------------------------------------------------------------------------- #


def delete_message(
    message_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """
    Soft delete a message.

    Uses existing model method for proper audit logging via ModerationAction.

    Args:
        message_id: ID of the message to delete
        reason: Reason for deletion (stored in ModerationAction)
        moderator_id: User ID of the moderator (agent's creator)

    Returns:
        Success status and details
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.conversations.models import ChatMessage

    User = get_user_model()

    try:
        msg = ChatMessage.objects.get(pk=message_id)
    except ChatMessage.DoesNotExist:
        raise ValueError(f"Message with id={message_id} does not exist.")

    try:
        moderator = User.objects.get(pk=moderator_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={moderator_id} does not exist.")

    # Use existing soft_delete_message method which handles permission checks
    # and creates ModerationAction record
    msg.soft_delete_message(moderator=moderator, reason=reason)

    logger.info(
        f"Message {message_id} deleted by agent (moderator: {moderator.username})"
    )

    return {
        "success": True,
        "message_id": message_id,
        "action": "deleted",
        "reason": reason,
    }


async def adelete_message(
    message_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """Async version of delete_message."""
    return await sync_to_async(delete_message, thread_sensitive=False)(
        message_id=message_id,
        reason=reason,
        moderator_id=moderator_id,
    )


def lock_thread(
    thread_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """
    Lock a thread to prevent new messages.

    Uses existing model method for proper audit logging.

    Args:
        thread_id: ID of the thread to lock
        reason: Reason for locking (stored in ModerationAction)
        moderator_id: User ID of the moderator

    Returns:
        Success status and details
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.conversations.models import Conversation

    User = get_user_model()

    try:
        thread = Conversation.objects.get(pk=thread_id)
    except Conversation.DoesNotExist:
        raise ValueError(f"Thread with id={thread_id} does not exist.")

    try:
        moderator = User.objects.get(pk=moderator_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={moderator_id} does not exist.")

    if thread.is_locked:
        return {
            "success": False,
            "thread_id": thread_id,
            "action": "lock",
            "message": "Thread is already locked",
        }

    # Use existing lock method
    thread.lock(moderator=moderator, reason=reason)

    logger.info(f"Thread {thread_id} locked by agent (moderator: {moderator.username})")

    return {
        "success": True,
        "thread_id": thread_id,
        "action": "locked",
        "reason": reason,
    }


async def alock_thread(
    thread_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """Async version of lock_thread."""
    return await sync_to_async(lock_thread, thread_sensitive=False)(
        thread_id=thread_id,
        reason=reason,
        moderator_id=moderator_id,
    )


def unlock_thread(
    thread_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """
    Unlock a previously locked thread.

    Args:
        thread_id: ID of the thread to unlock
        reason: Reason for unlocking (stored in ModerationAction)
        moderator_id: User ID of the moderator

    Returns:
        Success status and details
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.conversations.models import Conversation

    User = get_user_model()

    try:
        thread = Conversation.objects.get(pk=thread_id)
    except Conversation.DoesNotExist:
        raise ValueError(f"Thread with id={thread_id} does not exist.")

    try:
        moderator = User.objects.get(pk=moderator_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={moderator_id} does not exist.")

    if not thread.is_locked:
        return {
            "success": False,
            "thread_id": thread_id,
            "action": "unlock",
            "message": "Thread is not locked",
        }

    thread.unlock(moderator=moderator, reason=reason)

    logger.info(
        f"Thread {thread_id} unlocked by agent (moderator: {moderator.username})"
    )

    return {
        "success": True,
        "thread_id": thread_id,
        "action": "unlocked",
        "reason": reason,
    }


async def aunlock_thread(
    thread_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """Async version of unlock_thread."""
    return await sync_to_async(unlock_thread, thread_sensitive=False)(
        thread_id=thread_id,
        reason=reason,
        moderator_id=moderator_id,
    )


def add_thread_message(
    thread_id: int,
    content: str,
    agent_config_id: int,
    creator_id: int,
) -> dict[str, Any]:
    """
    Post an agent message to a thread.

    Creates a ChatMessage with LLM type and agent_configuration set.

    Args:
        thread_id: ID of the thread
        content: Message content (markdown supported)
        agent_config_id: ID of the AgentConfiguration posting the message
        creator_id: User ID for the message creator attribution

    Returns:
        Created message details
    """
    from opencontractserver.agents.models import AgentConfiguration
    from opencontractserver.conversations.models import (
        ChatMessage,
        Conversation,
        MessageTypeChoices,
    )

    try:
        thread = Conversation.objects.get(pk=thread_id)
    except Conversation.DoesNotExist:
        raise ValueError(f"Thread with id={thread_id} does not exist.")

    if thread.is_locked:
        raise ValueError(f"Thread {thread_id} is locked and cannot accept new messages")

    try:
        agent_config = AgentConfiguration.objects.get(pk=agent_config_id)
    except AgentConfiguration.DoesNotExist:
        raise ValueError(
            f"AgentConfiguration with id={agent_config_id} does not exist."
        )

    # Create message with LLM type and agent attribution
    # Note: We set _skip_signals to prevent triggering additional corpus actions
    message = ChatMessage(
        conversation=thread,
        msg_type=MessageTypeChoices.LLM,
        content=content,
        creator_id=creator_id,
        agent_configuration=agent_config,
    )
    message._skip_signals = True
    message.save()

    logger.info(
        f"Agent message posted to thread {thread_id} (agent_config: {agent_config.name})"
    )

    return {
        "success": True,
        "message_id": message.id,
        "thread_id": thread_id,
        "content_preview": content[:200] if len(content) > 200 else content,
    }


async def aadd_thread_message(
    thread_id: int,
    content: str,
    agent_config_id: int,
    creator_id: int,
) -> dict[str, Any]:
    """Async version of add_thread_message."""
    return await sync_to_async(add_thread_message, thread_sensitive=False)(
        thread_id=thread_id,
        content=content,
        agent_config_id=agent_config_id,
        creator_id=creator_id,
    )


def pin_thread(
    thread_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """
    Pin a thread to the top of the list.

    Args:
        thread_id: ID of the thread to pin
        reason: Reason for pinning (stored in ModerationAction)
        moderator_id: User ID of the moderator

    Returns:
        Success status and details
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.conversations.models import Conversation

    User = get_user_model()

    try:
        thread = Conversation.objects.get(pk=thread_id)
    except Conversation.DoesNotExist:
        raise ValueError(f"Thread with id={thread_id} does not exist.")

    try:
        moderator = User.objects.get(pk=moderator_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={moderator_id} does not exist.")

    if thread.is_pinned:
        return {
            "success": False,
            "thread_id": thread_id,
            "action": "pin",
            "message": "Thread is already pinned",
        }

    thread.pin(moderator=moderator, reason=reason)

    logger.info(f"Thread {thread_id} pinned by agent (moderator: {moderator.username})")

    return {
        "success": True,
        "thread_id": thread_id,
        "action": "pinned",
        "reason": reason,
    }


async def apin_thread(
    thread_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """Async version of pin_thread."""
    return await sync_to_async(pin_thread, thread_sensitive=False)(
        thread_id=thread_id,
        reason=reason,
        moderator_id=moderator_id,
    )


def unpin_thread(
    thread_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """
    Unpin a thread.

    Args:
        thread_id: ID of the thread to unpin
        reason: Reason for unpinning (stored in ModerationAction)
        moderator_id: User ID of the moderator

    Returns:
        Success status and details
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.conversations.models import Conversation

    User = get_user_model()

    try:
        thread = Conversation.objects.get(pk=thread_id)
    except Conversation.DoesNotExist:
        raise ValueError(f"Thread with id={thread_id} does not exist.")

    try:
        moderator = User.objects.get(pk=moderator_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={moderator_id} does not exist.")

    if not thread.is_pinned:
        return {
            "success": False,
            "thread_id": thread_id,
            "action": "unpin",
            "message": "Thread is not pinned",
        }

    thread.unpin(moderator=moderator, reason=reason)

    logger.info(
        f"Thread {thread_id} unpinned by agent (moderator: {moderator.username})"
    )

    return {
        "success": True,
        "thread_id": thread_id,
        "action": "unpinned",
        "reason": reason,
    }


async def aunpin_thread(
    thread_id: int,
    reason: str,
    moderator_id: int,
) -> dict[str, Any]:
    """Async version of unpin_thread."""
    return await sync_to_async(unpin_thread, thread_sensitive=False)(
        thread_id=thread_id,
        reason=reason,
        moderator_id=moderator_id,
    )
