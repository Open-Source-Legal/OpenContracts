# Remote Ingest Worker

Run the OpenContracts ingestion pipeline (Docling parse + embeddings) on a
beefy **off-cluster** host and stream **fully-processed, faithfully-mirrored**
documents into a target OpenContracts corpus — without giving the remote host
any access to the target's database.

This is the tool for the "I have spare workstations and a 100k–1M document
corpus to populate" problem. The expensive work (parsing + enrichment) happens
on your hardware; the target instance just ingests the finished artifacts.

---

## Why this is different from `scripts/bulk_import`

| | `bulk_import/oc_bulk_import.py` | `remote_ingest/oc_remote_ingest.py` (this tool) |
|---|---|---|
| What it ships | **raw** PDFs (ZIP) | **fully-processed** documents (PAWLs, text, annotations, relationships, embeddings) |
| Who parses | the **server** (`/api/imports/zip-to-corpus/`) | the **remote worker** (this host) |
| Offloads compute? | ❌ no — server still parses + embeds | ✅ yes — parse + embed run remotely |
| Endpoint | `/api/imports/zip-to-corpus/` | `/api/worker-uploads/documents/` |

Use `bulk_import` when the server has spare capacity. Use `remote_ingest` when
you want to throw your own hardware at ingestion and keep the target instance
cheap.

## Faithful by construction

The worker runs the **same Docling microservice image** and the **same
`DoclingParser` code** the server runs, and embeds against the **same
vector-embedder image**. So:

- **PAWLs token layer** — identical tokenisation (no drift; the worker-upload
  path trusts these tokens verbatim, and they *are* what the server would
  produce).
- **Text layer (`content`)** — rebuilt from the shipped PAWLs with the same
  `plasmapdf.build_translation_layer` the server's `save_parsed_data` uses.
- **Structural annotations + relationships** — produced by the real parser; the
  server's worker-upload path then materialises a `StructuralAnnotationSet` and
  subtree-group relationships exactly as in-cluster ingestion does.
- **Embeddings** — same 384-dim model, same inputs (full text for the document,
  `rawText` per annotation).
- **Thumbnail** — regenerated server-side from the uploaded PDF.

The net result: a document ingested through this worker is indistinguishable
from one ingested in-cluster.

---

## Setup

