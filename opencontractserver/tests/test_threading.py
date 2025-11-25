"""
Tests for discussion threading functionality in OpenContracts.

This module tests Epic #546: Discussion Threads - Core Threading & Agent Type Support

Tests cover:
1. Conversation types (CHAT vs THREAD)
2. Agent type tracking on messages
3. Parent-child message relationships (nested replies)
4. Soft delete functionality for conversations and messages
5. Custom manager behavior (objects vs all_objects)
6. Backward compatibility with existing chat conversations
7. Thread depth and nested reply structures
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from opencontractserver.conversations.models import (
    AgentTypeChoices,
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
)
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class TestConversationTypes(TestCase):
    """Test conversation type functionality (CHAT vs THREAD)."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="thread_testuser",
            password="testpass123",
            email="thread@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Thread Corpus",
            description="A corpus for testing threads",
            creator=cls.user,
            is_public=True,
        )

    def test_default_conversation_type_is_chat(self):
        """Test that conversations default to CHAT type for backward compatibility."""
        conversation = Conversation.objects.create(
            title="Default Conversation",
            creator=self.user,
            chat_with_corpus=self.corpus,
        )

        self.assertEqual(conversation.conversation_type, ConversationTypeChoices.CHAT)

    def test_create_thread_conversation(self):
        """Test creating a THREAD type conversation."""
        conversation = Conversation.objects.create(
            title="Discussion Thread",
            description="A discussion about documents",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.user,
            chat_with_corpus=self.corpus,
        )

        self.assertEqual(conversation.conversation_type, ConversationTypeChoices.THREAD)
        self.assertEqual(conversation.title, "Discussion Thread")

    def test_chat_vs_thread_distinction(self):
        """Test that we can distinguish between chats and threads."""
        chat = Conversation.objects.create(
            title="Agent Chat",
            conversation_type=ConversationTypeChoices.CHAT,
            creator=self.user,
        )

        thread = Conversation.objects.create(
            title="Discussion Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.user,
        )

        chat_conversations = Conversation.objects.filter(
            conversation_type=ConversationTypeChoices.CHAT
        )
        thread_conversations = Conversation.objects.filter(
            conversation_type=ConversationTypeChoices.THREAD
        )

        self.assertIn(chat, chat_conversations)
        self.assertNotIn(chat, thread_conversations)
        self.assertIn(thread, thread_conversations)
        self.assertNotIn(thread, chat_conversations)


class TestAgentTypes(TestCase):
    """Test agent type tracking on messages."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="agent_testuser",
            password="testpass123",
            email="agent@test.com",
        )

        cls.conversation = Conversation.objects.create(
            title="Agent Test Conversation",
            creator=cls.user,
        )

    def test_human_message_without_agent_type(self):
        """Test that human messages don't require an agent type."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Hello, agent!",
            creator=self.user,
        )

        self.assertIsNone(message.agent_type)

    def test_document_agent_message(self):
        """Test creating a message from a document agent."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="LLM",
            agent_type=AgentTypeChoices.DOCUMENT_AGENT,
            content="I analyzed the document.",
            creator=self.user,
        )

        self.assertEqual(message.agent_type, AgentTypeChoices.DOCUMENT_AGENT)
        self.assertEqual(message.msg_type, "LLM")

    def test_corpus_agent_message(self):
        """Test creating a message from a corpus agent."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="LLM",
            agent_type=AgentTypeChoices.CORPUS_AGENT,
            content="I searched the corpus.",
            creator=self.user,
        )

        self.assertEqual(message.agent_type, AgentTypeChoices.CORPUS_AGENT)
        self.assertEqual(message.msg_type, "LLM")

    def test_filter_messages_by_agent_type(self):
        """Test filtering messages by agent type."""
        ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="LLM",
            agent_type=AgentTypeChoices.DOCUMENT_AGENT,
            content="Document agent message",
            creator=self.user,
        )

        ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="LLM",
            agent_type=AgentTypeChoices.CORPUS_AGENT,
            content="Corpus agent message",
            creator=self.user,
        )

        ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Human message",
            creator=self.user,
        )

        doc_messages = ChatMessage.objects.filter(
            agent_type=AgentTypeChoices.DOCUMENT_AGENT
        )
        corpus_messages = ChatMessage.objects.filter(
            agent_type=AgentTypeChoices.CORPUS_AGENT
        )
        human_messages = ChatMessage.objects.filter(agent_type__isnull=True)

        self.assertEqual(doc_messages.count(), 1)
        self.assertEqual(corpus_messages.count(), 1)
        self.assertEqual(human_messages.count(), 1)


