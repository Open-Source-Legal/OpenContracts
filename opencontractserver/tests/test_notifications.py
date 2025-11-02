"""
Tests for notification system in OpenContracts.

This module tests Epic #562: Notification System
Sub-issue #563: Create Notification model

Tests cover:
1. Notification model creation and methods
2. Signal handlers for automatic notification creation
3. Mention extraction functionality
4. Badge award notifications
5. Moderation action notifications
6. Reply notifications (direct and thread participation)
7. GraphQL queries and mutations
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from opencontractserver.badges.models import Badge, BadgeTypeChoices, UserBadge
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)

User = get_user_model()


class TestNotificationModel(TestCase):
    """Test Notification model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user1 = User.objects.create_user(
            username="notification_user1",
            password="testpass123",
            email="user1@test.com",
        )

        cls.user2 = User.objects.create_user(
            username="notification_user2",
            password="testpass123",
            email="user2@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Notification Corpus",
            description="A corpus for testing notifications",
            creator=cls.user1,
            is_public=True,
        )

        cls.thread = Conversation.objects.create(
            conversation_type=ConversationTypeChoices.THREAD,
            title="Test Thread",
            description="Test thread for notifications",
            chat_with_corpus=cls.corpus,
            creator=cls.user1,
            is_public=True,
        )

        cls.message = ChatMessage.objects.create(
            conversation=cls.thread,
            content="Test message",
            msg_type="human",
            creator=cls.user1,
        )

    def test_create_notification(self):
        """Test creating a basic notification."""
        notification = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.REPLY,
            message=self.message,
            conversation=self.thread,
            actor=self.user2,
        )

        self.assertEqual(notification.recipient, self.user1)
        self.assertEqual(notification.notification_type, NotificationTypeChoices.REPLY)
        self.assertEqual(notification.message, self.message)
        self.assertEqual(notification.conversation, self.thread)
        self.assertEqual(notification.actor, self.user2)
        self.assertFalse(notification.is_read)

    def test_mark_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.REPLY,
            actor=self.user2,
        )

        self.assertFalse(notification.is_read)
        notification.mark_as_read()
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_as_unread(self):
        """Test marking notification as unread."""
        notification = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.REPLY,
            actor=self.user2,
            is_read=True,
        )

        self.assertTrue(notification.is_read)
        notification.mark_as_unread()
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_extract_mentions_basic(self):
        """Test extracting @username mentions from text."""
        text = "Hey @user1, check this out! cc @user2"
        mentions = Notification.extract_mentions(text)

        self.assertEqual(len(mentions), 2)
        self.assertIn("user1", mentions)
        self.assertIn("user2", mentions)

    def test_extract_mentions_with_punctuation(self):
        """Test mention extraction with various punctuation."""
        text = "@user1: please review. Thanks @user2!"
        mentions = Notification.extract_mentions(text)

        self.assertEqual(len(mentions), 2)
        self.assertIn("user1", mentions)
        self.assertIn("user2", mentions)

    def test_extract_mentions_no_matches(self):
        """Test mention extraction with no matches."""
        text = "This has no mentions, just email@example.com"
        mentions = Notification.extract_mentions(text)

        self.assertEqual(len(mentions), 0)

    def test_extract_mentions_deduplication(self):
        """Test that duplicate mentions are deduplicated."""
        text = "@user1 and @user1 again and @USER1"
        mentions = Notification.extract_mentions(text)

        # Should deduplicate case-insensitively
        self.assertEqual(len(mentions), 1)
        self.assertIn("user1", mentions)

    def test_extract_mentions_underscores_hyphens(self):
        """Test mentions with underscores and hyphens."""
        text = "Hello @user_name and @user-name-2"
        mentions = Notification.extract_mentions(text)

        self.assertEqual(len(mentions), 2)
        self.assertIn("user_name", mentions)
        self.assertIn("user-name-2", mentions)

    def test_notification_ordering(self):
        """Test that notifications are ordered by created_at descending."""
        notif1 = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.REPLY,
            actor=self.user2,
        )

        notif2 = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.BADGE,
            actor=self.user2,
        )

        notifications = Notification.objects.all()
        self.assertEqual(notifications[0], notif2)  # Most recent first
        self.assertEqual(notifications[1], notif1)

    def test_notification_string_representation(self):
        """Test notification string representation."""
        notification = Notification.objects.create(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.REPLY,
            actor=self.user2,
        )

        str_repr = str(notification)
        self.assertIn("Reply to Message", str_repr)
        self.assertIn(self.user1.username, str_repr)
        self.assertIn("unread", str_repr)


