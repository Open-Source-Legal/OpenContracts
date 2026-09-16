# Ingestion run policy and budget

Remote worker uploads can opt into a durable run with a fixed processing policy
and a USD ceiling. Apply database migrations and run Celery Beat plus a worker
consuming `worker_uploads`; Beat recovers admitted operations whose initial
dispatch was lost.

## Scope

The server records the worker's existing preparation fingerprints, parser
identities, external embedding identity and dimension, permitted stages,
fallback policy, initial ceiling, and versioned pricing basis. Credentials and
raw component settings are excluded. Upload receipts and resulting documents
retain their run binding, including corpus copies and subsequent versions.
Structural annotation sets use a run-specific namespace so identical source
content uploaded into separate runs cannot share or redirect charged operations.
Cross-corpus copies keep the binding; requests for a destination corpus's provider
are suppressed without pausing the original run. Accounting records are retained,
so a referenced corpus cannot be deleted, including after run cancellation.

Two modes are available:

| Mode | Server processing |
| --- | --- |
| `prepared` (default) | Store prepared artifacts and any supplied vectors; no server provider calls. |
| `server` | Store prepared artifacts and generate missing text embeddings through the priced OpenAI adapter or explicitly declared self-hosted sentence service. |

Both modes suppress server parsing, conversion, thumbnails, multimodal fallback,
and automatic corpus actions. Custom OpenAI endpoints, unknown providers, and
undeclared pricing cannot be admitted. The effective corpus/default provider, model,
dimension, non-secret configuration fingerprint, adapter contract version, and
configured pricing are checked at admission and
again before each request. Changed configuration pauses execution; restoring the
approved configuration permits resume. The fingerprint includes operator-supplied
`EMBEDDING_MODEL_REVISIONS`; bump that revision when a model changes in place.
Changing the policy requires a new run. Generated vectors retain this fingerprint
for readiness checks; unverified or stale vectors do not skip budgeted generation.
The adapter version is the provider's `accounting_version`; changes to its request
or accounting contract must bump that version. Formatting and comment edits do
not invalidate an approved run.

Runs generate only their approved provider's vectors. Global search using a
different default embedder may therefore omit run-bound content. Prepared mode
permits missing vectors and may remain outstanding in readiness; choose `server`
mode when server-generated text embeddings are required. Routing to a run means
the policy owns the work, not that embedding has completed: readiness and
`run-status` expose missing output, queued work, suppression, and violations.
Manual document parsing retries are rejected without clearing failure state;
embedding attempts use the run's explicit retry controls.

**The ceiling covers server provider usage at the recorded pricing basis.**
External worker parsing, enrichment and embedding, infrastructure, and later
interactive user work are explicitly excluded in the policy. Preparation already
in progress may finish after another worker exhausts the budget; its checkpoint
is retained. This is not a cap on the entire deployment's invoice.

## Operator pricing

### Self-hosted sentence service

Select the built-in `MicroserviceEmbedder` as the corpus or default embedder.
In its pipeline settings GUI (or the existing `updatePipelineSettings` mutation),
set `embedding_model_revision` to an identifier for the deployed model and immutable
revision, such as `multi-qa-MiniLM-L6-cos-v1@<revision>`, and set the boolean
`no_external_provider_fees` to `true` only when the service incurs no external
provider fees. Keep the existing service URL and authentication configuration.
No pricing environment variable or infrastructure configuration change is required. An existing
`EMBEDDING_MODEL_REVISIONS` entry is accepted when the component revision is unset.

For example, the `componentSettings` input to `updatePipelineSettings` can include
the following entry (retain any other configured non-secret options; credentials
continue to use `updateComponentSecrets`):

```json
{
  "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder": {
    "embeddings_microservice_url": "http://vector-embedder:8000",
    "embedding_model_revision": "multi-qa-MiniLM-L6-cos-v1@pinned-revision",
    "no_external_provider_fees": true
  }
}
```

The service has a fixed 384-dimensional output contract. The run pins its model
identity, configuration fingerprint, endpoint fingerprint and adapter version;
update the revision setting whenever the deployed model changes in place.
The configured identity is an operator declaration, not remote model attestation.
Credentials and raw endpoints are not included in run reports. Billing settings
do not change vector identity, and unset new settings preserve legacy fingerprints.

This adapter reserves and settles **zero provider fees**, so a zero USD ceiling
is valid in `server` mode. `accounted_tokens: 0` denotes zero billable provider
tokens, not measured inference token usage. **Infrastructure costs remain excluded**;
this setting does not imply free computation. Each attempt sends one bounded text
request (at most 30,000 characters, 30-second timeout), without HTTP retries or
redirects. The same persisted attempts, explicit retry limit and readiness checks
apply as for paid embeddings. Missing declarations, configuration changes, invalid
vectors and request failures fail closed; no paid-provider fallback is allowed.

### OpenAI

