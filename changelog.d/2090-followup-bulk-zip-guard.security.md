- **Bound memory use on the remaining unguarded ZIP-member reads flagged in PR #2090 review.**
  The reingest source-read guard in that PR left three sibling, equally user-reachable reads
  unbounded:
  - `process_documents_zip` (bulk document ZIP upload, `opencontractserver/tasks/import_tasks.py`)
    had NO size check at all before `ZipExtFile.read()` — a crafted member of any declared size
    could force an unbounded in-memory allocation. It now reads through the new
    `read_zip_member_bounded()` helper (`opencontractserver/utils/zip_security.py`), bounded by
    `ZIP_MAX_SINGLE_FILE_SIZE_BYTES`.
  - `import_zip_with_folder_structure` (folder-structure import, same file) had two unguarded
    reads: the `labels.json` sidecar (no size check at all) and each document member (declared-size
    pre-checked via `validate_zip_for_import`, but the actual read was still unbounded — a crafted
    member whose declared `file_size` under-reports its true content could bypass that check). Both
    now route through `read_zip_member_bounded()`.
  - `_read_sidecar` (annotation sidecar JSON) already had a pre-read declared-size check, but the
    actual read (`sidecar_handle.read()`) was unbounded, so the same declared-size-lie bypass
    applied. The read is now bounded to `ZIP_MAX_SIDECAR_SIZE_BYTES + 1` bytes.
  `read_zip_member_bounded()` checks the declared size first (cheap rejection), then performs the
  real read with `read(max_bytes + 1)` so the amount of memory allocated is capped regardless of
  what the zip's central-directory metadata claims — mirroring the pattern
  `import_tasks_v2._read_guarded_source_bytes` already used for the reingest path.
  Also clarifies the `MAX_CORPUS_REINGEST_SOURCE_BYTES` settings comment
  (`config/settings/base.py`): despite the name, the guard covers the baked-import path too, and
  setting it to `0` blocks importing any document via the V2 importer, not just reingest-mode ones.
