## Overview of Creating and Searching Embeddings

### Dual Embedding Strategy

OpenContracts uses a **dual embedding strategy** to enable both global cross-corpus search and corpus-optimized search:

1. **Default Embedder Embedding (Always Created)**
   - Every annotation, document, and note ALWAYS gets an embedding using the platform's default embedder (configured via `PipelineSettings.default_embedder` in the database)
   - This creates a common vector space for global search across all corpuses
   - Enables users to search all their documents regardless of which corpus they belong to

2. **Corpus-Specific Embedding (Created When Different)**
   - If a corpus has a `preferred_embedder` that differs from the default embedder, annotations also get an embedding using the corpus embedder
   - Enables optimized search within a corpus using domain-specific models (e.g., legal-bert for legal documents)

**Example Scenarios:**

| Corpus Embedder | Embeddings Created |
|-----------------|-------------------|
| None (default) | 1x default embedder |
| Same as default embedder | 1x default embedder |
| Different embedder | 2x (default embedder + corpus embedder) |

This strategy is implemented in the embedding tasks (`opencontractserver/tasks/embeddings_task.py`) which automatically handle the dual embedding creation.

### Creating Embeddings

1. **Generate the Embeddings (Text → Vector)**
   - Use the unified utility function **`generate_embeddings_from_text(text, embedder_path=None)`** or **`agenerate_embeddings_from_text(text, embedder_path=None)`** from [`opencontractserver/utils/embeddings.py`](../../opencontractserver/utils/embeddings.py).
   - These functions:
     - *Retrieve* any configured Python embedder class for the specified corpus (if `corpus_id` is provided to `get_embedder()`).
     - If no embedder is found or it fails, *fall back* to the configured default embedder (typically our built-in microservice).
     - Return a tuple `(embedder_path, vector)`, allowing you to know *which embedder* was used and the numeric embedding vector.

2. **Store the Embeddings**
   - Suppose you have a model instance (e.g., `Annotation`, `Document`, `Note`) that uses the `HasEmbeddingMixin`.
   - Once you have `(embedder_path, vector)` from the generation step, you call:
     ```python
     instance.add_embedding(embedder_path="my-embedder", vector=[...])
     ```
   - Internally, this uses:
     - The `HasEmbeddingMixin.add_embedding(...)` method, which contacts the `Embedding` manager to create or update an embedding record associated with this instance.
     - For multiple vectors (e.g., one instance with many embeddings), use:
       ```python
       instance.add_embeddings("my-embedder", [...multiple_vectors...])
       ```
   - This is the "write" step—saving the vectors to your database.

3. **Retrieve Stored Embeddings**
   - To retrieve a stored embedding vector:
     ```python
     # Synchronous retrieval
     vector = instance.get_embedding(
         embedder_path="openai/text-embedding-ada-002",
         dimension=384
     )

     # Asynchronous retrieval (uses database_sync_to_async)
     vector = await instance.aget_embedding(
         embedder_path="openai/text-embedding-ada-002",
         dimension=384
     )
     ```
   - Returns `List[float] | None` - the embedding vector or None if not found.

### Embedding Storage Architecture

The embedding system uses a dedicated `Embedding` model that supports multiple vector dimensions:

- **Supported Dimensions**: 384, 768, 1024, 1536, 2048, 3072, 4096
- **Vector Fields**: `vector_384`, `vector_768`, `vector_1024`, `vector_1536`, `vector_2048`, `vector_3072`, `vector_4096`
- **Reference Fields**: `document_id`, `annotation_id`, `note_id` (depending on the model type)
- **Embedder Tracking**: `embedder_path` field stores the identifier of the embedding model used

### Embedder Configuration

Embedder settings are managed via the **`PipelineSettings`** database singleton (see [`opencontractserver/documents/models.py`](../../opencontractserver/documents/models.py)):

- **`PipelineSettings.preferred_embedders`**: Map of MIME types to preferred embedder class paths
- **`PipelineSettings.default_embedder`**: Fallback embedder when no preferred embedder is found
- **`DEFAULT_EMBEDDING_DIMENSION`**: Default dimension (768, in `config/settings/base.py`)

