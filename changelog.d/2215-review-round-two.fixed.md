- **Closed a corpus-group slug-enumeration oracle in the deep-research kickoff
  tool.** `opencontractserver/llms/tools/research_tools.py::_load_group`
  resolved `corpus_group_slug` with an unfiltered
  `CorpusGroup.objects.filter(slug=...)`. No unauthorized access followed —
  `ResearchReportService.start` still refused the run — but the two failure
  modes *replied differently*: a nonexistent slug returned the tool's
  not-found string while a real-but-invisible one fell through to `start()`'s
  `PermissionError` text, letting a caller enumerate every group slug in the
  install. Now routed through `CorpusGroupService.get_group_by_ref`, matching
  the sibling `core_tools/multi_corpus.py::_resolve_group_corpora` and
  CLAUDE.md's services-layer rule, and both cases return one refusal.
- **`finalize_report` can no longer compose a report twice under concurrency.**
  The guard in `opencontractserver/tasks/research_tasks.py` was
  `refresh_from_db` + status check, i.e. check-then-act: pydantic-ai can
  dispatch parallel tool calls, and `reap_stalled_research` can put a second
  worker on the same report, so two callers could both observe RUNNING before
  either committed COMPLETED and both compose — the exact double-composition
  the guard exists to prevent. New `ResearchReportService.finalize_once` runs
  the check and the composition as one critical section under
  `select_for_update`, the same treatment `append_finding` / `append_tool_call`
  already receive. The salvage path in `_run_deep_research_async` uses it too,
  so a late salvage can no longer overwrite a genuine report committed by
  another worker.
- **Incremental reimport now records a terminal row for an unchanged,
  source-less document.** `opencontractserver/tasks/import_tasks_v2.py`
  returned early for a document matched by `canonical_key` whose content was
  unchanged and whose source is not reingestable (the NUL-placeholder members
  the V2 exporter writes for text/markdown documents), skipping the `DONE`
  `PendingDocumentAnnotations` row that `_reingest_document_with_deferred_remap`
  creates for the documents it converges. The document was therefore invisible
  to `finalize_corpus_import_relationships`: the corpus-level coordination row
  could not reach `DONE` on its account and `expected_doc_count` undercounted.
  Re-shipping a pack containing an unchanged markdown member is the ordinary
  case that hit this. (The row's `id_map` is empty for the same reason the
  converged path's is — relationship endpoints landing on unchanged documents
  remain tracked in issue #2220.)
