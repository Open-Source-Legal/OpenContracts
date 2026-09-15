# Remote Ingest Worker

Run the OpenContracts ingestion pipeline (PDF/DOCX/TXT parsing + embeddings) on a
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

The worker uses the same parser adapters as the server, with explicit local
settings. With equivalent settings, service versions and source metadata:

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
- **Thumbnail** — regenerated server-side from the uploaded source document (asynchronously).

---

## Parser selection and local settings

Docling PDF remains the default. To enable PDF, DOCX and TXT:

```bash
export OC_PARSER_CONFIG=/app/scripts/remote_ingest/parser-config.example.json
docker compose -f remote_worker.yml up -d docling-parser docxodus-parser vector-embedder
docker compose -f remote_worker.yml run --rm worker plan --extensions .pdf,.docx,.txt
docker compose -f remote_worker.yml run --rm worker run
```

The [example config](parser-config.example.json) maps canonical MIME types to
parser class paths and supplies optional settings by full class path.
`--parser-config` overrides `OC_PARSER_CONFIG`; the file must be mounted inside
the worker. Settings precedence is schema defaults, declared environment
variables, then JSON. All selected parsers are validated before processing.
Target admin/GUI settings are independent and are never fetched.

For Warp PDF, change the PDF mapping to
`opencontractserver.pipeline.parsers.warp_ingest_parser.WarpIngestParser` and
start `warp-ingest`. `WARP_INGEST_API_KEY` configures both worker and service.
TXT paragraph/window chunking needs no service; the sentence default needs
spaCy and its model. The worker starts no services automatically, and
`--no-embeddings` also removes the need for the vector embedder.

