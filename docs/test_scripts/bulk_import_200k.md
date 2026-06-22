# Test: Bulk PDF import driver (`scripts/bulk_import/oc_bulk_import.py`)

## Purpose

Verify, end-to-end against a local stack, that the resumable bulk-import driver:

1. mirrors a local folder tree into a corpus via `POST /api/imports/zip-to-corpus/`,
2. drives every document through the parse pipeline (PAWLs + embeddings),
3. resumes after a crash without creating duplicate documents, and
4. paces itself against the corpus parse backlog (backpressure).

These steps are the basis for a future automated integration test.

## Prerequisites

- Local stack up: `docker compose -f local.yml up` (Django on `:8000`, Celery
  worker, Docling/parser service reachable).
- A superuser with a known password (see CLAUDE.md "Authenticated Playwright
  Testing" for setting one), e.g. `admin` / `testpass123`.
- `pip install requests` in the environment running the driver.
- A small sample tree of PDFs with nested folders, e.g.:
  ```
  /tmp/sample_pdfs/
    contracts/2024/a.pdf
    contracts/2025/b.pdf
    memos/c.pdf
  ```
  (Reuse `opencontractserver/tests/fixtures/sample.pdf` copied into that layout.)

## Steps

1. **Unit tests (no server):**
   ```bash
   python scripts/bulk_import/tests/test_batching.py
   ```

2. **Create a corpus and capture its id:**
   ```bash
   export OC_API_BASE=http://localhost:8000
   export OC_USERNAME=admin OC_PASSWORD=testpass123
   export OC_CORPUS_ID=$(python scripts/bulk_import/oc_bulk_import.py \
       create-corpus --title "Bulk Import Smoke Test")
   echo "corpus=$OC_CORPUS_ID"
   ```

3. **Plan and inspect (no upload):**
   ```bash
   python scripts/bulk_import/oc_bulk_import.py plan \
       --root-dir /tmp/sample_pdfs --ledger /tmp/ingest.db
   ```

4. **Dry-run (build ZIPs, no submit):**
   ```bash
   python scripts/bulk_import/oc_bulk_import.py run \
       --root-dir /tmp/sample_pdfs --ledger /tmp/ingest.db --dry-run
   ```

5. **Real run with tiny batches to force multiple ZIPs + backpressure:**
   ```bash
   python scripts/bulk_import/oc_bulk_import.py run \
       --root-dir /tmp/sample_pdfs --ledger /tmp/ingest.db \
       --target-files 1 --max-inflight 2 --queue-high 1 --queue-low 0
   ```

6. **Crash-resume:** interrupt step 5 with `Ctrl-C` mid-run, then re-run the
   exact same command. Confirm it skips already-`SUBMITTED` batches.

7. **Watch + reconcile:**
   ```bash
   python scripts/bulk_import/oc_bulk_import.py status --ledger /tmp/ingest.db
   # wait until processing drains, then:
   python scripts/bulk_import/oc_bulk_import.py verify --ledger /tmp/ingest.db
   ```

## Expected Results

- **Step 1:** all unit tests pass.
- **Step 3:** logs `Planned N file(s)`, the right ZIP/oversize split, and the
  largest-ZIP summary. `/tmp/ingest.db` exists.
- **Step 4:** each batch logs `dry-run (...)`; no documents appear in the corpus.
- **Step 5:** each batch logs `OK ... (job ...)`. In the OpenContracts UI the
  corpus shows the **folder tree mirrored** (`contracts/2024`, `contracts/2025`,
  `memos`) with the PDFs inside, each parsing then completing.
- **Step 6:** the re-run logs `Nothing to submit` or only re-sends unfinished
  batches; the corpus document **count does not double** (same paths upversion).
- **Step 7:** `status` shows live `documentStats`; once `processingCount` is `0`,
  `verify` logs `Reconciled: marked N batch(es) VERIFIED. Import complete.` and
  exits 0.

### Verify document count via GraphQL (optional)

```bash
curl -s -X POST http://localhost:8000/graphql/ \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=<session-key>" \
  -d "{\"query\":\"query{documentStats(inCorpusWithId:\\\"$OC_CORPUS_ID\\\")\
{totalDocs processingCount processedCount}}\"}" | python3 -m json.tool
```

## Cleanup

```bash
rm -f /tmp/ingest.db
# Delete the test corpus (UI, or deleteCorpus mutation) to remove its documents.
```
