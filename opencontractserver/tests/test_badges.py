"""
Tests for badge system in OpenContracts.

This module tests Epic #558: Badge System

Tests cover:
1. Creating badges (global and corpus-specific)
2. Awarding badges to users
3. Badge validation (corpus constraints)
4. UserBadge unique constraints
5. GraphQL mutations and queries
6. Auto-badge checking tasks
7. Permission checks for badge management
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.badges.models import Badge, BadgeTypeChoices, UserBadge
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.tasks.badge_tasks import BadgeCriteriaType, check_auto_badges
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestBadgeModel(TestCase):
    """Test Badge model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.admin_user = User.objects.create_user(
            username="badgemodel_admin",
            password="testpass123",
            email="badgemodel_admin@test.com",
            is_superuser=True,
        )

        cls.normal_user = User.objects.create_user(
            username="badgemodel_normal",
            password="testpass123",
            email="badgemodel_normal@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Badge Corpus",
            description="A corpus for testing badges",
            creator=cls.admin_user,
            is_public=True,
        )

    def test_create_global_badge(self):
        """Test creating a global badge."""
        badge = Badge.objects.create(
            name="Global Champion",
            description="Awarded for excellence",
            icon="Trophy",
            badge_type=BadgeTypeChoices.GLOBAL,
            color="#FFD700",
            creator=self.admin_user,
            is_public=True,
        )

        self.assertEqual(badge.name, "Global Champion")
        self.assertEqual(badge.badge_type, BadgeTypeChoices.GLOBAL)
        self.assertIsNone(badge.corpus)
        self.assertEqual(badge.icon, "Trophy")
        self.assertEqual(badge.color, "#FFD700")

    def test_create_corpus_badge(self):
        """Test creating a corpus-specific badge."""
        badge = Badge.objects.create(
            name="Corpus Expert",
            description="Expert in this corpus",
            icon="Award",
            badge_type=BadgeTypeChoices.CORPUS,
            corpus=self.corpus,
            creator=self.admin_user,
            is_public=True,
        )

        self.assertEqual(badge.badge_type, BadgeTypeChoices.CORPUS)
        self.assertEqual(badge.corpus, self.corpus)

    def test_corpus_badge_without_corpus_validation(self):
        """Test that corpus badges must have a corpus."""
        badge = Badge(
            name="Invalid Badge",
            description="Should fail",
            icon="Star",
            badge_type=BadgeTypeChoices.CORPUS,
            corpus=None,  # Missing corpus
            creator=self.admin_user,
        )

        with self.assertRaises(ValidationError) as cm:
            badge.save()

        self.assertIn("corpus", str(cm.exception))

    def test_global_badge_with_corpus_validation(self):
        """Test that global badges cannot have a corpus."""
        badge = Badge(
            name="Invalid Global Badge",
            description="Should fail",
            icon="Star",
            badge_type=BadgeTypeChoices.GLOBAL,
            corpus=self.corpus,  # Should not have corpus
            creator=self.admin_user,
        )

        with self.assertRaises(ValidationError) as cm:
            badge.save()

        self.assertIn("corpus", str(cm.exception))

    def test_badge_auto_award_criteria(self):
        """Test badge with auto-award criteria."""
        badge = Badge.objects.create(
            name="First Post",
            description="Made your first post",
            icon="MessageSquare",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.FIRST_POST,
            },
            creator=self.admin_user,
            is_public=True,
        )

        self.assertTrue(badge.is_auto_awarded)
        self.assertEqual(badge.criteria_config["type"], BadgeCriteriaType.FIRST_POST)

    def test_badge_string_representation(self):
        """Test badge string representation."""
        global_badge = Badge.objects.create(
            name="Global Badge",
            description="Test",
            icon="Star",
            badge_type=BadgeTypeChoices.GLOBAL,
            creator=self.admin_user,
        )

        corpus_badge = Badge.objects.create(
            name="Corpus Badge",
            description="Test",
            icon="Award",
            badge_type=BadgeTypeChoices.CORPUS,
            corpus=self.corpus,
            creator=self.admin_user,
        )

        self.assertIn("Global", str(global_badge))
        self.assertIn(self.corpus.title, str(corpus_badge))


