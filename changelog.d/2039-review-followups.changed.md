- **Post-merge review follow-ups for the bulk-trash primitive (#2039, follow-up
  to #2030).** Hardening + documentation polish, no behavior change:
  `DocumentLifecycleService.bulk_soft_delete_documents`
  (`opencontractserver/corpuses/services/lifecycle.py`) now initialises
  `trashed_doc_ids` before the `transaction.atomic()` block so the trailing
  logger/return can never `NameError` if a future early-return is added (a
  `with` does not introduce a scope); the dangling `(#1951)` forward-reference
  in its `PERF/MEMORY` comment is retargeted to #2045, which now tracks the
  separate memory-bounding (chunking) follow-up since #1951 only fixed the
  query count. The `CorpusPathService` docstring
  (`opencontractserver/corpuses/services/paths.py`) now lists
  `DocumentLifecycleService` as a consumer and spells out that its
  single-underscore helpers are **package-internal (not class-private)**, so
  cross-service use within `corpuses.services` (e.g.
  `_dispatch_document_path_created_signals`) is by design rather than a leaked
  internal. `mypy.ini`'s `python_version` comment is trimmed to the load-bearing
  "must match the Dockerfile" note (the numpy-2.5.0 detail already lives in the
  `2030-mypy-py312` fragment). `test_query_count_independent_of_document_count`
  gains a `msg=` on its query-count floor so a future failure is
  self-documenting.
