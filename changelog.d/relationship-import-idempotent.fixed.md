- `relationships.csv` import created duplicate `DocumentRelationship` rows on
  re-import (`opencontractserver/tasks/import_tasks.py::_create_document_relationships`
  used a blind `create`). Now `get_or_create` on the edge's natural identity
  (source, target, corpus, label, type) — mirroring the enrichment writer's
  graph-rollup semantics — so relationships-only patch ZIPs and re-run batches
  are idempotent; duplicates count as `relationships_skipped`.
