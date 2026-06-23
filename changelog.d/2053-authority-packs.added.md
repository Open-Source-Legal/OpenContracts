- **Authority packs (Phase 1, seed-based).** A drop-in bundle format that stands
  up a jurisdiction's body-of-law as data on the existing Authority architecture
  — no bespoke app. Adds the generic `load_authority_pack` management command
  (`opencontractserver/corpuses/management/commands/load_authority_pack.py`),
  which reads a `pack.yaml` manifest and idempotently (1) loads the pack's
  `authority_mappings` YAML into `AuthorityNamespace` via
  `AuthorityMappingLoader.load_all(path=…)`, (2) bootstraps one authority corpus
  per legal area from a JSON section spec via `bootstrap_authority_corpus`, and
  (3) writes each area's persona into `Corpus.corpus_agent_instructions`.
  `--path` accepts any directory, so out-of-tree packs load identically. Ships a
  reference **Bolivia** pack
  (`opencontractserver/enrichment/data/authority_packs/bolivia/`) with the
  five-prefix taxonomy (`jurisdiction: bo`), a seeded `constitucional` corpus
  (CPE articles), and a Spanish persona — repackaging PR #1305 (@jseborga) as
  data rather than a standalone app. The live-fetch source provider is deferred
  to Phase 2 (#2054), since the Bolivian publishers are listing-page, not
  key-addressable. Design: `docs/architecture/proposals/0002-authority-packs.md`;
  tests: `opencontractserver/tests/test_authority_pack.py`.