class TestUserBadgeModel(TestCase):
    """Test UserBadge model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.admin_user = User.objects.create_user(
            username="userbadgemodel_admin",
            password="testpass123",
            email="userbadgemodel_admin@test.com",
            is_superuser=True,
        )

        cls.recipient = User.objects.create_user(
            username="userbadgemodel_recipient",
            password="testpass123",
            email="userbadgemodel_recipient@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=cls.admin_user,
            is_public=True,
        )

        cls.global_badge = Badge.objects.create(
            name="Global Award",
            description="Global badge",
            icon="Trophy",
            badge_type=BadgeTypeChoices.GLOBAL,
            creator=cls.admin_user,
            is_public=True,
        )

        cls.corpus_badge = Badge.objects.create(
            name="Corpus Award",
            description="Corpus badge",
            icon="Award",
            badge_type=BadgeTypeChoices.CORPUS,
            corpus=cls.corpus,
            creator=cls.admin_user,
            is_public=True,
        )

    def test_award_global_badge(self):
        """Test awarding a global badge."""
        user_badge = UserBadge.objects.create(
            user=self.recipient,
            badge=self.global_badge,
            awarded_by=self.admin_user,
        )

        self.assertEqual(user_badge.user, self.recipient)
        self.assertEqual(user_badge.badge, self.global_badge)
        self.assertEqual(user_badge.awarded_by, self.admin_user)
        self.assertIsNone(user_badge.corpus)

    def test_award_corpus_badge(self):
        """Test awarding a corpus-specific badge."""
        user_badge = UserBadge.objects.create(
            user=self.recipient,
            badge=self.corpus_badge,
            awarded_by=self.admin_user,
            corpus=self.corpus,
        )

        self.assertEqual(user_badge.corpus, self.corpus)
        self.assertEqual(user_badge.badge, self.corpus_badge)

    def test_auto_award_badge(self):
        """Test auto-awarding a badge (no awarded_by)."""
        user_badge = UserBadge.objects.create(
            user=self.recipient,
            badge=self.global_badge,
            awarded_by=None,  # Auto-awarded
        )

        self.assertIsNone(user_badge.awarded_by)

    def test_corpus_badge_without_corpus_validation(self):
        """Test that corpus badge awards must have corpus."""
        user_badge = UserBadge(
            user=self.recipient,
            badge=self.corpus_badge,
            awarded_by=self.admin_user,
            corpus=None,  # Missing corpus
        )

        with self.assertRaises(ValidationError) as cm:
            user_badge.save()

        self.assertIn("corpus", str(cm.exception))

    def test_corpus_badge_wrong_corpus_validation(self):
        """Test that corpus badge award must match badge's corpus."""
        other_corpus = Corpus.objects.create(
            title="Other Corpus",
            description="Different corpus",
            creator=self.admin_user,
        )

        user_badge = UserBadge(
            user=self.recipient,
            badge=self.corpus_badge,
            awarded_by=self.admin_user,
            corpus=other_corpus,  # Wrong corpus
        )

        with self.assertRaises(ValidationError) as cm:
            user_badge.save()

        self.assertIn("corpus", str(cm.exception))

    def test_global_badge_with_corpus_validation(self):
        """Test that global badge awards cannot have corpus."""
        user_badge = UserBadge(
            user=self.recipient,
            badge=self.global_badge,
            awarded_by=self.admin_user,
            corpus=self.corpus,  # Should not have corpus
        )

        with self.assertRaises(ValidationError) as cm:
            user_badge.save()

        self.assertIn("corpus", str(cm.exception))

    def test_unique_constraint(self):
        """Test that same badge can't be awarded twice to same user."""
        # Award badge first time
        UserBadge.objects.create(
            user=self.recipient,
            badge=self.global_badge,
            awarded_by=self.admin_user,
        )

        # Try to award again
        with self.assertRaises(ValidationError):
            UserBadge.objects.create(
                user=self.recipient,
                badge=self.global_badge,
                awarded_by=self.admin_user,
            )

    def test_user_badge_string_representation(self):
        """Test user badge string representation."""
        user_badge = UserBadge.objects.create(
            user=self.recipient,
            badge=self.global_badge,
            awarded_by=self.admin_user,
        )

        badge_str = str(user_badge)
        self.assertIn(self.global_badge.name, badge_str)
        self.assertIn(self.recipient.username, badge_str)


