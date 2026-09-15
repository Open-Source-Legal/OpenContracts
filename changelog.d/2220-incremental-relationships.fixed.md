- Preserve relationship endpoints on unchanged documents during incremental
  corpus imports (#2220). `utils.importing.recover_annotation_id_map` matches
  incoming anchors to existing annotations without parsing or duplicating them;
  `tasks.import_tasks_v2` includes those IDs in relationship fan-in and logs
  unresolved endpoints.
