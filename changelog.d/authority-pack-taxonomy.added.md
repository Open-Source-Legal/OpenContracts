- **Authority packs can carry their jurisdiction's citation vocabulary.** A pack's
  authority-mappings YAML may now declare two optional sections — `shape_rules:`
  (classify a numbered prefix family, e.g. `bo-ley-<n>`, without a core edit) and
  `abbreviations:` (`state`/`municipal` Bluebook abbreviations the Tier-2a
  extractor matches). They are read from every installed pack (in-tree +
  `AUTHORITY_PACK_PATHS`) and merged onto the shipped Python baseline at runtime
  (`classify_prefix` consults pack shape rules; `GenericCitationExtractor` merges
  pack abbreviations), so a jurisdiction's citation vocabulary travels *with* the
  pack — the baseline always wins a collision (a pack extends, never overrides).
  Malformed entries are logged + skipped at runtime and rejected fail-fast by
  `load_authority_pack`. New module
  `opencontractserver/enrichment/services/authority_pack_config.py`; tests in
  `test_authority_pack_taxonomy.py`. The shared `authority_type` vocabulary and the
  citation-*form* parsing grammars remain core (shared vocabulary / parsing logic,
  not per-authority config).
