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
MAX_DOC_LENGTH_FOR_FUZZY = 500_000

# Top-level key in datacell.data that holds the extraction result payload.
# This is the standard output format used by data_extract_tasks.py:
# datacell.data = {"data": <extraction_result>}
DATACELL_DATA_KEY = "data"
