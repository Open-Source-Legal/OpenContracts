- **Authority discovery providers (Phase 2 of the Authority Packs proposal, closes #2054).**
  Added `BaseAuthorityDiscoveryProvider`
  (`opencontractserver/pipeline/base/base_authority_discovery_provider.py`): unlike
  the citation-KEYED `BaseAuthoritySourceProvider`, a discovery provider crawls a
  publisher's index/listing page(s) for documents nobody has cited yet and lists
  candidates (`DiscoveryCandidate`: canonical_key + url + metadata) without
  fetching or ingesting them. Mirrors the existing `locate`/`fetch` split as
  `_fetch_index_impl` (I/O, SSRF-gated via `safe_fetch_text`) /
  `_parse_index_impl` (pure). `discover_candidates()` is bounded by
  `enrichment.constants.DISCOVERY_DEFAULT_MAX_CANDIDATES` /
  `DISCOVERY_MAX_MAX_CANDIDATES`, de-dupes by canonical_key across pages, records
  per-URL fetch failures (including SSRF rejections) in `skipped_index_urls`
  rather than aborting the whole run, and refuses to run unless
  `license == "public-domain"`.
- Added one reference implementation, `ListingIndexDiscoveryProvider`
  (`opencontractserver/pipeline/authority_discovery_providers/listing_index_provider.py`):
  a config-driven, jurisdiction-agnostic regex+template crawler — a publisher
  supplies a `ListingIndexRule` (link regex + canonical-key template), not new
  code. Illustrated/tested against a synthetic, Gaceta-Oficial-*shaped* fixture
  (Bolivia is the proposal's motivating case), not a verified live scraper.
- Added `AuthorityFrontierService.seed_from_discovery`
  (`opencontractserver/enrichment/services/authority_frontier_service.py`): the
  idempotent frontier-seeding entrypoint for discovery candidates, mirroring
  `seed_child_keys`'s contract exactly — a `canonical_key` that already has a
  row (any depth/state) is skipped, so re-running never duplicates rows and
  never resets an in-flight row's `discovery_state`.
- Extended the pipeline registry (`opencontractserver/pipeline/registry.py`) to
  auto-discover `BaseAuthorityDiscoveryProvider` subclasses the same way as
  `BaseAuthoritySourceProvider` — core `authority_discovery_providers/` package
  plus in-pack `<pack>/discovery_providers/*.py` — via a generalized
  `_discover_pack_component_classes` helper (replacing the source-provider-only
  `_discover_pack_provider_classes`). New `ComponentType.AUTHORITY_DISCOVERY_PROVIDER`
  and `get_all_authority_discovery_providers_cached()`.
- Added the `discover_authority_candidates` management command
  (`opencontractserver/annotations/management/commands/discover_authority_candidates.py`)
  as the operator entrypoint (`--index-url` / `--link-pattern` /
  `--canonical-key-template` / `--prefix` / `--max-candidates` / `--dry-run`) —
  no admin UI, by design (deferred alongside Phase 3/4 scheduling and
  multi-corpus orchestration).
