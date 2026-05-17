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
# Extract status strings exposed to agents
# ---------------------------------------------------------------------------
# ``Extract`` has three timestamp fields (``started``, ``finished``,
# ``error``) but no single ``status`` column, so ``_extract_status``
# synthesises one of these strings from the row. Keep these in sync with
# the human GraphQL surface — agents and humans should see the same
# vocabulary. Analyses already have a model-sourced ``status`` field, so
# ``list_recent_analyses`` passes it through unchanged.
EXTRACT_STATUS_FAILED = "failed"
EXTRACT_STATUS_COMPLETED = "completed"
EXTRACT_STATUS_RUNNING = "running"
EXTRACT_STATUS_QUEUED = "queued"
