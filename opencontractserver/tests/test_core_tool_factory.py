import sys
import types
from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase

from opencontractserver.llms.tools.tool_factory import (
    CoreTool,
    UnifiedToolFactory,
    create_document_tools,
)
from opencontractserver.llms.types import AgentFramework

# ---------------------------------------------------------------------------
# Optional lightweight stubs **only** if the real packages are unavailable.
# ---------------------------------------------------------------------------

try:
    import pydantic  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover -- local dev without deps
    _pydantic_stub = types.ModuleType("pydantic")

    class _BaseModelStub:  # Minimal replacement for pydantic.BaseModel
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def __repr__(self):
            attrs = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items())
            return f"BaseModelStub({attrs})"

    _pydantic_stub.BaseModel = _BaseModelStub  # type: ignore[attr-defined]
    _pydantic_stub.Field = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _pydantic_stub.ConfigDict = lambda **kwargs: {}  # type: ignore[attr-defined]
    sys.modules["pydantic"] = _pydantic_stub


try:
    import pydantic_ai  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    _pydantic_ai_stub = types.ModuleType("pydantic_ai")

    class _RunContext:  # Minimal RunContext replacement
        pass

    _pydantic_ai_stub.RunContext = _RunContext  # type: ignore[attr-defined]
    sys.modules["pydantic_ai"] = _pydantic_ai_stub


# ---------------------------------------------------------------------------
# Helper functions for building CoreTools used in the tests
# ---------------------------------------------------------------------------


def sample_function(a: int, b: str = "default") -> str:
    """Return a combined string.

    Args:
        a: An integer parameter
        b: A string parameter (optional)

    Returns:
        Combined string of the two inputs.
    """

    return f"{a}-{b}"


def function_without_docstring(x):  # type: ignore[missing-return-type-doc]
    # Intentionally leave out a docstring for description extraction tests
    return x


class TestCoreTool(SimpleTestCase):
    """Tests for the ``CoreTool`` data-class and helper functions."""

    def test_from_function_auto_metadata(self):
        """``from_function`` should populate name, description and parameters automatically."""
        tool = CoreTool.from_function(sample_function)

        # Metadata checks
        self.assertEqual(tool.name, "sample_function")
        self.assertEqual(tool.description, "Return a combined string.")

        # Parameter schema checks
        schema = tool.parameters
        self.assertEqual(schema["type"], "object")
        props: dict[str, Any] = schema["properties"]
        self.assertIn("a", props)
        self.assertIn("b", props)
        self.assertEqual(props["a"]["type"], "integer")
        self.assertEqual(props["b"]["type"], "string")

        # Required list should contain only the positional parameter ``a``
        self.assertListEqual(schema["required"], ["a"])

    def test_missing_docstring_fallback_description(self):
        """If a function lacks a docstring the description should fall back to a generic value."""
        tool = CoreTool.from_function(function_without_docstring)
        self.assertEqual(
            tool.description, f"Function {function_without_docstring.__name__}"
        )


class TestUnifiedToolFactory(SimpleTestCase):
    """Ensure framework dispatching logic works and raises the expected errors."""

    def setUp(self):
        self.core_tool = CoreTool.from_function(sample_function)

    @patch(
        "opencontractserver.llms.tools.pydantic_ai_tools.PydanticAIToolFactory.create_tool"
    )
    def test_create_tool_pydantic_ai(self, mock_create_tool):
        """``create_tool`` should delegate to the Pydantic AI factory when framework == PYDANTIC_AI."""
        mock_create_tool.return_value = "pydantic_proxy"
        result = UnifiedToolFactory.create_tool(
            self.core_tool, AgentFramework.PYDANTIC_AI
        )
        self.assertEqual(result, "pydantic_proxy")
        mock_create_tool.assert_called_once_with(self.core_tool, inject_params=None)

    def test_create_tool_invalid_framework(self):
        """An unsupported framework name should raise ``ValueError`` from the factory."""
        with self.assertRaises(ValueError):
            UnifiedToolFactory.create_tool(self.core_tool, "invalid")  # type: ignore[arg-type]

    @patch(
        "opencontractserver.llms.tools.pydantic_ai_tools.PydanticAIToolFactory.create_tools"
    )
    def test_create_tools_batch(self, mock_create_tools):
        """Batch ``create_tools`` should forward list of CoreTools to underlying factory."""
        mock_create_tools.return_value = ["tool1", "tool2"]
        result = UnifiedToolFactory.create_tools(
            [self.core_tool], AgentFramework.PYDANTIC_AI
        )
        self.assertEqual(result, ["tool1", "tool2"])
        mock_create_tools.assert_called_once_with([self.core_tool])

    @patch(
        "opencontractserver.llms.tools.pydantic_ai_tools.PydanticAIToolFactory.from_function"
    )
    def test_from_function_shortcut(self, mock_from_function):
        """``from_function`` helper should call through to the framework-specific shortcut."""
        mock_from_function.return_value = "pydantic_tool_from_func"
        res = UnifiedToolFactory.from_function(
            sample_function, AgentFramework.PYDANTIC_AI
        )
        self.assertEqual(res, "pydantic_tool_from_func")
        mock_from_function.assert_called_once()


class TestCreateDocumentTools(SimpleTestCase):
    """Verify the convenience ``create_document_tools`` helper returns the expected ``CoreTools``."""

    def test_create_document_tools_names(self):
        tools = create_document_tools()
        expected_names = {
            "search_exact_text_as_sources",
            "load_document_md_summary",
            "get_md_summary_token_length",
            "get_notes_for_document_corpus",
            "get_note_content_token_length",
            "get_partial_note_content",
            "get_page_image",
            # Image tools for multimodal support
            "list_document_images",
            "get_document_image",
            "get_annotation_images",
        }
        self.assertEqual({tool.name for tool in tools}, expected_names)
        # Ensure all returned objects are CoreTool instances
        self.assertTrue(all(isinstance(t, CoreTool) for t in tools))
