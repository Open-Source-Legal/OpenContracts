"""
Tests for Corpus Engagement Metrics functionality.

This module tests Epic #565: Corpus Engagement Metrics & Analytics

Tests cover:
1. CorpusEngagementMetrics model creation
2. OneToOne relationship with Corpus
3. Default values for all metrics fields
4. Metrics querying and retrieval
5. Signal-based metrics creation (if implemented)
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    MessageVote,
    VoteType,
)
from opencontractserver.corpuses.models import Corpus, CorpusEngagementMetrics

User = get_user_model()


class TestCorpusEngagementMetricsModel(TestCase):
    """Test the CorpusEngagementMetrics model."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="metrics_testuser",
            password="testpass123",
            email="metrics@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Metrics Corpus",
            description="A corpus for testing engagement metrics",
            creator=cls.user,
            is_public=True,
        )

    def test_create_engagement_metrics(self):
        """Test creating engagement metrics for a corpus."""
        metrics = CorpusEngagementMetrics.objects.create(corpus=self.corpus)

        self.assertEqual(metrics.corpus, self.corpus)
        self.assertEqual(metrics.total_threads, 0)
        self.assertEqual(metrics.active_threads, 0)
        self.assertEqual(metrics.total_messages, 0)
        self.assertEqual(metrics.messages_last_7_days, 0)
        self.assertEqual(metrics.messages_last_30_days, 0)
        self.assertEqual(metrics.unique_contributors, 0)
        self.assertEqual(metrics.active_contributors_30_days, 0)
        self.assertEqual(metrics.total_upvotes, 0)
        self.assertEqual(metrics.avg_messages_per_thread, 0.0)
        self.assertIsNotNone(metrics.last_updated)

    def test_onetoone_relationship_with_corpus(self):
        """Test that metrics has OneToOne relationship with corpus."""
        metrics = CorpusEngagementMetrics.objects.create(corpus=self.corpus)

        # Access metrics from corpus
        self.assertEqual(self.corpus.engagement_metrics, metrics)

        # Attempting to create another metrics record for the same corpus should fail
        with self.assertRaises(Exception):  # IntegrityError
            CorpusEngagementMetrics.objects.create(corpus=self.corpus)

    def test_metrics_string_representation(self):
        """Test the string representation of metrics."""
        metrics = CorpusEngagementMetrics.objects.create(corpus=self.corpus)

        expected_str = f"Engagement Metrics for {self.corpus.title}"
        self.assertEqual(str(metrics), expected_str)

    def test_metrics_default_values(self):
        """Test that all metrics have sensible default values."""
        metrics = CorpusEngagementMetrics.objects.create(corpus=self.corpus)

        # All count fields should default to 0
        self.assertEqual(metrics.total_threads, 0)
        self.assertEqual(metrics.active_threads, 0)
        self.assertEqual(metrics.total_messages, 0)
        self.assertEqual(metrics.messages_last_7_days, 0)
        self.assertEqual(metrics.messages_last_30_days, 0)
        self.assertEqual(metrics.unique_contributors, 0)
        self.assertEqual(metrics.active_contributors_30_days, 0)
        self.assertEqual(metrics.total_upvotes, 0)

        # Float field should default to 0.0
        self.assertEqual(metrics.avg_messages_per_thread, 0.0)

        # Timestamp should be auto-set
        self.assertIsNotNone(metrics.last_updated)

    def test_metrics_cascade_delete_with_corpus(self):
        """Test that metrics are deleted when corpus is deleted."""
        metrics = CorpusEngagementMetrics.objects.create(corpus=self.corpus)
        metrics_id = metrics.id

        # Delete the corpus
        self.corpus.delete()

        # Metrics should be deleted too (CASCADE)
        with self.assertRaises(CorpusEngagementMetrics.DoesNotExist):
            CorpusEngagementMetrics.objects.get(id=metrics_id)

    def test_metrics_can_be_updated(self):
        """Test that metrics can be updated with calculated values."""
        metrics = CorpusEngagementMetrics.objects.create(corpus=self.corpus)

        # Update metrics with test values
        metrics.total_threads = 10
        metrics.active_threads = 8
        metrics.total_messages = 50
        metrics.messages_last_7_days = 15
        metrics.messages_last_30_days = 35
        metrics.unique_contributors = 5
        metrics.active_contributors_30_days = 3
        metrics.total_upvotes = 25
        metrics.avg_messages_per_thread = 5.0
        metrics.save()

        # Reload and verify
        metrics.refresh_from_db()
        self.assertEqual(metrics.total_threads, 10)
        self.assertEqual(metrics.active_threads, 8)
        self.assertEqual(metrics.total_messages, 50)
        self.assertEqual(metrics.messages_last_7_days, 15)
        self.assertEqual(metrics.messages_last_30_days, 35)
        self.assertEqual(metrics.unique_contributors, 5)
        self.assertEqual(metrics.active_contributors_30_days, 3)
        self.assertEqual(metrics.total_upvotes, 25)
        self.assertEqual(metrics.avg_messages_per_thread, 5.0)


