- **Separate "bulk" embeddings microservice pool for ingest.** Added the
  `EMBEDDINGS_MICROSERVICE_URL_BULK` setting (`config/settings/base.py`, next to
  `EMBEDDINGS_MICROSERVICE_URL`), defaulting to `EMBEDDINGS_MICROSERVICE_URL` so
  single-pool deployments are unaffected. The Celery ingest tasks in
  `opencontractserver/tasks/embeddings_task.py` now thread this bulk URL into
  the embedder's existing call-time `embeddings_microservice_url` override kwarg
  via a new optional `service_url_override` parameter on `_create_text_embedding`,
  `_create_embedding_for_annotation`, `_batch_embed_text_annotations`, and
  `_apply_dual_embedding_strategy` (plus `_embed_relationship`). Query/search
  call sites are unchanged — they keep reading `EMBEDDINGS_MICROSERVICE_URL` (the
  always-warm pod), so search latency is fully isolated from batch ingest load.
  No change to the embedder client, base class, or any search resolver.
