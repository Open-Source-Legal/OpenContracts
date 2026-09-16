# Scoped automation credentials

Use `Authorization: Automation <token>` for the supported GraphQL operations
and all four direct import endpoints (`/api/imports/documents/`,
`documents-zip/`, `zip-to-corpus/`, `corpus/`) plus every `/api/imports/chunked/`
stage. No interactive login or `USE_API_KEY_AUTH` setting is needed. Existing
JWT, legacy GraphQL API-key, and narrow `WorkerKey` behavior is unchanged.
Automation credentials do not authenticate worker-upload receipts or other REST
endpoints; those retain their existing authentication contracts.

## Provision and manage

Active superusers can use **Admin Settings → Automation Credentials**
(`/admin/automation-credentials`) to list, inspect, mint, rotate and revoke
credentials, including ones created by the CLI. Search for an existing active
principal by name or stable user ID, choose explicit scopes and corpuses (or
explicitly allow all corpuses), and set a positive lifetime (default: 30 days).
The scope picker and CLI use the same server-side `Scope` catalog.

Mint/rotate show the token in a one-time copy/dismiss dialog. Dismissing,
leaving the page or signing out clears it; it is not written to Apollo cache,
local storage or session storage. Metadata remains available for inspection.
Rotation and revocation require confirmation in the credential detail dialog.

The authenticated GraphQL API exposes `automationCredentials(limit:, offset:)`,
`automationCredential(id:)`, `automationCredentialScopes` and the paginated
`automationCredentialChoices(kind:, search:, limit:, offset:)` selector
(`kind` is `principal` or `corpus`). Pages default to 20 and are capped at 100.
Writes are `mintAutomationCredential`, `rotateAutomationCredential` and
`revokeAutomationCredential`; only mint/rotate return a `token`. Credential IDs
are UUIDs; principal and corpus IDs are stable database IDs. These operations
require an active superuser login; **automation tokens cannot manage credentials**,
even when their principal is a superuser. Management responses use `no-store`.

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
actors by ID, without authorization headers or secret prefixes. Lifecycle audit
events record the acting administrator as `actor_id` separately from the bound
`principal_id`; CLI operations have no application actor (`actor_id=None`).

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
| `pipeline:read` | `pipelineSettings`, `pipelineComponents`, `supportedMimeTypes`, `convertibleExtensions`; requires all-corpus authorization and a superuser principal |
| `pipeline:configure` | `updatePipelineSettings`, including its nested settings response; requires all-corpus authorization and a superuser principal |

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

## Pipeline configuration

Mint a credential for an existing superuser with `--scope pipeline:read`
and/or `--scope pipeline:configure`, plus `--all-corpuses`. These scopes do not
imply one another; configuring settings does not permit a standalone read.
Existing credentials gain neither scope automatically. A corpus-restricted
credential cannot access these global operations, even for a superuser.

`pipelineComponents` permits each component group and its `settingsSchema`;
`supportedMimeTypes` permits `stageCoverage`. Queries and the update response
permit settings metadata, but **not `modifiedBy` or arbitrary user/Node
traversal**. Secret schema entries expose only presence (`hasValue`), never
decrypted values (`currentValue` is null). `resetPipelineSettings`,
`updateComponentSecrets`, `deleteComponentSecrets`, `updateToolSecrets` and
`deleteToolSecrets` remain denied. Secret management would require a separate
explicit capability; non-secret settings still reject inline credentials.

This example reads component schemas, updates non-secret settings and reads
back the result. It takes the token from an environment variable and prints
neither the token nor response bodies. Use your deployment's HTTPS URL and
configure secrets separately through an interactive administrator login.

```python
import json
import os
from urllib.request import Request, urlopen

def graphql(query, variables=None):
    request = Request(
        "https://contracts.example.org/graphql/",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Automation " + os.environ["OPENCONTRACTS_AUTOMATION_TOKEN"],
        },
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("GraphQL operation rejected")
    return result["data"]

catalog = graphql("""{ pipelineComponents { embedders {
  className settingsSchema { name settingType hasValue currentValue }
} } }""")
component = "opencontractserver.pipeline.embedders.openai_embedder.OpenAIEmbedder"
updated = graphql("""mutation($settings: GenericScalar!) {
  updatePipelineSettings(componentSettings: $settings) {
    ok pipelineSettings { componentSettings }
  }
}""", {"settings": {component: {"openai_embedding_dimensions": 1536}}})
if not updated["updatePipelineSettings"]["ok"]:
    raise RuntimeError("Pipeline settings validation failed")
current = graphql("{ pipelineSettings { componentSettings } }")
assert current["pipelineSettings"]["componentSettings"][component]["openai_embedding_dimensions"] == 1536
```

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
