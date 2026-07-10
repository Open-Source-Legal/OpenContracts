# Remote Ingest Worker

The remote ingest worker runs the **full OpenContracts ingestion pipeline**
(Docling parse + embeddings) on a beefy off-cluster host and streams the
finished documents -- PAWLs token layer, text layer, structural annotations,
relationships, embeddings, and any metadata you calculate -- into a corpus via
the [Worker Uploads](worker_uploads.md) REST API.

It is the tool for the "I have spare workstations and a 100k--1M document corpus
to populate" problem: the expensive parsing and enrichment happen on **your**
hardware, and the target instance just ingests the finished artifacts.

## When to Use It

- You want to **offload parsing and embedding** to your own machines instead of
  paying for it on the OpenContracts server.
- You have a **very large** local document tree (hundreds of thousands of files)
  to ingest resumably.
- You want each document to carry **calculated metadata and annotations**
  (detected dates, clause tags, typed metadata fields) produced by your own code.

### Versus the Bulk ZIP CLI

Both `scripts/bulk_import/` and `scripts/remote_ingest/` are CLI drivers for
large local corpora, but they offload different work:

| | Bulk ZIP driver (`scripts/bulk_import`) | Remote ingest worker (`scripts/remote_ingest`) |
|---|---|---|
| What it ships | **raw** PDFs (ZIP) | **fully-processed** documents |
| Who parses + embeds | the **server** | the **remote worker** (your hardware) |
| Offloads compute? | No | **Yes** |
| Endpoint | `/api/imports/zip-to-corpus/` | `/api/worker-uploads/documents/` |
| Pre-processing hook | -- | Yes (calc + inject metadata/annotations) |

Use the bulk ZIP driver when the server has spare capacity; use the remote
ingest worker when you want to throw your own hardware at ingestion.

## Faithful by Construction

The worker runs the **same Docling microservice image** and the **same
`DoclingParser` code** the server runs, and embeds against the **same
vector-embedder image**. So the result is indistinguishable from an in-cluster
ingestion:

- **PAWLs token layer** -- identical tokenization (no drift); the worker-upload
  path trusts these tokens verbatim.
- **Text layer** -- rebuilt from the shipped PAWLs with the same
  `plasmapdf.build_translation_layer` the server uses.
- **Structural annotations + relationships** -- produced by the real parser; the
  worker-upload path materializes a `StructuralAnnotationSet` and subtree-group
  relationships exactly as in-cluster ingestion does.
- **Embeddings** -- same model, same inputs (full text for the document,
  `rawText` per annotation).
- **Thumbnail** -- regenerated server-side from the uploaded PDF.

## How It Works

A small **docker-compose bundle** runs on the remote host: the Docling parser
microservice, the vector embedder microservice, and a worker driver. The driver
is a resumable, per-document CLI:

1. `plan` scans the PDF tree into a SQLite ledger.
2. `run` parses each PDF (real `DoclingParser`), runs your enrichers, computes
   embeddings, and `POST`s a `multipart/form-data` payload (PDF + metadata JSON)
   to `/api/worker-uploads/documents/` with `Authorization: WorkerKey <token>`.
3. `verify` polls the target for each upload's terminal status.

It streams per document (no archive is ever built), runs a thread pool of
workers, and paces itself against the target's worker-upload backlog. The ledger
makes the whole run crash-resumable -- re-running `run` skips finished documents.
The worker needs **no database access** to the target: it only makes outbound
HTTPS calls to the worker-upload endpoint.

## Setup

### Prerequisites on the target instance

Worker uploads are ingested **asynchronously**: the endpoint only stages each
upload (HTTP 202), and a Celery task (`process_pending_uploads`) turns it into a
Document. So the target **must** be running:

- a **Celery worker** that consumes the `worker_uploads` queue **and** the
  default `celery` queue (the latter generates thumbnails). The stock compose
  images already do this -- the worker starts with `-Q celery,worker_uploads`.
- **Celery Beat**, which schedules the periodic `process_pending_uploads` drain
  and `recover_stalled_uploads` (re-queues uploads stuck in `PROCESSING`).

