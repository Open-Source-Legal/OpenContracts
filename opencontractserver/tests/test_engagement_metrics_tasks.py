"""
Tests for Engagement Metrics Celery Tasks.

This module tests Epic #565: Corpus Engagement Metrics & Analytics
Specifically, Issue #567: Create Celery periodic task for updating engagement metrics

Tests cover:
1. update_corpus_engagement_metrics task execution
2. Metrics calculation accuracy
3. Performance considerations
4. Error handling
5. update_all_corpus_engagement_metrics batch processing
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    MessageVote,
    VoteType,
)
from opencontractserver.corpuses.models import Corpus, CorpusEngagementMetrics
from opencontractserver.tasks.corpus_tasks import (
    update_all_corpus_engagement_metrics,
    update_corpus_engagement_metrics,
)

User = get_user_model()


class TestUpdateCorpusEngagementMetricsTask(TestCase):
    """Test the update_corpus_engagement_metrics Celery task."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user1 = User.objects.create_user(
            username="task_user1",
            password="testpass123",
            email="task_user1@test.com",
        )
        cls.user2 = User.objects.create_user(
            username="task_user2",
            password="testpass123",
            email="task_user2@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Task Test Corpus",
            description="A corpus for testing metrics tasks",
            creator=cls.user1,
            is_public=True,
        )

        # Create threads and messages
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

        # Create messages
        cls.msg1 = ChatMessage.objects.create(
            conversation=cls.thread1,
            msg_type="HUMAN",
            content="Message 1",
            creator=cls.user1,
        )
        cls.msg2 = ChatMessage.objects.create(
            conversation=cls.thread1,
            msg_type="HUMAN",
            content="Message 2",
            creator=cls.user2,
        )
        cls.msg3 = ChatMessage.objects.create(
            conversation=cls.thread2,
            msg_type="HUMAN",
            content="Message 3",
            creator=cls.user1,
        )

        # Create votes
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

    def test_task_creates_metrics_record(self):
        """Test that task creates a metrics record if it doesn't exist."""
        # Ensure no metrics exist
        self.assertFalse(
            CorpusEngagementMetrics.objects.filter(corpus=self.corpus).exists()
        )

        # Run the task
        result = update_corpus_engagement_metrics(self.corpus.id)

        # Verify metrics record was created
        self.assertTrue(
            CorpusEngagementMetrics.objects.filter(corpus=self.corpus).exists()
        )
        self.assertTrue(result["created"])

    def test_task_updates_existing_metrics(self):
        """Test that task updates an existing metrics record."""
        # Create initial metrics with zero values
        metrics = CorpusEngagementMetrics.objects.create(corpus=self.corpus)
        self.assertEqual(metrics.total_messages, 0)

        # Run the task
        result = update_corpus_engagement_metrics(self.corpus.id)

        # Verify metrics were updated
        metrics.refresh_from_db()
        self.assertFalse(result["created"])
        self.assertEqual(metrics.total_messages, 3)
        self.assertEqual(metrics.total_threads, 2)

    def test_task_calculates_metrics_correctly(self):
        """Test that task calculates all metrics accurately."""
        result = update_corpus_engagement_metrics(self.corpus.id)

        # Verify returned result
        self.assertEqual(result["corpus_id"], self.corpus.id)
        self.assertEqual(result["corpus_title"], self.corpus.title)
        self.assertEqual(result["metrics"]["total_threads"], 2)
        self.assertEqual(result["metrics"]["active_threads"], 2)
        self.assertEqual(result["metrics"]["total_messages"], 3)
        self.assertEqual(result["metrics"]["messages_last_7_days"], 3)
        self.assertEqual(result["metrics"]["messages_last_30_days"], 3)
        self.assertEqual(result["metrics"]["unique_contributors"], 2)
        self.assertEqual(result["metrics"]["active_contributors_30_days"], 2)
        self.assertEqual(result["metrics"]["total_upvotes"], 2)
        self.assertEqual(result["metrics"]["avg_messages_per_thread"], 1.5)

        # Verify database record
        metrics = CorpusEngagementMetrics.objects.get(corpus=self.corpus)
        self.assertEqual(metrics.total_threads, 2)
        self.assertEqual(metrics.active_threads, 2)
        self.assertEqual(metrics.total_messages, 3)
        self.assertEqual(metrics.messages_last_7_days, 3)
        self.assertEqual(metrics.messages_last_30_days, 3)
        self.assertEqual(metrics.unique_contributors, 2)
        self.assertEqual(metrics.active_contributors_30_days, 2)
        self.assertEqual(metrics.total_upvotes, 2)
        self.assertEqual(metrics.avg_messages_per_thread, 1.5)

    def test_task_handles_locked_threads(self):
        """Test that locked threads are counted separately."""
        # Lock thread1
        self.thread1.is_locked = True
        self.thread1.save()

        result = update_corpus_engagement_metrics(self.corpus.id)

        # Total threads should be 2, but only 1 is active
        self.assertEqual(result["metrics"]["total_threads"], 2)
        self.assertEqual(result["metrics"]["active_threads"], 1)

    def test_task_handles_soft_deleted_threads(self):
        """Test that soft-deleted threads are excluded."""
        # Soft delete thread1
        self.thread1.deleted_at = timezone.now()
        self.thread1.save()

        result = update_corpus_engagement_metrics(self.corpus.id)

        # Should only count 1 thread and 1 message (from thread2)
        self.assertEqual(result["metrics"]["total_threads"], 1)
        self.assertEqual(result["metrics"]["total_messages"], 1)

    def test_task_handles_soft_deleted_messages(self):
        """Test that soft-deleted messages are excluded."""
        # Soft delete msg1
        self.msg1.deleted_at = timezone.now()
        self.msg1.save()

        result = update_corpus_engagement_metrics(self.corpus.id)

        # Should only count 2 messages
        self.assertEqual(result["metrics"]["total_messages"], 2)

    def test_task_handles_old_messages(self):
        """Test that time-based metrics filter correctly."""
        # Create an old message (35 days ago)
        old_time = timezone.now() - timedelta(days=35)
        old_msg = ChatMessage.objects.create(
            conversation=self.thread1,
            msg_type="HUMAN",
            content="Old message",
            creator=self.user1,
        )
        # Manually set created_at to bypass auto_now_add
        ChatMessage.objects.filter(pk=old_msg.pk).update(created_at=old_time)

        result = update_corpus_engagement_metrics(self.corpus.id)

        # Total should include old message
        self.assertEqual(result["metrics"]["total_messages"], 4)
        # But 7-day and 30-day counts should not
        self.assertEqual(result["metrics"]["messages_last_7_days"], 3)
        self.assertEqual(result["metrics"]["messages_last_30_days"], 3)

    def test_task_handles_corpus_with_no_threads(self):
        """Test task with a corpus that has no threads."""
        empty_corpus = Corpus.objects.create(
            title="Empty Corpus",
            description="No threads",
            creator=self.user1,
        )

        result = update_corpus_engagement_metrics(empty_corpus.id)

        # All counts should be zero
        self.assertEqual(result["metrics"]["total_threads"], 0)
        self.assertEqual(result["metrics"]["active_threads"], 0)
        self.assertEqual(result["metrics"]["total_messages"], 0)
        self.assertEqual(result["metrics"]["unique_contributors"], 0)
        self.assertEqual(result["metrics"]["total_upvotes"], 0)
        self.assertEqual(result["metrics"]["avg_messages_per_thread"], 0.0)

    def test_task_handles_invalid_corpus_id(self):
        """Test task with an invalid corpus ID."""
        with self.assertRaises(Corpus.DoesNotExist):
            update_corpus_engagement_metrics(99999)

    def test_task_is_idempotent(self):
        """Test that running task multiple times produces same result."""
        result1 = update_corpus_engagement_metrics(self.corpus.id)
        result2 = update_corpus_engagement_metrics(self.corpus.id)

        # Results should be identical (except 'created' flag)
        self.assertEqual(
            result1["metrics"],
            result2["metrics"],
        )
        self.assertTrue(result1["created"])
        self.assertFalse(result2["created"])


