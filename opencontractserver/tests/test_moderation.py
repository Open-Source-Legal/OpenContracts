"""
Comprehensive tests for the moderation system (Epic #555).

Tests cover:
- CorpusModerator model and permissions
- Conversation moderation (lock/unlock, pin/unpin, soft delete/restore)
- ChatMessage moderation (soft delete/restore)
- Permission checks for corpus owners and moderators
- ModerationAction audit trail
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    CorpusModerator,
    ModerationAction,
    ModerationActionType,
    ModeratorPermissionChoices,
)
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class CorpusModeratorModelTest(TestCase):
    """Test the CorpusModerator model."""

    def setUp(self):
        """Create test users and corpus."""
        self.owner = User.objects.create_user(username="owner", password="testpass123")
        self.moderator_user = User.objects.create_user(
            username="moderator", password="testpass123"
        )
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test corpus for moderation",
            creator=self.owner,
        )

    def test_create_moderator(self):
        """Test creating a corpus moderator with permissions."""
        moderator = CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_user,
            permissions=[
                ModeratorPermissionChoices.LOCK_THREADS,
                ModeratorPermissionChoices.PIN_THREADS,
            ],
            assigned_by=self.owner,
            creator=self.owner,
        )

        self.assertEqual(moderator.corpus, self.corpus)
        self.assertEqual(moderator.user, self.moderator_user)
        self.assertEqual(len(moderator.permissions), 2)
        self.assertEqual(moderator.assigned_by, self.owner)

    def test_has_permission_method(self):
        """Test the has_permission helper method."""
        moderator = CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_user,
            permissions=[
                ModeratorPermissionChoices.LOCK_THREADS,
                ModeratorPermissionChoices.PIN_THREADS,
            ],
            creator=self.owner,
        )

        self.assertTrue(
            moderator.has_permission(ModeratorPermissionChoices.LOCK_THREADS)
        )
        self.assertTrue(
            moderator.has_permission(ModeratorPermissionChoices.PIN_THREADS)
        )
        self.assertFalse(
            moderator.has_permission(ModeratorPermissionChoices.DELETE_MESSAGES)
        )
        self.assertFalse(
            moderator.has_permission(ModeratorPermissionChoices.DELETE_THREADS)
        )

    def test_unique_constraint_one_moderator_per_user_per_corpus(self):
        """Test that a user can only have one moderator record per corpus."""
        CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_user,
            permissions=[ModeratorPermissionChoices.LOCK_THREADS],
            creator=self.owner,
        )

        # Attempting to create another moderator record for the same user/corpus should fail
        with self.assertRaises(IntegrityError):
            CorpusModerator.objects.create(
                corpus=self.corpus,
                user=self.moderator_user,
                permissions=[ModeratorPermissionChoices.PIN_THREADS],
                creator=self.owner,
            )

    def test_moderator_str_representation(self):
        """Test the string representation of CorpusModerator."""
        moderator = CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_user,
            permissions=[ModeratorPermissionChoices.LOCK_THREADS],
            creator=self.owner,
        )

        expected = f"{self.moderator_user.username} - Moderator of {self.corpus.title}"
        self.assertEqual(str(moderator), expected)


class ConversationModerationTest(TestCase):
    """Test moderation actions on Conversation model."""

    def setUp(self):
        """Create test users, corpus, and conversation."""
        self.owner = User.objects.create_user(username="owner", password="testpass123")
        self.moderator_user = User.objects.create_user(
            username="moderator", password="testpass123"
        )
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test corpus for moderation",
            creator=self.owner,
        )

        self.conversation = Conversation.objects.create(
            title="Test Thread",
            description="A discussion thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )

        # Create a moderator with lock and pin permissions
        self.moderator = CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_user,
            permissions=[
                ModeratorPermissionChoices.LOCK_THREADS,
                ModeratorPermissionChoices.PIN_THREADS,
                ModeratorPermissionChoices.DELETE_THREADS,
            ],
            creator=self.owner,
        )

    def test_can_moderate_corpus_owner(self):
        """Test that corpus owner can moderate conversations."""
        self.assertTrue(self.conversation.can_moderate(self.owner))

    def test_can_moderate_designated_moderator(self):
        """Test that designated moderators can moderate conversations."""
        self.assertTrue(self.conversation.can_moderate(self.moderator_user))

    def test_can_moderate_regular_user_cannot(self):
        """Test that regular users cannot moderate conversations."""
        self.assertFalse(self.conversation.can_moderate(self.regular_user))

    def test_lock_conversation(self):
        """Test locking a conversation."""
        self.assertFalse(self.conversation.is_locked)
        self.assertIsNone(self.conversation.locked_at)
        self.assertIsNone(self.conversation.locked_by)

        self.conversation.lock(
            self.moderator_user, reason="Violates community guidelines"
        )

        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_locked)
        self.assertIsNotNone(self.conversation.locked_at)
        self.assertEqual(self.conversation.locked_by, self.moderator_user)

        # Check audit trail
        actions = ModerationAction.objects.filter(conversation=self.conversation)
        self.assertEqual(actions.count(), 1)
        action = actions.first()
        self.assertEqual(action.action_type, ModerationActionType.LOCK_THREAD.value)
        self.assertEqual(action.moderator, self.moderator_user)
        self.assertEqual(action.reason, "Violates community guidelines")

    def test_unlock_conversation(self):
        """Test unlocking a conversation."""
        # First lock it
        self.conversation.lock(self.moderator_user)
        self.assertTrue(self.conversation.is_locked)

        # Now unlock it
        self.conversation.unlock(self.owner, reason="Issue resolved")

        self.conversation.refresh_from_db()
        self.assertFalse(self.conversation.is_locked)
        self.assertIsNone(self.conversation.locked_at)
        self.assertIsNone(self.conversation.locked_by)

        # Check audit trail shows both actions
        actions = ModerationAction.objects.filter(
            conversation=self.conversation
        ).order_by("created_at")
        self.assertEqual(actions.count(), 2)
        self.assertEqual(actions[0].action_type, ModerationActionType.LOCK_THREAD.value)
        self.assertEqual(
            actions[1].action_type, ModerationActionType.UNLOCK_THREAD.value
        )
        self.assertEqual(actions[1].reason, "Issue resolved")

    def test_lock_permission_denied(self):
        """Test that non-moderators cannot lock conversations."""
        with self.assertRaises(PermissionError) as context:
            self.conversation.lock(self.regular_user)

        self.assertIn("does not have permission to lock", str(context.exception))
        self.assertFalse(self.conversation.is_locked)

    def test_pin_conversation(self):
        """Test pinning a conversation."""
        self.assertFalse(self.conversation.is_pinned)
        self.assertIsNone(self.conversation.pinned_at)
        self.assertIsNone(self.conversation.pinned_by)

        self.conversation.pin(self.moderator_user, reason="Important announcement")

        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_pinned)
        self.assertIsNotNone(self.conversation.pinned_at)
        self.assertEqual(self.conversation.pinned_by, self.moderator_user)

        # Check audit trail
        action = ModerationAction.objects.get(conversation=self.conversation)
        self.assertEqual(action.action_type, ModerationActionType.PIN_THREAD.value)
        self.assertEqual(action.moderator, self.moderator_user)
        self.assertEqual(action.reason, "Important announcement")

    def test_unpin_conversation(self):
        """Test unpinning a conversation."""
        # First pin it
        self.conversation.pin(self.moderator_user)
        self.assertTrue(self.conversation.is_pinned)

        # Now unpin it
        self.conversation.unpin(self.owner)

        self.conversation.refresh_from_db()
        self.assertFalse(self.conversation.is_pinned)
        self.assertIsNone(self.conversation.pinned_at)
        self.assertIsNone(self.conversation.pinned_by)

        # Check audit trail shows both actions
        actions = ModerationAction.objects.filter(
            conversation=self.conversation
        ).order_by("created_at")
        self.assertEqual(actions.count(), 2)
        self.assertEqual(actions[0].action_type, ModerationActionType.PIN_THREAD.value)
        self.assertEqual(
            actions[1].action_type, ModerationActionType.UNPIN_THREAD.value
        )

    def test_pin_permission_denied(self):
        """Test that non-moderators cannot pin conversations."""
        with self.assertRaises(PermissionError) as context:
            self.conversation.pin(self.regular_user)

        self.assertIn("does not have permission to pin", str(context.exception))
        self.assertFalse(self.conversation.is_pinned)

    def test_soft_delete_thread(self):
        """Test soft-deleting a conversation."""
        self.assertIsNone(self.conversation.deleted_at)

        self.conversation.soft_delete_thread(self.moderator_user, reason="Spam content")

        self.conversation.refresh_from_db()
        self.assertIsNotNone(self.conversation.deleted_at)

        # Check audit trail
        action = ModerationAction.objects.get(conversation=self.conversation)
        self.assertEqual(action.action_type, ModerationActionType.DELETE_THREAD.value)
        self.assertEqual(action.moderator, self.moderator_user)
        self.assertEqual(action.reason, "Spam content")

        # Conversation should not appear in default queryset
        self.assertFalse(Conversation.objects.filter(pk=self.conversation.pk).exists())
        # But should appear in all_objects queryset
        self.assertTrue(
            Conversation.all_objects.filter(pk=self.conversation.pk).exists()
        )

    def test_restore_thread(self):
        """Test restoring a soft-deleted conversation."""
        # First soft delete it
        self.conversation.soft_delete_thread(self.moderator_user)
        self.assertIsNotNone(self.conversation.deleted_at)

        # Now restore it
        self.conversation.restore_thread(self.owner, reason="False positive")

        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.deleted_at)

        # Check audit trail shows both actions
        actions = ModerationAction.objects.filter(
            conversation=self.conversation
        ).order_by("created_at")
        self.assertEqual(actions.count(), 2)
        self.assertEqual(
            actions[0].action_type, ModerationActionType.DELETE_THREAD.value
        )
        self.assertEqual(
            actions[1].action_type, ModerationActionType.RESTORE_THREAD.value
        )
        self.assertEqual(actions[1].reason, "False positive")

        # Conversation should appear in default queryset again
        self.assertTrue(Conversation.objects.filter(pk=self.conversation.pk).exists())

    def test_delete_thread_permission_denied(self):
        """Test that non-moderators cannot delete conversations."""
        with self.assertRaises(PermissionError) as context:
            self.conversation.soft_delete_thread(self.regular_user)

        self.assertIn("does not have permission to delete", str(context.exception))
        self.assertIsNone(self.conversation.deleted_at)

    def test_lock_and_pin_together(self):
        """Test that a conversation can be both locked and pinned."""
        self.conversation.lock(self.moderator_user, reason="Rule violation")
        self.conversation.pin(self.owner, reason="Visibility")

        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_locked)
        self.assertTrue(self.conversation.is_pinned)

        # Check audit trail shows both actions
        actions = ModerationAction.objects.filter(
            conversation=self.conversation
        ).order_by("created_at")
        self.assertEqual(actions.count(), 2)


class ChatMessageModerationTest(TestCase):
    """Test moderation actions on ChatMessage model."""

    def setUp(self):
        """Create test users, corpus, conversation, and message."""
        self.owner = User.objects.create_user(username="owner", password="testpass123")
        self.moderator_user = User.objects.create_user(
            username="moderator", password="testpass123"
        )
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test corpus for moderation",
            creator=self.owner,
        )

        self.conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )

        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Test message content",
            creator=self.regular_user,
        )

        # Create a moderator with delete permissions
        self.moderator = CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_user,
            permissions=[
                ModeratorPermissionChoices.DELETE_MESSAGES,
            ],
            creator=self.owner,
        )

    def test_soft_delete_message(self):
        """Test soft-deleting a message."""
        self.assertIsNone(self.message.deleted_at)

        self.message.soft_delete_message(
            self.moderator_user, reason="Inappropriate content"
        )

        self.message.refresh_from_db()
        self.assertIsNotNone(self.message.deleted_at)

        # Check audit trail
        action = ModerationAction.objects.get(message=self.message)
        self.assertEqual(action.action_type, ModerationActionType.DELETE_MESSAGE.value)
        self.assertEqual(action.moderator, self.moderator_user)
        self.assertEqual(action.conversation, self.conversation)
        self.assertEqual(action.reason, "Inappropriate content")

        # Message should not appear in default queryset
        self.assertFalse(ChatMessage.objects.filter(pk=self.message.pk).exists())
        # But should appear in all_objects queryset
        self.assertTrue(ChatMessage.all_objects.filter(pk=self.message.pk).exists())

    def test_restore_message(self):
        """Test restoring a soft-deleted message."""
        # First soft delete it
        self.message.soft_delete_message(self.moderator_user)
        self.assertIsNotNone(self.message.deleted_at)

        # Now restore it
        self.message.restore_message(self.owner, reason="Reinstated")

        self.message.refresh_from_db()
        self.assertIsNone(self.message.deleted_at)

        # Check audit trail shows both actions
        actions = ModerationAction.objects.filter(message=self.message).order_by(
            "created_at"
        )
        self.assertEqual(actions.count(), 2)
        self.assertEqual(
            actions[0].action_type, ModerationActionType.DELETE_MESSAGE.value
        )
        self.assertEqual(
            actions[1].action_type, ModerationActionType.RESTORE_MESSAGE.value
        )
        self.assertEqual(actions[1].reason, "Reinstated")

        # Message should appear in default queryset again
        self.assertTrue(ChatMessage.objects.filter(pk=self.message.pk).exists())

    def test_delete_message_permission_denied(self):
        """Test that non-moderators cannot delete messages."""
        with self.assertRaises(PermissionError) as context:
            self.message.soft_delete_message(self.regular_user)

        self.assertIn("does not have permission to delete", str(context.exception))
        self.assertIsNone(self.message.deleted_at)

    def test_restore_message_permission_denied(self):
        """Test that non-moderators cannot restore messages."""
        # First delete as moderator
        self.message.soft_delete_message(self.moderator_user)

        # Regular user tries to restore
        with self.assertRaises(PermissionError) as context:
            self.message.restore_message(self.regular_user)

        self.assertIn("does not have permission to restore", str(context.exception))
        self.assertIsNotNone(self.message.deleted_at)

    def test_corpus_owner_can_delete_messages(self):
        """Test that corpus owner can delete messages even without CorpusModerator record."""
        self.message.soft_delete_message(self.owner, reason="Owner moderation")

        self.message.refresh_from_db()
        self.assertIsNotNone(self.message.deleted_at)

        # Check audit trail
        action = ModerationAction.objects.get(message=self.message)
        self.assertEqual(action.moderator, self.owner)


class ModerationActionModelTest(TestCase):
    """Test the ModerationAction model and audit trail."""

    def setUp(self):
        """Create test users, corpus, and conversation."""
        self.owner = User.objects.create_user(username="owner", password="testpass123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.owner)
        self.conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )

    def test_moderation_action_str_representation(self):
        """Test the string representation of ModerationAction."""
        action = ModerationAction.objects.create(
            conversation=self.conversation,
            action_type=ModerationActionType.LOCK_THREAD.value,
            moderator=self.owner,
            reason="Test reason",
            creator=self.owner,
        )

        expected = f"lock_thread on conversation {self.conversation.pk} by {self.owner.username}"
        self.assertEqual(str(action), expected)

    def test_moderation_action_ordering(self):
        """Test that moderation actions are ordered by created_at descending."""
        # Create multiple actions
        action1 = ModerationAction.objects.create(
            conversation=self.conversation,
            action_type=ModerationActionType.LOCK_THREAD.value,
            moderator=self.owner,
            creator=self.owner,
        )

        action2 = ModerationAction.objects.create(
            conversation=self.conversation,
            action_type=ModerationActionType.PIN_THREAD.value,
            moderator=self.owner,
            creator=self.owner,
        )

        # Default ordering should be newest first
        actions = ModerationAction.objects.filter(conversation=self.conversation)
        self.assertEqual(actions[0].pk, action2.pk)  # Newest first
        self.assertEqual(actions[1].pk, action1.pk)  # Oldest last

    def test_moderation_action_audit_trail_immutable(self):
        """Test that moderation actions serve as immutable audit trail."""
        ModerationAction.objects.create(
            conversation=self.conversation,
            action_type=ModerationActionType.LOCK_THREAD.value,
            moderator=self.owner,
            reason="Original reason",
            creator=self.owner,
        )

        # Even if we unlock the conversation, the lock action remains in history
        self.conversation.unlock(self.owner)

        # Both actions should exist
        actions = ModerationAction.objects.filter(
            conversation=self.conversation
        ).order_by("created_at")
        self.assertEqual(actions.count(), 2)
        self.assertEqual(actions[0].action_type, ModerationActionType.LOCK_THREAD.value)
        self.assertEqual(
            actions[1].action_type, ModerationActionType.UNLOCK_THREAD.value
        )


class NonCorpusConversationModerationTest(TestCase):
    """Test moderation for conversations not associated with a corpus."""

    def setUp(self):
        """Create test users and document-based conversation."""
        self.creator = User.objects.create_user(
            username="creator", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="other", password="testpass123"
        )

        # Create a conversation without a corpus (e.g., document-based chat)
        self.conversation = Conversation.objects.create(
            title="Document Chat",
            conversation_type=ConversationTypeChoices.CHAT,
            creator=self.creator,
        )

    def test_creator_can_moderate_non_corpus_conversation(self):
        """Test that conversation creator can moderate non-corpus conversations."""
        self.assertTrue(self.conversation.can_moderate(self.creator))

    def test_non_creator_cannot_moderate_non_corpus_conversation(self):
        """Test that non-creators cannot moderate non-corpus conversations."""
        self.assertFalse(self.conversation.can_moderate(self.other_user))

    def test_creator_can_lock_non_corpus_conversation(self):
        """Test that creator can lock their own conversation."""
        self.conversation.lock(self.creator, reason="Personal lock")

        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_locked)

        # Check audit trail
        action = ModerationAction.objects.get(conversation=self.conversation)
        self.assertEqual(action.action_type, ModerationActionType.LOCK_THREAD.value)
        self.assertEqual(action.moderator, self.creator)


class ModerationMutationIDORTest(TestCase):
    """Test IDOR prevention in moderation GraphQL mutations."""

    def setUp(self):
        """Set up test data."""
        from django.contrib.auth import get_user_model
        from graphene.test import Client

        from config.graphql.schema import schema

        User = get_user_model()

        self.owner = User.objects.create_user(
            username="corpus_owner",
            password="testpass123",
            email="owner@test.com",
        )

        self.other_user = User.objects.create_user(
            username="other_user",
            password="testpass123",
            email="other@test.com",
        )

        self.moderator_user = User.objects.create_user(
            username="moderator",
            password="testpass123",
            email="mod@test.com",
        )

        # Create a private corpus owned by owner
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            description="Private",
            creator=self.owner,
            is_public=False,
        )

        self.client = Client(schema)

    def test_add_moderator_idor_prevention(self):
        """Test that AddModeratorMutation prevents corpus enumeration."""
        from graphql_relay import to_global_id

        corpus_global_id = to_global_id("CorpusType", self.private_corpus.id)
        user_global_id = to_global_id("UserType", self.moderator_user.id)

        # Try to add moderator to corpus owned by someone else
        mutation = f"""
            mutation AddModerator {{
                addModerator(
                    corpusId: "{corpus_global_id}"
                    userId: "{user_global_id}"
                    permissions: ["lock_threads", "pin_threads"]
                ) {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.other_user})(),
        )

        # Should get "Corpus not found" error, NOT "Only corpus owners can add moderators"
        # This prevents enumeration - same error whether corpus doesn't exist or user lacks permission
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["addModerator"]["ok"])
        self.assertEqual(result["data"]["addModerator"]["message"], "Corpus not found")

        # Now try with a non-existent corpus ID
        fake_corpus_global_id = to_global_id("CorpusType", 999999)
        mutation_fake = f"""
            mutation AddModerator {{
                addModerator(
                    corpusId: "{fake_corpus_global_id}"
                    userId: "{user_global_id}"
                    permissions: ["lock_threads"]
                ) {{
                    ok
                    message
                }}
            }}
        """

        result_fake = self.client.execute(
            mutation_fake,
            context_value=type("Request", (), {"user": self.other_user})(),
        )

        # Should get the SAME error message
        self.assertIsNone(result_fake.get("errors"))
        self.assertFalse(result_fake["data"]["addModerator"]["ok"])
        self.assertEqual(
            result_fake["data"]["addModerator"]["message"], "Corpus not found"
        )

    def test_remove_moderator_idor_prevention(self):
        """Test that RemoveModeratorMutation prevents corpus enumeration."""
        from graphql_relay import to_global_id

        from opencontractserver.conversations.models import CorpusModerator

        # First add a moderator (as owner)
        CorpusModerator.objects.create(
            corpus=self.private_corpus,
            user=self.moderator_user,
            assigned_by=self.owner,
            creator=self.owner,
            permissions=["lock_threads"],
        )

        corpus_global_id = to_global_id("CorpusType", self.private_corpus.id)
        user_global_id = to_global_id("UserType", self.moderator_user.id)

        # Try to remove moderator from corpus owned by someone else
        mutation = f"""
            mutation RemoveModerator {{
                removeModerator(
                    corpusId: "{corpus_global_id}"
                    userId: "{user_global_id}"
                ) {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.other_user})(),
        )

        # Should get "Corpus not found" error
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["removeModerator"]["ok"])
        self.assertEqual(
            result["data"]["removeModerator"]["message"], "Corpus not found"
        )

    def test_update_moderator_permissions_idor_prevention(self):
        """Test that UpdateModeratorPermissionsMutation prevents corpus enumeration."""
        from graphql_relay import to_global_id

        from opencontractserver.conversations.models import CorpusModerator

        # First add a moderator (as owner)
        CorpusModerator.objects.create(
            corpus=self.private_corpus,
            user=self.moderator_user,
            assigned_by=self.owner,
            creator=self.owner,
            permissions=["lock_threads"],
        )

        corpus_global_id = to_global_id("CorpusType", self.private_corpus.id)
        user_global_id = to_global_id("UserType", self.moderator_user.id)

        # Try to update moderator permissions for corpus owned by someone else
        mutation = f"""
            mutation UpdateModeratorPermissions {{
                updateModeratorPermissions(
                    corpusId: "{corpus_global_id}"
                    userId: "{user_global_id}"
                    permissions: ["lock_threads", "pin_threads", "delete_messages"]
                ) {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.other_user})(),
        )

        # Should get "Corpus not found" error
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateModeratorPermissions"]["ok"])
        self.assertEqual(
            result["data"]["updateModeratorPermissions"]["message"], "Corpus not found"
        )


