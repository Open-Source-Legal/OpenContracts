"""
Tests for User Profile functionality (Issue #611)

Epic: #572 - Social Features Epic
Issue: #611 - Create User Profile Page with badge display and stats

Tests the User.visible_to_user() manager method and profile privacy settings.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.conversations.models import ChatMessage, Conversation

User = get_user_model()


class UserProfileVisibilityTestCase(TestCase):
    """Test User.visible_to_user() manager method for profile privacy"""

    def setUp(self):
        """Create test users with different privacy settings"""
        # Public profile users
        self.public_user1 = User.objects.create_user(
            username="public_user1",
            email="public1@example.com",
            is_profile_public=True,
            is_active=True,
        )
        self.public_user2 = User.objects.create_user(
            username="public_user2",
            email="public2@example.com",
            is_profile_public=True,
            is_active=True,
        )

        # Private profile user
        self.private_user = User.objects.create_user(
            username="private_user",
            email="private@example.com",
            is_profile_public=False,
            is_active=True,
        )

        # Inactive user (should never be visible)
        self.inactive_user = User.objects.create_user(
            username="inactive_user",
            email="inactive@example.com",
            is_profile_public=True,
            is_active=False,
        )

    def test_anonymous_user_sees_only_public_profiles(self):
        """Anonymous users should only see public, active profiles"""
        visible = User.objects.visible_to_user(None)

        self.assertIn(self.public_user1, visible)
        self.assertIn(self.public_user2, visible)
        self.assertNotIn(self.private_user, visible)
        self.assertNotIn(self.inactive_user, visible)

    def test_anonymous_user_object_sees_only_public_profiles(self):
        """AnonymousUser instance should only see public, active profiles"""
        anonymous = AnonymousUser()
        visible = User.objects.visible_to_user(anonymous)

        self.assertIn(self.public_user1, visible)
        self.assertIn(self.public_user2, visible)
        self.assertNotIn(self.private_user, visible)
        self.assertNotIn(self.inactive_user, visible)

    def test_authenticated_user_sees_public_profiles(self):
        """Authenticated users should see all public, active profiles"""
        visible = User.objects.visible_to_user(self.public_user1)

        self.assertIn(self.public_user1, visible)  # Own profile
        self.assertIn(self.public_user2, visible)  # Other public profile
        self.assertNotIn(self.private_user, visible)  # Private profile
        self.assertNotIn(self.inactive_user, visible)  # Inactive user

    def test_user_sees_own_private_profile(self):
        """Users should always see their own profile, even if private"""
        visible = User.objects.visible_to_user(self.private_user)

        self.assertIn(self.private_user, visible)  # Own profile (private)
        self.assertIn(self.public_user1, visible)  # Public profiles
        self.assertIn(self.public_user2, visible)

    def test_user_cannot_see_other_private_profiles(self):
        """Users should not see other users' private profiles"""
        visible = User.objects.visible_to_user(self.public_user1)

        self.assertNotIn(self.private_user, visible)

    def test_inactive_users_never_visible(self):
        """Inactive users should never be visible, even with public profiles"""
        # Anonymous user
        visible = User.objects.visible_to_user(None)
        self.assertNotIn(self.inactive_user, visible)

        # Authenticated user
        visible = User.objects.visible_to_user(self.public_user1)
        self.assertNotIn(self.inactive_user, visible)

        # Own inactive profile
        visible = User.objects.visible_to_user(self.inactive_user)
        self.assertNotIn(self.inactive_user, visible)


