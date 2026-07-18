- **Content re-imports dropped a path's ingestion lineage**
  (`opencontractserver/documents/versioning.py::import_document`, update
  branch): re-importing a document at the same corpus path created the new
  current `DocumentPath` with empty `ingestion_source` / `external_id` /
  `ingestion_metadata`, while move, delete, and restore all carry those
  fields forward — so a durable `external_id` stamped by an earlier import
  was silently lost on upversion. The update branch now inherits the three
  lineage fields from the previous path version unless the caller supplies
  fresh values. Also hardened the customs enrichment namespace match to be
  case-insensitive (`CROSS:H022844` was stored verbatim but silently ignored
  at resolution time —
  `opencontractserver/enrichment/resolver.py::document_identity_candidates`).
