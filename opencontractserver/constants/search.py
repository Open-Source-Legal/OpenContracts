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
# Full-Text Search Configuration
# =============================================================================
# PostgreSQL text search configuration name for tsvector generation.
# "english" provides stemming and stop-word removal for English text.
# NOTE(deferred): This hardcodes English for full-text search. Multilingual corpora
# will need per-corpus or per-document FTS config.
FTS_CONFIG = "english"
