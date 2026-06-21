- Extended the declarative `authority_mappings.yaml` into the full "configure &
  maintain" surface for legal authority mappings:
  - **Namespaces collapsed into the YAML** — `prefixes:` now drives the
    `AuthorityNamespace` registry *and* the in-memory
    `AUTHORITY_PREFIX` / `PREFIX_CLASSIFICATION` / `PREFIX_DISPLAY_NAME` maps in
    `enrichment.constants` (derived at import from the pure reader
    `enrichment/data/mappings.py`), replacing the three hand-maintained dicts as
    the source of truth. `AuthorityMappingLoader.load_namespaces()` /
    `load_all()` upsert global registry rows idempotently (migration 0093),
    skipping corpus-linked namespaces.
  - **Runtime CRUD + admin panel** — superuser-only
    `AuthorityKeyEquivalenceService` (forced `source="manual"`, `created_by`
    provenance, `prefix:section` key-grammar validation, manual-only
    edit/delete) behind GraphQL `authorityKeyEquivalences` connection +
    `authorityMappingStats` + create/update/delete mutations, surfaced as a new
    `/admin/authority-mappings` React panel. Adds a nullable `created_by` FK to
    `AuthorityKeyEquivalence` (migration 0094).
  - **Auto-derivation** — `manage.py import_popular_name_table` harvests
    `stat: ↔ usc:` bridges (`source="popular_name"`) from the OLRC popular-name
    table, and the US Code provider now parses each ingested section's USLM
    `<sourceCredit>` to upsert `publ:`/`stat: ↔ usc:` bridges
    (`source="uslm"`). A shared source-scoped writer guarantees no importer ever
    overwrites a row owned by a different source.
  - **Prefix rewrite rules** — optional `rewrite_rules:` (e.g.
    `irc:N → usc-26:N`) are evaluated as a fallback in `_provider_for` *and*
    `find_authority_target` after explicit per-key equivalences (per-key wins),
    previewable via `manage.py preview_rewrite_rule` before going live.
