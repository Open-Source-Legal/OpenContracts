- **Remote-ingest worker: embedder API-key env var was wrong.** The embedder
  service block in `scripts/remote_ingest/remote_worker.yml` /
  `remote_worker.accel.yml` set `API_KEY`, but the embedder image reads
  `VECTOR_EMBEDDER_API_KEY` (`compose/accelerated/embedder/main.py`) — so the key
  was ignored, the image fell back to its built-in default, and a worker
  configured with any other key got HTTP 401 on every embedding request. The env
  var is renamed to `VECTOR_EMBEDDER_API_KEY` (the actual root cause) and its
  empty fallback hardened to `${VECTOR_EMBEDDER_API_KEY:-abc123}` so a forgotten
  export no longer sends an empty key. **Operators with a running embedder must
  recreate (not just restart) the container** to pick up the renamed env var.
- **Local dev: same embedder env-var fix in `local.yml`.** The `vector-embedder`
  and `multimodal-embedder` services set the ignored `API_KEY` too; they now set
  `VECTOR_EMBEDDER_API_KEY` sourced from the matching Django-side var
  (`VECTOR_`/`MULTIMODAL_EMBEDDER_API_KEY` in `.envs/.local/.django`) so an
  overridden key stays in sync on both sides instead of silently mismatching.
- **Tests: `test.yml`'s `vector-embedder` service was missing the same env var.**
  The `multimodal-embedder` block in `test.yml` was updated to pass
  `VECTOR_EMBEDDER_API_KEY`, but the `vector-embedder` block (`test.yml` lines
  7-16) was left without it — the test suite only worked because the embedder
  image's hardcoded `abc123` default happened to match the test env's
  `VECTOR_EMBEDDER_API_KEY`. Added the same `${VECTOR_EMBEDDER_API_KEY:-abc123}`
  wiring so the test container isn't silently disconnected from the Django-side
  key if that default is ever changed to a real key.
