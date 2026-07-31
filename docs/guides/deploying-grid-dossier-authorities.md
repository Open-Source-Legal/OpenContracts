# Deploying the GridDossier Authority Packs

This runbook installs the four independently reusable GridDossier authority
packs, sideloads externally prepared corpus exports, and assembles their ten
corpora into a public research group. OpenContracts does not crawl the source
sites in this workflow. For the pack format and provider contracts, see
[Authoring an Authority Pack](authoring-authority-packs.md).

> **Legal-review boundary**
>
> The shipped seed specs, fixture records, charters, and relationship
> declarations are engineering artifacts. Their review fields are
> `pending_legal_review`, and shipped relationship edges are `verified: false`.
> They have **not** been legally approved. Loading a pack, setting a group
> public, or finding a document on an official website does not change that
> status. Keep the corpora private until your legal owner has reviewed the
> intended materials, rights disposition, scope, and relationships.

## 1. Prepare the deployment

The deployment operator applies migrations, ensures the administrator account
already exists, and deploys the pack directories. Those are deployment
concerns, not steps the administrator performs in the application. Shipped
packs are discovered automatically; additional trusted packs can be exposed
through `AUTHORITY_PACK_PATHS`.

The commands below use `<creator-username>` for the user that owns the new
corpora, group, and orchestrator. Pack loading and group loading reject identity
collisions rather than mutating another user's objects.

The shipped public-group manifest creates a `GLOBAL` orchestrator, so its
`--creator` must be a superuser. This is the same authorization enforced by the
existing agent-configuration service for every other global agent; the
deployment command does not bypass it. A project-only manifest that reuses the
already-public orchestrator does not require a superuser, but its owner must be
able to read every declared member corpus.

The four packs are:

| Pack                 | Corpora | Research role                                                    |
| -------------------- | ------: | ---------------------------------------------------------------- |
| `texas_electric_law` |       2 | Texas statutes and legislative history                           |
| `puct_electric`      |       2 | PUCT rules/orders and large-load proceedings                     |
| `ercot_large_load`   |       3 | Current rules, revision history, and implementation materials    |
| `oncor_delivery`     |       3 | Current tariff, tariff history/filings, and service requirements |

The exact stable corpus slugs are declared in each `pack.yaml`. Group assembly
is a *deployment* concern, not a product one, so the manifest that composes
these corpora into groups lives in the external deployment repo (`ERCOT_LOAD_Grid_Dossier`) as
`manifests/ercot_grid_dossier_groups.yaml`, applied by the loader there.

## 2. Install the four packs privately

Sign in as a superuser and open **Admin Settings → Authority Console →
Authority Packs**. For each pack:

1. Select **Review & install**.
2. Review the fresh preflight, including the manifest fingerprint, declared
   corpora, source-host lineage, and approval state.
3. Leave **Make installed corpora public** unchecked.
4. Select **Install privately**.

The loader preflights the complete pack before writing, then atomically
converges taxonomy, stable corpus identity, seed content, personas, typed
metadata schemas, and canonical-key relationships. It does not treat
`pending_legal_review` declarations as approvals.

## 3. Sideload the ten corpus exports

Run the source acquisition and corpus-building process outside OpenContracts,
as for existing deployments. The repository's standalone builder reuses each
pack's declared discovery/source providers and `sources.yaml`, defaults to the
existing off-cluster settings profile so it needs no app database, performs no
ORM writes, and produces one ordinary OpenContracts corpus-export ZIP per
declared corpus:

```bash
python scripts/authority_import/build_authority_imports.py \
  --rights-approved \
  opencontractserver/enrichment/data/authority_packs/texas_electric_law \
  opencontractserver/enrichment/data/authority_packs/puct_electric \
  opencontractserver/enrichment/data/authority_packs/ercot_large_load \
  opencontractserver/enrichment/data/authority_packs/oncor_delivery
```

