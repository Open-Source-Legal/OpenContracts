"""
Tests for the core OpenContracts Agent API surface.
(agents, tools, vector_stores as imported from opencontractserver.llms)
"""

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms import agents, tools, vector_stores  # The API under test
from opencontractserver.llms.agents.agent_factory import UnifiedAgentFactory
from opencontractserver.llms.agents.core_agents import CoreAgent
from opencontractserver.llms.tools.tool_factory import CoreTool
from opencontractserver.llms.types import AgentFramework
from opencontractserver.llms.vector_stores.vector_store_factory import (
    UnifiedVectorStoreFactory,
)
from opencontractserver.users.models import User


class TestAPISetup(TestCase):
    user: User
    corpus1: Corpus
    doc1: Document
    doc2: Document
    label1: AnnotationLabel
    anno1_doc1: Annotation
    conversation1: Conversation
    chat_message1: ChatMessage
    chat_message2: ChatMessage
    dummy_tool_func: Callable[[str], str]
    core_tool_instance: CoreTool

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="api_testuser", password="password", email="api@test.com"
        )

        cls.corpus1 = Corpus.objects.create(title="API Test Corpus 1", creator=cls.user)
        # Create document and add to corpus - add_document returns corpus-isolated copy
        original_doc1 = Document.objects.create(
            title="API Test Doc 1", creator=cls.user
        )
        cls.doc1, _, _ = cls.corpus1.add_document(document=original_doc1, user=cls.user)

        cls.doc2 = Document.objects.create(
            title="API Test Doc 2", creator=cls.user
        )  # No corpus initially

        cls.label1 = AnnotationLabel.objects.create(text="Label1", creator=cls.user)
        cls.anno1_doc1 = Annotation.objects.create(
            document=cls.doc1,
            corpus=cls.corpus1,
            creator=cls.user,
            raw_text="Annotation 1 in Doc 1",
            annotation_label=cls.label1,
        )

        cls.conversation1 = Conversation.objects.create(
            title="Test Convo 1", creator=cls.user
        )
        cls.chat_message1 = ChatMessage.objects.create(
            conversation=cls.conversation1,
            content="Hello from user",
            msg_type="USER",
            creator=cls.user,
        )
        cls.chat_message2 = ChatMessage.objects.create(
            conversation=cls.conversation1,
            content="Hello from LLM",
            msg_type="LLM",
            creator=cls.user,
        )

        # For tool testing
        def dummy_tool_func(text: str) -> str:
            """A dummy tool function for testing."""
            return f"Processed: {text}"

        cls.dummy_tool_func = dummy_tool_func  # Store raw function
        cls.core_tool_instance = CoreTool.from_function(
            cls.dummy_tool_func, name="dummy_core_tool"
        )


