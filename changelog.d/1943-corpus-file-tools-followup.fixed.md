- **`rename_document` agent tool: dropped an extra query and closed a status race (PR #1940 follow-up, issue #1943 item 1).**
  `FolderDocumentService.rename_document`
  (`opencontractserver/corpuses/services/folder_documents.py`) now returns a
  4-tuple `(success, error, new_path, changed)` — the new `changed` boolean is
  `True` only for a real rename and `False` for a no-op (sanitised name already
  matched) or any failure. The tool
  (`opencontractserver/llms/tools/core_tools/documents.py`) previously
  snapshotted the pre-rename `DocumentPath.path` and compared it to the
  service's returned path to label the response `"renamed"` vs `"unchanged"`.
  That extra `DocumentPath` read is gone, and so is the snapshot-vs-service race
  window where a concurrent rename could mislabel the `status` (the underlying
  data was always safe — the service's `select_for_update` guarantees that;
  only the tool-layer status string could drift).