class TestUpdateAllCorpusEngagementMetricsTask(TestCase):
    """Test the update_all_corpus_engagement_metrics batch task."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="batch_user",
            password="testpass123",
            email="batch@test.com",
        )

        # Create multiple corpuses
        cls.corpus1 = Corpus.objects.create(
            title="Corpus 1",
            creator=cls.user,
        )
        cls.corpus2 = Corpus.objects.create(
            title="Corpus 2",
            creator=cls.user,
        )
        cls.corpus3 = Corpus.objects.create(
            title="Corpus 3",
            creator=cls.user,
        )

    def test_batch_task_queues_all_corpuses(self):
        """Test that batch task queues updates for all corpuses."""
        result = update_all_corpus_engagement_metrics()

        # Should queue 3 updates
        self.assertEqual(result["queued_updates"], 3)
        self.assertEqual(len(result["corpus_ids"]), 3)
        self.assertIn(self.corpus1.id, result["corpus_ids"])
        self.assertIn(self.corpus2.id, result["corpus_ids"])
        self.assertIn(self.corpus3.id, result["corpus_ids"])

    def test_batch_task_with_no_corpuses(self):
        """Test batch task when no corpuses exist."""
        # Delete all corpuses
        Corpus.objects.all().delete()

        result = update_all_corpus_engagement_metrics()

        self.assertEqual(result["queued_updates"], 0)
        self.assertEqual(result["corpus_ids"], [])


class TestMetricsTaskPerformance(TestCase):
    """Test performance characteristics of metrics tasks."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with moderate volume."""
        cls.user1 = User.objects.create_user(
            username="perf_user1",
            password="testpass123",
            email="perf1@test.com",
        )
        cls.user2 = User.objects.create_user(
            username="perf_user2",
            password="testpass123",
            email="perf2@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Performance Test Corpus",
            creator=cls.user1,
        )

        # Create 10 threads with 5 messages each
        for i in range(10):
            thread = Conversation.objects.create(
                title=f"Thread {i}",
                conversation_type=ConversationTypeChoices.THREAD,
                creator=cls.user1,
                chat_with_corpus=cls.corpus,
            )

            for j in range(5):
                ChatMessage.objects.create(
                    conversation=thread,
                    msg_type="HUMAN",
                    content=f"Message {j} in thread {i}",
                    creator=cls.user1 if j % 2 == 0 else cls.user2,
                )

    def test_task_completes_in_reasonable_time(self):
        """Test that task completes quickly even with moderate data."""
        import time

        start = time.time()
        result = update_corpus_engagement_metrics(self.corpus.id)
        elapsed = time.time() - start

        # Task should complete in under 1 second
        # (target is <200ms per issue spec, but allowing margin for test env)
        self.assertLess(elapsed, 1.0)

        # Verify correct results
        self.assertEqual(result["metrics"]["total_threads"], 10)
        self.assertEqual(result["metrics"]["total_messages"], 50)
        self.assertEqual(result["metrics"]["avg_messages_per_thread"], 5.0)
