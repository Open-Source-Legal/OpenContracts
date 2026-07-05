- **Warp-Ingest PDF parser (REST microservice).** Added an alternative PDF
  parser based on [Warp-Ingest](https://github.com/Open-Source-Legal/Warp-Ingest),
  a deterministic, rule-based parser (pdfplumber + optional RapidOCR, no GPU)
  that renders straight to the OpenContracts export format.
  - New parser `opencontractserver/pipeline/parsers/warp_ingest_parser.py::WarpIngestParser`
    (auto-discovered by the pipeline registry). Follows the Docling REST pattern
    but is non-chunked: it sends the whole PDF to Warp-Ingest's `POST /api/parse?render_format=opencontracts`
    (multipart), authenticates via the `X-API-Key` header (leaving `Authorization`
    free for Cloud Run IAM), unwraps the `result` payload, and classifies
    timeout/connection/5xx as transient vs 4xx as permanent `DocumentParsingError`s.
    A configurable `max_file_size_mb` cap (default 200, env
    `WARP_INGEST_MAX_FILE_SIZE_MB`) bounds per-worker memory before buffering the
    file, and the user-controlled `document.title` is sanitized before it becomes
    the multipart filename.
  - Settings wired in `config/settings/base.py` (`WARP_INGEST_PARSER_SERVICE_URL`,
    `WARP_INGEST_API_KEY`, `WARP_INGEST_PARSER_TIMEOUT`) with the shared
    request-timeout constant `WARP_INGEST_PARSER_REQUEST_TIMEOUT_SECONDS` in
    `opencontractserver/constants/document_processing.py`; documented in the
    sample `.django` env files.
  - `local.yml` / `production.yml` define a `warp-ingest` service running the
    official `ghcr.io/open-source-legal/warp-ingest` image behind an opt-in
    `warp-ingest` compose profile (Docling stays the default PDF parser).
  - Docs: `docs/pipelines/warp_ingest_parser.md` (linked from the pipeline
    overview + mkdocs nav) and an end-to-end smoke-test script at
    `docs/test_scripts/warp_ingest_parser_smoke_test.md`. Unit tests:
    `opencontractserver/tests/test_doc_parser_warp_ingest.py`.
