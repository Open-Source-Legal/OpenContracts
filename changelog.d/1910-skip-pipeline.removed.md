- **Removed the bulk-ZIP `skip_pipeline` inline-application path.** With deferred
  remap (#1910) sidecar documents flow through the standard parser pipeline, so
  `import_zip_with_folder_structure` (`opencontractserver/tasks/import_tasks.py`)
  no longer needs to apply annotations inline. Deleted the
  `if skip_pipeline and sidecar_data:` branch, the `_apply_sidecar_annotations`
  and `_validate_sidecar_schema` helpers (plus the `_ANNOTATION_REQUIRED_KEYS` /
  `_RELATIONSHIP_REQUIRED_KEYS` constants) and the now-unused imports. The
  always-zero `annotation_sidecars_processed` result key was replaced by
  `pending_annotation_docs`. `create_document_from_export_data`
  (`opencontractserver/utils/importing.py`) is retained — it is still used by the
  V2 corpus importer (`opencontractserver/tasks/import_tasks_v2.py`).
