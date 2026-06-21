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

Auth is a JWT from the `tokenAuth` mutation; the driver refreshes it
automatically on 401, so multi-day runs keep going.

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

## Known limitations

- **Oversize files (≥ 100 MB)** are uploaded via the single-document endpoint
  and land at the **corpus root** (not foldered), titled with their relative
  path. Rare for typical PDFs.
- **No server-side content de-dup.** The ledger is the source of truth for
  "already done"; re-importing the same relative path **upversions** (no
  duplicate active document), so re-runs converge safely.
- **`job_id` is not pollable** for this endpoint (a known server quirk), so the
  driver verifies by corpus document **count**, not job status.

## Tests

```bash
python -m pytest scripts/bulk_import/tests/      # or:
python scripts/bulk_import/tests/test_batching.py
```
