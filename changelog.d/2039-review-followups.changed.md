- **Post-merge review follow-ups for the bulk-trash primitive (#2039, follow-up
  to #2030).** Documentation + test polish, no behavior change. This work landed
  after the overlapping #2046 (review #2036) merged, so the
  `bulk_soft_delete_documents` parts are reconciled with it: in
  `opencontractserver/corpuses/services/lifecycle.py` the *memory* follow-up
  references (the docstring "Scaling caveat" and the `PERF/MEMORY` comment) are
  retargeted from the now-closed #1951 to the open #2045 — completing the #2039
  point that the `(#1951)` forward-reference dangles once #1951 is closed (#2046
  added the caveat but kept pointing at the closed #1951). The separate #2039
  nit about `trashed_doc_ids` being read outside its `with` block is now moot:
  #2046 moved the audit log into `transaction.on_commit` *inside* the block, so
  there is no outside-block reference left to guard and no pre-initialisation is
  needed. Both the module and class docstrings in
  `opencontractserver/corpuses/services/paths.py` are corrected to describe the
  mixed convention accurately — they previously claimed *all* methods were
  underscore-prefixed, which the public `disambiguate_path` /
  `reconcile_paths_after_folder_change` contradict — and record that the
  underscore helpers (e.g. `_dispatch_document_path_created_signals`) are
  deliberately shared across sibling services, while public `disambiguate_path`
  is also called from the model layer (`Corpus.add_document`) and
  `documents.versioning`. `mypy.ini`'s `python_version` comment is trimmed from
  12 lines to 6 — dropping prose while keeping the numpy detail and the
  dual-usage note (pre-commit hook + standalone CI `Run mypy` step) inline,
  rather than cross-referencing the `2030-mypy-py312` changelog fragment (which
  `collate_changelog.py --apply` deletes at release).
  `test_query_count_independent_of_document_count` gains `msg=` strings on both
  its query-count floor and the O(1) equality assertions so a future failure is
  self-documenting.