class TestThreadedReplies(TestCase):
    """Test parent-child message relationships for nested replies."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="reply_testuser",
            password="testpass123",
            email="reply@test.com",
        )

        cls.thread = Conversation.objects.create(
            title="Discussion Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=cls.user,
        )

    def test_create_root_message(self):
        """Test creating a root message without a parent."""
        message = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="This is a root message",
            creator=self.user,
        )

        self.assertIsNone(message.parent_message)
        self.assertEqual(message.replies.count(), 0)

    def test_create_reply_to_message(self):
        """Test creating a reply to an existing message."""
        parent = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Parent message",
            creator=self.user,
        )

        reply = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Reply to parent",
            parent_message=parent,
            creator=self.user,
        )

        self.assertEqual(reply.parent_message, parent)
        self.assertEqual(parent.replies.count(), 1)
        self.assertIn(reply, parent.replies.all())

    def test_nested_reply_depth(self):
        """Test creating nested replies (multiple levels deep)."""
        # Create a chain: root -> reply1 -> reply2 -> reply3
        root = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Root message",
            creator=self.user,
        )

        reply1 = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Reply level 1",
            parent_message=root,
            creator=self.user,
        )

        reply2 = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Reply level 2",
            parent_message=reply1,
            creator=self.user,
        )

        reply3 = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Reply level 3",
            parent_message=reply2,
            creator=self.user,
        )

        # Verify the chain
        self.assertEqual(reply1.parent_message, root)
        self.assertEqual(reply2.parent_message, reply1)
        self.assertEqual(reply3.parent_message, reply2)

        # Verify reply counts
        self.assertEqual(root.replies.count(), 1)
        self.assertEqual(reply1.replies.count(), 1)
        self.assertEqual(reply2.replies.count(), 1)
        self.assertEqual(reply3.replies.count(), 0)

    def test_multiple_replies_to_same_parent(self):
        """Test that a message can have multiple direct replies."""
        parent = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Parent message",
            creator=self.user,
        )

        reply1 = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="First reply",
            parent_message=parent,
            creator=self.user,
        )

        reply2 = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Second reply",
            parent_message=parent,
            creator=self.user,
        )

        reply3 = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Third reply",
            parent_message=parent,
            creator=self.user,
        )

        self.assertEqual(parent.replies.count(), 3)
        self.assertIn(reply1, parent.replies.all())
        self.assertIn(reply2, parent.replies.all())
        self.assertIn(reply3, parent.replies.all())

    def test_cascade_delete_replies(self):
        """Test that deleting a parent message cascades to replies."""
        parent = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Parent message",
            creator=self.user,
        )

        reply1 = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="First reply",
            parent_message=parent,
            creator=self.user,
        )

        reply2 = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Second reply",
            parent_message=reply1,
            creator=self.user,
        )

        parent_id = parent.id
        reply1_id = reply1.id
        reply2_id = reply2.id

        # Hard delete the parent (not soft delete)
        parent_obj = ChatMessage.all_objects.get(id=parent_id)
        parent_obj.delete()

        # Verify all messages in the chain are deleted
        self.assertFalse(ChatMessage.all_objects.filter(id=parent_id).exists())
        self.assertFalse(ChatMessage.all_objects.filter(id=reply1_id).exists())
        self.assertFalse(ChatMessage.all_objects.filter(id=reply2_id).exists())


class TestSoftDelete(TestCase):
    """Test soft delete functionality for conversations and messages."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="softdelete_testuser",
            password="testpass123",
            email="softdelete@test.com",
        )

    def test_soft_delete_conversation(self):
        """Test soft deleting a conversation."""
        conversation = Conversation.objects.create(
            title="Test Conversation",
            creator=self.user,
        )

        conversation_id = conversation.id

        # Soft delete by setting deleted_at
        conversation.deleted_at = timezone.now()
        conversation.save()

        # Verify it's excluded from default manager
        self.assertFalse(Conversation.objects.filter(id=conversation_id).exists())

        # Verify it's accessible via all_objects manager
        self.assertTrue(Conversation.all_objects.filter(id=conversation_id).exists())

    def test_soft_delete_message(self):
        """Test soft deleting a message."""
        conversation = Conversation.objects.create(
            title="Test Conversation",
            creator=self.user,
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Test message",
            creator=self.user,
        )

        message_id = message.id

        # Soft delete by setting deleted_at
        message.deleted_at = timezone.now()
        message.save()

        # Verify it's excluded from default manager
        self.assertFalse(ChatMessage.objects.filter(id=message_id).exists())

        # Verify it's accessible via all_objects manager
        self.assertTrue(ChatMessage.all_objects.filter(id=message_id).exists())

    def test_manager_excludes_soft_deleted_conversations(self):
        """Test that the default manager excludes soft-deleted conversations."""
        active_conv = Conversation.objects.create(
            title="Active Conversation",
            creator=self.user,
        )

        deleted_conv = Conversation.objects.create(
            title="Deleted Conversation",
            creator=self.user,
            deleted_at=timezone.now(),
        )

        # Default manager should only return active conversations
        active_conversations = Conversation.objects.all()
        self.assertIn(active_conv, active_conversations)
        self.assertNotIn(deleted_conv, active_conversations)

        # all_objects should return both
        all_conversations = Conversation.all_objects.all()
        self.assertIn(active_conv, all_conversations)
        self.assertIn(deleted_conv, all_conversations)

    def test_manager_excludes_soft_deleted_messages(self):
        """Test that the default manager excludes soft-deleted messages."""
        conversation = Conversation.objects.create(
            title="Test Conversation",
            creator=self.user,
        )

        active_msg = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Active message",
            creator=self.user,
        )

        deleted_msg = ChatMessage.all_objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Deleted message",
            creator=self.user,
            deleted_at=timezone.now(),
        )

        # Default manager should only return active messages
        active_messages = ChatMessage.objects.all()
        self.assertIn(active_msg, active_messages)
        self.assertNotIn(deleted_msg, active_messages)

        # all_objects should return both
        all_messages = ChatMessage.all_objects.all()
        self.assertIn(active_msg, all_messages)
        self.assertIn(deleted_msg, all_messages)

    def test_soft_deleted_conversations_can_be_restored(self):
        """Test that soft-deleted conversations can be restored."""
        conversation = Conversation.objects.create(
            title="Test Conversation",
            creator=self.user,
        )

        conversation_id = conversation.id

        # Soft delete
        conversation.deleted_at = timezone.now()
        conversation.save()

        # Verify it's soft deleted
        self.assertFalse(Conversation.objects.filter(id=conversation_id).exists())

        # Restore by setting deleted_at to None
        conversation_to_restore = Conversation.all_objects.get(id=conversation_id)
        conversation_to_restore.deleted_at = None
        conversation_to_restore.save()

        # Verify it's restored
        self.assertTrue(Conversation.objects.filter(id=conversation_id).exists())

    def test_soft_deleted_messages_can_be_restored(self):
        """Test that soft-deleted messages can be restored."""
        conversation = Conversation.objects.create(
            title="Test Conversation",
            creator=self.user,
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Test message",
            creator=self.user,
        )

        message_id = message.id

        # Soft delete
        message.deleted_at = timezone.now()
        message.save()

        # Verify it's soft deleted
        self.assertFalse(ChatMessage.objects.filter(id=message_id).exists())

        # Restore by setting deleted_at to None
        message_to_restore = ChatMessage.all_objects.get(id=message_id)
        message_to_restore.deleted_at = None
        message_to_restore.save()

        # Verify it's restored
        self.assertTrue(ChatMessage.objects.filter(id=message_id).exists())

    def test_filter_by_deleted_at_timestamp(self):
        """Test filtering conversations by deleted_at timestamp."""
        now = timezone.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)

        conv1 = Conversation.all_objects.create(
            title="Recently Deleted",
            creator=self.user,
            deleted_at=hour_ago,
        )

        conv2 = Conversation.all_objects.create(
            title="Deleted Yesterday",
            creator=self.user,
            deleted_at=day_ago,
        )

        conv3 = Conversation.objects.create(
            title="Active",
            creator=self.user,
        )

        # Find conversations deleted in the last day
        recently_deleted = Conversation.all_objects.filter(
            deleted_at__gte=day_ago - timedelta(hours=1)
        )

        self.assertIn(conv1, recently_deleted)
        self.assertIn(conv2, recently_deleted)
        self.assertNotIn(conv3, recently_deleted)


