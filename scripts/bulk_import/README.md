# Bulk PDF Import Driver (`oc_bulk_import.py`)

A resumable, client-side CLI for loading a **large local tree of PDFs**
(hundreds of thousands of files) into an OpenContracts corpus — performantly and
without tying up the system.

It feeds files through the existing **`POST /api/imports/zip-to-corpus/`**
endpoint, so:

- the local folder hierarchy is **mirrored** as corpus folders,
- each PDF runs the **normal parse pipeline** (Docling/text → PAWLs →
  embeddings), and
- **no server changes are required** — only the operational tuning below.

> **Why not a single bulk upload?** Base64-over-GraphQL and one giant ZIP both
> buffer everything in RAM, and queueing 200K parses at once starves interactive
> users. This driver packs files into right-sized ZIP batches, paces itself
> against the live parse backlog, and records progress in a SQLite ledger so a
> crash or `Ctrl-C` never loses work.

## Requirements

- Python 3.9+
- `pip install requests`

## How it works

1. **`plan`** walks `--root-dir`, selects files (`.pdf` by default), and packs
   them into ZIP batches that stay under the server's import caps
   (≤ files / total bytes / folders per ZIP). Each file's path *relative to the
   root* becomes its ZIP arcname — that's what reproduces the folder tree.
   Oversize files (≥ 100 MB) are routed to the single-document endpoint instead.
   The plan is written to a SQLite **ledger** (`--ledger`, default
   `./oc_ingest.db`). Batch ids are content hashes, so re-planning the same tree
   is stable.
2. **`run`** submits `PENDING`/`FAILED` batches with a small concurrent pool,
   **pausing** whenever the corpus has too many documents still parsing
   (backpressure). Accepted batches become `SUBMITTED`.
3. **`verify`** compares the corpus's document count against the ledger once
   parsing drains, and marks batches `VERIFIED`. Re-running `run` safely
   re-submits anything unfinished (same path **upversions** — it never creates
   duplicates).

## Quickstart

```bash
cd scripts/bulk_import            # the driver is a standalone script

export OC_API_BASE=https://your-opencontracts.example.com
export OC_USERNAME=bulk_importer
export OC_PASSWORD=...

# 1. Create a dedicated corpus (prints its global id)
CORPUS=$(python oc_bulk_import.py create-corpus --title "Archive 2026")
export OC_CORPUS_ID=$CORPUS

# 2. Plan the batches (no network beyond none; inspect before sending)
python oc_bulk_import.py plan --root-dir /data/pdfs

# 3. Run (resumable — safe to Ctrl-C and re-run)
python oc_bulk_import.py run --root-dir /data/pdfs --max-inflight 4

# 4. Watch progress
python oc_bulk_import.py status

# 5. Once processing drains, reconcile
python oc_bulk_import.py verify
```

## Authentication

The driver supports three auth modes, resolved in this priority order:

1. **Worker token — `OC_WORKER_TOKEN` (recommended for Auth0 / production).**
   A `CorpusAccessToken` minted for the target corpus, sent to the import
   endpoints as `Authorization: WorkerKey <token>`. It works regardless of
   whether the backend uses Auth0, is corpus-scoped, revocable, and bypasses the
   per-user usage cap by design (minting one already requires the corpus
   creator/superuser). The corpus must already exist — `create-corpus` is **not**
   available in this mode. Mint a token via GraphQL (corpus creator/superuser):

   ```graphql
   mutation { createWorkerAccount(name: "bulk-importer") { workerAccount { id } } }
   mutation {
     createCorpusAccessToken(workerAccountId: "<id>", corpusId: "<corpus global id>")
     { token }   # shown once — copy it
   }
   ```
   ```bash
   export OC_WORKER_TOKEN=<token from createCorpusAccessToken>
   export OC_CORPUS_ID="<corpus global id>"
   python oc_bulk_import.py run --root-dir /data/pdfs
   ```

   > **Backpressure needs an authenticated `documentStats`.** A `WorkerKey` is
   > REST-only, so in worker-token mode the GraphQL `documentStats` query runs
   > unauthenticated and a **private** corpus reports `processingCount=0` —
   > pacing then never engages (`run` warns about this). For a private corpus,
   > also export `OC_TOKEN` (a bearer JWT with READ on the corpus); the driver
   > uses it for GraphQL while still importing via the worker token. A public
   > corpus needs nothing extra.

