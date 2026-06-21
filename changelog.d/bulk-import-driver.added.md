- **Bulk PDF import driver** (`scripts/bulk_import/oc_bulk_import.py`, with
  `README.md` and `tests/test_batching.py`) — a resumable, client-side CLI for
  loading very large local PDF trees (100K+ files) into a corpus. It packs files
  into right-sized ZIP batches (under the server's file/size/folder import caps),
  submits them through the existing `POST /api/imports/zip-to-corpus/` endpoint
  (mirroring the local folder tree and running the normal parse pipeline), and
  records progress in a SQLite ledger so crashes/`Ctrl-C` never lose work.
  Re-runs are idempotent because re-importing the same relative path upversions
  rather than duplicating. The driver paces itself against the live corpus parse
  backlog (`documentStats.processingCount`) since the server has no built-in
  backpressure, refreshes its JWT automatically on 401 for multi-day runs, and
  reconciles completion by corpus document count (the `zip-to-corpus` `job_id` is
  not pollable). No backend changes were required — only the operational tuning
  documented in the README and `docs/test_scripts/bulk_import_200k.md` (notably
  disabling `ADD_DOCUMENT` CorpusActions during the load to avoid a per-document
  analysis fan-out, and raising `DOCUMENT_PROCESSING_STALE_MINUTES` so the
  stuck-document reconciler does not false-fail a deep backlog).