class TestBackwardCompatibility(TestCase):
    """Test that new features maintain backward compatibility."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="compat_testuser",
            password="testpass123",
            email="compat@test.com",
        )

    def test_existing_chat_functionality_preserved(self):
        """Test that existing chat conversations work unchanged."""
        # Create a conversation without specifying type (should default to CHAT)
        conversation = Conversation.objects.create(
            title="Traditional Chat",
            creator=self.user,
        )

        # Create messages without agent_type or parent_message
        message1 = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Hello",
            creator=self.user,
        )

        message2 = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="LLM",
            content="Hi there!",
            creator=self.user,
        )

        # Verify default values
        self.assertEqual(conversation.conversation_type, ConversationTypeChoices.CHAT)
        self.assertIsNone(conversation.deleted_at)
        self.assertIsNone(message1.agent_type)
        self.assertIsNone(message1.parent_message)
        self.assertIsNone(message1.deleted_at)
        self.assertIsNone(message2.agent_type)
        self.assertIsNone(message2.parent_message)
        self.assertIsNone(message2.deleted_at)

    def test_queries_exclude_thread_conversations_when_filtered(self):
        """Test that we can filter out threads to only get chats."""
        chat = Conversation.objects.create(
            title="Agent Chat",
            conversation_type=ConversationTypeChoices.CHAT,
            creator=self.user,
        )

        thread = Conversation.objects.create(
            title="Discussion Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.user,
        )

        # Get only chats (traditional conversations)
        chats_only = Conversation.objects.filter(
            conversation_type=ConversationTypeChoices.CHAT
        )

        self.assertIn(chat, chats_only)
        self.assertNotIn(thread, chats_only)
        self.assertGreaterEqual(chats_only.count(), 1)


class TestThreadIntegration(TestCase):
    """Integration tests for complete thread scenarios."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
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
            title="Discussion Corpus",
            description="A corpus for discussions",
            creator=cls.user1,
            is_public=True,
        )

    def test_complete_discussion_thread_scenario(self):
        """Test a complete discussion thread with multiple users and nested replies."""
        # User1 creates a discussion thread
        thread = Conversation.objects.create(
            title="Discuss Document Analysis",
            description="Let's discuss the analysis results",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.user1,
        )

        # User1 posts the initial message
        root_message = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="I found some interesting patterns in the documents.",
            creator=self.user1,
        )

        # Document agent responds
        agent_response = ChatMessage.objects.create(
            conversation=thread,
            msg_type="LLM",
            agent_type=AgentTypeChoices.DOCUMENT_AGENT,
            content="I can help analyze those patterns.",
            parent_message=root_message,
            creator=self.user1,
        )

        # User2 replies to the agent
        user2_reply = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="That's helpful! Can you provide more details?",
            parent_message=agent_response,
            creator=self.user2,
        )

        # User1 also replies to the root message (sibling to agent_response)
        user1_additional = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Specifically, I'm interested in clause patterns.",
            parent_message=root_message,
            creator=self.user1,
        )

        # Verify the thread structure
        self.assertEqual(thread.conversation_type, ConversationTypeChoices.THREAD)
        self.assertEqual(thread.chat_messages.count(), 4)

        # Verify root message has 2 direct replies
        self.assertEqual(root_message.replies.count(), 2)
        self.assertIn(agent_response, root_message.replies.all())
        self.assertIn(user1_additional, root_message.replies.all())

        # Verify agent response has 1 reply
        self.assertEqual(agent_response.replies.count(), 1)
        self.assertEqual(agent_response.replies.first(), user2_reply)

        # Verify agent type
        self.assertEqual(agent_response.agent_type, AgentTypeChoices.DOCUMENT_AGENT)

        # Verify leaf nodes have no replies
        self.assertEqual(user2_reply.replies.count(), 0)
        self.assertEqual(user1_additional.replies.count(), 0)

    def test_soft_delete_in_thread_preserves_structure(self):
        """Test that soft deleting messages preserves thread structure for non-deleted messages."""
        thread = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.user1,
        )

        # Create a chain of messages
        msg1 = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Message 1",
            creator=self.user1,
        )

        msg2 = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Message 2",
            parent_message=msg1,
            creator=self.user1,
        )

        msg3 = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Message 3",
            parent_message=msg2,
            creator=self.user1,
        )

        # Soft delete the middle message
        msg2.deleted_at = timezone.now()
        msg2.save()

        # Verify msg1 and msg3 are still visible
        visible_messages = ChatMessage.objects.filter(conversation=thread)
        self.assertIn(msg1, visible_messages)
        self.assertNotIn(msg2, visible_messages)
        self.assertIn(msg3, visible_messages)

        # Verify msg3 can still reference msg2 (for structure preservation)
        msg3_refreshed = ChatMessage.objects.get(id=msg3.id)
        # The parent_message FK should still work even if parent is soft-deleted
        msg3_parent = ChatMessage.all_objects.get(id=msg3_refreshed.parent_message.id)
        self.assertEqual(msg3_parent, msg2)
