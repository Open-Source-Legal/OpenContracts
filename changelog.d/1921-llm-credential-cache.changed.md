- **Memoized the per-agent-build LLM credential read (#1921).**
  `opencontractserver/llms/model_factory.py::_get_db_credentials` ran on every
  agent build — every chat message, structured-output call, and
  memory-curation task — and resolved the provider's secret through
  `PipelineSettings.get_full_component_settings`, which reads the encrypted
  secret store twice and so derived the Fernet key with the deliberately
  expensive PBKDF2 KDF (480k HMAC iterations) twice per build whenever any
  provider key was configured. The resolved per-provider credentials are now
  cached in-process keyed on `(class_path, PipelineSettings.modified)` — the
  same key the reranker/embedder instance caches use
  (`opencontractserver/pipeline/utils.py`). Repeat builds skip the decryption,
  while live rotation is preserved: a superuser key change calls
  `PipelineSettings.save()`, which bumps `modified` (auto_now) and clears the
  singleton cache, so the next build misses the memo and re-decrypts — no
  redeploy, and no staleness beyond the existing 5-minute `PipelineSettings`
  cache TTL (the live-configurability guarantee of #1897 is intact, as is the
  DB-wins / env-fallback precedence). New `invalidate_credential_cache()`
  mirrors the existing `invalidate_embedder_cache` / `invalidate_reranker_cache`
  helpers (wired into `conftest.py` for test isolation; call it after any
  out-of-band singleton write that bypasses `save()`). Tests:
  `opencontractserver/tests/test_llm_model_factory.py::TestCredentialCache`.
