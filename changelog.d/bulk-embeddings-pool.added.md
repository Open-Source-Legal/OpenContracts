- **Optional bulk embeddings pool for ingest** (supersedes #2282). `MicroserviceEmbedder`
  gains `embeddings_microservice_url_bulk` (env `EMBEDDINGS_MICROSERVICE_URL_BULK`, seeded
  via `migrate_pipeline_settings`). Ingest calls in `opencontractserver/tasks/embeddings_task.py`
  pass `use_bulk_pool=True`, and `_get_service_config` sends them to the bulk URL when it is
  set. Search queries stay on `embeddings_microservice_url`, so they are isolated from
  ingest load. The URL is left out of `utils/embedding_identity.py::embedding_configuration`.
  Adding the field would otherwise have re-fingerprinted every existing microservice vector
  and made the vectors invisible to `valid_embeddings`. Budgeted runs (`embed_text_accounted`)
  keep the policy-validated query endpoint. See `docs/deployment/performance_tuning.md`.
