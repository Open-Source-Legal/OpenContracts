- **One-command multi-YAML taxonomy merge (issue #2057).**
  `manage.py load_authority_mappings --include-packs` now converges the shipped
  core baseline **plus every installed authority pack's mappings YAML** (in-tree
  `authority_packs/` + `AUTHORITY_PACK_PATHS`) in one idempotent run, each file
  stamped with its writer origin (`AuthorityMappingLoader.load_installed`,
  reusing `authority_pack_config.iter_pack_mapping_files` — now public and
  yielding the parsed manifest — for pack discovery). Core loads first, so on a
  same-prefix collision the shipped baseline wins and the pack's claim is
  skipped + warned, mirroring the shape-rules/abbreviations merge rule.
  Per-origin summaries (including `skipped_foreign_baseline`) are printed for
  both commands (`load_authority_mappings`, `load_authority_pack`). Docs:
  "Prefix ownership" section in `docs/guides/authoring-authority-packs.md`;
  gap 7 closed in `docs/architecture/proposals/0002-authority-packs.md` §7.
  Tests: `test_authority_mapping_loader.py::LoadInstalledTests` +
  command tests.
