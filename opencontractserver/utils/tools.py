"""
Utility functions for LLM tool management.
"""

import logging
from typing import Callable

from opencontractserver.llms.tools.tool_factory import CoreTool

logger = logging.getLogger(__name__)


def as_core_tool(tool: CoreTool | Callable) -> CoreTool:
    """Retain a wrapped tool's capabilities when binding it to another context."""
    if isinstance(tool, CoreTool):
        return tool
    from opencontractserver.llms.tools.pydantic_ai_tools import PydanticAIToolWrapper

    if isinstance(tool, PydanticAIToolWrapper):
        return tool.core_tool
    wrapper = getattr(tool, "_pydantic_ai_wrapper", None)
    if isinstance(wrapper, PydanticAIToolWrapper) and wrapper.callable_function is tool:
        return wrapper.core_tool
    return CoreTool.from_function(tool)


def get_tool_name(tool: Callable) -> str | None:
    """
    Extract a tool's name, checking both __name__ and name attributes.

    Args:
        tool: A callable tool (function, method, or tool wrapper).

    Returns:
        The tool's name, or None if no name could be determined.
    """
    return getattr(tool, "__name__", None) or getattr(tool, "name", None)


def deduplicate_tools(
    default_tools: list[Callable],
    override_tools: list[Callable],
    context: str = "Caller",
) -> list[Callable]:
    """
    Merge default and override tools, with override tools taking precedence.

    When an override tool has the same name as a default tool, the default
    is replaced by the override. This allows callers to customize tool
    configurations (e.g., requires_approval, description) without modifying
    the framework.

    Args:
        default_tools: List of built-in default tools.
        override_tools: List of caller-provided tools that should take precedence.
        context: Descriptive context for log messages (e.g., "Caller", "Per-call").

    Returns:
        Merged list with filtered defaults followed by all override tools.

    Example:
        >>> defaults = [tool_a, tool_b, tool_c]  # tool_b.__name__ = "update_doc"
        >>> overrides = [custom_tool_b]  # custom_tool_b.__name__ = "update_doc"
        >>> result = deduplicate_tools(defaults, overrides)
        >>> # Returns [tool_a, tool_c, custom_tool_b]
        >>> # tool_b was replaced by custom_tool_b

    Security Note:
        This function enables overriding tool configurations including
        `requires_approval`. Only pass trusted tools via override_tools.
        If tools originate from user-controlled configurations, validate
        them against an approved registry first.
    """
    if not override_tools:
        return default_tools

    # Build set of override tool names, filtering out None values
    override_names = {get_tool_name(t) for t in override_tools} - {None}

    # Filter out defaults that will be replaced by override tools
    filtered_defaults = []
    for default_tool in default_tools:
        default_name = get_tool_name(default_tool)
        if default_name and default_name in override_names:
            logger.info(
                f"{context} tool '{default_name}' overrides default - "
                "using caller's configuration"
            )
        else:
            filtered_defaults.append(default_tool)

    # Return filtered defaults + all override tools
    return filtered_defaults + override_tools
