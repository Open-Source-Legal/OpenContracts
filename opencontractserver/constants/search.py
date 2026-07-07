"""
Constants for vector search, full-text search, and hybrid search operations.
"""

# =============================================================================
# HNSW Index Parameters
# =============================================================================
# These control the quality vs. speed tradeoff for approximate nearest neighbor
# search. See: https://github.com/pgvector/pgvector#hnsw

# Connections per node in the HNSW graph.
# Higher = better recall but more memory and slower builds.
# 16 is the pgvector default and works well up to ~10M vectors.
HNSW_M = 16

# Build-time quality parameter.
# Higher = better index quality but slower index creation.
# 64 is the pgvector default; 128 is recommended for high-recall production use.
HNSW_EF_CONSTRUCTION = 64

# =============================================================================
# Reciprocal Rank Fusion (RRF) Parameters
# =============================================================================
# Used when combining vector similarity and full-text search results.
# See: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf

# The RRF smoothing constant (k). Standard value is 60.
# Higher k gives more weight to lower-ranked results.
RRF_K = 60

# Default oversampling factor for hybrid search.
# Each sub-search fetches this multiple of the requested top_k, then RRF
# fuses and re-ranks down to top_k.
HYBRID_SEARCH_OVERSAMPLE_FACTOR = 3

# =============================================================================
# Discover Cross-Content Search Parameters
# =============================================================================
# Defaults for the unified Discover search resolvers (config/graphql/
# discover_queries.py), which fuse a text arm and a semantic arm per category.

# Default number of results returned per category when the caller does not
# specify a ``limit``. The frontend caps this per tab (preview vs. entity tab).
#
# Rate-cost note: the Discover "All" tab fires all FIVE category resolvers
# (annotations/documents/notes/collections/discussions) simultaneously, each
# decorated with the ``READ_LIGHT`` tier. So a single "All" search costs
# ``5 × READ_LIGHT`` tokens, not one. Account for that multiplier when tuning
# the READ_LIGHT rate in ``config/graphql/ratelimits.py``.
DISCOVER_DEFAULT_LIMIT = 25

# How many candidates each arm fetches relative to the requested ``limit``
# before fusion — a small oversample so RRF has room to reorder.
DISCOVER_OVERSAMPLE = 4

# Size of the per-process LRU that memoises the embedded query vector across
# the five Discover resolvers. The "All" tab issues one HTTP request per
# category (the frontend uses a non-batching Apollo link), so without a cache a
# single user search would embed the *same* query string up to five times. The
# embedding is deterministic for a given ``(query_text, embedder_path)``, so a
# small module-level cache lets those requests share one embedding call.
DISCOVER_QUERY_VECTOR_CACHE_SIZE = 32

# Maximum accepted Discover text search length. Keep this intentionally small
# because the same user-controlled string is used for database text predicates
# and, when semantic search is enabled, as input to the per-process query-vector
# cache. Longer GraphQL values are ignored before reaching either arm so workers
# never retain attacker-sized strings in cache keys.
DISCOVER_TEXT_SEARCH_MAX_LENGTH = 512

# Extra oversample applied to the corpus "content match" pre-filters
# (documents/annotations whose text matches), on top of ``fetch_k``. A corpus
# is reached transitively through many matching documents/annotations, so this
# arm casts a wider net before collapsing to distinct corpus ids.
DISCOVER_CORPUS_CONTENT_OVERSAMPLE = 4

# =============================================================================
# Reranker Parameters
# =============================================================================
# When a global reranker is configured (PipelineSettings.default_reranker),
# vector / hybrid search fetches ``top_k * RERANK_OVERSAMPLE_FACTOR`` candidates
# from the first-stage retrieval, feeds them through the reranker, and returns
# the top ``top_k`` results. A factor of 3 matches the industry-standard recipe
# (e.g. the bge-reranker paper). Tune higher for better recall, lower for
# cheaper latency.
RERANK_OVERSAMPLE_FACTOR = 3

# Hard cap on candidates sent to the reranker, regardless of oversample. Keeps
# the worst case bounded when callers request very large top_k values.
RERANK_MAX_CANDIDATES = 128

# Default number of candidates the reranker should operate on when no caller
# explicitly specifies ``similarity_top_k``. Matches vector-store defaults.
RERANK_DEFAULT_TOP_K = 10

# =============================================================================
# Embedding Dimensions
# =============================================================================
# All supported vector embedding dimensions across the platform.
# Used for validation in vector stores, mixins, and conversation models.
VALID_EMBEDDING_DIMS = frozenset({384, 768, 1024, 1536, 2048, 3072, 4096})

# Maps embedding dimension to the corresponding field name on the Embedding model.
# Used by VectorSearchViaEmbeddingMixin and conversation QuerySets.
DIM_TO_FIELD_MAP: dict[int, str] = {
    384: "vector_384",
    768: "vector_768",
    1024: "vector_1024",
    1536: "vector_1536",
    2048: "vector_2048",
    3072: "vector_3072",
    4096: "vector_4096",
}

# =============================================================================
# HNSW Index Dimension Coverage
# =============================================================================
# pgvector HNSW indexes have a hard 2000-dimension limit. Only the dimensions
# listed here actually have HNSW indexes created in migration 0063.
# Dimensions above HNSW_MAX_INDEXED_DIM (2048, 3072, 4096) fall back to
# sequential scan. These values are also frozen into migration 0063 (as
# local constants, per Django migration best practice).
HNSW_INDEXED_DIMS = frozenset({384, 768, 1024, 1536})
HNSW_MAX_INDEXED_DIM = max(HNSW_INDEXED_DIMS)

