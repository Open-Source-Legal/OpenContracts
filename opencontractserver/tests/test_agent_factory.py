"""
Tests for the UnifiedAgentFactory and related tool conversion logic.
"""

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.agent_factory import (
    UnifiedAgentFactory,
    _user_has_write_permission,
)
from opencontractserver.llms.agents.core_agents import AgentConfig, CoreAgent
from opencontractserver.llms.api import ToolType
from opencontractserver.llms.tools.tool_factory import (
    CoreTool,
)
from opencontractserver.llms.types import AgentFramework
from opencontractserver.users.models import User


class TestUserHasWritePermission(TestCase):
    """Tests for the _user_has_write_permission helper function."""

    user: User
    corpus: Corpus
    doc: Document

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="write_perm_testuser",
            password="password",
            email="writeperm@test.com",
        )
        cls.corpus = Corpus.objects.create(
            title="Write Perm Test Corpus", creator=cls.user
        )
        original_doc = Document.objects.create(
            title="Write Perm Test Doc", creator=cls.user
        )
        cls.doc, _, _ = cls.corpus.add_document(document=original_doc, user=cls.user)

    async def test_returns_false_when_resource_is_none(self):
        """Test that _user_has_write_permission returns False when resource is None."""
        # Line 40 coverage: resource is None
        result = await _user_has_write_permission(self.user.id, None)
        self.assertFalse(result)

    async def test_returns_false_when_user_is_none(self):
        """Test that _user_has_write_permission returns False for anonymous users."""
        # Line 42-44 coverage: user_id is None (anonymous)
        result = await _user_has_write_permission(None, self.doc)
        self.assertFalse(result)

    async def test_returns_false_when_user_does_not_exist(self):
        """Test that _user_has_write_permission returns False when user doesn't exist."""
        # Lines 52-53 coverage: User.DoesNotExist
        non_existent_user_id = 99999999
        result = await _user_has_write_permission(non_existent_user_id, self.doc)
        self.assertFalse(result)


class TestAgentFactorySetup(TestCase):
    user: User
    corpus1: Corpus
    doc1: Document
    callable_tool: Callable[[str], str]
    core_tool_instance: CoreTool

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="factory_testuser", password="password", email="factory@test.com"
        )
        cls.corpus1 = Corpus.objects.create(
            title="Factory Test Corpus 1", creator=cls.user
        )
        # Create document and add to corpus - add_document returns corpus-isolated copy
        original_doc1 = Document.objects.create(
            title="Factory Test Doc 1", creator=cls.user
        )
        cls.doc1, _, _ = cls.corpus1.add_document(document=original_doc1, user=cls.user)

        def dummy_callable_tool(q: str) -> str:
            return f"called: {q}"

        cls.callable_tool = dummy_callable_tool  # Store raw function
        cls.core_tool_instance = CoreTool.from_function(
            cls.callable_tool, name="dummy_core_from_callable"
        )