class DeleteRestoreThreadMutationTest(TestCase):
    """Test DeleteThread and RestoreThread mutations."""

    def setUp(self):
        """Set up test data."""
        from graphene.test import Client

        from config.graphql.schema import schema

        self.owner = User.objects.create_user(
            username="thread_owner",
            password="testpass123",
            email="owner@test.com",
        )
        self.other_user = User.objects.create_user(
            username="other_user",
            password="testpass123",
            email="other@test.com",
        )
        self.moderator_user = User.objects.create_user(
            username="thread_mod",
            password="testpass123",
            email="mod@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.owner,
            is_public=False,
        )

        self.conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )

        # Add moderator with delete permissions
        CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_user,
            permissions=["delete_threads"],
            creator=self.owner,
        )

        self.client = Client(schema)

    def test_delete_thread_mutation(self):
        """Test deleting a thread via GraphQL mutation."""
        from graphql_relay import to_global_id

        conv_global_id = to_global_id("ConversationType", self.conversation.id)

        mutation = f"""
            mutation DeleteThread {{
                deleteThread(
                    conversationId: "{conv_global_id}"
                    reason: "Test deletion"
                ) {{
                    ok
                    message
                    conversation {{
                        id
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.moderator_user})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteThread"]["ok"])
        self.assertEqual(
            result["data"]["deleteThread"]["message"], "Thread deleted successfully"
        )

        # Verify thread is soft-deleted
        self.conversation.refresh_from_db()
        self.assertIsNotNone(self.conversation.deleted_at)

        # Verify moderation action was created
        action = ModerationAction.objects.filter(
            conversation=self.conversation,
            action_type=ModerationActionType.DELETE_THREAD.value,
        ).first()
        self.assertIsNotNone(action)
        self.assertEqual(action.reason, "Test deletion")

    def test_delete_thread_permission_denied(self):
        """Test that non-moderators cannot delete threads."""
        from graphql_relay import to_global_id

        conv_global_id = to_global_id("ConversationType", self.conversation.id)

        mutation = f"""
            mutation DeleteThread {{
                deleteThread(conversationId: "{conv_global_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.other_user})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["deleteThread"]["ok"])
        self.assertEqual(
            result["data"]["deleteThread"]["message"],
            "Thread not found or access denied",
        )

    def test_restore_thread_mutation(self):
        """Test restoring a deleted thread via GraphQL mutation."""
        from graphql_relay import to_global_id

        # First delete the thread
        self.conversation.soft_delete_thread(self.owner)
        self.assertIsNotNone(self.conversation.deleted_at)

        conv_global_id = to_global_id("ConversationType", self.conversation.id)

        mutation = f"""
            mutation RestoreThread {{
                restoreThread(
                    conversationId: "{conv_global_id}"
                    reason: "Restored after review"
                ) {{
                    ok
                    message
                    conversation {{
                        id
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["restoreThread"]["ok"])
        self.assertEqual(
            result["data"]["restoreThread"]["message"], "Thread restored successfully"
        )

        # Verify thread is restored
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.deleted_at)


class RollbackModerationActionMutationTest(TestCase):
    """Test RollbackModerationAction mutation."""

    def setUp(self):
        """Set up test data."""
        from graphene.test import Client

        from config.graphql.schema import schema

        self.owner = User.objects.create_user(
            username="rollback_owner",
            password="testpass123",
            email="rollback@test.com",
        )
        self.other_user = User.objects.create_user(
            username="rollback_other",
            password="testpass123",
            email="other@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Rollback Test Corpus",
            creator=self.owner,
        )

        self.conversation = Conversation.objects.create(
            title="Rollback Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )

        self.client = Client(schema)

    def test_rollback_lock_action(self):
        """Test rolling back a lock action unlocks the thread."""
        from graphql_relay import to_global_id

        # Lock the thread
        lock_action = self.conversation.lock(self.owner, reason="Locked for test")
        self.assertTrue(self.conversation.is_locked)

        action_global_id = to_global_id("ModerationActionType", lock_action.id)

        mutation = f"""
            mutation RollbackAction {{
                rollbackModerationAction(
                    actionId: "{action_global_id}"
                    reason: "Rolling back lock"
                ) {{
                    ok
                    message
                    rollbackAction {{
                        id
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["rollbackModerationAction"]["ok"])
        self.assertIn(
            "Successfully rolled back",
            result["data"]["rollbackModerationAction"]["message"],
        )

        # Verify thread is unlocked
        self.conversation.refresh_from_db()
        self.assertFalse(self.conversation.is_locked)

        # Verify rollback action was created
        self.assertIsNotNone(
            result["data"]["rollbackModerationAction"]["rollbackAction"]
        )

    def test_rollback_pin_action(self):
        """Test rolling back a pin action unpins the thread."""
        from graphql_relay import to_global_id

        # Pin the thread
        pin_action = self.conversation.pin(self.owner, reason="Pinned for test")
        self.assertTrue(self.conversation.is_pinned)

        action_global_id = to_global_id("ModerationActionType", pin_action.id)

        mutation = f"""
            mutation RollbackAction {{
                rollbackModerationAction(actionId: "{action_global_id}") {{
                    ok
                    message
                    rollbackAction {{
                        id
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["rollbackModerationAction"]["ok"])

        # Verify thread is unpinned
        self.conversation.refresh_from_db()
        self.assertFalse(self.conversation.is_pinned)

        # Verify rollback action was created
        self.assertIsNotNone(
            result["data"]["rollbackModerationAction"]["rollbackAction"]
        )

    def test_rollback_delete_thread_action(self):
        """Test rolling back a delete action restores the thread."""
        from graphql_relay import to_global_id

        # Delete the thread
        delete_action = self.conversation.soft_delete_thread(
            self.owner, reason="Deleted for test"
        )
        self.assertIsNotNone(self.conversation.deleted_at)

        action_global_id = to_global_id("ModerationActionType", delete_action.id)

        mutation = f"""
            mutation RollbackAction {{
                rollbackModerationAction(actionId: "{action_global_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["rollbackModerationAction"]["ok"])

        # Verify thread is restored
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.deleted_at)

    def test_rollback_non_rollbackable_action(self):
        """Test that already-rolled-back actions cannot be rolled back."""
        from graphql_relay import to_global_id

        # Create an unlock action (which is a rollback of lock, not rollbackable itself)
        self.conversation.lock(self.owner)
        unlock_action = self.conversation.unlock(self.owner)

        action_global_id = to_global_id("ModerationActionType", unlock_action.id)

        mutation = f"""
            mutation RollbackAction {{
                rollbackModerationAction(actionId: "{action_global_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["rollbackModerationAction"]["ok"])
        self.assertIn(
            "cannot be rolled back",
            result["data"]["rollbackModerationAction"]["message"],
        )

    def test_rollback_permission_denied(self):
        """Test that non-moderators cannot rollback actions."""
        from graphql_relay import to_global_id

        lock_action = self.conversation.lock(self.owner)
        action_global_id = to_global_id("ModerationActionType", lock_action.id)

        mutation = f"""
            mutation RollbackAction {{
                rollbackModerationAction(actionId: "{action_global_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.other_user})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["rollbackModerationAction"]["ok"])
        self.assertIn(
            "permission",
            result["data"]["rollbackModerationAction"]["message"].lower(),
        )

    def test_rollback_nonexistent_action(self):
        """Test rolling back a non-existent action."""
        from graphql_relay import to_global_id

        fake_action_id = to_global_id("ModerationActionType", 999999)

        mutation = f"""
            mutation RollbackAction {{
                rollbackModerationAction(actionId: "{fake_action_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["rollbackModerationAction"]["ok"])
        self.assertIn(
            "not found", result["data"]["rollbackModerationAction"]["message"]
        )


class ModerationQueriesTest(TestCase):
    """Test moderation-related GraphQL queries."""

    def setUp(self):
        """Set up test data."""
        from graphene.test import Client

        from config.graphql.schema import schema

        self.owner = User.objects.create_user(
            username="queries_owner",
            password="testpass123",
            email="queries@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Queries Test Corpus",
            creator=self.owner,
        )

        self.conversation = Conversation.objects.create(
            title="Queries Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )

        # Create some moderation actions
        self.lock_action = self.conversation.lock(self.owner, reason="Lock reason")
        self.pin_action = self.conversation.pin(self.owner, reason="Pin reason")

        self.client = Client(schema)

    def test_moderation_actions_query(self):
        """Test querying moderation actions for a corpus."""
        from graphql_relay import to_global_id

        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = f"""
            query ModerationActions {{
                moderationActions(corpusId: "{corpus_global_id}", first: 10) {{
                    edges {{
                        node {{
                            id
                            actionType
                            reason
                            moderator {{
                                username
                            }}
                        }}
                    }}
                }}
            }}
        """

        result = self.client.execute(
            query,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["moderationActions"]["edges"]
        self.assertEqual(len(edges), 2)

        action_types = [edge["node"]["actionType"] for edge in edges]
        self.assertIn("LOCK_THREAD", action_types)
        self.assertIn("PIN_THREAD", action_types)

    def test_moderation_action_query(self):
        """Test querying a single moderation action by ID."""
        from graphql_relay import to_global_id

        action_global_id = to_global_id("ModerationActionType", self.lock_action.id)

        query = f"""
            query ModerationAction {{
                moderationAction(id: "{action_global_id}") {{
                    id
                    actionType
                    reason
                    canRollback
                }}
            }}
        """

        result = self.client.execute(
            query,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        action = result["data"]["moderationAction"]
        self.assertIsNotNone(action)
        self.assertEqual(action["actionType"], "LOCK_THREAD")
        self.assertEqual(action["reason"], "Lock reason")
        self.assertTrue(action["canRollback"])

    def test_moderation_metrics_query(self):
        """Test querying moderation metrics for a corpus."""
        from graphql_relay import to_global_id

        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = f"""
            query ModerationMetrics {{
                moderationMetrics(corpusId: "{corpus_global_id}", timeRangeHours: 24) {{
                    totalActions
                    automatedActions
                    manualActions
                    hourlyActionRate
                    isAboveThreshold
                    thresholdExceededTypes
                }}
            }}
        """

        result = self.client.execute(
            query,
            context_value=type("Request", (), {"user": self.owner})(),
        )

        self.assertIsNone(result.get("errors"))
        metrics = result["data"]["moderationMetrics"]
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["totalActions"], 2)
        self.assertEqual(metrics["manualActions"], 2)
        self.assertEqual(metrics["automatedActions"], 0)


class ResolveModerationActionAuthGateTest(TestCase):
    """Pin authorization for the single-action ``moderationAction`` resolver.

    Regression coverage for #1594: the resolver previously short-circuited
    to ``return action`` whenever ``conversation.chat_with_corpus`` was
    ``None``, leaking document-only and orphaned moderation actions to any
    authenticated user. The resolver now routes every case through
    :meth:`Conversation.can_moderate`.
    """

    def setUp(self):
        from graphene.test import Client

        from config.graphql.schema import schema
        from opencontractserver.documents.models import Document

        # Cast of users covering each branch of ``can_moderate``.
        self.corpus_owner = User.objects.create_user(
            username="auth_gate_corpus_owner", password="pw"
        )
        self.corpus_moderator = User.objects.create_user(
            username="auth_gate_corpus_moderator", password="pw"
        )
        self.doc_owner = User.objects.create_user(
            username="auth_gate_doc_owner", password="pw"
        )
        self.thread_creator = User.objects.create_user(
            username="auth_gate_thread_creator", password="pw"
        )
        self.unrelated = User.objects.create_user(
            username="auth_gate_unrelated", password="pw"
        )
        self.superuser = User.objects.create_superuser(
            username="auth_gate_superuser",
            password="pw",
            email="auth_gate_superuser@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Auth Gate Corpus", creator=self.corpus_owner
        )
        CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.corpus_moderator,
            creator=self.corpus_owner,
            permissions=[ModeratorPermissionChoices.LOCK_THREADS.value],
        )

        # Two parallel conversations: corpus-attached and document-only.
        self.corpus_conversation = Conversation.objects.create(
            title="Auth Gate Corpus Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.thread_creator,
        )
        self.corpus_action = self.corpus_conversation.lock(self.corpus_owner)

        self.document = Document.objects.create(
            title="Auth Gate Doc",
            creator=self.doc_owner,
            file_type="application/pdf",
        )
        self.doc_only_conversation = Conversation.objects.create(
            title="Auth Gate Doc-only Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_document=self.document,
            creator=self.thread_creator,
        )
        self.doc_only_action = self.doc_only_conversation.lock(self.doc_owner)

        self.client = Client(schema)

    def _query(self, action_pk: int, user) -> dict:
        from graphql_relay import to_global_id

        action_global_id = to_global_id("ModerationActionType", action_pk)
        return self.client.execute(
            f"""
            query {{
                moderationAction(id: "{action_global_id}") {{
                    id
                    actionType
                }}
            }}
            """,
            context_value=type("Request", (), {"user": user})(),
        )

    def _assert_visible(self, action_pk: int, user) -> None:
        result = self._query(action_pk, user)
        self.assertIsNone(result.get("errors"))
        self.assertIsNotNone(
            result["data"]["moderationAction"],
            f"User {user.username!r} should see action {action_pk}",
        )

    def _assert_hidden(self, action_pk: int, user) -> None:
        result = self._query(action_pk, user)
        self.assertIsNone(result.get("errors"))
        self.assertIsNone(
            result["data"]["moderationAction"],
            f"User {user.username!r} must NOT see action {action_pk}",
        )

    # ------- corpus-attached conversation -------

    def test_corpus_owner_sees_corpus_action(self):
        self._assert_visible(self.corpus_action.pk, self.corpus_owner)

    def test_corpus_moderator_sees_corpus_action(self):
        self._assert_visible(self.corpus_action.pk, self.corpus_moderator)

    def test_thread_creator_sees_corpus_action(self):
        # Conversation creator gets moderation rights independent of corpus.
        self._assert_visible(self.corpus_action.pk, self.thread_creator)

    def test_unrelated_user_cannot_see_corpus_action(self):
        self._assert_hidden(self.corpus_action.pk, self.unrelated)

    def test_superuser_sees_corpus_action(self):
        self._assert_visible(self.corpus_action.pk, self.superuser)

    # ------- document-only conversation (regression for #1594) -------

    def test_doc_owner_sees_doc_only_action(self):
        self._assert_visible(self.doc_only_action.pk, self.doc_owner)

    def test_thread_creator_sees_doc_only_action(self):
        self._assert_visible(self.doc_only_action.pk, self.thread_creator)

    def test_superuser_sees_doc_only_action(self):
        self._assert_visible(self.doc_only_action.pk, self.superuser)

    def test_unrelated_user_cannot_see_doc_only_action(self):
        # Pre-fix this returned the action because chat_with_corpus was None
        # and the resolver fell through. Pin the closure so the leak doesn't
        # silently come back.
        self._assert_hidden(self.doc_only_action.pk, self.unrelated)

    def test_corpus_owner_cannot_see_unrelated_doc_only_action(self):
        # An unrelated corpus owner has no claim on a document-only thread
        # — confirms the gate doesn't accidentally widen to "any moderator
        # of any corpus".
        self._assert_hidden(self.doc_only_action.pk, self.corpus_owner)

    # ------- orphaned action (conversation FK is NULL) -------

    def test_orphaned_action_visible_only_to_superuser(self):
        # ``conversation`` is a nullable FK on ModerationAction. Pin that
        # the resolver fails closed for non-superusers in this edge case
        # rather than re-opening the leak.
        orphaned = ModerationAction.objects.create(
            conversation=None,
            action_type=ModerationActionType.LOCK_THREAD.value,
            reason="orphan",
            moderator=self.corpus_owner,
            creator=self.corpus_owner,
        )
        self._assert_hidden(orphaned.pk, self.corpus_owner)
        self._assert_hidden(orphaned.pk, self.thread_creator)
        self._assert_hidden(orphaned.pk, self.unrelated)
        self._assert_visible(orphaned.pk, self.superuser)


class ModerationMethodReturnValueTest(TestCase):
    """Test that moderation methods return the created ModerationAction."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(
            username="return_owner",
            password="testpass123",
        )
        self.corpus = Corpus.objects.create(
            title="Return Test Corpus",
            creator=self.owner,
        )
        self.conversation = Conversation.objects.create(
            title="Return Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )

    def test_lock_returns_moderation_action(self):
        """Test that lock() returns the created ModerationAction."""
        action = self.conversation.lock(self.owner, reason="Test lock")

        self.assertIsInstance(action, ModerationAction)
        self.assertEqual(action.action_type, ModerationActionType.LOCK_THREAD.value)
        self.assertEqual(action.moderator, self.owner)
        self.assertEqual(action.reason, "Test lock")

    def test_unlock_returns_moderation_action(self):
        """Test that unlock() returns the created ModerationAction."""
        self.conversation.lock(self.owner)
        action = self.conversation.unlock(self.owner, reason="Test unlock")

        self.assertIsInstance(action, ModerationAction)
        self.assertEqual(action.action_type, ModerationActionType.UNLOCK_THREAD.value)

    def test_pin_returns_moderation_action(self):
        """Test that pin() returns the created ModerationAction."""
        action = self.conversation.pin(self.owner, reason="Test pin")

        self.assertIsInstance(action, ModerationAction)
        self.assertEqual(action.action_type, ModerationActionType.PIN_THREAD.value)

    def test_unpin_returns_moderation_action(self):
        """Test that unpin() returns the created ModerationAction."""
        self.conversation.pin(self.owner)
        action = self.conversation.unpin(self.owner, reason="Test unpin")

        self.assertIsInstance(action, ModerationAction)
        self.assertEqual(action.action_type, ModerationActionType.UNPIN_THREAD.value)

    def test_soft_delete_thread_returns_moderation_action(self):
        """Test that soft_delete_thread() returns the created ModerationAction."""
        action = self.conversation.soft_delete_thread(self.owner, reason="Test delete")

        self.assertIsInstance(action, ModerationAction)
        self.assertEqual(action.action_type, ModerationActionType.DELETE_THREAD.value)

    def test_restore_thread_returns_moderation_action(self):
        """Test that restore_thread() returns the created ModerationAction."""
        self.conversation.soft_delete_thread(self.owner)
        action = self.conversation.restore_thread(self.owner, reason="Test restore")

        self.assertIsInstance(action, ModerationAction)
        self.assertEqual(action.action_type, ModerationActionType.RESTORE_THREAD.value)

    def test_soft_delete_message_returns_moderation_action(self):
        """Test that soft_delete_message() returns the created ModerationAction."""
        from opencontractserver.conversations.models import ChatMessage

        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Test message",
            creator=self.owner,
        )

        action = message.soft_delete_message(self.owner, reason="Test delete message")

        self.assertIsInstance(action, ModerationAction)
        self.assertEqual(action.action_type, ModerationActionType.DELETE_MESSAGE.value)

    def test_restore_message_returns_moderation_action(self):
        """Test that restore_message() returns the created ModerationAction."""
        from opencontractserver.conversations.models import ChatMessage

        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Test message",
            creator=self.owner,
        )
        message.soft_delete_message(self.owner)
        action = message.restore_message(self.owner, reason="Test restore message")

        self.assertIsInstance(action, ModerationAction)
        self.assertEqual(action.action_type, ModerationActionType.RESTORE_MESSAGE.value)


class ModerationActionStrTest(TestCase):
    """
    Tests for ModerationAction.__str__ covering all branches introduced by the
    defensive guard that replaced the bare ``assert self.message is not None``.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="str_owner", password="pw")
        self.corpus = Corpus.objects.create(title="Str Corpus", creator=self.owner)
        self.conversation = Conversation.objects.create(
            title="Str Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )
        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Hello",
            creator=self.owner,
        )

    def test_str_with_conversation_set(self):
        """__str__ uses conversation pk when conversation is set."""
        action = ModerationAction.objects.create(
            conversation=self.conversation,
            action_type=ModerationActionType.LOCK_THREAD.value,
            moderator=self.owner,
            creator=self.owner,
        )
        expected = f"lock_thread on conversation {self.conversation.pk} by {self.owner.username}"
        self.assertEqual(str(action), expected)

    def test_str_with_message_set_and_no_conversation(self):
        """__str__ uses message pk when only message is set (normal moderated-message path)."""
        action = ModerationAction.objects.create(
            message=self.message,
            conversation=self.conversation,
            action_type=ModerationActionType.DELETE_MESSAGE.value,
            moderator=self.owner,
            creator=self.owner,
        )
        # conversation is set, so conversation branch wins
        self.assertIn(f"conversation {self.conversation.pk}", str(action))

        # Now force the message-only path by using update() to clear conversation
        ModerationAction.objects.filter(pk=action.pk).update(conversation=None)
        action.refresh_from_db()
        expected = (
            f"delete_message on message {self.message.pk} by {self.owner.username}"
        )
        self.assertEqual(str(action), expected)

    def test_str_with_both_none_falls_back_to_unknown_target(self):
        """__str__ returns 'unknown target' when both conversation and message are None."""
        action = ModerationAction.objects.create(
            conversation=self.conversation,
            action_type=ModerationActionType.LOCK_THREAD.value,
            moderator=self.owner,
            creator=self.owner,
        )
        # Bypass construction invariant via update() to exercise the defensive branch
        ModerationAction.objects.filter(pk=action.pk).update(
            conversation=None, message=None
        )
        action.refresh_from_db()
        self.assertIn("unknown target", str(action))

    def test_str_with_no_moderator(self):
        """__str__ shows 'Unknown' when moderator is None."""
        action = ModerationAction.objects.create(
            conversation=self.conversation,
            action_type=ModerationActionType.LOCK_THREAD.value,
            moderator=None,
            creator=self.owner,
        )
        self.assertIn("by Unknown", str(action))


class ManagerVisibleToUserNoneTest(TestCase):
    """
    Tests for the user=None path through ConversationManager and
    ChatMessageManager to ensure anonymous visibility is correct and
    that the lightweight / with_doc_label_annotations kwargs are accepted
    by all manager overrides without raising TypeError.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="mgr_owner", password="pw")
        self.corpus = Corpus.objects.create(
            title="Mgr Corpus", creator=self.owner, is_public=True
        )
        self.public_conv = Conversation.objects.create(
            title="Public Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.owner,
            is_public=True,
        )
        self.private_conv = Conversation.objects.create(
            title="Private Chat",
            conversation_type=ConversationTypeChoices.CHAT,
            creator=self.owner,
            is_public=False,
        )

    def test_conversation_manager_visible_to_user_none(self):
        """Passing user=None treats the caller as anonymous."""
        qs = Conversation.objects.visible_to_user(user=None)
        pks = list(qs.values_list("pk", flat=True))
        # Public THREAD on public corpus should be visible to anonymous
        self.assertIn(self.public_conv.pk, pks)
        # Private CHAT should NOT be visible to anonymous
        self.assertNotIn(self.private_conv.pk, pks)

    def test_conversation_manager_visible_to_user_accepts_lightweight_kwarg(self):
        """ConversationManager.visible_to_user must accept lightweight= without TypeError."""
        qs = Conversation.objects.visible_to_user(user=self.owner, lightweight=True)
        self.assertIsNotNone(qs)

    def test_conversation_manager_visible_to_user_accepts_doc_label_annotations_kwarg(
        self,
    ):
        """ConversationManager.visible_to_user accepts with_doc_label_annotations=."""
        qs = Conversation.objects.visible_to_user(
            user=self.owner, with_doc_label_annotations=True
        )
        self.assertIsNotNone(qs)

    def test_chat_message_manager_visible_to_user_none(self):
        """ChatMessageManager.visible_to_user(user=None) returns only
        messages whose parent conversation the anonymous caller can see.

        Symmetric assertions confirm a public-conversation message IS
        visible AND a private-conversation message is NOT visible — the
        latter mirrors what test_conversation_manager_visible_to_user_none
        pins for the conversation manager itself.
        """
        public_msg = ChatMessage.objects.create(
            conversation=self.public_conv,
            msg_type="HUMAN",
            content="Hello world",
            creator=self.owner,
        )
        private_msg = ChatMessage.objects.create(
            conversation=self.private_conv,
            msg_type="HUMAN",
            content="Secret",
            creator=self.owner,
        )
        qs = ChatMessage.objects.visible_to_user(user=None)
        pks = list(qs.values_list("pk", flat=True))
        # Public conversation's message is visible to anonymous
        self.assertIn(public_msg.pk, pks)
        # Private conversation's message is NOT visible to anonymous
        self.assertNotIn(private_msg.pk, pks)

    def test_chat_message_manager_visible_to_user_accepts_kwargs(self):
        """ChatMessageManager.visible_to_user accepts lightweight= and with_doc_label_annotations=."""
        qs = ChatMessage.objects.visible_to_user(
            user=self.owner, lightweight=True, with_doc_label_annotations=False
        )
        self.assertIsNotNone(qs)
