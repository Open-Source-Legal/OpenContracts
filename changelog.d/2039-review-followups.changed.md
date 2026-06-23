- **Post-merge review follow-ups for the bulk-trash primitive (#2039, follow-up
  to #2030).** Hardening + documentation polish, no behavior change:
  `DocumentLifecycleService.bulk_soft_delete_documents`
  (`opencontractserver/corpuses/services/lifecycle.py`) now initialises
  `trashed_doc_ids` before the `transaction.atomic()` block so the trailing
  logger/return can never `NameError` if a future early-return is added (a
  `with` does not introduce a scope); its `PERF/MEMORY` comment's dangling
  forward-reference now points to #2045 for the memory-bounding (chunking)
  follow-up, with #1951 retained as the query-count fix it actually was. Both
  the module and class docstrings in
  `opencontractserver/corpuses/services/paths.py` are corrected to describe the
  mixed convention accurately — they previously claimed *all* methods were
  underscore-prefixed, which the public `disambiguate_path` /
  `reconcile_paths_after_folder_change` contradict — and record that the
  underscore helpers (e.g. `_dispatch_document_path_created_signals`) are
  deliberately shared across sibling services, while public `disambiguate_path`
  is also called from the model layer (`Corpus.add_document`) and
  `documents.versioning`. `mypy.ini`'s `python_version` comment is trimmed from
  12 lines to 4, keeping the numpy detail inline rather than cross-referencing
  the `2030-mypy-py312` changelog fragment (which `collate_changelog.py --apply`
  deletes at release). `test_query_count_independent_of_document_count` gains
  `msg=` strings on both its query-count floor and the O(1) equality assertions
  so a future failure is self-documenting.
