"""LLM / agent integration constants (issue #1381)."""

# pydantic-ai default is 1; Anthropic models often need retries to commit
# to ``final_result``. Bumping this requires re-checking ``TOOL_LOOP_THRESHOLD``
# below — a legitimate retried tool call could be mis-classified as a loop
# if the threshold is lower than the retry budget.
STRUCTURED_OUTPUT_RETRIES = 3

# Same-call repetition count that ``_classify_none_result`` treats as a
# pipeline bug (post-mortem heuristic, not a pydantic-ai input). Kept
# strictly greater than ``STRUCTURED_OUTPUT_RETRIES`` so a worst-case
# legitimate ``final_result`` retry budget can never trip the loop
# detector even though pydantic-ai's ``output_retries`` only governs
# ``final_result`` retries today (regular tool calls are not retried by
# the same budget). The margin is defensive: if pydantic-ai ever extends
# retry coverage to other tools, the threshold still has headroom.
TOOL_LOOP_THRESHOLD = 4

# Vocabulary written to ``Datacell.stacktrace`` as ``failure_mode=...``.
# Operators grep these; changing the strings breaks downstream dashboards.
NONE_RESULT_AGENT_COMMITTED = "agent_committed_none"
NONE_RESULT_NO_FINAL = "no_final_response"
NONE_RESULT_TOOL_LOOP = "tool_loop_no_output"
# The structured run hit ``EXTRACT_AGENT_REQUEST_LIMIT`` and pydantic-ai raised
# ``UsageLimitExceeded`` before the agent committed a ``final_result``. Distinct
# from ``tool_loop_no_output`` (same-call repetition) so an operator can tell a
# genuine runaway loop from a request budget set too tight for the model/doc.
NONE_RESULT_USAGE_LIMIT = "usage_limit_exceeded"
NONE_RESULT_UNKNOWN = "unknown"

# Default ceiling on model requests for a single structured-response run
# (applied via ``setdefault``, so any caller may override it per-call). Without
# a budget a weak model (e.g. gpt-4o-mini) can run away making dozens-to-
# hundreds of identical ``similarity_search`` calls on a hard or absent value
# before pydantic-ai's loop gives up — observed at 100 calls / 770KB message
# logs / ~100s per cell in the diligence eval, surfacing as
# ``failure_mode=tool_loop_no_output``. A capable model commits within a handful
# of requests; this tightens pydantic-ai's own default of 50 to bound
# cost/latency for the pathological case while leaving generous headroom for
# legitimate multi-search + ``STRUCTURED_OUTPUT_RETRIES`` final_result retries.
# A caller that legitimately needs more (e.g. a future corpus-wide structured
# analytic) can pass its own ``usage_limits``.
EXTRACT_AGENT_REQUEST_LIMIT = 20

EXTRACT_DEFAULT_TEMPERATURE = 0.3

# Low temperature for conversation-title generation: a title is a short,
# deterministic summary, so consistency matters more than creativity.
TITLE_GENERATION_TEMPERATURE = 0.3

# General-purpose default sampling temperature for the one-shot completion
# helper (``llms.completions.agenerate_text``) when a caller does not pass an
# explicit temperature. Mirrors the bare ``0.7`` default used across the agent
# API; named here so the helper signature carries no magic number.
DEFAULT_COMPLETION_TEMPERATURE = 0.7

# Default bare Anthropic model for the Claude-specific analyzer tasks
# (``doc_analysis_tasks.agentic_highlighter_claude`` / ``pii_highlighter_claude``).
# These tasks are deliberately provider-pinned — the highlighter depends on
# Claude's citations API, which no other provider (or pydantic-ai) exposes —
# so they do NOT walk the ``resolve_model_spec`` chain. The *model within the
# family* is retargetable at runtime instead: both tasks read
# ``ANTHROPIC_MODEL`` from their per-task ``settings.ANALYZER_KWARGS`` entry
# and fall back to this constant (issue #2078).
CLAUDE_ANALYZER_DEFAULT_MODEL = "claude-3-5-sonnet-latest"
