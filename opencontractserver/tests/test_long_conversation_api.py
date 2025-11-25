"""
Tests for long conversation functionality in the OpenContracts LLM API.

This tests:
1. Anonymous conversation creation and behavior (ephemeral, not stored)
2. Persistent conversation creation and continuity
3. Session restoration for persistent conversations
4. Message storage behavior differences
5. Conversation metadata access
"""

from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.api import agents

User = get_user_model()


class TestLongConversationAPI(TestCase):
    """Test suite for long conversation functionality."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="conversation_testuser",
            password="testpass123",
            email="conversation@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Conversation Corpus",
            description="A corpus for testing conversations",
            creator=cls.user,
            is_public=True,
        )

        cls.document = Document.objects.create(
            title="Test Conversation Document",
            description="A document for testing conversations",
            creator=cls.user,
            is_public=True,
        )

        cls.corpus.add_document(document=cls.document, user=cls.user)

        # Ensure fixture-derived corpus is public for anonymous-agent tests.
        if hasattr(cls, "corpus"):
            cls.corpus.is_public = True
            cls.corpus.save(update_fields=["is_public"])

    async def test_anonymous_conversation_creation(self):
        """Test that anonymous conversations are created but not stored."""
        initial_conversation_count = await Conversation.objects.acount()
        initial_message_count = await ChatMessage.objects.acount()

        # Mock only the LLM interaction, not the agent creation
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent that will be used internally
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            mock_run_result = MagicMock()
            mock_run_result.messages = []
            mock_run_result.new_messages = []
            mock_run_result.output = "Test response"
            mock_run_result.all_messages = MagicMock(return_value=[])
            mock_llm_agent.run.return_value = mock_run_result

            # Mock the Agent constructor to return our mock
            MockPydanticAgent.return_value = mock_llm_agent

            # Create real agent through the API - no user_id means anonymous
            agent = await agents.for_document(
                self.document.id,
                self.corpus.id,
                framework="pydantic_ai",  # Use PydanticAI which we're mocking
            )

            # Verify conversation metadata
            conversation_id = agent.get_conversation_id()
            conversation_info = agent.get_conversation_info()

            self.assertIsNone(
                conversation_id, "Anonymous conversations should have no ID"
            )
            self.assertIsNone(conversation_info["conversation_id"])
            self.assertIsNone(conversation_info["user_id"])

            # Verify no database records were created
            final_conversation_count = await Conversation.objects.acount()
            final_message_count = await ChatMessage.objects.acount()

            self.assertEqual(
                initial_conversation_count,
                final_conversation_count,
                "Anonymous conversations should not create database records",
            )
            self.assertEqual(
                initial_message_count,
                final_message_count,
                "Anonymous conversations should not store messages",
            )

    async def test_persistent_conversation_creation(self):
        """Test that user conversations are created and stored."""
        # Ensure corpus is *private* so the new public-context optimisation does not
        # bypass DB persistence for this authenticated user.
        self.corpus.is_public = False
        await self.corpus.asave(update_fields=["is_public"])

        initial_conversation_count = await Conversation.objects.acount()

        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            mock_run_result = MagicMock()
            mock_run_result.messages = []
            mock_run_result.new_messages = []
            mock_run_result.output = "Test response"
            mock_run_result.all_messages = MagicMock(return_value=[])
            mock_llm_agent.run.return_value = mock_run_result

            MockPydanticAgent.return_value = mock_llm_agent

            # Create real agent with user_id for persistence
            agent = await agents.for_document(
                self.document.id,
                self.corpus.id,
                user_id=self.user.id,
                framework="pydantic_ai",
            )

            # Verify conversation metadata
            conversation_id = agent.get_conversation_id()
            conversation_info = agent.get_conversation_info()

            self.assertIsNotNone(
                conversation_id, "User conversations should have a real ID"
            )
            self.assertEqual(conversation_info["user_id"], self.user.id)
            self.assertIn(self.document.title, conversation_info["title"])

            # Verify database record was created
            final_conversation_count = await Conversation.objects.acount()
            self.assertEqual(
                initial_conversation_count + 1,
                final_conversation_count,
                "User conversations should create database records",
            )

            # Verify conversation exists in database
            conversation = await Conversation.objects.aget(id=conversation_id)
            self.assertEqual(conversation.creator_id, self.user.id)
            self.assertIn(self.document.title, conversation.title)

    async def test_anonymous_conversation_no_message_storage(self):
        """Test that anonymous conversations don't store messages."""
        initial_message_count = await ChatMessage.objects.acount()

        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            MockPydanticAgent.return_value = mock_llm_agent

            # Create anonymous agent
            agent = await agents.for_document(
                self.document.id, self.corpus.id, framework="pydantic_ai"
            )  # Anonymous

            # Test the actual message storage methods
            user_msg_id = await agent.store_user_message("Test user message")
            llm_msg_id = await agent.store_llm_message("Test LLM response")

            # Verify anonymous behavior
            self.assertEqual(
                user_msg_id,
                0,
                "Anonymous conversations should return 0 for message IDs",
            )
            self.assertEqual(
                llm_msg_id,
                0,
                "Anonymous conversations should return 0 for message IDs",
            )

            # Verify no messages were stored in database
            final_message_count = await ChatMessage.objects.acount()
            self.assertEqual(
                initial_message_count,
                final_message_count,
                "Anonymous conversations should not store messages",
            )

            # Verify get_conversation_messages returns empty list
            messages = await agent.get_conversation_messages()
            self.assertEqual(
                len(messages),
                0,
                "Anonymous conversations should have no stored messages",
            )

    async def test_persistent_conversation_message_storage(self):
        """Test that user conversations store messages."""
        # Make corpus private to enable message persistence for authenticated user.
        self.corpus.is_public = False
        await self.corpus.asave(update_fields=["is_public"])

        initial_message_count = await ChatMessage.objects.acount()

        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            MockPydanticAgent.return_value = mock_llm_agent

            # Create agent with user_id for persistence
            agent = await agents.for_document(
                self.document.id,
                self.corpus.id,
                user_id=self.user.id,
                framework="pydantic_ai",
            )

            # Simulate storing a user message
            user_msg_id = await agent.store_user_message("Test user message")
            self.assertNotEqual(
                user_msg_id, 0, "User conversations should return real message IDs"
            )

            # Simulate storing an LLM message
            llm_msg_id = await agent.store_llm_message("Test LLM response")
            self.assertNotEqual(
                llm_msg_id, 0, "User conversations should return real message IDs"
            )

            # Verify messages were stored in database
            final_message_count = await ChatMessage.objects.acount()
            self.assertEqual(
                initial_message_count + 2,
                final_message_count,
                "User conversations should store messages",
            )

            # Verify message content
            user_message = await ChatMessage.objects.aget(id=user_msg_id)
            llm_message = await ChatMessage.objects.aget(id=llm_msg_id)

            self.assertEqual(user_message.content, "Test user message")
            self.assertEqual(user_message.msg_type, "HUMAN")
            self.assertEqual(llm_message.content, "Test LLM response")
            self.assertEqual(llm_message.msg_type, "LLM")

            # Verify get_conversation_messages works
            messages = await agent.get_conversation_messages()
            self.assertEqual(len(messages), 2, "Should retrieve stored messages")

    async def test_conversation_continuity(self):
        """Test that persistent conversations can be continued across sessions."""
        # Ensure corpus is private for persistence.
        self.corpus.is_public = False
        await self.corpus.asave(update_fields=["is_public"])

        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            MockPydanticAgent.return_value = mock_llm_agent

            # Create first agent session
            agent1 = await agents.for_document(
                self.document.id,
                self.corpus.id,
                user_id=self.user.id,
                framework="pydantic_ai",
            )
            conversation_id = agent1.get_conversation_id()

            # Store a message in the first session
            await agent1.store_user_message("First session message")

            # Create second agent session with same conversation
            agent2 = await agents.for_document(
                self.document.id,
                self.corpus.id,
                user_id=self.user.id,
                conversation_id=conversation_id,
                framework="pydantic_ai",
            )

            # Verify it's the same conversation
            self.assertEqual(
                agent1.get_conversation_id(),
                agent2.get_conversation_id(),
                "Should continue the same conversation",
            )

            # Verify message history is accessible
            messages = await agent2.get_conversation_messages()
            self.assertGreater(
                len(messages),
                0,
                "Should have message history from previous session",
            )

            # Find our message
            user_messages = [msg for msg in messages if msg.msg_type == "HUMAN"]
            self.assertTrue(
                any("First session message" in msg.content for msg in user_messages),
                "Should preserve message history across sessions",
            )

    async def test_anonymous_conversation_no_continuity(self):
        """Test that anonymous conversations cannot be continued."""
        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            MockPydanticAgent.return_value = mock_llm_agent

            # Create anonymous agent
            agent1 = await agents.for_document(
                self.document.id, self.corpus.id, framework="pydantic_ai"
            )  # No user_id
            conversation_id = agent1.get_conversation_id()

            self.assertIsNone(
                conversation_id, "Anonymous conversations should have no ID"
            )

            # Try to "continue" the conversation (should create a new anonymous one)
            agent2 = await agents.for_document(
                self.document.id,
                self.corpus.id,
                conversation_id=conversation_id,
                framework="pydantic_ai",
            )

            # Both should be None since anonymous conversations aren't stored
            self.assertIsNone(agent1.get_conversation_id())
            self.assertIsNone(agent2.get_conversation_id())

    async def test_corpus_agent_anonymous_conversation(self):
        """Test anonymous conversations work for corpus agents too."""
        initial_conversation_count = await Conversation.objects.acount()

        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            MockPydanticAgent.return_value = mock_llm_agent

            # Create anonymous corpus agent
            agent = await agents.for_corpus(
                self.corpus.id, framework="pydantic_ai"
            )  # Anonymous

            # Verify anonymous behavior
            conversation_id = agent.get_conversation_id()
            self.assertIsNone(
                conversation_id, "Anonymous corpus conversations should have no ID"
            )

            # Verify no database records created
            final_conversation_count = await Conversation.objects.acount()
            self.assertEqual(
                initial_conversation_count,
                final_conversation_count,
                "Anonymous corpus conversations should not create database records",
            )

    async def test_corpus_agent_persistent_conversation(self):
        """Test persistent conversations work for corpus agents."""
        # Switch corpus to private to allow persistence logic.
        self.corpus.is_public = False
        await self.corpus.asave(update_fields=["is_public"])

        # Ensure a clean slate for this user's conversations for this test
        await Conversation.objects.filter(creator=self.user).adelete()

        initial_conversation_count = await Conversation.objects.acount()
        self.assertEqual(
            initial_conversation_count,
            0,
            "Ensuring no pre-existing convos for this user before test.",
        )

        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            mock_run_result = MagicMock()
            mock_run_result.messages = []
            mock_run_result.new_messages = []
            mock_run_result.output = "Test response"
            mock_run_result.all_messages = MagicMock(return_value=[])
            mock_llm_agent.run.return_value = mock_run_result

            MockPydanticAgent.return_value = mock_llm_agent

            # Create persistent corpus agent
            agent = await agents.for_corpus(
                self.corpus.id,
                user_id=self.user.id,
                conversation_id=None,  # Explicitly None
                conversation=None,  # Explicitly None
                framework="pydantic_ai",
            )

            # Verify persistent behavior
            conversation_id = agent.get_conversation_id()
            self.assertIsNotNone(
                conversation_id, "User corpus conversations should have a real ID"
            )

            # Verify database record created
            final_conversation_count = await Conversation.objects.acount()
            self.assertEqual(
                initial_conversation_count + 1,
                final_conversation_count,
                "User corpus conversations should create database records",
            )

            # Verify conversation details
            conversation = await Conversation.objects.aget(id=conversation_id)
            self.assertEqual(conversation.creator_id, self.user.id)
            self.assertIn(self.corpus.title, conversation.title)

    async def test_multi_turn_anonymous_conversation(self):
        """Test multiple interactions in an anonymous conversation."""
        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            MockPydanticAgent.return_value = mock_llm_agent

            # Create anonymous agent
            agent = await agents.for_document(
                self.document.id, self.corpus.id, framework="pydantic_ai"
            )  # Anonymous

            # Test multiple message storage operations
            questions = [
                "What is this document about?",
                "What are the key points?",
                "Can you summarize?",
            ]

            for question in questions:
                user_msg_id = await agent.store_user_message(question)
                llm_msg_id = await agent.store_llm_message(f"Response to: {question}")

                # Verify anonymous message IDs
                self.assertEqual(
                    user_msg_id,
                    0,
                    "Anonymous conversations should return 0 for user message IDs",
                )
                self.assertEqual(
                    llm_msg_id,
                    0,
                    "Anonymous conversations should return 0 for LLM message IDs",
                )

            # Verify conversation ID remains None throughout
            self.assertIsNone(agent.get_conversation_id())

            # Verify no messages stored
            messages = await agent.get_conversation_messages()
            self.assertEqual(len(messages), 0)

    async def test_conversation_info_structure(self):
        """Test conversation info structure for both anonymous and persistent."""
        # Mock only the LLM interaction
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        ) as MockPydanticAgent:
            # Create a mock LLM agent
            mock_llm_agent = AsyncMock()
            mock_llm_agent.run = AsyncMock()
            mock_run_result = MagicMock()
            mock_run_result.messages = []
            mock_run_result.new_messages = []
            mock_run_result.output = "Test response"
            mock_run_result.all_messages = MagicMock(return_value=[])
            mock_llm_agent.run.return_value = mock_run_result

            MockPydanticAgent.return_value = mock_llm_agent

            # Test anonymous conversation info
            anonymous_agent = await agents.for_document(
                self.document.id, self.corpus.id, framework="pydantic_ai"
            )
            anonymous_info = anonymous_agent.get_conversation_info()

            self.assertIsNone(anonymous_info["conversation_id"])
            self.assertIsNone(anonymous_info["user_id"])
            self.assertIsNone(anonymous_info["title"])

            # Switch to private corpus so persistent agent will store messages.
            self.corpus.is_public = False
            await self.corpus.asave(update_fields=["is_public"])

            # Test persistent conversation info
            persistent_agent = await agents.for_document(
                self.document.id,
                self.corpus.id,
                user_id=self.user.id,
                framework="pydantic_ai",
            )
            persistent_info = persistent_agent.get_conversation_info()

            self.assertIsNotNone(persistent_info["conversation_id"])
            self.assertEqual(persistent_info["user_id"], self.user.id)
            self.assertIsNotNone(persistent_info["title"])
            self.assertIn(self.document.title, persistent_info["title"])
            self.assertIsNotNone(persistent_info["created"])