All shipped source-plan entries use `full_content`. The explicit
`--rights-approved` flag is therefore required after the legal owner approves
acquisition of the `REVIEW_REQUIRED` publisher files. It records the collector
run's rights decision; it does not publish a corpus or verify a relationship.
Without it, those records fail closed.

Do not use `--allow-partial` for a deployment build. For every pack-local
`imports/scrape-report.json`, require `rights_approved: true`, `linked: 0`, no
errors or artifact warnings, and only `full_content`/`ok` decisions. Confirm
that `fetched` equals the sum of that pack's generated archive document counts
and that `imports/manifest.json` lists all ten archives.

Project 59142 has one explicit project-root record plus hierarchical discovery
through every current filing row, detail page, and attachment. It is an active
PUCT proceeding. Native filing ZIPs are retained exactly and every safely
bounded member is emitted as a separate hash-bound source record; a
consolidated PDF rendition is not treated as a replacement for those originals.
Its document count can therefore grow both with publisher filings and archive
contents. Use the current scrape report and archive manifests as the
run-specific count; do not compare against an old fixed total.

PUCT Interchange currently omits public intermediates from its TLS response.
The PUCT pack references its public, pack-local CA bundle from both discovery
and fetch settings. This additively repairs certificate-chain verification;
hostname checks, the platform trust store, DNS pinning, source-host allowlists,
redirect validation, and byte limits remain enabled.

Return to **Authority Console → Authority Packs**, open the installed pack, and
select **Import corpus ZIP** beside the matching corpus. The existing
corpus-export importer uploads directly into that installed corpus, preserving
the pack's stable slug, owner, and visibility. Large archives use the existing
resumable chunked-upload path.

Authority documents in these exports carry `custom_meta.canonical_key`.
Importing the same archive again therefore converges onto the existing pack
document paths: unchanged content is skipped and changed content becomes the
next version. The importer fails closed if a canonical key is already
ambiguous. Use the ingestion monitor to confirm completion before moving to the
next operational step.

Neither pack installation nor corpus sideloading contacts a declared source
host. The pack's source metadata remains provenance and deployment information;
the external acquisition process owns fetching and crawling.

## 4. Review and publish

Review relationship declarations separately. They load as canonical-key edges
with their declared `verified` flag; the frontier rights approval does not
verify an edge. Preserve `verified: false` and
`review_status: pending_legal_review` until a qualified reviewer confirms the
relationship itself.

After the legal owner approves publication under the installation's policy,
deploy charters whose `approval_status` records that decision. Reopen the
pack's preflight, explicitly select **Make installed corpora public**, and
choose **Install and publish**. The option remains disabled while any charter
is missing approval or remains `pending_legal_review`.

Publishing propagates visibility to the corpus documents. It does not turn an
unverified relationship into a verified one, and it does not replace the
external acquisition process's rights and provenance review.

## 5. Load the public group and orchestrator

In **Admin Settings → Agent Configurations**, create the global
`dfw-large-load-orchestrator` using the instructions and tool configuration in
`manifests/ercot_grid_dossier_groups.yaml` in the external deployment repo
(`ERCOT_LOAD_Grid_Dossier`) — or let its loader converge both the agent and the
group for you, which is what that manifest is for.

Then open **Corpus Groups** from the user menu and create
`DFW Large-Load Public Authorities`. Add the ten installed pack corpora, select
the orchestrator as the default agent, review the membership, and make the
group public.

This converges `DFW Large-Load Public Authorities` and its
`dfw-large-load-orchestrator` across all ten corpora. The same manifest also
defines the temporary three-corpus `ERCOT Large-Load Authorities` vertical
slice with an `ercot-large-load-orchestrator` that is constrained to that group.
Existing group and corpus permissions are preserved; creator CRUD is granted
only for newly created group/agent objects. The generic manifest planner routes
mutations through the existing agent and corpus-group CRUD services, including
their visibility and permission checks. Group search still filters corpora at
call time, so making the group public does not expose a private member corpus
to a caller who cannot read it.

### Reconcile sideloaded effective-date metadata

