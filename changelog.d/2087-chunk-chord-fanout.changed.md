- **Chunked ingest: cap chord fan-out to bound worker-pool pressure.** `ingest_doc`
  (`opencontractserver/tasks/doc_tasks.py`) previously dispatched an unbounded Celery
  chord — one task per chunk — so a very large document could enqueue hundreds of header
  tasks at once and saturate the worker pool (an availability risk). It now fans out only
  while `chunk_count <= parser.max_chord_tasks`; above that ceiling the document is parsed
  in a single in-process task. `max_chord_tasks` is a **new, distinct** config
  (`DEFAULT_MAX_CHORD_TASKS = 10` in `opencontractserver/constants/document_processing.py`,
  surfaced on `BaseChunkedParser` and as a `DoclingParser` pipeline setting /
  `DOCLING_MAX_CHORD_TASKS` env var) — deliberately separate from `max_concurrent_chunks`,
  which only sizes the in-process thread pool, so tuning thread parallelism never silently
  changes which documents fan out vs. parse in-process. A non-positive `max_chord_tasks`
  (e.g. `DOCLING_MAX_CHORD_TASKS=0`) now logs a warning identifying the misconfiguration
  each time it forces a chunked document onto the in-process path, instead of silently
  disabling chord fan-out with no indication.
