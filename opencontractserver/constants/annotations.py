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

# Geographic annotation conventions — issue #1819.
# Spans that have been geocoded by ``opencontractserver/utils/geocoding`` carry
# one of these labels and write ``{canonical_name, lat, lng, admin_codes,
# geocoded}`` into ``Annotation.data`` so the map UI (#1820, #1821) can
# aggregate pins without re-running the geocoder. The three labels share a
# blue→teal hue family so country / state / city pins read at a glance when
# rendered together: country is the deepest shade, city the lightest.
OC_COUNTRY_LABEL = "OC_COUNTRY"
OC_STATE_LABEL = "OC_STATE"
OC_CITY_LABEL = "OC_CITY"

# Geographic label presentation. The colours form a coherent dark→light ramp
# (country deepest, city lightest) so a map cluster that mixes label types is
# legible at small zoom levels.
OC_COUNTRY_LABEL_COLOR = "#0E3A5F"
OC_STATE_LABEL_COLOR = "#1E6091"
OC_CITY_LABEL_COLOR = "#3E92CC"
OC_COUNTRY_LABEL_ICON = "globe"
OC_STATE_LABEL_ICON = "map"
OC_CITY_LABEL_ICON = "map marker alternate"
OC_COUNTRY_LABEL_DESCRIPTION = "Geocoded country reference"
OC_STATE_LABEL_DESCRIPTION = "Geocoded state / first-level admin division"
OC_CITY_LABEL_DESCRIPTION = "Geocoded city / locality reference"

# Per-pin cap on the bounded ``sample_document_ids`` preview shipped with
# each map aggregation row. The frontend uses this preview to decide
# whether to expand the pin into a side panel — the side panel pulls the
# full document set on demand, so the preview only needs to be enough to
# show "yes, multiple documents here". Five is the size at which the
# preview comfortably fits a hover/popover without overflowing.
GEOGRAPHIC_PIN_SAMPLE_DOC_LIMIT = 5

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

# --------------------------------------------------------------------------- #
# PDF outline enrichment (PdfOutlineEnricher)                                 #
# --------------------------------------------------------------------------- #
# Minimum difflib similarity ratio (0.0-1.0) for fuzzy-matching a PDF bookmark
# title against text on its destination page. A bookmark whose title cannot be
# located on its page at or above this ratio is dropped, and its children are
# re-parented to the nearest matched ancestor.
PDF_OUTLINE_FUZZY_MATCH_THRESHOLD = 0.82

# Hard cap on the number of OC_SECTION entries a single PdfOutlineEnricher run
# emits. Bounded by the document-index limit so the enricher never produces
# more section annotations than the index is allowed to hold.
PDF_OUTLINE_MAX_ENTRIES = DOCUMENT_ANNOTATION_INDEX_LIMIT

# Maximum /Outlines nesting depth walked by the enricher. Matches the document
# annotation index depth cap; deeper bookmark branches are pruned with a
# warning rather than emitted.
PDF_OUTLINE_MAX_DEPTH = DOCUMENT_ANNOTATION_INDEX_MAX_DEPTH

# Minimum difflib ratio between a bookmark title's first word and a candidate
# start token. A cheap pre-filter so the fuzzy match only does real work on
# plausible starting tokens.
PDF_OUTLINE_FIRST_WORD_PREFILTER_RATIO = 0.6

# Multiplier applied to PDF_OUTLINE_MAX_ENTRIES to derive the processed-item
# cap for the /Outlines tree walk. The walk may visit nodes (bare nested
# lists, empty-title or unresolvable-destination entries) that never become
# emitted annotations, so the item cap is set higher than the entry cap to
# avoid aborting a legitimate-but-sparse outline while still bounding work on
# malformed/cyclic data.
PDF_OUTLINE_WALK_ITEM_MULTIPLIER = 4

# Maximum number of document relationships returned in a single query.
# Set high to accommodate Table of Contents hierarchies.
DOCUMENT_RELATIONSHIP_QUERY_MAX_LIMIT = 500

# Maximum number of results returned by semantic search queries.
SEMANTIC_SEARCH_MAX_RESULTS = 200

# Character cap for the concatenated block-of-context text that
# ``CoreAnnotationVectorStore`` attaches to a vector hit and that the
# relationship-embedding pipeline feeds to the embedder. Capped well below
# typical embedder token limits (most APIs accept ~8k tokens ≈ ~30k chars at
# ~4 chars/token) so we never need to round-trip to a tokenizer just to
# decide whether to truncate. Matches ``OPENAI_EMBEDDER_MAX_INPUT_CHARS``
# upper bound but is kept independent so a future change to the embedder
# input cap doesn't silently change the size of the block context exposed
# to GraphQL clients.
SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS = 16_000

# ── Compact annotation JSON v2 safety limits ──
# Maximum span for a single range segment (safety guard).
COMPACT_JSON_MAX_RANGE_SPAN = 10_000
# Maximum total tokens across all pages (safety guard).
COMPACT_JSON_MAX_TOTAL_TOKENS = 50_000

# --- Post-ingest annotation remap (dumb-anchor sidecars) ----------------------
# Min fraction of an OC token's area that must intersect a producer bbox for the
# token to be selected when anchoring a PDF annotation.
ANNOTATION_ANCHOR_GEOMETRY_OVERLAP_THRESHOLD = 0.5
# Min difflib ratio between selected tokens' text and rawText to confirm a PDF
# geometric anchor before falling back to text search.
ANNOTATION_ANCHOR_TEXT_CONFIRM_RATIO = 0.82
# Min difflib ratio for the rawText fuzzy-match fallback when a PDF annotation
# could not be confirmed geometrically. Kept separate from
# ``PDF_OUTLINE_FUZZY_MATCH_THRESHOLD`` even though they share a value today:
# the outline threshold is calibrated for short exact headings, whereas an
# annotation's rawText can be a long multi-word span, so the two are tuned
# independently as the feature matures.
ANNOTATION_ANCHOR_TEXT_FUZZY_THRESHOLD = 0.82
# rawText preview kept on a remap ``report`` entry. Head+tail (rather than a
# single head slice) so a long-span annotation that was dropped can be
# reconstructed from both ends of its text — the start AND the end disambiguate
# which span failed when several share a prefix.
ANNOTATION_REPORT_RAWTEXT_HEAD = 60
ANNOTATION_REPORT_RAWTEXT_TAIL = 20

# ── Annotation count caching (issue #1908) ──
# The un-scoped "Browse annotations" view shows an exact "Total Annotations"
# tile backed by ``COUNT(*)`` over the full permission-filtered annotation set
# (a ``DISTINCT`` across several visibility joins). graphene-django 3.2.3 runs
# that COUNT eagerly on every page — including each infinite-scroll page — so
# at hundreds of thousands of rows it dominates latency. ``CachedCountQuerySet``
# caches the exact value, keyed by the compiled SQL (which inlines the
# per-user visibility predicate and every active filter), for this long. The
# tile stays exact; it is stale by at most this window after a create/delete.
ANNOTATION_COUNT_CACHE_TTL_SECONDS = 60 * 60  # 60 minutes

# Cache-key namespace for the cached annotation count. Bump the trailing
# version when the visibility predicate or count semantics change so stale
# entries from the old shape are never served.
ANNOTATION_COUNT_CACHE_PREFIX = "oc:annotation_count:v1"
