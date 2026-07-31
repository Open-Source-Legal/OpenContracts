# Standalone authority import builder

Authority sources are fetched outside the OpenContracts application and emitted
as ordinary V2 corpus-export ZIPs. Administrators then install the trusted
authority pack and upload each ZIP through **Authority Packs → Import corpus
ZIP**. The server never runs the scraper.

The operator script initializes Django only to reuse the existing component
registry and provider configuration. It defaults to the repository's existing
off-cluster settings profile, whose throwaway SQLite configuration means no app
database is required. It is not exposed through a web, GraphQL, or Celery entry
point and performs no ORM writes.

The builder deliberately ignores an inherited `DJANGO_SETTINGS_MODULE`, which
may name a web or worker profile. An operator who needs a different standalone
profile can set `AUTHORITY_IMPORT_DJANGO_SETTINGS_MODULE` explicitly.

Each pack owns a `sources.yaml`:

```yaml
schema_version: 1
sources:
  - id: official-rules
    ingestion_mode: full_content
    discovery_provider: ExampleRuleIndexDiscoveryProvider
    source_provider: ExampleRuleAuthoritySourceProvider
    index_urls:
      - https://publisher.example/rules
    discovery_kwargs:
      max_candidates: 250
    candidate_filters:
      exclude_title: ["(?i)unrelated"]

  - id: rights-reviewed-guides
    ingestion_mode: full_content
    corpus_slug: example-guides
    source_provider: ExampleGuideAuthoritySourceProvider
    candidates:
      - canonical_key: example-guide:application
        url: https://publisher.example/application.pdf
        publisher_title: Application guide
        display_title: "[LEGAL REVIEW REQUIRED] Application guide"
        extra:
          source_identifier: application.pdf
          parent_key: example-proceeding:42
```

Exactly one candidate mode is allowed per source:

- `discovery_provider` plus `index_urls`
- `candidates`
- `canonical_keys`

Provider names are existing registered authority provider class names. An
omitted `source_provider` uses the existing canonical-key router.
`ingestion_mode: link_only` performs discovery and pure provider location, but
never calls the source provider's network fetch. `full_content` runs the
existing authority gate; records requiring rights approval are refused unless
the operator deliberately supplies `--rights-approved`.

The shipped GridDossier plans use `full_content` for every source. A complete
GridDossier build therefore requires a legal owner to approve acquisition of
the `REVIEW_REQUIRED` records and the operator to record that decision
explicitly:

```bash
python scripts/authority_import/build_authority_imports.py \
  --rights-approved \
  opencontractserver/enrichment/data/authority_packs/texas_electric_law \
  opencontractserver/enrichment/data/authority_packs/puct_electric \
  opencontractserver/enrichment/data/authority_packs/ercot_large_load \
  opencontractserver/enrichment/data/authority_packs/oncor_delivery
```

Omitting `--rights-approved` is expected to fail those records closed. The flag
does not declare the resulting corpora public, approve graph relationships, or
waive publisher restrictions; it only records the external collector's
per-build rights decision. Do not use `--allow-partial` for an acceptance
build.

`metadata` may be declared on a source as shared defaults and on an explicit
candidate as overrides. Live discovery providers use the same candidate
override contract by returning a nested `DiscoveryCandidate.extra["metadata"]`
mapping. Candidate values win over source defaults; that merge-only nested
mapping is removed from the persisted `discovery_metadata`.
Link-only documents default to `review_status: pending_legal_review`; a source
or candidate may explicitly override it. Direct candidate `version_label`,
`current_version`, and authority date fields are also validated and promoted
onto the document metadata so version-lineage reconciliation can consume them.

Every link-only record must resolve these six non-empty authority fields or the
candidate fails closed:

- `authority_family`
- `instrument_type`
- `publisher`
- `jurisdiction`
- `status`
- `authority_weight`

Controlled fields are validated against the existing authority vocabularies,
dates and booleans are normalized, and builder-owned provenance fields cannot
be supplied through `metadata`. Source plans continue to put per-record
`source_identifier` and `parent_key` in candidate `extra`.

`parent_key` remains discovery provenance by default. A link-only source may
set `parent_relationship_type` to an existing typed relationship value such as
`FILED_IN`; only then does the builder copy the candidate parent to
`parent_proceeding` and emit exactly one unverified relationship. Its metadata
marks it `pending_legal_review` and records the source-plan ID, candidate URL
when available, and `source_plan_parent_key` provenance. This prevents an
incidental publisher hierarchy from becoming a trusted graph edge.

Full-content providers emit their own typed relationships. For example, each
PUCT Project 59142 attachment carries a provider-authored `FILED_IN`
relationship to `puct-project:59142`; source plans do not manufacture that
edge.

## PUCT Interchange collection

Project 59142 is an active publisher listing, not a fixed candidate list. Its
plan has one explicit full-content project-root record and a separate
`PUCTProjectDiscoveryProvider` source that:

- enumerates every filing row from the project listing;
- opens every bounded filing-detail page;
- preserves every PDF and native ZIP under its publisher document identity;
- retains each exact ZIP package and emits every safely bounded native member
  as its own hash-bound source record, rather than treating the publisher's
  consolidated PDF rendition as a substitute for omitted originals; and
- sends every discovered attachment through the normal PUCT source provider
  and authority gate.

The Interchange server currently omits part of its public TLS chain. The pack's
`certificates/interchange-missing-intermediates.pem` contains only public CA
certificates. `discovery_kwargs.extra_ca_certificates` and
`fetch_kwargs.extra_ca_certificates` reference that pack-relative file. The
builder validates the path and PEM contents, adds the certificates to the
platform trust store, and keeps hostname verification, DNS pinning, redirects,
host allowlists, and size limits enabled. It never disables TLS verification.

Because the proceeding is active, the number of PUCT rows and attachments can
change. Treat `scrape-report.json` and the generated archive manifests as the
authority for each run; do not assert a historical fixed document total.

## Output and acceptance

The builder writes:

- `<pack>/imports/<corpus-slug>.zip`
- `<pack>/imports/index.json`
- `<pack>/imports/scrape-report.json`
- `imports/manifest.json` across all requested packs

Every archive uses the normal V2 fields, including `ingestion_sources`,
`document_paths`, source identifiers, retrieval metadata, and document
`custom_meta`. Targeted GUI imports reconcile an existing authority seed by
`custom_meta.canonical_key`; dynamic keys create normal new document paths.

Publisher bytes are hash-bound into the existing V2 format. A natively
ingestible source can be the document member itself; otherwise the portable
text artifact remains the ingestible member and the unmodified publisher file
is retained as a sidecar restored through the existing `original_file` field.
The manifest records `publisher_source_member`,
`publisher_source_content_hash`, `publisher_source_mime_type`, and
`publisher_source_packaging` so the import can be audited byte-for-byte.

Before using the GUI, verify for every requested pack:

- `rights_approved` is `true`;
- `linked` is zero and `errors` and `artifact_warnings` are empty;
- every decision has `ingestion_mode: full_content` and `verdict: ok`;
- `fetched` equals the sum of document counts in that pack's archive manifest;
  and
- neither document bodies nor extracted text contain a link-only or
  unfetched-content sentinel.

Install the four packs and upload the ten generated ZIPs through **Authority
Packs → Import corpus ZIP**. Source collection never runs in the application.
