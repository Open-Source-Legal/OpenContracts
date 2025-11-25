"""
Tests for Engagement Metrics GraphQL Queries.

This module tests Epic #565: Corpus Engagement Metrics & Analytics
Specifically, Issue #568: Create GraphQL queries for engagement metrics and leaderboards

Tests cover:
1. CorpusEngagementMetricsType GraphQL type
2. corpus.engagementMetrics field resolution
3. user.reputationGlobal field resolution
4. user.reputationForCorpus field resolution
5. corpusLeaderboard query
6. globalLeaderboard query
7. Permission checks
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    UserReputation,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.tasks.corpus_tasks import update_corpus_engagement_metrics

User = get_user_model()


class TestCorpusEngagementMetricsGraphQL(TestCase):
    """Test GraphQL queries for corpus engagement metrics."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="gql_user",
            password="testpass123",
            email="gql@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="GraphQL Test Corpus",
            description="Testing engagement metrics GraphQL",
            creator=cls.user,
            is_public=True,
        )

        # Create thread and messages
        cls.thread = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=cls.user,
            chat_with_corpus=cls.corpus,
        )

        cls.msg = ChatMessage.objects.create(
            conversation=cls.thread,
            msg_type="HUMAN",
            content="Test message",
            creator=cls.user,
        )

        # Calculate metrics
        update_corpus_engagement_metrics(cls.corpus.id)

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user
        self.client = Client(schema, context_value=self.request)

    def test_query_corpus_engagement_metrics(self):
        """Test querying engagement metrics for a corpus."""
        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetCorpusMetrics($corpusId: ID!) {
                corpus(id: $corpusId) {
                    id
                    title
                    engagementMetrics {
                        totalThreads
                        activeThreads
                        totalMessages
                        messagesLast7Days
                        messagesLast30Days
                        uniqueContributors
                        activeContributors30Days
                        totalUpvotes
                        avgMessagesPerThread
                        lastUpdated
                    }
                }
            }
        """

        result = self.client.execute(query, variables={"corpusId": corpus_gid})

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Verify metrics data
        metrics = result["data"]["corpus"]["engagementMetrics"]
        self.assertEqual(metrics["totalThreads"], 1)
        self.assertEqual(metrics["activeThreads"], 1)
        self.assertEqual(metrics["totalMessages"], 1)
        self.assertEqual(metrics["uniqueContributors"], 1)
        self.assertIsNotNone(metrics["lastUpdated"])

    def test_query_corpus_without_metrics(self):
        """Test querying a corpus that doesn't have metrics calculated yet."""
        new_corpus = Corpus.objects.create(
            title="Corpus Without Metrics",
            creator=self.user,
            is_public=True,
        )
        corpus_gid = to_global_id("CorpusType", new_corpus.id)

        query = """
            query GetCorpusMetrics($corpusId: ID!) {
                corpus(id: $corpusId) {
                    id
                    engagementMetrics {
                        totalThreads
                    }
                }
            }
        """

        result = self.client.execute(query, variables={"corpusId": corpus_gid})

        # Should return null for engagement metrics if not calculated
        self.assertIsNone(result["data"]["corpus"]["engagementMetrics"])


