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
# OC_URL annotations carry a target URL in ``Annotation.link_url`` that the
# frontend opens when the annotation is clicked, turning highlighted text into
# a navigable hyperlink.
OC_URL_LABEL = "OC_URL"
# Default presentation for the auto-created OC_URL label. Keeping these as
# constants (rather than inline magic values in the mutation) means a future
# theme change updates both backend-seeded labels and frontend renderers
# from the same source of truth.
OC_URL_LABEL_COLOR = "#2563EB"
OC_URL_LABEL_ICON = "link"
OC_URL_LABEL_DESCRIPTION = "Click-through hyperlink annotation"

# Built-in relationship label name for subtree group rows materialized
# during structural-annotation ingestion. One row per non-leaf node:
# source_annotations = [ancestor], target_annotations = [transitive descendants].
OC_SUBTREE_GROUP_LABEL_NAME = "OC_SUBTREE_GROUP"

# Conventional label name for parent-child Relationship edges that future
# parsers/analyzers may emit. The subtree-group walker treats rows with this
# label as additional adjacency edges alongside the Annotation.parent FK.
OC_PARENT_CHILD_LABEL_NAME = "OC_PARENT_CHILD"

# Hard cap on descendants per subtree group. Defends against malformed
# parsers emitting a single ancestor with thousands of descendants.
SUBTREE_GROUP_MAX_DESCENDANTS = 500

# Defensive depth limit for the subtree walker; protects against pathological
# or cyclic input. Branches deeper than this are pruned with a warning.
# Legal documents routinely nest 6–8 levels (Part → Chapter → Section →
# Subsection → Article → Clause → Sub-clause) with tables and lists adding
# further depth, so the cap is set well above realistic structures.
SUBTREE_GROUP_MAX_DEPTH = 32

# Bounded sample of pruned descendant IDs included in the max_depth summary
# warning so production debugging can locate the offending branch without
# log spam on a pathological tree.
SUBTREE_GROUP_PRUNED_SAMPLE_CAP = 5

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