> **Target prerequisite (easy to miss):** worker uploads are ingested
> asynchronously — the endpoint only stages each upload (HTTP 202) and a Celery
> task creates the Document. The target instance **must** run a Celery worker on
> the `worker_uploads` queue **and** the default `celery` queue (thumbnails), plus
> Celery Beat (periodic drain + stalled-upload recovery). The stock compose images
> already do this (`-Q celery,worker_uploads`). **If nothing drains that queue,
> uploads stage as `PENDING` forever and no documents are created** — the worker
> still reports success, so the failure is silent. See [Troubleshooting](#troubleshooting).

### 1. On the target server — mint a corpus-scoped token (one command)

```bash
# mint_worker_token runs inside the Django container:
docker compose -f production.yml run --rm django \
    python manage.py mint_worker_token --corpus <CORPUS_PK> --worker-name <name>
```

This prints a one-time `OC_WORKER_TOKEN` (and the `OC_CORPUS_ID`). The token is
bound to exactly one corpus — the remote host can never target another. Only the
SHA-256 hash is stored server-side; copy the plaintext now.

> The corpus must already exist (create it in the UI or via the API). To cap
> throughput, pass `--rate-limit <uploads/min>`; to expire the token, pass
> `--expires-days <N>`.

### 2. On the remote worker host — run the bundle (a few commands)

```bash
git clone <opencontracts repo>           # the worker runs the real parser code
cd opencontracts/scripts/remote_ingest

export OC_TARGET_URL=https://opencontracts.example.com
export OC_WORKER_TOKEN=<token from step 1>
export OC_DATA_DIR=/data/pdfs            # your directory tree of PDFs
# The bundle wires this SAME value to both the embedder service and the worker.
# The embedder authorizes by comparing it to the request's X-API-Key header
# (default "abc123"); a mismatch -> HTTP 401 on every embed. Any value works as
# long as both sides match — which the bundle guarantees from this one var.
export VECTOR_EMBEDDER_API_KEY=<any-value>

# Start the parser + embedder microservices (one-time, ~minutes to pull):
docker compose -f remote_worker.yml up -d --build docling-parser vector-embedder

# Plan (scan the tree into the resumable ledger), then run:
docker compose -f remote_worker.yml run --rm worker plan
docker compose -f remote_worker.yml run --rm worker run --max-workers 8

# Confirm everything landed:
docker compose -f remote_worker.yml run --rm worker verify
docker compose -f remote_worker.yml run --rm worker status
```

That's it. The directory tree under `OC_DATA_DIR` is mirrored into the corpus's
folder structure (each PDF's path becomes its folder path). `run` is resumable —
if it's interrupted, just run it again; finished documents are skipped.

### GPU acceleration (recommended on beefy workstations)

The slow step is the Docling parse. If the host has a GPU, merge
`remote_worker.accel.yml` and the matching vendor overlay to run the parser +
embedder on it. The common override supplies the locally built
[accelerated images](../../compose/accelerated/README.md); the vendor overlay
supplies only the correct device access and torch wheel family.

Intel example:

```bash
export RENDER_GID=$(stat -c '%g' /dev/dri/renderD128)
docker compose \
  -f remote_worker.yml \
  -f remote_worker.accel.yml \
  -f ../../compose/accelerated/accel.intel.yml \
  up -d --build docling-parser vector-embedder
```

Use `accel.nvidia.yml` on NVIDIA. On AMD, set `VIDEO_GID` from `/dev/kfd` and
`RENDER_GID` from `/dev/dri/renderD128`, then use `accel.amd.yml`. Intel hosts
with `/dev/accel/accel0` can additionally merge `accel.intel-npu.yml`.

Pass the same complete `-f` list to `plan`, `run`, `verify`, and `status` so the
worker keeps using the same backend. For example:

```bash
docker compose \
  -f remote_worker.yml \
  -f remote_worker.accel.yml \
  -f ../../compose/accelerated/accel.intel.yml \
  run --rm worker run --max-workers 8
```

No vendor file requires hand-editing. The common override alone, or with
`accel.cpu.yml`, is safe on a CPU-only host. **Benchmark Docling on your GPU**
with `compose/accelerated/bench_parse.py`; its speedup is hardware-specific.

---

## Subcommands

| Command | What it does |
|---|---|
| `plan` | Scan `OC_DATA_DIR` and record every PDF in the SQLite ledger. No network, no parsing. |
| `run` | Parse + embed + upload all `PENDING`/`FAILED` docs. Resumable, concurrent, back-pressure-aware. |
| `verify` | Poll the target for each uploaded doc's terminal status; mark `COMPLETED`/`FAILED`. |
| `status` | Print ledger counts + the target's live worker-upload backlog. |

Useful flags (append after the subcommand):

- `--max-workers N` — parse/upload concurrency (default 4). The Docling parse is
  the bottleneck. On CPU each OCR parse is serial and uses **3-6 GB RAM**, so size
  this to **available RAM** (and parser replicas), not raw CPU count —
  over-parallelizing OCR on CPU can exhaust memory/swap. On a capable GPU, scale up.
- `--no-embeddings` — skip remote embedding and let the **server** embed instead
  (the worker still offloads parsing). By default the worker embeds and the
  server is told not to re-embed.
- `--limit N` — (on `plan`) cap how many documents are recorded; handy for a
  trial run.
- `--flat` — do not mirror the directory tree into corpus folders.
- `--queue-high / --queue-low` — back-pressure thresholds against the target's
  worker-upload backlog (pause when `PENDING+PROCESSING` exceeds high, resume
  below low).
- `--enricher MODULE:CALLABLE` — run a pre-processing enricher (repeatable; also
  `OC_ENRICHERS`, comma-separated). See below.
- `--max-attempts N` — retries per document before it is PARKED (default 5).
- `--insecure` — disable TLS verification (testing only; e.g. a self-signed or
  local HTTPS target).

---

## Pre-processing / enrichment — inject metadata + annotations

Often you want each document to carry **more than the parser produces**: a
structured metadata blob, a document-type label, or extra annotations you
calculate (detected dates, parties, clauses, regex/NER hits, an LLM
classification). The worker runs a **pluggable enrichment stage** after parsing
and *before* embedding + upload — so anything you inject is embedded and
ingested exactly like the parser's own output.

An enricher is a callable `(EnricherContext) -> Enrichment`. Point the worker at
it with `--enricher module:function` (repeatable) or `OC_ENRICHERS`. The context
gives you the parsed token layer + text and **correctness helpers** so injected
annotations are faithful (valid `annotation_json` — bounds, token indices,
`rawText`). The worker **validates** every enrichment before upload, so a buggy
enricher fails that document loudly (in the ledger) instead of silently shipping
a broken annotation.

```python
# my_enrichers.py  (mount it into the worker, or drop it next to the driver)
import re
from enrichers import Enrichment, EnricherContext, label_def, TOKEN_LABEL, DOC_TYPE_LABEL

def enrich(ctx: EnricherContext) -> Enrichment:
    enr = Enrichment(
        # 1. structured metadata  -> Document.custom_meta
        custom_meta={"jurisdiction": "TX"},
        # 2. a document-type label -> DOC_TYPE_LABEL
        doc_labels=["contract:construction"],
        doc_label_defs={"contract:construction": label_def("contract:construction", DOC_TYPE_LABEL)},
        # 3. label definitions for any annotations we inject
        annotation_labels={"EFFECTIVE_DATE": label_def("EFFECTIVE_DATE", TOKEN_LABEL)},
    )
    # 4. inject token annotations for matched text (faithful annotation_json built for you)
    for m in ctx.find_token_matches(r"\b\w+ \d{1,2}, \d{4}\b"):
        enr.annotations.append(ctx.token_annotation("EFFECTIVE_DATE", m))
    return enr
```

```bash
docker compose -f remote_worker.yml run --rm worker run \
    --enricher my_enrichers:enrich
```

What an `Enrichment` can carry (all optional, additive):

| Field | Effect on the document |
|---|---|
| `metadata` (via `metadata_field`) | **typed corpus metadata** — Column/Datacell values (the UI's document metadata, successor to legacy "metadata annotations"). Corpus-scoped, typed, queryable. |
| `custom_meta` (dict) | merged onto `Document.custom_meta` (a freeform JSON blob — not the typed metadata schema) |
| `title` / `description` | override the document title/description |
| `doc_labels` + `doc_label_defs` | apply DOC_TYPE_LABELs |
| `annotations` + `annotation_labels` | inject token (or span) annotations; they get embedded + rendered |
| `relationships` | annotation-to-annotation relationships (reference annotation `id`s) |

### Typed metadata (the metadata system, not `custom_meta`)

OpenContracts has two metadata mechanisms: the freeform `Document.custom_meta`
JSON blob, and the **typed corpus metadata** system (`Fieldset` → `Column` →
`Datacell` — what the UI shows in the document metadata grid). Prefer the latter
for real metadata: it's corpus-scoped, typed, validated, and queryable.

Emit typed metadata with `metadata_field(name, value, data_type=…)`:

```python
from enrichers import Enrichment, metadata_field

def enrich(ctx):
    return Enrichment(metadata=[
        metadata_field("Contract Number", "058000"),                 # STRING (inferred)
        metadata_field("Effective Date", "2025-01-01", data_type="DATE"),
        metadata_field("Pages", 6),                                  # INTEGER (inferred)
        metadata_field("Contract Type", "Service",
                       data_type="CHOICE",
                       validation_config={"choices": ["Service", "NDA"]}),
    ])
```

On ingest the worker get-or-creates a manual-entry `Column` (by name) in the
corpus's metadata schema and sets the document's `Datacell` value. Data types:
`STRING, TEXT, BOOLEAN, INTEGER, FLOAT, DATE (YYYY-MM-DD), DATETIME (ISO), URL,
EMAIL, CHOICE, MULTI_CHOICE, JSON`. Values are type-checked both client-side
(`validate_enrichment`) and server-side (`Datacell.clean`) — a mismatch fails the
document rather than landing a bad value. The first document to use a column name
defines its type for the corpus.

Context helpers (`EnricherContext`):

- `ctx.export` / `ctx.content` — the parsed `OpenContractDocExport` + text layer.
- `ctx.find_token_matches(regex)` — regex over each page's token text, returns the
  matching token runs (`TokenMatch`).
- `ctx.token_annotation(label, match)` — build a valid TOKEN_LABEL annotation
  (union bounds + token indices + `rawText`) for a match. Injected annotation
  `id`s are assigned automatically (`enr-0`, ...) so they never collide with the
  parser's, and they participate in embeddings + relationships.

Three runnable examples ship in `example_enrichers.py` (filename → metadata,
detected dates → annotations, content → document-type label). Use them directly:
`--enricher example_enrichers:effective_date_annotations`.

---

## Security

- **Auth**: a `CorpusAccessToken` sent as `Authorization: WorkerKey <token>` over
  TLS. The token is corpus-scoped and the corpus is fixed by the binding — the
  remote host cannot reach another corpus or any other API.
- **No database access**: the worker never connects to the target's database. It
  only makes outbound HTTPS calls to `/api/worker-uploads/`.
- **No inbound ports**: the worker initiates all connections.
- **Revocation**: deactivate the token (or its worker account) server-side and
  in-flight + future uploads stop.

For production, run the target behind a reverse proxy with `limit_req` for hard
rate limiting (the per-token limit is best-effort).

---

## How it works (per document)

1. Read the PDF bytes.
2. `DoclingParser.parse_pdf_bytes(bytes)` → `OpenContractDocExport` (PAWLs,
   structural annotations, relationships) — the real parser, no database.
3. Rebuild the text layer from the PAWLs (`build_translation_layer`).
4. Embed the document text + each annotation's `rawText` against the
   vector-embedder.
5. POST `multipart/form-data` (the PDF + a metadata JSON) to
   `/api/worker-uploads/documents/`.
6. The server stages the upload and a Celery worker ingests it: creates the
   document, imports annotations/relationships, stores the embeddings,
   materialises the structural set, and regenerates the thumbnail.

The ledger (`/ledger/ledger.sqlite3`, a named volume) records each document's
state so the whole run is crash-resumable.

---

## Requirements on the remote host

- Docker + Docker Compose.
- The OpenContracts repo (the worker image is built from it).
- Outbound HTTPS to the target.
- RAM for the Docling microservice plus the worker. The service idles at ~2 GB,
  but **each in-flight OCR parse adds ~3-6 GB**, so budget for
  `~3-6 GB x concurrent parses` (≈ `--max-workers`, capped by parser replicas) on
  CPU. On a GPU, VRAM is the constraint instead.

The driver itself runs inside the OpenContracts image and uses
`config.settings.remote_worker`, which points Django at a throwaway SQLite file
so the worker needs **no Postgres and no Redis**.

---

## Troubleshooting

The canonical troubleshooting table — embedder `401`, `DJANGO_ALLOWED_HOSTS`
`400`, the silent "no Celery worker" stall, OCR RAM exhaustion, and stalled
`PROCESSING` uploads — lives in
[Remote Ingest Worker → Troubleshooting](../../docs/upload_methods/remote_ingest_worker.md#troubleshooting).
Only the symptom unique to this script driver is listed here:

| Symptom | Likely cause | Fix |
|---|---|---|
| `nothing to do` on `run` after merging the accel override | You ran `plan` with a different Compose file set, or never ran `plan`. | Run `plan` with the same base, common accelerator, and vendor `-f` files you use for `run`. |
