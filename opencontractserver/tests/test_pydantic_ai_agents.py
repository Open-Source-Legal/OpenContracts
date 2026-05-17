"""Tests for PydanticAI agent implementations following modern patterns."""

import random
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from pydantic import BaseModel
from pydantic_ai.agent import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.agents.agent_factory import UnifiedAgentFactory
from opencontractserver.llms.agents.core_agents import UnifiedChatResponse
from opencontractserver.llms.agents.pydantic_ai_agents import PydanticAIDocumentAgent
from opencontractserver.llms.tools.pydantic_ai_tools import (
    PydanticAIToolFactory,
    PydanticAIToolWrapper,
)
from opencontractserver.llms.tools.tool_factory import CoreTool
from opencontractserver.llms.types import AgentFramework
from opencontractserver.llms.vector_stores.pydantic_ai_vector_stores import (
    PydanticAIAnnotationVectorStore,
    PydanticAIVectorSearchRequest,
)
from opencontractserver.llms.vector_stores.vector_store_factory import (
    UnifiedVectorStoreFactory,
)
from opencontractserver.pipeline.utils import get_default_embedder_path

User = get_user_model()


def random_vector(dimension: int = 384, seed: int = 42) -> list[float]:
    """Generate a random vector for testing."""
    rng = random.Random(seed)
    return [rng.random() for _ in range(dimension)]


def constant_vector(dimension: int = 384, value: float = 0.5) -> list[float]:
    """Generate a constant vector for testing."""
    return [value] * dimension


@dataclass
class TestDependencies:
    """Test dependencies for PydanticAI agents."""

    user_id: int
    document_id: Optional[int] = None
    corpus_id: Optional[int] = None
    api_key: str = "test-key"


class UserProfile(BaseModel):
    """Test structured output model."""

    name: str
    interests: list[str]


class _DummyRunResult:
    """Mock run result for testing."""

    def __init__(self, data: str):
        self.data = data
        self.output = data  # Add output attribute for compatibility
        self.sources = []

    def usage(self):
        return None


class _DummyStreamResult:
    """Mock stream result for testing."""

    def __init__(self, data: str):
        self.data = data
        self.sources = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def stream_text(
        self, delta: bool = True, debounce_by: Optional[float] = None
    ):
        for ch in self.data:
            yield ch

    def usage(self):
        return None

    # ------------------------------------------------------------------ #
    # Additional helpers expected by PydanticAICoreAgent.stream()
    # ------------------------------------------------------------------ #
    async def get_output(self) -> str:  # noqa: D401 – simple passthrough
        """Return the full output accumulated during streaming."""
        return self.data

    def all_messages(self):  # noqa: D401 – simple passthrough
        """Return an empty message history for tests that don't need it."""
        return []


