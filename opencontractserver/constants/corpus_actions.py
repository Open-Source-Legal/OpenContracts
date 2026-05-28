"""
Constants for corpus action configuration.

Provides default tool sets and prompt templates for agent-based corpus actions.

Note: Keys in the dicts below use the *string values* of
``CorpusActionTrigger`` (e.g. ``"add_document"``) rather than importing the
enum directly. Constants modules should never import from model modules to
avoid circular dependencies. Alignment with the enum is verified in
``test_corpus_action_model.py``.
"""

# ---------------------------------------------------------------------------
# Default tool sets by trigger type
# ---------------------------------------------------------------------------
# When a user creates an agent corpus action without specifying tools,
# the system uses these defaults based on the trigger type.

DEFAULT_DOCUMENT_ACTION_TOOLS: list[str] = [
    "load_document_text",
    "get_document_description",
    "update_document_description",
    "get_document_summary",
    "update_document_summary",
    "add_document_note",
    "search_exact_text",
]

DEFAULT_THREAD_ACTION_TOOLS: list[str] = [
    "get_thread_context",
    "get_thread_messages",
    "get_message_content",
    "add_thread_message",
    "lock_thread",
    "unlock_thread",
    "delete_message",
    "pin_thread",
    "unpin_thread",
]

# Map trigger types to their default tool sets.
# Keys correspond to CorpusActionTrigger enum values (see note above).
DEFAULT_TOOLS_BY_TRIGGER: dict[str, list[str]] = {
    "add_document": DEFAULT_DOCUMENT_ACTION_TOOLS,
    "edit_document": DEFAULT_DOCUMENT_ACTION_TOOLS,
    "new_thread": DEFAULT_THREAD_ACTION_TOOLS,
    "new_message": DEFAULT_THREAD_ACTION_TOOLS,
    "manual_batch": DEFAULT_DOCUMENT_ACTION_TOOLS,
}

# ---------------------------------------------------------------------------
# Trigger descriptions for system prompt context injection
# ---------------------------------------------------------------------------
# Keys correspond to CorpusActionTrigger enum values (see note above).

TRIGGER_DESCRIPTIONS: dict[str, str] = {
    "add_document": "was just added to",
    "edit_document": "was just edited in",
    "new_thread": "triggered by new thread in",
    "new_message": "triggered by new message in",
    "manual_batch": "was batch-processed in",
}

# ---------------------------------------------------------------------------
# System prompt truncation limits
# ---------------------------------------------------------------------------
# Max characters of document description injected into the system prompt.
MAX_DESCRIPTION_PREVIEW_LENGTH = 500

# Max characters of a thread message preview in the system prompt.
MAX_MESSAGE_PREVIEW_LENGTH = 200

# ---------------------------------------------------------------------------
# Manual batch-run limits
# ---------------------------------------------------------------------------
# Hard cap on the number of documents a single batch-run mutation may queue.
# Prevents one click from fanning out hundreds of agent runs and flooding the
# LLM rate limit. If the eligible-document set exceeds this, the mutation
# refuses; the user is expected to narrow scope or wait for in-flight runs
# to complete before pressing again.
BATCH_RUN_MAX_DOCS = 200
