- **Hardened the bulk-trash audit log (#2036, follow-up to #1951).**
  `DocumentLifecycleService.bulk_soft_delete_documents`
  (`opencontractserver/corpuses/services/lifecycle.py`) now emits its
  "Bulk soft-deleted N document(s)" log via `transaction.on_commit`, so the line
  is written only for durably committed trashing (no false success on a
  rolled-back or failed-`COMMIT` block) — matching the rollback-safety contract
  the primitive's dispatched `post_save` signals already use. Also promoted the
  in-body PERF/MEMORY note to a "Scaling caveat" in the method docstring: the
  primitive is O(1) in queries but still materializes the full document set in
  memory, so it carries no built-in document-count ceiling for the
  `empty_corpus` / folder cascade-delete callers.
