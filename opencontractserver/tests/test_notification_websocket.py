"""
Tests for NotificationUpdatesConsumer WebSocket endpoint.

Issue #637: Real-time notification delivery via WebSocket

Tests cover:
- Authentication and authorization
- Connection lifecycle
- Notification broadcasting
- IDOR prevention (user isolation)
- Heartbeat/ping-pong
- Signal integration
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test.utils import override_settings

from config.asgi import application
from config.websocket.consumers.notification_updates import (
    get_notification_channel_group,
)
from config.websocket.middleware import WS_AUTH_SUBPROTOCOL
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

User = get_user_model()
logger = logging.getLogger(__name__)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class NotificationWebSocketTestCase(WebsocketFixtureBaseTestCase):
    """Tests for notification WebSocket consumer."""

    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        # Create test users
        self.user1 = User.objects.create_user(
            username="testuser1", email="user1@test.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="testuser2", email="user2@test.com", password="testpass123"
        )

    @database_sync_to_async
    def _create_notification(
        self, recipient: User, notification_type: str
    ) -> Notification:
        """Create a test notification."""
        return Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            data={"test": "data"},
        )

    @database_sync_to_async
    def _create_badge_notification(self, user: User) -> tuple[UserBadge, Notification]:
        """Create a badge and badge notification."""
        # Create badge (BaseOCModel requires creator field)
        badge = Badge.objects.create(
            name="Test Badge",
            description="Test Description",
            icon="Award",
            color="#05313d",
            creator=user,
        )

        # Create user badge (this will trigger signal and create notification)
        user_badge = UserBadge.objects.create(
            user=user,
            badge=badge,
            awarded_by=None,  # Auto-awarded
        )

        # Get the created notification
        notification = Notification.objects.filter(
            recipient=user, notification_type=NotificationTypeChoices.BADGE
        ).latest("created_at")

        return user_badge, notification

    @database_sync_to_async
    def _create_conversation(self) -> Conversation:
        """Create a test conversation."""
        return Conversation.objects.create(
            title="Test Thread",
            creator=self.user1,
            conversation_type="thread",
        )

    @database_sync_to_async
    def _create_chat_message(
        self, conversation: Conversation, creator: User, content: str
    ) -> ChatMessage:
        """Create a chat message."""
        return ChatMessage.objects.create(
            conversation=conversation,
            creator=creator,
            content=content,
            msg_type="HUMAN",
        )

    async def test_unauthenticated_connection_rejected(self):
        """Unauthenticated connections should be rejected with code 4001."""
        ws_path = "ws/notification-updates/"
        communicator = WebsocketCommunicator(application, ws_path)
        connected, subprotocol = await communicator.connect()

        # Should reject connection
        self.assertFalse(connected)

    async def test_authenticated_connection_accepted(self):
        """Authenticated users should be able to connect."""
        ws_path = "ws/notification-updates/"
        communicator = WebsocketCommunicator(
            application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, subprotocol = await communicator.connect()

        self.assertTrue(connected)

        # Drain initial AUTH_OK frame from auth handshake mixin
        raw = await communicator.receive_from(timeout=5)
        self.assertEqual(json.loads(raw)["type"], "AUTH_OK")

        # Should receive CONNECTED message
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "CONNECTED")
        self.assertIn("user_id", data)
        self.assertIn("session_id", data)

        await communicator.disconnect()

    async def test_ping_pong(self):
        """Client should be able to ping and receive pong."""
        ws_path = "ws/notification-updates/"
        communicator = WebsocketCommunicator(
            application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Drain initial AUTH_OK + CONNECTED messages
        await communicator.receive_from(timeout=5)
        await communicator.receive_from(timeout=5)

        # Send ping
        await communicator.send_to(json.dumps({"type": "ping"}))

        # Should receive pong
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)
        self.assertEqual(data["type"], "pong")

        await communicator.disconnect()

    async def test_heartbeat_ack(self):
        """Client should be able to send heartbeat and receive ack."""
        ws_path = "ws/notification-updates/"
        communicator = WebsocketCommunicator(
            application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Drain initial AUTH_OK + CONNECTED messages
        await communicator.receive_from(timeout=5)
        await communicator.receive_from(timeout=5)

        # Send heartbeat
        await communicator.send_to(json.dumps({"type": "heartbeat"}))

        # Should receive heartbeat_ack
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)
        self.assertEqual(data["type"], "heartbeat_ack")
        self.assertIn("session_id", data)

        await communicator.disconnect()

    async def test_invalid_json_handling(self):
        """Consumer should gracefully handle invalid JSON from client."""
        ws_path = "ws/notification-updates/"
        communicator = WebsocketCommunicator(
            application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Drain initial AUTH_OK + CONNECTED messages
        await communicator.receive_from(timeout=5)
        await communicator.receive_from(timeout=5)

        # Send invalid JSON (should be logged and ignored, not crash)
        await communicator.send_to("this is not valid json {{{")

        # Connection should still work - send ping and expect pong
        await communicator.send_to(json.dumps({"type": "ping"}))
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)
        self.assertEqual(data["type"], "pong")

        await communicator.disconnect()

    async def test_unknown_message_type_handling(self):
        """Consumer should gracefully handle unknown message types."""
        ws_path = "ws/notification-updates/"
        communicator = WebsocketCommunicator(
            application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Drain initial AUTH_OK + CONNECTED messages
        await communicator.receive_from(timeout=5)
        await communicator.receive_from(timeout=5)

        # Send unknown message type (should be logged and ignored)
        await communicator.send_to(json.dumps({"type": "UNKNOWN_TYPE", "data": "test"}))

        # Connection should still work - send ping and expect pong
        await communicator.send_to(json.dumps({"type": "ping"}))
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)
        self.assertEqual(data["type"], "pong")

        await communicator.disconnect()

    async def test_notification_broadcast_via_channel_layer(self):
        """Notifications should be broadcast via channel layer."""
        ws_path = "ws/notification-updates/"
        communicator = WebsocketCommunicator(
            application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Drain initial AUTH_OK + CONNECTED messages
        await communicator.receive_from(timeout=5)
        await communicator.receive_from(timeout=5)

        # Manually send notification via channel layer
        # (simulating what the signal handler does)
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_created",
                "notification_id": "123",
                "notification_type": "BADGE",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {
                    "badge_id": "456",
                    "badge_name": "Test Badge",
                },
            },
        )

        # Should receive notification
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "NOTIFICATION_CREATED")
        self.assertEqual(data["notificationId"], "123")
        self.assertEqual(data["notificationType"], "BADGE")
        self.assertFalse(data["isRead"])
        self.assertEqual(data["data"]["badge_id"], "456")

        await communicator.disconnect()

    async def test_user_isolation_idor_prevention(self):
        """Users should only receive their own notifications (IDOR prevention)."""
        # Connect user1
        communicator1 = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected1, _ = await communicator1.connect()
        self.assertTrue(connected1)
        await communicator1.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator1.receive_from(timeout=5)  # Drain CONNECTED

        # Create user2's token
        user2 = await database_sync_to_async(
            lambda: User.objects.get(username="testuser2")
        )()
        from graphql_jwt.shortcuts import get_token

        user2_token_str = await database_sync_to_async(get_token)(user2)

        # Connect user2
        communicator2 = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, user2_token_str],
        )
        connected2, _ = await communicator2.connect()
        self.assertTrue(connected2)
        await communicator2.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator2.receive_from(timeout=5)  # Drain CONNECTED

        # Send notification to user2's channel group ONLY
        channel_layer = get_channel_layer()
        user2_group = get_notification_channel_group(user2.pk)

        await channel_layer.group_send(
            user2_group,
            {
                "type": "notification_created",
                "notification_id": "999",
                "notification_type": "BADGE",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {"test": "user2_only"},
            },
        )

        # User2 should receive the notification
        response2 = await communicator2.receive_from(timeout=5)
        data2 = json.loads(response2)
        self.assertEqual(data2["notificationId"], "999")

        # User1 should NOT receive anything (timeout expected)
        # WebsocketCommunicator.receive_from raises either TimeoutError or
        # asyncio.CancelledError on timeout depending on Python version
        import asyncio

        try:
            await communicator1.receive_from(timeout=2)
            # If we get here, we received unexpected data
            self.fail("User1 should not have received notification destined for User2")
        except (TimeoutError, asyncio.CancelledError):
            # Expected: no message received (IDOR prevention working correctly)
            pass

        # Clean up connections - may also raise CancelledError in some cases
        try:
            await communicator1.disconnect()
        except asyncio.CancelledError:
            pass  # Connection already terminated due to timeout
        await communicator2.disconnect()

    @patch(
        "opencontractserver.notifications.signals.broadcast_notification_via_websocket"
    )
    async def test_badge_award_triggers_broadcast(self, mock_broadcast):
        """Badge award should trigger WebSocket broadcast via signal."""
        # Create badge award (triggers signal)
        user_badge, notification = await self._create_badge_notification(self.user)

        # Verify broadcast was called
        self.assertTrue(mock_broadcast.called)
        call_args = mock_broadcast.call_args[0]
        broadcast_notification = call_args[0]

        self.assertEqual(broadcast_notification.recipient, self.user)
        self.assertEqual(
            broadcast_notification.notification_type, NotificationTypeChoices.BADGE
        )

    async def test_notification_update_broadcast(self):
        """Notification updates should be broadcast."""
        communicator = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator.receive_from(timeout=5)  # Drain CONNECTED

        # Send notification update via channel layer
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_updated",
                "notification_id": "123",
                "is_read": True,
                "modified": "2025-01-01T00:00:00Z",
            },
        )

        # Should receive update
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "NOTIFICATION_UPDATED")
        self.assertEqual(data["notificationId"], "123")
        self.assertTrue(data["isRead"])

        await communicator.disconnect()

    async def test_notification_deleted_broadcast(self):
        """Notification deletions should be broadcast."""
        communicator = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator.receive_from(timeout=5)  # Drain CONNECTED

        # Send notification deletion via channel layer
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_deleted",
                "notification_id": "123",
            },
        )

        # Should receive deletion
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "NOTIFICATION_DELETED")
        self.assertEqual(data["notificationId"], "123")

        await communicator.disconnect()

    async def test_multiple_concurrent_connections(self):
        """Multiple users can connect concurrently without interference."""
        # Connect user1 twice (simulate multiple tabs)
        communicator1a = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected1a, _ = await communicator1a.connect()
        self.assertTrue(connected1a)
        await communicator1a.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator1a.receive_from(timeout=5)  # Drain CONNECTED

        communicator1b = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected1b, _ = await communicator1b.connect()
        self.assertTrue(connected1b)
        await communicator1b.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator1b.receive_from(timeout=5)  # Drain CONNECTED

        # Send notification to user1's channel group
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_created",
                "notification_id": "777",
                "notification_type": "MENTION",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {},
            },
        )

        # Both connections should receive the notification
        response1a = await communicator1a.receive_from(timeout=5)
        data1a = json.loads(response1a)
        self.assertEqual(data1a["notificationId"], "777")

        response1b = await communicator1b.receive_from(timeout=5)
        data1b = json.loads(response1b)
        self.assertEqual(data1b["notificationId"], "777")

        await communicator1a.disconnect()
        await communicator1b.disconnect()

    async def test_disconnect_cleanup(self):
        """Disconnecting should remove user from channel group."""
        communicator = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator.receive_from(timeout=5)  # Drain CONNECTED

        # Disconnect
        await communicator.disconnect()

        # Send notification to the channel group
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_created",
                "notification_id": "888",
                "notification_type": "BADGE",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {},
            },
        )

        # No error should occur (consumer is no longer in group)
        # This test verifies cleanup happened without errors

    async def test_document_processed_notification_broadcast(self):
        """DOCUMENT_PROCESSED notifications should be broadcast correctly (Issue #624)."""
        communicator = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator.receive_from(timeout=5)  # Drain CONNECTED

        # Send DOCUMENT_PROCESSED notification via channel layer
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_created",
                "notification_id": "doc-123",
                "notification_type": "DOCUMENT_PROCESSED",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {
                    "document_id": 42,
                    "document_title": "Test Document",
                    "page_count": 10,
                    "file_type": "application/pdf",
                },
            },
        )

        # Should receive notification
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "NOTIFICATION_CREATED")
        self.assertEqual(data["notificationId"], "doc-123")
        self.assertEqual(data["notificationType"], "DOCUMENT_PROCESSED")
        self.assertEqual(data["data"]["document_title"], "Test Document")
        self.assertEqual(data["data"]["page_count"], 10)

        await communicator.disconnect()

    async def test_extract_complete_notification_broadcast(self):
        """EXTRACT_COMPLETE notifications should be broadcast correctly (Issue #624)."""
        communicator = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator.receive_from(timeout=5)  # Drain CONNECTED

        # Send EXTRACT_COMPLETE notification via channel layer
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_created",
                "notification_id": "extract-456",
                "notification_type": "EXTRACT_COMPLETE",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {
                    "extract_id": 99,
                    "extract_name": "Test Extract",
                    "document_count": 5,
                    "fieldset_name": "Test Fieldset",
                },
            },
        )

        # Should receive notification
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "NOTIFICATION_CREATED")
        self.assertEqual(data["notificationId"], "extract-456")
        self.assertEqual(data["notificationType"], "EXTRACT_COMPLETE")
        self.assertEqual(data["data"]["extract_name"], "Test Extract")
        self.assertEqual(data["data"]["document_count"], 5)

        await communicator.disconnect()

    async def test_analysis_complete_notification_broadcast(self):
        """ANALYSIS_COMPLETE notifications should be broadcast correctly (Issue #624)."""
        communicator = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator.receive_from(timeout=5)  # Drain CONNECTED

        # Send ANALYSIS_COMPLETE notification via channel layer
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_created",
                "notification_id": "analysis-789",
                "notification_type": "ANALYSIS_COMPLETE",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {
                    "analysis_id": 55,
                    "analyzer_name": "Test Analyzer",
                    "corpus_name": "Test Corpus",
                    "status": "completed",
                },
            },
        )

        # Should receive notification
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "NOTIFICATION_CREATED")
        self.assertEqual(data["notificationId"], "analysis-789")
        self.assertEqual(data["notificationType"], "ANALYSIS_COMPLETE")
        self.assertEqual(data["data"]["analyzer_name"], "Test Analyzer")
        self.assertEqual(data["data"]["status"], "completed")

        await communicator.disconnect()

    async def test_analysis_failed_notification_broadcast(self):
        """ANALYSIS_FAILED notifications should be broadcast correctly (Issue #624)."""
        communicator = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator.receive_from(timeout=5)  # Drain CONNECTED

        # Send ANALYSIS_FAILED notification via channel layer
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_created",
                "notification_id": "analysis-fail-321",
                "notification_type": "ANALYSIS_FAILED",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {
                    "analysis_id": 66,
                    "analyzer_name": "Failing Analyzer",
                    "corpus_name": "Test Corpus",
                    "status": "failed",
                },
            },
        )

        # Should receive notification
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "NOTIFICATION_CREATED")
        self.assertEqual(data["notificationId"], "analysis-fail-321")
        self.assertEqual(data["notificationType"], "ANALYSIS_FAILED")
        self.assertEqual(data["data"]["status"], "failed")

        await communicator.disconnect()

    async def test_export_complete_notification_broadcast(self):
        """EXPORT_COMPLETE notifications should be broadcast correctly (Issue #624)."""
        communicator = WebsocketCommunicator(
            application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # Drain AUTH_OK
        await communicator.receive_from(timeout=5)  # Drain CONNECTED

        # Send EXPORT_COMPLETE notification via channel layer
        channel_layer = get_channel_layer()
        group_name = get_notification_channel_group(self.user.pk)

        await channel_layer.group_send(
            group_name,
            {
                "type": "notification_created",
                "notification_id": "export-999",
                "notification_type": "EXPORT_COMPLETE",
                "created_at": "2025-01-01T00:00:00Z",
                "is_read": False,
                "data": {
                    "export_id": 77,
                    "export_name": "My Export",
                    "corpus_name": "Test Corpus",
                    "format": "OPEN_CONTRACTS",
                },
            },
        )

        # Should receive notification
        response = await communicator.receive_from(timeout=5)
        data = json.loads(response)

        self.assertEqual(data["type"], "NOTIFICATION_CREATED")
        self.assertEqual(data["notificationId"], "export-999")
        self.assertEqual(data["notificationType"], "EXPORT_COMPLETE")
        self.assertEqual(data["data"]["corpus_name"], "Test Corpus")
        self.assertEqual(data["data"]["format"], "OPEN_CONTRACTS")

        await communicator.disconnect()
