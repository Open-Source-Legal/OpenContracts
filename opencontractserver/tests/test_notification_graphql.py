"""
Tests for notification GraphQL API in OpenContracts.

This module tests Epic #562: Notification System
Sub-issue #564: Create GraphQL queries and mutations for notifications

Tests cover:
1. GraphQL queries for notifications
2. GraphQL mutations for managing notifications
3. Permission checks (users can only access their own notifications)
4. Pagination and filtering
5. Unread count queries
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.conversations.models import (
    Conversation,
    ConversationTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)

User = get_user_model()


class TestNotificationQueries(TestCase):
    """Test GraphQL queries for notifications."""

    def setUp(self):
        """Create test data for each test."""
        self.client = Client(schema)

        self.user1 = User.objects.create_user(
            username="query_user1",
            password="testpass123",
            email="query1@test.com",
        )

        self.user2 = User.objects.create_user(
            username="query_user2",
            password="testpass123",
            email="query2@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Query Test Corpus",
            creator=self.user1,
            is_public=True,
        )

        self.thread = Conversation.objects.create(
            conversation_type=ConversationTypeChoices.THREAD,
            title="Query Test Thread",
            chat_with_corpus=self.corpus,
            creator=self.user1,
            is_public=True,
        )

        # Create some notifications for user1
        self.notif1 = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.REPLY,
            actor=self.user2,
            is_read=False,
        )

        self.notif2 = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.BADGE,
            actor=self.user2,
            is_read=True,
        )

        self.notif3 = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.MENTION,
            actor=self.user2,
            conversation=self.thread,
            is_read=False,
        )

        # Create notification for user2
        self.notif_user2 = Notification.objects.create(
            recipient=self.user2,
            notification_type=NotificationTypeChoices.REPLY,
            actor=self.user1,
            is_read=False,
        )

    def test_query_notifications(self):
        """Test querying notifications for the current user."""
        query = """
            query {
                notifications {
                    edges {
                        node {
                            id
                            notificationType
                            isRead
                            actor {
                                username
                            }
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["notifications"]["edges"]

        # User1 should see 3 notifications
        self.assertEqual(len(edges), 3)

        # Check they're ordered by created_at descending (most recent first)
        notification_ids = [edge["node"]["id"] for edge in edges]
        expected_ids = [
            to_global_id("NotificationType", self.notif3.id),
            to_global_id("NotificationType", self.notif2.id),
            to_global_id("NotificationType", self.notif1.id),
        ]
        self.assertEqual(notification_ids, expected_ids)

    def test_query_notifications_filters_by_user(self):
        """Test that users can only see their own notifications."""
        query = """
            query {
                notifications {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user2})()
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["notifications"]["edges"]

        # User2 should see only 1 notification
        self.assertEqual(len(edges), 1)
        notification_id = edges[0]["node"]["id"]
        expected_id = to_global_id("NotificationType", self.notif_user2.id)
        self.assertEqual(notification_id, expected_id)

    def test_query_unread_notification_count(self):
        """Test getting count of unread notifications."""
        query = """
            query {
                unreadNotificationCount
            }
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        count = result["data"]["unreadNotificationCount"]

        # User1 has 2 unread notifications
        self.assertEqual(count, 2)

    def test_query_single_notification(self):
        """Test querying a single notification by ID."""
        notification_id = to_global_id("NotificationType", self.notif1.id)

        query = f"""
            query {{
                notification(id: "{notification_id}") {{
                    id
                    notificationType
                    isRead
                    recipient {{
                        username
                    }}
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        notification = result["data"]["notification"]

        self.assertEqual(notification["id"], notification_id)
        self.assertEqual(notification["notificationType"], "REPLY")
        self.assertFalse(notification["isRead"])

    def test_query_notification_permission_check(self):
        """Test that users cannot access other users' notifications in list."""
        query = """
            query {
                notifications {
                    edges {
                        node {
                            id
                            recipient {
                                username
                            }
                        }
                    }
                }
            }
        """

        # User2 should only see their own notifications, not user1's
        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user2})()
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["notifications"]["edges"]

        # User2 should only see 1 notification (their own)
        self.assertEqual(len(edges), 1)

        # Verify it's user2's notification
        self.assertEqual(edges[0]["node"]["recipient"]["username"], "query_user2")

    def test_query_notifications_unauthenticated(self):
        """Test that unauthenticated users get empty results."""
        query = """
            query {
                notifications {
                    edges {
                        node {
                            id
                        }
                    }
                }
                unreadNotificationCount
            }
        """

        result = self.client.execute(
            query,
            context_value=type(
                "Request",
                (),
                {"user": type("AnonymousUser", (), {"is_authenticated": False})()},
            )(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertEqual(len(result["data"]["notifications"]["edges"]), 0)
        self.assertEqual(result["data"]["unreadNotificationCount"], 0)


class TestNotificationMutations(TestCase):
    """Test GraphQL mutations for notifications."""

    def setUp(self):
        """Create test data for each test."""
        self.client = Client(schema)

        self.user1 = User.objects.create_user(
            username="mutation_user1",
            password="testpass123",
            email="mutation1@test.com",
        )

        self.user2 = User.objects.create_user(
            username="mutation_user2",
            password="testpass123",
            email="mutation2@test.com",
        )

        self.notif1 = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.REPLY,
            actor=self.user2,
            is_read=False,
        )

        self.notif2 = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.BADGE,
            actor=self.user2,
            is_read=False,
        )

        self.notif_user2 = Notification.objects.create(
            recipient=self.user2,
            notification_type=NotificationTypeChoices.REPLY,
            actor=self.user1,
            is_read=False,
        )

    def test_mark_notification_read(self):
        """Test marking a single notification as read."""
        notification_id = to_global_id("NotificationType", self.notif1.id)

        mutation = f"""
            mutation {{
                markNotificationRead(notificationId: "{notification_id}") {{
                    ok
                    message
                    notification {{
                        id
                        isRead
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["markNotificationRead"]

        self.assertTrue(data["ok"])
        self.assertTrue(data["notification"]["isRead"])

        # Verify in database
        self.notif1.refresh_from_db()
        self.assertTrue(self.notif1.is_read)

    def test_mark_notification_unread(self):
        """Test marking a notification as unread."""
        # First mark it as read
        self.notif1.is_read = True
        self.notif1.save()

        notification_id = to_global_id("NotificationType", self.notif1.id)

        mutation = f"""
            mutation {{
                markNotificationUnread(notificationId: "{notification_id}") {{
                    ok
                    message
                    notification {{
                        id
                        isRead
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["markNotificationUnread"]

        self.assertTrue(data["ok"])
        self.assertFalse(data["notification"]["isRead"])

        # Verify in database
        self.notif1.refresh_from_db()
        self.assertFalse(self.notif1.is_read)

    def test_mark_notification_read_permission_check(self):
        """Test that users cannot mark other users' notifications as read."""
        notification_id = to_global_id("NotificationType", self.notif1.id)

        mutation = f"""
            mutation {{
                markNotificationRead(notificationId: "{notification_id}") {{
                    ok
                    message
                }}
            }}
        """

        # User2 tries to mark user1's notification
        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user2})()
        )

        # Should return ok=False with consistent error message to prevent IDOR enumeration
        self.assertIsNone(result.get("errors"))
        data = result["data"]["markNotificationRead"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_mark_all_notifications_read(self):
        """Test marking all notifications as read."""
        mutation = """
            mutation {
                markAllNotificationsRead {
                    ok
                    message
                    count
                }
            }
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["markAllNotificationsRead"]

        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 2)  # User1 had 2 unread notifications

        # Verify in database
        unread_count = Notification.objects.filter(
            recipient=self.user1, is_read=False
        ).count()
        self.assertEqual(unread_count, 0)

    def test_mark_all_notifications_read_only_affects_own(self):
        """Test that marking all as read only affects the current user."""
        mutation = """
            mutation {
                markAllNotificationsRead {
                    ok
                    count
                }
            }
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["markAllNotificationsRead"]["ok"])

        # User2's notification should still be unread
        self.notif_user2.refresh_from_db()
        self.assertFalse(self.notif_user2.is_read)

    def test_delete_notification(self):
        """Test deleting a notification."""
        notification_id = to_global_id("NotificationType", self.notif1.id)

        mutation = f"""
            mutation {{
                deleteNotification(notificationId: "{notification_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteNotification"]

        self.assertTrue(data["ok"])

        # Verify notification is deleted
        self.assertFalse(Notification.objects.filter(id=self.notif1.id).exists())

    def test_delete_notification_permission_check(self):
        """Test that users cannot delete other users' notifications."""
        notification_id = to_global_id("NotificationType", self.notif1.id)

        mutation = f"""
            mutation {{
                deleteNotification(notificationId: "{notification_id}") {{
                    ok
                    message
                }}
            }}
        """

        # User2 tries to delete user1's notification
        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user2})()
        )

        # Should return ok=False with consistent error message to prevent IDOR enumeration
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteNotification"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

        # Verify notification still exists
        self.assertTrue(Notification.objects.filter(id=self.notif1.id).exists())

    def test_delete_nonexistent_notification(self):
        """Test deleting a notification that doesn't exist."""
        fake_id = to_global_id("NotificationType", 99999)

        mutation = f"""
            mutation {{
                deleteNotification(notificationId: "{fake_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteNotification"]

        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())
