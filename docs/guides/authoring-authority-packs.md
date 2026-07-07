# Authoring an Authority Pack

An **authority pack** is a single, self-contained directory that stands up a body
of law for a jurisdiction — its citation taxonomy, optional scraper, target
corpora, and agent personas — as **data + one small module**, with **no bespoke
Django app**. Because everything for one authority lives in one place, a pack is
**copy-to-add, delete-to-remove, copy-to-port**: drop the directory into another
OpenContracts install and the authority comes with it.

This is the operator/author how-to. For the management UI see
[Authority Console](../architecture/authority-console.md); for the
detection→discovery→crawl engine see
[Reference-Web Enrichment](../architecture/reference-web-enrichment.md); for the
original design rationale and the gap/phasing analysis see the proposal,
[0002 — Authority Packs](../architecture/proposals/0002-authority-packs.md).

## Anatomy of a pack

```
<pack>/
  pack.yaml                          # the manifest (below)
  authority_mappings.<name>.yaml     # taxonomy: prefixes / equivalences / rewrite_rules
  specs/<area>.json                  # curated section content (one doc per section)
  personas/<area>.txt                # agent persona → Corpus.corpus_agent_instructions
  providers/<name>_provider.py       # OPTIONAL: citation-keyed scraper (discovered from here)
  discovery_providers/<name>.py      # OPTIONAL: listing-index crawler (discovered from here)
```

The reference pack lives at
`opencontractserver/enrichment/data/authority_packs/bolivia/` — read it alongside
this guide; it is the canonical worked example (taxonomy + curated content +
Spanish persona; no scraper, because its sources are listing-page, not
key-addressable).

Each artifact binds to an existing extension seam, so the runtime needs **zero
changes** to accept a new pack:

| Slot | Lives in | Binds to | Required |
|---|---|---|---|
| Taxonomy (prefixes / equivalences / rewrite rules) | `authority_mappings.<name>.yaml` | `AuthorityNamespace` / `AuthorityKeyEquivalence` via `AuthorityMappingLoader` | one of taxonomy **or** corpora |
| Curated content (per legal area) | `specs/<area>.json` | `bootstrap_authority_corpus()` → keyed authority documents | optional |
| Agent persona (per corpus) | `personas/<area>.txt` | `Corpus.corpus_agent_instructions` | optional |
| Fetch provider ("scraper") | `providers/<name>_provider.py` | `BaseAuthoritySourceProvider`, discovered from the pack dir | optional |
| Discovery provider (listing-index crawler) | `discovery_providers/<name>.py` | `BaseAuthorityDiscoveryProvider`, discovered the same way | optional |
| Source hosts (for a scraper) | `pack.yaml` `source_hosts:` | the SSRF allowlist, merged at runtime | optional |
| Provider credentials | the `PipelineSettings` encrypted-secrets vault (**not** a pack file) | `get_component_settings()`, keyed by provider class path | optional |

**Secrets never live in a pack.** A scraper that needs an API key reads it from
the singleton `PipelineSettings` encrypted-secrets vault (keyed by the provider's
full class path), edited through System Settings — see the Authority Console's
*Scrapers & Credentials* tab. Pack files stay safe to commit and copy.

## The `pack.yaml` manifest

```yaml
name: bolivia                        # descriptive id
display_name: "Bolivia — Derecho del Estado Plurinacional"
jurisdiction: bo                     # descriptive (the real jurisdiction is per-prefix in the mappings YAML)
mappings: authority_mappings.bolivia.yaml   # optional: path (relative to the pack) to a taxonomy YAML
source_hosts:                        # optional: hosts a scraper may fetch from (widens the SSRF allowlist)
  - tcpbolivia.bo
corpora:                             # optional: one authority corpus per legal area
  - title: "Bolivia — Derecho Constitucional"
    spec: specs/constitucional.json          # required per entry: JSON section spec
    persona: personas/constitucional.es.txt  # optional
    preferred_embedder: "..."                # optional corpus model overrides
    preferred_llm: "..."
```

The taxonomy YAML (`mappings:`) uses the same schema as the shipped baseline
`opencontractserver/enrichment/data/authority_mappings.yaml`: `prefixes:`
(`display_name` / `jurisdiction` / `authority_type` / `aliases`), optional
`equivalences:` (`from_key`/`to_key`), and optional `rewrite_rules:`
(regex `pattern`/`replacement`). `jurisdiction` is free text (any value);
`authority_type` must be one of the controlled vocabulary in
`opencontractserver/enrichment/constants.py` (`ALL_AUTHORITY_TYPES`).

