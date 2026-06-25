- **Remote-ingest worker: offload parsing + enrichment to off-cluster hosts.**
  Added a driver and Docker bundle (`scripts/remote_ingest/`) that run the FULL
  ingestion pipeline (Docling parse + embeddings) on a remote workstation and
  stream fully-processed, faithfully-mirrored documents to a target instance via
  the worker-upload REST API (`/api/worker-uploads/documents/`) — no access to
  the target's database required. Because the worker runs the same Docling
  microservice image and the same `DoclingParser` code, the PAWLs token layer,
  structural annotations and embeddings are identical to an in-cluster
  ingestion (faithful by construction). Components:
  - `scripts/remote_ingest/oc_remote_ingest.py` — resumable per-document driver
    (SQLite ledger; `plan`/`run`/`verify`/`status` subcommands; thread-pool
    concurrency; back-pressure against the target's worker-upload backlog;
    bounded retry/backoff honouring `429 Retry-After`).
  - `scripts/remote_ingest/remote_worker.yml` + `worker-entrypoint.sh` — a
    self-contained bundle (docling-parser + vector-embedder + worker) the remote
    host brings up with a few commands.
  - `config/settings/remote_worker.py` — a lean Django settings module that
    points at a throwaway SQLite file so the worker needs no Postgres/Redis. The
    parse path is database-free; settings are sourced from `DOCLING_*` /
    `EMBEDDINGS_*` env vars.
  - `opencontractserver/worker_uploads/management/commands/mint_worker_token.py`
    — one-command server-side setup: creates/reuses a worker account and prints a
    one-time corpus-scoped `CorpusAccessToken`.
  - `BaseChunkedParser.parse_pdf_bytes()`
    (`opencontractserver/pipeline/base/chunked_parser.py`) — a new database-free
    entry point that turns raw PDF bytes into an `OpenContractDocExport` (chunk
    split → parse → reassemble → image extraction) without reading a `Document`
    row, so the parser can be driven headlessly. `_parse_document_impl` now
    fetches the PDF bytes and delegates to it (behaviour unchanged).
  See `scripts/remote_ingest/README.md`.