class TestUnifiedAgentFactory(TestAgentFactorySetup):

    @patch(f"{UnifiedAgentFactory.__module__}.get_default_llm_spec", return_value="")
    @patch("opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIDocumentAgent")
    @patch(f"{UnifiedAgentFactory.__module__}.get_default_config")
    @patch(f"{UnifiedAgentFactory.__module__}._convert_tools_for_framework")
    async def test_create_document_agent_pydantic_ai_with_tools(
        self,
        mock_convert_tools: MagicMock,
        mock_get_config: MagicMock,
        mock_pydantic_agent_class: MagicMock,
        mock_llm_spec: MagicMock,
    ):
        mock_config = AgentConfig()
        mock_get_config.return_value = mock_config

        # Mock the agent instance
        mock_agent_instance = AsyncMock(spec=CoreAgent)
        mock_pydantic_agent_class.create = AsyncMock(return_value=mock_agent_instance)

        raw_tools: list[ToolType] = [self.callable_tool]
        converted_framework_tools = [MagicMock()]  # Mocked converted tools
        mock_convert_tools.return_value = converted_framework_tools

        agent = await UnifiedAgentFactory.create_document_agent(
            self.doc1,
            self.corpus1,
            framework=AgentFramework.PYDANTIC_AI,
            tools=raw_tools,
        )

        # Runtime LLM configuration: ``UnifiedAgentFactory`` now resolves
        # the model spec via the canonical priority chain (per-call →
        # per-agent → corpus.preferred_llm → settings) BEFORE building
        # ``AgentConfig``, passing the result through as ``model_name``.
        # ``self.corpus1`` was created without a ``preferred_llm`` so
        # the resolver falls back to ``settings.OPENAI_MODEL`` and
        # normalises to canonical ``"openai:<model>"`` form.
        from opencontractserver.llms.llm_registry import resolve_model_spec

        expected_model = resolve_model_spec()
        mock_get_config.assert_called_once_with(
            user_id=None,
            model_name=expected_model,
            system_prompt=None,
            temperature=0.7,
            max_tokens=None,
            streaming=True,
            conversation=None,
            conversation_id=None,
            loaded_messages=None,
            embedder_path=None,
            tools=raw_tools,
        )
        mock_convert_tools.assert_called_once_with(
            raw_tools,
            AgentFramework.PYDANTIC_AI,
            document_id=self.doc1.id,
            corpus_id=self.corpus1.id,
            user_id=None,
            corpus_action_id=None,
        )
        mock_pydantic_agent_class.create.assert_called_once()
        self.assertIs(agent, mock_agent_instance)

    @patch(f"{UnifiedAgentFactory.__module__}.get_default_llm_spec", return_value="")
    @patch("opencontractserver.llms.agents.pydantic_ai_agents.PydanticAICorpusAgent")
    @patch(f"{UnifiedAgentFactory.__module__}.get_default_config")
    async def test_create_corpus_agent_pydantic_ai(
        self,
        mock_get_config: MagicMock,
        mock_pydantic_agent_class: MagicMock,
        mock_llm_spec: MagicMock,
    ):
        mock_config = AgentConfig()
        mock_get_config.return_value = mock_config

        # Mock the agent instance
        mock_agent_instance = AsyncMock(spec=CoreAgent)
        mock_pydantic_agent_class.create = AsyncMock(return_value=mock_agent_instance)

        agent = await UnifiedAgentFactory.create_corpus_agent(
            self.corpus1, framework=AgentFramework.PYDANTIC_AI
        )

        # Runtime LLM configuration: factory resolves model_name via
        # the priority chain (per-call → per-agent → corpus.preferred_llm
        # → settings) before invoking ``get_default_config``. With no
        # corpus.preferred_llm set, the resolver returns the normalised
        # settings default (``"openai:<OPENAI_MODEL>"``).
        from opencontractserver.llms.llm_registry import resolve_model_spec

        expected_model = resolve_model_spec()
        mock_get_config.assert_called_once_with(
            user_id=None,
            model_name=expected_model,
            system_prompt=None,
            temperature=0.7,  # Default
            max_tokens=None,  # Default
            streaming=True,  # Default
            conversation=None,
            conversation_id=None,  # Default
            loaded_messages=None,
            embedder_path=None,
            tools=[],  # Default
        )
        mock_pydantic_agent_class.create.assert_called_once()
        self.assertIs(agent, mock_agent_instance)

    @patch(f"{UnifiedAgentFactory.__module__}.get_default_llm_spec", return_value="")
    async def test_unsupported_framework_raises_error(self, mock_llm_spec: MagicMock):
        """Test that invalid framework names raise ValueError."""
        # Deliberately pass an invalid framework *string* to exercise the
        # ValueError path; the production signature expects AgentFramework, so
        # the bad value is type-ignored rather than coerced.
        with self.assertRaises(ValueError):
            await UnifiedAgentFactory.create_document_agent(
                self.doc1, self.corpus1, framework="invalid_framework_name"  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            await UnifiedAgentFactory.create_corpus_agent(
                self.corpus1, framework="invalid_framework_name"  # type: ignore[arg-type]
            )


class TestToolFilteringDocumentAgent(TestCase):
    """Tests for tool filtering logic in document agent creation."""

    owner: User
    reader: User
    corpus: Corpus
    doc: Document

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="tool_filter_owner", password="password", email="owner@test.com"
        )
        cls.reader = User.objects.create_user(
            username="tool_filter_reader", password="password", email="reader@test.com"
        )
        cls.corpus = Corpus.objects.create(
            title="Tool Filter Test Corpus", creator=cls.owner
        )
        # Create document and add to corpus - add_document returns corpus-isolated copy
        original_doc = Document.objects.create(
            title="Tool Filter Test Doc", creator=cls.owner
        )
        cls.doc, _, _ = cls.corpus.add_document(document=original_doc, user=cls.owner)

    @patch(f"{UnifiedAgentFactory.__module__}.get_default_llm_spec", return_value="")
    @patch("opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIDocumentAgent")
    @patch(f"{UnifiedAgentFactory.__module__}.get_default_config")
    @patch(f"{UnifiedAgentFactory.__module__}._convert_tools_for_framework")
    async def test_corpus_required_tool_filtered_when_no_corpus(
        self,
        mock_convert_tools: MagicMock,
        mock_get_config: MagicMock,
        mock_pydantic_agent_class: MagicMock,
        mock_llm_spec: MagicMock,
    ):
        """Test that corpus-required tools are filtered out when no corpus is provided.

        Line 196 coverage: corpus_required tool filtered for document-only agent.
        """
        mock_config = AgentConfig()
        mock_get_config.return_value = mock_config
        mock_agent_instance = AsyncMock(spec=CoreAgent)
        mock_pydantic_agent_class.create = AsyncMock(return_value=mock_agent_instance)
        mock_convert_tools.return_value = []

        # Create a corpus-required tool
        corpus_tool = CoreTool.from_function(
            func=lambda q: f"searched: {q}",
            name="corpus_search",
            description="Search across corpus",
            requires_corpus=True,
        )
        # Create a regular tool
        regular_tool = CoreTool.from_function(
            func=lambda q: f"searched: {q}",
            name="doc_search",
            description="Search document",
            requires_corpus=False,
        )

        # Call without corpus - corpus_tool should be filtered out
        await UnifiedAgentFactory.create_document_agent(
            self.doc,
            corpus=None,  # No corpus provided
            framework=AgentFramework.PYDANTIC_AI,
            tools=[corpus_tool, regular_tool],
        )

        # Verify convert_tools was called with only the regular tool (corpus_tool filtered)
        call_args = mock_convert_tools.call_args[0][0]
        self.assertEqual(len(call_args), 1)
        self.assertEqual(call_args[0].name, "doc_search")

    @patch(f"{UnifiedAgentFactory.__module__}.get_default_llm_spec", return_value="")
    @patch("opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIDocumentAgent")
    @patch(f"{UnifiedAgentFactory.__module__}.get_default_config")
    @patch(f"{UnifiedAgentFactory.__module__}._convert_tools_for_framework")
    @patch(f"{UnifiedAgentFactory.__module__}._user_has_write_permission")
    async def test_write_tool_filtered_when_user_lacks_permission(
        self,
        mock_has_write_perm: MagicMock,
        mock_convert_tools: MagicMock,
        mock_get_config: MagicMock,
        mock_pydantic_agent_class: MagicMock,
        mock_llm_spec: MagicMock,
    ):
        """Test that write tools are filtered when user lacks write permission.

        Lines 203, 209 coverage: write tools filtered for read-only users on document agent.
        """
        mock_config = AgentConfig()
        mock_get_config.return_value = mock_config
        mock_agent_instance = AsyncMock(spec=CoreAgent)
        mock_pydantic_agent_class.create = AsyncMock(return_value=mock_agent_instance)
        mock_convert_tools.return_value = []
        # Mock user lacking write permission
        mock_has_write_perm.return_value = False

        # Create a write-required tool
        write_tool = CoreTool.from_function(
            func=lambda note: f"added: {note}",
            name="add_note",
            description="Add a note to document",
            requires_write_permission=True,
        )
        # Create a read-only tool
        read_tool = CoreTool.from_function(
            func=lambda: "content",
            name="read_doc",
            description="Read document",
            requires_write_permission=False,
        )

        # Call with reader user (no write permission) - write_tool should be filtered
        await UnifiedAgentFactory.create_document_agent(
            self.doc,
            corpus=self.corpus,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.reader.id,  # Reader lacks write permission
            tools=[write_tool, read_tool],
        )

        # Verify convert_tools was called with only the read tool (write_tool filtered)
        call_args = mock_convert_tools.call_args[0][0]
        self.assertEqual(len(call_args), 1)
        self.assertEqual(call_args[0].name, "read_doc")