A section spec is `{aliases?: [..], sections: [{key, heading, text, source_url?}]}`
(`aliases` must be a list, never a bare string). The loader validates the **whole
pack before any DB write**, so a malformed spec/persona/host can never strand a
half-loaded pack.

## Shipping a scraper inside the pack

A live-fetch provider is the one irreducibly-Python slot (every source's HTML/XML/
API shape differs). It now lives **with its pack**, under `<pack>/providers/`,
instead of in core's `pipeline/authority_source_providers/`:

1. Subclass `BaseAuthoritySourceProvider`
   (`opencontractserver/pipeline/base/base_authority_source_provider.py`):
   declare `supported_prefixes` / `license` / `priority` / `requires_approval` /
   `enabled` as class attributes, and implement the pure `_locate_impl`
   (canonical key → request plan) and `_fetch_impl` (request → sections). The
   shipped `cfr_provider.py` / `us_code_provider.py` / `federal_register_provider.py`
   are worked references.
2. Drop the module in `<pack>/providers/`. The pipeline registry discovers it from
   the pack directory at startup — no registration call, no edit to core.
3. List the source's host(s) in `pack.yaml` `source_hosts:`. Every fetch stays
   SSRF-gated (HTTPS-only, public-IP, per-redirect revalidation, size caps); the
   pack only widens **which** hosts are reachable, and only once you install it
   (the install IS the trust decision; each added host is logged).
4. Put any credentials in the secrets vault (above), never in the pack.

All sources must be **public-domain**; the gate blocks any other license.

## Discovering UNKNOWN documents (listing-index crawl)

A `BaseAuthoritySourceProvider` needs a *known* `canonical_key` — it cannot find
documents nobody has cited yet. For a publisher whose site is a browsable
listing/index (not key-addressable) — the motivating case is Bolivia's Gaceta
Oficial, per [0002 — Authority Packs](../architecture/proposals/0002-authority-packs.md)
§7 — use `BaseAuthorityDiscoveryProvider`
(`opencontractserver/pipeline/base/base_authority_discovery_provider.py`)
instead. It crawls index page(s) and lists candidates (canonical_key + url +
metadata) *without* fetching or ingesting them; `AuthorityFrontierService
.seed_from_discovery` then queues the candidates for the normal discovery
runtime.

The shipped reference implementation, `ListingIndexDiscoveryProvider`
(`opencontractserver/pipeline/authority_discovery_providers/listing_index_provider.py`),
is config-driven and jurisdiction-agnostic: supply a `ListingIndexRule` (a link
regex + a canonical-key template) rather than writing new code. Ship one in
`<pack>/discovery_providers/*.py` (discovered the same way as `providers/`) only
if a publisher's markup needs bespoke parsing beyond that rule.

