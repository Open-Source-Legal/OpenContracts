- **Every fresh desktop install died mid-migration on `pg_trgm`**
  (`opencontractserver/annotations/migrations/0074_annotation_raw_text_trigram_index.py`).
  The embedded `pgserver` PostgreSQL bundles only `plpgsql` + `vector` (no
  contrib extensions), so the unconditional `TrigramExtension()` raised
  `NotSupportedError: extension "pg_trgm" is not available` and the launcher
  aborted — unrecoverable for an end user (escaping it required compiling the
  extension from PostgreSQL source). The migration now probes
  `pg_available_extensions` via `RunPython` and skips the extension + GIN
  index when `pg_trgm` is absent: the queries it accelerates are plain
  `icontains`/ILIKE, which run correctly (sequentially scanned) without it —
  an acceptable trade at single-user desktop scale. Real Postgres deployments
  (compose/production/CI) still get the identical extension + index. The
  reverse operation now drops only the index and deliberately leaves the
  extension installed, removing the previously documented `DROP EXTENSION`
  reversal hazard.