@pytest.mark.serial
class TestPydanticAIAgents(TransactionTestCase):
    """Test suite for PydanticAI agent implementations.

    Uses TransactionTestCase because async test methods with Django ORM calls
    don't work well with TestCase's transaction-based isolation. The async code
    runs in a different thread context that can't share the test transaction.

    Marked as serial because PydanticAI's run_sync() requires an active event loop,
    which pytest-xdist workers may close between test batches.
    """

    def setUp(self) -> None:
        """Create test data for each test.

        Using setUp instead of setUpTestData because TransactionTestCase
        doesn't support the transaction-based isolation that setUpTestData relies on.

        We close old connections at the start to ensure fresh connections after
        any async operations from previous tests may have corrupted them.
        """
        from django import db

        db.close_old_connections()

        # Use unique username to avoid conflicts with fixtures
        self.user = User.objects.create_user(
            username="pydantic_ai_test_user",
            password="testpass",
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="A test corpus for agent testing",
            creator=self.user,
            is_public=True,
        )

        # processing_started is set to short-circuit the
        # process_doc_on_create_atomic post_save signal which would otherwise
        # try to ingest a non-existent PDF file via the (eager) celery chain
        # under TransactionTestCase. The signal exits early when this field
        # is non-null on the create call.
        self.doc1 = Document.objects.create(
            title="Test Document 1",
            description="First test document",
            creator=self.user,
            is_public=True,
            processing_started=timezone.now(),
        )

        self.doc2 = Document.objects.create(
            title="Test Document 2",
            description="Second test document",
            creator=self.user,
            is_public=True,
            processing_started=timezone.now(),
        )

        # Add documents to corpus
        self.corpus.add_document(document=self.doc1, user=self.user)
        self.corpus.add_document(document=self.doc2, user=self.user)

        # Create DocumentPath records for dual-tree versioning
        # This is required for the vector store to find documents
        DocumentPath.objects.create(
            document=self.doc1,
            corpus=self.corpus,
            path="/test_doc1.pdf",
            version_number=1,
            is_deleted=False,
            is_current=True,
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=self.doc2,
            corpus=self.corpus,
            path="/test_doc2.pdf",
            version_number=1,
            is_deleted=False,
            is_current=True,
            creator=self.user,
        )

        # Create annotation labels
        self.label_important = AnnotationLabel.objects.create(
            text="Important Label",
            creator=self.user,
        )

        self.label_summary = AnnotationLabel.objects.create(
            text="Summary",
            creator=self.user,
        )

        # Create annotations with text content
        self.anno1 = Annotation.objects.create(
            document=self.doc1,
            corpus=self.corpus,
            creator=self.user,
            raw_text="This is the first annotation text about important topics",
            annotation_label=self.label_important,
            is_public=True,
        )

        self.anno2 = Annotation.objects.create(
            document=self.doc1,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Another annotation in the same document about different topics",
            annotation_label=self.label_summary,
            is_public=True,
        )

        self.anno3 = Annotation.objects.create(
            document=self.doc2,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Annotation text for doc2, also marked as important",
            annotation_label=self.label_important,
            is_public=True,
        )

        # Add embeddings to annotations
        # Use get_default_embedder_path() to match what vector store searches for
        embedder_path = get_default_embedder_path()
        self.anno1.add_embedding(embedder_path, constant_vector(384, 0.1))
        self.anno2.add_embedding(embedder_path, constant_vector(384, 0.2))
        self.anno3.add_embedding(embedder_path, constant_vector(384, 0.3))

        self.test_deps = TestDependencies(
            user_id=self.user.id,
            document_id=self.doc1.id,
            corpus_id=self.corpus.id,
        )

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    def test_pydantic_ai_document_agent_creation(
        self,
        mock_pyd_ai_cls: MagicMock,
    ) -> None:
        """Ensure we can build a document agent with mocked internals."""
        # Produce the mock `PydanticAIAgent` instance
        mock_pyd_ai_instance = MagicMock()
        mock_pyd_ai_cls.return_value = mock_pyd_ai_instance

        # Fake context & conversation-manager
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            DocumentAgentContext,
        )

        cfg = MagicMock(spec=AgentConfig)
        cfg.store_user_messages = True
        cfg.store_llm_messages = True

        mock_ctx = MagicMock(spec=DocumentAgentContext)
        mock_ctx.document = self.doc1
        mock_ctx.config = cfg

        mock_conv_mgr = MagicMock(spec=CoreConversationManager)

        # Build the agent
        agent = PydanticAIDocumentAgent(
            context=mock_ctx,
            conversation_manager=mock_conv_mgr,
            pydantic_ai_agent=mock_pyd_ai_instance,
            agent_deps=MagicMock(),  # dependencies object
        )

        # Basic sanity checks
        self.assertIs(agent.context, mock_ctx)
        self.assertIs(agent.conversation_manager, mock_conv_mgr)
        self.assertIs(agent.pydantic_ai_agent, mock_pyd_ai_instance)

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_pydantic_ai_agent_with_test_model(
        self, mock_agent_class: MagicMock
    ) -> None:
        """Test PydanticAI agent using TestModel for testing."""
        # Create a real PydanticAI agent with TestModel for testing
        test_agent = Agent(
            model=TestModel(),
            deps_type=TestDependencies,
            system_prompt="You are a helpful assistant.",
        )

        # Test basic functionality
        with test_agent.override(deps=self.test_deps):
            result = await test_agent.run("Hello, how are you?")
            self.assertIsInstance(result.output, str)
            self.assertTrue(len(result.output) > 0)

    def test_pydantic_ai_tool_wrapper_creation(self) -> None:
        """Test PydanticAIToolWrapper creation and factory behavior."""
        from opencontractserver.llms.tools.core_tools import (
            aget_md_summary_token_length,
        )

        core_tool = CoreTool.from_function(aget_md_summary_token_length)

        # Instantiate the wrapper directly
        wrapper = PydanticAIToolWrapper(core_tool)

        # --- Assertions for the PydanticAIToolWrapper instance ---
        # Check name: func.__name__ is "aget_md_summary_token_length"
        self.assertEqual(
            wrapper.name,
            "aget_md_summary_token_length",
            f"Wrapper name mismatch. Expected 'aget_md_summary_token_length', got '{wrapper.name}'",
        )

        # Check description: assuming it exists and contains specific text
        self.assertIsNotNone(
            wrapper.description, "Tool description should not be None."
        )
        # This assertion implies 'get_md_summary_token_length' has a docstring containing "token length"
        self.assertIn(
            "token length",
            wrapper.description.lower(),
            "Tool description does not contain expected text 'token length'.",
        )

        # Check the to_dict() method of the wrapper
        tool_dict = wrapper.to_dict()
        expected_keys = {"function", "name", "description"}
        self.assertSetEqual(
            set(tool_dict.keys()),
            expected_keys,
            f"wrapper.to_dict() keys mismatch. Expected {expected_keys}, got {set(tool_dict.keys())}",
        )

        # --- Assertions for the PydanticAIToolFactory ---
        # Factory should return a callable function
        callable_tool = PydanticAIToolFactory.create_tool(core_tool)
        self.assertTrue(
            callable(callable_tool),
            "PydanticAIToolFactory.create_tool() should return a callable function.",
        )

        # The callable function's signature should start with 'ctx'
        import inspect

        sig = inspect.signature(callable_tool)
        try:
            first_param_name = next(iter(sig.parameters.keys()))
            self.assertEqual(
                first_param_name,
                "ctx",
                f"First parameter of the callable tool should be 'ctx', got '{first_param_name}'.",
            )
        except StopIteration:
            self.fail("Callable tool has no parameters, expected 'ctx' as the first.")

    @patch("opencontractserver.llms.tools.core_tools.Document.objects.get")
    async def test_pydantic_ai_tool_with_agent(self, mock_doc_get: MagicMock) -> None:
        """Test PydanticAI tools working with an agent."""
        # Mock document retrieval
        mock_doc = MagicMock()
        mock_doc.md_summary_file.open.return_value.__enter__.return_value.read.return_value = (
            "Test document content"
        )
        mock_doc_get.return_value = mock_doc

        # Create agent with tools
        async def mock_load_summary(
            ctx: RunContext[TestDependencies],
            document_id: int,
            truncate_length: Optional[int] = None,
            from_start: bool = True,
        ) -> str:
            """Mock document loading tool."""
            return f"Mock summary for document {document_id}"

        agent = Agent(
            model=TestModel(),
            deps_type=TestDependencies,
            tools=[mock_load_summary],
        )

        with agent.override(deps=self.test_deps):
            result = await agent.run(f"Load summary for document {self.doc1.id}")

            self.assertIsInstance(result.output, str)
            # TestModel should call the tool
            self.assertIn("Mock summary", result.output)

    def test_pydantic_ai_vector_store_creation(self) -> None:
        """Test creating PydanticAI vector store through factory."""
        vector_store = UnifiedVectorStoreFactory.create_vector_store(
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
            corpus_id=self.corpus.id,
        )

        self.assertIsInstance(vector_store, PydanticAIAnnotationVectorStore)
        self.assertEqual(vector_store.user_id, self.user.id)
        self.assertEqual(vector_store.corpus_id, self.corpus.id)

    async def test_pydantic_ai_vector_store_search(self) -> None:
        """Test vector search functionality with PydanticAI vector store."""
        from asgiref.sync import sync_to_async

        vector_store = await sync_to_async(PydanticAIAnnotationVectorStore)(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
        )

        # Test search with query text
        response = await vector_store.search_annotations(
            query_text="important topics",
            similarity_top_k=5,
        )

        self.assertGreater(response.total_results, 0)
        self.assertIsInstance(response.results, list)

        # Check result structure
        if response.results:
            result = response.results[0]
            self.assertIn("annotation_id", result)
            self.assertIn("content", result)
            self.assertIn("similarity_score", result)

    async def test_pydantic_ai_vector_search_tool_creation(self) -> None:
        """Test creating vector search tools for PydanticAI agents."""
        from opencontractserver.llms.vector_stores.pydantic_ai_vector_stores import (
            create_vector_search_tool,
        )

        # Create vector search tool
        search_tool = await create_vector_search_tool(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
        )

        self.assertTrue(callable(search_tool))

        # Test tool signature
        import inspect

        sig = inspect.signature(search_tool)
        params = list(sig.parameters.keys())

        self.assertIn("ctx", params)
        self.assertIn("query_text", params)

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    async def test_pydantic_ai_agent_with_vector_search_tool(
        self, mock_gen_embeds: MagicMock
    ) -> None:
        """Test PydanticAI agent using vector search tools."""
        # Mock embedding generation
        mock_gen_embeds.return_value = ("test_embedder", constant_vector(384, 0.15))

        # Create vector search tool
        async def vector_search_tool(
            ctx: RunContext[TestDependencies],
            query_text: str,
            similarity_top_k: int = 5,
        ) -> str:
            """Mock vector search tool for testing."""
            # Simulate search results
            return f"Found {similarity_top_k} results for query: {query_text}"

        # Create agent with vector search capability
        agent = Agent(
            model=TestModel(),
            deps_type=TestDependencies,
            tools=[vector_search_tool],
            system_prompt="You are a document search assistant. Use vector search to find relevant information.",
        )

        with agent.override(deps=self.test_deps):
            result = await agent.run("Search for documents about important topics")

            self.assertIsInstance(result.output, str)
            # Should contain search results
            self.assertIn("Found", result.output)

    async def test_pydantic_ai_structured_output(self) -> None:
        """Test PydanticAI agents with structured outputs."""
        # Create agent that returns structured data
        agent = Agent(
            model=TestModel(),
            output_type=UserProfile,
            instructions="Extract user profile information.",
        )

        result = await agent.run("My name is John and I like reading and coding")

        self.assertIsInstance(result.output, UserProfile)
        self.assertIsInstance(result.output.name, str)
        self.assertIsInstance(result.output.interests, list)

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_pydantic_ai_error_handling(
        self,
        mock_pyd_ai_cls: MagicMock,
    ) -> None:
        """`chat` and `stream` should succeed even if the LLM is mocked."""
        # Configure mock agent
        mock_llm = MagicMock()
        mock_llm.run = AsyncMock(
            return_value=_DummyRunResult("PydanticAI Placeholder"),
        )
        mock_llm.run_stream = MagicMock(
            return_value=_DummyStreamResult("PydanticAI Placeholder"),
        )
        mock_pyd_ai_cls.return_value = mock_llm

        # Build minimal context & manager
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            DocumentAgentContext,
        )
        from opencontractserver.llms.context_guardrails import CompactionConfig

        cfg = MagicMock(spec=AgentConfig)
        cfg.store_user_messages = cfg.store_llm_messages = True
        cfg.user_id = self.user.id
        cfg.compaction = CompactionConfig()

        ctx = MagicMock(spec=DocumentAgentContext)
        ctx.document = self.doc1
        ctx.config = cfg

        # Conversation-manager mock needs a few async helpers and config so that
        # CoreAgentBase.chat()/stream() can interact without AttributeErrors.
        conv_mgr = MagicMock(spec=CoreConversationManager)

        # Minimal conversation context – None disables DB persistence paths.
        conv_mgr.conversation = None  # behave like anonymous session

        # Attach the **same** config object so attribute access works.
        conv_mgr.config = cfg

        # Async variants for any IO helpers that CoreAgentBase may call during
        # chat/stream.  We stub them out so the test remains pure unit.
        conv_mgr.get_conversation_messages = AsyncMock(return_value=[])
        conv_mgr.update_message_content = AsyncMock()
        conv_mgr.complete_message = AsyncMock()
        conv_mgr.cancel_message = AsyncMock()
        conv_mgr.update_message = AsyncMock()

        agent = PydanticAIDocumentAgent(
            context=ctx,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=mock_llm,
            agent_deps=MagicMock(),
        )

        # Patch I/O helpers to avoid touching the DB
        agent.store_user_message = AsyncMock(return_value="user-1")
        agent.store_llm_message = AsyncMock(return_value="llm-1")
        agent.update_message = AsyncMock()

        # Chat
        chat_resp = await agent.chat("test")
        self.assertIsInstance(chat_resp, UnifiedChatResponse)
        self.assertIn("PydanticAI Placeholder", chat_resp.content)

        # Stream
        streamed = [chunk async for chunk in agent.stream("test")]
        self.assertTrue(any(c.is_complete for c in streamed))

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_pydantic_ai_chat_error_wrapping(
        self, mock_pyd_ai_cls: MagicMock
    ) -> None:
        """`chat` should return an *error* response, not raise."""

        # Mock the underlying LLM to raise
        erring_llm = MagicMock()
        erring_llm.run = AsyncMock(side_effect=Exception("LLM failure"))
        mock_pyd_ai_cls.return_value = erring_llm

        # Build minimal agent (reuse helpers from previous test)
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            DocumentAgentContext,
        )
        from opencontractserver.llms.context_guardrails import CompactionConfig

        cfg = MagicMock(spec=AgentConfig)
        cfg.store_user_messages = cfg.store_llm_messages = False  # simplify
        cfg.user_id = self.user.id
        # Provide a real CompactionConfig so _get_message_history doesn't
        # try arithmetic with MagicMock values.
        cfg.compaction = CompactionConfig()

        ctx = MagicMock(spec=DocumentAgentContext)
        ctx.document = self.doc1
        ctx.config = cfg

        conv_mgr = MagicMock(spec=CoreConversationManager)
        conv_mgr.conversation = None
        conv_mgr.config = cfg
        # Stub async helpers that _get_message_history calls so the code
        # path reaches the LLM call (which is what we're testing).
        conv_mgr.get_conversation_messages = AsyncMock(return_value=[])

        agent = PydanticAIDocumentAgent(
            context=ctx,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=erring_llm,
            agent_deps=MagicMock(),
        )

        # Chat – should *not* raise
        resp = await agent.chat("trigger error")

        from opencontractserver.llms.agents.core_agents import UnifiedChatResponse

        self.assertIsInstance(resp, UnifiedChatResponse)
        self.assertEqual(resp.metadata.get("error"), "LLM failure")
        self.assertTrue(resp.content.startswith("Error:"))

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_pydantic_ai_agent_factory_integration(
        self,
        mock_pyd_ai_cls: MagicMock,
    ) -> None:
        """UnifiedAgentFactory should return a working PydanticAI agent."""
        # Mock LLM behaviour
        dummy = MagicMock()
        dummy.run = AsyncMock(return_value=_DummyRunResult("PydanticAI Placeholder"))
        mock_pyd_ai_cls.return_value = dummy

        # Build agent via factory
        agent = await UnifiedAgentFactory.create_document_agent(
            self.doc1,
            self.corpus,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )
        self.assertIsInstance(agent, PydanticAIDocumentAgent)

        # Monkey-patch message helpers
        agent.store_user_message = AsyncMock(return_value="u-id")
        agent.store_llm_message = AsyncMock(return_value="l-id")
        agent.update_message = AsyncMock()
        agent.conversation_manager.get_conversation_messages = AsyncMock(
            return_value=[],
        )

        # Verify `chat`
        resp = await agent.chat("What is this document about?")
        self.assertIsInstance(resp, UnifiedChatResponse)
        self.assertIn("PydanticAI Placeholder", resp.content)

    @override_settings(
        OPENAI_API_KEY="test-key",
        ANTHROPIC_API_KEY="test-key",
    )
    async def test_pydantic_ai_dependencies_injection(self) -> None:
        """Test dependency injection with PydanticAI agents."""
        # Create agent with dependencies
        agent = Agent(
            model=TestModel(),
            deps_type=TestDependencies,
            system_prompt="You have access to user context through dependencies.",
        )

        # Test with different dependencies
        deps1 = TestDependencies(user_id=self.user.id, document_id=self.doc1.id)
        deps2 = TestDependencies(user_id=self.user.id, corpus_id=self.corpus.id)

        with agent.override(deps=deps1):
            result1 = await agent.run("What document am I working with?")
            self.assertIsInstance(result1.output, str)

        with agent.override(deps=deps2):
            result2 = await agent.run("What corpus am I working with?")
            self.assertIsInstance(result2.output, str)

    def test_pydantic_ai_vector_search_request_validation(self) -> None:
        """Test PydanticAI vector search request validation."""
        # Valid request
        request = PydanticAIVectorSearchRequest(
            query_text="test query",
            similarity_top_k=10,
            filters={"label": "Important Label"},
        )

        self.assertEqual(request.query_text, "test query")
        self.assertEqual(request.similarity_top_k, 10)
        self.assertEqual(request.filters["label"], "Important Label")

        # Request with embedding instead of text
        embedding_request = PydanticAIVectorSearchRequest(
            query_embedding=constant_vector(384, 0.5),
            similarity_top_k=5,
        )

        self.assertIsNone(embedding_request.query_text)
        self.assertEqual(len(embedding_request.query_embedding), 384)


