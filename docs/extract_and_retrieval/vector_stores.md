# Vector Store Architecture

## Introduction

OpenContracts uses a flexible vector store architecture that provides compatibility with multiple agent frameworks (PydanticAI, etc.) while maintaining a clean separation between business logic and framework-specific adapters.

Our approach uses a **two-layer architecture**:
1. **Core Layer**: Framework-agnostic business logic (`CoreAnnotationVectorStore`)
2. **Adapter Layer**: Thin wrappers for specific frameworks

This design enables efficient vector search across granular, visually-locatable annotations from PDF pages while supporting multiple agent frameworks through a single, well-tested codebase.

> **Storage backend note:** the similarity ranking underneath all of this
> (`VectorSearchViaEmbeddingMixin.search_by_embedding`) is itself pluggable via
> `VECTOR_SEARCH_BACKEND` — `pgvector` (default, Postgres HNSW) or
> `object_storage` (turbopuffer-style WAL + centroid index in S3/GCS/local
> storage). See `docs/architecture/object_storage_vector_search.md`. All
> permission filtering described below applies identically to both backends.

## Architecture Overview

### Core Layer: `CoreAnnotationVectorStore`

The core layer contains all business logic for vector search operations, independent of any specific agent framework:

```python
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
    VectorSearchResult,
)

# Initialize core store with filtering parameters
core_store = CoreAnnotationVectorStore(
    corpus_id=123,
    user_id=456,
    embedder_path="sentence-transformers/all-MiniLM-L6-v2",
    embed_dim=384,
)

# Create framework-agnostic query
query = VectorSearchQuery(
    query_text="What are the key findings?",
    similarity_top_k=10,
    filters={"label": "conclusion"}
)

# Execute search
results = core_store.search(query)

# Access results
for result in results:
    annotation = result.annotation  # Django Annotation model
    score = result.similarity_score  # Similarity score (0.0-1.0)
```

**Key features:**
- **Framework Independence**: No dependencies on specific AI frameworks
- **Django Integration**: Direct use of Django ORM and `VectorSearchViaEmbeddingMixin`
- **Flexible Filtering**: Support for corpus, document, user, and metadata filters
- **Embedding Generation**: Automatic text-to-vector conversion using `generate_embeddings_from_text`
- **pgvector Integration**: Efficient vector similarity search using PostgreSQL's pgvector extension

### Adapter Layer: Framework-Specific Wrappers

Framework adapters are lightweight classes that translate between the core API and specific framework interfaces.

#### PydanticAI Adapter

```python
class PydanticAIVectorStore:
    """PydanticAI adapter for Django Annotation Vector Store."""

    def __init__(self, corpus_id=None, user_id=None, **kwargs):
        self._core_store = CoreAnnotationVectorStore(
            corpus_id=corpus_id,
            user_id=user_id,
            **kwargs
        )

    async def search(self, query: str, top_k: int = 10) -> list[Document]:
        """Execute search using PydanticAI interface."""
        search_query = VectorSearchQuery(
            query_text=query,
            similarity_top_k=top_k
        )
        results = await self._core_store.search_async(search_query)
        return self._convert_to_documents(results)
```

### Unified Factory Pattern

The `UnifiedVectorStoreFactory` automatically creates the appropriate vector store based on configuration:

```python
from opencontractserver.llms.vector_stores import UnifiedVectorStoreFactory

# Automatically creates the right adapter based on settings
vector_store = UnifiedVectorStoreFactory.create(
    framework=settings.LLMS_DEFAULT_AGENT_FRAMEWORK,  # "pydantic_ai"
    corpus_id=corpus_id,
    user_id=user_id
)
```

## Technical Deep Dive

### Vector Search Pipeline

The search process follows this pipeline:

1. **Query Reception**: Framework adapter receives query in framework-specific format
2. **Query Translation**: Adapter converts to `VectorSearchQuery`
3. **Core Processing**:
   - Build base Django queryset with instance filters (corpus, document, user)
   - Apply metadata filters (labels, etc.)
   - Generate embeddings from text if needed
   - Execute vector similarity search via `search_by_embedding` mixin
4. **Result Translation**: Adapter converts `VectorSearchResult` back to framework format

### Integration with Django ORM and pgvector

The core store leverages Django's powerful ORM features combined with pgvector:

```python
def search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
    """Execute vector search using Django ORM and pgvector."""
    # Build filtered queryset
    queryset = self._build_base_queryset()
    queryset = self._apply_metadata_filters(queryset, query.filters)

    # Perform vector search using mixin
    if query.query_embedding is not None:
        queryset = queryset.search_by_embedding(
            query_vector=query.query_embedding,
            embedder_path=self.embedder_path,
            top_k=query.similarity_top_k
        )

    # Convert to results
    return [
        VectorSearchResult(
            annotation=ann,
            similarity_score=getattr(ann, 'similarity_score', 1.0)
        )
        for ann in queryset
    ]
```

Under the hood, this uses pgvector's `CosineDistance` for efficient similarity computation:

```sql
-- Generated SQL uses pgvector's <=> operator
SELECT *, (embedding <=> %s) AS similarity_score
FROM annotations
WHERE corpus_id = %s
ORDER BY similarity_score
LIMIT %s
```

### Embedding Management

The system automatically handles embedding generation and retrieval:

- **Text Queries**: Automatically converted to embeddings using corpus-configured embedders
- **Embedding Queries**: Used directly for similarity search
- **Multi-dimensional Support**: Supports 384, 768, 1536, and 3072 dimensional embeddings
- **Embedder Detection**: Automatic detection of corpus-specific embedder configurations

