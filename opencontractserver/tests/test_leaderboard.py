"""
Tests for leaderboard and community stats queries.

Issue: #613 - Create leaderboard and community stats dashboard
Epic: #572 - Social Features Epic
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    UserReputation,
)
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class LeaderboardQueryTestCase(TestCase):
    """Test leaderboard GraphQL queries."""

    def setUp(self):
        """Set up test fixtures."""
        # Create users
        self.user1 = User.objects.create_user(
            username="testuser1", password="password", is_profile_public=True
        )
        self.user2 = User.objects.create_user(
            username="testuser2", password="password", is_profile_public=True
        )
        self.user3 = User.objects.create_user(
            username="testuser3", password="password", is_profile_public=True
        )
        self.private_user = User.objects.create_user(
            username="privateuser", password="password", is_profile_public=False
        )

        # Create badges
        self.badge1 = Badge.objects.create(
            creator=self.user1,
            name="First Post",
            description="Made your first post",
            icon="Trophy",
            badge_type="GLOBAL",
            color="#FFD700",
            is_auto_awarded=True,
            criteria_config={"type": "first_post"},
        )
        self.badge2 = Badge.objects.create(
            creator=self.user1,
            name="Top Contributor",
            description="100 messages posted",
            icon="Star",
            badge_type="GLOBAL",
            color="#C0C0C0",
            is_auto_awarded=True,
            criteria_config={"type": "message_count", "value": 100},
        )

        # Award badges to users
        UserBadge.objects.create(user=self.user1, badge=self.badge1, awarded_by=None)
        UserBadge.objects.create(user=self.user1, badge=self.badge2, awarded_by=None)
        UserBadge.objects.create(user=self.user2, badge=self.badge1, awarded_by=None)

        # Create corpus for testing
        self.corpus = Corpus.objects.create(
            title="Test Corpus", description="Test description", creator=self.user1
        )
        self.corpus.is_public = True
        self.corpus.save()

        # Create conversations (skip signals to prevent auto-badge awards)
        self.conversation1 = Conversation(
            creator=self.user1,
            conversation_type="thread",
            title="Test Thread 1",
            chat_with_corpus=self.corpus,
            is_public=True,
        )
        self.conversation1._skip_signals = True
        self.conversation1.save()

        self.conversation2 = Conversation(
            creator=self.user2,
            conversation_type="thread",
            title="Test Thread 2",
            chat_with_corpus=self.corpus,
            is_public=True,
        )
        self.conversation2._skip_signals = True
        self.conversation2.save()

        # Create messages (skip signals to avoid auto-badge awards during test setup)
        for i in range(5):
            msg = ChatMessage(
                creator=self.user1,
                conversation=self.conversation1,
                msg_type="HUMAN",
                content=f"Message {i} from user1",
            )
            msg._skip_signals = True
            msg.save()
        for i in range(3):
            msg = ChatMessage(
                creator=self.user2,
                conversation=self.conversation2,
                msg_type="HUMAN",
                content=f"Message {i} from user2",
            )
            msg._skip_signals = True
            msg.save()

        # NOTE: We skip creating actual documents and annotations for these tests
        # since the leaderboard queries work without them. The annotation metric
        # tests will simply return zero annotations, which is fine for testing
        # the query logic.

        # Create reputation records
        UserReputation.objects.create(
            creator=self.user1, user=self.user1, reputation_score=150, corpus=None
        )
        UserReputation.objects.create(
            creator=self.user2, user=self.user2, reputation_score=100, corpus=None
        )
        UserReputation.objects.create(
            creator=self.user3, user=self.user3, reputation_score=75, corpus=None
        )

        # GraphQL client
        self.client = Client(schema)

    def test_leaderboard_badges_metric(self):
        """Test leaderboard query with badges metric."""
        query = """
            query {
                leaderboard(metric: BADGES, scope: ALL_TIME, limit: 10) {
                    metric
                    scope
                    totalUsers
                    entries {
                        rank
                        score
                        user {
                            username
                        }
                    }
                }
            }
        """

        # Execute query with authentication
        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        leaderboard = result["data"]["leaderboard"]

        self.assertEqual(leaderboard["metric"], "BADGES")
        self.assertEqual(leaderboard["scope"], "ALL_TIME")
        self.assertGreaterEqual(leaderboard["totalUsers"], 2)

        # Check entries are sorted by badge count
        entries = leaderboard["entries"]
        self.assertEqual(entries[0]["user"]["username"], "testuser1")
        self.assertEqual(entries[0]["score"], 2)  # user1 has 2 badges
        self.assertEqual(entries[0]["rank"], 1)

        self.assertEqual(entries[1]["user"]["username"], "testuser2")
        self.assertEqual(entries[1]["score"], 1)  # user2 has 1 badge
        self.assertEqual(entries[1]["rank"], 2)

    def test_leaderboard_messages_metric(self):
        """Test leaderboard query with messages metric."""
        query = """
            query {
                leaderboard(metric: MESSAGES, scope: ALL_TIME, limit: 10) {
                    entries {
                        rank
                        score
                        user {
                            username
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        entries = result["data"]["leaderboard"]["entries"]

        # user1 has 5 messages, user2 has 3 messages
        self.assertEqual(entries[0]["user"]["username"], "testuser1")
        self.assertEqual(entries[0]["score"], 5)

        self.assertEqual(entries[1]["user"]["username"], "testuser2")
        self.assertEqual(entries[1]["score"], 3)

    def test_leaderboard_threads_metric(self):
        """Test leaderboard query with threads metric."""
        query = """
            query {
                leaderboard(metric: THREADS, scope: ALL_TIME, limit: 10) {
                    entries {
                        rank
                        score
                        user {
                            username
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        entries = result["data"]["leaderboard"]["entries"]

        # Both users created 1 thread each
        self.assertGreaterEqual(len(entries), 2)
        usernames = [e["user"]["username"] for e in entries]
        self.assertIn("testuser1", usernames)
        self.assertIn("testuser2", usernames)

    def test_leaderboard_annotations_metric(self):
        """Test leaderboard query with annotations metric."""
        query = """
            query {
                leaderboard(metric: ANNOTATIONS, scope: ALL_TIME, limit: 10) {
                    metric
                    entries {
                        rank
                        score
                        user {
                            username
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        leaderboard = result["data"]["leaderboard"]

        # Query should succeed even with no annotations
        self.assertEqual(leaderboard["metric"], "ANNOTATIONS")
        # Entries will be empty since we didn't create annotations
        self.assertIsInstance(leaderboard["entries"], list)

    def test_leaderboard_reputation_metric(self):
        """Test leaderboard query with reputation metric."""
        query = """
            query {
                leaderboard(metric: REPUTATION, scope: ALL_TIME, limit: 10) {
                    entries {
                        rank
                        score
                        user {
                            username
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        entries = result["data"]["leaderboard"]["entries"]

        # Sorted by reputation
        self.assertEqual(entries[0]["user"]["username"], "testuser1")
        self.assertEqual(entries[0]["score"], 150)

        self.assertEqual(entries[1]["user"]["username"], "testuser2")
        self.assertEqual(entries[1]["score"], 100)

        self.assertEqual(entries[2]["user"]["username"], "testuser3")
        self.assertEqual(entries[2]["score"], 75)

    def test_leaderboard_respects_user_privacy(self):
        """Test that leaderboard excludes private user profiles."""
        # Award badge to private user
        UserBadge.objects.create(
            user=self.private_user, badge=self.badge1, awarded_by=None
        )

        query = """
            query {
                leaderboard(metric: BADGES, scope: ALL_TIME, limit: 10) {
                    entries {
                        user {
                            username
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        entries = result["data"]["leaderboard"]["entries"]

        # Private user should not appear in leaderboard
        usernames = [e["user"]["username"] for e in entries]
        self.assertNotIn("privateuser", usernames)

    def test_leaderboard_current_user_rank(self):
        """Test that current user's rank is returned."""
        query = """
            query {
                leaderboard(metric: BADGES, scope: ALL_TIME, limit: 10) {
                    currentUserRank
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        leaderboard = result["data"]["leaderboard"]

        # user1 should be rank 1 (has 2 badges)
        self.assertEqual(leaderboard["currentUserRank"], 1)

    def test_community_stats_query(self):
        """Test community stats query."""
        query = """
            query {
                communityStats {
                    totalUsers
                    totalMessages
                    totalThreads
                    totalAnnotations
                    totalBadgesAwarded
                    badgeDistribution {
                        awardCount
                        uniqueRecipients
                        badge {
                            name
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        stats = result["data"]["communityStats"]

        # Check total counts
        self.assertGreaterEqual(stats["totalUsers"], 3)
        self.assertEqual(stats["totalMessages"], 8)  # 5 + 3 messages
        self.assertEqual(stats["totalThreads"], 2)  # 2 threads
        self.assertEqual(stats["totalAnnotations"], 0)  # No annotations in test
        self.assertEqual(stats["totalBadgesAwarded"], 3)  # 3 badge awards

        # Check badge distribution
        badge_dist = stats["badgeDistribution"]
        self.assertGreaterEqual(len(badge_dist), 1)

        # Find "First Post" badge in distribution
        first_post = next(
            (b for b in badge_dist if b["badge"]["name"] == "First Post"), None
        )
        self.assertIsNotNone(first_post)
        self.assertEqual(first_post["awardCount"], 2)  # Awarded twice
        self.assertEqual(first_post["uniqueRecipients"], 2)  # To 2 users

    def test_leaderboard_with_limit(self):
        """Test leaderboard respects limit parameter."""
        query = """
            query {
                leaderboard(metric: BADGES, scope: ALL_TIME, limit: 1) {
                    totalUsers
                    entries {
                        rank
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Context", (), {"user": self.user1})
        )

        self.assertIsNone(result.get("errors"))
        leaderboard = result["data"]["leaderboard"]

        # Should only return 1 entry
        self.assertEqual(len(leaderboard["entries"]), 1)
        self.assertEqual(leaderboard["entries"][0]["rank"], 1)

    def test_leaderboard_corpus_scoped(self):
        """Test corpus-scoped leaderboard."""
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = """
            query($corpusId: ID!) {
                leaderboard(metric: MESSAGES, scope: ALL_TIME, corpusId: $corpusId) {
                    corpusId
                    entries {
                        user {
                            username
                        }
                        score
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"corpusId": corpus_global_id},
            context_value=type("Context", (), {"user": self.user1}),
        )

        self.assertIsNone(result.get("errors"))
        leaderboard = result["data"]["leaderboard"]

        self.assertEqual(leaderboard["corpusId"], corpus_global_id)
        # Should only show users who contributed to this corpus
        self.assertGreaterEqual(len(leaderboard["entries"]), 2)

    def test_leaderboard_unauthorized_access_to_corpus(self):
        """Test that leaderboard returns error for unauthorized corpus access."""
        # Create a private corpus
        private_corpus = Corpus.objects.create(
            title="Private Corpus", description="Private", creator=self.user2
        )
        private_corpus.is_public = False
        private_corpus.save()

        corpus_global_id = to_global_id("CorpusType", private_corpus.id)

        query = """
            query($corpusId: ID!) {
                leaderboard(metric: MESSAGES, scope: ALL_TIME, corpusId: $corpusId) {
                    entries {
                        rank
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"corpusId": corpus_global_id},
            context_value=type("Context", (), {"user": self.user1}),
        )

        # Should get an error for unauthorized access
        self.assertIsNotNone(result.get("errors"))
        self.assertIn("Corpus not found or access denied", str(result["errors"]))