class TestAgentAPIHypermodern(TestAPISetup):
    @patch(
        f"{UnifiedAgentFactory.__module__}.{UnifiedAgentFactory.__name__}.create_document_agent",
        new_callable=AsyncMock,
    )
    async def test_document_agent_creation_default_framework(
        self, mock_create_doc_agent: AsyncMock
    ):
        mock_create_doc_agent.return_value = AsyncMock(spec=CoreAgent)

        agent = await agents.for_document(self.doc1.id, self.corpus1.id)

        mock_create_doc_agent.assert_called_once()
        args, kwargs = mock_create_doc_agent.call_args
        self.assertEqual(args[0], self.doc1.id)
        self.assertEqual(args[1], self.corpus1.id)
        self.assertEqual(kwargs["framework"], AgentFramework.PYDANTIC_AI)  # Default
        self.assertIsInstance(agent, CoreAgent)

    @patch(
        f"{UnifiedAgentFactory.__module__}.{UnifiedAgentFactory.__name__}.create_document_agent",
        new_callable=AsyncMock,
    )
    async def test_document_agent_creation_pydantic_ai(
        self, mock_create_doc_agent: AsyncMock
    ):
        mock_create_doc_agent.return_value = AsyncMock(spec=CoreAgent)

        agent = await agents.for_document(
            self.doc1.id, self.corpus1.id, framework="pydantic_ai"
        )

        mock_create_doc_agent.assert_called_once()
        args, kwargs = mock_create_doc_agent.call_args
        self.assertEqual(args[0], self.doc1.id)
        self.assertEqual(args[1], self.corpus1.id)
        self.assertEqual(kwargs["framework"], AgentFramework.PYDANTIC_AI)
        self.assertIsInstance(agent, CoreAgent)

    @patch(
        f"{UnifiedAgentFactory.__module__}.{UnifiedAgentFactory.__name__}.create_document_agent",
        new_callable=AsyncMock,
    )
    async def test_document_agent_all_params(self, mock_create_doc_agent: AsyncMock):
        mock_create_doc_agent.return_value = AsyncMock(spec=CoreAgent)

        await agents.for_document(
            self.doc1.id,
            self.corpus1.id,
            framework="pydantic_ai",
            user_id=self.user.id,
            model="gpt-4-turbo",
            system_prompt="You are helpful.",
            conversation=self.conversation1,
            messages=[self.chat_message1, self.chat_message2],
            tools=["summarize", self.dummy_tool_func, self.core_tool_instance],
            embedder="custom/path/to/embedder",
            streaming=False,
            verbose=True,
            custom_arg="test_value",
        )

        mock_create_doc_agent.assert_called_once()
        args, kwargs = mock_create_doc_agent.call_args

        self.assertEqual(args[0], self.doc1.id)
        self.assertEqual(args[1], self.corpus1.id)
        self.assertEqual(kwargs["framework"], AgentFramework.PYDANTIC_AI)
        self.assertEqual(kwargs["user_id"], self.user.id)
        self.assertEqual(kwargs["model"], "gpt-4-turbo")
        self.assertEqual(kwargs["system_prompt"], "You are helpful.")
        self.assertEqual(kwargs["conversation"], self.conversation1)
        self.assertEqual(
            kwargs["loaded_messages"], [self.chat_message1, self.chat_message2]
        )
        self.assertEqual(kwargs["embedder_path"], "custom/path/to/embedder")
        self.assertFalse(kwargs["streaming"])
        self.assertTrue(kwargs["verbose"])
        self.assertEqual(kwargs["custom_arg"], "test_value")

        # Check tools were resolved - UnifiedAgentFactory receives CoreTools
        resolved_tools_arg = kwargs["tools"]
        self.assertIsInstance(resolved_tools_arg, list)
        self.assertEqual(len(resolved_tools_arg), 3)
        self.assertTrue(all(isinstance(t, CoreTool) for t in resolved_tools_arg))
        # Names might be auto-generated for built-ins/callables if not directly CoreTool
        tool_names = [t.name for t in resolved_tools_arg]
        self.assertIn(
            "load_document_summary", tool_names
        )  # "summarize" resolves via alias to canonical "load_document_summary"
        self.assertIn("dummy_tool_func", tool_names)
        self.assertIn("dummy_core_tool", tool_names)

    @patch(
        f"{UnifiedAgentFactory.__module__}.{UnifiedAgentFactory.__name__}.create_corpus_agent",
        new_callable=AsyncMock,
    )
    async def test_corpus_agent_creation(self, mock_create_corpus_agent: AsyncMock):
        mock_create_corpus_agent.return_value = AsyncMock(spec=CoreAgent)

        agent = await agents.for_corpus(self.corpus1.id, model="claude-opus")

        mock_create_corpus_agent.assert_called_once()
        args, kwargs = mock_create_corpus_agent.call_args
        self.assertEqual(args[0], self.corpus1.id)
        self.assertEqual(kwargs["model"], "claude-opus")
        self.assertEqual(kwargs["framework"], AgentFramework.PYDANTIC_AI)  # Default
        self.assertIsInstance(agent, CoreAgent)

    @patch(
        f"{UnifiedAgentFactory.__module__}.{UnifiedAgentFactory.__name__}.create_document_agent",
        new_callable=AsyncMock,
    )
    async def test_agent_interaction_chat_mocked(
        self, mock_create_doc_agent: AsyncMock
    ):
        # Setup the agent mock that will be returned by the factory
        mock_agent_instance = AsyncMock(spec=CoreAgent)
        mock_agent_instance.chat.return_value = "Mocked LLM response"
        mock_create_doc_agent.return_value = mock_agent_instance

        agent = await agents.for_document(self.doc1.id, self.corpus1.id)
        response = await agent.chat("hello")

        self.assertEqual(response, "Mocked LLM response")
        mock_agent_instance.chat.assert_called_once_with("hello")

    @patch(
        f"{UnifiedAgentFactory.__module__}.{UnifiedAgentFactory.__name__}.create_document_agent",
        new_callable=AsyncMock,
    )
    async def test_agent_interaction_stream_chat_mocked(
        self, mock_create_doc_agent: AsyncMock
    ):
        mock_agent_instance = AsyncMock(spec=CoreAgent)

        async def mock_stream_chat_impl(message: str):
            yield "chunk1"
            yield "chunk2"

        mock_agent_instance.stream_chat = mock_stream_chat_impl
        mock_create_doc_agent.return_value = mock_agent_instance

        agent = await agents.for_document(self.doc1.id, self.corpus1.id)

        chunks = []
        # ``stream_chat`` is the legacy wrapper on the concrete agent base, not
        # part of the modern CoreAgent protocol (which exposes ``stream``); the
        # mock above replaces it wholesale, so the protocol-typed call is ignored.
        async for chunk in agent.stream_chat("stream hello"):  # type: ignore[attr-defined]
            chunks.append(chunk)

        self.assertEqual(chunks, ["chunk1", "chunk2"])
        # Asserting call on the mock_stream_chat_impl directly is tricky with async generators.
        # The fact that we got the chunks is proof it was called.
        # If specific call assertion is needed, one might need to inspect mock_agent_instance.stream_chat.call_args

    async def test_agent_creation_with_nonexistent_document(self):
        # This will call the actual factory, which should raise Document.DoesNotExist
        # We need to specify pydantic_ai as the framework
        with self.assertRaises(Document.DoesNotExist):
            await agents.for_document(99999, self.corpus1.id, framework="pydantic_ai")


