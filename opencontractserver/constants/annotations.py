"""
Constants for annotation-related operations.
"""

# Sentinel value used in GraphQL filters to indicate "include annotations
# that were created manually (not by an analysis/analyzer)".
MANUAL_ANNOTATION_SENTINEL = "~~MANUAL~~"

# --------------------------------------------------------------------------- #
# Built-in annotation label names (OC_ namespace)                             #
# --------------------------------------------------------------------------- #
# Labels prefixed with OC_ are reserved for platform-generated annotations.
# They drive built-in features such as the document index.
OC_SECTION_LABEL = "OC_SECTION"
OC_EXTRACT_SOURCE_LABEL = "OC_EXTRACT_SOURCE"

# Maximum number of entries allowed in a single create_document_index call.
DOCUMENT_ANNOTATION_INDEX_LIMIT = 500

# Maximum nesting depth for document annotation index hierarchy.
# Frontend stops rendering beyond this depth; backend does not enforce it
# (deeper nesting is valid data but won't be visible in the UI).
DOCUMENT_ANNOTATION_INDEX_MAX_DEPTH = 6

# Maximum number of document relationships returned in a single query.
# Set high to accommodate Table of Contents hierarchies.
DOCUMENT_RELATIONSHIP_QUERY_MAX_LIMIT = 500

# Maximum number of results returned by semantic search queries.
SEMANTIC_SEARCH_MAX_RESULTS = 200

# ── Compact annotation JSON v2 safety limits ──
# Maximum span for a single range segment (safety guard).
COMPACT_JSON_MAX_RANGE_SPAN = 10_000
# Maximum total tokens across all pages (safety guard).
COMPACT_JSON_MAX_TOTAL_TOKENS = 50_000
