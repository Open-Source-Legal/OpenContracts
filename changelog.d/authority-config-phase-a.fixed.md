- **Authority namespace re-seed no longer clobbers curator edits.** The
  `post_migrate` convergence in `opencontractserver/enrichment/_namespace_seed.py`
  (`ensure_seeded` → `seed`) ran on every production `migrate` and every test
  flush and `update_or_create`d every shipped-prefix `AuthorityNamespace`
  unconditionally — silently reverting a curator's `source="manual"` console edits
  (display_name / jurisdiction / authority_type / aliases) and re-forcing
  `is_global=True` on the next deploy, defeating the Authority Console's headline
  "a re-load can no longer clobber a curator's runtime edits" guarantee. The seed
  now honours the same source-ownership partition as
  `AuthorityMappingLoader.load_namespaces` (skip `source="manual"` and
  corpus-linked rows), guarded on the `source` column's presence so the historical
  0082/0085/0086/0090 seed states are unaffected. Regression tests in
  `test_authority_mapping_loader.py::NamespaceReseedOwnershipTests`.
- **`authority_mappings` reader rejects self-referential equivalences.**
  `enrichment/data/mappings.py::iter_equivalences` now raises `ValueError` for a
  `from_key == to_key` pair (matching the DB `CheckConstraint`) instead of
  counting it into `total` and then silently dropping it in the loader.
- **Removed dead code in the authority crawl.** The per-jurisdiction-cap parking
  in `crawl_authorities_service.py` now routes through the previously-unused
  `_park_for_cap` helper (DRY; behaviour-preserving).
