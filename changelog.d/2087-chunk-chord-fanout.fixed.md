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
