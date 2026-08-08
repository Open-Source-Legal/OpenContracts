- **Authority-pack tests now exercise the loader, not one jurisdiction's data.**
  The five `test_grid_dossier_*` modules asserted pack machinery through the
  shipped Texas packs, so removing the packs would have removed the coverage
  with them. They are replaced by a complete, deliberately fictional schema-v2
  fixture pack (`opencontractserver/tests/fixtures/authority_packs/example_utility`
  — two corpora, taxonomy, charters, specs, personas, typed metadata schema,
  relationships and a source plan) and:
  - `test_authority_pack_loader.py` — corpus/taxonomy/metadata-schema/relationship
    convergence, idempotency and curator-state preservation, atomic abort, and
    prefix-binding validation, all against the fixture pack.
  - `test_authority_discovery_runtime.py` (renamed from
    `test_grid_dossier_discovery_runtime.py`) — unchanged in substance; it always
    defined its own providers and only *named* them after a jurisdiction.
  - `test_authority_pack_sideload.py` (new) — the sideload contract itself:
    bundle-root discovery, precedence, de-duplication across overlapping
    settings, a misconfigured entry being skipped rather than raised, and
    `--check` reporting a plan without writing.
  The fixture pack lives under `tests/fixtures/` rather than the in-tree pack
  root on purpose: `authority_pack_dirs()` enumerates every immediate
  subdirectory of that root, so a fixture placed there would ship as an
  installable pack in every deployment's Authority Console catalog.
  The three modules that asserted the packs' own identities moved out with the
  packs, including the one whose `authority_corpus_id is None` assertion was
  failing before this branch began.
