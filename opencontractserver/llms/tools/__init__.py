"""
OpenContracts LLM Tools Package

This package provides framework-agnostic tools and framework-specific adapters.
"""

from opencontractserver.llms.tools.core_tools import (
    agenerate_annotation_hyperlink,
    agenerate_corpus_hyperlink,
    agenerate_document_hyperlink,
    aload_document_md_summary,
    aload_document_txt_extract,
    generate_annotation_hyperlink,
    generate_corpus_hyperlink,
    generate_document_hyperlink,
    get_md_summary_token_length,
    get_note_content_token_length,
    get_notes_for_document_corpus,
    get_partial_note_content,
    load_document_md_summary,
    load_document_txt_extract,
)
from opencontractserver.llms.tools.tool_factory import (
    CoreTool,
    ToolMetadata,
    UnifiedToolFactory,
    create_document_tools,
)

__all__ = [
    # Core tools
    "load_document_md_summary",
    "get_md_summary_token_length",
    "get_notes_for_document_corpus",
    "get_note_content_token_length",
    "get_partial_note_content",
    "load_document_txt_extract",
    "aload_document_txt_extract",
    "aload_document_md_summary",
    # Hyperlink generation tools
    "generate_document_hyperlink",
    "generate_annotation_hyperlink",
    "generate_corpus_hyperlink",
    "agenerate_document_hyperlink",
    "agenerate_annotation_hyperlink",
    "agenerate_corpus_hyperlink",
    # Factory and metadata
    "CoreTool",
    "ToolMetadata",
    "UnifiedToolFactory",
    "create_document_tools",
]
