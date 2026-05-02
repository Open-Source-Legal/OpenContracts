"""
Constants for the extraction grounding pipeline.

Used by ``opencontractserver.utils.extraction_grounding`` and
``opencontractserver.utils.text_alignment``.
"""

# Minimum length for a string to be worth grounding.
# Very short strings (e.g. "Yes", "42") produce noisy/ambiguous matches.
MIN_GROUNDABLE_LENGTH = 5

# Maximum number of strings to attempt grounding for per datacell.
# Prevents runaway cost on cells that extract hundreds of items.
MAX_GROUNDABLE_STRINGS = 50

# Maximum document length (in characters) for which fuzzy matching is
# attempted. Fuzzy matching is O(n * m) where n = doc length and m = query
# length, so it becomes prohibitively expensive on very large documents.
# Documents exceeding this threshold fall back to exact + normalized only.
# 200 KB comfortably covers most production legal documents (MSAs, ISDA
# schedules, EPC agreements routinely run 100-200 KB). Worst-case fuzzy
# cost is already bounded by FUZZY_PER_QUERY_TIMEOUT_SECONDS and the
# n-gram anchor pre-filter (FUZZY_ANCHOR_MIN_NGRAM_WORDS) — those are
# the real safety valves; this cap is the outer guard.
MAX_DOC_LENGTH_FOR_FUZZY = 200_000

# Maximum query length (in characters) accepted by the fuzzy fallback.
# Some models occasionally return entire paragraphs as a single extracted
# string; running a sliding-window fuzzy match against a multi-paragraph
# query is quadratic in query length and almost never produces useful
# alignments. Skip and log instead of grinding through it.
MAX_QUERY_LENGTH_FOR_FUZZY = 2_000

# Wallclock budget per fuzzy query, in seconds. The fuzzy matcher is
# bounded already (window count is fixed by query/doc length) but worst-
# case ratios with autojunk=False on highly repetitive legal boilerplate
# can blow up. A hard timeout makes per-cell grounding latency
# predictable: at most MAX_GROUNDABLE_STRINGS * FUZZY_PER_QUERY_TIMEOUT_SECONDS
# wallclock per cell, even on pathological inputs.
FUZZY_PER_QUERY_TIMEOUT_SECONDS = 2.0

# Minimum number of words the query must share with the document (as exact
# n-gram substring hits) before we even attempt fuzzy alignment. Most
# queries that ultimately fail fuzzy also fail this anchor test, so we
# skip the expensive sliding window. Set to 0 to disable.
FUZZY_ANCHOR_MIN_NGRAM_WORDS = 4

# Top-level key in datacell.data that holds the extraction result payload.
# This is the standard output format used by data_extract_tasks.py:
# datacell.data = {"data": <extraction_result>}
DATACELL_DATA_KEY = "data"

# Default LLM identifier used by doc_extract_query_task when no explicit
# model_override is supplied.  Any string pydantic-ai accepts is valid.
DEFAULT_EXTRACT_MODEL = "openai:gpt-4o-mini"
