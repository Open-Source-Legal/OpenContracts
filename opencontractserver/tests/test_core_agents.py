"""
Tests for core agent components: AgentConfig, Contexts, and CoreConversationManager.
"""

from unittest.mock import MagicMock, patch

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from opencontractserver.constants.context_guardrails import (
    CHARS_PER_TOKEN_ESTIMATE,
    DEFAULT_CONTEXT_WINDOW,
    EPHEMERAL_CONTEXT_EXHAUSTION_RATIO,
)
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.core_agents import (
    AgentConfig,
    CoreConversationManager,
    CoreCorpusAgentFactory,
    CoreDocumentAgentFactory,
    DocumentAgentContext,
    get_default_config,
)
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
)

User = get_user_model()


class TestCoreAgentComponentsSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="core_testuser", password="password", email="core@test.com"
        )

        cls.corpus1 = Corpus.objects.create(
            title="Core Test Corpus",
            creator=cls.user,
            preferred_embedder="test/embedder/corpus_default",
        )
        # Create document and add to corpus - add_document returns corpus-isolated copy
        original_doc1 = Document.objects.create(
            title="Core Test Doc 1",
            creator=cls.user,
            description="Doc1 Description",
            is_public=True,
        )
        cls.doc1, _, _ = cls.corpus1.add_document(document=original_doc1, user=cls.user)

        cls.doc2 = Document.objects.create(
            title="Core Test Doc 2",
            creator=cls.user,
            description="Doc2 Description",
            is_public=True,
        )  # No corpus

        cls.conversation1 = Conversation.objects.create(
            title="Core Convo 1", creator=cls.user
        )
        cls.chat_message1 = ChatMessage.objects.create(
            conversation=cls.conversation1,
            content="User says hi",
            msg_type="USER",
            creator=cls.user,
        )


class TestAgentConfig(TestCoreAgentComponentsSetup):
    def test_get_default_config(self):
        config = get_default_config()
        self.assertEqual(config.model_name, "gpt-4o")  # Default model
        # Handle gracefully - API key might be None or present from environment
        self.assertIsNotNone(config)  # Just check config exists
        self.assertTrue(config.streaming)

    @override_settings(OPENAI_API_KEY="test_key_from_settings")
    def test_get_default_config_with_settings_override(self):
        config = get_default_config(model_name="custom_model", streaming=False)
        self.assertEqual(config.model_name, "custom_model")
        self.assertEqual(config.api_key, "test_key_from_settings")
        self.assertFalse(config.streaming)
        # Ensure other defaults are still there
        self.assertEqual(config.similarity_top_k, 10)