### Multimodal Embedding Support

When a multimodal embedder (e.g., CLIP ViT-L-14) is configured, the vector store supports cross-modal similarity search across both text and image content.

**Unified Vector Space**

CLIP produces 768-dimensional vectors in a shared embedding space for both text and images. This enables:
- Text queries finding visually similar images
- Image annotations found alongside relevant text
- Combined text+image annotations with weighted embeddings

**Content Modalities Filter**

Use the `modalities` parameter to filter search results by content type:

```python
# Search only text annotations
results = await vector_store.similarity_search(
    query="contract terms",
    modalities=["TEXT"]
)

# Search only image annotations
results = await vector_store.similarity_search(
    query="bar chart",
    modalities=["IMAGE"]
)

# Search both (default behavior)
results = await vector_store.similarity_search(
    query="revenue figures",
    modalities=["TEXT", "IMAGE"]
)
```

**Configuration**

Configure multimodal embedder at corpus level:

```python
corpus.preferred_embedder = (
    "opencontractserver.pipeline.embedders."
    "multimodal_microservice.CLIPMicroserviceEmbedder"
)
corpus.save()
```

Configure text/image weighting for mixed-modality annotations:

```python
# settings.py or environment variables
MULTIMODAL_EMBEDDING_WEIGHTS = {
    "text_weight": 0.3,   # Weight for text embedding
    "image_weight": 0.7,  # Weight for image embedding (higher by default)
}
```

**How Mixed-Modality Embeddings Work**

For annotations containing both text and images:
1. Text content is embedded via CLIP's text encoder
2. Each image is embedded via CLIP's image encoder
3. Image embeddings are averaged if multiple images
4. Text and image embeddings are combined via weighted average
5. Final embedding is stored in the same vector space as text-only and image-only annotations

## Benefits of the Layered Architecture

### 1. Framework Flexibility
- Support multiple agent frameworks through simple adapters
- Business logic remains consistent across frameworks
- Easy switching between frameworks via configuration

### 2. Maintainability
- Single source of truth for search logic
- Framework-specific code is minimal and focused
- Bug fixes and improvements benefit all frameworks

### 3. Performance
- Direct Django ORM integration
- Efficient pgvector similarity search
- Optimized queryset construction with proper filtering

### 4. Extensibility
- Easy to add new metadata filters
- Simple to support additional frameworks
- Flexible configuration options

### 5. Testing
- Core logic can be tested independently
- Framework adapters have minimal, focused tests
- Clear separation of concerns

## Adding Support for New Frameworks

To add support for a new framework:

### 1. Create the Adapter Class

```python
class MyFrameworkVectorStore:
    def __init__(self, **kwargs):
        self._core_store = CoreAnnotationVectorStore(**kwargs)

    def search(self, framework_query):
        # Convert framework query to VectorSearchQuery
        core_query = self._convert_query(framework_query)

        # Use core store
        results = self._core_store.search(core_query)

        # Convert results back to framework format
        return self._convert_results(results)
```

### 2. Register with Factory

```python
# In vector_store_factory.py
class UnifiedVectorStoreFactory:
    @classmethod
    def create(cls, framework: str, **kwargs):
        if framework == "my_framework":
            return MyFrameworkVectorStore(**kwargs)
        # ... other frameworks
```

### 3. Test the Adapter

```python
def test_my_framework_adapter():
    store = MyFrameworkVectorStore(corpus_id=1)
    results = store.search("test query")
    assert len(results) > 0
```

## Configuration

### Framework Selection

Set the default framework in settings:

```python
# settings.py
LLMS_DEFAULT_AGENT_FRAMEWORK = "pydantic_ai"
```

### Embedder Configuration

Configure embedders per corpus:

```python
# Corpus model
corpus.preferred_embedder = "sentence-transformers/all-MiniLM-L6-v2"
corpus.embed_dim = 384
```

### Search Parameters

Customize search behavior:

```python
# In your code
vector_store = CoreAnnotationVectorStore(
    similarity_threshold=0.7,  # Minimum similarity score
    max_results=100,           # Maximum results to return
    include_metadata=True      # Include annotation metadata
)
```

## Performance Considerations

### Indexing

Ensure proper PostgreSQL indexes:

```sql
-- pgvector index for similarity search
CREATE INDEX ON annotations USING ivfflat (embedding vector_cosine_ops);

-- B-tree indexes for filtering
CREATE INDEX ON annotations (corpus_id, document_id);
CREATE INDEX ON annotations (annotation_label_id);
```

### Batch Operations

For bulk searches, use batch processing:

```python
# Process multiple queries efficiently
queries = [VectorSearchQuery(text) for text in texts]
results = await asyncio.gather(*[
    core_store.search_async(q) for q in queries
])
```

### Caching

Embeddings are cached automatically:
- Document embeddings stored in database
- Query embeddings cached in memory (15-minute TTL)
- Corpus-level embedding configuration cached

## Conclusion

This layered architecture provides a robust foundation for vector search capabilities while maintaining compatibility with multiple agent frameworks. By separating core business logic from framework-specific adapters, we achieve:

- **Consistency**: Same search behavior across all frameworks
- **Maintainability**: Single codebase for core functionality
- **Flexibility**: Easy addition of new framework support
- **Performance**: Direct integration with Django ORM and pgvector

This design pattern is applied throughout OpenContracts to create a comprehensive, framework-agnostic foundation for AI-powered document analysis.