# =============================================================================
# Select-All Document IDs
# =============================================================================
# Hard cap on how many document global-ids the ``corpusDocumentIds`` query
# (document grid "Select All") will return in one response. The resolver returns
# every matching id ignoring pagination, so without a cap a Select-All on a very
# large corpus would serialize a multi-megabyte ``List[ID]`` (~40 chars/id) on
# every call — the READ_LIGHT rate limiter throttles frequency but not payload
# size. When the match count exceeds this, the resolver raises a GraphQLError
# rather than silently truncating (a truncated id set would make a subsequent
# bulk-remove act on only part of the selection — a correctness bug, not just a
# perf one). 25k ids ≈ ~1 MB, comfortably above any realistic interactive
# Select-All while bounding the worst case.
MAX_SELECT_ALL_DOCUMENT_IDS = 25_000

# =============================================================================
# Vector Search Backend Selection
# =============================================================================
# Values accepted by settings.VECTOR_SEARCH_BACKEND. "pgvector" is the default
# Postgres HNSW path; "object_storage" serves similarity ranking from the
# turbopuffer-style WAL + centroid index in object storage (see
# docs/architecture/object_storage_vector_search.md).
VECTOR_SEARCH_BACKEND_PGVECTOR = "pgvector"
VECTOR_SEARCH_BACKEND_OBJECT_STORAGE = "object_storage"
VALID_VECTOR_SEARCH_BACKENDS = frozenset(
    {VECTOR_SEARCH_BACKEND_PGVECTOR, VECTOR_SEARCH_BACKEND_OBJECT_STORAGE}
)

# =============================================================================
# Object-Storage Vector Index Parameters
# =============================================================================
# Tuning knobs for opencontractserver/vector_search/engine.py.

# Below this many vectors a namespace is stored as a single brute-force
# cluster — k-means clustering only pays off once fetching the whole segment
# per query costs more than the extra centroid roundtrip.
OBJECT_INDEX_MIN_VECTORS_FOR_ANN = 256

# Upper bound on k-means centroids per namespace (k = sqrt(n) capped here).
# 1024 clusters keeps the centroid blob < 6 MB for 1536-dim float32 vectors.
OBJECT_INDEX_MAX_CENTROIDS = 1024

# Lloyd iterations during compaction. Compaction is offline/async, but each
# iteration is O(n*k); 8 gets within a few percent of converged assignment.
OBJECT_INDEX_KMEANS_ITERATIONS = 8

# Fixed seed so compaction is deterministic (same data -> same segments),
# which makes rebuilds reproducible and cache keys stable.
OBJECT_INDEX_KMEANS_SEED = 0

# How many nearest clusters a query probes: max(NPROBE_MIN, k * NPROBE_RATIO),
# clamped to k. Higher = better recall, more object-store roundtrips.
OBJECT_INDEX_NPROBE_MIN = 4
OBJECT_INDEX_NPROBE_RATIO = 0.25

# Permission filtering happens AFTER ANN retrieval (post-filtering), so the
# engine is asked for this multiple of top_k so that heavily-filtered
# querysets can still fill top_k results.
OBJECT_INDEX_FILTER_OVERSAMPLE = 4

# WAL tail length that triggers async compaction after a write. Each tail file
# costs one GET per query, so this bounds worst-case query roundtrips.
OBJECT_INDEX_COMPACT_MIN_WAL_FILES = 16

# Cache-lock TTL for the per-namespace compaction mutex (seconds). Must exceed
# the slowest realistic compaction so a crashed worker's lock expires. This
# bound is coupled to the "full recluster per compaction is fine up to ~1M
# vectors per namespace" scaling note in the design doc: if compactions ever
# approach this ceiling, a second compactor can start while the first is
# still running (racing manifest writes, resolved last-writer-wins by
# put_bytes) — raise this together with any namespace-size increase.
OBJECT_INDEX_COMPACT_LOCK_TIMEOUT_SECONDS = 600

# Bounded retries for the delete-then-save overwrite dance in
# DjangoStorageObjectStore.put_bytes (Django's Storage.save never overwrites;
# it uniquifies names on collision). Contention on a mutable key means the
# compaction lock was breached, so after this many attempts we concede
# last-writer-wins to the racing writer instead of looping.
OBJECT_STORE_PUT_OVERWRITE_MAX_ATTEMPTS = 3

# Max entries in the per-process LRU for immutable index artifacts
# (centroids + cluster blobs, keyed by generation).
OBJECT_INDEX_CACHE_MAX_ENTRIES = 64

# Batch size for the rebuild_object_vector_index management command — how many
# vectors are folded into a single WAL file per PUT.
OBJECT_INDEX_REBUILD_BATCH_SIZE = 500

# =============================================================================
# Full-Text Search Configuration
# =============================================================================
# PostgreSQL text search configuration name for tsvector generation.
# "english" provides stemming and stop-word removal for English text.
# NOTE(deferred): This hardcodes English for full-text search. Multilingual corpora
# will need per-corpus or per-document FTS config.
FTS_CONFIG = "english"
