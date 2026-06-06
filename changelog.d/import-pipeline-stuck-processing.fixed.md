### Fixed

- **Documents no longer get stranded in "processing" after an ingest-pipeline
  failure.** The document-ingest Celery chain (`extract_thumbnail → ingest_doc →
  remap_pending_annotations → set_doc_lock_state`) carried no error callback, so
  if any task *raised* (a worker OOM/SIGKILL mid-task, a lost broker message, or
  a DB error inside `_mark_document_failed`) the chain halted before
  `set_doc_lock_state` could finalize status — leaving the document at
  `processing_status=PROCESSING` + `backend_lock=True`, which the frontend
  renders as "processing" forever (`ModernDocumentItem.tsx`:
  `isProcessing = status != FAILED && backendLock`). Three layers of hardening:
  - **Fail fast on permanent docling failures** — `docling_parser_rest.py` now
    classifies a `5xx` whose body is a docling `ConversionStatus.FAILURE` /
    `ConversionError` (a malformed PDF, e.g. "could not find the
    page-dimensions") as **non-transient**, so it fails on the first attempt
    instead of exhausting retries. This kills the retry storm that overloaded
    the parser service (the 503 cascade) during bulk imports.
  - **link_error on the ingest chains** — new
    `mark_doc_failed_on_chain_error` task is attached via `link_error` to the
    chains in `documents/signals.py` and `retry_document_processing`
    (`tasks/doc_tasks.py`); a raised chain failure now marks the document FAILED
    immediately (idempotent — won't clobber an already-terminal state).
  - **Periodic reconciliation sweep** — new `reconcile_stuck_documents`
    Celery-beat task (`tasks/doc_tasks.py`, scheduled every 5 min in
    `CELERY_BEAT_SCHEDULE`) reclaims any `PROCESSING` + locked document whose
    `processing_started` is older than `DOCUMENT_PROCESSING_STALE_MINUTES`
    (default 30) and marks it FAILED via `_mark_document_failed`, covering the
    silent failure modes (hard worker kills / lost messages) that never surface
    as an exception. New setting `DOCUMENT_PROCESSING_STALE_MINUTES` in
    `config/settings/base.py`.
