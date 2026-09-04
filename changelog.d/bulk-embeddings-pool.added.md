- **Separate "bulk" embeddings microservice pool for ingest.** `MicroserviceEmbedder`
  gained an optional `embeddings_microservice_url_bulk` setting (on its `Settings`
  dataclass in `opencontractserver/pipeline/embedders/sent_transformer_microservice.py`,
  seeded from the `EMBEDDINGS_MICROSERVICE_URL_BULK` env var via
  `migrate_pipeline_settings`). The ingest Celery tasks in
  `opencontractserver/tasks/embeddings_task.py` tag their embed calls with
  `use_bulk_pool=True`; `_get_service_config` routes those to the bulk URL when one is
  configured, while search queries (untagged) stay on `embeddings_microservice_url`.
  This isolates search-query latency from batch-ingest load with no change to the
  embedder client, base class, or any query call site. Opt-in: when the bulk URL is
  unset the flag is a no-op and ingest stays on the query pool, so single-pool
  deployments are unaffected. The bulk URL is configured through the same
  `PipelineSettings` singleton as the query URL — no separate configuration pathway.
