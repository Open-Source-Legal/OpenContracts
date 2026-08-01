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
  worked example the format needs, and the pack machinery is unchanged.
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