class TestToolAPIHypermodern(TestAPISetup):
    def test_get_standard_document_tools(self):
        # Patch create_document_tools where it's imported and used by ToolAPI in api.py
        with patch(
            "opencontractserver.llms.api.create_document_tools"
        ) as mock_api_create_doc_tools:
            core_tool_mock = CoreTool.from_function(lambda x: x, name="mock_doc_tool")
            mock_api_create_doc_tools.return_value = [core_tool_mock]

            retrieved_tools = tools.document_tools()

            mock_api_create_doc_tools.assert_called_once()
            self.assertIsInstance(retrieved_tools, list)
            self.assertEqual(len(retrieved_tools), 1)
            self.assertIs(retrieved_tools[0], core_tool_mock)

    def test_create_tool_from_function_defaults(self):
        tool = tools.from_function(self.dummy_tool_func)
        self.assertIsInstance(tool, CoreTool)
        self.assertEqual(tool.name, "dummy_tool_func")
        self.assertEqual(tool.description, "A dummy tool function for testing.")
        # Basic check for parameter schema generation
        self.assertIn("text", tool.parameters["properties"])

    def test_create_tool_from_function_overrides(self):
        tool = tools.from_function(
            self.dummy_tool_func,
            name="custom_dummy_name",
            description="Overridden description.",
            parameter_descriptions={"text": "Input text string."},
        )
        self.assertEqual(tool.name, "custom_dummy_name")
        self.assertEqual(tool.description, "Overridden description.")
        self.assertEqual(
            tool.parameters["properties"]["text"]["description"], "Input text string."
        )


class TestVectorStoreAPIHypermodern(TestAPISetup):
    @patch(
        f"{UnifiedVectorStoreFactory.__module__}.{UnifiedVectorStoreFactory.__name__}.create_vector_store"
    )
    def test_create_vector_store_defaults(self, mock_create_vs: MagicMock):
        mock_vs_instance = MagicMock()
        mock_create_vs.return_value = mock_vs_instance

        store = vector_stores.create(corpus_id=self.corpus1.id)

        mock_create_vs.assert_called_once()
        call_kwargs = mock_create_vs.call_args.kwargs
        self.assertEqual(call_kwargs["framework"], AgentFramework.PYDANTIC_AI)
        self.assertEqual(call_kwargs["corpus_id"], self.corpus1.id)
        self.assertIs(store, mock_vs_instance)

    @patch(
        f"{UnifiedVectorStoreFactory.__module__}.{UnifiedVectorStoreFactory.__name__}.create_vector_store"
    )
    def test_create_vector_store_pydantic_ai(self, mock_create_vs: MagicMock):
        mock_vs_instance = MagicMock()
        mock_create_vs.return_value = mock_vs_instance

        store = vector_stores.create(framework="pydantic_ai", document_id=self.doc1.id)

        mock_create_vs.assert_called_once()
        call_kwargs = mock_create_vs.call_args.kwargs
        self.assertEqual(call_kwargs["framework"], AgentFramework.PYDANTIC_AI)
        self.assertEqual(call_kwargs["document_id"], self.doc1.id)
        self.assertIs(store, mock_vs_instance)

    @patch(
        f"{UnifiedVectorStoreFactory.__module__}.{UnifiedVectorStoreFactory.__name__}.create_vector_store"
    )
    def test_create_vector_store_all_params(self, mock_create_vs: MagicMock):
        mock_vs_instance = MagicMock()
        mock_create_vs.return_value = mock_vs_instance

        store = vector_stores.create(
            framework="pydantic_ai",
            user_id=self.user.id,
            corpus_id=self.corpus1.id,
            document_id=self.doc1.id,
            embedder_path="custom/embedder/path",
            must_have_text="specific_text",
            embed_dim=1536,
            custom_vs_arg="vs_value",
        )

        mock_create_vs.assert_called_once()
        call_kwargs = mock_create_vs.call_args.kwargs
        self.assertEqual(call_kwargs["framework"], AgentFramework.PYDANTIC_AI)
        self.assertEqual(call_kwargs["user_id"], self.user.id)
        self.assertEqual(call_kwargs["corpus_id"], self.corpus1.id)
        self.assertEqual(call_kwargs["document_id"], self.doc1.id)
        self.assertEqual(call_kwargs["embedder_path"], "custom/embedder/path")
        self.assertEqual(call_kwargs["must_have_text"], "specific_text")
        self.assertEqual(call_kwargs["embed_dim"], 1536)
        self.assertEqual(call_kwargs["custom_vs_arg"], "vs_value")
        self.assertIs(store, mock_vs_instance)
