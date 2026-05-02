"""
Signal handlers for the notifications app.

This file is imported in apps.py ready() method and creates notifications
in response to various events in the system.

Issue #637: Added WebSocket broadcasting for real-time notifications
"""

import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from opencontractserver.badges.models import UserBadge
from opencontractserver.conversations.models import (
    ChatMessage,
    ModerationAction,
    ModerationActionType,
)
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def broadcast_notification_via_websocket(notification: Notification) -> None:
    """
    Broadcast a notification to the user via WebSocket.

    Sends the notification through the channel layer to the user-specific
    notification channel group (notification_user_{user_id}).

    Security: User-specific channel groups prevent cross-user data leakage.
    Performance: Async broadcast doesn't block the request thread.

    Args:
        notification: The Notification instance to broadcast

    Issue #637: Real-time notification delivery via WebSocket
    """
    try:
        # Import here to avoid issues during Django startup
        from config.websocket.consumers.notification_updates import (
            get_notification_channel_group,
        )

        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning(
                "Channel layer not configured - notifications will not be "
                "broadcast via WebSocket"
            )
            return

        # Prepare notification data for WebSocket transmission
        # Use getattr with fallback for created_at in case bulk_create doesn't populate it
        created_at = getattr(notification, "created_at", None) or timezone.now()

        notification_data = {
            "type": "notification_created",
            "notification_id": str(notification.id),
            "notification_type": notification.notification_type,
            "created_at": created_at.isoformat(),
            "is_read": notification.is_read,
            "data": notification.data or {},
        }

        # Add optional fields if present
        if notification.actor:
            notification_data["actor"] = {
                "id": str(notification.actor.id),
                "username": notification.actor.username,
            }

        if notification.message_id:
            notification_data["message_id"] = str(notification.message_id)

        if notification.conversation_id:
            notification_data["conversation_id"] = str(notification.conversation_id)

        # Broadcast to user-specific channel group
        group_name = get_notification_channel_group(notification.recipient_id)
        async_to_sync(channel_layer.group_send)(group_name, notification_data)

        logger.debug(
            f"Broadcast {notification.notification_type} notification "
            f"to {group_name} (notification_id={notification.id})"
        )

    except Exception as e:
        # Don't fail the signal handler if WebSocket broadcast fails
        # Notification is still saved to database
        logger.error(
            f"Failed to broadcast notification {notification.id} via WebSocket: "
            f"{type(e).__name__}: {e}",
            exc_info=True,
        )


