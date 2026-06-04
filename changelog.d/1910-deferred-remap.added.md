- **Deferred annotation import: re-anchor producer annotations onto the final PAWLs layer.**
  Bulk-ZIP / scraper / sidecar producers ship _dumb-anchor_ annotations — PDF
  `page`+`bbox` or text char-span (`start`/`end`) plus `rawText`, with no PAWLs
  or token indices (which go stale the moment the document is re-parsed). The
  document is created through the **normal** parser pipeline; producer
  annotations are persisted in a new `PendingDocumentAnnotations` model
  (`opencontractserver/documents/models.py`, migration `documents/0041`) and
  re-anchored after ingest.
  - `remap_pending_annotations` (`opencontractserver/tasks/doc_tasks.py`) now
    runs as a standard step in the post_save ingest chain
    (`extract_thumbnail → ingest_doc → remap_pending_annotations →
    set_doc_lock_state`, `opencontractserver/documents/signals.py`) and bails in
    a single indexed query when a document has no pending rows (the common case).
    Document creation and the pending row are wrapped in one
    `transaction.atomic()` so the chain's `on_commit` dispatch fires only after
    the row is committed (closes a latent race). `_remap_one_pending_row`
    likewise wraps annotation creation + status/`id_map` save in one atomic block
    so a failed status save can't leave duplicate annotations behind on retry,
    and it processes **all** PENDING rows for a document, not just the first.
  - `anchor_annotations` (`opencontractserver/utils/annotation_anchoring.py`)
    re-derives token indices from bbox + `rawText` against the freshly-parsed
    PAWLs; `_anchor_pdf` is multi-page. A `legacy_annotation_to_dumb_anchor`
    adapter normalises legacy baked-`annotation_json` exports through the same
    path (dropping their stale token indices). `structural=True` and
    unrecognised/compact-v2 `annotation_json` are **reported as dropped, never
    silently lost**, each with a distinct reason. Remapped token annotations are
    stored in the canonical compact v2 `annotation_json` encoding via
    `compact_annotation_json`.
  - Annotations that cannot be confidently anchored, or whose label does not
    resolve in the corpus labelset, are dropped and reported on the pending row
    (`dropped: true` + reason; `dropped` / `label_unresolved` counts). If
    anchoring succeeded but every annotation was dropped on an unresolved label,
    the row is marked `FAILED` rather than a silent `DONE`. `PendingDocumentAnnotations`
    gains an `updated_at` column and a Django admin registration for visibility
    into stuck/failed rows.
  - A standalone validator `validate_dumb_anchor_sidecar`
    (`opencontractserver/utils/validate_export.py`) checks a producer's sidecar
    against its `labels.json` before zipping (including the span-label-must-be-
    `TOKEN_LABEL` import gotcha). Shared PAWLs token-matching helpers
    (region selection, page-text tokenisation, fuzzy title matching, bounds
    union) were extracted to `opencontractserver/utils/pdf_token_matching.py`
    and are shared by the PDF outline enricher and the re-anchoring code.
  The full-V2 / single-document corpus-export import path (which ships
  self-consistent PAWLs + indices) is deliberately unchanged.
