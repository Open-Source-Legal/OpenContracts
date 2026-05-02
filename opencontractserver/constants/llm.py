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
NONE_RESULT_UNKNOWN = "unknown"

EXTRACT_DEFAULT_TEMPERATURE = 0.3