@pytest.mark.serial
class TestPydanticAIAgentsCoverage(TransactionTestCase):
    """Additional tests to improve coverage of pydantic_ai_agents.py.

    Uses TransactionTestCase because async test methods with Django ORM calls
    don't work well with TestCase's transaction-based isolation.

    Marked as serial because PydanticAI's run_sync() requires an active event loop.
    """

    def setUp(self) -> None:
        """Create test data for each test.

        We close old connections at the start to ensure fresh connections after
        any async operations from previous tests may have corrupted them.
        """
        from django import db

        db.close_old_connections()

        self.user = User.objects.create_user(
            username="coverageuser",
            password="testpass",
        )
        self.corpus = Corpus.objects.create(
            title="Coverage Test Corpus",
            description="Test corpus for coverage",
            creator=self.user,
            is_public=True,
        )
        # See comment on TestPydanticAIAgents.setUp for why processing_started
        # is set explicitly.
        self.doc1 = Document.objects.create(
            title="Coverage Document",
            description="Test document for coverage",
            creator=self.user,
            is_public=True,
            processing_started=timezone.now(),
        )
        self.corpus.add_document(document=self.doc1, user=self.user)

    # ========================================================================
    # Group 1: Helper function tests (_to_source_node)
    # ========================================================================

    def test_to_source_node_with_source_node_input(self) -> None:
        """Test _to_source_node with SourceNode input (passthrough)."""
        from opencontractserver.llms.agents.core_agents import SourceNode
        from opencontractserver.llms.agents.pydantic_ai_agents import _to_source_node

        source = SourceNode(
            annotation_id=123,
            content="test content",
            metadata={"page": 5},
            similarity_score=0.95,
        )

        result = _to_source_node(source)
        self.assertIs(result, source)
        self.assertEqual(result.annotation_id, 123)
        self.assertEqual(result.content, "test content")

    def test_to_source_node_with_dict_content_key(self) -> None:
        """Test _to_source_node with dict containing 'content' key."""
        from opencontractserver.llms.agents.pydantic_ai_agents import _to_source_node

        raw_dict = {
            "annotation_id": 456,
            "content": "dict content",
            "similarity_score": 0.85,
            "page": 3,
        }

        result = _to_source_node(raw_dict)
        self.assertEqual(result.annotation_id, 456)
        self.assertEqual(result.content, "dict content")
        self.assertEqual(result.similarity_score, 0.85)
        self.assertEqual(result.metadata["page"], 3)

    def test_to_source_node_with_dict_rawtext_key(self) -> None:
        """Test _to_source_node with dict containing 'rawText' key."""
        from opencontractserver.llms.agents.pydantic_ai_agents import _to_source_node

        raw_dict = {
            "annotation_id": 789,
            "rawText": "raw text content",
            "similarity_score": 0.75,
        }

        result = _to_source_node(raw_dict)
        self.assertEqual(result.annotation_id, 789)
        self.assertEqual(result.content, "raw text content")

    def test_to_source_node_with_pydantic_model(self) -> None:
        """Test _to_source_node with Pydantic model that has model_dump."""
        from pydantic import BaseModel

        from opencontractserver.llms.agents.pydantic_ai_agents import _to_source_node

        class TestSource(BaseModel):
            annotation_id: int
            content: str
            similarity_score: float = 1.0

        model = TestSource(annotation_id=111, content="pydantic content")
        result = _to_source_node(model)

        self.assertEqual(result.annotation_id, 111)
        self.assertEqual(result.content, "pydantic content")

    # ========================================================================
    # Group 2: _check_tool_requires_approval tests
    # ========================================================================

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    def test_check_tool_requires_approval_via_config_tools(
        self, mock_agent_cls: MagicMock
    ) -> None:
        """Test _check_tool_requires_approval finds approval requirement in config.tools."""
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.tools.tool_factory import CoreTool

        # Create a tool with requires_approval
        def test_tool():
            """Test tool."""
            pass

        core_tool = CoreTool.from_function(test_tool)
        core_tool.requires_approval = True

        # Create a mock wrapper
        mock_tool = MagicMock()
        mock_tool.__name__ = "test_tool"
        mock_tool.core_tool = core_tool

        config = AgentConfig(user_id=self.user.id, tools=[mock_tool])

        mock_pydantic_agent = MagicMock()
        mock_pydantic_agent.toolsets = []
        mock_agent_cls.return_value = mock_pydantic_agent

        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=MagicMock(),
            pydantic_ai_agent=mock_pydantic_agent,
            agent_deps=MagicMock(),
        )

        result = agent._check_tool_requires_approval("test_tool")
        self.assertTrue(result)

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    def test_check_tool_requires_approval_default_false(
        self, mock_agent_cls: MagicMock
    ) -> None:
        """Test _check_tool_requires_approval returns False by default."""
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        config = AgentConfig(user_id=self.user.id)

        mock_pydantic_agent = MagicMock()
        mock_pydantic_agent.toolsets = []
        mock_agent_cls.return_value = mock_pydantic_agent

        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=MagicMock(),
            pydantic_ai_agent=mock_pydantic_agent,
            agent_deps=MagicMock(),
        )

        result = agent._check_tool_requires_approval("nonexistent_tool")
        self.assertFalse(result)

    # ========================================================================
    # Group 3: Message initialization tests
    # ========================================================================

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_initialise_llm_message_with_existing_human(
        self, mock_agent_cls: MagicMock
    ) -> None:
        """Test _initialise_llm_message reuses existing HUMAN message."""
        from opencontractserver.conversations.models import ChatMessage, Conversation
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        # Create conversation and message
        conversation = await Conversation.objects.acreate(
            title="Test Conversation",
            creator=self.user,
        )

        human_msg = await ChatMessage.objects.acreate(
            conversation=conversation,
            content="test message",
            msg_type="HUMAN",
            creator=self.user,
        )

        config = AgentConfig(user_id=self.user.id, conversation=conversation)
        conv_mgr = await CoreConversationManager.create_for_document(
            corpus=self.corpus,
            document=self.doc1,
            user_id=self.user.id,
            config=config,
            override_conversation=conversation,
        )

        mock_pydantic_agent = MagicMock()
        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=mock_pydantic_agent,
            agent_deps=MagicMock(),
        )

        user_id, llm_id = await agent._initialise_llm_message("test")

        # Should reuse the existing HUMAN message
        self.assertEqual(user_id, human_msg.id)
        self.assertIsInstance(llm_id, int)

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_initialise_llm_message_fallback_creates_new(
        self, mock_agent_cls: MagicMock
    ) -> None:
        """Test _initialise_llm_message creates new message when no HUMAN exists."""
        from opencontractserver.conversations.models import Conversation
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        # Create conversation without messages
        conversation = await Conversation.objects.acreate(
            title="Empty Conversation",
            creator=self.user,
        )

        config = AgentConfig(user_id=self.user.id, conversation=conversation)
        conv_mgr = await CoreConversationManager.create_for_document(
            corpus=self.corpus,
            document=self.doc1,
            user_id=self.user.id,
            config=config,
            override_conversation=conversation,
        )

        mock_pydantic_agent = MagicMock()
        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=mock_pydantic_agent,
            agent_deps=MagicMock(),
        )

        # Mock store_user_message since fallback will create one
        agent.store_user_message = AsyncMock(return_value=999)

        user_id, llm_id = await agent._initialise_llm_message("test")

        # Should create new user message via fallback
        self.assertEqual(user_id, 999)
        agent.store_user_message.assert_called_once_with("test")

    # ========================================================================
    # Group 4: resume_with_approval tests
    # ========================================================================

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_resume_with_approval_approved_success(
        self, mock_agent_cls: MagicMock
    ) -> None:
        """Test resume_with_approval with approved tool execution that succeeds."""
        from opencontractserver.conversations.models import ChatMessage, Conversation
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            MessageState,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        # Create conversation and paused message
        conversation = await Conversation.objects.acreate(
            title="Approval Test",
            creator=self.user,
        )

        paused_msg = await ChatMessage.objects.acreate(
            conversation=conversation,
            content="Awaiting approval",
            msg_type="LLM",
            creator=self.user,
            data={
                "state": MessageState.AWAITING_APPROVAL,
                "pending_tool_call": {
                    "name": "test_tool",
                    "arguments": {"arg1": "value1"},
                    "tool_call_id": "call-123",
                },
            },
        )

        config = AgentConfig(user_id=self.user.id, conversation=conversation)
        conv_mgr = await CoreConversationManager.create_for_document(
            corpus=self.corpus,
            document=self.doc1,
            user_id=self.user.id,
            config=config,
            override_conversation=conversation,
        )

        mock_pydantic_agent = MagicMock()
        mock_pydantic_agent.toolsets = []

        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=mock_pydantic_agent,
            agent_deps=MagicMock(),
        )

        # Mock the tool function
        def mock_tool_function(ctx, arg1):
            return {"status": "success", "value": arg1}

        # Mock _stream_core to yield a simple final event
        from opencontractserver.llms.agents.core_agents import FinalEvent

        async def mock_stream_core(*args, **kwargs):
            yield FinalEvent(
                content="Tool executed successfully",
                accumulated_content="Tool executed successfully",
            )

        agent._stream_core = mock_stream_core
        agent.create_placeholder_message = AsyncMock(return_value=999)

        # Add tool to config
        mock_tool_wrapper = MagicMock()
        mock_tool_wrapper.__name__ = "test_tool"
        mock_tool_wrapper.return_value = {"status": "success", "value": "value1"}
        config.tools = [mock_tool_wrapper]

        events = []
        async for event in agent.resume_with_approval(paused_msg.id, approved=True):
            events.append(event)

        # Should have approval result and final events
        self.assertTrue(len(events) > 0)
        self.assertTrue(
            any(e.type == "approval_result" for e in events if hasattr(e, "type"))
        )

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_resume_with_approval_rejected(
        self, mock_agent_cls: MagicMock
    ) -> None:
        """Test resume_with_approval with rejected tool execution."""
        from opencontractserver.conversations.models import ChatMessage, Conversation
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            MessageState,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        # Create conversation and paused message
        conversation = await Conversation.objects.acreate(
            title="Rejection Test",
            creator=self.user,
        )

        paused_msg = await ChatMessage.objects.acreate(
            conversation=conversation,
            content="Awaiting approval",
            msg_type="LLM",
            creator=self.user,
            data={
                "state": MessageState.AWAITING_APPROVAL,
                "pending_tool_call": {
                    "name": "dangerous_tool",
                    "arguments": {"action": "delete"},
                    "tool_call_id": "call-456",
                },
            },
        )

        config = AgentConfig(user_id=self.user.id, conversation=conversation)
        conv_mgr = await CoreConversationManager.create_for_document(
            corpus=self.corpus,
            document=self.doc1,
            user_id=self.user.id,
            config=config,
            override_conversation=conversation,
        )

        mock_pydantic_agent = MagicMock()
        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=mock_pydantic_agent,
            agent_deps=MagicMock(),
        )

        events = []
        async for event in agent.resume_with_approval(paused_msg.id, approved=False):
            events.append(event)

        # Should emit approval_result (rejected) and final events
        self.assertTrue(len(events) > 0)
        approval_events = [
            e for e in events if hasattr(e, "type") and e.type == "approval_result"
        ]
        self.assertTrue(len(approval_events) > 0)
        self.assertEqual(approval_events[0].decision, "rejected")

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_resume_with_approval_parses_json_string_args(
        self, mock_agent_cls: MagicMock
    ) -> None:
        """Test resume_with_approval parses JSON string arguments correctly."""
        import json

        from opencontractserver.conversations.models import ChatMessage, Conversation
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            MessageState,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        # Create conversation with JSON string arguments
        conversation = await Conversation.objects.acreate(
            title="JSON Args Test",
            creator=self.user,
        )

        tool_args = {"key": "value", "number": 42}
        paused_msg = await ChatMessage.objects.acreate(
            conversation=conversation,
            content="Awaiting approval",
            msg_type="LLM",
            creator=self.user,
            data={
                "state": MessageState.AWAITING_APPROVAL,
                "pending_tool_call": {
                    "name": "json_tool",
                    "arguments": json.dumps(tool_args),  # JSON string
                    "tool_call_id": "call-789",
                },
            },
        )

        config = AgentConfig(user_id=self.user.id, conversation=conversation)
        conv_mgr = await CoreConversationManager.create_for_document(
            corpus=self.corpus,
            document=self.doc1,
            user_id=self.user.id,
            config=config,
            override_conversation=conversation,
        )

        mock_pydantic_agent = MagicMock()
        mock_pydantic_agent.toolsets = []

        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=mock_pydantic_agent,
            agent_deps=MagicMock(),
        )

        # Mock tool
        mock_tool = MagicMock()
        mock_tool.__name__ = "json_tool"

        async def tool_impl(ctx, **kwargs):
            return kwargs

        mock_tool.return_value = tool_args
        config.tools = [mock_tool]

        # Mock _stream_core
        from opencontractserver.llms.agents.core_agents import FinalEvent

        async def mock_stream_core(*args, **kwargs):
            yield FinalEvent(content="Done", accumulated_content="Done")

        agent._stream_core = mock_stream_core
        agent.create_placeholder_message = AsyncMock(return_value=888)

        events = []
        async for event in agent.resume_with_approval(paused_msg.id, approved=True):
            events.append(event)

        self.assertTrue(len(events) > 0)

    # ========================================================================
    # Group 5: _structured_response_raw — Anthropic reliability fix (issue #1381)
    # ========================================================================

    async def _build_core_agent_for_structured_test(
        self,
        mock_pyd_ai_cls: MagicMock,
        *,
        model_name: Optional[str] = None,
        config_temperature: Optional[float] = None,
    ):
        """Build a ``PydanticAICoreAgent`` for ``_structured_response_raw`` tests.

        Patches the ``PydanticAIAgent`` symbol so the *structured* agent
        constructor is tracked, mocks history retrieval to avoid DB I/O,
        and stubs the seeded function-tools dict so deduplication is a
        no-op.  Returns the agent and the mock for the structured agent's
        ``run`` result so callers can assert on ``call_args``.
        """
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
            _HistoryResult,
        )

        # Structured agent built inside _structured_response_raw will hit
        # the patched class — wire up a runnable mock.
        structured_run_result = MagicMock()
        structured_run_result.output = "extracted-value"
        structured_agent_mock = MagicMock()
        structured_agent_mock.run = AsyncMock(return_value=structured_run_result)
        mock_pyd_ai_cls.return_value = structured_agent_mock

        config = AgentConfig(
            user_id=self.user.id,
            model_name=model_name,
            temperature=config_temperature,
        )
        conv_mgr = MagicMock(spec=CoreConversationManager)
        conv_mgr.conversation = None
        conv_mgr.config = config

        # The agent passed in at construction is unrelated to the
        # structured agent — it just has to expose a function-tools dict.
        prebuilt_agent = MagicMock()
        prebuilt_agent._function_tools = {}

        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=prebuilt_agent,
            agent_deps=MagicMock(),
        )
        # Skip DB-backed history retrieval; we only care about agent ctor args.
        agent._get_message_history = AsyncMock(
            return_value=_HistoryResult(messages=None)
        )
        return agent, structured_agent_mock

    @staticmethod
    def _structured_agent_call(mock_pyd_ai_cls: MagicMock):
        """Find the constructor call that built the structured agent.

        ``output_retries`` is set only on the structured agent so it makes
        a reliable signature.  Returns ``None`` if no such call was made.
        """
        for call in mock_pyd_ai_cls.call_args_list:
            if call.kwargs.get("output_retries") is not None:
                return call
        return None

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_structured_response_anthropic_forces_temperature_zero(
        self, mock_pyd_ai_cls: MagicMock
    ) -> None:
        """Anthropic + temperature=None ⇒ structured run gets temperature=0."""
        from opencontractserver.constants.llm import STRUCTURED_OUTPUT_RETRIES

        class DummyOutput(BaseModel):
            value: str

        agent, _ = await self._build_core_agent_for_structured_test(
            mock_pyd_ai_cls,
            model_name="anthropic:claude-sonnet-4-6",
        )

        await agent._structured_response_raw(
            prompt="any",
            target_type=DummyOutput,
            model="anthropic:claude-sonnet-4-6",
            temperature=None,
        )

        structured_call = self._structured_agent_call(mock_pyd_ai_cls)
        self.assertIsNotNone(
            structured_call,
            "Expected _structured_response_raw to build a PydanticAIAgent",
        )
        self.assertEqual(
            structured_call.kwargs["model_settings"]["temperature"],
            0,
            "Anthropic structured runs must force temperature=0 (issue #1381)",
        )
        self.assertEqual(
            structured_call.kwargs["output_retries"],
            STRUCTURED_OUTPUT_RETRIES,
            "Structured runs must use the configured retry budget",
        )
        self.assertEqual(
            structured_call.kwargs["model"],
            "anthropic:claude-sonnet-4-6",
        )

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_structured_response_explicit_temperature_not_overridden(
        self, mock_pyd_ai_cls: MagicMock
    ) -> None:
        """A caller-supplied temperature wins over the Anthropic override."""

        class DummyOutput(BaseModel):
            value: str

        agent, _ = await self._build_core_agent_for_structured_test(
            mock_pyd_ai_cls,
            model_name="anthropic:claude-sonnet-4-6",
        )

        await agent._structured_response_raw(
            prompt="any",
            target_type=DummyOutput,
            model="anthropic:claude-sonnet-4-6",
            temperature=0.5,
        )

        structured_call = self._structured_agent_call(mock_pyd_ai_cls)
        self.assertIsNotNone(structured_call)
        self.assertEqual(
            structured_call.kwargs["model_settings"]["temperature"],
            0.5,
            "Function-level temperature pin must NOT be overridden by Anthropic guard",
        )

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_structured_response_config_temperature_not_overridden(
        self, mock_pyd_ai_cls: MagicMock
    ) -> None:
        """``config.temperature`` (non-None) blocks the Anthropic override."""

        class DummyOutput(BaseModel):
            value: str

        agent, _ = await self._build_core_agent_for_structured_test(
            mock_pyd_ai_cls,
            model_name="anthropic:claude-sonnet-4-6",
            config_temperature=0.7,
        )

        await agent._structured_response_raw(
            prompt="any",
            target_type=DummyOutput,
            model="anthropic:claude-sonnet-4-6",
            temperature=None,
        )

        structured_call = self._structured_agent_call(mock_pyd_ai_cls)
        self.assertIsNotNone(structured_call)
        # config.temperature is propagated by _prepare_pydantic_ai_model_settings
        self.assertEqual(
            structured_call.kwargs["model_settings"]["temperature"],
            0.7,
            "config.temperature must be preserved when caller did not override",
        )

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    def test_document_agent_structured_prompt_commits_to_result(
        self, mock_pyd_ai_cls: MagicMock
    ) -> None:
        """``PydanticAIDocumentAgent._build_structured_system_prompt`` must
        instruct the model to commit to the result tool (issue #1381)."""
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            DocumentAgentContext,
        )

        cfg = MagicMock(spec=AgentConfig)
        cfg.store_user_messages = cfg.store_llm_messages = True

        ctx = MagicMock(spec=DocumentAgentContext)
        ctx.document = self.doc1
        ctx.config = cfg

        conv_mgr = MagicMock(spec=CoreConversationManager)

        agent = PydanticAIDocumentAgent(
            context=ctx,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=MagicMock(),
            agent_deps=MagicMock(),
        )

        class DummyOutput(BaseModel):
            value: str

        prompt = agent._build_structured_system_prompt(DummyOutput, "user query")

        self.assertIn("EXTRACTION PROTOCOL", prompt)
        self.assertIn("MUST", prompt)
        self.assertIn("result tool", prompt)
        self.assertIn(str(self.doc1.id), prompt)
        # Issue #1414: prompt must encourage committing as soon as the
        # answer is found (stop tool-loops) and prefer similarity_search
        # over byte-range reads for fact-finding.
        self.assertIn("COMMIT-EARLY", prompt)
        self.assertIn("similarity_search", prompt)
        self.assertIn("load_document_text", prompt)

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    def test_corpus_agent_structured_prompt_commits_to_result(
        self, mock_pyd_ai_cls: MagicMock
    ) -> None:
        """``PydanticAICorpusAgent._build_structured_system_prompt`` must
        instruct the model to commit to the result tool (issue #1381)."""
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            CorpusAgentContext,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICorpusAgent,
        )

        cfg = MagicMock(spec=AgentConfig)
        cfg.store_user_messages = cfg.store_llm_messages = True

        ctx = MagicMock(spec=CorpusAgentContext)
        ctx.corpus = self.corpus
        ctx.config = cfg

        conv_mgr = MagicMock(spec=CoreConversationManager)

        agent = PydanticAICorpusAgent(
            context=ctx,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=MagicMock(),
            agent_deps=MagicMock(),
        )

        class DummyOutput(BaseModel):
            value: str

        prompt = agent._build_structured_system_prompt(DummyOutput, "user query")

        self.assertIn("EXTRACTION PROTOCOL", prompt)
        self.assertIn("MUST", prompt)
        self.assertIn("result tool", prompt)
        self.assertIn(str(self.corpus.id), prompt)
        # Issue #1414: corpus extraction also gets the commit-early /
        # prefer-similarity_search guidance.
        self.assertIn("COMMIT-EARLY", prompt)
        self.assertIn("similarity_search", prompt)

    def test_core_agent_base_structured_prompt_commits_to_result(self) -> None:
        """Base ``_build_structured_system_prompt`` must also enforce commit."""
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        config = AgentConfig(user_id=self.user.id)
        conv_mgr = MagicMock(spec=CoreConversationManager)

        agent = PydanticAICoreAgent(
            config=config,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=MagicMock(),
            agent_deps=MagicMock(),
        )

        class DummyOutput(BaseModel):
            value: str

        prompt = agent._build_structured_system_prompt(DummyOutput, "user query")

        # Universal phrasing for both Anthropic and OpenAI: agent must
        # commit to the result tool after gathering data (issue #1381).
        self.assertIn("MUST", prompt)
        self.assertIn("result tool", prompt)
        # SEARCH PROTOCOL nudge: don't bail after a single failed query.
        self.assertIn("SEARCH PROTOCOL", prompt)
        self.assertIn(
            "multiple search attempts",
            prompt,
            "Negative case must require multiple attempts before committing to None",
        )
        # Issue #1414: stop the tool-loop pattern. The prompt must tell
        # the agent to commit as soon as it has a confident answer, and
        # prefer similarity_search over walking the document via
        # sequential byte-range reads.
        self.assertIn("COMMIT-EARLY", prompt)
        self.assertIn("similarity_search", prompt)
        self.assertIn("load_document_text", prompt)
        # The 2-3-search rule is bound to the negative case only. It must
        # NOT appear as an unconditional precondition to committing —
        # that's exactly the wording that produced the loop in #1414.
        self.assertNotIn(
            "Before concluding the requested information is absent, you "
            "MUST issue at least 2-3 distinct search queries that approach "
            "the question from different angles",
            prompt,
        )

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_structured_response_openai_skips_anthropic_override(
        self, mock_pyd_ai_cls: MagicMock
    ) -> None:
        """OpenAI models never get the Anthropic temperature=0 nudge."""

        class DummyOutput(BaseModel):
            value: str

        agent, _ = await self._build_core_agent_for_structured_test(
            mock_pyd_ai_cls,
            model_name="openai:gpt-4o-mini",
        )

        await agent._structured_response_raw(
            prompt="any",
            target_type=DummyOutput,
            model="openai:gpt-4o-mini",
            temperature=None,
        )

        structured_call = self._structured_agent_call(mock_pyd_ai_cls)
        self.assertIsNotNone(structured_call)
        # When neither the caller nor the config pin temperature/max_tokens,
        # model_settings should be passed through as ``None`` (matching the
        # pre-issue-#1381 contract with PydanticAIAgent), not as ``{}``.
        self.assertIsNone(
            structured_call.kwargs.get("model_settings"),
            "OpenAI structured runs without pins must pass model_settings=None",
        )

    @patch("opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent")
    async def test_document_agent_inherits_anthropic_temperature_guard(
        self, mock_pyd_ai_cls: MagicMock
    ) -> None:
        """``PydanticAIDocumentAgent`` inherits ``_structured_response_raw``
        from ``PydanticAICoreAgent``, so the Anthropic ``temperature=0``
        guard must fire when extraction runs on a document agent too.

        The base-class test covers the implementation itself; this test
        explicitly exercises the inheritance path so a future override
        on a subclass cannot silently regress the fix.
        """
        from opencontractserver.constants.llm import STRUCTURED_OUTPUT_RETRIES
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
            DocumentAgentContext,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import _HistoryResult

        # Wire up the structured-agent mock the same way the core helper does.
        structured_run_result = MagicMock()
        structured_run_result.output = "extracted-value"
        structured_agent_mock = MagicMock()
        structured_agent_mock.run = AsyncMock(return_value=structured_run_result)
        mock_pyd_ai_cls.return_value = structured_agent_mock

        config = AgentConfig(
            user_id=self.user.id,
            model_name="anthropic:claude-sonnet-4-6",
            temperature=None,
        )
        ctx = MagicMock(spec=DocumentAgentContext)
        ctx.document = self.doc1
        ctx.config = config
        conv_mgr = MagicMock(spec=CoreConversationManager)
        conv_mgr.conversation = None
        conv_mgr.config = config

        prebuilt_agent = MagicMock()
        prebuilt_agent._function_tools = {}

        agent = PydanticAIDocumentAgent(
            context=ctx,
            conversation_manager=conv_mgr,
            pydantic_ai_agent=prebuilt_agent,
            agent_deps=MagicMock(),
        )
        agent._get_message_history = AsyncMock(
            return_value=_HistoryResult(messages=None)
        )

        class DummyOutput(BaseModel):
            value: str

        await agent._structured_response_raw(
            prompt="any",
            target_type=DummyOutput,
            model="anthropic:claude-sonnet-4-6",
            temperature=None,
        )

        structured_call = self._structured_agent_call(mock_pyd_ai_cls)
        self.assertIsNotNone(
            structured_call,
            "Document agent must reach the inherited _structured_response_raw",
        )
        self.assertEqual(
            structured_call.kwargs["model_settings"]["temperature"],
            0,
            "Document agents must also force Anthropic temperature=0 (issue #1381)",
        )
        self.assertEqual(
            structured_call.kwargs["output_retries"],
            STRUCTURED_OUTPUT_RETRIES,
        )
