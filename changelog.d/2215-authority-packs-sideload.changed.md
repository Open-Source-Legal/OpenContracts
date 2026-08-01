- **Authority packs are deployment data, and the tree now says so.** The four
  Texas / large-load packs (`texas_electric_law`, `puct_electric`,
  `ercot_large_load`, `oncor_delivery` — ten corpora, their providers, charters,
  specs, personas, relationship declarations and rights fixtures) are no longer
  shipped in `opencontractserver/enrichment/data/authority_packs/`. They were
  **moved, not deleted**, to their own repository (`Authorities/TX_Large_Loads`),
  alongside the four test modules that assert their data contract, source plans,
  provider parsers and load identities. A body of regulation has its own
  legal-review state, refresh cadence and publisher relationships; shipping one
  in the product meant every install carried — and every worker imported the
  providers of — one deployment's regulatory topology. `bolivia` remains as the
  worked example the format needs, and the pack machinery is unchanged. The
  corpus-group manifests that composed these ten corpora, and the evaluation
  commands that graded runs over them, went to their own repositories earlier on
  this branch for the same reason; none of them ever appeared in a release.
- **Added `AUTHORITY_PACK_ROOTS`** (env var, comma-separated, empty by default):
  directories *of* packs, the same shape as the in-tree root, so a pack
  repository mounts with one variable instead of one entry per pack.
  `AUTHORITY_PACK_PATHS` (individual pack directories) is unchanged and both are
  honoured; `pipeline/registry.py::authority_pack_dirs` now de-duplicates by
  resolved path, so a pack reachable through both is registered once rather than
  importing its providers twice under the same generated module name.
- **Added `load_authority_pack --check`**: runs the same validation as the
  Authority Console preflight — manifest fingerprint, declared source hosts,
  approval state, per-corpus plan — and writes nothing, exiting non-zero on an
  invalid pack. The Console preflight needs an authority-admin browser session;
  a headless deployment installing a pack it did not author had no equivalent.
- **Fixed: a sideloaded pack could not import its own modules.** In-pack
  component modules are imported by file path, so their parent packages did not
  exist and `from ..helper import x` had nothing to resolve against; a pack in
  the tree hid this by also being importable as a real Python package, so two of
  the four packs reached their own pack-root helpers by absolute dotted path and
  silently failed to register 15 providers the moment they were sideloaded.
  `pipeline/registry.py` now creates each pack's parent packages (shared across
  component families, so one pack helper is one module object however many
  families import it, and re-pointed on every discovery pass so `reset_registry`
  and a swapped pack directory stay correct). The now-redundant `module_ns`
  parameter of `_discover_pack_component_classes` is gone — the component
  subdirectory name already disambiguates the two families.
- **Fixed: re-mounting a pack name from a new directory served the old pack's
  helper.** The synthetic parent package is keyed by pack name, and an import
  resolves against `sys.modules` before consulting that package's `__path__`, so
  re-pointing the path alone left cached submodules from the previous directory
  in place. Cached submodules are now dropped when the path actually changes.
  Covered by
  `PackSiblingImportTests::test_same_pack_name_from_a_new_directory_reloads_its_helper`,
  which fails against the un-purged version.
