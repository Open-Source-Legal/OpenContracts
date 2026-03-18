"""
OpenContracts LLM Tools Package

This package provides framework-agnostic tools and framework-specific adapters.

All registered tools MUST be async.  Sync versions of tool functions
exist in the source files for test convenience only and should be
imported directly from ``core_tools``, ``image_tools``, or
``moderation_tools`` when needed in tests.
"""

from opencontractserver.llms.tools.core_tools import (
    aget_md_summary_token_length,
    aget_note_content_token_length,
    aget_notes_for_document_corpus,
    aget_partial_note_content,
    aload_document_md_summary,
    aload_document_txt_extract,
)
from opencontractserver.llms.tools.tool_factory import (
    CoreTool,
    ToolMetadata,
    UnifiedToolFactory,
    create_document_tools,
)

__all__ = [
    # Core async tools
    "aload_document_md_summary",
    "aget_md_summary_token_length",
    "aget_notes_for_document_corpus",
    "aget_note_content_token_length",
    "aget_partial_note_content",
    "aload_document_txt_extract",
    # Factory and metadata
    "CoreTool",
    "ToolMetadata",
    "UnifiedToolFactory",
    "create_document_tools",
]