class TestAgentContexts(TestCoreAgentComponentsSetup):
    @patch(
        f"{CoreAnnotationVectorStore.__module__}.CoreAnnotationVectorStore.__init__",
        return_value=None,
    )  # Mock __init__ to prevent DB/embedder calls
    def test_document_agent_context_init_minimal(
        self, mock_vector_store_init: MagicMock
    ):
        config = AgentConfig(
            user_id=self.user.id, embedder_path="test/embedder/doc_specific"
        )
        context = DocumentAgentContext(self.corpus1, self.doc1, config)

        self.assertIs(context.document, self.doc1)
        self.assertIs(context.config, config)
        mock_vector_store_init.assert_called_once_with(
            user_id=self.user.id,
            document_id=self.doc1.id,
            corpus_id=self.corpus1.id,
            embedder_path="test/embedder/doc_specific",
        )

    @patch(
        f"{CoreAnnotationVectorStore.__module__}.CoreAnnotationVectorStore.__init__",
        return_value=None,
    )
    def test_document_agent_context_with_explicit_vector_store(
        self, mock_vector_store_init: MagicMock
    ):
        mock_vs = MagicMock(spec=CoreAnnotationVectorStore)
        config = AgentConfig()
        context = DocumentAgentContext(
            self.corpus1, self.doc1, config, vector_store=mock_vs
        )
        self.assertIs(context.vector_store, mock_vs)
        mock_vector_store_init.assert_not_called()  # Should not init a new one

    async def test_corpus_agent_context_init(self):
        # Create a fresh corpus and its documents specifically for this test
        # self.user is available from TestCoreAgentComponentsSetup.setUpTestData
        test_corpus = await Corpus.objects.acreate(
            title="Test Corpus for Context Init",
            creator=self.user,
            preferred_embedder="test/embedder/corpus_default",
        )
        doc1_for_this_test = await Document.objects.acreate(
            title="Doc1 in Test Corpus",
            creator=self.user,
            description="First document for this specific test",
            is_public=True,
        )
        # add_document returns corpus-isolated copy (not the original)
        corpus_doc1, _, _ = await sync_to_async(test_corpus.add_document)(
            document=doc1_for_this_test, user=self.user
        )

        # This is the second document expected by the original test logic
        doc2_for_this_test = await Document.objects.acreate(
            title="Doc2 in Test Corpus",
            creator=self.user,
            description="Second document for this specific test",
            is_public=True,
        )
        # add_document returns corpus-isolated copy (not the original)
        corpus_doc2, _, _ = await sync_to_async(test_corpus.add_document)(
            document=doc2_for_this_test, user=self.user
        )

        config = AgentConfig(embedder_path=None)  # Test corpus default embedder
        config.user_id = self.user.id

        # Use the factory method with the ID of the locally created corpus
        context = await CoreCorpusAgentFactory.create_context(test_corpus.id, config)

        # Assertions using the locally created corpus and documents
        self.assertEqual(
            context.corpus, test_corpus
        )  # Django models __eq__ compares PKs
        self.assertIs(
            context.config, config
        )  # Config object should be the same instance
        self.assertIsNotNone(context.documents)

        doc_ids_in_context = {doc.id for doc in context.documents}

        # Check that corpus-isolated copies are found in the context
        self.assertIn(corpus_doc1.id, doc_ids_in_context)
        self.assertIn(corpus_doc2.id, doc_ids_in_context)
        self.assertEqual(len(context.documents), 2)  # Expecting two documents

        # Check if corpus preferred embedder was used (this part of the logic remains)
        self.assertEqual(config.embedder_path, "test/embedder/corpus_default")

    async def test_corpus_agent_context_specific_embedder(self):
        # Ensure corpus is public to allow anonymous access during context creation.
        self.corpus1.is_public = True
        await self.corpus1.asave(update_fields=["is_public"])

        config = AgentConfig(embedder_path="specific/path")
        # Use the factory method instead of direct instantiation
        await CoreCorpusAgentFactory.create_context(self.corpus1.id, config)
        self.assertEqual(
            config.embedder_path, "specific/path"
        )  # Should not be overridden


