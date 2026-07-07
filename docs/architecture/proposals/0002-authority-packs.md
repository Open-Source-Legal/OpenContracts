# 0002 — Authority Packs

| | |
|---|---|
| **Status** | Partially implemented — this doc is the original design rationale + gap analysis. For the operator/author how-to (and the now-self-contained pack layout: in-pack providers + `source_hosts`), see the guide: [Authoring an Authority Pack](../../guides/authoring-authority-packs.md). |
| **Supersedes / builds on** | 0001 — Generic scheduled scraping + corpus groups (PR #1444; the `0001-…` proposal doc is not yet written) |
| **Relates to** | PR #1305 (Bolivian-law contributor PR, closed/reference), the Authority architecture (PRs #1990 / #1997 / #2037), [`authority-console.md`](../authority-console.md), [`reference-web-enrichment.md`](../reference-web-enrichment.md) |
| **Author** | follow-up to #1305 / #1444 |

## TL;DR

An **authority pack** is a drop-in bundle that stands up an entire body-of-law
family for a new jurisdiction — its taxonomy, its source provider(s), and its
target corpora + agent personas — **without a bespoke Django app**. It binds to
the four extension seams the Authority architecture already ships, so a pack is
**~90% data + one thin provider module**. PR #1305's 4,704-line `bolivian_laws/`
app collapses, under this shape, to a YAML fragment, a handful of JSON seeds, and
a single ~150-line provider — the exact inverse of its current ~90%-code form.

This proposal is the **authority-rail successor to 0001/#1444**. #1444 proposed a
*new* generic `scraping/` app because, when it was written, the platform had no
pluggable fetch rail. That rail now exists (`BaseAuthoritySourceProvider` +
auto-discovery + frontier/enrichment runtime), so the "extract the missing
primitives" intent of #1444 is re-expressed here against what actually shipped,
rather than against a `scraping/` app that was never built.

> **Implementation status (Phase 1, shipped in this PR).** The seed-based
> reference Bolivia pack and the generic `load_authority_pack` loader are
> implemented — see
> `opencontractserver/enrichment/data/authority_packs/bolivia/` and
> `opencontractserver/corpuses/management/commands/load_authority_pack.py`
> (tests: `opencontractserver/tests/test_authority_pack.py`). The live-fetch
> **provider folds into Phase 2**: reading PR #1305's actual scrapers confirmed
> the Bolivian sources (Gaceta Oficial / TSJ / TCP) are **listing-page** sites,
> **not key-addressable**, so a deterministic `canonical_key → URL` provider
> cannot be built today — that is the bulk-discovery work of issue #2054. Phase 1
> therefore ships taxonomy + curated content + personas (no live fetch, so no
> host-allowlist edit is needed yet).

> **Update — packs are now self-contained (gaps 1 & 6 closed).** A pack may now
> ship its scraper inside the pack (`<pack>/providers/*.py`, discovered by the
> pipeline registry from in-tree packs and out-of-tree dirs on the
> `AUTHORITY_PACK_PATHS` setting) and declare the hosts it fetches from in
> `pack.yaml` (`source_hosts:`, merged into the SSRF allowlist at runtime). The
> "one un-packable edit" of §3 (the hardcoded host allowlist) and the
> "single hardcoded package" of gap 6 (§7) no longer hold — a fetching pack is
> portable as a directory, secrets still living in the `PipelineSettings` vault.
> See [Authoring an Authority Pack](../../guides/authoring-authority-packs.md)
> (tests: `test_authority_pack_providers.py`, `test_authority_source_hosts.py`).
> The remaining gaps (scheduled scraping, multi-corpus orchestration,
> config-declarable `authority_type`/shape grammars) are unchanged.

> **Update — Phase 2 (listing-index discovery, gap 3) shipped, issue #2054.**
> `BaseAuthorityDiscoveryProvider`
> (`opencontractserver/pipeline/base/base_authority_discovery_provider.py`) answers
> the question a citation-keyed `BaseAuthoritySourceProvider` cannot: "what
> documents exist that nobody has cited yet". It crawls a publisher's index page(s)
> and lists candidates (canonical_key + url + metadata) WITHOUT fetching or
> ingesting them — mirroring the `locate`/`fetch` split as `_fetch_index_impl`
> (I/O) / `_parse_index_impl` (pure). The one reference implementation,
> `ListingIndexDiscoveryProvider`
> (`opencontractserver/pipeline/authority_discovery_providers/listing_index_provider.py`),
> is a config-driven regex+template engine — jurisdiction-agnostic; a publisher
> supplies a `ListingIndexRule` (link regex + canonical-key template), not new
> code. Candidates are seeded into `AuthorityFrontier` via the new
> `AuthorityFrontierService.seed_from_discovery`, which mirrors `seed_child_keys`'
> idempotency contract exactly (skip, never duplicate, never reset an in-flight
> row). The pipeline registry discovers discovery providers the same way as
> source providers (core package + `<pack>/discovery_providers/`). Bounded by
> `enrichment.constants.DISCOVERY_DEFAULT_MAX_CANDIDATES` /
> `DISCOVERY_MAX_MAX_CANDIDATES`, and every fetch is SSRF- and
> license-gated, same as Phase 1. Operator surface is the
> `discover_authority_candidates` management command — **no admin UI** (out of
> scope for #2054; deferred to a future console surface alongside Phase 3/4).
> The shipped `bolivia` pack is NOT wired to a live index (nobody has verified
> Gaceta Oficial's real markup in this codebase); the engine is proven against a
> synthetic, Gaceta-Oficial-*shaped* fixture in
> `test_listing_index_discovery_provider.py`. An operator who has verified a real
> publisher's markup supplies their own `ListingIndexRule`. Tests:
> `test_authority_discovery_provider_base.py`,
> `test_listing_index_discovery_provider.py`,
> `test_authority_frontier_discovery_seed.py`,
> `test_discover_authority_candidates_command.py`, plus the pack-discovery
> additions in `test_authority_pack_providers.py`.

> **Update — gap 7 closed (issue #2057).** The mappings loader now guards
> baseline-vs-baseline collisions and merge-loads multiple YAMLs. Every
> `source="baseline"` `AuthorityNamespace` row is stamped with its writer origin
> (`baseline_origin`: `"core"` for the shipped YAML, else the pack's manifest
> `name`), and a load **skips + warns instead of clobbering** a prefix a
> different origin owns — first writer wins; curator `manual` rows still trump
> everything (`AuthorityMappingLoader.load_namespaces`; the `post_migrate`
> convergence in `enrichment/_namespace_seed.py` honours the same guard). So
> re-loading two packs that touch distinct prefixes can never clobber each
> other, and a same-prefix collision is loud instead of silent.
> `manage.py load_authority_mappings --include-packs` converges the core
> baseline plus every installed pack's mappings in one idempotent run
> (`AuthorityMappingLoader.load_installed`). Tests:
> `test_authority_mapping_loader.py::BaselineOriginGuardTests` /
> `LoadInstalledTests`.

> **Update — Phase 4 (multi-corpus orchestration, gap 4) shipped, issue #2056.**
> `CorpusGroup` (`opencontractserver/corpuses/models.py`) bundles N corpora
> (M2M + unique slug + optional `default_agent` FK binding an orchestrator
> `AgentConfiguration`) with full guardian object permissions.
> `CorpusGroupService`
> (`opencontractserver/corpuses/services/corpus_groups.py`) resolves the
> group's corpora at **call time**, filtered per-user — never a config-time
> snapshot. The `search_across_corpora` agent tool
> (`opencontractserver/llms/tools/core_tools/multi_corpus.py`) fans a query
> out per visible member corpus (each searched with its own
> `preferred_embedder`) and returns hits grouped per corpus for per-corpus
> citations. The orchestrator runs over the existing `ws/agent-chat/`
> transport: an explicitly-selected agent's `system_instructions` +
> `available_tools` now thread through `UnifiedAgentConsumer` (and
> `available_tools` through @mention delegation), so a GLOBAL
> `AgentConfiguration` carrying the orchestrator persona +
> `search_across_corpora` restores #1305's unified `askBolivianLaw`
> experience as pure data. GraphQL: `corpusGroups` query +
> create/update/delete mutations. Tests:
> `opencontractserver/tests/test_corpus_groups.py`,
> `CorpusGroupAuthorizationInvariantsTestCase`. *Closes gap 4.*

## 1. Context — three artifacts, one intent

| Artifact | What it is | Status |
|---|---|---|
| **#1305** | A standalone `opencontractserver/bolivian_laws/` app: its own `BaseScraper` + 3 site scrapers, SHA-256-dedup ingestion, 11 hard-coded legal areas with personas, a bespoke `AskBolivianLawMutation`, and an orchestrator/specialist agent layer. | Closed — reference implementation |
| **#1444 / 0001** | A design proposal to extract #1305's genuinely-missing primitives (scheduled scraping, multi-corpus retrieval) into a generic `scraping/` app (Phase A) + `CorpusGroup`/`asearch_across_corpora` (Phase B). | Open — design only |
| **Authority architecture** (#1990/#1997/#2037) | The shipped system: `AuthorityNamespace` + `authority_mappings.yaml` declarative taxonomy, `BaseAuthoritySourceProvider` + auto-discovered providers, `AuthorityFrontier` + discovery/crawl/enrichment runtime, the unified Authority Console. | Merged |

The shipped architecture took a **different rail** than #1444 imagined: instead of
a `scraping/` app with `ScrapedSource`/`ScrapedDocument` models, it built a
*citation-keyed* provider rail feeding a *frontier*. That rail already does most
of what #1305 hand-rolled — but it left two of #1444's primitives (scheduled
scraping, multi-corpus orchestration) **unbuilt**. The authority-pack concept
exploits the rail that shipped, and is explicit about the two gaps that did not.

## 2. The four seams a pack binds to

The Authority architecture exposes exactly four extension points. A pack supplies
one declaration per seam; the runtime does the rest with **zero changes**.

1. **Taxonomy** — `opencontractserver/enrichment/data/authority_mappings.yaml`
   (`prefixes:` / `equivalences:` / `rewrite_rules:`), loaded idempotently by
   `AuthorityMappingLoader.load_all(path=…)`
   (`opencontractserver/enrichment/services/authority_mapping_loader.py`) into
   `AuthorityNamespace` + `AuthorityKeyEquivalence` rows. **`jurisdiction` is an
   open `CharField`** — `bo`, `bo-la-paz`, anything — so a non-US jurisdiction is
   pure data. The **only** closed vocabulary is `authority_type`, which must be
   one of the nine `ALL_AUTHORITY_TYPES`
   (`opencontractserver/enrichment/constants.py`): `statute`, `regulation`,
   `admin-rule`, `municipal-ordinance`, `case`, `constitution`, `court-rule`,
   `guidance`, `treaty` — and these already cover Bolivian instruments.
2. **Fetch** — a concrete subclass of `BaseAuthoritySourceProvider`
   (`opencontractserver/pipeline/base/base_authority_source_provider.py`) dropped
   into `opencontractserver/pipeline/authority_source_providers/`. The registry
   (`PipelineComponentRegistry`) auto-discovers it by **mere presence** — no
   registration call, no entry-point. This is the irreducible *code* slot: every
   source's HTML/XML/API shape differs.
3. **Corpus + content** — `bootstrap_authority_corpus()`
   (`opencontractserver/enrichment/authorities.py`), driven by the
   `bootstrap_authority` management command from a JSON section spec. Idempotent
   (unchanged sections skipped, changed text version-ups) — the functional
   equivalent of #1305's SHA-256 dedup, with no stored hash.
4. **Persona** (optional) — `Corpus.corpus_agent_instructions`
   (`opencontractserver/corpuses/models.py`) consumed by
   `CoreCorpusAgentFactory`, and/or an `AgentConfiguration(scope=CORPUS)` row.
   Free text — Spanish fully supported.

## 3. Pack anatomy

| Slot | Binds to | Format | Required |
|---|---|---|---|
| Taxonomy / namespaces (`prefixes:`) | `authority_mappings.yaml` → `AuthorityMappingLoader` → `AuthorityNamespace` | YAML data | ✅ |
| Aliases / equivalences (`equivalences:` / `rewrite_rules:`) | same YAML → `AuthorityKeyEquivalence` | YAML data | optional |
| Source provider(s) | `BaseAuthoritySourceProvider` subclass in the auto-discovered package | Python module | ✅ |
| Corpus + content seed (per legal area) | `bootstrap_authority_corpus()` via `bootstrap_authority --file` | JSON fixture | ✅ |
| Agent persona (per corpus) | `corpus_agent_instructions` / `AgentConfiguration` | DB row / fixture | optional |
| Provider credentials | `PipelineSettings.encrypted_secrets` vault | DB row | optional |
| **Source-host allowlist entry** | `PUBLIC_DOMAIN_SOURCE_HOSTS` in `opencontractserver/constants/safe_http.py` | **source edit** | Phase 2 ⚠️ |

**The one binding a pack cannot self-declare** (only relevant once a pack ships a
live-fetch provider — Phase 2). Every fetch is SSRF-gated to a hardcoded
registrable-suffix allowlist (`PUBLIC_DOMAIN_SOURCE_HOSTS`). An un-listed host
raises `SSRFValidationError`, and `AuthorityGateService` parks the result at
`GATE_BLOCKED_DOMAIN`. So a *fetching* pack needs a one-line same-PR edit to
`safe_http.py` adding its government host(s). A seed-based pack (Phase 1) does no
live fetch and needs no such edit; §7 proposes making this declarative (issue
#2057) so even fetching packs stay pure data.

## 4. Drop-in lifecycle

For a **seed-based pack (Phase 1, implemented)** the whole lifecycle is one
idempotent command — `manage.py load_authority_pack --path <dir> --creator USER
[--public]` — which loads the taxonomy YAML, bootstraps each area corpus from its
section spec, and applies each persona. The fuller, provider-driven lifecycle
below adds live fetch and is the **Phase 2** target.

1. **Drop in** — place the provider module(s) in
   `opencontractserver/pipeline/authority_source_providers/` and the pack's YAML +
   JSON specs + persona text on disk.
2. **The one un-packable edit** — add the pack's host(s) (e.g. `tsj.bo`) to
   `PUBLIC_DOMAIN_SOURCE_HOSTS`; restart so registry auto-discovery sees the new
   provider.
3. **Load taxonomy** — `manage.py load_authority_mappings` (or
   `AuthorityMappingLoader.load_all(path=<pack>/authority_mappings.yaml)` for a
   per-pack file): upserts `AuthorityNamespace` + `AuthorityKeyEquivalence` rows
   (`source="baseline"`), never clobbering `source="manual"` curator edits.
4. **Verify registration** — the Authority Console **Scrapers** tab
   (`AuthoritySourceProviderService.list_providers`) now shows the pack's provider
   with its `supported_prefixes` / `license` / `priority` / `enabled`.
5. **Seed corpus + content + persona** — per legal area:
   `manage.py bootstrap_authority --creator USER --title '…' --file <area>.json
   [--public]`. Get-or-creates the corpus, imports one keyed text document per
   section, sets `corpus_agent_instructions` from the pack persona, and relinks
   citing corpora.
6. **Runtime is armed** — discovery is triggered either *citation-driven*
   (references in ingested documents seed frontier rows) or *directly*
   (`RunAuthorityDiscoveryMutation` over chosen frontier rows). Per key, the
   provider-agnostic runtime runs automatically: `_provider_for` picks the pack's
   provider by priority-sorted `can_handle` → `locate` → `fetch` → license+host
   gate → `bootstrap_authority_corpus` → relink → crawl depth+1.
7. **Queryable** — each area corpus's `CoreCorpusAgentFactory` agent answers in
   the pack's persona — **per corpus** (see the orchestrator gap, §6).

## 5. Why this shape (and not the alternatives)

| Option | Verdict |
|---|---|
| **Data-only YAML+JSON bundle** | Insufficient: the fetch/parse logic is irreducibly Python (every source differs), so a pure-data pack can only fetch via the opt-in, approval-gated agentic fallback (`AgenticWebLocatorProvider`, `priority=9999`) — and even that still needs the host-allowlist edit. Reduces to a "taxonomy + seed-content" pack, not a self-fetching one. |
| **Data bundle + thin provider module** ✅ | **Recommended.** Binds to every seam exactly as designed: registry auto-discovery, `_provider_for` priority routing, gate, bootstrap, relink, credential vault. ~90% data + one provider module. The only non-data binding is the host-allowlist edit. |
| **Per-pack Django app** (the #1305 shape) | Re-implements subsystems that exist: `BaseScraper`↔`BaseAuthoritySourceProvider`, `LegalArea` enum↔`AuthorityNamespace`, SHA-256 dedup↔bootstrap text-equality, per-area persona↔`corpus_agent_instructions`. Hardwires jurisdiction into a `TextChoices` enum (every country = code + migration) and violates the Tier-0 service-layer invariant (E001). The anti-pattern this exercise exists to avoid. |
| **pip entry-point plugin** | Unsupported today: discovery scans **one hardcoded package** with no entry-point hook. Would require core work (`registry._discover_subclasses`). A candidate for the future isolation work in §7. |

## 6. PR #1305 → pack mapping

**Fully collapses to data / native primitives:**

| #1305 component | Pack slot | How |
|---|---|---|
| `LegalArea` (11 areas) + `AreaProfile` dict | Taxonomy + corpus seeds | The 11 enum values → `AuthorityNamespace` rows (`jurisdiction='bo'`) and one seeded corpus per area. Code+migration → YAML. |
| `pdf_sha256` + `_sha256` dedup + `BolivianLegalDocument` table | Content seed (runtime-handled) | `bootstrap_authority_corpus` dedups by canonical key + text equality; the tracking table is redundant with `Document.custom_meta.canonical_key`. |
| per-area `agent_instructions` (Spanish) + `ensure_area_corpus` | Persona + corpus seed | → `corpus_agent_instructions` / `AgentConfiguration`; get-or-create maps to the bootstrapper's. |

**Ports as a thin provider (irreducible code):**

| #1305 component | Pack slot | How |
|---|---|---|
| `BaseScraper` + Gaceta/TSJ/TCP scrapers | Source provider(s) | Each becomes a `BaseAuthoritySourceProvider` subclass. **Caveat:** #1305 scrapers are *listing-page crawlers* (discover new docs); providers are *citation-keyed* (resolve a known key). Per-site parse ports cleanly; bulk-discovery does not (see §7 Phase 2). |
| `classify_pdf_area` + `_SALA_TO_AREA` chamber heuristics | Provider logic | Genuinely novel, no core primitive — lives as logic inside the provider deciding which prefix/corpus a fetched ruling maps to. |

**Genuine gaps — no native home today:**

| #1305 component | Gap |
|---|---|
| `askBolivianLaw` orchestrator (one question → N area corpora → synthesize) | **`CorpusGroup` / `asearch_across_corpora` do not exist.** `AgentConfiguration` binds to one corpus. = #1444 Phase B, unbuilt. |
| `bolivian-laws-scrape-all` daily Celery-Beat entry | **No scheduling primitive.** `CELERY_BEAT_SCHEDULE` has zero crawl/enrichment entries; all ingestion is on-demand. = #1444 Phase A, unbuilt. |

**Contributor credit.** As committed in #1444's migration story: @jseborga's three
scrapers, dedup approach, eleven specialist personas, and `httpx.MockTransport`
testing pattern all port forward. The Phase-1 pack PR should credit them as
co-author.

## 7. Gaps and a phasing recommendation

| # | Gap | Severity | Needed for Bolivia? | Phase |
|---|---|---|---|---|
| 1 | Host allowlist is a hardcoded frozenset — a pack cannot open a new fetch host as data | **Blocker** (trivial fix) | Only with a live provider | **Shipped** — `pack.yaml` `source_hosts` (see update callout) |
| 2 | No scheduled/recurring scraping (`CELERY_BEAT_SCHEDULE` has no crawl entries) | Major | If continuous ingestion is in scope | Phase 3 (= #1444 Phase A) |
| 3 | Provider rail is citation-keyed; no listing-page bulk-discovery shape | Major | If publisher-crawl is in scope | **Phase 2 — shipped, issue #2054** |
| 4 | No multi-corpus orchestration (`CorpusGroup` / cross-corpus retrieval) | Major | No (per-area corpora work independently) | **Phase 4 — shipped, issue #2056** |
| 5 | Spanish / sala-aware classification has no core primitive | Minor | Spanish: no (data); sala-aware: with provider | Phase 1 handles Spanish via aliases/persona; sala-aware → Phase 2 provider code |
| 6 | Provider discovery scans one hardcoded package — no out-of-tree isolation | Minor | No | **Shipped** — in-pack providers + `AUTHORITY_PACK_PATHS` (see update callout) |
| 7 | Loader reads one default path; no multi-YAML merge; two baseline writers can collide on a prefix | Minor | No | **Shipped** — issue #2057 (see update callout) |

**Recommended phasing.** The pack's *core job* — taxonomy + provider + ingestion
of cited/known authorities — binds cleanly today. Everything beyond that is the
two primitives #1444 already identified as genuinely missing.

- **Phase 1 — the seed-based Bolivia pack (shipped in this PR).** Taxonomy YAML
  + per-area curated content seeds + personas, loaded by the generic
  `load_authority_pack` command. Recognises Bolivian citations and seeds
  public-domain content; no live fetch (so no provider and no host-allowlist
  edit). The live-fetch provider folds into Phase 2 because the Bolivian sources
  are listing-page, not key-addressable. *Handles the Spanish half of gap 5 via
  data.*
- **Phase 2 — listing-page discovery (shipped, issue #2054).**
  `BaseAuthorityDiscoveryProvider` crawls a publisher index for *unknown* new
  documents and seeds frontier rows via `AuthorityFrontierService
  .seed_from_discovery`, with one config-driven reference implementation
  (`ListingIndexDiscoveryProvider`). See the implementation-status callout
  above for the full shape. *Closes gap 3.*
- **Phase 3 — scheduled scraping (= #1444 Phase A).** A declarative
  "crawl publisher X into corpus Y nightly" surface (`PeriodicTask` / Beat sync).
  A core feature, not pack data. *Closes gap 2.*
- **Phase 4 — multi-corpus orchestration (shipped, issue #2056; = #1444
  Phase B).** `CorpusGroup` + `search_across_corpora`, restoring #1305's
  unified `askBolivianLaw` cross-area experience. See the
  implementation-status callout above for the full shape. *Closes gap 4.*

Phases 2–4 are independent and individually optional; Phase 1 delivers a working,
queryable Bolivia deployment on its own.

## 8. Open decisions

1. **Packaging isolation** — accept that a pack's provider module physically lives
   in core's `authority_source_providers/` package (Option 2), or invest in
   out-of-tree isolation (entry-point discovery + DB-driven host allowlist, gap 6)
   so packs never touch core's tree?
2. **Scope** — citation-driven only (Phase 1), or also bulk publisher discovery
   (Phase 2)? Resolved: Phase 2 shipped (issue #2054) as a generic engine; wiring
   a *verified* live rule for any specific publisher (Bolivia included) is left
   to an operator who has inspected that site's real markup.
3. **Scheduling** — is continuous nightly ingestion in scope (Phase 3), or does
   operator-triggered ingestion suffice?
4. **Unified query** — is the cross-area `askBolivianLaw` experience a requirement
   (Phase 4), or are per-area single-corpus agents acceptable?
5. **Host trust** — confirm which Bolivian government registrable domains
   (`gacetaoficialdebolivia.gob.bo`, `tsj.bo`, `tcpbolivia.bo`) are accepted as
   public-domain sources added to the allowlist.
6. **Namespace ownership** — pack namespaces as `source="baseline"` (loader-owned,
   overwritten on re-drop) or `source="manual"` (curator-owned, never clobbered)?

## 9. Relationship to 0001 / #1444

This proposal does not discard #1444 — it **re-homes its two genuinely-missing
primitives** onto the rail that shipped:

- #1444 **Phase A** (scheduled scraping) → this proposal's **Phase 3**, now framed
  as a scheduler over the *authority frontier/provider* rail rather than a new
  `scraping/` app with `ScrapedSource`/`ScrapedDocument` models.
- #1444 **Phase B** (`CorpusGroup` + `asearch_across_corpora`) → this proposal's
  **Phase 4**, unchanged in intent.

What #1444 could not yet assume — a pluggable fetch rail, a declarative taxonomy,
an idempotent corpus bootstrapper — now exists, which is why the bulk of #1305
collapses to *data* here instead of moving "verbatim" into a new app. A concrete,
buildable Phase-1 artifact is specified in the companion document:
[`0002-authority-packs-bolivia-spec.md`](./0002-authority-packs-bolivia-spec.md).
