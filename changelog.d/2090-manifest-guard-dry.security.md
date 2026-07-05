- **Bound the last unguarded ZIP-member read in the V2 importer: the `data.json` manifest.**
  `import_corpus_v2_from_bytes` (`opencontractserver/tasks/import_tasks_v2.py`) read the manifest —
  the very first member the importer opens, before any per-document guard runs — with an unbounded
  `ZipExtFile.read()`. A crafted `data.json` entry with a high compression ratio (classic zip-bomb
  pattern) could force an unbounded allocation independent of `MAX_DOCUMENT_IMPORT_SIZE_BYTES`
  (which only bounds the compressed upload size). It now routes through `read_zip_member_bounded()`,
  bounded by the new `MAX_CORPUS_MANIFEST_SIZE_BYTES` setting (default 512 MiB, backed by
  `DEFAULT_MAX_CORPUS_MANIFEST_SIZE_BYTES` in `opencontractserver/constants/document_processing.py`;
  same negative-disables-the-guard sentinel convention as `MAX_CORPUS_REINGEST_SOURCE_BYTES`).
- **Consolidated the three hand-rolled bounded-read implementations onto one.** `read_zip_member_bounded()`
  (`opencontractserver/utils/zip_security.py`) now accepts `max_bytes: int | None`, with `None` as the
  "unbounded" sentinel. `import_tasks_v2._read_guarded_source_bytes` and `import_tasks._read_sidecar`
  — which each re-implemented the same declared-size-check-then-bounded-read-then-post-read-guard
  shape (with subtly different exception handling that had already drifted once between commits) —
  are now thin wrappers around the shared helper, so a future change to the read strategy only needs
  to happen in one place.