See the public [parser configuration reference](../../docs/upload_methods/remote_ingest_worker.md#parser-selection-and-local-settings)
for settings, dependencies, MIME detection, annotation parity and provenance.
`parser_version="1.0"` follows structural-set convention, not a discovered
service version. Keep credentials in environment variables, outside config files.

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
export OC_PARSER_IDENTITY=docling-deployment-v1   # pin/bump with your service revision
export OC_EMBEDDING_IDENTITY=embedding-model-v1  # pin/bump with your model revision

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
| `verify` | Verify the whole ledger; poll uploaded receipts and return a completion, outstanding, failure or unavailable result. |
| `status` | Print ledger counts + token-scoped outstanding uploads (or `unknown`). |

Useful flags (append after the subcommand):

- `--max-workers N` — parse/upload concurrency (default 4). The Docling parse is
  the bottleneck. On CPU each OCR parse is serial and uses **3-6 GB RAM**, so size
  this to **available RAM** (and parser replicas), not raw CPU count —
  over-parallelizing OCR on CPU can exhaust memory/swap. On a capable GPU, scale up.
- `--ledger-page-size N` — maximum rows read per ledger page by `run`/`verify`
  (default 256, must be positive). The submitted-but-unfinished future window is
  bounded separately at **2 × `--max-workers`**, including active workers.
- `--no-embeddings` — skip remote embedding and let the **server** embed instead
  (the worker still offloads parsing). By default the worker embeds and the
  server is told not to re-embed.
- `--limit N` — (on `plan`) stop after recording N **new** documents; existing
  ledger paths do not consume the limit. Zero means no cap.
- `--flat` — do not mirror the directory tree into corpus folders.
- `--queue-high / --queue-low` — token-scoped outstanding upload thresholds:
  pause above high, resume at/below low. See [Admission](#admission).
- `--enricher MODULE:CALLABLE` — run a pre-processing enricher (repeatable; also
  `OC_ENRICHERS`, comma-separated). See below.
- `--max-attempts N` — retries per document before it is PARKED (default 5).
- `--insecure` — disable TLS verification (testing only; e.g. a self-signed or
  local HTTPS target).

### Verification contract

`verify` covers **every row in the ledger**, including work never uploaded and
failures from earlier passes. It polls each `UPLOADED` receipt once, persists valid
`COMPLETED`/`FAILED` responses, then decides its exit from final ledger state and
any unavailable observations. It does not poll the unrelated token backlog.

| Exit | Outcome | Meaning |
|---|---|---|
| `0` | `complete` / `empty` | Every row is `COMPLETED`; an empty ledger is an explicit successful no-op. |
| `1` | `outstanding` | Local `PENDING` work or receipts still `PENDING`/`PROCESSING`. |
| `2` | `failed` | `FAILED`, `PARKED`, `AMBIGUOUS` or `CONFLICT` work needs retry/reconciliation. |
| `3` | `unable_to_verify` | At least one receipt is unavailable/malformed/missing, or a ledger state is unknown. |

For mixed results, `3` takes precedence over `2`, then `1`. Codes `0`/`1`/`2`
follow the bulk-import convention where applicable. Repeating verification keeps
reporting unresolved failures and preserves their receipt/error. HTTP 401/403,
404 (missing or inaccessible under this worker and corpus), 429, 5xx, transport errors,
and malformed responses have distinct reasons; none changes the receipt's ledger
state, attempts or diagnostic history. Correct the cause and rerun verification.

For automation, use `verify --json`. Standard output is **JSON Lines**, with one
`type: "document"` record per ledger row in path order, followed by one
`type: "summary"` record. Both carry `schema_version: 1`. Document records include
`rel_path`, final local `status`, `upload_id`, observed `receipt_status` (or null),
stable `reason`, diagnostic `detail`, and `http_status` (or null). Reasons include
`not_uploaded`, `receipt_pending`, `receipt_processing`, `failed`, `parked`,
`ambiguous_upload`, `source_conflict`, `missing_receipt`, `unauthorized`, `forbidden`,
`not_found`, `rate_limited`, `server_unavailable`, `network_error`, `invalid_request`,
`http_error`, `invalid_response`, `unknown_ledger_state`, and `completed`.
The final summary includes `scope: "whole_ledger"`, `outcome`, `exit_code`, `total`,
final status `counts`, `reason_counts`, `unavailable`, and
`completion_boundary: "worker_upload_transaction"`. Consumers must require the
final summary and successful process exit; a truncated stream is not completion.
Results stream in bounded pages rather than accumulating all documents in memory.

Success means that the worker-upload transaction committed document, annotations,
relationships, supplied embeddings, structural set and metadata writes. Thumbnail
generation, independently queued document embedding, indexing and search readiness
are asynchronous and are **not** established by the receipt or its `document_id`.

### Bounded traversal and resume

`plan` walks depth-first in filesystem order, yielding files without collecting
or sorting the tree (including within a large directory). Directory symlinks are
not traversed; matching file symlinks remain eligible. `--limit` stops discovery
immediately, but its selected subset is no longer globally sorted or guaranteed
to repeat after filesystem changes. Relative POSIX paths, case-insensitive
extension matching are unchanged. Replanning reconciles known paths by SHA-256
and can add the next limited set; changed existing paths do not consume `--limit`.

`run` and `verify` visit ledger rows in ascending relative-path order, in bounded
pages using a keyset cursor. Updating earlier rows cannot skip later rows, and a
document that fails stays behind the cursor until the next `run`. Totals use
separate SQL counts. Partial path indexes are added automatically to existing
ledgers; no manual migration is needed. Coordinator storage is proportional to
the page size plus the future window, independent of the document count. Active
documents still require memory for their source and preparation artifacts.

On **Ctrl-C**, `run` stops fetching/submitting rows, cancels queued futures, and
wakes workers paused by backpressure without consuming a retry attempt. At most
`--max-workers` already-started document/status calls finish before exit **130**;
their upload/failure transitions are saved. This is a graceful drain, so it can
take as long as those operations and their configured timeouts/retries. Run the
command again to resume unfinished rows.

Use one CLI invocation per ledger at a time, including `plan` and `verify`.
These cursors do not coordinate ownership across processes. Preparation checkpoints
recover local work; uncertain uploads stop in `AMBIGUOUS` until server lookup
establishes their receipt or absence. See the verification exit codes above.

### Admission

With `--queue-high > 0`, no document starts until both `PENDING` and `PROCESSING`
status requests succeed with nonnegative integer counts. One caller polls while
the others wait; a complete measurement is shared for 15 seconds after completion.
Missing, invalid, failed or stale measurements cannot admit work. After a reading
above high, admission resumes only with a fresh count at/below low. Enabled
watermarks require `0 <= queue_low <= queue_high`. `--queue-high <= 0` disables
admission polling, including the `run` summary; explicit `status` still polls.

Network/timeouts, 429, 5xx and malformed responses pause admission and retry with
exponential backoff (2–60 seconds before 50–100% jitter). Valid `Retry-After`
seconds or HTTP dates extend that delay, capped at 300 seconds; zero/invalid/past
values still use backoff. Other HTTP errors, including 401/403 and redirects,
stop `run` with exit **2** and a credential/configuration diagnostic. Neither
waiting nor status failure consumes document retry attempts. Ctrl-C wakes all
waiters and uses the bounded scheduler's graceful drain and exit **130** above.
If a poll itself aborts (for example, `SystemExit` in its worker), admission stops
and wakes all waiters before propagating the exception; `run` reports a safe
diagnostic and exits **2**.

These counts cover only the **exact authenticated token's** outstanding staged
uploads, including other producers using that token. They are two separate reads,
not an atomic snapshot, corpus-wide count or install-wide Celery capacity metric.
Already-admitted local workers (up to `--max-workers`) can still parse/upload after
a high reading, and other tokens are invisible: this is not a hard queue ceiling.
The server retains batch draining, row claims and stalled-upload recovery.
Upload status does not establish thumbnail, embedding or search readiness.

`status` displays a measured zero as `0`, and an unavailable/invalid count as
`unknown` with a safe reason. It does not print response bodies or request secrets.
Permanent status errors return exit **2**, as in `run`. Otherwise `status` remains
informational (exit **0**, including transient unknown status or ledger-only output);
its exit code does not certify availability or worker-upload completion.

### Durable preparation, identities, and source versions

The worker stores `<ledger>.artifacts/` beside SQLite, inside the existing
`/ledger` volume in Compose. Each relative path has a small manifest referencing
three content-digested JSON checkpoints:

| Stage | Durable result | Fingerprint inputs |
|---|---|---|
| Parse | Complete normalized export, reconstructed PDF text, original correlation IDs | Source SHA-256, filename, selected parser implementation, effective settings and operator revision |
| Enrich | Complete enriched export and the existing `MetadataOverlay` | Parse artifact digest, source paths, ordered enricher implementations and configuration identity |
| Embed | Complete document and eligible annotation vectors | Enriched artifact digest, client implementation, service URL, model identity, expected dimension |

Artifacts and manifests use atomic replacement and file/directory `fsync`. Each
stage is reusable only after its artifact is durable, its digest matches, and
its contract validates. Every stage passes through JSON on both fresh and resumed
runs, preserving annotation IDs, parent links, relationships, and embedding keys.
Missing, truncated, modified or incompatible artifacts recompute that stage and
its dependents. Changing only an embedding identity retains parsing/enrichment;
changing only enrichment retains parsing. Upload rejection or a server-reported
transaction failure likewise retains valid preparation.

Service revisions cannot be inferred from a mutable URL or the structural-set
`parser_version="1.0"` convention. Configure these stable, **non-secret** identities:

- `--parser-identity` / `OC_PARSER_IDENTITY`: required for service-backed parsers.
  Per-component strings in the parser JSON's `identities` object override this
  shared deployment identity. TXT needs no service identity, but use one when
  its spaCy model, imported chunker helpers, or other external dependencies change.
- `--embedding-identity` / `OC_EMBEDDING_IDENTITY`: required unless
  `--no-embeddings`; identify the deployed model/revision. Set
  `--embedding-dimension` / `OC_EMBEDDING_DIMENSION` (default 384) to match it.
- `--enricher-identity` / `OC_ENRICHER_IDENTITY`: required with enrichers; identify
  the entire chain's effective configuration, environment-dependent behavior,
  helper/model versions and external data. For pure example functions,
  `examples-v1` suffices. Enrichers must derive source content from `ctx.export`
  and `ctx.content`; `ctx.abs_path` is path metadata, not a stable file snapshot.

Keep identities unchanged across restarts of the same deployment; bump the
relevant identity when an output-affecting dependency changes. Python component
modules (including parser base classes), normalization and text reconstruction
implementations are hashed automatically. Arbitrary imported dependencies,
remote model changes and environment reads by enrichers cannot be discovered
automatically. Configuration is hashed in memory; manifests contain only opaque
keys and artifact digests, never credentials or raw settings. Artifacts contain
source-derived text/metadata and should have the same access controls as the source.

Embedding mode requires a finite numeric document vector and exactly one vector
of the configured, storage-supported dimension per annotation with nonblank
`rawText`. Missing/duplicate/string-colliding IDs, partial batches or malformed
vectors fail preparation before upload and never commit an embedding checkpoint.
Only explicit `--no-embeddings` omits the payload for server annotation fallback.
The remote worker uses the text embedding policy: document content is required;
annotations with empty/whitespace `rawText` are exempt. Its response normalization
is shared with `MicroserviceEmbedder`, without importing ORM persistence helpers.
A single response must be `{"embeddings": [number, ...]}` or
`{"embeddings": [[number, ...]]}`. Batch responses contain exactly one flat or
singleton-wrapped vector per nonblank input; missing and extra rows both fail.
Strings, booleans, nonfinite values and inconsistent dimensions are rejected.
Failures retain parse/enrichment checkpoints and follow normal retry/parking rules.

`plan` and preparation reconcile actual source bytes. A changed unaccepted source
resets `PENDING`/`FAILED`/`PARKED` to `PENDING`, clears stale receipts/errors and
retry exhaustion, and invalidates the old preparation chain on its next run.
The uploader sends the same immutable in-memory byte snapshot that was hashed
and parsed, even if the original path changes during preparation or cache reuse.
The ledger hash therefore describes the uploaded snapshot; replan to detect later
filesystem changes. A missing source fails before upload, even with cached work.

A change to an `UPLOADED`, `COMPLETED` or `AMBIGUOUS` source produces `CONFLICT`.
The old source hash, receipt/timestamps, and prior status are retained alongside
the observed conflict hash. The row is excluded from `run`; restoring the old
bytes and replanning restores its prior status. Otherwise an operator must
resolve an explicit server replace/new-document policy. There is no automatic
replacement or creation of another document for a conflicted path.

Upload state is separate from these checkpoints. Before POST, the worker durably
records a random `client_key`, a digest of source bytes plus semantic metadata and
preparation configuration, and `AMBIGUOUS`. It sends the key as `Idempotency-Key`.
Identical replays return the same receipt; changed bytes or metadata return HTTP
409. Requests without a key retain the legacy create-on-every-POST behavior.

On restart, `run` looks up ambiguous keys before doing preparation. A matching
receipt restores `UPLOADED`/`COMPLETED`; an explicit authenticated absence permits
replay with the same key and cached preparation. A timeout, malformed response,
404 (including an older server without lookup), or authorization failure leaves
the row ambiguous. `verify` can recover receipts but never replays uploads.
Legacy ambiguous rows without a client key still require manual reconciliation.

Receipts belong to a worker account and corpus. A replacement token for that
same pair can list, look up and retry old receipts, including after the original
token is deleted. Other workers cannot access them; revoked tokens are rejected.

`POST /api/worker-uploads/documents/<receipt>/retry/` retries a failed receipt
using its retained file and metadata, for at most three server processing
attempts. `run` uses this endpoint for failed rows with receipts. It does not
repeat parsing, enrichment or embedding, and needs no local source for this
server retry. Missing staging files and exhausted retries return HTTP 409.
Stale attempts are recovered in bounded batches; a live import holds a row lock,
and fenced ownership prevents an abandoned worker from committing later.
Attempt errors remain in the receipt's bounded `error_history`.

`GET /api/worker-uploads/documents/by-key/<client_key>/` returns a versioned
`found` envelope. Only `schema_version: 1, found: false` proves scoped absence.
Keys use 1–128 ASCII letters, digits, dots, underscores, colons or hyphens.
Use one ledger with one target, worker account and corpus. Token rotation is
supported; switching worker accounts changes the key namespace.
`COMPLETED` means worker-upload transaction completion, not thumbnail/search readiness.

Existing SQLite ledgers gain nullable conflict and identity columns in place; no export or
one-time migration is needed. Rows without a manifest run as uncached work after
the identities above are configured. Back up SQLite and its artifacts together.
The ledger and its SQLite recovery files are restricted to owner read/write
(`0600`), including existing ledgers when reopened.
Do not use an older worker against a ledger containing these new states.

Run `worker cleanup` while no other command owns that ledger. It walks ledger rows
in bounded pages and one artifact directory at a time, deleting only unreferenced
files and interrupted temporary writes older than 24 hours. Referenced artifacts
are retained for **all** rows, including failed, parked, ambiguous, conflicted and
completed work. An unreadable manifest is left alone until `run` repairs it.
Manifest rechecks and the retention grace period do not provide an interprocess
lock; concurrent `run` and `cleanup` are unsupported and can race during deletion.
Cleanup does not create caches for legacy rows or remove whole ledgers. After
archiving a finished ledger, its owner may delete that ledger's entire artifact
directory; do not manually delete individual active manifests.

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
    --enricher my_enrichers:enrich --enricher-identity my-config-v1
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
`--enricher example_enrichers:effective_date_annotations --enricher-identity examples-v1`.

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

1. Read source bytes and detect the canonical MIME type.
2. Call the selected parser’s shared bytes/text method → `OpenContractDocExport`.
3. Rebuild PDF text from PAWLS; preserve DOCX/TXT content and validate anchors.
4. Embed the document text + each annotation's `rawText` against the
   vector-embedder.
5. POST `multipart/form-data` (the source file + metadata JSON) to
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
`config.settings.remote_worker`, which disables the Django database backend. Explicit local component settings mean
the worker needs **no Postgres and no Redis**.

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
