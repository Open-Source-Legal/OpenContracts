- **Single-user desktop packaging, Phase 0 — run the whole stack as processes
  with no Docker and no Redis.** Adds a `config.settings.desktop` profile and an
  `oc-desktop.py` launcher (`opencontractserver/desktop/launcher.py`) that starts
  an embedded PostgreSQL+pgvector child (`pgserver`) or an external
  `DATABASE_URL`, runs `migrate` + a one-time `desktop_bootstrap`
  (`opencontractserver/documents/management/commands/desktop_bootstrap.py`:
  local superuser, `PipelineSettings` seeding, nltk corpora), then supervises
  Daphne (serving the API and the pre-built SPA) plus a Celery worker/beat over
  the kombu *filesystem* broker with a SQLAlchemy DB result backend. The desktop
  profile drops Redis entirely: cache → `LocMemCache`, channel layer →
  `InMemoryChannelLayer`, storage → local per-user app-data dir
  (`opencontractserver/desktop/paths.py`). The SPA is served from Daphne via
  WhiteNoise + a catch-all (`config/spa.py`, wired into `config/urls.py` only
  when `OC_DESKTOP_SPA_ROOT` is set; the `:3000` dev redirect is skipped there).
  See `docs/deployment/desktop_packaging.md`.
- **`WarpIngestParser`
  (`opencontractserver/pipeline/parsers/warp_ingest_parser.py`)** — an
  in-process, rule-based PDF parser (pure-Python, no torch/GPU) wrapping
  [Warp-Ingest](https://github.com/Open-Source-Legal/Warp-Ingest)'s
  `pdf_ingestor.parse_to_opencontracts`, which emits PAWLS tokens, structural
  annotations and the `OC_PARENT_CHILD` heading hierarchy directly as an
  `OpenContractDocExport`. It replaces the Docling parsing microservice for the
  desktop build. `warp_ingest` is imported lazily so pipeline auto-discovery is
  unaffected when the optional dependency is absent; it is registered for all
  deployments but only selected when `PREFERRED_PARSERS`/`PipelineSettings` point
  at it (the compose default stays Docling). New extras live in
  `requirements/desktop.txt` (`warp-ingest[ocr]`, `pgserver`, `sqlalchemy`).