2. **Bearer token — `OC_TOKEN`.** A raw JWT used for both REST and GraphQL
   (e.g. an Auth0 token copied from a browser session, or a `tokenAuth` token on
   a non-Auth0 backend).

3. **Username / password — `OC_USERNAME` / `OC_PASSWORD`.** Exchanged for a JWT
   via the `tokenAuth` mutation. **Only works on non-Auth0 backends** (an Auth0
   deployment rejects the resulting token). The driver re-authenticates on a 401
   so multi-day runs keep going. The account must not be usage-capped (or set
   `USAGE_CAPPED_USER_CAN_IMPORT_CORPUS=True` on the server).

> **Token safety:** prefer the `OC_*` env vars over the `--worker-token` /
> `--token` / `--password` flags — flag values are visible to other users on the
> host via `ps` and `/proc/<pid>/cmdline`. The ledger is bound to the first
> `--corpus-id` it sees and warns if a later `run`/`verify` points at a different
> corpus. The SQLite ledger stores only batch/progress metadata — **never the
> token or any credential** — so it doesn't need the same protection as the token.

> **Large files & proxies:** payloads above 50 MB (large ZIP batches and any
> file ≥ the `--single-file-cap`, which routes to the single-document endpoint)
> are uploaded automatically via the chunked endpoints (`/api/imports/chunked/*`),
> so they stream past reverse-proxy body limits (e.g. Cloudflare's 100 MB) and
> never buffer whole on the server. No manual tuning is required.

## Operational runbook (do this before a 200K load)

The driver handles ingestion; these steps keep **processing** healthy. The real
bottleneck is parsing, not upload.

### Pre-flight

1. **Dedicated corpus.** Use a fresh corpus (created above) so the load is
   isolated and easy to reconcile.
2. **Disable `ADD_DOCUMENT` CorpusActions during the load — most important.**
   Every document added to a corpus fires
   `process_corpus_action(trigger=ADD_DOCUMENT)`
   (`opencontractserver/corpuses/models.py`). An enabled auto-analysis/extract
   action would fan out **once per document** → 200K extra agent tasks. Audit
   and set `CorpusAction.disabled = True` for the load window (corpus-scoped
   actions *and* any `run_on_all_corpuses=True`):

   ```python
   # docker compose -f local.yml run django python manage.py shell
   from opencontractserver.corpuses.models import CorpusAction, CorpusActionTrigger
   (CorpusAction.objects
        .filter(trigger=CorpusActionTrigger.ADD_DOCUMENT, disabled=False)
        .update(disabled=True))
   ```
3. **Raise server caps / throttle via env** (no code change):
   - `ZIP_MAX_FILE_COUNT`, `ZIP_MAX_TOTAL_SIZE_BYTES`, `ZIP_MAX_FOLDER_COUNT`
     (keep the driver's `--target-*` below these).
   - `MAX_DOCUMENT_IMPORT_SIZE_BYTES` ≥ your largest ZIP.
   - `document_imports` throttle (DRF `DEFAULT_THROTTLE_RATES`) — raise from the
     default `120/hour` if you want submission headroom (optional; parse-drain
     is the real limiter).
   - `DOCUMENT_PROCESSING_STALE_MINUTES` → e.g. `120`. Under a deep backlog the
     `reconcile_stuck_documents` beat (default 30 min) can otherwise mark
     still-queued docs `FAILED`.
4. **Confirm parser capacity.** `DOCLING_PARSER_SERVICE_URL` and its
   replicas/concurrency set the true throughput ceiling — size it for your
   target docs/hour.

### During the load

- **Scale parse workers** consuming the default `celery` queue
  (`prefetch_multiplier=1`, `max_tasks_per_child=4`). **Recommended: isolate**
  the bulk parse load on a separate worker fleet (or run in a maintenance
  window) so a 200K backlog doesn't starve interactive document parsing.
- **Pace with the driver, not the server** (there is no server-side
  backpressure). `--queue-high` / `--queue-low` pause submission when the
  corpus's `processingCount` is too deep. Defaults: pause above 5000, resume
  below 2000. Lower these on a small worker fleet.
- **Monitor** with `oc_bulk_import.py status` (ledger + live
  `documentStats`) and your broker/Flower for default-queue depth.

### After the load

1. **Recover any `FAILED` documents** (e.g. false-stuck) once the backlog
   clears, via `retry_document_processing(user_id, doc_id)` over the corpus's
   `processing_status=FAILED` rows.
2. **Re-enable CorpusActions** you disabled.
3. **Run intended analyses deliberately as one batched job** (not the per-doc
   auto-fire you disabled).
4. **Revert** the env tuning (stale-minutes, throttle, caps).

## Tuning reference

| Flag | Default | Notes |
|------|---------|-------|
| `--target-files` | 500 | Max files per ZIP (server cap 1000). |
| `--target-bytes` | 250 MB | Max uncompressed bytes per ZIP (server cap 500 MB). |
| `--target-folders` | 400 | Max distinct folders per ZIP (server cap 500). |
| `--single-file-cap` | 100 MB | ≥ this → single-document endpoint. |
| `--max-inflight` | 4 | Concurrent ZIP submissions. |
| `--queue-high` / `--queue-low` | 5000 / 2000 | Backpressure watermarks (`processingCount`). `--queue-high 0` disables. |
| `--max-attempts` | 5 | Per-batch retry ceiling before parking `FAILED`. |
| `--ext` / `--all-files` | `.pdf` | File selection. |
| `--hash` | off | Compute SHA-256 per file (integrity; slower). |
| `--dry-run` | off | Build ZIPs but don't submit. |

**Memory:** each in-flight ZIP is built in RAM, so peak driver memory is roughly
`--target-bytes` × `--max-inflight` (defaults ≈ 250 MB × 4 ≈ 1 GB). Lower either
flag if the driver host is memory-constrained.

**HTTP retries:** transient failures (5xx / network) are retried up to 6 times
per request with exponential backoff + jitter; 429s honor `Retry-After`; 401s
trigger one JWT refresh. This is separate from `--max-attempts`, which is the
per-batch ceiling across submissions.

## Known limitations

- **Oversize files (≥ 100 MB)** are routed to the single-document endpoint
  (with chunked transport if needed) instead of being packed into a batch ZIP,
  but still land in the **correct folder** — the file's path relative to
  `--root-dir` becomes the nested corpus folder, with the file name as the
  document title. Rare for typical PDFs.
- **No server-side content de-dup.** The ledger is the source of truth for
  "already done"; re-importing the same relative path **upversions** (no
  duplicate active document), so re-runs converge safely.
- **`job_id` is not pollable** for this endpoint (a known server quirk), so the
  driver verifies by corpus document **count**, not job status.
- **Abandoned chunked sessions.** When a chunked part upload fails mid-stream the
  batch is marked `FAILED` and re-run starts a *fresh* session; the partial one
  is left `PENDING` on the server. These are reclaimed by the server's
  stale-session GC (`purge_stale_chunked_uploads`), not by the driver — on a very
  large import with many transient failures, watch server chunked-session counts
  if the GC interval is long.

## Tests

```bash
python -m pytest scripts/bulk_import/tests/      # or:
python scripts/bulk_import/tests/test_batching.py
```