The operator surface is the `discover_authority_candidates` management command
(`--index-url` / `--link-pattern` / `--canonical-key-template` / `--prefix`, plus
`--dry-run` to preview before seeding) — there is no admin UI for discovery
(scope of issue #2054); see the command's docstring for a worked example.

## Add / remove / copy

**Add (in-tree).** Commit the pack directory under
`opencontractserver/enrichment/data/authority_packs/`. Load its DB-side
(taxonomy + content + personas):

```bash
docker compose -f local.yml run --rm django python manage.py load_authority_pack \
  --path opencontractserver/enrichment/data/authority_packs/<pack> \
  --creator <username> --public
```

`load_authority_pack` is idempotent and re-runnable (unchanged content is skipped,
changed text version-ups, curator edits are never clobbered). Restart so the
registry/SSRF allowlist pick up any `providers/` module and `source_hosts`.

**Add (out-of-tree / copy to another install).** Place the pack directory
anywhere and point the install at it with the `AUTHORITY_PACK_PATHS` setting (a
list of pack directories; env var `AUTHORITY_PACK_PATHS`, comma-separated), then
run `load_authority_pack --path <dir> ...` and restart. The pack's provider and
hosts travel with the directory — nothing in core needs editing. This is how a
pack ports to another system.

**Remove.** Delete the pack directory (or drop it from `AUTHORITY_PACK_PATHS`) and
restart — its provider and `source_hosts` stop being discovered immediately. The
already-loaded taxonomy/content rows persist (the loader upserts, it does not
delete prefixes dropped from a YAML); remove them deliberately via the Authority
Console if you want them gone.

## Prefix ownership (what a re-load can and cannot clobber)

Namespace rows are ownership-partitioned so no writer silently overwrites
another (issue #2057):

- A **curator edit** through the console stamps `source="manual"` — no loader
  run ever touches the row again.
- A **corpus-linked** namespace (`is_global=False`) is bootstrap-owned — same.
- A **baseline** row is stamped with the writer that loaded it
  (`AuthorityNamespace.baseline_origin`: the pack's manifest `name`, or `"core"`
  for the shipped `authority_mappings.yaml`). Re-loading the same pack updates
  its own rows (its YAML stays authoritative); a load that hits a prefix a
  *different* origin owns **skips it with a warning** (counted as
  `skipped_foreign_baseline` in the command output) — first writer wins. Resolve
  a genuine collision by dropping the prefix from one YAML, or by curating the
  row through the console (making it manual-owned). The pack name `core` is
  reserved for the shipped baseline, and a pack's `name:` must be **unique
  across every installed pack directory** (in-tree + `AUTHORITY_PACK_PATHS`):
  two directories declaring the same name are treated as the same pack — they
  co-own their prefixes with no collision guard between them.

To converge the whole installed taxonomy — the shipped baseline plus every
installed pack's mappings — in one idempotent run (e.g. after editing several
packs' YAMLs):

```bash
docker compose -f local.yml run --rm django python manage.py load_authority_mappings --include-packs
```

`load_authority_pack` stays the full per-pack loader (taxonomy **+ content +
personas**); `load_authority_mappings --include-packs` re-converges taxonomy
only, across every installed pack at once.

## Carrying a jurisdiction's citation vocabulary in the pack

Beyond `prefixes`/`equivalences`/`rewrite_rules`, a pack's mappings YAML may carry
two optional sections so a new jurisdiction's *citation vocabulary* travels with
the pack (merged onto the shipped Python baseline at runtime; the baseline always
wins a collision — a pack extends, never overrides):

```yaml
# in <pack>/authority_mappings.<name>.yaml
shape_rules:                       # classify a numbered prefix family without a core edit
  - pattern: '^bo-ley-\d+$'        # e.g. bo-ley-1234
    jurisdiction: bo
    authority_type: statute        # must be one of ALL_AUTHORITY_TYPES

abbreviations:                     # Bluebook-style abbreviations the Tier-2a extractor matches
  state:
    "Bol. Civ. Code":
      prefix: bo-civ
      jurisdiction: bo
      authority_type: statute
  municipal:
    "La Paz Mun. Code":
      prefix: muni-la-paz
      jurisdiction: bo-la-paz
      authority_type: municipal-ordinance
```

These are read from every installed pack (in-tree + `AUTHORITY_PACK_PATHS`) and
validated fail-fast by `load_authority_pack`. Tests:
`test_authority_pack_taxonomy.py`.

## What is still core (shared engine vocabulary)

Two things stay in the engine rather than per-pack, by design — they are *shared
vocabulary*, not per-authority config:

- The **`authority_type` controlled vocabulary** (`ALL_AUTHORITY_TYPES`): every
  pack draws its types from this one shipped set (it is wired into model field
  `choices`); a pack picks a type, it does not invent one.
- The **Tier-2a citation-*form* parsing grammars** (the regexes in `grammars.py`
  that turn `"15 U.S.C. § 78j"` into a canonical key): these are parsing *logic*,
  not authority *configuration*. A pack declares its prefixes/aliases (Tier-1) and
  its shape-family classification + abbreviations (above) as data; only a genuinely
  new citation *form* would need a grammar change in core.

## Verify the load

- Authority Console → **Registry** tab: the pack's prefixes appear as
  `AuthorityNamespace` rows (scope/jurisdiction/type/aliases).
- Authority Console → **Scrapers** tab: a shipped provider appears with its
  prefixes / license / priority / credential status.
- The seeded corpora are queryable, each answering in its pack persona.

Tests for the mechanics live in `opencontractserver/tests/test_authority_pack.py`,
`test_authority_pack_providers.py`, and `test_authority_source_hosts.py`.
