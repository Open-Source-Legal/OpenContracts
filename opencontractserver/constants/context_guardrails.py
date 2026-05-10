"""
Constants for LLM context window management, conversation compaction, and
tool output guardrails.

These thresholds control when and how the system compacts conversation
history to prevent context overflow when talking to LLMs.
"""

# ---------------------------------------------------------------------------
# Model context window sizes (in tokens)
# ---------------------------------------------------------------------------
# Maps model name prefixes to their maximum context window.  When an exact
# match is not found the lookup falls back to prefix matching (e.g.
# "gpt-4o-mini" matches the "gpt-4o" entry).
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3": 200_000,
    "o3-mini": 128_000,
    "o4-mini": 200_000,
    # Anthropic
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    # Google
    "gemini-1.5-pro": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
}

# Fallback context window when the model is unknown.
DEFAULT_CONTEXT_WINDOW: int = 128_000

# ---------------------------------------------------------------------------
# Compaction thresholds
# ---------------------------------------------------------------------------
# Fraction of the model context window at which compaction is triggered.
# E.g. 0.75 means "compact when estimated usage exceeds 75% of the window".
COMPACTION_THRESHOLD_RATIO: float = 0.75

# Minimum number of recent messages to *always* preserve verbatim (never
# summarised), regardless of their token cost.  This ensures the LLM sees
# enough immediate context to maintain conversational coherence.
MIN_RECENT_MESSAGES: int = 4

# Maximum number of recent messages to preserve.  Caps memory usage for
# very chatty sessions where individual messages are small.
MAX_RECENT_MESSAGES: int = 20

# ---------------------------------------------------------------------------
# Tool output guardrails
# ---------------------------------------------------------------------------
# Hard ceiling (in characters) for a single tool return value that gets
# inserted into the conversation history.  Outputs exceeding this limit
# are truncated with an ellipsis marker.
MAX_TOOL_OUTPUT_CHARS: int = 50_000

# Truncation notice appended when a tool output is clipped.
TOOL_OUTPUT_TRUNCATION_NOTICE: str = (
    "\n\n[… output truncated to {limit} characters — "
    "use start/end parameters to load specific sections]"
)

# Floor (in characters) for the budget-derived default chunk size used by
# ``load_document_text`` when ``end`` is omitted. Keeps the implicit slice
# big enough to be useful for whole-document tasks (summarisation, full-text
# Q&A) even when the per-turn context budget is starved. ``MAX_TOOL_OUTPUT_CHARS``
# is the wrapper-level ceiling for stringified tool returns; the dict-returning
# ``load_document_text`` deliberately bypasses that truncation, so a 5K floor
# is comfortably below any model's residual context.
#
# Trade-off: when the agent is genuinely starved (≈4K-token effective budget,
# ≈14K chars residual), several end-less ``load_document_text`` calls will
# each individually clear the floor but can collectively overflow. The
# in-turn deduction (``turn_implicit_doc_text_chars``) backs successive
# implicit reads off proportionally, but a single call still serves at
# least 5K chars even if that crosses the residual budget. We accept this
# usability tax over the alternative of the agent receiving a sub-1K
# slice that's useless for whole-document tasks.
MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS: int = 5_000

# Soft warning threshold for the budget-derived implicit chunk size,
# expressed as a fraction of the model's full context window in characters
# (``context_window_tokens * CHARS_PER_TOKEN_ESTIMATE``). When
# ``recommended_chunk_chars`` exceeds this fraction of the window,
# ``load_document_text`` emits a warning so the heuristic's drift is
# observable in production logs (e.g. when ``CHARS_PER_TOKEN_ESTIMATE``
# no longer reflects the tokenisation density of multilingual or code-heavy
# documents). The threshold is *relative* so 1M-token models (Gemini 1.5,
# Claude Opus large-context) don't spam the warning on legitimately large
# recommendations — half the entire window is the sign of real drift, not
# just a big context. This is only an observability signal — the chunk is
# still served at the budgeted size.
LARGE_IMPLICIT_CHUNK_WARN_RATIO: float = 0.5

# ---------------------------------------------------------------------------
# Compaction summary budget
# ---------------------------------------------------------------------------
# Target token length for the summary that replaces compacted messages.
# Keeps the summary concise while preserving key facts.
COMPACTION_SUMMARY_TARGET_TOKENS: int = 300

# Maximum token budget for the *cumulative* compaction summary stored in
# the database.  When a merge would exceed this, the summary is truncated
# to keep it from becoming a significant fraction of the context window.
COMPACTION_SUMMARY_MAX_TOKENS: int = 600

# System-level instruction prepended to the summary so the LLM knows its
# origin.  Must be kept short to avoid eating into the summary budget.
COMPACTION_SUMMARY_PREFIX: str = (
    "[Conversation summary — earlier messages were compacted to save context]\n"
)

# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------
# Average characters per token used for the fast heuristic estimator.
# English text averages ~4 chars/token across common tokenisers.  Using
# 3.5 instead of 4 chars-per-token means we over-estimate the token count
# for a given string, triggering compaction conservatively rather than
# risking a hard context-window overflow.
CHARS_PER_TOKEN_ESTIMATE: float = 3.5

# ---------------------------------------------------------------------------
# Ephemeral session context guardrail
# ---------------------------------------------------------------------------
# Fraction of the model context window at which an ephemeral (anonymous)
# session is considered exhausted.  At this point the WebSocket consumer
# signals the client that no further turns are accepted.  Set conservatively
# below 1.0 to leave headroom for the system prompt and tool outputs.
EPHEMERAL_CONTEXT_EXHAUSTION_RATIO: float = 0.9

# ---------------------------------------------------------------------------
# WebSocket error types
# ---------------------------------------------------------------------------
# Error type identifier sent to the client when an ephemeral session has
# exhausted its context window.  Used in both the backend consumer and the
# frontend message handler to avoid duplicating magic strings.
WS_ERROR_CONTEXT_EXHAUSTED: str = "CONTEXT_EXHAUSTED"
