- **Opt-in "reingest & remap" mode for V2/V3 corpus-export import.** A new
  `reingest_and_remap: bool = False` flag, threaded through
  `import_corpus_export_for_user` → `import_corpus` → `import_corpus_v2` →
  `import_corpus_v2_from_bytes` → `_import_corpus` →
  `_import_document_with_annotations`, re-parses each imported document through
  the *current* pipeline instead of trusting the export's baked PAWLs /
  structural layer. Per document it: drops the exported structural annotations
  (skips `import_structural_annotation_set`), re-ingests from the raw source
  bytes via `corpus.import_content(..., backend_lock=True)` so the standard
  post-save chain regenerates PAWLs + structural annotations, and defers the
  surviving non-structural annotations into a `PendingDocumentAnnotations` row
  for `remap_pending_annotations` to re-anchor (`tasks/import_tasks_v2.py`,
  `_reingest_document_with_deferred_remap`). Default behavior is unchanged —
  the synchronous V2 import stays the default and the only path the REST
  endpoint and `fork_corpus` use (no REST field, no frontend toggle this
  iteration).
- **Asynchronous corpus-relationship fan-in.** New `PendingCorpusImport`
  coordination model (`documents/models.py`, migration `documents/0042`) holds
  a reingest run's corpus-level relationships and an `expected_doc_count`. An
  exactly-once `_maybe_finalize_corpus_import(run_id)`
  (`select_for_update(skip_locked=True)` claim) is triggered from both the
  post-loop in `_import_corpus` and from `remap_pending_annotations`
  (`tasks/doc_tasks.py`), and dispatches `finalize_corpus_import_relationships`
  once every document's remap has recorded its `id_map`. The finalizer
  aggregates the per-document maps, rebuilds the `(text, label_type)` label
  lookup, and calls the existing `_import_v2_relationships`. The task is
  retry-safe (accepts `FINALIZING`/`FAILED` re-entry; wiring + `DONE` flip in
  one transaction so a crash rolls partial writes back).
- **Fixed: compact-v2 PDF annotations are now anchorable on reingest.**
  `legacy_annotation_to_dumb_anchor` (`utils/annotation_anchoring.py`) now
  accepts the compact-v2 `annotation_json` shape (`{"v": 2, "p": {page: {"b":
  [top, left, right, bottom], "t": ...}}}`) the V2/V3 exporter actually emits,
  in addition to the legacy verbose `{page: {"bounds": ...}}` shape. Without
  this, every PDF annotation in a real corpus export was silently dropped when
  fed through the remap machinery.
