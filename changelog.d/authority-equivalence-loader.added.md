- Authority key equivalences are now maintained in a single declarative
  `opencontractserver/enrichment/data/authority_mappings.yaml`, loaded idempotently
  by `AuthorityMappingLoader` / `manage.py load_authority_mappings` (and a
  re-runnable data migration) as `source="baseline"`. The loader is source-scoped —
  it never clobbers a runtime `source="manual"` override. Closing an "unsupported"
  authority (e.g. `irc:401 → usc-26:401`, `exchange-act:10d → usc-15:78j-4`) is now
  a one-line YAML edit + reload instead of a hand-written migration. Adds the
  `baseline` source choice to `AuthorityKeyEquivalence`.
