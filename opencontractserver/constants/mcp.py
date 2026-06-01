"""
Constants for the MCP (Model Context Protocol) server and tools.
"""

# Maximum length, in characters, accepted by the ``create_thread_message``
# write tool. Caps abusive payloads at the tool boundary independently of
# any DB-level limit on the ``ChatMessage.content`` column.
MAX_THREAD_MESSAGE_LENGTH: int = 50_000

# Truncation budgets (characters) for MCP tool payloads. Keep AI-facing
# results bounded so a single tool call cannot blow the context window.
MCP_SEARCH_SNIPPET_MAX_CHARS: int = 1_500  # passage hit `text`
MCP_BLOCK_SNIPPET_MAX_CHARS: int = 4_000  # subtree-group block `text`
MCP_REL_ANNOTATION_TEXT_MAX_CHARS: int = 500  # source/target text in list_relationships
MCP_DOCUMENT_TEXT_DEFAULT_CHARS: int = 50_000  # default get_document_text window
MCP_DOCUMENT_TEXT_MAX_CHARS: int = 200_000  # hard cap for get_document_text max_chars
