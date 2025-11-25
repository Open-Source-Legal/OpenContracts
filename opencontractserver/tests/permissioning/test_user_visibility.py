"""
Tests for User Profile Visibility System

These tests verify that user profiles respect privacy settings and corpus membership rules.
The UserQueryOptimizer provides centralized logic for determining user visibility.

Visibility Rules:
- Own profile: always visible
- Public profiles (is_profile_public=True): visible to all
- Private profiles: visible to users who share corpus membership with > READ permission
- Inactive users: never visible (except to superusers)

Issue: Permission audit remediation
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.query_optimizer import UserQueryOptimizer
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestUserProfilePrivacy(TestCase):
    """Tests that verify user profile privacy settings are respected."""

    def setUp(self):
        """Create test users with different privacy settings."""
        self.public_user = User.objects.create_user(
            username="public_alice",
            email="alice@example.com",
            password="testpass123",
            is_profile_public=True,
        )
        self.private_user = User.objects.create_user(
            username="private_bob",
            email="bob@example.com",
            password="testpass123",
            is_profile_public=False,
        )
        self.viewer = User.objects.create_user(
            username="viewer_carol",
            email="carol@example.com",
            password="testpass123",
        )

    def test_public_profile_visible_to_any_authenticated_user(self):
        """
        GIVEN: A user (Alice) with is_profile_public=True
        WHEN: Another user (Carol) queries for visible users
        THEN: Alice's profile should be in the results
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.viewer)

        self.assertIn(
            self.public_user,
            visible_users,
            "Public profiles should be visible to any authenticated user",
        )

    def test_private_profile_not_visible_to_unrelated_user(self):
        """
        GIVEN: A user (Bob) with is_profile_public=False
        AND: A viewer (Carol) who does NOT share any corpus membership with Bob
        WHEN: Carol queries for visible users
        THEN: Bob's profile should NOT be in the results
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.viewer)

        self.assertNotIn(
            self.private_user,
            visible_users,
            "Private profiles should NOT be visible to unrelated users",
        )

    def test_own_profile_always_visible_regardless_of_privacy_setting(self):
        """
        GIVEN: A user (Bob) with is_profile_public=False
        WHEN: Bob queries for visible users
        THEN: Bob should see his own profile in the results
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.private_user)

        self.assertIn(
            self.private_user,
            visible_users,
            "Users should always see their own profile regardless of privacy setting",
        )

    def test_check_user_visibility_returns_correct_boolean(self):
        """
        GIVEN: Different visibility scenarios
        WHEN: Using check_user_visibility method
        THEN: Returns correct boolean values
        """
        # Public user is visible to viewer
        self.assertTrue(
            UserQueryOptimizer.check_user_visibility(self.viewer, self.public_user.id),
            "Public user should be visible",
        )

        # Private user is not visible to unrelated viewer
        self.assertFalse(
            UserQueryOptimizer.check_user_visibility(self.viewer, self.private_user.id),
            "Private user should not be visible to unrelated user",
        )

        # User can see themselves
        self.assertTrue(
            UserQueryOptimizer.check_user_visibility(
                self.private_user, self.private_user.id
            ),
            "User should always be able to see themselves",
        )


