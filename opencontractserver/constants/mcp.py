"""
Constants for the MCP (Model Context Protocol) server and tools.
"""

# Maximum length, in characters, accepted by the ``create_thread_message``
# write tool. Caps abusive payloads at the tool boundary independently of
# any DB-level limit on the ``ChatMessage.content`` column.
MAX_THREAD_MESSAGE_LENGTH: int = 50_000