@receiver(post_save, sender=ChatMessage)
def create_reply_notification(
    sender: type[ChatMessage],
    instance: ChatMessage,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Create notification when a user replies to a message.

    Creates two types of notifications:
    1. REPLY: Direct reply to the parent message creator
    2. THREAD_REPLY: Reply in a thread the user is participating in
    """
    if not created:
        return

    message = instance

    # Don't notify if the message is from a system/bot
    if message.msg_type != "HUMAN":
        return

    # Don't create duplicate notifications during tests or fixtures
    if hasattr(instance, "_skip_signals"):
        return

    # 1. Notify parent message creator (direct reply)
    if message.parent_message and message.parent_message.creator:
        parent_creator = message.parent_message.creator

        # Don't notify self
        if parent_creator != message.creator:
            try:
                notification = Notification.objects.create(
                    recipient=parent_creator,
                    notification_type=NotificationTypeChoices.REPLY,
                    message=message,
                    conversation=message.conversation,
                    actor=message.creator,
                    data={
                        "parent_message_id": message.parent_message.id,
                        "reply_content_preview": message.content[:100],
                    },
                )
                logger.debug(
                    f"Created REPLY notification for {parent_creator.username} "
                    f"from {message.creator.username}"
                )
                # Broadcast via WebSocket for real-time delivery (Issue #637)
                broadcast_notification_via_websocket(notification)
            except Exception as e:
                logger.error(
                    f"Failed to create REPLY notification: {type(e).__name__}: {e}",
                    exc_info=True,
                )

    # 2. Notify thread participants (excluding direct parent reply to avoid duplicates)
    if message.conversation and message.conversation.conversation_type == "thread":
        try:
            # Get all users who have posted in this thread
            # Exclude the new message itself to prevent race conditions
            participant_ids = (
                ChatMessage.objects.filter(conversation=message.conversation)
                .exclude(pk=message.pk)  # Exclude the new message itself
                .exclude(creator=message.creator)  # Don't notify self
                .values_list("creator_id", flat=True)
                .distinct()
            )

            # Build list of notifications to create in bulk (performance optimization)
            notifications_to_create = []
            for participant_id in participant_ids:
                # Skip if this is the parent message creator (already notified above)
                if (
                    message.parent_message
                    and message.parent_message.creator_id == participant_id
                ):
                    continue

                notifications_to_create.append(
                    Notification(
                        recipient_id=participant_id,
                        notification_type=NotificationTypeChoices.THREAD_REPLY,
                        message=message,
                        conversation=message.conversation,
                        actor=message.creator,
                        data={
                            "thread_title": message.conversation.title,
                            "reply_content_preview": message.content[:100],
                        },
                    )
                )

            # Use bulk_create to avoid N+1 query problem
            if notifications_to_create:
                try:
                    created_notifications = Notification.objects.bulk_create(
                        notifications_to_create
                    )
                    logger.debug(
                        f"Created {len(created_notifications)} THREAD_REPLY "
                        f"notifications for thread {message.conversation.id}"
                    )
                    # Broadcast each notification via WebSocket (Issue #637)
                    for notification in created_notifications:
                        broadcast_notification_via_websocket(notification)
                except Exception as e:
                    logger.error(
                        f"Failed to bulk create THREAD_REPLY notifications: "
                        f"{type(e).__name__}: {e}",
                        exc_info=True,
                    )

        except Exception as e:
            logger.error(
                f"Failed to process thread participant notifications: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )


@receiver(post_save, sender=ChatMessage)
def create_mention_notification(
    sender: type[ChatMessage],
    instance: ChatMessage,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Create notification when a user is mentioned in a message.

    Detects @username mentions in message content and notifies mentioned users.
    """
    if not created:
        return

    message = instance

    # Don't process system messages
    if message.msg_type != "HUMAN":
        return

    # Don't create duplicate notifications during tests or fixtures
    if hasattr(instance, "_skip_signals"):
        return

    # Extract mentions from message content
    mentioned_usernames = Notification.extract_mentions(message.content)

    if not mentioned_usernames:
        return

    # Find users who were mentioned
    try:
        mentioned_users = User.objects.filter(username__in=mentioned_usernames)

        for user in mentioned_users:
            # Don't notify self
            if user == message.creator:
                continue

            try:
                notification = Notification.objects.create(
                    recipient=user,
                    notification_type=NotificationTypeChoices.MENTION,
                    message=message,
                    conversation=message.conversation,
                    actor=message.creator,
                    data={
                        "mention_context": message.content[:200],
                    },
                )
                logger.debug(
                    f"Created MENTION notification for {user.username} "
                    f"in message {message.id}"
                )
                # Broadcast via WebSocket for real-time delivery (Issue #637)
                broadcast_notification_via_websocket(notification)
            except Exception as e:
                logger.error(
                    f"Failed to create MENTION notification for {user.username}: "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )

    except Exception as e:
        logger.error(
            f"Failed to process mentions: {type(e).__name__}: {e}", exc_info=True
        )


@receiver(post_save, sender=UserBadge)
def create_badge_notification(
    sender: type[UserBadge],
    instance: UserBadge,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Create notification when a user is awarded a badge.
    """
    if not created:
        return

    user_badge = instance

    # Don't create duplicate notifications during tests or fixtures
    if hasattr(instance, "_skip_signals"):
        return

    try:
        notification = Notification.objects.create(
            recipient=user_badge.user,
            notification_type=NotificationTypeChoices.BADGE,
            actor=user_badge.awarded_by,  # May be None for auto-awards
            data={
                "badge_id": user_badge.badge.id,
                "badge_name": user_badge.badge.name,
                "badge_description": user_badge.badge.description,
                "badge_icon": user_badge.badge.icon,
                "badge_color": user_badge.badge.color,
                "is_auto_awarded": user_badge.awarded_by is None,
            },
        )
        logger.debug(
            f"Created BADGE notification for {user_badge.user.username}: "
            f"{user_badge.badge.name}"
        )
        # Broadcast via WebSocket for real-time delivery (Issue #637)
        broadcast_notification_via_websocket(notification)
    except Exception as e:
        logger.error(
            f"Failed to create BADGE notification: {type(e).__name__}: {e}",
            exc_info=True,
        )


@receiver(post_save, sender=ModerationAction)
def create_moderation_notification(
    sender: type[ModerationAction],
    instance: ModerationAction,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Create notifications for moderation actions.

    Notifies affected users when their content is moderated.
    """
    if not created:
        return

    action = instance

    # Don't create duplicate notifications during tests or fixtures
    if hasattr(instance, "_skip_signals"):
        return

    # Map action types to notification types. ``ModerationActionType`` is
    # a :class:`TextChoices` subclass, so each enum member is *also* a
    # ``str`` — we annotate the dict with ``str`` keys so the lookup with
    # ``action.action_type`` (a plain ``str`` coming back from the DB)
    # type-checks without a cast.
    action_to_notification: dict[str, NotificationTypeChoices] = {
        ModerationActionType.LOCK_THREAD: NotificationTypeChoices.THREAD_LOCKED,
        ModerationActionType.UNLOCK_THREAD: NotificationTypeChoices.THREAD_UNLOCKED,
        ModerationActionType.PIN_THREAD: NotificationTypeChoices.THREAD_PINNED,
        ModerationActionType.UNPIN_THREAD: NotificationTypeChoices.THREAD_UNPINNED,
        ModerationActionType.DELETE_MESSAGE: NotificationTypeChoices.MESSAGE_DELETED,
        ModerationActionType.DELETE_THREAD: NotificationTypeChoices.THREAD_DELETED,
        ModerationActionType.RESTORE_MESSAGE: NotificationTypeChoices.MESSAGE_RESTORED,
        ModerationActionType.RESTORE_THREAD: NotificationTypeChoices.THREAD_RESTORED,
    }

    notification_type = action_to_notification.get(action.action_type)
    if not notification_type:
        logger.debug(f"No notification type mapped for action: {action.action_type}")
        return

    # A ``ModerationAction`` without a moderator is a data inconsistency
    # we have no way to notify about; skip it rather than raise.
    if action.moderator is None:
        logger.debug(f"Moderation action {action.id} has no moderator, skipping")
        return

    # Determine recipient based on action type
    recipient = None

    if action.message:
        # Message-level action: notify message creator
        recipient = action.message.creator
    elif action.conversation:
        # Thread-level action: notify thread creator
        recipient = action.conversation.creator

    if not recipient:
        logger.debug(f"No recipient for moderation action {action.id}")
        return

    # Don't notify if moderator is acting on their own content
    if recipient == action.moderator:
        return

    try:
        notification = Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            message=action.message,
            conversation=action.conversation,
            actor=action.moderator,
            data={
                "action_type": action.action_type,
                "reason": action.reason,
                "moderator_username": action.moderator.username,
            },
        )
        logger.debug(
            f"Created {notification_type} notification for {recipient.username} "
            f"by {action.moderator.username}"
        )
        # Broadcast via WebSocket for real-time delivery (Issue #637)
        broadcast_notification_via_websocket(notification)
    except Exception as e:
        logger.error(
            f"Failed to create moderation notification: {type(e).__name__}: {e}",
            exc_info=True,
        )
