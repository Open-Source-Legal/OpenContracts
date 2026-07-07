"""
Pluggable vector-search backends for OpenContracts.

The default backend is pgvector (Postgres HNSW via
``VectorSearchViaEmbeddingMixin``). This package adds an optional,
turbopuffer-style backend that keeps its index entirely in object storage
(S3 / GCS / local filesystem via django-storages):

- ``object_store``  — minimal blob-store adapter over a Django Storage
- ``engine``        — WAL + segment + centroid-ANN search engine
- ``router``        — backend selection + queryset integration
- ``hooks``         — write-path fan-out from ``Embedding.objects.store_embedding``

Enable with ``VECTOR_SEARCH_BACKEND=object_storage``. See
``docs/architecture/object_storage_vector_search.md`` for the design.
"""
