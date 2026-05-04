"""
NotificationUpdatesConsumer

WebSocket consumer for real-time notification updates.
Clients subscribe to receive instant notifications about:
- Badge awards (BADGE)
- Message replies (REPLY, THREAD_REPLY)
- Mentions (MENTION)
- Accepted answers (ACCEPTED)
- Moderation actions (THREAD_LOCKED, MESSAGE_DELETED, etc.)

This consumer is read-only - it only broadcasts updates when notifications
are created or updated via signals.

Security:
- User-specific channel groups (notification_user_{user_id})
- IDOR prevention: Only shows notifications for authenticated user
- Token validation via WebSocket auth middleware

Performance:
- Efficient channel layer broadcasting
- Minimal payload (only essential notification data)
- Heartbeat for connection health monitoring
- Graceful cleanup on disconnect

Issue #637: Migrate badge notifications from polling to WebSocket/SSE
"""

from __future__ import annotations

import json
import logging
import uuid

from channels.generic.websocket import AsyncWebsocketConsumer

from config.ratelimit.decorators import check_ws_rate_limit
from config.websocket.auth_handshake import AuthHandshakeMixin
from config.websocket.middleware import (
    WS_CLOSE_RATE_LIMITED,
    WS_CLOSE_UNAUTHENTICATED,
)

logger = logging.getLogger(__name__)


def get_notification_channel_group(user_id: int) -> str:
    """
    Get the channel group name for a user's notifications.

    Security: User-specific groups prevent cross-user data leakage.
    Each user only receives their own notifications.

    Args:
        user_id: The user's primary key

    Returns:
        Channel group name like "notification_user_123"
    """
    return f"notification_user_{user_id}"


