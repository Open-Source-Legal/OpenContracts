- **Folded in code-review follow-ups (#2036) on the bulk-trash primitive**
  `DocumentLifecycleService.bulk_soft_delete_documents`
  (`opencontractserver/corpuses/services/lifecycle.py`). The success audit log
  now fires via `transaction.on_commit`, so it reports only durably committed
  trashing (no false "soft-deleted N" line if the block rolls back or the
  `COMMIT` fails) — the same rollback-safety contract the primitive's dispatched
  `post_save` signals already rely on; the count is captured inside the
  `atomic()` block so `trashed_doc_ids` is referenced only within its defining
  scope. Also surfaced the existing in-body PERF/MEMORY note as a "Scaling
  caveat" in the method docstring so callers eyeing an `empty_corpus` / folder
  cascade-delete size limit see that the primitive is O(1) in *queries* but
  still materializes the full doc set in memory (no built-in document-count
  ceiling). The review's `_dispatch_document_path_created_signals` rename
  suggestion was intentionally **not** taken: the `_`-prefix is consistent with
  five other cross-service helpers in `corpuses/services/` (e.g.
  `CorpusDocumentService._check_document_in_corpus`), so renaming one in
  isolation would break that convention rather than clarify it.