class TestCoreConversationManager(TestCoreAgentComponentsSetup):
    async def test_create_for_document_new_conversation(self):
        initial_convo_count = await Conversation.objects.acount()
        config = AgentConfig(user_id=self.user.id)
        manager = await CoreConversationManager.create_for_document(
            self.corpus1, self.doc1, self.user.id, config
        )

        self.assertIsNotNone(manager.conversation)
        self.assertEqual(manager.conversation.creator_id, self.user.id)
        self.assertTrue(self.doc1.title in manager.conversation.title)
        self.assertEqual(await Conversation.objects.acount(), initial_convo_count + 1)

    async def test_create_for_document_existing_conversation(self):
        initial_convo_count = await Conversation.objects.acount()
        config = AgentConfig(user_id=self.user.id, conversation=self.conversation1)
        manager = await CoreConversationManager.create_for_document(
            self.corpus1, self.doc1, self.user.id, config
        )
        self.assertIs(manager.conversation, self.conversation1)
        self.assertEqual(
            await Conversation.objects.acount(), initial_convo_count
        )  # No new convo

    async def test_create_for_corpus_new_conversation(self):
        initial_convo_count = await Conversation.objects.acount()
        config = AgentConfig(user_id=self.user.id)
        manager = await CoreConversationManager.create_for_corpus(
            self.corpus1, self.user.id, config
        )

        self.assertIsNotNone(manager.conversation)
        self.assertEqual(manager.conversation.creator_id, self.user.id)
        self.assertTrue(self.corpus1.title in manager.conversation.title)
        self.assertEqual(await Conversation.objects.acount(), initial_convo_count + 1)

    async def test_create_for_corpus_existing_conversation(self):
        config = AgentConfig(user_id=self.user.id, conversation=self.conversation1)
        manager = await CoreConversationManager.create_for_corpus(
            self.corpus1, self.user.id, config
        )
        self.assertIs(manager.conversation, self.conversation1)

    async def test_store_user_message(self):
        config = AgentConfig(user_id=self.user.id)
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.store_user_message("Test user message")
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.content, "Test user message")
        self.assertEqual(message.msg_type, "HUMAN")
        self.assertEqual(message.conversation_id, self.conversation1.id)
        self.assertEqual(message.creator_id, self.user.id)

    async def test_store_llm_message(self):
        config = AgentConfig(user_id=self.user.id)
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.store_llm_message(
            "Test LLM response", metadata={"tool_used": "yes"}
        )
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.content, "Test LLM response")
        self.assertEqual(message.msg_type, "LLM")
        self.assertEqual(message.data["tool_used"], "yes")

    async def test_update_message(self):
        config = AgentConfig(user_id=self.user.id)
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.store_user_message("Original content")
        await manager.update_message(
            msg_id, "Updated content", metadata={"status": "edited"}
        )
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.content, "Updated content")
        self.assertEqual(message.data["status"], "edited")

    async def test_complete_message_stores_model_name(self):
        """complete_message() should persist the model name from AgentConfig."""
        config = AgentConfig(user_id=self.user.id, model_name="gpt-4o")
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.create_placeholder_message("LLM")
        await manager.complete_message(msg_id, "Response text")
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.data["model_name"], "gpt-4o")

    async def test_complete_message_uses_default_model_name(self):
        """complete_message() should use the default model name when none is explicitly set."""
        config = AgentConfig(user_id=self.user.id)
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.create_placeholder_message("LLM")
        await manager.complete_message(msg_id, "Response text")
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.data["model_name"], config.model_name)

    async def test_store_llm_message_stores_model_name(self):
        """store_llm_message() should persist the model name from AgentConfig."""
        config = AgentConfig(user_id=self.user.id, model_name="claude-3-opus")
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.store_llm_message("LLM response")
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.data["model_name"], "claude-3-opus")

    async def test_placeholder_message_stores_model_name(self):
        """create_placeholder_message() should persist the model name for traceability."""
        config = AgentConfig(user_id=self.user.id, model_name="gpt-4-turbo")
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.create_placeholder_message("LLM")
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.data["model_name"], "gpt-4-turbo")

    async def test_update_message_stores_model_name(self):
        """update_message() should backfill model_name when absent."""
        config = AgentConfig(user_id=self.user.id, model_name="gpt-4o")
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.store_user_message("Original content")
        await manager.update_message(msg_id, "Updated content")
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.data["model_name"], "gpt-4o")

    async def test_mark_message_error_stores_model_name(self):
        """mark_message_error() should backfill model_name when absent."""
        config = AgentConfig(user_id=self.user.id, model_name="claude-3-opus")
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.create_placeholder_message("LLM")
        await manager.mark_message_error(msg_id, "Something went wrong")
        message = await ChatMessage.objects.aget(id=msg_id)
        self.assertEqual(message.data["model_name"], "claude-3-opus")
        self.assertEqual(message.data["error"], "Something went wrong")

    async def test_complete_message_preserves_placeholder_model_name(self):
        """complete_message() should not overwrite model_name set by create_placeholder_message()."""
        config = AgentConfig(user_id=self.user.id, model_name="gpt-4o")
        manager = CoreConversationManager(
            conversation=self.conversation1, user_id=self.user.id, config=config
        )
        msg_id = await manager.create_placeholder_message("LLM")

        # Simulate config change between placeholder creation and completion
        manager.config.model_name = "gpt-4o-mini"
        await manager.complete_message(msg_id, "Response text")

        message = await ChatMessage.objects.aget(id=msg_id)
        # Placeholder value ("gpt-4o") should be preserved via setdefault
        self.assertEqual(message.data["model_name"], "gpt-4o")


