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
