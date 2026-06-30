- **Bound memory use when reingesting corpus-export ZIP members.** User-facing V2 corpus-export
  imports default to reingest mode, where `_import_corpus`
  (`opencontractserver/tasks/import_tasks_v2.py`) previously did an unbounded `ZipExtFile.read()`
  on each document member — a crafted ZIP could force Celery workers to allocate memory
  proportional to the uncompressed member. `_read_reingest_source_bytes` now (1) skips the read
  when the central-directory `file_size` exceeds the new
  `MAX_CORPUS_REINGEST_SOURCE_BYTES` setting (256 MiB default, `config/settings/base.py`), read
  directly (no `getattr` 0-fallback that could silently disable the guard); (2) performs a bounded
  read of `limit + 1` bytes so memory is capped even if the metadata lies; (3) treats a member it
  cannot read safely (a lied-down `file_size` trips CRC validation on the bounded read) as
  non-reingestable, returning `None` so just that document falls back to the baked import instead
  of aborting the whole corpus import; and (4) keeps a post-read length guard as defense-in-depth.
  The fallback log now distinguishes a size-guarded/unreadable source from a genuine NUL
  placeholder so crafted-member probes stay visible. Tests:
  `opencontractserver/tests/test_import_v2_reingest_remap.py::TestSourceReingestability`.
