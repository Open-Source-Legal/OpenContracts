"""
Central registry of all available tools for agent configurations.

This module provides:
  1. ``ToolDefinition`` / ``AVAILABLE_TOOLS`` — static metadata (names,
     descriptions, flags) exposed via the GraphQL API.
  2. ``ToolFunctionRegistry`` — singleton that maps tool names to their
     async Python function implementations.  This is the **single
     source of truth** for resolving tool names to callable functions.
"""

from __future__ import annotations

import inspect
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from opencontractserver.llms.tools.base_tool import BaseTool
    from opencontractserver.llms.tools.tool_factory import CoreTool

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    """Categories for agent tools."""

    SEARCH = "search"
    DOCUMENT = "document"
    CORPUS = "corpus"
    NOTES = "notes"
    ANNOTATIONS = "annotations"
    COORDINATION = "coordination"
    MODERATION = "moderation"
    IMAGE = "image"
    WEB = "web"
    MEMORY = "memory"
    EXTRACTS = "extracts"
    ANALYZERS = "analyzers"


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of an available tool for agents.

    Flags:
        requires_corpus: Tool needs a corpus_id to function
        requires_approval: Tool requires user confirmation before execution
        requires_write_permission: Tool performs write operations (filtered for read-only users)
    """

    name: str
    description: str
    category: ToolCategory
    requires_corpus: bool = False
    requires_approval: bool = False
    requires_write_permission: bool = False
    parameters: tuple[tuple[str, str, bool], ...] = ()  # (name, description, required)

    def to_dict(self) -> dict:
        """Convert to dictionary for GraphQL response.

        Uses camelCase keys to match GraphQL field names in AvailableToolType,
        since plain graphene.ObjectType doesn't auto-convert snake_case.
        """
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "requiresCorpus": self.requires_corpus,
            "requiresApproval": self.requires_approval,
            "requiresWritePermission": self.requires_write_permission,
            "parameters": [
                {"name": p[0], "description": p[1], "required": p[2]}
                for p in self.parameters
            ],
        }


# =============================================================================
# AVAILABLE TOOLS REGISTRY
# =============================================================================

AVAILABLE_TOOLS: tuple[ToolDefinition, ...] = (
    # -------------------------------------------------------------------------
    # SEARCH TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="similarity_search",
        description=(
            "Search for semantically similar content using vector embeddings. "
            "With multimodal embedder (CLIP), searches across both text and image "
            "content in a unified vector space. Use modalities filter to restrict results "
            "to specific content types."
        ),
        category=ToolCategory.SEARCH,
        parameters=(
            ("query", "The search query text", True),
            ("k", "Number of results to return (default 5)", False),
            (
                "modalities",
                "Filter by content type: ['TEXT'], ['IMAGE'], or ['TEXT', 'IMAGE']",
                False,
            ),
        ),
    ),
    ToolDefinition(
        name="search_exact_text",
        description=(
            "Find exact text matches in a document and return them as source nodes "
            "with page numbers and bounding boxes. Essential for creating proper citations."
        ),
        category=ToolCategory.SEARCH,
        parameters=(
            (
                "search_strings",
                "List of exact strings to find (all occurrences will be found)",
                True,
            ),
        ),
    ),
    # -------------------------------------------------------------------------
    # WEB TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="web_search",
        description=(
            "Search the web for information. Useful for finding recent information, "
            "verifying facts, or researching topics not covered in the loaded "
            "documents. Returns titles, URLs, and content snippets."
        ),
        category=ToolCategory.WEB,
        parameters=(
            ("query", "The search query. Be specific for better results.", True),
            (
                "num_results",
                "Number of results to return (1-20, default 5)",
                False,
            ),
            (
                "search_type",
                'Type of search: "general" (default), "news", or "research"',
                False,
            ),
        ),
    ),
    # -------------------------------------------------------------------------
    # DOCUMENT TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="load_document_summary",
        description=(
            "Load the markdown summary of a document. Optionally truncate by length "
            "and direction (from start or end)."
        ),
        category=ToolCategory.DOCUMENT,
        parameters=(
            ("truncate_length", "Optional number of characters to truncate to", False),
            ("from_start", "If True, truncate from start; if False, from end", False),
        ),
    ),
    ToolDefinition(
        name="get_summary_token_length",
        description="Get the approximate token length of a document's markdown summary.",
        category=ToolCategory.DOCUMENT,
    ),
    ToolDefinition(
        name="get_document_text_length",
        description=(
            "Get the total character length of the document's plain-text extract. "
            "Use this BEFORE loading text to plan your chunking strategy."
        ),
        category=ToolCategory.DOCUMENT,
    ),
    ToolDefinition(
        name="get_remaining_context_budget",
        description=(
            "Inspect the agent's remaining context-window budget for this "
            "turn. Returns model name, total context window, estimated "
            "tokens already used, tokens left before compaction trips, "
            "the compaction threshold ratio, and the recommended "
            "character chunk size for the next ``load_document_text`` "
            "call. Use this when planning multi-step document reads so "
            "each call uses an appropriately-sized chunk."
        ),
        category=ToolCategory.DOCUMENT,
    ),
    # NOTE for developers: the document agent (``PydanticAIDocumentAgent``)
    # replaces this registry entry at runtime with an adaptive variant that
    # auto-sizes ``end`` to the agent's remaining context budget when
    # omitted. The adaptive variant ships its own LLM-facing description.
    # The description below is what non-document-agent callers (and the
    # registry's own docs) see, so keep it user/LLM-focused only.
    ToolDefinition(
        name="load_document_text",
        description=(
            "Load a slice of the document's plain-text extract by "
            "character index. ``start`` defaults to 0; if ``end`` is "
            "omitted the slice runs to the end of the file. After "
            "reading, call ``search_exact_text`` on key passages to "
            "create citations."
        ),
        category=ToolCategory.DOCUMENT,
        parameters=(
            ("start", "Inclusive start character index (default 0)", False),
            (
                "end",
                "Exclusive end character index. If omitted on the document "
                "agent, defaults to a chunk sized for the remaining context "
                "budget; otherwise defaults to the end of the file.",
                False,
            ),
            ("refresh", "If true, refresh the cached content from disk", False),
        ),
    ),
    ToolDefinition(
        name="get_page_image",
        description=(
            "Get a visual image of a specific page from a PDF document as base64. "
            "Useful for inspecting diagrams, tables, images, and other visual content."
        ),
        category=ToolCategory.DOCUMENT,
        parameters=(
            ("page_number", "The page number to render (1-indexed)", True),
            ("image_format", "Image format: 'jpeg' or 'png' (default 'jpeg')", False),
            ("dpi", "Resolution in DPI (default 150)", False),
        ),
    ),
    # -------------------------------------------------------------------------
    # DOCUMENT DESCRIPTION TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="get_document_description",
        description=(
            "Get the document's description field. This is a simple text field "
            "that can be used to store metadata about the document."
        ),
        category=ToolCategory.DOCUMENT,
        parameters=(
            ("truncate_length", "Optional max characters to return", False),
            ("from_start", "If True truncate from beginning, else from end", False),
        ),
    ),
    ToolDefinition(
        name="update_document_description",
        description=(
            "Update the document's description field. "
            "Returns information about the update including previous description."
        ),
        category=ToolCategory.DOCUMENT,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(("new_description", "The new description content", True),),
    ),
    # -------------------------------------------------------------------------
    # DOCUMENT SUMMARY VERSIONING TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="get_document_summary",
        description=(
            "Get the latest summary content for a document in a specific corpus."
        ),
        category=ToolCategory.DOCUMENT,
        requires_corpus=True,
        parameters=(
            ("truncate_length", "Optional max characters to return", False),
            ("from_start", "If True truncate from beginning, else from end", False),
        ),
    ),
    ToolDefinition(
        name="get_document_summary_versions",
        description="Get the version history for a document's summaries in a corpus.",
        category=ToolCategory.DOCUMENT,
        requires_corpus=True,
        parameters=(
            (
                "limit",
                "Maximum number of versions to return (most recent first)",
                False,
            ),
        ),
    ),
    ToolDefinition(
        name="get_document_summary_diff",
        description="Get the diff between two summary versions.",
        category=ToolCategory.DOCUMENT,
        requires_corpus=True,
        parameters=(
            ("from_version", "Starting version number", True),
            ("to_version", "Ending version number", True),
        ),
    ),
    ToolDefinition(
        name="update_document_summary",
        description=(
            "Create a new summary revision for a document. "
            "Returns version information about the created revision."
        ),
        category=ToolCategory.DOCUMENT,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(("new_content", "The new summary content", True),),
    ),
    # -------------------------------------------------------------------------
    # NOTES TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="get_document_notes",
        description=(
            "Retrieve all notes attached to a document in the current corpus. "
            "Returns metadata and first 512-char preview of each note."
        ),
        category=ToolCategory.NOTES,
        requires_corpus=True,
    ),
    ToolDefinition(
        name="search_document_notes",
        description=(
            "Search notes by title or content (case-insensitive). "
            "Returns matching notes for a document."
        ),
        category=ToolCategory.NOTES,
        parameters=(
            ("search_term", "Text to search for in title or content", True),
            ("limit", "Maximum number of notes to return", False),
        ),
    ),
    ToolDefinition(
        name="add_document_note",
        description="Create a new note attached to a document.",
        category=ToolCategory.NOTES,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("title", "Note title", True),
            ("content", "Note content", True),
        ),
    ),
    ToolDefinition(
        name="update_document_note",
        description=(
            "Update an existing note, creating a new revision. "
            "Provide either new_content or diff_text (ndiff format)."
        ),
        category=ToolCategory.NOTES,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("note_id", "ID of the note to update", True),
            (
                "new_content",
                "Full new content (mutually exclusive with diff_text)",
                False,
            ),
            (
                "diff_text",
                "ndiff format diff to apply (mutually exclusive with new_content)",
                False,
            ),
        ),
    ),
    # -------------------------------------------------------------------------
    # CORPUS TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="get_corpus_description",
        description="Retrieve the latest markdown description for this corpus.",
        category=ToolCategory.CORPUS,
        requires_corpus=True,
        parameters=(
            ("truncate_length", "Optionally truncate to this many characters", False),
            ("from_start", "If true, truncate from beginning else from end", False),
        ),
    ),
    ToolDefinition(
        name="update_corpus_description",
        description=(
            "Update corpus description with new markdown text, creating a revision if changed."
        ),
        category=ToolCategory.CORPUS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(("new_content", "Full markdown content", True),),
    ),
    ToolDefinition(
        name="read_corpus_caml_article",
        description=(
            "Read the corpus's Readme.CAML article for citation review. Returns "
            "the markdown content split into blocks (paragraphs) with each "
            "block's existing inline directives and a heuristic flag marking "
            "prose blocks that lack a {{@cite ...}} directive. Use this first "
            "to identify candidate locations before proposing citations."
        ),
        category=ToolCategory.CORPUS,
        requires_corpus=True,
    ),
    ToolDefinition(
        name="propose_caml_citation_match",
        description=(
            "Propose annotation citation candidates for a CAML prose snippet. "
            "Runs the same semantic search the renderer uses over annotations "
            "visible to the current user in this corpus and returns ranked "
            "candidates. Use this to verify a citation match before asking the "
            "user to approve an edit via apply_caml_article_edit."
        ),
        category=ToolCategory.CORPUS,
        requires_corpus=True,
        parameters=(
            (
                "query_text",
                "The CAML prose snippet (sentence or paragraph) to find citations for",
                True,
            ),
            (
                "limit",
                "Maximum number of candidates to return (default 5, capped at 25)",
                False,
            ),
        ),
    ),
    ToolDefinition(
        name="apply_caml_article_edit",
        description=(
            "Replace a single occurrence of target_text inside the corpus's "
            "Readme.CAML with replacement_text. Each call requires explicit "
            "approval and only mutates one location at a time, so the agent "
            "can step through citations one-by-one. target_text MUST match "
            "exactly once in the article -- the call fails closed otherwise."
        ),
        category=ToolCategory.CORPUS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            (
                "target_text",
                "Exact substring to replace. Must occur exactly once in the article.",
                True,
            ),
            (
                "replacement_text",
                "Replacement content (typically the original sentence plus "
                "an inline {{@cite ...}} directive).",
                True,
            ),
            (
                "rationale",
                "Short explanation surfaced in the approval modal so the user "
                "understands why the edit was proposed.",
                True,
            ),
        ),
    ),
    ToolDefinition(
        name="move_document",
        description=(
            "Move a document to a different folder within the current corpus. "
            "Pass target_folder_id to specify the destination folder, or omit "
            "it to move the document to the corpus root."
        ),
        # CORPUS (not DOCUMENT) because this manipulates the corpus folder
        # hierarchy, not the document's own content or metadata.  It is only
        # available to corpus-level agents where the LLM picks which document
        # to move; document-scoped agents operate on a single fixed document.
        category=ToolCategory.CORPUS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            (
                "document_id",
                "ID of the document to move",
                True,
            ),
            (
                "target_folder_id",
                "ID of the destination folder, or omit for corpus root",
                False,
            ),
        ),
    ),
    # -------------------------------------------------------------------------
    # COORDINATION TOOLS (for corpus agents)
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="list_documents",
        description=(
            "List all documents in the current corpus with their IDs, titles, and descriptions. "
            "Use this to decide which document to query with ask_document."
        ),
        category=ToolCategory.COORDINATION,
        requires_corpus=True,
    ),
    ToolDefinition(
        name="ask_document",
        description=(
            "Ask a question to a document-specific agent within this corpus. "
            "The sub-agent has full access to document tools (search, summary, notes, etc.)."
        ),
        category=ToolCategory.COORDINATION,
        requires_corpus=True,
        parameters=(
            (
                "document_id",
                "ID of the target document (must belong to this corpus)",
                True,
            ),
            ("question", "The natural-language question to forward", True),
        ),
    ),
    # -------------------------------------------------------------------------
    # ANNOTATION TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="duplicate_annotations_with_label",
        description=(
            "Duplicate existing annotations with a new label. "
            "Creates copies of annotations with the specified label applied."
        ),
        category=ToolCategory.ANNOTATIONS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("annotation_ids", "List of annotation IDs to duplicate", True),
            ("new_label_text", "Text of the label to apply to duplicates", True),
            ("label_type", "Optional label type (defaults to TOKEN_LABEL)", False),
        ),
    ),
    ToolDefinition(
        name="add_annotations_from_exact_strings",
        description=(
            "Create annotations for exact string matches in documents. "
            "For PDFs: creates token-level annotations. For text: creates span annotations."
        ),
        category=ToolCategory.ANNOTATIONS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            (
                "items",
                "List of objects with keys: label_text (str), exact_string (str)",
                True,
            ),
        ),
    ),
    ToolDefinition(
        name="scan_and_annotate_pii",
        description=(
            "Scan a document for sensitive information (emails, phone numbers, "
            "people, addresses, account numbers, URLs, dates, secrets) using the "
            "privacy-filter service and create one labeled annotation per detection. "
            "Supports PDF (token-level annotations) and plain-text documents "
            "(character-span annotations); other file types (docx, html, etc.) "
            "are rejected with an error. "
            "Set dry_run=True to preview detections without writing annotations. "
            "Use entity_groups to restrict the scan to specific categories and "
            "start_char/end_char to scope the scan to a slice of the document."
        ),
        category=ToolCategory.ANNOTATIONS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("min_score", "Minimum confidence threshold (0..1), default 0.5", False),
            (
                "entity_groups",
                "Optional allowlist, e.g. ['private_email','phone_number']",
                False,
            ),
            (
                "dry_run",
                "If True, return detections without creating annotations",
                False,
            ),
            (
                "start_char",
                "Optional start offset into the document text (scope the scan)",
                False,
            ),
            ("end_char", "Optional end offset into the document text", False),
        ),
    ),
    ToolDefinition(
        name="create_document_index",
        description=(
            "Create a hierarchical document index (table of contents) from exact "
            "string matches. Each entry has a title, markdown description, an "
            "exact_string anchor, and a parent_index for hierarchy (-1 for roots). "
            "Uses the OC_SECTION label."
        ),
        category=ToolCategory.ANNOTATIONS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            (
                "entries",
                (
                    "List of objects with keys: title (str), exact_string (str), "
                    "long_description (str, optional), parent_index (int, -1 for root)"
                ),
                True,
            ),
        ),
    ),
    ToolDefinition(
        name="get_annotation_images",
        description=(
            "Get all images contained within an annotation's bounding box. "
            "Returns image metadata and base64-encoded data for each image. "
            "Use this to inspect visual content within annotated regions."
        ),
        category=ToolCategory.ANNOTATIONS,
        parameters=(("annotation_id", "ID of the annotation", True),),
    ),
    # -------------------------------------------------------------------------
    # IMAGE TOOLS (for multimodal document processing)
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="list_document_images",
        description=(
            "List all images in a document with metadata (page number, position, "
            "dimensions, format). Use this to discover images before retrieving them. "
            "For PDFs, images are extracted during parsing with docling."
        ),
        category=ToolCategory.IMAGE,
        parameters=(
            (
                "page_index",
                "Optional 0-based page filter to list images from specific page",
                False,
            ),
        ),
    ),
    ToolDefinition(
        name="get_document_image",
        description=(
            "Get base64-encoded image data for a specific image token. "
            "Use list_document_images first to find page_index and token_index. "
            "Returns the image in its original format (PNG, JPEG, etc.)."
        ),
        category=ToolCategory.IMAGE,
        parameters=(
            ("page_index", "0-based page index where the image is located", True),
            ("token_index", "0-based token index of the image on the page", True),
        ),
    ),
    # -------------------------------------------------------------------------
    # MODERATION TOOLS (for thread/message moderation)
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="get_thread_context",
        description=(
            "Get thread metadata including title, creator, lock/pin status, "
            "message count, and linked corpus/document info."
        ),
        category=ToolCategory.MODERATION,
        parameters=(("thread_id", "ID of the thread", True),),
    ),
    ToolDefinition(
        name="get_thread_messages",
        description=(
            "Retrieve recent messages from a thread for context. Returns message content, "
            "author info, timestamps, and vote counts."
        ),
        category=ToolCategory.MODERATION,
        parameters=(
            ("thread_id", "ID of the thread", True),
            ("limit", "Maximum number of messages to return (default 20)", False),
            ("include_deleted", "Include soft-deleted messages (default False)", False),
        ),
    ),
    ToolDefinition(
        name="get_message_content",
        description="Get full content of a specific message including metadata.",
        category=ToolCategory.MODERATION,
        parameters=(("message_id", "ID of the message", True),),
    ),
    ToolDefinition(
        name="delete_message",
        description=(
            "Soft delete a message from a thread. Creates a moderation audit log. "
            "Use when content violates community guidelines."
        ),
        category=ToolCategory.MODERATION,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("message_id", "ID of the message to delete", True),
            ("reason", "Reason for deletion (for audit log)", True),
        ),
    ),
    ToolDefinition(
        name="lock_thread",
        description=(
            "Lock a thread to prevent further messages. Use for resolved discussions "
            "or threads that have become contentious."
        ),
        category=ToolCategory.MODERATION,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("thread_id", "ID of the thread to lock", True),
            ("reason", "Reason for locking (for audit log)", True),
        ),
    ),
    ToolDefinition(
        name="unlock_thread",
        description="Unlock a previously locked thread to allow new messages.",
        category=ToolCategory.MODERATION,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("thread_id", "ID of the thread to unlock", True),
            ("reason", "Reason for unlocking (for audit log)", True),
        ),
    ),
    ToolDefinition(
        name="add_thread_message",
        description=(
            "Add an agent message to a thread. Use for providing guidance, "
            "warnings, or additional context to thread participants."
        ),
        category=ToolCategory.MODERATION,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("thread_id", "ID of the thread to post to", True),
            ("content", "Message content (markdown supported)", True),
        ),
    ),
    ToolDefinition(
        name="pin_thread",
        description="Pin a thread to appear at the top of the thread list.",
        category=ToolCategory.MODERATION,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("thread_id", "ID of the thread to pin", True),
            ("reason", "Reason for pinning (for audit log)", True),
        ),
    ),
    ToolDefinition(
        name="unpin_thread",
        description="Unpin a previously pinned thread.",
        category=ToolCategory.MODERATION,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            ("thread_id", "ID of the thread to unpin", True),
            ("reason", "Reason for unpinning (for audit log)", True),
        ),
    ),
    # -------------------------------------------------------------------------
    # UTILITY TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="create_markdown_link",
        description=(
            "Create a markdown-formatted link for an annotation, corpus, document, or conversation. "
            "Returns [Title](URL) format following OpenContracts routing patterns. "
            "Useful for creating references in notes, summaries, or responses."
        ),
        category=ToolCategory.COORDINATION,
        parameters=(
            (
                "entity_type",
                "Type of entity: 'annotation', 'corpus', 'document', or 'conversation'",
                True,
            ),
            ("entity_id", "The primary key (ID) of the entity", True),
        ),
    ),
    # -------------------------------------------------------------------------
    # MEMORY TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="get_corpus_memory",
        description=(
            "Read accumulated insights about this corpus from previous interactions. "
            "Returns patterns about document structure, effective search strategies, "
            "and common question types learned over time."
        ),
        category=ToolCategory.MEMORY,
        requires_corpus=True,
        parameters=(
            (
                "section",
                "Optional section to filter to (e.g., 'Collection Patterns' or 'Query Patterns')",
                False,
            ),
        ),
    ),
    ToolDefinition(
        name="suggest_memory_update",
        description=(
            "Suggest a new insight to add to corpus memory for future interactions. "
            "Use this when you discover a useful pattern about the document collection "
            "or an effective search strategy."
        ),
        category=ToolCategory.MEMORY,
        requires_corpus=True,
        requires_write_permission=True,
        parameters=(
            (
                "section",
                "Which section: 'collection_patterns' or 'query_patterns'",
                True,
            ),
            (
                "insight",
                "The insight text, formatted as '- **Title**: Description'",
                True,
            ),
        ),
    ),
    # -------------------------------------------------------------------------
    # EXTRACT TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="list_fieldsets",
        description=(
            "List the configured Fieldsets (extract column schemas) visible to "
            "the user. Use this to pick an existing Fieldset before calling "
            "start_extract — do not invent new column definitions. Returns "
            "each Fieldset's name, description, and column names. Pass "
            "include_columns=true to also get the full column definitions "
            "(query, output_type, instructions) inline."
        ),
        category=ToolCategory.EXTRACTS,
        requires_corpus=True,
        parameters=(
            ("limit", "Max number of fieldsets to return (default 20)", False),
            (
                "include_columns",
                "When true, include the full column definitions "
                "(query/match_text/output_type/instructions/extract_is_list) "
                "inline. Default false returns column names only to keep "
                "the response compact.",
                False,
            ),
        ),
    ),
    ToolDefinition(
        name="start_extract",
        description=(
            "Run a configured Fieldset over the corpus to extract structured "
            "data into Datacells. Always pick a fieldset_id from list_fieldsets; "
            "this tool does not invent new columns. Returns the new extract_id "
            "with status='queued' — the Celery pipeline runs asynchronously. "
            "If document_ids is omitted on a corpus agent the run targets the "
            "entire corpus; for corpora with thousands of documents pass an "
            "explicit document_ids subset to bound the dispatch cost."
        ),
        category=ToolCategory.EXTRACTS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            (
                "fieldset_id",
                "Integer ID of an existing Fieldset to apply (Fieldset PKs "
                "are auto-increment integers — pass the `id` value from "
                "list_fieldsets, not the `name`).",
                True,
            ),
            ("name", "Optional name for the new Extract record", False),
            (
                "document_ids",
                "Optional list of Document IDs to scope the run. Omitted = "
                "current document for doc agents, whole corpus for corpus "
                "agents.",
                False,
            ),
        ),
    ),
    ToolDefinition(
        name="list_recent_extracts",
        description=(
            "List the most recent Extracts on this corpus visible to the user, "
            "with status and fieldset info. Use this before start_extract to "
            "avoid re-running an extract that already completed."
        ),
        category=ToolCategory.EXTRACTS,
        requires_corpus=True,
        parameters=(("limit", "Max number of extracts to return (default 10)", False),),
    ),
    # -------------------------------------------------------------------------
    # ANALYZER TOOLS
    # -------------------------------------------------------------------------
    ToolDefinition(
        name="list_analyzers",
        description=(
            "List the Analyzers visible to the user. The corpus_id is used "
            "to verify you can access this corpus, but the returned list is "
            "NOT filtered by corpus-type affinity — it contains every "
            "non-disabled analyzer visible to you, and the agent is "
            "responsible for picking one that makes sense for the corpus. "
            "Use this to pick an analyzer_id before calling start_analysis. "
            "Note: Analyzer.id is a STRING (e.g. 'noop.analyzer'), unlike "
            "Fieldset.id which is an integer."
        ),
        category=ToolCategory.ANALYZERS,
        requires_corpus=True,
        parameters=(
            ("limit", "Max number of analyzers to return (default 20)", False),
        ),
    ),
    ToolDefinition(
        name="start_analysis",
        description=(
            "Run a configured Analyzer over the corpus. Returns the new "
            "analysis_id with status='queued' — the analyzer runs "
            "asynchronously via the existing Gremlin/task pipeline. If "
            "document_ids is omitted on a corpus agent the run targets the "
            "entire corpus; for corpora with thousands of documents pass an "
            "explicit document_ids subset to bound the dispatch cost."
        ),
        category=ToolCategory.ANALYZERS,
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True,
        parameters=(
            (
                "analyzer_id",
                "STRING ID of an existing Analyzer (Analyzer PKs are "
                "CharFields like 'noop.analyzer' — pass the `id` value from "
                "list_analyzers, not the `description`).",
                True,
            ),
            (
                "document_ids",
                "Optional list of Document IDs to scope the run. Omitted = "
                "current document for doc agents, whole corpus for corpus "
                "agents.",
                False,
            ),
            (
                "analysis_input_data",
                "Optional JSON object matching the analyzer's input_schema",
                False,
            ),
        ),
    ),
    ToolDefinition(
        name="list_recent_analyses",
        description=(
            "List the most recent Analyses on this corpus visible to the user, "
            "with status and analyzer info. Use this before start_analysis to "
            "avoid re-running an analyzer that already produced results."
        ),
        category=ToolCategory.ANALYZERS,
        requires_corpus=True,
        parameters=(("limit", "Max number of analyses to return (default 10)", False),),
    ),
)


def get_all_tools() -> list[dict]:
    """Get all available tools as a list of dictionaries."""
    return [tool.to_dict() for tool in AVAILABLE_TOOLS]


def get_tools_by_category(category: str) -> list[dict]:
    """Get tools filtered by category."""
    try:
        cat = ToolCategory(category)
    except ValueError:
        return []
    return [tool.to_dict() for tool in AVAILABLE_TOOLS if tool.category == cat]


def get_tool_by_name(name: str) -> dict | None:
    """Get a single tool by name."""
    for tool in AVAILABLE_TOOLS:
        if tool.name == name:
            return tool.to_dict()
    return None


def get_tool_names() -> list[str]:
    """Get just the names of all available tools."""
    return [tool.name for tool in AVAILABLE_TOOLS]


def validate_tool_names(names: list[str]) -> tuple[list[str], list[str]]:
    """
    Validate a list of tool names against the registry.

    Returns:
        Tuple of (valid_names, invalid_names)
    """
    valid_names = get_tool_names()
    valid = [n for n in names if n in valid_names]
    invalid = [n for n in names if n not in valid_names]
    return valid, invalid


def get_moderation_tool_names() -> list[str]:
    """Get names of all moderation tools."""
    return [
        tool.name
        for tool in AVAILABLE_TOOLS
        if tool.category == ToolCategory.MODERATION
    ]


# Alias for backwards compatibility
TOOL_REGISTRY = AVAILABLE_TOOLS


# =============================================================================
# TOOL FUNCTION REGISTRY — maps tool names to implementations
# =============================================================================


@dataclass
class ToolRegistryEntry:
    """Links a ToolDefinition to its async function implementation.

    All registered tools MUST be async.  Sync versions of tool functions
    exist in the source files for test convenience only and are never
    registered here.  ``PydanticAIToolWrapper`` does NOT wrap sync
    functions in a thread pool, so a sync tool that touches the Django
    ORM will raise ``SynchronousOnlyOperation`` at runtime.

    If ``tool_class`` is set to a :class:`BaseTool` subclass, the tool
    is only available when ``tool_class.is_configured()`` returns True.
    This enables database-level enablement gating — the tool silently
    disappears from agents until an admin configures the required
    secrets (API keys, etc.) in PipelineSettings.
    """

    definition: ToolDefinition
    async_func: Callable
    aliases: tuple[str, ...] = field(default_factory=tuple)
    tool_class: type[BaseTool] | None = None  # BaseTool subclass for enablement gating

    def __post_init__(self) -> None:
        if not inspect.iscoroutinefunction(self.async_func):
            raise TypeError(
                f"Tool {self.definition.name!r}: async_func must be an async "
                f"function, got {self.async_func!r}. All registered tools must "
                f"be async."
            )


class ToolFunctionRegistry:
    """Singleton registry: tool name -> async function refs + metadata.

    Single source of truth for resolving tool names to implementations.
    All registered tools must be async.
    """

    _instance: ToolFunctionRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._entries: dict[str, ToolRegistryEntry] = {}
        self._aliases: dict[str, str] = {}

    @classmethod
    def get(cls) -> ToolFunctionRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = cls()
                    inst._populate()
                    cls._instance = inst
        return cls._instance

    def register(self, entry: ToolRegistryEntry) -> None:
        self._entries[entry.definition.name] = entry
        for alias in entry.aliases:
            self._aliases[alias] = entry.definition.name

    def resolve(self, name: str) -> ToolRegistryEntry | None:
        canonical = self._aliases.get(name, name)
        return self._entries.get(canonical)

    def to_core_tool(self, name: str) -> CoreTool | None:
        """Resolve *name* -> ``CoreTool`` using its async implementation.

        If the entry has a ``tool_class`` (:class:`BaseTool` subclass), the
        tool is only returned when ``tool_class.is_configured()`` is True.
        This enforces database-level enablement — unconfigured tools are
        silently skipped, just like pipeline components without credentials.
        """
        from opencontractserver.llms.tools.tool_factory import CoreTool

        entry = self.resolve(name)
        if not entry:
            return None

        # Database-level enablement gate.
        # NOTE: is_configured() performs sync ORM access — safe here because
        # to_core_tool() is called during sync tool resolution, never from
        # an async context.  See CLAUDE.md pitfall #13.
        if entry.tool_class is not None:
            try:
                if not entry.tool_class.is_configured():
                    logger.info(
                        "Tool '%s' skipped — not configured (missing required "
                        "settings in PipelineSettings key '%s')",
                        name,
                        entry.tool_class.full_settings_key(),
                    )
                    return None
            except Exception:
                logger.debug("Tool '%s' configuration check failed — skipping", name)
                return None

        return CoreTool.from_function(
            entry.async_func,
            name=entry.definition.name,
            description=entry.definition.description,
            requires_approval=entry.definition.requires_approval,
            requires_corpus=entry.definition.requires_corpus,
            requires_write_permission=entry.definition.requires_write_permission,
        )

    @classmethod
    def reset(cls) -> None:
        """Reset for test isolation."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Internal: populate with all known tools on first access
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        """Lazily import and register all async tool functions.

        ``FUNCTION_MAP`` + ``AVAILABLE_TOOLS`` are the ONLY two places to
        edit when adding a new tool.  ``_resolve_tools()`` and the agent
        factories never need touching again.

        All registered tools MUST be async.  Sync versions of tool
        functions exist in the source files for test convenience only
        and are never imported here.
        """
        # Lazy imports avoid circular dependencies — async only
        from opencontractserver.llms.tools.core_tools import (
            aadd_annotations_from_exact_strings,
            aadd_document_note,
            aapply_caml_article_edit,
            acreate_document_index,
            acreate_markdown_link,
            aduplicate_annotations_with_label,
            aget_corpus_description,
            aget_corpus_memory,
            aget_document_description,
            aget_document_summary,
            aget_document_summary_diff,
            aget_document_summary_versions,
            aget_md_summary_token_length,
            aget_notes_for_document_corpus,
            aget_page_image,
            alist_analyzers,
            alist_fieldsets,
            alist_recent_analyses,
            alist_recent_extracts,
            aload_document_md_summary,
            aload_document_txt_extract,
            amove_document,
            apropose_caml_citation_match,
            aread_corpus_caml_article,
            ascan_and_annotate_pii,
            asearch_document_notes,
            asearch_exact_text_as_sources,
            astart_analysis,
            astart_extract,
            asuggest_memory_update,
            aupdate_corpus_description,
            aupdate_document_description,
            aupdate_document_note,
            aupdate_document_summary,
        )
        from opencontractserver.llms.tools.image_tools import (
            aget_annotation_images,
            aget_document_image,
            alist_document_images,
        )
        from opencontractserver.llms.tools.moderation_tools import (
            aadd_thread_message,
            adelete_message,
            aget_message_content,
            aget_thread_context,
            aget_thread_messages,
            alock_thread,
            apin_thread,
            aunlock_thread,
            aunpin_thread,
        )
        from opencontractserver.llms.tools.web_search_tools import (
            WebSearchTool,
            aweb_search,
        )

        # canonical_name -> (async_func, aliases)
        FUNCTION_MAP: dict[str, tuple[Callable, tuple[str, ...]]] = {
            # Core document tools
            "load_document_summary": (
                aload_document_md_summary,
                ("load_md_summary", "load_document_md_summary"),
            ),
            "get_summary_token_length": (
                aget_md_summary_token_length,
                ("md_summary_length", "get_md_summary_token_length"),
            ),
            "load_document_text": (
                aload_document_txt_extract,
                ("load_document_txt_extract",),
            ),
            "get_document_description": (aget_document_description, ()),
            "update_document_description": (aupdate_document_description, ()),
            "get_document_summary": (aget_document_summary, ()),
            "get_document_summary_versions": (aget_document_summary_versions, ()),
            "get_document_summary_diff": (aget_document_summary_diff, ()),
            "update_document_summary": (aupdate_document_summary, ()),
            "get_document_notes": (
                aget_notes_for_document_corpus,
                ("get_notes", "get_notes_for_document_corpus"),
            ),
            "search_document_notes": (asearch_document_notes, ()),
            "add_document_note": (aadd_document_note, ()),
            "update_document_note": (aupdate_document_note, ()),
            "search_exact_text": (
                asearch_exact_text_as_sources,
                ("search_exact_text_as_sources",),
            ),
            "get_page_image": (aget_page_image, ()),
            "duplicate_annotations_with_label": (aduplicate_annotations_with_label, ()),
            "add_annotations_from_exact_strings": (
                aadd_annotations_from_exact_strings,
                (),
            ),
            "scan_and_annotate_pii": (ascan_and_annotate_pii, ()),
            "create_document_index": (acreate_document_index, ()),
            # Corpus tools
            "get_corpus_description": (aget_corpus_description, ()),
            "update_corpus_description": (aupdate_corpus_description, ()),
            "move_document": (amove_document, ()),
            # CAML article review tools (corpus-scoped Readme.CAML editor)
            "read_corpus_caml_article": (aread_corpus_caml_article, ()),
            "propose_caml_citation_match": (apropose_caml_citation_match, ()),
            "apply_caml_article_edit": (aapply_caml_article_edit, ()),
            # Image tools
            "list_document_images": (alist_document_images, ()),
            "get_document_image": (aget_document_image, ()),
            "get_annotation_images": (aget_annotation_images, ()),
            # Moderation tools
            "get_thread_context": (aget_thread_context, ()),
            "get_thread_messages": (aget_thread_messages, ()),
            "get_message_content": (aget_message_content, ()),
            "delete_message": (adelete_message, ()),
            "lock_thread": (alock_thread, ()),
            "unlock_thread": (aunlock_thread, ()),
            "add_thread_message": (aadd_thread_message, ()),
            "pin_thread": (apin_thread, ()),
            "unpin_thread": (aunpin_thread, ()),
            # Utility tools
            "create_markdown_link": (acreate_markdown_link, ()),
            # Web tools
            "web_search": (aweb_search, ("search_web",)),
            # Memory tools
            "get_corpus_memory": (aget_corpus_memory, ()),
            "suggest_memory_update": (asuggest_memory_update, ()),
            # Extract & analyzer tools
            "list_fieldsets": (alist_fieldsets, ()),
            "start_extract": (astart_extract, ()),
            "list_recent_extracts": (alist_recent_extracts, ()),
            "list_analyzers": (alist_analyzers, ()),
            "start_analysis": (astart_analysis, ()),
            "list_recent_analyses": (alist_recent_analyses, ()),
        }
        # NOTE: similarity_search, get_document_text_length,
        # get_remaining_context_budget, list_documents, and ask_document
        # are NOT in FUNCTION_MAP because they require runtime context
        # (vector store, cache, agent deps snapshot, sub-agent) that is
        # built in the agent factory.  They have ToolDefinition entries
        # only for the GraphQL "available tools" API.

        # Legacy aliases (short names -> canonical names)
        LEGACY_ALIASES: dict[str, str] = {
            "summarize": "load_document_summary",
            "notes": "get_document_notes",
        }

        # Maps tool names to BaseTool subclasses for database-level
        # enablement gating.  Tools without an entry here are always
        # available (the legacy default).
        TOOL_CLASSES: dict[str, type] = {
            "web_search": WebSearchTool,
        }

        definitions_by_name = {d.name: d for d in AVAILABLE_TOOLS}
        for name, (async_fn, aliases) in FUNCTION_MAP.items():
            defn = definitions_by_name.get(name)
            if defn is None:
                logger.debug(
                    "Tool '%s' in FUNCTION_MAP has no matching ToolDefinition — skipping",
                    name,
                )
                continue
            self.register(
                ToolRegistryEntry(
                    definition=defn,
                    async_func=async_fn,
                    aliases=aliases,
                    tool_class=TOOL_CLASSES.get(name),
                )
            )

        for alias, canonical in LEGACY_ALIASES.items():
            self._aliases[alias] = canonical
