"""Unified tool factory that can create tools for different frameworks."""

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from opencontractserver.llms.types import AgentFramework

# Re-exported so framework adapters can accept any ``ToolProtocol`` rather
# than depending on the concrete ``CoreTool`` dataclass below.  The
# protocol pins the minimum surface (`name` / `description` /
# `parameters` / `requires_approval`) — the dataclass adds optional
# behaviour like ``inject_params`` on top.
from opencontractserver.types.protocols import ToolProtocol  # noqa: F401

logger = logging.getLogger(__name__)


def build_inject_params_for_context(
    tool: "CoreTool",
    document_id: int | None = None,
    corpus_id: int | None = None,
    user_id: int | None = None,
    corpus_action_id: int | None = None,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    """
    Inspect a CoreTool's function signature and build inject_params dict
    for context-bound parameters that should be hidden from the LLM.

    This function examines a tool's function signature and determines which
    parameters should be automatically injected from context rather than
    being provided by the LLM. This prevents the LLM from hallucinating
    incorrect document_id, corpus_id, or user_id values.

    Args:
        tool: The CoreTool to inspect
        document_id: Document ID to inject if the tool accepts it
        corpus_id: Corpus ID to inject if the tool accepts it
        user_id: User ID to inject for author_id/creator_id params
        corpus_action_id: CorpusAction ID to inject if the tool accepts it

    Returns:
        Dictionary mapping parameter names to values to inject
    """
    sig = inspect.signature(tool.function)
    inject: dict[str, Any] = {}

    for param_name in sig.parameters:
        if param_name == "document_id" and document_id is not None:
            inject["document_id"] = document_id
        elif param_name == "corpus_id" and corpus_id is not None:
            inject["corpus_id"] = corpus_id
        elif (
            param_name in ("author_id", "creator_id", "user_id") and user_id is not None
        ):
            inject[param_name] = user_id
        elif param_name == "corpus_action_id" and corpus_action_id is not None:
            inject["corpus_action_id"] = corpus_action_id
        elif param_name == "conversation_id" and conversation_id is not None:
            inject["conversation_id"] = conversation_id

    if inject:
        logger.debug(
            f"Built inject_params for tool '{tool.name}': {list(inject.keys())}"
        )

    return inject


@dataclass
class ToolMetadata:
    """Metadata for a tool function."""

    name: str
    description: str
    parameter_descriptions: Optional[dict[str, str]] = None


@dataclass
class CoreTool:
    """Framework-agnostic tool representation.

    ``requires_approval`` marks tools that must be explicitly approved by a
    human before execution.  Framework adapters **must** honour this flag
    and implement a veto-gate when set to ``True``.

    ``requires_corpus`` marks tools that need a corpus_id to function.
    These tools will be filtered out when creating agents for documents
    that are not in any corpus.

    ``requires_write_permission`` marks tools that perform write operations.
    These tools will be filtered out when the calling user lacks WRITE
    permission on the target resource (corpus or document).
    """

    function: Callable
    metadata: ToolMetadata
    requires_approval: bool = False
    requires_corpus: bool = False
    requires_write_permission: bool = False

    @classmethod
    def from_function(
        cls,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameter_descriptions: Optional[dict[str, str]] = None,
        *,
        requires_approval: bool = False,
        requires_corpus: bool = False,
        requires_write_permission: bool = False,
    ) -> "CoreTool":
        """Create a CoreTool from a Python function.

        Args:
            func: The Python function to wrap
            name: Optional custom name (defaults to function name)
            description: Optional custom description (extracted from docstring if not provided)
            parameter_descriptions: Optional parameter descriptions
            requires_approval: Whether the tool requires explicit approval
            requires_corpus: Whether the tool requires a corpus_id to function
            requires_write_permission: Whether the tool performs write operations

        Returns:
            CoreTool instance
        """
        tool_name = name or func.__name__
        tool_description = description or _extract_description_from_docstring(func)

        if not parameter_descriptions:
            parameter_descriptions = _extract_parameter_descriptions_from_docstring(
                func
            )

        metadata = ToolMetadata(
            name=tool_name,
            description=tool_description,
            parameter_descriptions=parameter_descriptions,
        )

        return cls(
            function=func,
            metadata=metadata,
            requires_approval=requires_approval,
            requires_corpus=requires_corpus,
            requires_write_permission=requires_write_permission,
        )

    @property
    def name(self) -> str:
        """Get the tool name."""
        return self.metadata.name

    @property
    def description(self) -> str:
        """Get the tool description."""
        return self.metadata.description

    @property
    def parameters(self) -> dict[str, Any]:
        """Get the tool parameters schema."""
        sig = inspect.signature(self.function)
        properties = {}
        required = []
        param_descriptions = self.metadata.parameter_descriptions or {}

        for param_name, param in sig.parameters.items():
            param_info = {
                "type": "string",  # Default type
                "description": param_descriptions.get(param_name, ""),
            }

            # Try to infer type from annotation
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_info["type"] = "integer"
                elif param.annotation == float:
                    param_info["type"] = "number"
                elif param.annotation == bool:
                    param_info["type"] = "boolean"
                elif param.annotation == list:
                    param_info["type"] = "array"
                elif param.annotation == dict:
                    param_info["type"] = "object"

            properties[param_name] = param_info

            # Add to required if no default value
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {"type": "object", "properties": properties, "required": required}


class UnifiedToolFactory:
    """Factory that creates tools using different frameworks with a common interface."""

    @staticmethod
    def create_tool(
        tool: CoreTool,
        framework: AgentFramework,
        inject_params: dict[str, Any] | None = None,
    ) -> Any:
        """Create a framework-specific tool from a CoreTool.

        Args:
            tool: CoreTool instance
            framework: Target framework
            inject_params: Optional dict of params to inject at execution time,
                          hiding them from the LLM's view of the tool schema

        Returns:
            Framework-specific tool instance
        """
        if framework == AgentFramework.PYDANTIC_AI:
            from opencontractserver.llms.tools.pydantic_ai_tools import (
                PydanticAIToolFactory,
            )

            return PydanticAIToolFactory.create_tool(tool, inject_params=inject_params)
        else:
            raise ValueError(f"Unsupported framework: {framework}")

    @staticmethod
    def create_tools(tools: list[CoreTool], framework: AgentFramework) -> list[Any]:
        """Create framework-specific tools from a list of CoreTools.

        Args:
            tools: List of CoreTool instances
            framework: Target framework

        Returns:
            List of framework-specific tool instances
        """
        if framework == AgentFramework.PYDANTIC_AI:
            from opencontractserver.llms.tools.pydantic_ai_tools import (
                PydanticAIToolFactory,
            )

            return PydanticAIToolFactory.create_tools(tools)
        else:
            raise ValueError(f"Unsupported framework: {framework}")

    @staticmethod
    def from_function(
        func: Callable,
        framework: AgentFramework,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameter_descriptions: Optional[dict[str, str]] = None,
        *,
        requires_approval: bool = False,
        requires_corpus: bool = False,
        requires_write_permission: bool = False,
    ) -> Any:
        """Create a framework-specific tool directly from a function.

        Args:
            func: Python function to wrap
            framework: Target framework
            name: Optional custom name
            description: Optional custom description
            parameter_descriptions: Optional parameter descriptions
            requires_approval: Whether the tool requires explicit approval
            requires_corpus: Whether the tool requires a corpus_id to function
            requires_write_permission: Whether the tool performs write operations

        Returns:
            Framework-specific tool instance
        """
        if framework == AgentFramework.PYDANTIC_AI:
            from opencontractserver.llms.tools.pydantic_ai_tools import (
                PydanticAIToolFactory,
            )

            return PydanticAIToolFactory.from_function(
                func=func,
                name=name,
                description=description,
                parameter_descriptions=parameter_descriptions,
                requires_approval=requires_approval,
                requires_corpus=requires_corpus,
                requires_write_permission=requires_write_permission,
            )
        else:
            raise ValueError(f"Unsupported framework: {framework}")


def _extract_description_from_docstring(func: Callable) -> str:
    """Extract the main description from a function's docstring."""
    if not func.__doc__:
        return f"Function {func.__name__}"

    # Get the first line or paragraph of the docstring
    lines = func.__doc__.strip().split("\n")
    description = lines[0].strip()

    # If the first line is empty, try the next non-empty line
    if not description and len(lines) > 1:
        for line in lines[1:]:
            if line.strip():
                description = line.strip()
                break

    return description or f"Function {func.__name__}"


def _extract_parameter_descriptions_from_docstring(func: Callable) -> dict[str, str]:
    """Extract parameter descriptions from a function's docstring."""
    if not func.__doc__:
        return {}

    parameter_descriptions = {}
    lines = func.__doc__.strip().split("\n")
    in_args_section = False

    for line in lines:
        line = line.strip()
        if line.startswith("Args:") or line.startswith("Arguments:"):
            in_args_section = True
            continue
        elif line.startswith("Returns:") or line.startswith("Raises:"):
            in_args_section = False
            continue

        if in_args_section and ":" in line:
            # Parse lines like "document_id: The primary key (ID) of the Document"
            parts = line.split(":", 1)
            if len(parts) == 2:
                param_name = parts[0].strip()
                description = parts[1].strip()
                parameter_descriptions[param_name] = description

    return parameter_descriptions


# Convenience functions for creating common tools
def create_document_tools() -> list[CoreTool]:
    """Create standard document-related tools.

    All tools are async — sync versions exist in the source files for
    test convenience only and must never be registered for production use.
    """
    from opencontractserver.llms.tools.core_tools import (
        aget_md_summary_token_length,
        aget_note_content_token_length,
        aget_notes_for_document_corpus,
        aget_page_image,
        aget_partial_note_content,
        aload_document_md_summary,
        asearch_exact_text_as_sources,
    )
    from opencontractserver.llms.tools.image_tools import (
        aget_annotation_images,
        aget_document_image,
        alist_document_images,
    )

    return [
        CoreTool.from_function(
            asearch_exact_text_as_sources,
            name="search_exact_text_as_sources",
            description=(
                "Search for exact text matches in a "
                "document and return them as source nodes with page numbers and bounding boxes."
            ),
        ),
        CoreTool.from_function(
            aload_document_md_summary,
            name="load_document_md_summary",
            description="Load markdown summary of a document, optionally truncated.",
        ),
        CoreTool.from_function(
            aget_md_summary_token_length,
            name="get_md_summary_token_length",
            description="Get the token length of a document's markdown summary.",
        ),
        CoreTool.from_function(
            aget_notes_for_document_corpus,
            name="get_notes_for_document_corpus",
            description="Get notes associated with a document and optional corpus.",
        ),
        CoreTool.from_function(
            aget_note_content_token_length,
            name="get_note_content_token_length",
            description="Get the token length of a note's content.",
        ),
        CoreTool.from_function(
            aget_partial_note_content,
            name="get_partial_note_content",
            description="Get a substring of a note's content by start/end indices.",
        ),
        CoreTool.from_function(
            aget_page_image,
            name="get_page_image",
            description=(
                "Get a visual image of a specific page from a PDF document. "
                "Useful for inspecting diagrams, tables, images, and other "
                "visual content that may not be captured in text."
            ),
        ),
        # Image tools for accessing embedded/extracted images
        CoreTool.from_function(
            alist_document_images,
            name="list_document_images",
            description=(
                "List all images in a document. Returns metadata (position, size, format) "
                "without the actual image data. Use get_document_image to retrieve specific images."
            ),
        ),
        CoreTool.from_function(
            aget_document_image,
            name="get_document_image",
            description=(
                "Get image data (base64) for a specific image in a document. "
                "Returns data URL suitable for LLM vision input. Use list_document_images first "
                "to find available images by page and index."
            ),
        ),
        CoreTool.from_function(
            aget_annotation_images,
            name="get_annotation_images",
            description=(
                "Get all images referenced by an annotation. Use for figure, chart, or image "
                "annotations that have embedded or referenced images in their bounds."
            ),
        ),
    ]