class UserProfileStatsTestCase(TestCase):
    """Test UserType GraphQL stats resolvers"""

    def setUp(self):
        """Create test users and activity data"""
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            is_profile_public=True,
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            is_profile_public=True,
        )

        # Create conversation and messages for user1
        self.conversation = Conversation.objects.create(
            title="Test Conversation",
            creator=self.user1,
            is_public=True,
        )

        self.message1 = ChatMessage.objects.create(
            conversation=self.conversation,
            creator=self.user1,
            msg_type="HUMAN",
            content="Test message 1",
        )
        self.message2 = ChatMessage.objects.create(
            conversation=self.conversation,
            creator=self.user1,
            msg_type="HUMAN",
            content="Test message 2",
        )

        # Create message from user2
        self.message3 = ChatMessage.objects.create(
            conversation=self.conversation,
            creator=self.user2,
            msg_type="HUMAN",
            content="Test message 3",
        )

    def test_user_message_count_basic(self):
        """Test that message counts are accurate"""
        # user1 should have 2 messages
        user1_count = (
            ChatMessage.objects.filter(creator=self.user1, msg_type="HUMAN")
            .visible_to_user(self.user1)
            .count()
        )
        self.assertEqual(user1_count, 2)

        # user2 should have 1 message
        user2_count = (
            ChatMessage.objects.filter(creator=self.user2, msg_type="HUMAN")
            .visible_to_user(self.user2)
            .count()
        )
        self.assertEqual(user2_count, 1)

    def test_user_message_count_respects_permissions(self):
        """Test that message counts respect visibility permissions"""
        # Make conversation private
        self.conversation.is_public = False
        self.conversation.save()

        # user1 can see their own messages in private conversation
        user1_count = (
            ChatMessage.objects.filter(creator=self.user1, msg_type="HUMAN")
            .visible_to_user(self.user1)
            .count()
        )
        self.assertEqual(user1_count, 2)

        # Anonymous user cannot see messages in private conversation
        anon_count = (
            ChatMessage.objects.filter(creator=self.user1, msg_type="HUMAN")
            .visible_to_user(None)
            .count()
        )
        self.assertEqual(anon_count, 0)

    def test_user_conversations_created_count(self):
        """Test that conversation creation counts are accurate"""
        # Create additional conversation for user1
        Conversation.objects.create(
            title="Second Conversation",
            creator=self.user1,
            is_public=True,
        )

        user1_conversations = (
            Conversation.objects.filter(creator=self.user1)
            .visible_to_user(self.user1)
            .count()
        )
        self.assertEqual(user1_conversations, 2)

        user2_conversations = (
            Conversation.objects.filter(creator=self.user2)
            .visible_to_user(self.user2)
            .count()
        )
        self.assertEqual(user2_conversations, 0)


class UserProfilePrivacyUpdateTestCase(TestCase):
    """Test updating user profile privacy settings"""

    def setUp(self):
        """Create test user"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            is_profile_public=True,
        )

    def test_default_profile_is_public(self):
        """Test that new users default to public profiles"""
        new_user = User.objects.create_user(
            username="newuser",
            email="new@example.com",
        )
        self.assertTrue(new_user.is_profile_public)

    def test_can_set_profile_private(self):
        """Test that users can set their profile to private"""
        self.user.is_profile_public = False
        self.user.save()

        updated_user = User.objects.get(pk=self.user.pk)
        self.assertFalse(updated_user.is_profile_public)

    def test_can_set_profile_public(self):
        """Test that users can set their profile to public"""
        self.user.is_profile_public = False
        self.user.save()

        self.user.is_profile_public = True
        self.user.save()

        updated_user = User.objects.get(pk=self.user.pk)
        self.assertTrue(updated_user.is_profile_public)

    def test_private_profile_not_visible_to_others(self):
        """Test that private profiles are filtered from querysets"""
        self.user.is_profile_public = False
        self.user.save()

        other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
        )

        visible = User.objects.visible_to_user(other_user)
        self.assertNotIn(self.user, visible)

    def test_user_sees_own_profile_when_private(self):
        """Test that users see their own profile even when private"""
        self.user.is_profile_public = False
        self.user.save()

        visible = User.objects.visible_to_user(self.user)
        self.assertIn(self.user, visible)
