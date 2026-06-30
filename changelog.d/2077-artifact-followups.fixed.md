- **Avoid an N+1 SELECT on artifact creation.** `ArtifactService.create` now refetches the new
  artifact with `select_related("corpus", "creator")` before returning, so the `CreateArtifact`
  mutation's `_artifact_to_type` serializer (which reads `a.corpus.slug`) no longer issues an extra
  query per create.
- **`ingest_corpus --wait` no longer stalls to timeout on a failed or deleted document.**
  `_wait_for_processing` (`opencontractserver/corpuses/management/commands/ingest_corpus.py`)
  waited for `free == len(doc_ids)`; a failed doc never clears its backend lock and a deleted doc
  leaves the queryset, so either burned the full `--timeout`. It now treats a document as settled
  once it is lock-free, failed, or missing, and reports the failed/missing counts when it continues.
  Test: `test_wait_for_processing_settles_on_failed_and_missing_docs`.
