"""
Tests for Badge/UserBadge Visibility System

These tests verify that badge awards respect the recipient's profile privacy.
Badge visibility follows the same rules as user profile visibility.

Visibility Rules:
- Badge awards are visible if the recipient's profile is visible
- Corpus-specific badges: visible to users with access to that corpus
- Own badges: always visible regardless of profile privacy

Issue: Permission audit remediation
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.badges.query_optimizer import BadgeQueryOptimizer
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestUserBadgeVisibility(TestCase):
    """Tests that user badge visibility follows profile privacy rules."""

    def setUp(self):
        """Create test users, badges, and awards."""
        self.badge_owner = User.objects.create_user(
            username="badgeholder",
            email="badge@example.com",
            password="testpass123",
            is_profile_public=False,  # Private profile
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="testpass123",
        )

        # Create a badge
        self.achievement_badge = Badge.objects.create(
            name="First Annotation Badge",
            description="Awarded for creating your first annotation",
            icon="Star",
            creator=self.viewer,  # Badge definition creator
        )

        # Award the badge
        self.badge_award = UserBadge.objects.create(
            user=self.badge_owner,  # Private user receives badge
            badge=self.achievement_badge,
        )

    def test_badge_of_private_user_not_visible_to_unrelated_viewer(self):
        """
        GIVEN: A badge awarded to a user (badgeholder) with is_profile_public=False
        AND: A viewer who does NOT share corpus membership with badgeholder
        WHEN: Viewer queries for visible user badges
        THEN: The badge award should NOT be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.viewer)

        self.assertNotIn(
            self.badge_award,
            visible_badges,
            "Badges of private users should NOT be visible to unrelated viewers",
        )

    def test_own_badges_always_visible(self):
        """
        GIVEN: A user (badgeholder) with badge awards
        WHEN: badgeholder queries for their own badges
        THEN: Their badges should be visible regardless of profile privacy
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.badge_owner)

        self.assertIn(
            self.badge_award,
            visible_badges,
            "Users should always see their own badges",
        )

    def test_badge_of_public_user_visible_to_viewer(self):
        """
        GIVEN: A badge awarded to a public user
        WHEN: Another user queries for visible badges
        THEN: The badge should be visible
        """
        public_user = User.objects.create_user(
            username="publicuser",
            email="public@example.com",
            password="testpass123",
            is_profile_public=True,
        )
        public_badge_award = UserBadge.objects.create(
            user=public_user,
            badge=self.achievement_badge,
        )

        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.viewer)

        self.assertIn(
            public_badge_award,
            visible_badges,
            "Badges of public users should be visible",
        )


class TestBadgeVisibilityViaCorpusMembership(TestCase):
    """Tests that corpus membership enables badge visibility."""

    def setUp(self):
        """Create scenario with corpus collaborators."""
        self.corpus_owner = User.objects.create_user(
            username="corpusowner",
            email="owner@example.com",
            password="testpass123",
        )
        self.private_collaborator = User.objects.create_user(
            username="collaborator",
            email="collab@example.com",
            password="testpass123",
            is_profile_public=False,  # Private profile
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
        )

        # Create corpus and set up permissions
        self.shared_corpus = Corpus.objects.create(
            title="Shared Corpus",
            creator=self.corpus_owner,
        )

        # Give collaborator UPDATE permission (> READ)
        set_permissions_for_obj_to_user(
            self.private_collaborator,
            self.shared_corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

        # Create badge and award to collaborator
        self.badge = Badge.objects.create(
            name="Team Player Badge",
            description="For great collaboration",
            icon="Users",
            creator=self.corpus_owner,
        )
        self.badge_award = UserBadge.objects.create(
            user=self.private_collaborator,
            badge=self.badge,
        )

    def test_badge_visible_via_corpus_membership(self):
        """
        GIVEN: A badge awarded to a private user
        AND: The private user has > READ permission on a shared corpus
        WHEN: Corpus owner queries for visible badges
        THEN: The badge should be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.corpus_owner)

        self.assertIn(
            self.badge_award,
            visible_badges,
            "Badges should be visible via corpus membership",
        )

    def test_badge_not_visible_to_outsider(self):
        """
        GIVEN: A badge awarded to a private user
        AND: An outsider with no shared corpus membership
        WHEN: Outsider queries for visible badges
        THEN: The badge should NOT be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.outsider)

        self.assertNotIn(
            self.badge_award,
            visible_badges,
            "Badges should NOT be visible to outsiders",
        )


class TestCorpusSpecificBadgeVisibility(TestCase):
    """Tests for corpus-specific badge visibility."""

    def setUp(self):
        """Create corpus-specific badge scenario."""
        self.corpus_owner = User.objects.create_user(
            username="corpusowner",
            email="owner@example.com",
            password="testpass123",
        )
        self.badge_recipient = User.objects.create_user(
            username="recipient",
            email="recipient@example.com",
            password="testpass123",
            is_profile_public=True,  # Public profile
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
        )

        # Create private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Legal Corpus",
            creator=self.corpus_owner,
            is_public=False,
        )

        # Give recipient access to corpus
        set_permissions_for_obj_to_user(
            self.badge_recipient,
            self.private_corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

        # Create corpus-specific badge
        self.corpus_badge = Badge.objects.create(
            name="Top Contributor",
            description="Top contributor in this corpus",
            icon="Trophy",
            badge_type="CORPUS",
            corpus=self.private_corpus,
            creator=self.corpus_owner,
        )

        # Award corpus badge
        self.corpus_badge_award = UserBadge.objects.create(
            user=self.badge_recipient,
            badge=self.corpus_badge,
            corpus=self.private_corpus,
        )

    def test_corpus_badge_visible_to_corpus_member(self):
        """
        GIVEN: A corpus-specific badge awarded in a private corpus
        AND: A user who has access to that corpus
        WHEN: User queries for visible badges
        THEN: The corpus badge should be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.corpus_owner)

        self.assertIn(
            self.corpus_badge_award,
            visible_badges,
            "Corpus-specific badges should be visible to corpus members",
        )

    def test_corpus_badge_not_visible_to_outsider(self):
        """
        GIVEN: A corpus-specific badge awarded in a private corpus
        AND: A user who does NOT have access to that corpus
        WHEN: User queries for visible badges
        THEN: The corpus badge should NOT be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.outsider)

        self.assertNotIn(
            self.corpus_badge_award,
            visible_badges,
            "Corpus-specific badges should NOT be visible to non-members",
        )


class TestBadgeVisibilityIDORProtection(TestCase):
    """Tests for IDOR protection in badge visibility."""

    def setUp(self):
        """Create scenario for IDOR testing."""
        self.user_a = User.objects.create_user(
            username="user_a",
            email="a@example.com",
            password="testpass123",
            is_profile_public=False,
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="b@example.com",
            password="testpass123",
        )

        self.badge = Badge.objects.create(
            name="Secret Badge",
            description="A private badge",
            icon="Lock",
            creator=self.user_a,
        )

        # Award badge to private user
        self.private_badge_award = UserBadge.objects.create(
            user=self.user_a,
            badge=self.badge,
        )

    def test_check_visibility_returns_false_for_inaccessible_badge(self):
        """
        GIVEN: A badge awarded to a private user
        AND: A viewer with no access to that user
        WHEN: Checking badge visibility directly
        THEN: Returns (False, None) - cannot enumerate badge IDs
        """
        has_permission, badge = BadgeQueryOptimizer.check_user_badge_visibility(
            self.user_b, self.private_badge_award.id
        )

        self.assertFalse(has_permission, "Should return False for inaccessible badge")
        self.assertIsNone(badge, "Should return None badge object")

    def test_check_visibility_returns_true_for_own_badge(self):
        """
        GIVEN: A user's own badge
        WHEN: Checking badge visibility
        THEN: Returns (True, badge_object)
        """
        has_permission, badge = BadgeQueryOptimizer.check_user_badge_visibility(
            self.user_a, self.private_badge_award.id
        )

        self.assertTrue(has_permission, "Should return True for own badge")
        self.assertEqual(
            badge, self.private_badge_award, "Should return the badge object"
        )

    def test_check_visibility_returns_false_for_nonexistent_badge(self):
        """
        GIVEN: A non-existent badge ID
        WHEN: Checking badge visibility
        THEN: Returns (False, None) - same as access denied (IDOR protection)
        """
        has_permission, badge = BadgeQueryOptimizer.check_user_badge_visibility(
            self.user_a, 999999  # Non-existent ID
        )

        self.assertFalse(
            has_permission,
            "Should return False for non-existent badge (same as access denied)",
        )
        self.assertIsNone(badge, "Should return None for non-existent badge")


class TestBadgeVisibilityAnonymousUser(TestCase):
    """Tests for anonymous user badge visibility."""

    def setUp(self):
        """Create test users and badges."""
        self.public_user = User.objects.create_user(
            username="public",
            email="public@example.com",
            password="testpass123",
            is_profile_public=True,
        )
        self.private_user = User.objects.create_user(
            username="private",
            email="private@example.com",
            password="testpass123",
            is_profile_public=False,
        )

        self.badge = Badge.objects.create(
            name="Achievement Badge",
            description="For achievements",
            icon="Award",
            creator=self.public_user,
        )

        self.public_badge_award = UserBadge.objects.create(
            user=self.public_user,
            badge=self.badge,
        )
        self.private_badge_award = UserBadge.objects.create(
            user=self.private_user,
            badge=self.badge,
        )

    def test_anonymous_user_sees_public_user_badges(self):
        """
        GIVEN: A badge awarded to a public user
        WHEN: An anonymous user queries for badges
        THEN: The badge should be visible
        """
        anonymous = AnonymousUser()
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(anonymous)

        self.assertIn(
            self.public_badge_award,
            visible_badges,
            "Anonymous users should see badges of public users",
        )

    def test_anonymous_user_cannot_see_private_user_badges(self):
        """
        GIVEN: A badge awarded to a private user
        WHEN: An anonymous user queries for badges
        THEN: The badge should NOT be visible
        """
        anonymous = AnonymousUser()
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(anonymous)

        self.assertNotIn(
            self.private_badge_award,
            visible_badges,
            "Anonymous users should NOT see badges of private users",
        )


class TestSuperuserBadgeVisibility(TestCase):
    """Tests for superuser badge visibility."""

    def setUp(self):
        """Create test scenario."""
        import uuid

        self.superuser = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            password="adminpass123",
        )
        self.private_user = User.objects.create_user(
            username="private",
            email="private@example.com",
            password="testpass123",
            is_profile_public=False,
        )

        self.badge = Badge.objects.create(
            name="Hidden Badge",
            description="A private badge",
            icon="EyeOff",
            creator=self.superuser,
        )

        self.badge_award = UserBadge.objects.create(
            user=self.private_user,
            badge=self.badge,
        )

    def test_superuser_sees_all_badges(self):
        """
        GIVEN: A badge awarded to a private user
        WHEN: A superuser queries for badges
        THEN: All badges should be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.superuser)

        self.assertIn(
            self.badge_award,
            visible_badges,
            "Superusers should see all badges",
        )