class TestCorpusEngagementMetricsCalculation(TestCase):
    """Test engagement metrics calculation logic."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with threads, messages, and votes."""
        cls.user1 = User.objects.create_user(
            username="user1",
            password="testpass123",
            email="user1@test.com",
        )
        cls.user2 = User.objects.create_user(
            username="user2",
            password="testpass123",
            email="user2@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Engagement Corpus",
            description="A corpus with threads and messages",
            creator=cls.user1,
            is_public=True,
        )

        # Create some threads
        cls.thread1 = Conversation.objects.create(
            title="Thread 1",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=cls.user1,
            chat_with_corpus=cls.corpus,
        )
        cls.thread2 = Conversation.objects.create(
            title="Thread 2",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=cls.user2,
            chat_with_corpus=cls.corpus,
        )

        # Create messages in thread1
        cls.msg1 = ChatMessage.objects.create(
            conversation=cls.thread1,
            msg_type="HUMAN",
            content="First message in thread 1",
            creator=cls.user1,
        )
        cls.msg2 = ChatMessage.objects.create(
            conversation=cls.thread1,
            msg_type="HUMAN",
            content="Second message in thread 1",
            creator=cls.user2,
        )

        # Create message in thread2
        cls.msg3 = ChatMessage.objects.create(
            conversation=cls.thread2,
            msg_type="HUMAN",
            content="First message in thread 2",
            creator=cls.user1,
        )

        # Create some votes
        MessageVote.objects.create(
            message=cls.msg1,
            vote_type=VoteType.UPVOTE,
            creator=cls.user2,
        )
        MessageVote.objects.create(
            message=cls.msg2,
            vote_type=VoteType.UPVOTE,
            creator=cls.user1,
        )

    def test_manual_metrics_calculation(self):
        """Test manually calculating metrics from database."""
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        # Calculate metrics
        threads = Conversation.objects.filter(
            chat_with_corpus=self.corpus,
            conversation_type=ConversationTypeChoices.THREAD,
            deleted_at__isnull=True,
        )

        total_threads = threads.count()
        active_threads = threads.filter(is_locked=False).count()

        messages = ChatMessage.objects.filter(
            conversation__chat_with_corpus=self.corpus,
            conversation__conversation_type=ConversationTypeChoices.THREAD,
            deleted_at__isnull=True,
        )

        total_messages = messages.count()
        messages_last_7_days = messages.filter(created_at__gte=seven_days_ago).count()
        messages_last_30_days = messages.filter(created_at__gte=thirty_days_ago).count()

        unique_contributors = messages.values("creator").distinct().count()
        active_contributors_30_days = (
            messages.filter(created_at__gte=thirty_days_ago)
            .values("creator")
            .distinct()
            .count()
        )

        total_upvotes = MessageVote.objects.filter(
            message__conversation__chat_with_corpus=self.corpus,
            vote_type=VoteType.UPVOTE,
        ).count()

        avg_messages_per_thread = (
            total_messages / total_threads if total_threads > 0 else 0.0
        )

        # Verify calculations
        self.assertEqual(total_threads, 2)
        self.assertEqual(active_threads, 2)
        self.assertEqual(total_messages, 3)
        self.assertEqual(messages_last_7_days, 3)  # All messages are recent
        self.assertEqual(messages_last_30_days, 3)
        self.assertEqual(unique_contributors, 2)  # user1 and user2
        self.assertEqual(active_contributors_30_days, 2)
        self.assertEqual(total_upvotes, 2)
        self.assertEqual(avg_messages_per_thread, 1.5)

        # Create metrics record and update it
        metrics = CorpusEngagementMetrics.objects.create(corpus=self.corpus)
        metrics.total_threads = total_threads
        metrics.active_threads = active_threads
        metrics.total_messages = total_messages
        metrics.messages_last_7_days = messages_last_7_days
        metrics.messages_last_30_days = messages_last_30_days
        metrics.unique_contributors = unique_contributors
        metrics.active_contributors_30_days = active_contributors_30_days
        metrics.total_upvotes = total_upvotes
        metrics.avg_messages_per_thread = avg_messages_per_thread
        metrics.save()

        # Verify stored metrics
        metrics.refresh_from_db()
        self.assertEqual(metrics.total_threads, 2)
        self.assertEqual(metrics.active_threads, 2)
        self.assertEqual(metrics.total_messages, 3)
        self.assertEqual(metrics.messages_last_7_days, 3)
        self.assertEqual(metrics.messages_last_30_days, 3)
        self.assertEqual(metrics.unique_contributors, 2)
        self.assertEqual(metrics.active_contributors_30_days, 2)
        self.assertEqual(metrics.total_upvotes, 2)
        self.assertEqual(metrics.avg_messages_per_thread, 1.5)

    def test_metrics_with_locked_thread(self):
        """Test that locked threads are excluded from active_threads count."""
        # Lock thread1
        self.thread1.is_locked = True
        self.thread1.save()

        threads = Conversation.objects.filter(
            chat_with_corpus=self.corpus,
            conversation_type=ConversationTypeChoices.THREAD,
            deleted_at__isnull=True,
        )

        total_threads = threads.count()
        active_threads = threads.filter(is_locked=False).count()

        self.assertEqual(total_threads, 2)  # Still 2 total
        self.assertEqual(active_threads, 1)  # Only 1 active

    def test_metrics_with_deleted_thread(self):
        """Test that soft-deleted threads are excluded."""
        from django.utils import timezone

        # Soft delete thread1
        self.thread1.deleted_at = timezone.now()
        self.thread1.save()

        threads = Conversation.objects.filter(
            chat_with_corpus=self.corpus,
            conversation_type=ConversationTypeChoices.THREAD,
            deleted_at__isnull=True,
        )

        total_threads = threads.count()

        self.assertEqual(total_threads, 1)  # Only 1 non-deleted thread
