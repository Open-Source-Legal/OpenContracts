- **Bound memory use when reingesting corpus-export ZIP members — on both the reingest and baked
  paths.** User-facing V2 corpus-export imports default to reingest mode, where
  `_import_document_with_annotations` (`opencontractserver/tasks/import_tasks_v2.py`) previously did
  an unbounded `ZipExtFile.read()` on each document member — a crafted ZIP could force Celery
  workers to allocate memory proportional to the uncompressed member. A single shared choke point,
  `_read_guarded_source_bytes`, now (1) skips the read when the central-directory `file_size`
  exceeds the new `MAX_CORPUS_REINGEST_SOURCE_BYTES` setting (256 MiB default, backed by
  `DEFAULT_MAX_CORPUS_REINGEST_SOURCE_BYTES` in `opencontractserver/constants/document_processing.py`);
  (2) performs a bounded read of `limit + 1` bytes so memory is capped even if the metadata lies;
  (3) treats a member it cannot read safely (a lied-down `file_size` trips CRC validation, or the
  post-read length guard catches a `ZIP_STORED` lie) as unreadable, returning `None`; and (4)
  catches a missing member (`KeyError`) so one absent file falls back gracefully instead of aborting
  the corpus import.
- **Close the baked-import bypass of the source-size guard.** When the reingest peek rejected an
  over-size member, `_import_document_with_annotations` previously fell through to the baked-import
  block and re-opened the *same* member with `import_zip.open(doc_filename)` (no size limit),
  streaming the whole entry into storage — fully defeating the guard on every size-rejected member
  (reingest defaults on at the user-facing service boundary). The baked block now reads through the
  same `_read_guarded_source_bytes` choke point and skips the document when the source is rejected,
  so an over-size member is refused on both paths.
- **`MAX_CORPUS_REINGEST_SOURCE_BYTES` disable is now a negative sentinel, not `0`.** Previously the
  guard short-circuited on a falsy `0`, so an operator zeroing the value to *harden* silently
  removed all protection (the read became `read(-1)`, unbounded). Parsing in `config/settings/base.py`
  now maps a negative value to `None` (guard disabled, intentional escape hatch); `0` is a literal
  zero-byte limit that rejects every non-empty member. Tests:
  `opencontractserver/tests/test_import_v2_reingest_remap.py::TestSourceReingestability`.