Source records sideloaded before the shared effective-date review-state contract
may lack the required explicit state. This metadata-only command does not fetch,
reparse, or version documents. Review its dry-run output first, then add
`--apply` only for the intended corpora:

```bash
python manage.py reconcile_authority_effective_date_states \
  --creator admin \
  --corpus-slug ercot-current-large-load-rules \
  --corpus-slug ercot-large-load-revision-history \
  --corpus-slug ercot-large-load-implementation
```

For every current authority without `effective_from`, the apply mode writes
`effective_date_review_status=UNKNOWN_NEEDS_REVIEW`; it preserves explicit
curator states and ignores historical (`current_version=false`) records.

### Review cross-corpus acceptance questions

`gold/grid_dossier_gold_questions.yaml`, in the external deployment repo
(`ERCOT_LOAD_Grid_Dossier`), defines twenty DFW-public-authority questions. Each declares the source corpus
and canonical key that an accepted answer must cover, requires temporal/source
identity behavior, and includes nonpublic-study abstention cases. The fixture
is intentionally `pending_legal_review`: it is an evaluation contract, not
evidence that legal has approved the source materials.

Run them against the installed group once its corpora are populated. The
acceptance harness and its question set are **not** part of OpenContracts —
evaluation tooling that reaches inside the app drifts from the product it is
supposed to be measuring. Both now live in the external deployment repo (`ERCOT_LOAD_Grid_Dossier`) (`gold/`), which drives the
install from outside over its own APIs.

Each answer is scored for source-corpus citation coverage, canonical-key
coverage, expected abstention, and temporal accuracy. A reviewer judges legal
correctness, which the harness deliberately does not attempt. Expect
`key_coverage` to be low — models cite documents by name, not by internal
canonical key — and read `corpus_coverage` as the headline signal.

## 6. Create a private project group

Use **Corpus Groups → New Corpus Group** again. The file
`manifests/project_groups.template.yaml` in the external deployment repo (`ERCOT_LOAD_Grid_Dossier`) is a reference for the
intended private membership and agent configuration;
copy those values into the form, select the public authority corpora plus the
private project corpora the owner can read, and leave the group private.

The project template reuses the same public authority corpora and orchestrator
while adding private assumptions, engineering records, correspondence, study
results, permitting material, and dossier work product. Group configuration
never broadens existing object permissions.

## 7. Verify convergence

- Reopen each pack preflight. Installed corpus IDs and visibility should match
  the intended state; reinstalling unchanged seed content should report
  skipped/unchanged work rather than new document versions.
- Reopen the public group and confirm the intended ten-member corpus list and
  default orchestrator.
- In the Authority Console Registry, confirm the four pack origins and their
  declared prefixes.
- In the corpus metadata view, confirm the shared typed source fields exist and
  that live documents retain `canonical_key`, source URL, retrieval time,
  source MIME type, content hash, rights status, and authority weight. Also
  verify `publisher_source_member`, `publisher_source_content_hash`,
  `publisher_source_mime_type`, and `publisher_source_packaging` against the
  uploaded archive. Non-native ingest formats retain the unchanged publisher
  file through the existing original-file field while using a portable text
  member for ingestion.
- In the ingestion monitor, confirm every sideloaded corpus export completed
  and investigate any per-document failures. Open representative documents
  from every corpus and confirm rendered text is real publisher content, never
  a link-only or unfetched-content notice.
- Confirm the public group has exactly ten members and the orchestrator uses the
  active/selected group slug. Test with a user who can read the public corpora
  and with a user who cannot read a private project corpus.
- Sample the relationship graph and confirm no pending fixture edge is
  represented as legally verified.

For deeper ingestion checks, follow
[Ingesting Authorities & Adding Providers](ingesting-authorities.md). The
orchestrator is designed to state dates and missing facts and to abstain on
physical capacity, upgrade cost, and energization timing without
project-specific utility evidence; include those behaviors in deployment
acceptance testing.