class TestCoreAgentFactoriesDefaults(TestCoreAgentComponentsSetup):
    # These test the default prompt generation, not full context creation
    def test_document_agent_default_system_prompt(self):
        prompt = CoreDocumentAgentFactory.get_default_system_prompt(self.doc1)
        self.assertIn(self.doc1.title, prompt)
        self.assertIn(str(self.doc1.id), prompt)
        # Note: The current implementation doesn't include description in the prompt
        # self.assertIn(self.doc1.description, prompt)

    def test_corpus_agent_default_system_prompt(self):
        prompt = CoreCorpusAgentFactory.get_default_system_prompt(self.corpus1)
        self.assertIn(self.corpus1.title, prompt)

    @override_settings(DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS="Default doc instructions")
    def test_document_agent_uses_default_instructions_when_corpus_has_none(self):
        """Test that default settings are used when corpus has no custom document_agent_instructions."""
        prompt = CoreDocumentAgentFactory.get_default_system_prompt(
            self.doc1, self.corpus1
        )
        self.assertIn("Default doc instructions", prompt)
        self.assertIn(self.doc1.title, prompt)

    @override_settings(DEFAULT_CORPUS_AGENT_INSTRUCTIONS="Default corpus instructions")
    def test_corpus_agent_uses_default_instructions_when_corpus_has_none(self):
        """Test that default settings are used when corpus has no custom corpus_agent_instructions."""
        prompt = CoreCorpusAgentFactory.get_default_system_prompt(self.corpus1)
        self.assertIn("Default corpus instructions", prompt)
        self.assertIn(self.corpus1.title, prompt)

    def test_document_agent_uses_custom_instructions_when_corpus_has_them(self):
        """Test that custom document_agent_instructions from corpus are used when available."""
        self.corpus1.document_agent_instructions = (
            "Custom document instructions for this corpus"
        )
        self.corpus1.save()
        prompt = CoreDocumentAgentFactory.get_default_system_prompt(
            self.doc1, self.corpus1
        )
        self.assertIn("Custom document instructions for this corpus", prompt)
        self.assertIn(self.doc1.title, prompt)

    def test_corpus_agent_uses_custom_instructions_when_corpus_has_them(self):
        """Test that custom corpus_agent_instructions from corpus are used when available."""
        self.corpus1.corpus_agent_instructions = (
            "Custom corpus instructions for this corpus"
        )
        self.corpus1.save()
        prompt = CoreCorpusAgentFactory.get_default_system_prompt(self.corpus1)
        self.assertIn("Custom corpus instructions for this corpus", prompt)
        self.assertIn(self.corpus1.title, prompt)

    @patch(
        f"{CoreDocumentAgentFactory.__module__}.CoreDocumentAgentFactory.get_default_system_prompt"
    )
    async def test_create_document_context_uses_default_prompt(
        self, mock_get_prompt: MagicMock
    ):
        mock_get_prompt.return_value = "Mocked default prompt"
        config = AgentConfig(system_prompt=None)  # Ensure it's None to trigger default
        config.user_id = self.user.id

        context = await CoreDocumentAgentFactory.create_context(
            self.doc1, self.corpus1, config
        )

        mock_get_prompt.assert_called_once_with(self.doc1, self.corpus1)
        self.assertEqual(context.config.system_prompt, "Mocked default prompt")

    async def test_create_document_context_uses_override_prompt(self):
        override_prompt = "My custom prompt for docs"
        config = AgentConfig(system_prompt=override_prompt)
        config.user_id = self.user.id

        context = await CoreDocumentAgentFactory.create_context(
            self.doc1, self.corpus1, config
        )
        self.assertEqual(context.config.system_prompt, override_prompt)

    # Similar tests for CoreCorpusAgentFactory and its prompt logic can be added.


