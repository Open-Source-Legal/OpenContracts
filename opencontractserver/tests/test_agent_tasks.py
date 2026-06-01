"""
Tests for agent task functions in opencontractserver/tasks/agent_tasks.py.

These tests cover:
- Helper functions (get_thread_channel_group, broadcast_to_thread, async_broadcast_to_thread)
- The trigger_agent_responses_for_message Celery task
- Error handling paths in generate_agent_response
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.tasks.agent_tasks import (
    async_broadcast_to_thread,
    broadcast_to_thread,
    generate_agent_response,
    get_thread_channel_group,
    trigger_agent_responses_for_message,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


class TestGetThreadChannelGroup(TestCase):
    """Tests for get_thread_channel_group helper function."""

    def test_returns_correct_format(self):
        """Test that channel group name follows expected format."""
        result = get_thread_channel_group(123)
        self.assertEqual(result, "thread_123")

    def test_handles_different_ids(self):
        """Test with various conversation IDs."""
        self.assertEqual(get_thread_channel_group(1), "thread_1")
        self.assertEqual(get_thread_channel_group(999999), "thread_999999")
        self.assertEqual(get_thread_channel_group(0), "thread_0")


class TestBroadcastToThread(TestCase):
    """Tests for broadcast_to_thread helper function."""

    @patch("opencontractserver.tasks.agent_tasks.get_channel_layer")
    def test_no_channel_layer_logs_warning(self, mock_get_channel_layer):
        """Test that missing channel layer logs warning and returns early."""
        mock_get_channel_layer.return_value = None

        # Should not raise, just log and return
        broadcast_to_thread(123, "agent.stream", {"key": "value"})

        mock_get_channel_layer.assert_called_once()

    @patch("opencontractserver.tasks.agent_tasks.get_channel_layer")
    @patch("opencontractserver.tasks.agent_tasks.async_to_sync")
    def test_broadcasts_with_converted_message_type(
        self, mock_async_to_sync, mock_get_channel_layer
    ):
        """Test that message type dots are converted to underscores."""
        mock_channel_layer = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer
        mock_async_to_sync.return_value = MagicMock()

        broadcast_to_thread(123, "agent.stream_start", {"message_id": "456"})

        # Check async_to_sync was called with group_send
        mock_async_to_sync.assert_called_once_with(mock_channel_layer.group_send)

    @patch("opencontractserver.tasks.agent_tasks.get_channel_layer")
    @patch("opencontractserver.tasks.agent_tasks.async_to_sync")
    def test_uses_correct_group_name(self, mock_async_to_sync, mock_get_channel_layer):
        """Test that correct group name is used for broadcast."""
        mock_channel_layer = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer
        mock_send = MagicMock()
        mock_async_to_sync.return_value = mock_send

        broadcast_to_thread(789, "test.event", {"data": "test"})

        # Verify the call arguments
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        self.assertEqual(call_args[0], "thread_789")
        self.assertEqual(call_args[1]["type"], "test_event")
        self.assertEqual(call_args[1]["data"], "test")


class TestAsyncBroadcastToThread(TestCase):
    """Tests for async_broadcast_to_thread helper function."""

    @patch("opencontractserver.tasks.agent_tasks.get_channel_layer")
    def test_no_channel_layer_returns_early(self, mock_get_channel_layer):
        """Test that missing channel layer logs warning and returns early."""
        mock_get_channel_layer.return_value = None

        # Run the async function
        asyncio.run(async_broadcast_to_thread(123, "agent.stream", {"key": "value"}))

        mock_get_channel_layer.assert_called_once()

    @patch("opencontractserver.tasks.agent_tasks.get_channel_layer")
    def test_broadcasts_with_converted_message_type(self, mock_get_channel_layer):
        """Test that message type dots are converted to underscores in async version."""
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        asyncio.run(
            async_broadcast_to_thread(123, "agent.stream_start", {"message_id": "456"})
        )

        # Check group_send was called
        mock_channel_layer.group_send.assert_called_once()
        call_args = mock_channel_layer.group_send.call_args[0]
        self.assertEqual(call_args[0], "thread_123")
        self.assertEqual(call_args[1]["type"], "agent_stream_start")
        self.assertEqual(call_args[1]["message_id"], "456")


class TestTriggerAgentResponsesForMessage(TestCase):
    """Tests for trigger_agent_responses_for_message Celery task."""

    user: User
    corpus: Corpus
    conversation: Conversation
    agent: AgentConfiguration

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="agent_task_test_user",
            email="agent_task@example.com",
            password="testpass123",
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=cls.user,
        )
        set_permissions_for_obj_to_user(cls.user, cls.corpus, [PermissionTypes.CRUD])

        cls.conversation = Conversation.objects.create(
            title="Test Conversation",
            conversation_type="thread",
            chat_with_corpus=cls.corpus,
            creator=cls.user,
        )
        set_permissions_for_obj_to_user(
            cls.user, cls.conversation, [PermissionTypes.CRUD]
        )

        cls.agent = AgentConfiguration.objects.create(
            name="Test Agent",
            slug="test-agent",
            description="A test agent",
            system_instructions="You are a test agent.",
            scope="CORPUS",
            corpus=cls.corpus,
            creator=cls.user,
            is_active=True,
        )
        set_permissions_for_obj_to_user(cls.user, cls.agent, [PermissionTypes.CRUD])

    def test_message_not_found_returns_error(self):
        """Test handling of non-existent message."""
        result = trigger_agent_responses_for_message(999999, self.user.pk)

        self.assertEqual(result["agents_triggered"], 0)
        self.assertEqual(result["task_ids"], [])
        self.assertEqual(result["error"], "Message not found")

    def test_no_mentioned_agents_returns_zero(self):
        """Test message with no agent mentions."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type=MessageTypeChoices.HUMAN,
            content="Hello, no agents mentioned here",
            creator=self.user,
        )

        result = trigger_agent_responses_for_message(message.pk, self.user.pk)

        self.assertEqual(result["agents_triggered"], 0)
        self.assertEqual(result["task_ids"], [])

    @patch("opencontractserver.tasks.agent_tasks.generate_agent_response.delay")
    def test_triggers_response_for_mentioned_agent(self, mock_delay):
        """Test that mentioning an agent triggers a response task."""
        mock_task = MagicMock()
        mock_task.id = "test-task-id-123"
        mock_delay.return_value = mock_task

        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type=MessageTypeChoices.HUMAN,
            content="Hello @test-agent, how are you?",
            creator=self.user,
        )
        # Manually add the agent mention (normally done by mention parser)
        message.mentioned_agents.add(self.agent)

        result = trigger_agent_responses_for_message(message.pk, self.user.pk)

        self.assertEqual(result["agents_triggered"], 1)
        self.assertEqual(result["task_ids"], ["test-task-id-123"])
        mock_delay.assert_called_once_with(
            source_message_id=message.pk,
            agent_config_id=self.agent.pk,
            user_id=self.user.pk,
        )

    @patch("opencontractserver.tasks.agent_tasks.generate_agent_response.delay")
    def test_inactive_agent_not_triggered(self, mock_delay):
        """Test that inactive agents are not triggered."""
        # Create an inactive agent
        inactive_agent = AgentConfiguration.objects.create(
            name="Inactive Agent",
            slug="inactive-agent",
            description="An inactive agent",
            system_instructions="You are inactive.",
            scope="CORPUS",
            corpus=self.corpus,
            creator=self.user,
            is_active=False,
        )

        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type=MessageTypeChoices.HUMAN,
            content="Hello @inactive-agent",
            creator=self.user,
        )
        message.mentioned_agents.add(inactive_agent)

        result = trigger_agent_responses_for_message(message.pk, self.user.pk)

        self.assertEqual(result["agents_triggered"], 0)
        self.assertEqual(result["task_ids"], [])
        mock_delay.assert_not_called()