These values are seeded from Django settings on first creation but are managed at runtime via the admin UI or GraphQL mutations. Changes take effect immediately across all processes (cached via Django's cache framework with a 5-minute TTL).

Available embedder implementations in [`opencontractserver/pipeline/embedders/`](../../opencontractserver/pipeline/embedders/):

**Text-only:**
- **`MicroserviceEmbedder`**: Calls external sentence-transformer microservice (384-dim, default)

**Multimodal (text + images):**
- **`CLIPMicroserviceEmbedder`**: CLIP-based multimodal embedder via microservice (768-dim)
- **`QwenMicroserviceEmbedder`**: Qwen-based multimodal embedder via microservice (1024-dim)

### Searching Embeddings

Our search architecture is designed with two layers: a **core API** that contains our business logic, and **framework adapters** that provide compatibility with different agent frameworks.

#### Core Search API

1. **`CoreAnnotationVectorStore`** - Framework-Agnostic Business Logic
   - Located in [`opencontractserver/llms/vector_stores/core_vector_stores.py`](../../opencontractserver/llms/vector_stores/core_vector_stores.py)
   - Contains all the business logic for vector search without dependencies on specific agent frameworks
   - Key classes: `CoreAnnotationVectorStore`, `VectorSearchQuery`, `VectorSearchResult`
   - See the source file for initialization and usage examples

2. **Framework-Agnostic Data Structures**
   - `VectorSearchQuery`: Contains query text/embedding, filters, and search parameters
   - `VectorSearchResult`: Contains the annotation and similarity score

3. **Filtering Logic**
   - **Corpus Filtering**: Annotations are filtered by corpus membership. Structural annotations (`structural=True`) are always included regardless of corpus, while non-structural annotations must belong to the specified corpus.
   - **Document Filtering**: When `document_id` is provided, only annotations from that document are included.
   - **Visibility Filtering**: Annotations are visible if they are structural, public, or created by the requesting user.
   - **Metadata Filtering**: Additional filters can be applied on annotation labels and other fields.

#### Global Search

The `CoreAnnotationVectorStore` provides a `global_search` class method for cross-corpus search:

```python
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchResult,
)

# Search across ALL documents the user has access to
results = CoreAnnotationVectorStore.global_search(
    user_id=my_user_id,
    query_text="contract termination clause",
    top_k=100,
    modalities=["TEXT"],  # Optional: filter by content type
)

# Async version
results = await CoreAnnotationVectorStore.async_global_search(
    user_id=my_user_id,
    query_text="contract termination clause",
    top_k=100,
)

# Process results
for result in results:
    annotation = result.annotation
    similarity = result.similarity_score
    document_title = annotation.document.title if annotation.document else "N/A"
    print(f"Found: {annotation.raw_text[:50]}... (score: {similarity:.3f})")
```

**Key Features:**
- Uses default embedder embeddings for consistent cross-corpus search
- Respects user permissions (only searches documents the user can access)
- Supports modality filtering (TEXT, IMAGE, etc.)
- Works with both standalone and corpus-bound documents

#### Vector Search Mixin

Models that store embeddings can use `VectorSearchViaEmbeddingMixin` from [`opencontractserver/shared/mixins.py`](../../opencontractserver/shared/mixins.py) to enable vector similarity searches (the model must also use `HasEmbeddingMixin`). See the source file for usage examples.

#### Framework Adapters

Framework adapters are thin wrappers that translate between the core API and specific agent frameworks:

1. **LlamaIndex Adapter** - *Removed*
   - The LlamaIndex vector store adapter has been removed from the codebase.
   - If you need LlamaIndex integration, implement your own adapter wrapping `CoreAnnotationVectorStore`.

2. **PydanticAI Adapter** - `PydanticAIAnnotationVectorStore`
   - Located in [`opencontractserver/llms/vector_stores/pydantic_ai_vector_stores.py`](../../opencontractserver/llms/vector_stores/pydantic_ai_vector_stores.py)
   - Provides async-first API with Pydantic models for type safety
   - Converts between PydanticAI types and our core types (see source file for usage examples)

3. **PydanticAI Tool Creation**
   - Use `create_vector_search_tool()` from [`pydantic_ai_vector_stores.py`](../../opencontractserver/llms/vector_stores/pydantic_ai_vector_stores.py) to create vector search tools for PydanticAI agents.

4. **PydanticAI Response Format**
   - Returns structured `PydanticAIVectorSearchResponse` with validated data containing annotation details, similarity scores, and location information.
   - See [`pydantic_ai_vector_stores.py`](../../opencontractserver/llms/vector_stores/pydantic_ai_vector_stores.py) for the complete response structure.

### Async/Sync Compatibility

The embedding system supports both synchronous and asynchronous operations:

**Synchronous Methods:**
- `generate_embeddings_from_text()`
- `instance.get_embedding()`
- `instance.add_embedding()`
- `store.search()`

**Asynchronous Methods:**
- `agenerate_embeddings_from_text()`
- `instance.aget_embedding()` (uses `database_sync_to_async`)
- `store.async_search()`

When working in async contexts (such as Django Channels WebSocket consumers), always use the async variants to avoid blocking operations.

### How This Works in Practice

1. **Query Processing**
   - Framework adapter receives a query in framework-specific format
   - Adapter converts to `VectorSearchQuery`
   - Core store processes the query using our business logic

2. **Vector Generation**
   - If `query.query_text` is provided, core store calls `generate_embeddings_from_text(...)` or `agenerate_embeddings_from_text(...)`
   - If `query.query_embedding` is provided, uses it directly

3. **Database Search**
   - Core store builds Django queryset with filters (corpus, document, user, metadata)
   - Applies structural annotation logic (structural annotations bypass corpus filtering)
   - Uses `.search_by_embedding(...)` from `VectorSearchViaEmbeddingMixin` for similarity search
     (backend-pluggable: pgvector HNSW by default, or the object-storage index
     when `VECTOR_SEARCH_BACKEND=object_storage` — see
     `docs/architecture/object_storage_vector_search.md`)
   - Returns `VectorSearchResult` objects with annotations and similarity scores

4. **Result Conversion**
   - Framework adapter converts `VectorSearchResult` objects to framework-specific format
   - Embedding vectors are retrieved using `aget_embedding()` for async contexts

### Performance Considerations

1. **Database Indexes**: The `Annotation` model includes composite indexes for optimal query performance. See [`opencontractserver/annotations/models.py`](../../opencontractserver/annotations/models.py) for index definitions.

2. **Embedding Retrieval**: Use `prefetch_related("embeddings")` when fetching multiple annotations to avoid N+1 queries.

3. **Vector Dimensions**: Choose appropriate embedding dimensions based on your use case:
   - 384: Fast, good for general similarity
   - 768: Balanced performance and accuracy
   - 1536: High accuracy, more computational cost
   - 3072: Highest accuracy, highest computational cost

### Architecture Benefits

This architecture provides:
- **Reusability**: Core logic works with any framework
- **Maintainability**: Business logic changes in one place
- **Extensibility**: Easy to add new framework adapters
- **Type Safety**: Clear interfaces between layers
- **Testing**: Core functionality can be tested independently
- **Async Support**: Full compatibility with async Django applications
- **Performance**: Optimized database queries and indexing strategies

By following this pattern, you can use the same underlying search capabilities across different agent frameworks while maintaining consistency and avoiding code duplication.
