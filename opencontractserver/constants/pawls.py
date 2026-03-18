"""
Constants for PAWLs (Page-Aware Word-Level Segmentation) operations.
"""

# ── Compact PAWLs v2 format ──

# Version marker for the compact format.
COMPACT_PAWLS_VERSION = 2

# Number of decimal places to round coordinate floats to.
# Sub-pixel precision is meaningless for PDF rendering; 1 decimal place
# (0.1 PDF points ≈ 0.0014 inches) is more than sufficient.
COMPACT_PAWLS_COORDINATE_PRECISION = 1

# Maximum number of tokens per page before refusing to compact.
# Safety guard to prevent pathological inputs from producing huge arrays.
COMPACT_PAWLS_MAX_TOKENS_PER_PAGE = 100_000
