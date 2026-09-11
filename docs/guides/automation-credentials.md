# Scoped automation credentials

Use `Authorization: Automation <token>` for the supported GraphQL operations
and all four direct import endpoints (`/api/imports/documents/`,
`documents-zip/`, `zip-to-corpus/`, `corpus/`) plus every `/api/imports/chunked/`
stage. No interactive login or `USE_API_KEY_AUTH` setting is needed. Existing
JWT, legacy GraphQL API-key, and narrow `WorkerKey` behavior is unchanged.
Automation credentials do not authenticate worker-upload receipts or other REST
endpoints; those retain their existing authentication contracts.

## Provision and manage

An operator with access to `manage.py` can bind a credential to an **existing
active user**. Choose a dedicated service user and grant its corpus permissions
through the normal permission system. The command neither creates users nor
grants roles or object permissions.

```bash
python manage.py automation_credential mint \
  --user ingest-service --name nightly-import \
  --scope corpus:read --scope document:import \
  --corpus 7 --expires-days 30
python manage.py automation_credential inspect <credential-id>
python manage.py automation_credential rotate <credential-id>
python manage.py automation_credential revoke <credential-id>
```

Repeat `--scope` and `--corpus` as needed. Use `--all-corpuses` explicitly instead
of `--corpus` for global operations; it still grants no principal permissions.
The CLI defaults to a 30-day lifetime and rejects nonpositive lifetimes. Mint
and rotate emit JSON containing a new `token` exactly once. Store it securely;
inspect returns metadata only, never the token or its hash. Only SHA-256 hashes
of random 256-bit secrets are persisted. Audit events identify credentials and
actors by ID, without authorization headers or secret prefixes.

## Capability boundaries

Effective access is **credential scope ∩ corpus restriction ∩ principal
permissions**. Scope names do not imply one another.

| Scope | Supported operations |
| --- | --- |
| `corpus:read` | GraphQL `corpus(id:)` and `corpuses(id:)` metadata; unfiltered lists require all-corpus authorization |
| `corpus:create` | `createCorpus`; corpus-export import without a destination |
| `corpus:configure` | `updateCorpus`, `updateCorpusDescription`; corpus-export import into an existing destination |
| `corpus:publish` | `setCorpusVisibility`; imports setting `make_public`; corpus-export imports |
| `document:import` | Direct and chunked document/ZIP/corpus-export imports |
| `ingestion:read` | Existing `admin*Ingestion` / upload / import diagnostics; requires all-corpus authorization and the existing superuser gate |
| `ingestion:repair` | `reEmbedCorpus` for an allowed corpus; `retryDocumentProcessing` requires all-corpus authorization because it changes the document globally |
| `authority:admin` | Explicit namespace, key-equivalence, frontier and trusted-pack operations; requires all-corpus authorization and `is_authority_admin` |

Corpus-export archives can carry public objects, so importing them requires
`document:import`, `corpus:publish`, and either `corpus:configure` (destination
specified) or `corpus:create` (new destination). Pack installation additionally
requires `corpus:create` and `corpus:configure`, plus `corpus:publish` when
publishing. Authority privileges are still decided centrally by
`enrichment/services/authority_permissions.py::is_authority_admin`.

GraphQL's exact operation and metadata-selection allowlists live in
`config/graphql/automation.py`. Unlisted roots, arbitrary nested relationships,
login/token mutations, and generic Node traversal are denied. The entire selected
operation is checked before any resolver runs, including aliases, fragments,
variables and directives. A denied field rejects the operation without partial
mutation effects. A browser session cannot override an explicit automation
header. Normal resolver/service permission checks remain in effect.

## Rotation and in-progress work

Every HTTP request reloads the credential and active principal. Revocation,
expiry and deactivation reject subsequent requests. Rotation atomically replaces
the secret without changing the credential ID, scopes, corpus restrictions or
expiry. The old secret stops authenticating immediately after commit. Rotation
cannot revive an expired or revoked credential; mint a new one instead.

Chunked uploads belong to both the actor and credential ID. Only that credential
(including its rotated secret) can send parts, inspect status or complete the
upload. Another credential for the same actor/corpus, a JWT, or a worker token
cannot take it over. Each stage rechecks current scopes, the persisted target,
and the principal's corpus EDIT permission before accessing or changing upload
state. Minting a separate credential requires restarting its uploads.

Requests already admitted and queued work continue after rotation/revocation;
credentials are an admission boundary, not cancellation of asynchronous tasks.
Readiness, receipt recovery/idempotency, pack persistence and run budgets remain
the separate contracts tracked by #2336–#2340.