class TestGenerateAgentResponseErrors(TestCase):
    """Tests for error handling in generate_agent_response task."""

    user: User
    corpus: Corpus
    conversation: Conversation
    agent: AgentConfiguration
    message: ChatMessage

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="agent_response_test_user",
            email="agent_response@example.com",
            password="testpass123",
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus for Response",
            creator=cls.user,
        )
        set_permissions_for_obj_to_user(cls.user, cls.corpus, [PermissionTypes.CRUD])

        cls.conversation = Conversation.objects.create(
            title="Test Conversation",
            conversation_type="thread",
            chat_with_corpus=cls.corpus,
            creator=cls.user,
        )

        cls.agent = AgentConfiguration.objects.create(
            name="Response Test Agent",
            slug="response-test-agent",
            description="A test agent for response testing",
            system_instructions="You are a test agent.",
            scope="CORPUS",
            corpus=cls.corpus,
            creator=cls.user,
            is_active=True,
        )

        cls.message = ChatMessage.objects.create(
            conversation=cls.conversation,
            msg_type=MessageTypeChoices.HUMAN,
            content="Test message",
            creator=cls.user,
        )

    def test_user_not_found_returns_error(self):
        """Test handling when user doesn't exist."""
        result = generate_agent_response(
            self.message.pk,
            self.agent.pk,
            999999,  # Non-existent user ID
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "User not found")

    def test_message_not_found_returns_error(self):
        """Test handling when source message doesn't exist."""
        result = generate_agent_response(
            999999,  # Non-existent message ID
            self.agent.pk,
            self.user.pk,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Source message not found")

    def test_agent_config_not_found_returns_error(self):
        """Test handling when agent configuration doesn't exist."""
        result = generate_agent_response(
            self.message.pk,
            999999,  # Non-existent agent config ID
            self.user.pk,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Agent configuration not found")