class TestEphemeralConversationManager(TestCase):
    """Tests for the in-memory ephemeral buffer used by anonymous sessions."""

    def _make_ephemeral_manager(self) -> CoreConversationManager:
        """Return a CoreConversationManager with no DB conversation (anonymous)."""
        config = AgentConfig(
            model_name="gpt-4o",
            store_user_messages=True,
            store_llm_messages=True,
        )
        return CoreConversationManager(None, None, config)

    # ------------------------------------------------------------------
    # Task 1: Buffer initialisation
    # ------------------------------------------------------------------

    def test_ephemeral_buffer_initialised_empty(self):
        manager = self._make_ephemeral_manager()
        self.assertIsNone(manager.conversation)
        self.assertEqual(manager._ephemeral_messages, [])
        self.assertEqual(manager._ephemeral_token_estimate, 0)
        self.assertEqual(manager._ephemeral_next_id, 1)

    # ------------------------------------------------------------------
    # Task 2: store_user_message and create_placeholder_message
    # ------------------------------------------------------------------

    async def test_store_user_message_appends_to_buffer(self):
        manager = self._make_ephemeral_manager()
        msg_id = await manager.store_user_message("Hello, world!")
        self.assertEqual(len(manager._ephemeral_messages), 1)
        msg = manager._ephemeral_messages[0]
        self.assertEqual(msg.id, msg_id)
        self.assertEqual(msg.content, "Hello, world!")
        self.assertEqual(msg.msg_type, "HUMAN")

    async def test_store_user_message_returns_truthy_id(self):
        manager = self._make_ephemeral_manager()
        msg_id = await manager.store_user_message("test")
        self.assertGreater(msg_id, 0)
        # A truthy ID is required so downstream `if msg_id:` guards work.
        self.assertTrue(msg_id)

    async def test_create_placeholder_returns_synthetic_id(self):
        manager = self._make_ephemeral_manager()
        msg_id = await manager.create_placeholder_message("LLM")
        # Must be truthy so `if llm_msg_id:` at line ~844 proceeds.
        self.assertTrue(msg_id)
        self.assertGreater(msg_id, 0)

    async def test_create_placeholder_does_not_append_to_buffer(self):
        """Placeholder only reserves an ID; buffer stays empty until complete_message."""
        manager = self._make_ephemeral_manager()
        await manager.create_placeholder_message("LLM")
        self.assertEqual(len(manager._ephemeral_messages), 0)

    async def test_sequential_ids_increment(self):
        manager = self._make_ephemeral_manager()
        id1 = await manager.store_user_message("first")
        id2 = await manager.create_placeholder_message("LLM")
        id3 = await manager.store_user_message("second")
        self.assertEqual(id2, id1 + 1)
        self.assertEqual(id3, id2 + 1)

    # ------------------------------------------------------------------
    # Task 3: complete_message, update_message, get_conversation_messages
    # ------------------------------------------------------------------

    async def test_complete_message_appends_assistant_to_buffer(self):
        manager = self._make_ephemeral_manager()
        msg_id = await manager.create_placeholder_message("LLM")
        await manager.complete_message(msg_id, "This is the assistant reply.")
        self.assertEqual(len(manager._ephemeral_messages), 1)
        msg = manager._ephemeral_messages[0]
        self.assertEqual(msg.id, msg_id)
        self.assertEqual(msg.content, "This is the assistant reply.")
        # msg_type must be "LLM" to match _get_message_history() convention
        self.assertEqual(msg.msg_type, "LLM")

    async def test_update_message_modifies_existing(self):
        manager = self._make_ephemeral_manager()
        msg_id = await manager.store_user_message("original")
        await manager.update_message(msg_id, "updated content")
        msg = manager._ephemeral_messages[0]
        self.assertEqual(msg.content, "updated content")

    async def test_get_conversation_messages_returns_buffer(self):
        manager = self._make_ephemeral_manager()
        await manager.store_user_message("question")
        llm_id = await manager.create_placeholder_message("LLM")
        await manager.complete_message(llm_id, "answer")

        messages = await manager.get_conversation_messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].msg_type, "HUMAN")
        self.assertEqual(messages[1].msg_type, "LLM")

    async def test_get_conversation_messages_returns_copy(self):
        """Mutating the returned list must not affect the internal buffer."""
        manager = self._make_ephemeral_manager()
        await manager.store_user_message("q")
        messages = await manager.get_conversation_messages()
        messages.clear()
        self.assertEqual(len(manager._ephemeral_messages), 1)

    async def test_token_estimate_accumulates(self):
        manager = self._make_ephemeral_manager()
        self.assertEqual(manager._ephemeral_token_estimate, 0)
        await manager.store_user_message("x" * 100)
        est_after_user = manager._ephemeral_token_estimate
        self.assertGreater(est_after_user, 0)

        llm_id = await manager.create_placeholder_message("LLM")
        await manager.complete_message(llm_id, "y" * 200)
        est_after_llm = manager._ephemeral_token_estimate
        self.assertGreater(est_after_llm, est_after_user)

    # ------------------------------------------------------------------
    # store_llm_message
    # ------------------------------------------------------------------

    async def test_store_llm_message_appends_to_buffer(self):
        manager = self._make_ephemeral_manager()
        msg_id = await manager.store_llm_message("LLM says hi")
        self.assertEqual(len(manager._ephemeral_messages), 1)
        msg = manager._ephemeral_messages[0]
        self.assertEqual(msg.id, msg_id)
        self.assertEqual(msg.content, "LLM says hi")
        self.assertEqual(msg.msg_type, "LLM")

    async def test_store_llm_message_retains_sources_and_metadata(self):
        from opencontractserver.llms.agents.core_agents import SourceNode

        manager = self._make_ephemeral_manager()
        src = SourceNode(annotation_id=42, content="excerpt")
        meta = {"key": "value"}
        await manager.store_llm_message("response", sources=[src], metadata=meta)
        msg = manager._ephemeral_messages[0]
        self.assertEqual(msg.sources, [src])
        self.assertEqual(msg.metadata, meta)

    # ------------------------------------------------------------------
    # sources/metadata retention in complete_message and update_message
    # ------------------------------------------------------------------

    async def test_complete_message_retains_sources_and_metadata(self):
        from opencontractserver.llms.agents.core_agents import SourceNode

        manager = self._make_ephemeral_manager()
        msg_id = await manager.create_placeholder_message("LLM")
        src = SourceNode(annotation_id=7, content="text")
        meta = {"timeline": [{"step": 1}]}
        await manager.complete_message(msg_id, "done", sources=[src], metadata=meta)
        msg = manager._ephemeral_messages[0]
        self.assertEqual(msg.sources, [src])
        self.assertEqual(msg.metadata, meta)

    async def test_update_message_retains_sources_and_metadata(self):
        from opencontractserver.llms.agents.core_agents import SourceNode

        manager = self._make_ephemeral_manager()
        msg_id = await manager.store_user_message("original")
        src = SourceNode(annotation_id=99, content="snip")
        await manager.update_message(
            msg_id, "updated", sources=[src], metadata={"a": 1}
        )
        msg = manager._ephemeral_messages[0]
        self.assertEqual(msg.content, "updated")
        self.assertEqual(msg.sources, [src])
        self.assertEqual(msg.metadata, {"a": 1})

    # ------------------------------------------------------------------
    # Task 4: context_exhausted property
    # ------------------------------------------------------------------

    def test_context_not_exhausted_initially(self):
        manager = self._make_ephemeral_manager()
        self.assertFalse(manager.context_exhausted)

    async def test_context_exhausted_when_buffer_large(self):
        """Filling past the exhaustion threshold should set context_exhausted."""
        manager = self._make_ephemeral_manager()
        # gpt-4o window = DEFAULT_CONTEXT_WINDOW; threshold chars =
        # window * ratio * chars_per_token.  Add 2% margin to be safely above.
        threshold_chars = int(
            DEFAULT_CONTEXT_WINDOW
            * EPHEMERAL_CONTEXT_EXHAUSTION_RATIO
            * CHARS_PER_TOKEN_ESTIMATE
        )
        large_content = "a" * int(threshold_chars * 1.02)
        await manager.store_user_message(large_content)
        self.assertTrue(manager.context_exhausted)

    async def test_context_exhaustion_unknown_model_uses_fallback(self):
        """Unknown model names should use DEFAULT_CONTEXT_WINDOW, not block immediately."""
        config = AgentConfig(model_name="totally-unknown-model-xyz")
        manager = CoreConversationManager(None, None, config)
        # With an empty buffer the estimate is 0, which should not exceed
        # the fallback context window (DEFAULT_CONTEXT_WINDOW = 128_000).
        self.assertFalse(manager.context_exhausted)
        # A small message should also not trigger exhaustion
        await manager.store_user_message("Hello, world!")
        self.assertFalse(manager.context_exhausted)

    def test_context_not_exhausted_for_db_conversations(self):
        """DB-backed sessions always return False (compaction handles them)."""
        from opencontractserver.conversations.models import Conversation

        fake_conv = Conversation.__new__(Conversation)
        fake_conv.pk = 1
        config = AgentConfig(model_name="gpt-4o")
        manager = CoreConversationManager(fake_conv, 1, config)
        # Manually set a large estimate to verify the DB guard takes priority
        manager._ephemeral_token_estimate = 9_999_999
        self.assertFalse(manager.context_exhausted)

    # ------------------------------------------------------------------
    # Task 5: Guard against None/0 message_id in complete_message
    # ------------------------------------------------------------------

    async def test_complete_message_skips_none_message_id(self):
        manager = self._make_ephemeral_manager()
        # Should be a no-op and not raise
        await manager.complete_message(None, "some content")
        self.assertEqual(len(manager._ephemeral_messages), 0)
        self.assertEqual(manager._ephemeral_token_estimate, 0)

    async def test_complete_message_skips_zero_message_id(self):
        manager = self._make_ephemeral_manager()
        await manager.complete_message(0, "some content")
        self.assertEqual(len(manager._ephemeral_messages), 0)
        self.assertEqual(manager._ephemeral_token_estimate, 0)

    async def test_complete_message_no_double_write(self):
        """Simulates the stream() → complete_message(None) → complete_message(real_id) path."""
        manager = self._make_ephemeral_manager()
        msg_id = await manager.create_placeholder_message("LLM")

        # _stream_core calls complete_message(None, ...) — must be a no-op
        await manager.complete_message(None, "ignored content")
        self.assertEqual(len(manager._ephemeral_messages), 0)

        # CoreAgentBase.stream() then calls complete_message(real_id, ...)
        await manager.complete_message(msg_id, "real content")
        self.assertEqual(len(manager._ephemeral_messages), 1)
        self.assertEqual(manager._ephemeral_messages[0].content, "real content")

    async def test_complete_message_idempotent_same_id(self):
        """complete_message(real_id) called twice updates in place, no duplicate."""
        manager = self._make_ephemeral_manager()
        msg_id = await manager.create_placeholder_message("LLM")

        await manager.complete_message(msg_id, "first content")
        self.assertEqual(len(manager._ephemeral_messages), 1)

        # Second call with the same ID — should update, not append.
        await manager.complete_message(msg_id, "updated content")
        self.assertEqual(len(manager._ephemeral_messages), 1)
        self.assertEqual(manager._ephemeral_messages[0].content, "updated content")

    async def test_ephemeral_update_missing_id_logs_warning(self):
        """_ephemeral_update returns False for unknown IDs, callers log warning."""
        manager = self._make_ephemeral_manager()
        result = manager._ephemeral_update(9999, "nope")
        self.assertFalse(result)

    async def test_update_message_content_missing_id_logs_warning(self):
        """update_message_content logs when the message ID is not in the buffer."""
        manager = self._make_ephemeral_manager()
        with self.assertLogs(
            "opencontractserver.llms.agents.core_agents", level="WARNING"
        ) as cm:
            await manager.update_message_content(9999, "missing")
        self.assertTrue(any("9999 not found" in msg for msg in cm.output))

    async def test_update_message_missing_id_logs_warning(self):
        """update_message logs when the message ID is not in the buffer."""
        manager = self._make_ephemeral_manager()
        with self.assertLogs(
            "opencontractserver.llms.agents.core_agents", level="WARNING"
        ) as cm:
            await manager.update_message(9999, "missing")
        self.assertTrue(any("9999 not found" in msg for msg in cm.output))

    def test_storage_backend_ephemeral(self):
        """AgentConfig.storage_backend is 'ephemeral' for anonymous managers."""
        config = AgentConfig(model_name="gpt-4o")
        config.storage_backend = "ephemeral"
        config.store_user_messages = True
        config.store_llm_messages = True
        manager = CoreConversationManager(None, None, config)
        self.assertEqual(manager.config.storage_backend, "ephemeral")
        self.assertTrue(manager.config.store_user_messages)

    def test_storage_backend_default_is_db(self):
        """AgentConfig.storage_backend defaults to 'db'."""
        config = AgentConfig(model_name="gpt-4o")
        self.assertEqual(config.storage_backend, "db")