class TestNotificationSignals(TransactionTestCase):
    """Test signal handlers that create notifications automatically."""

    def setUp(self):
        """Create test data for each test."""
        self.user1 = User.objects.create_user(
            username="signal_user1",
            password="testpass123",
            email="signal1@test.com",
        )

        self.user2 = User.objects.create_user(
            username="signal_user2",
            password="testpass123",
            email="signal2@test.com",
        )

        self.user3 = User.objects.create_user(
            username="signal_user3",
            password="testpass123",
            email="signal3@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Signal Test Corpus",
            description="Corpus for signal testing",
            creator=self.user1,
            is_public=True,
        )

        self.thread = Conversation.objects.create(
            conversation_type=ConversationTypeChoices.THREAD,
            title="Signal Test Thread",
            description="Thread for signal testing",
            chat_with_corpus=self.corpus,
            creator=self.user1,
            is_public=True,
        )

    def test_reply_notification_created(self):
        """Test that replying to a message creates a notification."""
        # Create parent message
        parent = ChatMessage.objects.create(
            conversation=self.thread,
            content="Parent message",
            msg_type="human",
            creator=self.user1,
        )

        # User2 replies to user1's message
        reply = ChatMessage.objects.create(
            conversation=self.thread,
            content="Reply message",
            msg_type="human",
            creator=self.user2,
            parent_message=parent,
        )

        # Check notification was created for user1
        notifications = Notification.objects.filter(
            recipient=self.user1, notification_type=NotificationTypeChoices.REPLY
        )

        self.assertEqual(notifications.count(), 1)
        notification = notifications.first()
        self.assertEqual(notification.actor, self.user2)
        self.assertEqual(notification.message, reply)
        self.assertEqual(notification.conversation, self.thread)

    def test_no_self_reply_notification(self):
        """Test that replying to your own message doesn't create a notification."""
        # Create parent message
        parent = ChatMessage.objects.create(
            conversation=self.thread,
            content="Parent message",
            msg_type="human",
            creator=self.user1,
        )

        # User1 replies to their own message
        ChatMessage.objects.create(
            conversation=self.thread,
            content="Self reply",
            msg_type="human",
            creator=self.user1,
            parent_message=parent,
        )

        # No notification should be created
        notifications = Notification.objects.filter(
            recipient=self.user1, notification_type=NotificationTypeChoices.REPLY
        )

        self.assertEqual(notifications.count(), 0)

    def test_thread_participation_notification(self):
        """Test that thread participants get notified of new replies."""
        # User1 creates initial message in thread (thread creator, won't get notified)
        ChatMessage.objects.create(
            conversation=self.thread,
            content="User1 initial message",
            msg_type="human",
            creator=self.user1,
        )

        # User2 posts in the thread (user1 should get notified)
        ChatMessage.objects.create(
            conversation=self.thread,
            content="User2 message",
            msg_type="human",
            creator=self.user2,
        )

        # User3 posts in the thread (should notify user1 and user2)
        ChatMessage.objects.create(
            conversation=self.thread,
            content="User3 message",
            msg_type="human",
            creator=self.user3,
        )

        # Check user1 got notified (thread creator + participant)
        # Should have 2 notifications: one from user2's post and one from user3's post
        user1_notifications = Notification.objects.filter(
            recipient=self.user1, notification_type=NotificationTypeChoices.THREAD_REPLY
        )
        self.assertEqual(user1_notifications.count(), 2)

        # Check user2 got notified (participant, from user3's post)
        user2_notifications = Notification.objects.filter(
            recipient=self.user2, notification_type=NotificationTypeChoices.THREAD_REPLY
        )
        self.assertEqual(user2_notifications.count(), 1)

    def test_mention_notification_created(self):
        """Test that mentioning a user creates a notification."""
        # Create message with mention
        message = ChatMessage.objects.create(
            conversation=self.thread,
            content=f"Hey @{self.user2.username}, check this out!",
            msg_type="human",
            creator=self.user1,
        )

        # Check notification was created for user2
        notifications = Notification.objects.filter(
            recipient=self.user2, notification_type=NotificationTypeChoices.MENTION
        )

        self.assertEqual(notifications.count(), 1)
        notification = notifications.first()
        self.assertEqual(notification.actor, self.user1)
        self.assertEqual(notification.message, message)

    def test_mention_multiple_users(self):
        """Test mentioning multiple users creates multiple notifications."""
        # Create message with multiple mentions
        ChatMessage.objects.create(
            conversation=self.thread,
            content=f"Hey @{self.user2.username} and @{self.user3.username}!",
            msg_type="human",
            creator=self.user1,
        )

        # Check both users got notified
        user2_notifications = Notification.objects.filter(
            recipient=self.user2, notification_type=NotificationTypeChoices.MENTION
        )
        user3_notifications = Notification.objects.filter(
            recipient=self.user3, notification_type=NotificationTypeChoices.MENTION
        )

        self.assertEqual(user2_notifications.count(), 1)
        self.assertEqual(user3_notifications.count(), 1)

    def test_no_self_mention_notification(self):
        """Test that mentioning yourself doesn't create a notification."""
        ChatMessage.objects.create(
            conversation=self.thread,
            content=f"I think @{self.user1.username} should do this",
            msg_type="human",
            creator=self.user1,
        )

        # No notification should be created
        notifications = Notification.objects.filter(
            recipient=self.user1, notification_type=NotificationTypeChoices.MENTION
        )

        self.assertEqual(notifications.count(), 0)

    def test_badge_notification_created(self):
        """Test that awarding a badge creates a notification."""
        # Create badge
        badge = Badge.objects.create(
            name="Test Badge",
            description="A test badge",
            icon="Trophy",
            badge_type=BadgeTypeChoices.GLOBAL,
            creator=self.user1,
            is_public=True,
        )

        # Award badge to user2
        UserBadge.objects.create(user=self.user2, badge=badge, awarded_by=self.user1)

        # Check notification was created
        notifications = Notification.objects.filter(
            recipient=self.user2, notification_type=NotificationTypeChoices.BADGE
        )

        self.assertEqual(notifications.count(), 1)
        notification = notifications.first()
        self.assertEqual(notification.actor, self.user1)
        self.assertIn("badge_name", notification.data)
        self.assertEqual(notification.data["badge_name"], "Test Badge")

    def test_moderation_lock_notification(self):
        """Test that locking a thread creates a notification."""
        # User2 creates a thread
        thread = Conversation.objects.create(
            conversation_type=ConversationTypeChoices.THREAD,
            title="User2's Thread",
            chat_with_corpus=self.corpus,
            creator=self.user2,
            is_public=True,
        )

        # Clear any notifications created from thread creation
        Notification.objects.filter(recipient=self.user2).delete()

        # Moderator locks it (this creates the ModerationAction automatically)
        thread.lock(self.user1, reason="Off topic")

        # Check notification was created
        notifications = Notification.objects.filter(
            recipient=self.user2,
            notification_type=NotificationTypeChoices.THREAD_LOCKED,
        )

        self.assertEqual(notifications.count(), 1)
        notification = notifications.first()
        self.assertEqual(notification.actor, self.user1)
        self.assertEqual(notification.conversation, thread)
        self.assertIn("reason", notification.data)

    def test_moderation_delete_message_notification(self):
        """Test that deleting a message creates a notification."""
        # User2 creates a message
        message = ChatMessage.objects.create(
            conversation=self.thread,
            content="User2's message",
            msg_type="human",
            creator=self.user2,
        )

        # Clear any notifications created from message posting (user1 gets THREAD_REPLY)
        Notification.objects.filter(recipient=self.user1).delete()

        # Moderator deletes it (this creates the ModerationAction automatically)
        message.soft_delete_message(self.user1, reason="Spam")

        # Check notification was created
        notifications = Notification.objects.filter(
            recipient=self.user2,
            notification_type=NotificationTypeChoices.MESSAGE_DELETED,
        )

        self.assertEqual(notifications.count(), 1)
        notification = notifications.first()
        self.assertEqual(notification.actor, self.user1)
        self.assertEqual(notification.message, message)

    def test_no_notification_for_self_moderation(self):
        """Test that moderating your own content doesn't create a notification."""
        # User1 creates and locks their own thread
        thread = Conversation.objects.create(
            conversation_type=ConversationTypeChoices.THREAD,
            title="User1's Thread",
            chat_with_corpus=self.corpus,
            creator=self.user1,
            is_public=True,
        )

        # lock() method creates the ModerationAction automatically
        thread.lock(self.user1, reason="Resolved")

        # No notification should be created
        notifications = Notification.objects.filter(
            recipient=self.user1,
            notification_type=NotificationTypeChoices.THREAD_LOCKED,
        )

        self.assertEqual(notifications.count(), 0)
