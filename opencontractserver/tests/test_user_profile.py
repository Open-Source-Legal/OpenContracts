"""
Tests for User Profile functionality (Issue #611)

Epic: #572 - Social Features Epic
Issue: #611 - Create User Profile Page with badge display and stats

Tests the User.visible_to_user() manager method and profile privacy settings.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphene.test import Client

from opencontractserver.conversations.models import ChatMessage, Conversation

User = get_user_model()


class _TestContext:
    """Minimal request-context shim with a ``user`` attribute for graphene tests."""

    def __init__(self, user):
        self.user = user


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


class UpdateMeMarkdownProfileFieldsTestCase(TestCase):
    """GraphQL UpdateMe acceptance of markdown profile fields."""

    def setUp(self):
        from config.graphql.schema import schema

        self.user = User.objects.create_user(
            username="mdprofileuser",
            email="mdprofile@example.com",
            is_profile_public=True,
        )
        self.client = Client(schema, context_value=_TestContext(self.user))

    def test_update_me_persists_markdown_profile_fields(self):
        mutation = """
            mutation UpdateMe(
                $profileHeadline: String,
                $profileAboutMarkdown: String,
                $profileLinksMarkdown: String,
            ) {
                updateMe(
                    profileHeadline: $profileHeadline,
                    profileAboutMarkdown: $profileAboutMarkdown,
                    profileLinksMarkdown: $profileLinksMarkdown,
                ) {
                    ok
                    message
                }
            }
        """
        variables = {
            "profileHeadline": "Contracts counsel",
            "profileAboutMarkdown": "**About me.**",
            "profileLinksMarkdown": "- [Site](https://example.com)",
        }
        result = self.client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateMe"]["ok"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_headline, "Contracts counsel")
        self.assertEqual(self.user.profile_about_markdown, "**About me.**")
        self.assertEqual(
            self.user.profile_links_markdown,
            "- [Site](https://example.com)",
        )

    def test_user_type_exposes_markdown_profile_fields(self):
        self.user.profile_headline = "Contracts counsel"
        self.user.profile_about_markdown = "About text"
        self.user.profile_links_markdown = "Links text"
        self.user.save()

        query = """
            query Me {
                me {
                    profileHeadline
                    profileAboutMarkdown
                    profileLinksMarkdown
                }
            }
        """
        result = self.client.execute(query)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["me"]
        self.assertEqual(data["profileHeadline"], "Contracts counsel")
        self.assertEqual(data["profileAboutMarkdown"], "About text")
        self.assertEqual(data["profileLinksMarkdown"], "Links text")

    def test_update_me_rejects_oversized_markdown_fields(self):
        """`graphene.String` has no length constraint, but `UpdateMe.mutate`
        routes through `UserUpdateSerializer` (DRF `ModelSerializer`), which
        auto-applies each model field's `max_length` validator. An oversized
        payload must therefore be rejected with a serializer error rather
        than silently persisted in the row.
        """
        from opencontractserver.users.models import User as UserModel

        # Each field exceeds its max_length by one character — headline is
        # the 200-char ``CharField``; about/links are the 5000-char fields.
        oversize_headline = "h" * 201
        oversize_about = "a" * 5001
        oversize_links = "b" * 5001

        mutation = """
            mutation UpdateMe(
                $profileHeadline: String,
                $profileAboutMarkdown: String,
                $profileLinksMarkdown: String,
            ) {
                updateMe(
                    profileHeadline: $profileHeadline,
                    profileAboutMarkdown: $profileAboutMarkdown,
                    profileLinksMarkdown: $profileLinksMarkdown,
                ) {
                    ok
                    message
                }
            }
        """
        result = self.client.execute(
            mutation,
            variables={
                "profileHeadline": oversize_headline,
                "profileAboutMarkdown": oversize_about,
                "profileLinksMarkdown": oversize_links,
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateMe"]["ok"])
        # Confirm the row wasn't mutated.
        persisted = UserModel.objects.get(pk=self.user.pk)
        self.assertEqual(persisted.profile_headline, "")
        self.assertEqual(persisted.profile_about_markdown, "")
        self.assertEqual(persisted.profile_links_markdown, "")

    def test_update_me_persists_is_profile_public_toggle(self):
        """isProfilePublic was newly added to UpdateMeInputs — verify round-trip."""
        mutation = """
            mutation UpdateMe($isProfilePublic: Boolean) {
                updateMe(isProfilePublic: $isProfilePublic) {
                    ok
                    message
                }
            }
        """
        # Sanity: starts public
        self.assertTrue(self.user.is_profile_public)

        result = self.client.execute(mutation, variables={"isProfilePublic": False})
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateMe"]["ok"])
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_profile_public)

        # Flip back to true and confirm
        result = self.client.execute(mutation, variables={"isProfilePublic": True})
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateMe"]["ok"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_profile_public)


class UserBySlugMarkdownProfileFieldVisibilityTestCase(TestCase):
    """Cross-user `userBySlug` access of markdown profile fields.

    The fields are not behind the `_is_self_view` gate because `userBySlug`
    itself filters non-self viewers to public profiles. These tests verify
    that contract end-to-end.
    """

    def setUp(self):
        from config.graphql.schema import schema

        self.public_owner = User.objects.create_user(
            username="public_owner",
            email="public_owner@example.com",
            is_profile_public=True,
            profile_headline="Headline",
            profile_about_markdown="**bio**",
            profile_links_markdown="- [home](https://example.com)",
        )
        self.private_owner = User.objects.create_user(
            username="private_owner",
            email="private_owner@example.com",
            is_profile_public=False,
            profile_headline="Hidden Headline",
            profile_about_markdown="hidden bio",
            profile_links_markdown="- [hidden](https://example.com)",
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            is_profile_public=True,
        )
        self.schema = schema

    def _client_as(self, user):
        return Client(self.schema, context_value=_TestContext(user))

    def _query_by_slug(self, viewer, slug):
        client = self._client_as(viewer)
        query = """
            query UserBySlug($slug: String!) {
                userBySlug(slug: $slug) {
                    id
                    slug
                    profileHeadline
                    profileAboutMarkdown
                    profileLinksMarkdown
                }
            }
        """
        return client.execute(query, variables={"slug": slug})

    def test_non_self_viewer_can_read_markdown_fields_on_public_profile(self):
        result = self._query_by_slug(self.viewer, self.public_owner.slug)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["userBySlug"]
        self.assertIsNotNone(data)
        self.assertEqual(data["profileHeadline"], "Headline")
        self.assertEqual(data["profileAboutMarkdown"], "**bio**")
        self.assertEqual(data["profileLinksMarkdown"], "- [home](https://example.com)")

    def test_non_self_viewer_cannot_reach_private_profile_at_all(self):
        result = self._query_by_slug(self.viewer, self.private_owner.slug)
        self.assertIsNone(result.get("errors"))
        # The whole user is hidden — not just the fields.
        self.assertIsNone(result["data"]["userBySlug"])

    def test_owner_can_read_their_own_private_profile_markdown_fields(self):
        """Closes the coverage gap flagged in review: the owner of a
        private profile must still be able to fetch their own markdown
        fields via ``userBySlug``. ``User.objects.visible_to_user``
        always includes ``user == requesting_user`` in the queryset, so
        a regression that broke this contract would be silent.
        """
        result = self._query_by_slug(self.private_owner, self.private_owner.slug)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["userBySlug"]
        self.assertIsNotNone(data, "Owner must see their own private profile")
        self.assertEqual(data["profileHeadline"], "Hidden Headline")
        self.assertEqual(data["profileAboutMarkdown"], "hidden bio")
        self.assertEqual(
            data["profileLinksMarkdown"], "- [hidden](https://example.com)"
        )
