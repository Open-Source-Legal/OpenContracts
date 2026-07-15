- ZIP import metadata (`meta.csv`) accepts an optional `external_id` column
  (`opencontractserver/utils/metadata_file_parser.py`): a durable, producer-
  namespaced identifier (e.g. `cross:H022844`) stored verbatim on the
  document's `DocumentPath.external_id` by `import_zip_with_folder_structure`
  (`opencontractserver/tasks/import_tasks.py`, new `external_ids_applied`
  result counter). Customs-ruling citation resolution already reads the
  `cross:` namespace as its highest-priority identity, so exported corpora
  can now resolve citations even after documents are renamed. Values longer
  than the field's 512-character limit are rejected per-row with a warning,
  never truncated.
- `enrich_customs_rulings` summary now records per-phase cost separately —
  `load_seconds` (storage fetches, summed across the prefetch pool),
  `match_seconds` (regex detection + citation resolution), `write_seconds`
  (annotation/reference/graph persistence), and a `load_failures` breakdown
  of `documents_skipped_unanchorable` — closing the handoff's item-E
  instrumentation follow-up.