class TestUserReputationGraphQL(TestCase):
    """Test GraphQL queries for user reputation."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user1 = User.objects.create_user(
            username="rep_user1",
            password="testpass123",
            email="rep1@test.com",
        )
        cls.user2 = User.objects.create_user(
            username="rep_user2",
            password="testpass123",
            email="rep2@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Reputation Test Corpus",
            creator=cls.user1,
            is_public=True,
        )

        # Create reputation records (creator is the user themselves for system-generated records)
        UserReputation.objects.create(
            user=cls.user1,
            corpus=None,  # Global reputation
            reputation_score=100,
            creator=cls.user1,
        )
        UserReputation.objects.create(
            user=cls.user1,
            corpus=cls.corpus,
            reputation_score=50,
            creator=cls.user1,
        )
        UserReputation.objects.create(
            user=cls.user2,
            corpus=cls.corpus,
            reputation_score=75,
            creator=cls.user2,
        )

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user1
        self.client = Client(schema, context_value=self.request)

    def test_query_user_global_reputation(self):
        """Test querying user's global reputation."""
        query = """
            query {
                me {
                    id
                    username
                    reputationGlobal
                }
            }
        """

        result = self.client.execute(query)

        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["me"]["reputationGlobal"], 100)

    def test_query_user_corpus_reputation(self):
        """Test querying user's reputation for a specific corpus."""
        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetUserCorpusReputation($corpusId: ID!) {
                me {
                    id
                    username
                    reputationForCorpus(corpusId: $corpusId)
                }
            }
        """

        result = self.client.execute(query, variables={"corpusId": corpus_gid})

        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["me"]["reputationForCorpus"], 50)

    def test_query_user_without_reputation(self):
        """Test querying user who has no reputation records."""
        user_no_rep = User.objects.create_user(
            username="no_rep_user",
            password="testpass123",
            email="norep@test.com",
        )

        request = self.factory.get("/graphql")
        request.user = user_no_rep
        client = Client(schema, context_value=request)

        query = """
            query {
                me {
                    reputationGlobal
                }
            }
        """

        result = client.execute(query)

        # Should return 0 if no reputation record exists
        self.assertEqual(result["data"]["me"]["reputationGlobal"], 0)


class TestLeaderboardGraphQL(TestCase):
    """Test GraphQL leaderboard queries."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with multiple users and reputation scores."""
        # Create users with different reputation scores
        cls.user1 = User.objects.create_user(
            username="leader1", password="testpass123", email="leader1@test.com"
        )
        cls.user2 = User.objects.create_user(
            username="leader2", password="testpass123", email="leader2@test.com"
        )
        cls.user3 = User.objects.create_user(
            username="leader3", password="testpass123", email="leader3@test.com"
        )

        cls.corpus = Corpus.objects.create(
            title="Leaderboard Corpus",
            creator=cls.user1,
            is_public=True,
        )

        # Create global reputations
        UserReputation.objects.create(
            user=cls.user1, corpus=None, reputation_score=100, creator=cls.user1
        )
        UserReputation.objects.create(
            user=cls.user2, corpus=None, reputation_score=150, creator=cls.user2
        )
        UserReputation.objects.create(
            user=cls.user3, corpus=None, reputation_score=75, creator=cls.user3
        )

        # Create corpus-specific reputations
        UserReputation.objects.create(
            user=cls.user1, corpus=cls.corpus, reputation_score=60, creator=cls.user1
        )
        UserReputation.objects.create(
            user=cls.user2, corpus=cls.corpus, reputation_score=40, creator=cls.user2
        )
        UserReputation.objects.create(
            user=cls.user3, corpus=cls.corpus, reputation_score=80, creator=cls.user3
        )

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user1
        self.client = Client(schema, context_value=self.request)

    def test_query_global_leaderboard(self):
        """Test querying global leaderboard."""
        query = """
            query {
                globalLeaderboard(limit: 10) {
                    id
                    username
                    reputationGlobal
                }
            }
        """

        result = self.client.execute(query)

        self.assertIsNone(result.get("errors"))

        # Check that users are returned in order of reputation
        leaderboard = result["data"]["globalLeaderboard"]
        self.assertEqual(len(leaderboard), 3)

        # Should be ordered by reputation score descending
        self.assertEqual(leaderboard[0]["username"], "leader2")  # 150
        self.assertEqual(leaderboard[1]["username"], "leader1")  # 100
        self.assertEqual(leaderboard[2]["username"], "leader3")  # 75

    def test_query_corpus_leaderboard(self):
        """Test querying corpus-specific leaderboard."""
        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetCorpusLeaderboard($corpusId: ID!) {
                corpusLeaderboard(corpusId: $corpusId, limit: 10) {
                    id
                    username
                    reputationForCorpus(corpusId: $corpusId)
                }
            }
        """

        result = self.client.execute(query, variables={"corpusId": corpus_gid})

        self.assertIsNone(result.get("errors"))

        # Check that users are returned in order of corpus reputation
        leaderboard = result["data"]["corpusLeaderboard"]
        self.assertEqual(len(leaderboard), 3)

        # Should be ordered by corpus reputation score descending
        self.assertEqual(leaderboard[0]["username"], "leader3")  # 80
        self.assertEqual(leaderboard[1]["username"], "leader1")  # 60
        self.assertEqual(leaderboard[2]["username"], "leader2")  # 40

    def test_leaderboard_with_limit(self):
        """Test leaderboard query with limit parameter."""
        query = """
            query {
                globalLeaderboard(limit: 2) {
                    username
                }
            }
        """

        result = self.client.execute(query)

        leaderboard = result["data"]["globalLeaderboard"]
        self.assertEqual(len(leaderboard), 2)

    def test_corpus_leaderboard_permission_check(self):
        """Test that corpus leaderboard respects permissions."""
        # Create a private corpus
        private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=self.user2,
            is_public=False,
        )
        corpus_gid = to_global_id("CorpusType", private_corpus.id)

        query = """
            query GetCorpusLeaderboard($corpusId: ID!) {
                corpusLeaderboard(corpusId: $corpusId) {
                    username
                }
            }
        """

        result = self.client.execute(query, variables={"corpusId": corpus_gid})

        # Should return an error since user1 doesn't have access
        self.assertIsNotNone(result.get("errors"))
        self.assertIn("not found or access denied", str(result["errors"][0]))
