- **Worker-upload ingestion now produces a faithful mirror of the parser
  pipeline.** Closed three fidelity gaps in
  `opencontractserver/worker_uploads/tasks.py::_process_single_upload` so a
  document pushed through `/api/worker-uploads/documents/` ends up
  byte-for-byte equivalent to one ingested in-cluster:
  - **Structural annotation set materialisation.** Previously the parser's
    structural annotations (which are nearly *all* of a Docling parse) were
    imported as plain per-document annotations (`structural=True` but
    `structural_set=NULL`), diverging from in-cluster ingestion where they live
    in a shared `StructuralAnnotationSet` (`document=NULL`) and resolve through
    the structural-set join in `AnnotationService.get_document_annotations`. The
    worker path now calls `build_subtree_groups_for_document` +
    `create_structural_annotation_set` (the same steps as
    `BaseParser.save_parsed_data`). The migration logic was extracted from
    `BaseParser._create_structural_annotation_set` into a shared
    `opencontractserver/utils/structural_sets.py::create_structural_annotation_set`
    (no behaviour change to the parser path; DRY).
  - **Thumbnail generation.** The worker path now dispatches `extract_thumbnail`
    after ingest (the uploaded PDF is stored, so the server can regenerate
    `Document.icon` exactly as the parser pipeline does). This is the standalone
    thumbnail task — it does not trigger a re-parse.
  - **Embedding ownership.** `import_annotations` gained a
    `dispatch_embeddings: bool = True` parameter
    (`opencontractserver/utils/importing.py`). When a worker upload supplies
    pre-computed embeddings, `_process_single_upload` passes
    `dispatch_embeddings=False` so the server does not redundantly re-embed every
    annotation — the remote worker owns the embedding layer (the point of
    offloading enrichment). With no embeddings supplied, the server embeds as
    before.
  - `WorkerDocumentUploadMetadataType` gained optional `parser_name` /
    `parser_version` fields so a remotely-parsed document records the same
    structural-set provenance as an in-cluster parse.
