- Hardened authority-mapping resolution + the source-ownership partition:
  - `AuthorityMappingLoader.load` now skips *any* pre-existing equivalence whose
    `source` is not `baseline` (not just `manual`), so a baseline reload can
    never clobber an importer-owned `uslm` / `popular_name` row — matching the
    documented "a writer never overwrites another source's row" invariant
    (`opencontractserver/enrichment/services/authority_mapping_loader.py`). The
    loader summary key is renamed `skipped_manual → skipped_owned`.
  - `AuthorityDiscoveryService._provider_for` now composes the equivalence hop
    *and* the prefix rewrite rules over a single ordered candidate set (direct →
    equivalence → rewrite → equivalence+rewrite), so it resolves an equivalence
    that points into a rewriteable key — symmetric with `find_authority_target`
    — and the equivalence query is now `order_by`-ed so the counterpart chosen
    for a one-to-many key is deterministic
    (`opencontractserver/enrichment/services/authority_discovery_service.py`).