class TestToolFilteringCorpusAgent(TestCase):
    """Tests for tool filtering logic in corpus agent creation."""

    owner: User
    reader: User
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="corpus_tool_owner",
            password="password",
            email="corpusowner@test.com",
        )
        cls.reader = User.objects.create_user(
            username="corpus_tool_reader",
            password="password",
            email="corpusreader@test.com",
        )
        cls.corpus = Corpus.objects.create(
            title="Corpus Tool Filter Test", creator=cls.owner
        )

    @patch(f"{UnifiedAgentFactory.__module__}.get_default_llm_spec", return_value="")
    @patch("opencontractserver.llms.agents.pydantic_ai_agents.PydanticAICorpusAgent")
    @patch(f"{UnifiedAgentFactory.__module__}.get_default_config")
    @patch(f"{UnifiedAgentFactory.__module__}._convert_tools_for_framework")
    @patch(f"{UnifiedAgentFactory.__module__}._user_has_write_permission")
    async def test_write_tool_filtered_when_user_lacks_permission_corpus(
        self,
        mock_has_write_perm: MagicMock,
        mock_convert_tools: MagicMock,
        mock_get_config: MagicMock,
        mock_pydantic_agent_class: MagicMock,
        mock_llm_spec: MagicMock,
    ):
        """Test that write tools are filtered when user lacks write permission on corpus.

        Lines 350-362 coverage: write tools filtered for read-only users on corpus agent.
        """
        mock_config = AgentConfig()
        mock_get_config.return_value = mock_config
        mock_agent_instance = AsyncMock(spec=CoreAgent)
        mock_pydantic_agent_class.create = AsyncMock(return_value=mock_agent_instance)
        mock_convert_tools.return_value = []
        # Mock user lacking write permission
        mock_has_write_perm.return_value = False

        # Create a write-required tool
        write_tool = CoreTool.from_function(
            func=lambda desc: f"updated: {desc}",
            name="update_corpus_description",
            description="Update corpus description",
            requires_write_permission=True,
        )
        # Create a read-only tool
        read_tool = CoreTool.from_function(
            func=lambda q: f"searched: {q}",
            name="search_corpus",
            description="Search corpus",
            requires_write_permission=False,
        )

        # Call with reader user (no write permission) - write_tool should be filtered
        await UnifiedAgentFactory.create_corpus_agent(
            self.corpus,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.reader.id,  # Reader lacks write permission
            tools=[write_tool, read_tool],
        )

        # Verify convert_tools was called with only the read tool (write_tool filtered)
        call_args = mock_convert_tools.call_args[0][0]
        self.assertEqual(len(call_args), 1)
        self.assertEqual(call_args[0].name, "search_corpus")