class NotificationUpdatesConsumer(AuthHandshakeMixin, AsyncWebsocketConsumer):
    """
    WebSocket consumer for subscribing to real-time notification updates.

    Clients connect and receive instant updates when:
    - New notifications are created (via signals)
    - Notifications are marked as read/unread
    - Notifications are deleted

    This consumer does NOT handle GraphQL queries - use GET_NOTIFICATIONS for that.
    It only broadcasts real-time updates.

    Usage:
        ws://localhost:8000/ws/notification-updates/
        (No query parameters required - uses authenticated user)

    Message Types (Server -> Client):
        - CONNECTED: Connection established
        - NOTIFICATION_CREATED: New notification created
        - NOTIFICATION_UPDATED: Notification read status changed
        - NOTIFICATION_DELETED: Notification deleted
        - pong: Response to ping
        - heartbeat_ack: Response to heartbeat

    Message Types (Client -> Server):
        - ping: Check connection health
        - heartbeat: Keep connection alive

    Rate Limiting:
        Uses the shared rate limiting engine (config.ratelimit):
        - WS_CONNECT (10/m): Limits new connection attempts per user/IP.
        - WS_HEARTBEAT (120/m): Limits client-initiated messages (ping/heartbeat).
    """

    user_id: int | None = None
    session_id: str | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.consumer_id = uuid.uuid4()
        logger.debug(f"[NotificationUpdates {self.consumer_id}] __init__ called.")

    # -------------------------------------------------------------------------
    #  WebSocket lifecycle
    # -------------------------------------------------------------------------

    async def connect(self) -> None:
        """
        Authenticate user and subscribe to their notification channel.

        Security:
        - Rejects unauthenticated connections (code 4001)
        - Subscribes to user-specific channel group (prevents IDOR)
        - Validates user exists and is authenticated
        """
        self.session_id = str(uuid.uuid4())
        logger.debug(
            f"[NotificationUpdates {self.consumer_id} | Session {self.session_id}] "
            f"connect() called. Path: {self.scope['path']}"
        )

        # Rate limit new connections (skip JSON message — connection
        # is about to be closed so the client won't see it)
        if await check_ws_rate_limit(self, "WS_CONNECT", send_message=False):
            await self.close(code=WS_CLOSE_RATE_LIMITED)
            return

        # Extract user from scope (set by auth middleware)
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            logger.warning(
                f"[NotificationUpdates {self.consumer_id}] "
                "Unauthenticated connection rejected"
            )
            # 4000 (UNAUTHENTICATED) — there was no token at all. Use 4001
            # (TOKEN_EXPIRED) only when the middleware actually decoded a
            # token and found it expired (scope["auth_error"]). Otherwise
            # the frontend treats every anonymous-mount as "the user's
            # session expired" and stops reconnecting.
            await self.close(code=WS_CLOSE_UNAUTHENTICATED)
            return

        self.user_id = user.pk

        # Subscribe to user-specific notification channel
        # Security: Each user gets their own channel group
        self.room_group_name = get_notification_channel_group(self.user_id)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept_with_auth()
        logger.info(
            f"[NotificationUpdates {self.consumer_id}] "
            f"User {self.user_id} subscribed to {self.room_group_name}"
        )

        # Send connection confirmation
        await self.send(
            text_data=json.dumps(
                {
                    "type": "CONNECTED",
                    "user_id": str(self.user_id),
                    "session_id": self.session_id,
                }
            )
        )

    async def disconnect(self, close_code: int) -> None:
        """Leave the notification channel group on disconnect."""
        await self.cleanup_auth_handshake()
        if hasattr(self, "room_group_name") and self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )
            logger.info(
                f"[NotificationUpdates {self.consumer_id}] "
                f"User {self.user_id} disconnected from {self.room_group_name} "
                f"(code: {close_code})"
            )

    async def receive(self, text_data: str) -> None:
        """
        Handle incoming messages from client.

        This consumer is primarily for receiving broadcasts, but we handle
        a few client-initiated message types for connection management.

        Supported message types:
        - ping: Connection health check
        - heartbeat: Keep-alive message
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            logger.warning(
                f"[NotificationUpdates {self.consumer_id}] Invalid JSON received"
            )
            return

        if isinstance(data, dict) and data.get("type") == "AUTH":
            await self.handle_auth_message(data)
            return

        if await check_ws_rate_limit(self, "WS_HEARTBEAT"):
            return

        msg_type = data.get("type", "") if isinstance(data, dict) else ""

        if msg_type == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

        elif msg_type == "heartbeat":
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "heartbeat_ack",
                        "session_id": self.session_id,
                    }
                )
            )

        else:
            logger.debug(
                f"[NotificationUpdates {self.consumer_id}] "
                f"Unknown message type: {msg_type}"
            )

    # -------------------------------------------------------------------------
    #  Channel layer message handlers (from signals/tasks)
    # -------------------------------------------------------------------------

    async def notification_created(self, event: dict) -> None:
        """
        Handle new notification creation.

        Called when a notification is created via signals and broadcast
        through the channel layer.

        Event data:
        - notification_id: Notification primary key
        - notification_type: Type of notification (BADGE, REPLY, etc.)
        - created_at: ISO timestamp
        - is_read: Boolean read status
        - data: Additional notification context (badge info, etc.)
        - actor: User who triggered the notification (optional)
        - message_id: Related message ID (optional)
        - conversation_id: Related conversation ID (optional)
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "NOTIFICATION_CREATED",
                    "notificationId": event.get("notification_id"),
                    "notificationType": event.get("notification_type"),
                    "createdAt": event.get("created_at"),
                    "isRead": event.get("is_read", False),
                    "data": event.get("data"),
                    "actor": event.get("actor"),
                    "messageId": event.get("message_id"),
                    "conversationId": event.get("conversation_id"),
                }
            )
        )

    async def notification_updated(self, event: dict) -> None:
        """
        Handle notification update (e.g., marked as read).

        Event data:
        - notification_id: Notification primary key
        - is_read: Updated read status
        - modified: ISO timestamp of modification
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "NOTIFICATION_UPDATED",
                    "notificationId": event.get("notification_id"),
                    "isRead": event.get("is_read"),
                    "modified": event.get("modified"),
                }
            )
        )

    async def notification_deleted(self, event: dict) -> None:
        """
        Handle notification deletion.

        Event data:
        - notification_id: Notification primary key
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "NOTIFICATION_DELETED",
                    "notificationId": event.get("notification_id"),
                }
            )
        )