If nothing drains the `worker_uploads` queue, uploads accumulate as `PENDING`
forever and **no documents are ever created** -- the worker still reports success
(202 / `UPLOADED` in its ledger), so this failure is silent. See
[Troubleshooting](#troubleshooting), and
[Celery Configuration for Worker Uploads](worker_celery_setup.md) for the full
infra reference (queues, Beat, scaling, verification commands).

### 1. On the server -- mint a corpus-scoped token (one command)

```bash
# mint_worker_token runs inside the Django container:
docker compose -f production.yml run --rm django \
    python manage.py mint_worker_token --corpus <CORPUS_PK> --worker-name <name>
```

This prints a one-time `OC_WORKER_TOKEN` **and** the `OC_CORPUS_ID` it is bound
to (the remote host can never target another corpus). The corpus must already
exist. See [Worker Uploads](worker_uploads.md) for the token model.

### 2. On the remote host -- run the bundle (a few commands)

```bash
git clone <opencontracts repo>          # the worker runs the real parser code
cd opencontracts/scripts/remote_ingest

export OC_TARGET_URL=https://opencontracts.example.com
export OC_WORKER_TOKEN=<token from step 1>
export OC_CORPUS_ID=<corpus id from step 1>   # informational; the token enforces it
export OC_DATA_DIR=/data/pdfs                 # your directory tree of PDFs
# One value, wired by the bundle to BOTH the embedder service and the worker.
# The embedder authorizes by comparing it to the request's X-API-Key header
# (its built-in default is "abc123"); a mismatch yields HTTP 401 on embedding.
export VECTOR_EMBEDDER_API_KEY=<any-value>

docker compose -f remote_worker.yml up -d --build docling-parser vector-embedder
docker compose -f remote_worker.yml run --rm worker plan
docker compose -f remote_worker.yml run --rm worker run --max-workers 8
docker compose -f remote_worker.yml run --rm worker verify
```

The directory tree under `OC_DATA_DIR` is mirrored into the corpus's folder
structure. See [`scripts/remote_ingest/README.md`](https://github.com/Open-Source-Legal/OpenContracts/blob/main/scripts/remote_ingest/README.md)
for the full flag reference (`--no-embeddings`, `--flat`, `--limit`,
`--queue-high/--queue-low`, `--max-attempts N` (retries before a doc is PARKED),
`--insecure`, etc.).

### GPU acceleration (optional)

The slow step is the Docling parse. If the remote host has a GPU, merge the
[accelerated images](https://github.com/Open-Source-Legal/OpenContracts/blob/main/compose/accelerated/README.md)
override to run the parser + embedder on it (auto-detects CUDA / ROCm / Intel
XPU·NPU). Vendor embedder overlays require the requested accelerator so a driver
or device-passthrough error is visible instead of silently reverting to CPU.

`remote_worker.accel.yml` is CPU-safe and contains no device mounts. Merge the
matching reusable vendor overlay after it: `accel.intel.yml`,
`accel.nvidia.yml`, or `accel.amd.yml`. Intel NPU hosts can additionally merge
`accel.intel-npu.yml`; CPU-only hosts can use `accel.cpu.yml`. The Docling
speedup is hardware-specific, so **benchmark your host** with
`compose/accelerated/bench_parse.py`. Full details:
[`scripts/remote_ingest/README.md`](https://github.com/Open-Source-Legal/OpenContracts/blob/main/scripts/remote_ingest/README.md#gpu-acceleration-recommended-on-beefy-workstations)
and the [accelerated images README](https://github.com/Open-Source-Legal/OpenContracts/blob/main/compose/accelerated/README.md).

```bash
export RENDER_GID=$(stat -c '%g' /dev/dri/renderD128)   # Intel/AMD; not needed for NVIDIA
docker compose \
  -f remote_worker.yml \
  -f remote_worker.accel.yml \
  -f ../../compose/accelerated/accel.intel.yml \
  up -d --build docling-parser vector-embedder
docker compose \
  -f remote_worker.yml \
  -f remote_worker.accel.yml \
  -f ../../compose/accelerated/accel.intel.yml \
  run --rm worker run --max-workers 8
```

On CPU, the stock `docling-parser` handles **one parse at a time** and each
scanned-PDF OCR can take minutes and use **3-6 GB RAM**. Size `--max-workers` (and
any parser replicas) to available RAM, not CPU count -- over-parallelizing OCR on
CPU can exhaust memory. Do **not** run the stock parser image with `uvicorn
--workers > 1` (its OCR engine races on startup and crashes).

## Pre-processing / Enrichment: Calculate and Inject Metadata + Annotations

Often you want each document to carry **more than the parser produces**: typed
metadata, a document-type label, or extra annotations you calculate (detected
dates, parties, clauses, an LLM classification). The worker runs a pluggable
**enrichment stage** after parsing and *before* embedding + upload -- so anything
you inject is embedded and ingested like the parser's own output.

An enricher is a callable `(EnricherContext) -> Enrichment`, wired in with
`--enricher module:function` (repeatable) or the `OC_ENRICHERS` env var. The
context provides correctness helpers (`find_token_matches(regex)`,
`token_annotation(label, match)`) that build valid `annotation_json`, and the
worker **validates** every enrichment before upload so a buggy enricher fails the
document loudly instead of shipping a broken annotation.

```python
import re
from enrichers import Enrichment, EnricherContext, label_def, metadata_field, TOKEN_LABEL

def enrich(ctx: EnricherContext) -> Enrichment:
    enr = Enrichment(
        # Typed corpus metadata (Column/Datacell -- the document metadata grid):
        metadata=[
            metadata_field("Contract Number", "058000"),                 # STRING (inferred)
            metadata_field("Effective Date", "2025-01-01", data_type="DATE"),
        ],
        # Label definitions for any annotations we inject:
        annotation_labels={"EFFECTIVE_DATE": label_def("EFFECTIVE_DATE", TOKEN_LABEL)},
    )
    # Inject token annotations for matched text (faithful annotation_json built for you):
    for m in ctx.find_token_matches(r"\b\w+ \d{1,2}, \d{4}\b"):
        enr.annotations.append(ctx.token_annotation("EFFECTIVE_DATE", m))
    return enr
```

```bash
docker compose -f remote_worker.yml run --rm worker run --enricher my_enrichers:enrich
```

What an `Enrichment` can carry (all optional, additive):

| Field | Effect |
|---|---|
| `metadata` (`metadata_field`) | **typed corpus metadata** -- `Column`/`Datacell` values (the UI's document metadata grid, successor to legacy metadata annotations). Corpus-scoped, typed, queryable. |
| `custom_meta` (dict) | a freeform JSON blob on `Document.custom_meta` (not the typed schema) |
| `doc_labels` (+ defs) | apply `DOC_TYPE_LABEL`s |
| `annotations` (+ labels) | inject token/span annotations; they get embedded + rendered |
| `relationships` | annotation-to-annotation relationships |
| `title` / `description` | override document title/description |

### Two metadata mechanisms

OpenContracts has two ways to attach document metadata, and the enrichment stage
supports both:

- **Typed corpus metadata** -- the `Fieldset` -> `Column` -> `Datacell` system
  (see [Metadata Fields](../metadata/metadata_fields.md)). This is what the UI
  shows as document metadata, it is typed and queryable, and it is the preferred
  mechanism. Emit it with `metadata_field(name, value, data_type=...)`. On ingest
  the worker get-or-creates a manual-entry `Column` (by name) in the corpus
  metadata schema and sets the document's value, type-validated against the
  column. Supported types: `STRING, TEXT, BOOLEAN, INTEGER, FLOAT, DATE
  (YYYY-MM-DD), DATETIME (ISO), URL, EMAIL, CHOICE, MULTI_CHOICE, JSON`.
- **`Document.custom_meta`** -- a freeform JSON blob for ad-hoc data that does not
  belong in the corpus schema.

## Security

- **Auth**: a corpus-scoped `CorpusAccessToken` sent as
  `Authorization: WorkerKey <token>` over TLS. The corpus is fixed by the token
  binding -- the remote host cannot reach another corpus or any other API.
- **No database access**: the worker only makes outbound HTTPS calls to
  `/api/worker-uploads/`.
- **No inbound ports**: the worker initiates all connections.
- **Enricher trust model**: enrichers are first-party Python you write and run on
  your own worker host; do not load enricher modules you did not write.

For production, run the target behind a reverse proxy with `limit_req` for hard
rate limiting (the per-token limit is best-effort).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `run` reports success (HTTP 202) but the ledger stays at `UPLOADED` (never `COMPLETED`), `verify` reports docs still-processing forever, **no documents appear**, and `worker status` shows the target backlog stuck | No Celery worker is consuming the `worker_uploads` queue on the **target** (uploads stage as `PENDING` forever). | Start the target's Celery worker (`-Q celery,worker_uploads`) and Beat -- see [Prerequisites](#prerequisites-on-the-target-instance). |
| Docs `FAILED` with `401 ... /embeddings` (or land with no embeddings) | `VECTOR_EMBEDDER_API_KEY` mismatch between the worker and the embedder service (the embedder checks `X-API-Key`, default `abc123`). | Export the **same** `VECTOR_EMBEDDER_API_KEY` before bringing up the bundle so it reaches both services; recreate the embedder if you change it. |
| `run` gets an opaque **HTTP 400** from the target (empty body) and marks docs failed | `OC_TARGET_URL`'s host is not in the target's `DJANGO_ALLOWED_HOSTS` (Django rejects the `Host` header). | Add the host to the target's `DJANGO_ALLOWED_HOSTS`. (In production the real hostname is already listed; this bites local/testing targets.) |
| Parsing is very slow / the host runs out of memory under load | On CPU, each Docling OCR parse is serial and uses 3-6 GB RAM. Too-high `--max-workers` (or too many parser replicas) exhausts RAM/swap. | Lower `--max-workers`, add parser replicas only up to available RAM, or use [GPU acceleration](#gpu-acceleration-optional). |
| A few uploads stay `PROCESSING` after a worker restart/crash | Uploads were claimed but not finished. | `recover_stalled_uploads` (Beat-scheduled) re-queues them after `WORKER_UPLOAD_STALE_MINUTES` (default 15); ensure Beat is running. |