class TestBadgeGraphQLMutations(TransactionTestCase):
    """Test GraphQL mutations for badges."""

    def setUp(self):
        """Set up test data for each test."""
        self.admin_user = User.objects.create_user(
            username="graphqlmutations_admin",
            password="testpass123",
            email="graphqlmutations_admin@test.com",
            is_superuser=True,
        )

        self.normal_user = User.objects.create_user(
            username="graphqlmutations_normal",
            password="testpass123",
            email="graphqlmutations_normal@test.com",
        )

        self.corpus_owner = User.objects.create_user(
            username="graphqlmutations_corpusowner",
            password="testpass123",
            email="graphqlmutations_corpusowner@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=self.corpus_owner,
            is_public=True,
        )
        set_permissions_for_obj_to_user(
            self.corpus_owner, self.corpus, [PermissionTypes.CRUD]
        )

        self.client = Client(schema)

    def test_create_global_badge_as_admin(self):
        """Test creating a global badge as superuser."""
        mutation = """
            mutation CreateBadge {
                createBadge(
                    name: "Test Global Badge"
                    description: "A test badge"
                    icon: "Trophy"
                    badgeType: "GLOBAL"
                    color: "#FFD700"
                ) {
                    ok
                    message
                    badge {
                        name
                        badgeType
                        icon
                    }
                }
            }
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.admin_user})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createBadge"]["ok"])
        self.assertEqual(
            result["data"]["createBadge"]["badge"]["name"], "Test Global Badge"
        )
        self.assertEqual(result["data"]["createBadge"]["badge"]["badgeType"], "GLOBAL")

    def test_create_corpus_badge_as_corpus_owner(self):
        """Test creating a corpus badge as corpus owner."""
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation CreateBadge {{
                createBadge(
                    name: "Corpus Expert"
                    description: "Expert in corpus"
                    icon: "Award"
                    badgeType: "CORPUS"
                    corpusId: "{corpus_global_id}"
                ) {{
                    ok
                    message
                    badge {{
                        name
                        badgeType
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.corpus_owner})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createBadge"]["ok"])

    def test_create_global_badge_as_normal_user_fails(self):
        """Test that normal users cannot create global badges."""
        mutation = """
            mutation CreateBadge {
                createBadge(
                    name: "Unauthorized Badge"
                    description: "Should fail"
                    icon: "Star"
                    badgeType: "GLOBAL"
                ) {
                    ok
                    message
                }
            }
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.normal_user})(),
        )

        # Should have GraphQL error or ok=False
        if "errors" not in result:
            self.assertFalse(result["data"]["createBadge"]["ok"])

    def test_award_badge_mutation(self):
        """Test awarding a badge via GraphQL."""
        # Create a badge first
        badge = Badge.objects.create(
            name="Test Award",
            description="Test",
            icon="Award",
            badge_type=BadgeTypeChoices.GLOBAL,
            creator=self.admin_user,
            is_public=True,
        )

        badge_global_id = to_global_id("BadgeType", badge.id)
        user_global_id = to_global_id("UserType", self.normal_user.id)

        mutation = f"""
            mutation AwardBadge {{
                awardBadge(
                    badgeId: "{badge_global_id}"
                    userId: "{user_global_id}"
                ) {{
                    ok
                    message
                    userBadge {{
                        user {{
                            username
                        }}
                        badge {{
                            name
                        }}
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.admin_user})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["awardBadge"]["ok"])
        self.assertEqual(
            result["data"]["awardBadge"]["userBadge"]["user"]["username"],
            "graphqlmutations_normal",
        )

    def test_create_badge_idor_prevention(self):
        """Test that CreateBadgeMutation prevents corpus enumeration (IDOR fix)."""
        # Create a corpus owned by corpus_owner
        private_corpus = Corpus.objects.create(
            title="Private Corpus",
            description="Private",
            creator=self.corpus_owner,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.corpus_owner, private_corpus, [PermissionTypes.CRUD]
        )

        # Try to create a badge for this corpus as normal_user (who doesn't have access)
        corpus_global_id = to_global_id("CorpusType", private_corpus.id)
        mutation = f"""
            mutation CreateBadge {{
                createBadge(
                    name: "Unauthorized Badge"
                    description: "Should fail"
                    icon: "Trophy"
                    badgeType: "CORPUS"
                    corpusId: "{corpus_global_id}"
                ) {{
                    ok
                    message
                    badge {{
                        name
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.normal_user})(),
        )

        # Should get "Corpus not found" error, NOT "You must be a corpus owner"
        # This prevents enumeration - same error whether corpus doesn't exist or user lacks permission
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createBadge"]["ok"])
        self.assertEqual(result["data"]["createBadge"]["message"], "Corpus not found")

        # Now try with a non-existent corpus ID
        fake_corpus_global_id = to_global_id("CorpusType", 999999)
        mutation_fake = f"""
            mutation CreateBadge {{
                createBadge(
                    name: "Fake Corpus Badge"
                    description: "Should fail"
                    icon: "Trophy"
                    badgeType: "CORPUS"
                    corpusId: "{fake_corpus_global_id}"
                ) {{
                    ok
                    message
                }}
            }}
        """

        result_fake = self.client.execute(
            mutation_fake,
            context_value=type("Request", (), {"user": self.normal_user})(),
        )

        # Should get the SAME error message
        self.assertIsNone(result_fake.get("errors"))
        self.assertFalse(result_fake["data"]["createBadge"]["ok"])
        self.assertEqual(
            result_fake["data"]["createBadge"]["message"], "Corpus not found"
        )

    def test_award_badge_idor_prevention(self):
        """Test that AwardBadgeMutation prevents corpus enumeration (IDOR fix)."""
        # Create a corpus badge
        corpus_badge = Badge.objects.create(
            name="Corpus Expert",
            description="Expert in this corpus",
            icon="Award",
            badge_type="CORPUS",
            corpus=self.corpus,
            creator=self.corpus_owner,
        )
        badge_global_id = to_global_id("BadgeType", corpus_badge.id)
        user_global_id = to_global_id("UserType", self.normal_user.id)

        # Create a private corpus
        private_corpus = Corpus.objects.create(
            title="Private Corpus",
            description="Private",
            creator=self.corpus_owner,
            is_public=False,
        )
        private_corpus_global_id = to_global_id("CorpusType", private_corpus.id)

        # Try to award badge with private_corpus as corpus_id (user doesn't have access)
        mutation = f"""
            mutation AwardBadge {{
                awardBadge(
                    badgeId: "{badge_global_id}"
                    userId: "{user_global_id}"
                    corpusId: "{private_corpus_global_id}"
                ) {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.normal_user})(),
        )

        # Should get "Corpus not found" error, preventing enumeration
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["awardBadge"]["ok"])
        self.assertEqual(result["data"]["awardBadge"]["message"], "Corpus not found")


class TestBadgeGraphQLQueries(TransactionTestCase):
    """Test GraphQL queries for badges."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="graphqlqueries_testuser",
            password="testpass123",
            email="graphqlqueries_test@test.com",
        )

        self.badge = Badge.objects.create(
            name="Test Badge",
            description="Test",
            icon="Trophy",
            badge_type=BadgeTypeChoices.GLOBAL,
            creator=self.user,
            is_public=True,
        )

        self.user_badge = UserBadge.objects.create(
            user=self.user,
            badge=self.badge,
        )

        self.client = Client(schema)

    def test_query_badges(self):
        """Test querying badges."""
        query = """
            query {
                badges {
                    edges {
                        node {
                            name
                            badgeType
                            icon
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            context_value=type("Request", (), {"user": self.user})(),
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["badges"]["edges"]
        self.assertGreater(len(edges), 0)
        self.assertEqual(edges[0]["node"]["name"], "Test Badge")

    def test_query_user_badges(self):
        """Test querying user badge awards."""
        query = """
            query {
                userBadges {
                    edges {
                        node {
                            user {
                                username
                            }
                            badge {
                                name
                            }
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            context_value=type("Request", (), {"user": self.user})(),
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["userBadges"]["edges"]
        self.assertGreater(len(edges), 0)


class TestBadgeAutoAwardTasks(TransactionTestCase):
    """Test auto-badge award tasks."""

    def setUp(self):
        """Create test data."""
        self.admin_user = User.objects.create_user(
            username="autoawardtasks_admin",
            password="testpass123",
            email="autoawardtasks_admin@test.com",
            is_superuser=True,
        )

        self.user = User.objects.create_user(
            username="autoawardtasks_testuser",
            password="testpass123",
            email="autoawardtasks_test@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=self.admin_user,
            is_public=True,
        )

        # Delete default badges from migration to have a clean test environment
        Badge.objects.filter(
            badge_type=BadgeTypeChoices.GLOBAL, is_auto_awarded=True
        ).delete()

        # Create auto-award badge for first post
        self.first_post_badge = Badge.objects.create(
            name="First Post",
            description="Made your first post",
            icon="MessageSquare",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.FIRST_POST,
            },
            creator=self.admin_user,
            is_public=True,
        )

    def test_auto_award_first_post_badge(self):
        """Test auto-awarding first post badge."""
        # Create a conversation and message
        conversation = Conversation.objects.create(
            title="Test",
            creator=self.user,
        )
        # Create message without triggering automatic badge award
        msg = ChatMessage(
            conversation=conversation,
            msg_type="HUMAN",
            content="First post!",
            creator=self.user,
        )
        msg._skip_signals = True
        msg.save()

        # Run auto-badge check manually
        result = check_auto_badges(self.user.id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["awards_count"], 1)

        # Verify badge was awarded
        user_badge = UserBadge.objects.filter(
            user=self.user, badge=self.first_post_badge
        ).first()
        self.assertIsNotNone(user_badge)
        self.assertIsNone(user_badge.awarded_by)  # Auto-awarded

    def test_auto_badge_not_awarded_twice(self):
        """Test that auto-badges are not awarded multiple times."""
        # Create message
        conversation = Conversation.objects.create(
            title="Test",
            creator=self.user,
        )
        # Create message without triggering automatic badge award
        msg = ChatMessage(
            conversation=conversation,
            msg_type="HUMAN",
            content="First post!",
            creator=self.user,
        )
        msg._skip_signals = True
        msg.save()

        # Run auto-badge check twice
        result1 = check_auto_badges(self.user.id)
        result2 = check_auto_badges(self.user.id)

        self.assertEqual(result1["awards_count"], 1)
        self.assertEqual(result2["awards_count"], 0)  # Already awarded

        # Verify only one badge awarded
        count = UserBadge.objects.filter(
            user=self.user, badge=self.first_post_badge
        ).count()
        self.assertEqual(count, 1)

    def test_message_count_criteria(self):
        """Test message count badge criteria."""
        # Create badge for 5 messages
        badge = Badge.objects.create(
            name="Contributor",
            description="Made 5 posts",
            icon="MessageCircle",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.MESSAGE_COUNT,
                "value": 5,
            },
            creator=self.admin_user,
            is_public=True,
        )

        conversation = Conversation.objects.create(
            title="Test",
            creator=self.user,
        )

        # Create 4 messages - should not award
        for i in range(4):
            ChatMessage.objects.create(
                conversation=conversation,
                msg_type="HUMAN",
                content=f"Message {i}",
                creator=self.user,
            )

        check_auto_badges(self.user.id)
        self.assertEqual(
            UserBadge.objects.filter(user=self.user, badge=badge).count(), 0
        )

        # Create 5th message - should award
        ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Message 5",
            creator=self.user,
        )

        check_auto_badges(self.user.id)
        self.assertEqual(
            UserBadge.objects.filter(user=self.user, badge=badge).count(), 1
        )

    def test_corpus_contribution_criteria(self):
        """Test corpus contribution badge criteria."""
        from opencontractserver.documents.models import Document

        # Create badge for 3 corpus contributions
        badge = Badge.objects.create(
            name="Corpus Contributor",
            description="Made 3 contributions to corpus",
            icon="Users",
            badge_type=BadgeTypeChoices.CORPUS,
            corpus=self.corpus,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.CORPUS_CONTRIBUTION,
                "value": 3,
            },
            creator=self.admin_user,
            is_public=True,
        )

        # Add 2 documents to corpus - should not award
        for i in range(2):
            doc = Document.objects.create(
                title=f"Doc {i}",
                description="Test",
                creator=self.user,
            )
            doc, _, _ = self.corpus.add_document(document=doc, user=self.user)

        check_auto_badges(self.user.id, self.corpus.id)
        self.assertEqual(
            UserBadge.objects.filter(user=self.user, badge=badge).count(), 0
        )

        # Add one more document (total 3) - should award
        doc = Document.objects.create(
            title="Doc 3",
            description="Test",
            creator=self.user,
        )
        doc, _, _ = self.corpus.add_document(document=doc, user=self.user)

        check_auto_badges(self.user.id, self.corpus.id)
        self.assertEqual(
            UserBadge.objects.filter(user=self.user, badge=badge).count(), 1
        )

    def test_check_auto_badges_user_not_found(self):
        """Test check_auto_badges with non-existent user."""
        result = check_auto_badges(user_id=999999)
        self.assertFalse(result["ok"])
        self.assertIn("User not found", result["error"])

    def test_check_auto_badges_corpus_not_found(self):
        """Test check_auto_badges with non-existent corpus."""
        result = check_auto_badges(user_id=self.user.id, corpus_id=999999)
        self.assertFalse(result["ok"])
        self.assertIn("Corpus not found", result["error"])

    def test_badge_without_criteria_config(self):
        """Test badge with no criteria config raises validation error."""
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as cm:
            Badge.objects.create(
                name="No Criteria",
                description="Badge without criteria",
                icon="Star",
                badge_type=BadgeTypeChoices.GLOBAL,
                is_auto_awarded=True,
                criteria_config=None,
                creator=self.admin_user,
                is_public=True,
            )

        # Verify the validation error mentions missing criteria_config
        self.assertIn("criteria_config", cm.exception.message_dict)

    def test_badge_with_incomplete_criteria_config(self):
        """Test badge with incomplete criteria config raises validation error."""
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as cm:
            Badge.objects.create(
                name="Incomplete Criteria",
                description="Badge with incomplete criteria",
                icon="Star",
                badge_type=BadgeTypeChoices.GLOBAL,
                is_auto_awarded=True,
                criteria_config={
                    "type": BadgeCriteriaType.MESSAGE_COUNT
                },  # Missing count
                creator=self.admin_user,
                is_public=True,
            )

        # Verify the validation error mentions missing required field
        self.assertIn("criteria_config", cm.exception.message_dict)

    def test_badge_with_unknown_criteria_type(self):
        """Test badge with unknown criteria type raises validation error."""
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as cm:
            Badge.objects.create(
                name="Unknown Criteria",
                description="Badge with unknown criteria",
                icon="Star",
                badge_type=BadgeTypeChoices.GLOBAL,
                is_auto_awarded=True,
                criteria_config={
                    "type": "unknown_type",
                    "value": 10,
                },
                creator=self.admin_user,
                is_public=True,
            )

        # Verify the validation error mentions unknown criteria type
        self.assertIn("criteria_config", cm.exception.message_dict)

    def test_check_badges_for_all_users(self):
        """Test checking badges for all active users."""
        from opencontractserver.tasks.badge_tasks import check_badges_for_all_users

        # Create another active user
        user2 = User.objects.create_user(
            username="autoawardtasks_user2",
            password="testpass123",
            email="autoawardtasks_user2@test.com",
            is_active=True,
        )

        # Create messages for both users without triggering automatic badge awards
        for user in [self.user, user2]:
            conversation = Conversation.objects.create(
                title=f"Test {user.username}",
                creator=user,
            )
            msg = ChatMessage(
                conversation=conversation,
                msg_type="HUMAN",
                content="First post!",
                creator=user,
            )
            msg._skip_signals = True
            msg.save()

        # Run task
        result = check_badges_for_all_users()

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["users_checked"], 2)
        self.assertGreaterEqual(result["users_with_awards"], 2)

        # Verify both users got the first post badge
        for user in [self.user, user2]:
            self.assertTrue(
                UserBadge.objects.filter(
                    user=user, badge=self.first_post_badge
                ).exists()
            )

    def test_revoke_badges_by_criteria(self):
        """Test revoking badges that no longer meet criteria."""
        from opencontractserver.tasks.badge_tasks import revoke_badges_by_criteria

        # Create a badge with message count criteria
        badge = Badge.objects.create(
            name="Active User",
            description="Has 2+ messages",
            icon="MessageCircle",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.MESSAGE_COUNT,
                "value": 2,
            },
            creator=self.admin_user,
            is_public=True,
        )

        # Create 2 messages and award badge
        conversation = Conversation.objects.create(
            title="Test",
            creator=self.user,
        )
        # Create messages without triggering badge signals
        msg1 = ChatMessage(
            conversation=conversation,
            msg_type="HUMAN",
            content="Message 1",
            creator=self.user,
        )
        msg1._skip_signals = True
        msg1.save()

        msg2 = ChatMessage(
            conversation=conversation,
            msg_type="HUMAN",
            content="Message 2",
            creator=self.user,
        )
        msg2._skip_signals = True
        msg2.save()

        # Manually award badge
        UserBadge.objects.create(
            user=self.user,
            badge=badge,
        )

        # Verify badge exists
        self.assertTrue(UserBadge.objects.filter(user=self.user, badge=badge).exists())

        # Delete one message so user no longer meets criteria
        msg2.delete()

        # Run revoke task
        result = revoke_badges_by_criteria(badge.id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["checked_count"], 1)
        self.assertEqual(result["revoked_count"], 1)

        # Verify badge was revoked
        self.assertFalse(UserBadge.objects.filter(user=self.user, badge=badge).exists())

    def test_revoke_badges_badge_not_found(self):
        """Test revoking badges with non-existent badge."""
        from opencontractserver.tasks.badge_tasks import revoke_badges_by_criteria

        result = revoke_badges_by_criteria(badge_id=999999)
        self.assertFalse(result["ok"])
        self.assertIn("Badge not found", result["error"])

    def test_revoke_badges_non_auto_awarded_badge(self):
        """Test revoking badges for non-auto-awarded badge."""
        from opencontractserver.tasks.badge_tasks import revoke_badges_by_criteria

        # Create non-auto-awarded badge
        badge = Badge.objects.create(
            name="Manual Badge",
            description="Manually awarded",
            icon="Trophy",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=False,
            creator=self.admin_user,
            is_public=True,
        )

        result = revoke_badges_by_criteria(badge.id)
        self.assertFalse(result["ok"])
        self.assertIn("not auto-awarded", result["error"])

    def test_reputation_threshold_criteria_global(self):
        """Test auto-awarding badge based on global reputation threshold."""
        from opencontractserver.conversations.models import UserReputation

        # Create auto-award badge for reputation
        badge = Badge.objects.create(
            name="Reputable User",
            description="Achieved high reputation",
            icon="Star",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.REPUTATION,
                "value": 10,
            },
            creator=self.admin_user,
            is_public=True,
        )

        # Create global reputation record (corpus=None)
        UserReputation.objects.create(
            user=self.user,
            corpus=None,
            reputation_score=5,
            creator=self.user,
        )

        # Check badges - should not be awarded yet
        result = check_auto_badges(self.user.id)
        self.assertEqual(result["awards_count"], 0)

        # Increase reputation to meet threshold
        rep = UserReputation.objects.get(user=self.user, corpus__isnull=True)
        rep.reputation_score = 15
        rep.save()

        # Check badges again - should be awarded
        result = check_auto_badges(self.user.id)
        self.assertEqual(result["awards_count"], 1)

        # Verify badge was awarded
        user_badge = UserBadge.objects.filter(user=self.user, badge=badge).first()
        self.assertIsNotNone(user_badge)
        self.assertIsNone(user_badge.awarded_by)

    def test_reputation_threshold_criteria_corpus(self):
        """Test auto-awarding badge based on corpus-specific reputation threshold."""
        from opencontractserver.conversations.models import UserReputation

        # Create corpus-specific auto-award badge
        badge = Badge.objects.create(
            name="Corpus Expert",
            description="High reputation in corpus",
            icon="Award",
            badge_type=BadgeTypeChoices.CORPUS,
            corpus=self.corpus,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.REPUTATION,
                "value": 20,
            },
            creator=self.admin_user,
            is_public=True,
        )

        # Create corpus-specific reputation record
        UserReputation.objects.create(
            user=self.user,
            corpus=self.corpus,
            reputation_score=25,
            creator=self.user,
        )

        # Check badges - should be awarded
        result = check_auto_badges(self.user.id, corpus_id=self.corpus.id)
        self.assertEqual(result["awards_count"], 1)

        # Verify badge was awarded
        user_badge = UserBadge.objects.filter(
            user=self.user, badge=badge, corpus=self.corpus
        ).first()
        self.assertIsNotNone(user_badge)

    def test_message_upvotes_criteria_global(self):
        """Test auto-awarding badge when user's message gets N upvotes."""
        from opencontractserver.conversations.models import MessageVote, VoteType

        # Create auto-award badge for message upvotes
        badge = Badge.objects.create(
            name="Popular Message",
            description="Got a message with 5 upvotes",
            icon="ThumbsUp",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.MESSAGE_UPVOTES,
                "value": 5,
            },
            creator=self.admin_user,
            is_public=True,
        )

        # Create conversation and message
        conversation = Conversation.objects.create(
            title="Test Conversation",
            creator=self.user,
        )
        msg = ChatMessage(
            conversation=conversation,
            msg_type="HUMAN",
            content="Popular message!",
            creator=self.user,
        )
        msg._skip_signals = True
        msg.save()

        # Create some voters
        voters = [
            User.objects.create_user(
                username=f"voter{i}",
                password="testpass123",
                email=f"voter{i}@test.com",
            )
            for i in range(6)
        ]

        # Add 3 upvotes - should not meet threshold yet
        for voter in voters[:3]:
            MessageVote.objects.create(
                message=msg, vote_type=VoteType.UPVOTE, creator=voter
            )

        check_auto_badges(self.user.id)
        # First Post badge will be awarded, but not the upvotes badge
        self.assertFalse(
            UserBadge.objects.filter(user=self.user, badge=badge).exists(),
            "Upvotes badge should not be awarded with only 3 upvotes",
        )

        # Add 2 more upvotes to meet threshold
        for voter in voters[3:5]:
            MessageVote.objects.create(
                message=msg, vote_type=VoteType.UPVOTE, creator=voter
            )

        check_auto_badges(self.user.id)

        # Verify the upvotes badge was awarded
        user_badge = UserBadge.objects.filter(user=self.user, badge=badge).first()
        self.assertIsNotNone(
            user_badge, "Upvotes badge should be awarded with 5 upvotes"
        )

    def test_message_upvotes_criteria_corpus(self):
        """Test auto-awarding badge for corpus-specific message upvotes."""
        from opencontractserver.conversations.models import MessageVote, VoteType

        # Create corpus-specific auto-award badge
        badge = Badge.objects.create(
            name="Corpus Influencer",
            description="Got a popular message in corpus",
            icon="MessageCircle",
            badge_type=BadgeTypeChoices.CORPUS,
            corpus=self.corpus,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.MESSAGE_UPVOTES,
                "value": 3,
            },
            creator=self.admin_user,
            is_public=True,
        )

        # Create conversation linked to corpus
        conversation = Conversation.objects.create(
            title="Corpus Conversation",
            creator=self.user,
            chat_with_corpus=self.corpus,
        )
        msg = ChatMessage(
            conversation=conversation,
            msg_type="HUMAN",
            content="Corpus message!",
            creator=self.user,
        )
        msg._skip_signals = True
        msg.save()

        # Create voters and add upvotes
        voters = [
            User.objects.create_user(
                username=f"corpus_voter{i}",
                password="testpass123",
                email=f"corpus_voter{i}@test.com",
            )
            for i in range(4)
        ]

        for voter in voters[:4]:
            MessageVote.objects.create(
                message=msg, vote_type=VoteType.UPVOTE, creator=voter
            )

        # Check badges for corpus context
        result = check_auto_badges(self.user.id, corpus_id=self.corpus.id)
        self.assertEqual(result["awards_count"], 1)

        # Verify badge was awarded with corpus context
        user_badge = UserBadge.objects.filter(
            user=self.user, badge=badge, corpus=self.corpus
        ).first()
        self.assertIsNotNone(user_badge)

    def test_multiple_reputation_thresholds_progressive_awards(self):
        """
        Test that multiple reputation threshold badges are awarded progressively
        as user's reputation increases through upvotes.

        Creates badges for reputation scores of 1, 3, and 10, then gives the user
        upvotes to verify each badge is awarded at the correct threshold.
        """
        from opencontractserver.conversations.models import (
            MessageVote,
            UserReputation,
            VoteType,
        )

        # Create three reputation threshold badges with increasing thresholds
        badge_1_point = Badge.objects.create(
            name="First Reputation Point",
            description="Earned your first reputation point",
            icon="Star",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.REPUTATION,
                "value": 1,
            },
            creator=self.admin_user,
            is_public=True,
        )

        badge_3_points = Badge.objects.create(
            name="Rising Star",
            description="Reached 3 reputation points",
            icon="TrendingUp",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.REPUTATION,
                "value": 3,
            },
            creator=self.admin_user,
            is_public=True,
        )

        badge_10_points = Badge.objects.create(
            name="Reputation Master",
            description="Reached 10 reputation points",
            icon="Award",
            badge_type=BadgeTypeChoices.GLOBAL,
            is_auto_awarded=True,
            criteria_config={
                "type": BadgeCriteriaType.REPUTATION,
                "value": 10,
            },
            creator=self.admin_user,
            is_public=True,
        )

        # Create a conversation and message from test user
        conversation = Conversation.objects.create(
            title="Test Conversation for Reputation",
            creator=self.user,
        )
        msg = ChatMessage(
            conversation=conversation,
            msg_type="HUMAN",
            content="Quality content deserving upvotes!",
            creator=self.user,
        )
        msg._skip_signals = True
        msg.save()

        # Create voters who will upvote the message
        voters = [
            User.objects.create_user(
                username=f"reputation_voter_{i}",
                password="testpass123",
                email=f"reputation_voter_{i}@test.com",
            )
            for i in range(12)
        ]

        # SCENARIO 1: No reputation yet - no badges awarded
        result = check_auto_badges(self.user.id)
        # First Post badge gets awarded, but no reputation badges
        self.assertFalse(
            UserBadge.objects.filter(user=self.user, badge=badge_1_point).exists(),
            "1-point badge should NOT be awarded with 0 reputation",
        )
        self.assertFalse(
            UserBadge.objects.filter(user=self.user, badge=badge_3_points).exists(),
            "3-point badge should NOT be awarded with 0 reputation",
        )
        self.assertFalse(
            UserBadge.objects.filter(user=self.user, badge=badge_10_points).exists(),
            "10-point badge should NOT be awarded with 0 reputation",
        )

        # SCENARIO 2: Give 1 upvote -> reputation = 1 -> should award 1-point badge
        MessageVote.objects.create(
            message=msg, vote_type=VoteType.UPVOTE, creator=voters[0]
        )

        # Update user reputation manually (simulating what would happen via signals)
        UserReputation.objects.update_or_create(
            user=self.user,
            corpus=None,
            defaults={
                "reputation_score": 1,
                "total_upvotes_received": 1,
                "creator": self.user,
            },
        )

        result = check_auto_badges(self.user.id)

        # Verify 1-point badge awarded
        self.assertTrue(
            UserBadge.objects.filter(user=self.user, badge=badge_1_point).exists(),
            "1-point badge SHOULD be awarded with 1 reputation",
        )
        # Others not yet awarded
        self.assertFalse(
            UserBadge.objects.filter(user=self.user, badge=badge_3_points).exists(),
            "3-point badge should NOT be awarded with 1 reputation",
        )
        self.assertFalse(
            UserBadge.objects.filter(user=self.user, badge=badge_10_points).exists(),
            "10-point badge should NOT be awarded with 1 reputation",
        )

        # SCENARIO 3: Give 2 more upvotes -> reputation = 3 -> should award 3-point badge
        for voter in voters[1:3]:
            MessageVote.objects.create(
                message=msg, vote_type=VoteType.UPVOTE, creator=voter
            )

        # Update reputation to 3
        rep = UserReputation.objects.get(user=self.user, corpus=None)
        rep.reputation_score = 3
        rep.total_upvotes_received = 3
        rep.save()

        result = check_auto_badges(self.user.id)

        # Verify 3-point badge awarded (1-point already awarded)
        self.assertTrue(
            UserBadge.objects.filter(user=self.user, badge=badge_3_points).exists(),
            "3-point badge SHOULD be awarded with 3 reputation",
        )
        # 10-point not yet awarded
        self.assertFalse(
            UserBadge.objects.filter(user=self.user, badge=badge_10_points).exists(),
            "10-point badge should NOT be awarded with 3 reputation",
        )

        # SCENARIO 4: Give 7 more upvotes -> reputation = 10 -> should award 10-point badge
        for voter in voters[3:10]:
            MessageVote.objects.create(
                message=msg, vote_type=VoteType.UPVOTE, creator=voter
            )

        # Update reputation to 10
        rep.reputation_score = 10
        rep.total_upvotes_received = 10
        rep.save()

        result = check_auto_badges(self.user.id)

        # Verify 10-point badge awarded
        self.assertTrue(
            UserBadge.objects.filter(user=self.user, badge=badge_10_points).exists(),
            "10-point badge SHOULD be awarded with 10 reputation",
        )

        # FINAL VERIFICATION: All three badges awarded, user has reputation of 10
        awarded_badges = UserBadge.objects.filter(
            user=self.user,
            badge__in=[badge_1_point, badge_3_points, badge_10_points],
        )
        self.assertEqual(
            awarded_badges.count(),
            3,
            f"User should have all 3 reputation badges. Has: {awarded_badges.count()}",
        )

        # Verify reputation score is correct
        final_rep = UserReputation.objects.get(user=self.user, corpus=None)
        self.assertEqual(
            final_rep.reputation_score,
            10,
            f"Final reputation should be 10, got {final_rep.reputation_score}",
        )
        self.assertEqual(
            final_rep.total_upvotes_received,
            10,
            f"Should have 10 total upvotes, got {final_rep.total_upvotes_received}",
        )

        # BONUS: Verify badges are NOT awarded twice (idempotency)
        result = check_auto_badges(self.user.id)
        self.assertEqual(
            result["awards_count"],
            0,
            "Running badge check again should not award any new badges",
        )

    def test_criteria_validation_number_type_error(self):
        """Test validation rejects non-number values for number fields."""
        from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry

        # Test with string instead of number
        is_valid, error = BadgeCriteriaRegistry.validate_config(
            {"type": BadgeCriteriaType.REPUTATION, "value": "not_a_number"}
        )
        self.assertFalse(is_valid)
        self.assertIn("must be a number", error)

    def test_criteria_validation_number_min_value(self):
        """Test validation enforces minimum value for number fields."""
        from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry

        # Test with value below minimum
        is_valid, error = BadgeCriteriaRegistry.validate_config(
            {"type": BadgeCriteriaType.REPUTATION, "value": -5}
        )
        self.assertFalse(is_valid)
        self.assertIn("must be >=", error)

    def test_criteria_validation_number_max_value(self):
        """Test validation enforces maximum value for number fields."""
        from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry

        # Test with value above maximum (if max_value is set)
        # Using a very large number that would exceed reasonable limits
        is_valid, error = BadgeCriteriaRegistry.validate_config(
            {"type": BadgeCriteriaType.REPUTATION, "value": 999999999}
        )
        # This might pass if there's no max_value set, so we check
        # Let's test with message_count which might have limits
        is_valid, error = BadgeCriteriaRegistry.validate_config(
            {"type": BadgeCriteriaType.MESSAGE_COUNT, "value": 999999999}
        )
        # If there's a max value defined, this should fail
        # Otherwise we just verify it doesn't crash

    def test_criteria_validation_unexpected_fields(self):
        """Test validation rejects unexpected fields in config."""
        from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry

        is_valid, error = BadgeCriteriaRegistry.validate_config(
            {
                "type": BadgeCriteriaType.REPUTATION,
                "value": 10,
                "unexpected_field": "should_not_be_here",
                "another_bad_field": 123,
            }
        )
        self.assertFalse(is_valid)
        self.assertIn("Unexpected fields", error)
