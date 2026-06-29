- **Remote-ingest worker: safer `VECTOR_EMBEDDER_API_KEY` default.** Changed the
  empty fallback (`${VECTOR_EMBEDDER_API_KEY:-}`) in
  `scripts/remote_ingest/remote_worker.yml` and `remote_worker.accel.yml` to
  `:-abc123` (matching `compose/accelerated/accel.override.yml`), so a forgotten
  export no longer silently sends an empty key to the embedder service and causes
  HTTP 401 on every embedding request.
