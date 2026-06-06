- **Bulk import: annotation-to-annotation relationships, richer annotation metadata, and cross-batch document relationships.**
  Closes long-standing gaps in what the bulk-ZIP / dumb-anchor sidecar format
  could express. Builds on the deferred-remap pipeline (the producer-id →
  new-annotation `id_map` it already persisted is now consumed end-to-end).
  - **Annotation-to-annotation relationships in sidecars.** A dumb-anchor
    sidecar may now carry a top-level `relationships` list
    (`relationshipLabel` + `source_annotation_ids` / `target_annotation_ids`
    referencing the sidecar's own annotation `id`s — e.g. `OC_PARENT_CHILD`,
    `OC_SUBTREE_GROUP`). `import_zip_with_folder_structure`
    (`opencontractserver/tasks/import_tasks.py`) persists them verbatim onto the
    `PendingDocumentAnnotations` payload (and counts them in the new
    `sidecar_relationships_found` result field) instead of the old
    drop-and-warn. After ingest, `remap_pending_annotations`
    (`opencontractserver/tasks/doc_tasks.py`, `_wire_pending_relationships`)
    wires them in the **same atomic block** as the annotation import, using the
    `import_annotations` `id_map` to resolve endpoints (int/str-id tolerant) and
    auto-creating each `RELATIONSHIP_LABEL` via `corpus.ensure_label_and_labelset`
    (mirroring the `relationships.csv` path). An edge whose endpoints did not
    survive anchoring is **dropped and reported** on the row (`relationships` /
    `relationships_dropped` counts), never silently lost.
  - **`link_url` + `data` survive the re-anchor.** `anchor_annotations`
    (`opencontractserver/utils/annotation_anchoring.py`) now carries the OC_URL
    click-through `link_url` and the structured `data` sidecar (e.g. the geocoded
    `OC_COUNTRY`/`OC_STATE`/`OC_CITY` `{canonical_name, lat, lng, …}` payload)
    verbatim through PDF, span, and legacy-adapter anchoring; `import_annotations`
    (`opencontractserver/utils/importing.py`) persists `data` onto
    `Annotation.data` (it already handled `link_url`). `OpenContractsAnnotationPythonType`
    gains an optional `data` field.
  - **Cross-batch document relationships.** A `relationships.csv` endpoint that
    matches no file in the current ZIP now falls back to a document already in
    the corpus (`build_existing_corpus_path_map`, gated by
    `CorpusDocumentService.get_corpus_documents` so only documents the importing
    user can access are eligible). The phase runs whenever a `relationships.csv`
    is present — even for a ZIP that contains *only* the CSV — so separately
    imported batches can be wired together; the in-import map takes precedence
    over the corpus fallback.
  - **Validation.** `validate_dumb_anchor_sidecar`
    (`opencontractserver/utils/validate_export.py`) now validates the
    `relationships` list (label present; non-empty source/target id lists; every
    endpoint references an annotation declared in the sidecar) and type-checks
    optional `link_url` (string) / `data` (object) on annotations.
  Span annotations still import as `TOKEN_LABEL`-typed labels (the deliberate
  importer constraint is unchanged), and `structural=true` / exact-geometry
  pinning remain re-derived by the parser by design.
