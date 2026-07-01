- **Chunked ingest: fix chunk-scratch storage leak on the in-process fallback.**
  `prepare_chunk_inputs` unconditionally writes N chunk PDFs to `default_storage`
  (`chunk_scratch/doc_{id}/`) before returning, but `cleanup_chunk_artifacts` only ran
  inside the chord callback (`reassemble_and_finalize`). When `ingest_doc`
  (`opencontractserver/tasks/doc_tasks.py`) skips the chord and parses in-process, the
  in-process path re-reads the original PDF and never touches the scratch files, so every
  document exceeding the fan-out ceiling leaked all of its chunk PDFs on every ingest
  (multiplied across Celery retries). The fallback branch now calls
  `cleanup_chunk_artifacts(doc_id)` before re-parsing. Regression test:
  `opencontractserver/tests/test_chunk_tasks.py::TestChunkTasks::test_ingest_doc_large_pdf_falls_back_when_chunk_count_exceeds_limit`.
- **Chunked ingest: don't let a cleanup-storage exception strand a document in
  a retry loop.** `cleanup_chunk_artifacts` only guards its own `listdir` call
  against `(FileNotFoundError, NotADirectoryError, OSError)`
  (`opencontractserver/pipeline/chunk_artifacts.py`); cloud storage backends
  (S3, GCS) can raise SDK-specific exceptions (e.g.
  `botocore.exceptions.ClientError`) that aren't `OSError` subclasses. If that
  escaped the fallback branch in `ingest_doc`
  (`opencontractserver/tasks/doc_tasks.py`), Celery's outer `except Exception`
  would treat it as transient and retry — `prepare_chunk_inputs` writes the
  same scratch files again, cleanup fails again, and the document exhausts
  its retries without ever actually parsing. The call is now wrapped in its
  own `try/except Exception`, logging a warning and continuing to the
  in-process parse (a leaked scratch file is far less harmful than a document
  that never parses). Regression test:
  `TestChunkTasks::test_ingest_doc_fallback_survives_cleanup_exception`.
