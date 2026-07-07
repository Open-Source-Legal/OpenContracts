- **Optional object-storage vector search backend (turbopuffer-style), disabled by default.**
  New `VECTOR_SEARCH_BACKEND` setting (`pgvector` default | `object_storage`) routes the
  single similarity call site (`opencontractserver/shared/mixins.py::VectorSearchViaEmbeddingMixin.search_by_embedding`)
  through a WAL + centroid-ANN index kept in the default file storage (local disk, S3/MinIO, or GCS
  under `VECTOR_INDEX_STORAGE_PREFIX`), with Postgres `Embedding` rows remaining the source of truth.
  Engine (`opencontractserver/vector_search/engine.py`) provides strongly consistent reads
  (WAL-tail overlay), deterministic k-means compaction (Celery, cache-lock serialised,
  auto-triggered at `OBJECT_INDEX_COMPACT_MIN_WAL_FILES`), tombstones, and a per-process LRU for
  warm queries. Write path fans out from `Embedding.objects.store_embedding`
  (`opencontractserver/shared/Managers.py`) via `opencontractserver/tasks/vector_index_tasks.py`;
  candidate ids are re-filtered through the caller's queryset so all permission/visibility scoping
  is preserved; unindexed namespaces and engine errors fall back to pgvector automatically.
  Includes `manage.py rebuild_object_vector_index`, system check `opencontracts.E002` for invalid
  backend values, constants in `opencontractserver/constants/search.py`, design doc
  `docs/architecture/object_storage_vector_search.md`, MinIO manual test script
  `docs/test_scripts/object_storage_vector_backend_minio.md`, and 18 tests in
  `opencontractserver/tests/test_object_storage_vector_backend.py`.