class TestUserVisibilityViaCorpusMembership(TestCase):
    """Tests that verify corpus membership enables user visibility."""

    def setUp(self):
        """Create test users and a shared corpus."""
        self.corpus_owner = User.objects.create_user(
            username="owner",
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

        # Create a corpus
        self.shared_corpus = Corpus.objects.create(
            title="Shared Legal Corpus",
            creator=self.corpus_owner,
        )

        # Give collaborator UPDATE permission (> READ) on the corpus
        set_permissions_for_obj_to_user(
            self.private_collaborator,
            self.shared_corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

    def test_private_user_visible_to_corpus_member_with_write_permission(self):
        """
        GIVEN: A user (collaborator) with is_profile_public=False
        AND: Another user (owner) who shares a corpus with collaborator
        AND: Collaborator has > READ permission on that corpus
        WHEN: Owner queries for visible users
        THEN: Collaborator's profile should be visible
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.corpus_owner)

        self.assertIn(
            self.private_collaborator,
            visible_users,
            "Private profiles should be visible to users who share corpus with > READ",
        )

    def test_private_user_not_visible_to_outsider(self):
        """
        GIVEN: A user (collaborator) with is_profile_public=False
        AND: A user (outsider) who does NOT have access to any shared corpus
        WHEN: Outsider queries for visible users
        THEN: Collaborator's profile should NOT be visible
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.outsider)

        self.assertNotIn(
            self.private_collaborator,
            visible_users,
            "Private profiles should NOT be visible to users outside shared corpuses",
        )

    def test_read_only_corpus_member_cannot_see_private_profiles(self):
        """
        GIVEN: A corpus with two members
        AND: One member (viewer) has only READ permission
        AND: Another member (collaborator) has is_profile_public=False
        WHEN: Viewer queries for visible users
        THEN: Collaborator's profile should NOT be visible (READ is not enough)
        """
        read_only_user = User.objects.create_user(
            username="readonly",
            email="readonly@example.com",
            password="testpass123",
        )
        # Give only READ permission (not > READ)
        set_permissions_for_obj_to_user(
            read_only_user,
            self.shared_corpus,
            [PermissionTypes.READ],
        )

        visible_users = UserQueryOptimizer.get_visible_users(read_only_user)

        self.assertNotIn(
            self.private_collaborator,
            visible_users,
            "READ-only permission should NOT enable seeing private profiles",
        )

    def test_corpus_owner_can_see_collaborators(self):
        """
        GIVEN: A corpus owner
        AND: A private collaborator with > READ permission on the corpus
        WHEN: Owner queries for visible users
        THEN: The collaborator should be visible (owner has implicit full access)
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.corpus_owner)

        self.assertIn(
            self.private_collaborator,
            visible_users,
            "Corpus owner should see collaborators with > READ permission",
        )


class TestUserVisibilityAnonymousUser(TestCase):
    """Tests for anonymous user visibility rules."""

    def setUp(self):
        """Create test users."""
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

    def test_anonymous_user_can_see_public_profiles(self):
        """
        GIVEN: A public user profile
        WHEN: An anonymous user queries for visible users
        THEN: Public profiles should be visible
        """
        anonymous = AnonymousUser()
        visible_users = UserQueryOptimizer.get_visible_users(anonymous)

        self.assertIn(
            self.public_user,
            visible_users,
            "Anonymous users should see public profiles",
        )

    def test_anonymous_user_cannot_see_private_profiles(self):
        """
        GIVEN: A private user profile
        WHEN: An anonymous user queries for visible users
        THEN: Private profiles should NOT be visible
        """
        anonymous = AnonymousUser()
        visible_users = UserQueryOptimizer.get_visible_users(anonymous)

        self.assertNotIn(
            self.private_user,
            visible_users,
            "Anonymous users should NOT see private profiles",
        )

    def test_none_user_treated_as_anonymous(self):
        """
        GIVEN: None passed as user
        WHEN: Querying for visible users
        THEN: Should behave same as anonymous user
        """
        visible_users = UserQueryOptimizer.get_visible_users(None)

        self.assertIn(
            self.public_user,
            visible_users,
            "None user should see public profiles like anonymous",
        )
        self.assertNotIn(
            self.private_user,
            visible_users,
            "None user should NOT see private profiles",
        )


class TestInactiveUserVisibility(TestCase):
    """Tests that inactive users are properly hidden."""

    def setUp(self):
        """Create active and inactive users."""
        self.active_user = User.objects.create_user(
            username="active",
            email="active@example.com",
            password="testpass123",
            is_active=True,
        )
        self.inactive_user = User.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            password="testpass123",
            is_active=False,  # Deactivated account
            is_profile_public=True,  # Even public profiles should be hidden
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="testpass123",
        )

    def test_inactive_user_not_visible_even_with_public_profile(self):
        """
        GIVEN: A user account that has been deactivated (is_active=False)
        AND: That user had is_profile_public=True
        WHEN: Another user queries for visible users
        THEN: The inactive user should NOT be visible
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.viewer)

        self.assertNotIn(
            self.inactive_user,
            visible_users,
            "Inactive users should NOT be visible even with public profile",
        )

    def test_superuser_can_see_all_active_users(self):
        """
        GIVEN: A superuser
        WHEN: Superuser queries for visible users
        THEN: All active users should be visible
        """
        import uuid

        superuser = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            password="adminpass123",
        )
        visible_users = UserQueryOptimizer.get_visible_users(superuser)

        # Active users should definitely be visible
        self.assertIn(self.active_user, visible_users)
        self.assertIn(self.viewer, visible_users)


class TestUserSearchForMention(TestCase):
    """Tests for the get_users_for_mention convenience method."""

    def setUp(self):
        """Create test users."""
        self.searcher = User.objects.create_user(
            username="searcher",
            email="searcher@example.com",
            password="testpass123",
        )
        self.alice = User.objects.create_user(
            username="alice_public",
            email="alice@example.com",
            password="testpass123",
            is_profile_public=True,
        )
        self.bob = User.objects.create_user(
            username="bob_private",
            email="bob@example.com",
            password="testpass123",
            is_profile_public=False,
        )

    def test_search_filters_by_username(self):
        """
        GIVEN: Users with different usernames
        WHEN: Searching by username substring
        THEN: Only matching public users are returned
        """
        results = UserQueryOptimizer.get_users_for_mention(self.searcher, "alice")

        self.assertIn(self.alice, results, "Alice should be found by username search")
        self.assertNotIn(self.bob, results, "Bob is private and should not be found")

    def test_search_filters_by_email(self):
        """
        GIVEN: Users with different emails
        WHEN: Searching by email substring
        THEN: Only matching visible users are returned
        """
        results = UserQueryOptimizer.get_users_for_mention(
            self.searcher, "alice@example"
        )

        self.assertIn(self.alice, results, "Alice should be found by email search")

    def test_anonymous_user_cannot_search(self):
        """
        GIVEN: An anonymous user
        WHEN: Attempting to search for mentions
        THEN: Empty queryset is returned
        """
        anonymous = AnonymousUser()
        results = UserQueryOptimizer.get_users_for_mention(anonymous, "alice")

        self.assertEqual(
            results.count(), 0, "Anonymous users cannot search for mentions"
        )
