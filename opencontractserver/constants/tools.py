"""
Constants for agent tool configuration.

Defines the namespace prefix used by all agent tools in PipelineSettings.
Tool-specific constants should remain in their own constants modules
(e.g. ``constants/web_search.py``).
"""

# ---------------------------------------------------------------------------
# PipelineSettings namespace prefix for agent tool secrets/settings
# ---------------------------------------------------------------------------
# Tool secrets are stored under a "tool:" namespace in PipelineSettings
# encrypted_secrets to distinguish them from pipeline component secrets.
TOOL_SETTINGS_PREFIX = "tool:"


# ---------------------------------------------------------------------------
# Pagination limits for extract/analyzer discovery tools
# ---------------------------------------------------------------------------
# Hard cap that callers cannot exceed regardless of requested ``limit``.
EXTRACT_ANALYZER_TOOL_MAX_LIST_LIMIT = 100
# Default when the LLM omits ``limit`` on discovery tools (``list_fieldsets``
# / ``list_analyzers``).
EXTRACT_ANALYZER_TOOL_DEFAULT_LIST_LIMIT = 20
# Default for the "recent runs" tools (``list_recent_extracts`` /
# ``list_recent_analyses``) — kept smaller than the discovery default
# because the LLM typically only wants a handful of recent runs.
EXTRACT_ANALYZER_TOOL_DEFAULT_RECENT_LIMIT = 10


# ---------------------------------------------------------------------------
# Pagination limits for the corpus file-management search tool
# ---------------------------------------------------------------------------
# Default page size when ``search_corpus_documents`` is called without an
# explicit ``limit`` — enough rows for the agent to pick a file without
# flooding the context window.
CORPUS_FILE_SEARCH_DEFAULT_LIMIT = 25
# Hard cap that callers cannot exceed regardless of requested ``limit``.
CORPUS_FILE_SEARCH_MAX_LIMIT = 200


# ---------------------------------------------------------------------------
# Extract status strings exposed to agents
# ---------------------------------------------------------------------------
# ``Extract`` has three timestamp fields (``started``, ``finished``,
# ``error``) but no single ``status`` column, so ``_extract_status``
# synthesises one of these strings from the row. Keep these in sync with
# the human GraphQL surface — agents and humans should see the same
# vocabulary.
EXTRACT_STATUS_FAILED = "failed"
EXTRACT_STATUS_COMPLETED = "completed"
EXTRACT_STATUS_RUNNING = "running"
EXTRACT_STATUS_QUEUED = "queued"


# ---------------------------------------------------------------------------
# Analyzer ``input_schema`` size cap (in characters of the JSON dump)
# ---------------------------------------------------------------------------
# ``Analyzer.input_schema`` is a freeform ``JSONField`` populated from the
# analyzer's Python decorator and unbounded by the model. A poorly
# implemented analyzer can therefore register a 100 KB schema that would
# inflate the LLM's context window on every ``list_analyzers`` call.
# Schemas larger than this cap (measured as the length of the
# ``json.dumps`` output) are replaced with a placeholder; the LLM is
# instructed to call ``start_analysis`` (whose dispatch path validates
# the payload against the full schema task-side) to see them.
ANALYZER_INPUT_SCHEMA_MAX_INLINE_CHARS = 4_000


# ---------------------------------------------------------------------------
# Keys that must NOT be tunnelled in via ``analysis_input_data``
# ---------------------------------------------------------------------------
# ``run_task_name_analyzer`` spreads ``analysis_input_data`` directly into
# the analyzer task's keyword arguments via ``**(analysis_input_data or
# {})``. A crafted payload (including one assembled from adversarial
# document content via prompt injection) can therefore override the
# internal kwargs the task expects — most importantly ``analysis_id``
# and the corpus / document scoping. ``start_analysis`` strips these
# before dispatch and logs a warning. The task itself is still the
# canonical validation boundary; this is defense in depth on the
# agent-facing path where the input may be attacker-controlled.
ANALYSIS_INPUT_DATA_RESERVED_KEYS = frozenset(
    {
        "analysis_id",
        "user_id",
        "corpus_id",
        "document_id",
        "document_ids",
        "analyzed_corpus_id",
        "analyzed_documents",
        "corpus_action",
        "corpus_action_id",
        "analyzer",
        "analyzer_id",
    }
)
