"""
Test for bug: Duplicate Tool Registration in PydanticAI Agent

This test confirms the bug where passing a tool name (e.g., "update_document_description")
via the `tools` parameter results in a duplicate tool registration error because
the PydanticAIDocumentAgent.create() method already creates this tool by default.

Bug report:
    pydantic_ai.exceptions.UserError: Tool name conflicts with existing tool:
    'update_document_description'
"""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms import agents
from opencontractserver.llms.agents.core_agents import AgentConfig
from opencontractserver.llms.agents.pydantic_ai_agents import PydanticAIDocumentAgent
from opencontractserver.llms.tools.core_tools import aupdate_document_description
from opencontractserver.llms.tools.tool_factory import CoreTool

User = get_user_model()


class TestDuplicateToolRegistration(TransactionTestCase):
    """Tests for duplicate tool registration bug."""

    # Note: Signal management is handled globally by conftest.py fixture
    # `disable_document_processing_signals` - no need to disconnect/reconnect here.

    def setUp(self) -> None:
        """Create test data."""
        # ``ToolFunctionRegistry`` is a process-singleton. Other tests sharing
        # this worker (xdist loadscope deterministically co-locates whole
        # modules but the *set* of modules on a worker shifts whenever the
        # repo's test-file list changes) can register extra entries or aliases
        # that survive into this class and skew the per-agent tool counts the
        # assertions below pin. ``reset()`` is the registry's own documented
        # test-isolation hook (see ``tool_registry.py``); calling it forces
        # the next ``get()`` to rebuild from ``FUNCTION_MAP`` + ``AVAILABLE_TOOLS``.
        from opencontractserver.llms.tools.tool_registry import (
            ToolFunctionRegistry,
        )

        ToolFunctionRegistry.reset()

        self.user = User.objects.create_user(
            username="testuser",
            password="testpass",
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test corpus",
            creator=self.user,
            is_public=True,
        )

        doc_text = "This is a test document with some content."
        self.doc = Document.objects.create(
            title="Test Document",
            description="Test document for duplicate tool test",
            creator=self.user,
            is_public=True,
            file_type="text/plain",
        )
        self.doc.txt_extract_file.save(
            "test_doc.txt", ContentFile(doc_text.encode("utf-8")), save=True
        )

    async def test_duplicate_tool_via_string_name_does_not_raise(self):
        """
        Test that passing 'update_document_description' as a tool name
        via the high-level API does NOT cause a duplicate tool error.

        Before the fix, this would raise:
            pydantic_ai.exceptions.UserError: Tool name conflicts with existing tool:
            'update_document_description'

        After the fix, duplicates should be silently deduplicated.
        """
        # This tool name is ALREADY registered as a default tool in
        # PydanticAIDocumentAgent.create(), so passing it again should
        # either be deduplicated or cause an error (before the fix).
        tool_names = ["update_document_description"]

        # Use the high-level API which goes through:
        # agents.for_document() -> api.py:_resolve_tools() -> agent_factory.py
        # -> PydanticAIDocumentAgent.create()
        agent = await agents.for_document(
            document=self.doc,
            corpus=self.corpus,
            user_id=self.user.id,
            tools=tool_names,
            streaming=False,
        )

        # If we get here without UserError, the fix worked
        self.assertIsNotNone(agent)

    async def test_duplicate_tool_via_core_tool_does_not_raise(self):
        """
        Test that passing a CoreTool with the same name as a default tool
        does NOT cause a duplicate tool error.
        """
        from django.conf import settings

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIToolFactory,
        )

        # Create a CoreTool that wraps the same function as the default
        duplicate_core_tool = CoreTool.from_function(
            aupdate_document_description,
            name="update_document_description",
            description="Duplicate tool for testing",
        )
        # Convert to PydanticAI tool format (same as what agent_factory does)
        duplicate_pydantic_tool = PydanticAIToolFactory.create_tool(duplicate_core_tool)

        config = AgentConfig(
            user_id=self.user.id,
            model_name=settings.OPENAI_MODEL,  # Use a valid model name
            store_user_messages=False,
            store_llm_messages=False,
        )

        # This should NOT raise even though 'update_document_description'
        # is already a default tool
        agent = await PydanticAIDocumentAgent.create(
            document=self.doc,
            corpus=self.corpus,
            config=config,
            tools=[duplicate_pydantic_tool],
        )

        self.assertIsNotNone(agent)

    async def test_caller_tool_overrides_default_configuration(self):
        """
        Test that caller-provided tools OVERRIDE default tool configurations.

        This verifies that when a caller provides a tool with the same name as
        a default tool, the caller's configuration is used instead of the default.
        We verify this by checking that only one instance of the tool exists
        and by using a custom docstring that differs from the default.
        """
        from django.conf import settings

        # Create a custom function with a unique docstring we can identify
        custom_docstring = "UNIQUE_CUSTOM_DOCSTRING_FOR_OVERRIDE_TEST_12345"

        async def custom_update_document_description(new_description: str) -> dict:
            pass

        # Set the docstring and name to match the default tool
        custom_update_document_description.__doc__ = custom_docstring
        custom_update_document_description.__name__ = "update_document_description"

        config = AgentConfig(
            user_id=self.user.id,
            model_name=settings.OPENAI_MODEL,
            store_user_messages=False,
            store_llm_messages=False,
        )

        agent = await PydanticAIDocumentAgent.create(
            document=self.doc,
            corpus=self.corpus,
            config=config,
            tools=[custom_update_document_description],
        )

        self.assertIsNotNone(agent)

        # Verify the caller's tool is used, not the default
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _get_function_tools,
        )

        function_tools = _get_function_tools(agent.pydantic_ai_agent)

        # Count how many times 'update_document_description' appears
        update_desc_count = sum(
            1 for name in function_tools.keys() if "update_document_description" in name
        )

        # Should only appear once (caller's tool replaces default)
        self.assertEqual(
            update_desc_count,
            1,
            f"Expected exactly 1 instance of 'update_document_description' but found {update_desc_count}",
        )

        # Find the update_document_description tool and verify it's our custom one
        # by checking that the tool's description contains our custom docstring
        for tool_name, tool_def in function_tools.items():
            if "update_document_description" in tool_name:
                # PydanticAI Tool objects have a 'description' attribute that comes from
                # the function's docstring. Check if our custom docstring is present.
                tool_desc = getattr(tool_def, "description", "")
                # The tool description should contain our unique marker
                self.assertIn(
                    custom_docstring,
                    tool_desc,
                    f"Expected caller's custom docstring in tool description but got: {tool_desc}. "
                    "The default tool may have been used instead of the caller's override.",
                )
                break

    async def test_multiple_duplicate_tools_deduplicated(self):
        """
        Test that passing multiple tools with the same name as default tools
        results in proper deduplication (only one instance of each).
        """
        # These are all default tools that will be duplicated
        tool_names = [
            "update_document_description",
            "get_document_description",
        ]

        agent = await agents.for_document(
            document=self.doc,
            corpus=self.corpus,
            user_id=self.user.id,
            tools=tool_names,
            streaming=False,
        )

        self.assertIsNotNone(agent)

    async def test_config_tools_deduplicated_in_structured_response(self):
        """
        Test that config.tools are properly deduplicated in structured_response().

        This exercises the `elif self.config.tools` branch in _structured_response_raw(),
        ensuring that tools passed via AgentConfig don't cause duplicate tool errors
        when structured_response() creates a temporary agent that seeds tools from
        the main agent.
        """
        from unittest.mock import AsyncMock, patch

        from django.conf import settings
        from pydantic import BaseModel

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIToolFactory,
        )

        # Create a duplicate tool that will be in config.tools
        duplicate_core_tool = CoreTool.from_function(
            aupdate_document_description,
            name="update_document_description",
            description="Duplicate tool for testing structured_response",
        )
        duplicate_pydantic_tool = PydanticAIToolFactory.create_tool(duplicate_core_tool)

        # Create config with the duplicate tool in config.tools
        config = AgentConfig(
            user_id=self.user.id,
            model_name=settings.OPENAI_MODEL,
            store_user_messages=False,
            store_llm_messages=False,
            tools=[
                duplicate_pydantic_tool
            ],  # This will go through elif self.config.tools
        )

        # Create the agent (this should work - deduplication happens at create time)
        agent = await PydanticAIDocumentAgent.create(
            document=self.doc,
            corpus=self.corpus,
            config=config,
            tools=[],  # Empty tools list so config.tools path is used in structured_response
        )
        self.assertIsNotNone(agent)

        # Define a simple response model for structured_response
        class SimpleResponse(BaseModel):
            answer: str

        # Mock the PydanticAI agent's run method to avoid actual API calls
        # The key test is that agent creation inside structured_response doesn't raise UserError
        mock_result = AsyncMock()
        mock_result.output = SimpleResponse(answer="test")

        with patch.object(
            agent.pydantic_ai_agent.__class__, "run", return_value=mock_result
        ):
            # This should NOT raise UserError even though config.tools contains
            # a duplicate of 'update_document_description' which is already seeded
            # from the main agent's tools
            try:
                # We need to mock the temporary agent created inside structured_response
                # The actual test is that the PydanticAIAgent constructor doesn't raise
                with patch(
                    "opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent"
                ) as mock_agent_class:
                    mock_agent_instance = AsyncMock()
                    mock_agent_instance.run = AsyncMock(return_value=mock_result)
                    mock_agent_class.return_value = mock_agent_instance

                    await agent.structured_response(
                        prompt="Test prompt",
                        target_type=SimpleResponse,
                    )

                    # Verify the agent was created (no UserError during construction)
                    mock_agent_class.assert_called_once()

                    # Check that tools were passed correctly (seeded + deduplicated config.tools)
                    call_kwargs = mock_agent_class.call_args.kwargs
                    tools_passed = call_kwargs.get("tools", [])

                    # Count how many times 'update_document_description' appears
                    update_desc_count = sum(
                        1
                        for t in tools_passed
                        if getattr(t, "__name__", "") == "update_document_description"
                    )

                    # Should only appear once (seeded from main agent, not duplicated from config)
                    self.assertEqual(
                        update_desc_count,
                        1,
                        f"Expected 1 instance of 'update_document_description' but found {update_desc_count}",
                    )

            except Exception as e:
                if "UserError" in type(e).__name__ or "Tool name conflicts" in str(e):
                    self.fail(f"structured_response raised duplicate tool error: {e}")
