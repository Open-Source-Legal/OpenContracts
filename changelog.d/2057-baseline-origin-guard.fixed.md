- **Baseline-vs-baseline namespace clobbering fixed (issue #2057).** Two
  `source="baseline"` writers on the same authority prefix — the core
  `authority_mappings.yaml` vs. a pack's mappings YAML, or two packs — previously
  last-write-wins'd each other silently
  (`AuthorityMappingLoader.load_namespaces`' `update_or_create` had no writer
  partition). Every baseline `AuthorityNamespace` row is now stamped with its
  writer origin (new nullable `baseline_origin` column, migration
  `annotations/0101`; `"core"` for the shipped YAML / `post_migrate` seed, else
  the pack's manifest `name`), and a load skips + warns (counted as
  `skipped_foreign_baseline`) instead of overwriting a prefix a different origin
  owns — first writer wins; curator `manual` rows still trump everything. The
  `post_migrate` convergence (`opencontractserver/enrichment/_namespace_seed.py`)
  honours the same guard, so a `migrate`/flush can no longer revert a pack-owned
  prefix to the constants baseline. Legacy baseline rows (null origin) are
  adopted — stamped — by the next owning load. The pack name `core` is reserved
  (`load_authority_pack` rejects it fail-fast). Re-loading two packs that touch
  distinct prefixes can never clobber each other. Tests:
  `opencontractserver/tests/test_authority_mapping_loader.py::BaselineOriginGuardTests`
  and the reseed-ownership additions in the same file.