For OpenAI `server` mode, configure `INGESTION_RUN_PRICING` as a JSON environment value
with `version` and `openai_usd_per_million_tokens`. The latter maps each permitted
OpenAI embedding model name to its positive USD rate, expressed as a decimal
string. Set an operator-maintained version whenever prices change. No rates are
assumed by default. See `worker_uploads/run_policy.py::pricing_for` for validation.
The corpus's effective embedder must resolve to `OpenAIEmbedder` with the official
endpoint and a supported model/dimension.

Each text operation reserves its UTF-8 byte count as a conservative token bound,
after the adapter's existing input truncation. Costs round up to nine decimal
places. Admission locks the run and enforces
`accounted + reserved + next reservation <= ceiling`, including queued work.
An exact fit is admitted; the next non-fitting operation waits and marks the run
`BUDGET_EXHAUSTED`.

The adapter makes one request with SDK retries disabled. Provider-reported prompt
tokens settle the attempt at the recorded rate and release unused allowance.
Timeouts, missing usage, and crashes after the persisted request claim retain the
full reservation. Redelivery cannot repeat a claimed attempt. An explicit retry
requires an additional reservation, with a maximum of three attempts per
operation. Late responses still account usage but cannot overwrite newer results.
Targets and input digests are checked again before publishing a result. If vector
validation or storage fails, known usage still settles and the operation is
`FAILED`, available for an explicit retry; no vector is published for changed input.
Uncertain reservations are never automatically treated as unspent money.

## CLI

Use the same parser, enricher and embedding configuration for run creation and
upload. The run UUID is saved in the existing SQLite ledger before creation is
posted, so a lost response can be retried with the same identity.

```bash
# Store externally prepared artifacts; external preparation costs are excluded.
python scripts/remote_ingest/oc_remote_ingest.py --run-budget-usd 0 run-create
python scripts/remote_ingest/oc_remote_ingest.py plan
python scripts/remote_ingest/oc_remote_ingest.py run
python scripts/remote_ingest/oc_remote_ingest.py run-status
```

For server text embeddings, use `--no-embeddings --run-embedding-mode server`
with `run-create`, supply `--run-budget-usd` (zero is valid for the declared
self-hosted service; OpenAI requires enough allowance for its requests), and retain
`--no-embeddings` for `run`. Existing target URL/token, source, ledger and parser
options still apply. A ledger remains bound to its original run.

```bash
# After configuring the self-hosted service through pipeline settings:
python scripts/remote_ingest/oc_remote_ingest.py --no-embeddings --run-embedding-mode server --run-budget-usd 0 run-create
python scripts/remote_ingest/oc_remote_ingest.py --no-embeddings run
```

- `run-pause`: retain receipts, checkpoints and reservations, and stop admission.
- `run-resume`: resume after restoring policy settings; optional
  `--run-budget-usd` raises the ceiling with an audit event.
- `run-retry --run-operation UUID`: permit another attempt for a running,
  failed, or uncertain operation. Resume a paused run separately.
- `run-cancel-operation --run-operation UUID`: cancel an operation and release
  reservations that were never claimed.
- `run-cancel`: cancel the run. Claimed/uncertain reservations remain held.
- `run-status --run-offset N`: page through operations using `next_offset` from
  the preceding JSON report. Each page includes all reservations for those
  operations; totals always cover the entire run.

`run` stops with exit code 2 when the run is paused, unavailable, exhausted, or
violates policy, without consuming preparation attempts. `verify` continues to
describe upload receipt completion; use `run-status` for server operation and
cost completion.

## Worker API

Authenticate with the existing `Authorization: WorkerKey <token>` header. Access
is scoped to the stable worker account and corpus, so token rotation preserves
access without granting access to another worker or corpus.

- `POST /api/worker-uploads/runs/`: create/replay a run using optional client UUID
  `id`, decimal string `ceiling_usd`, `preparations`, `embedding_mode`, and
  `fallback: "forbid"`. Preparation descriptors use the exact schema in
  `run_policy.py::build_policy`; the CLI builds them from existing checkpoints.
- Set `metadata.ingestion_run_id` on document uploads and supply an idempotency
  key. Previously accepted uploads remain retrievable/replayable while paused.
- `GET /api/worker-uploads/runs/<uuid>/?offset=0`: policy, decimal-string totals,
  remaining allowance, waiting estimates, operations, reservations, and recent
  credential-free audit events. Pages contain at most 100 operations.
- `POST /api/worker-uploads/runs/<uuid>/`: `action` is `pause`, `resume`, `cancel`,
  `retry_operation`, or `cancel_operation`; operation actions require
  `operation_id`, and resume accepts an increased `ceiling_usd`.

Database constraints protect the ceiling and immutable policy/bindings. The
accounting and execution protocol lives in `worker_uploads/run_services.py`;
legacy task entry points route bound objects through it before provider lookup.
