- **Authority crawl now bridges popular-name citations to their statutory
  equivalents instead of marking them `unsupported`.** Filings cite domain keys
  (`exchange-act:10`, `securities-act:2`) but the source providers only
  `can_handle` positive-law canonical keys (`usc-*`, `cfr-*`, `fedreg`). The
  curated `AuthorityKeyEquivalence` table (e.g. `exchange-act:10 → usc-15:78j`)
  was consulted only *after* ingest (the relink seam), so the frontier row was
  marked `unsupported` before the equivalence could help — every popular-name
  citation died at provider selection.
  `AuthorityDiscoveryService._provider_for` (`opencontractserver/enrichment/services/authority_discovery_service.py`)
  now returns a `fetch_key`: when no provider handles the domain key directly,
  it resolves a provider-supported `AuthorityKeyEquivalence` counterpart and
  fetches/verifies under that (the existing post-ingest relink then upgrades the
  original domain-key EXTERNAL references). `discover_and_bootstrap` locates and
  gate-verifies against `fetch_key`; the frontier row keeps its own
  `canonical_key` identity. Tests: `test_authority_discovery.py::ProviderForEquivalenceBridgeTests`.
  - Scope/known gap: this covers authorities with curated equivalences
    (Exchange Act, Securities Act → 15 U.S.C.). `sec-rule:*` (→ 17 C.F.R. 230/240),
    `irc:*` (→ 26 U.S.C.), and state law like `dgcl:*` still have no provider
    coverage and remain `unsupported` — follow-up work (equivalence seeds or a
    dedicated provider).
