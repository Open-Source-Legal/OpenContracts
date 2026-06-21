- **Authority Console — Phase 1 (namespace management API).** Added a runtime
  management surface for `AuthorityNamespace` (the registry of bodies of law whose
  aliases drive Tier-1 citation extraction), which previously had **no** GraphQL,
  admin, or GUI surface and was editable only by hand-editing
  `authority_mappings.yaml` + re-running the loader. New
  `AuthorityNamespaceService` (`opencontractserver/enrichment/services/authority_namespace_service.py`)
  provides superuser-gated create / update / delete / `set_aliases` plus faceted
  `stats` and a string-joined `detail` projection that assembles one authority's
  namespace + aliases + in/out key-equivalences + discovery-frontier rows +
  reference demand (joined colon-anchored on `"<prefix>:"` / `authority=prefix`,
  since the authority models have no FKs between them). Exposed via
  `authorityNamespaces` (relay connection), `authorityNamespaceStats`,
  `authorityNamespaceDetail(prefix)`, and `create/update/setAliases/delete
  AuthorityNamespace` mutations (`config/graphql/authority_namespace_mutations.py`).
- **Single authority-admin permission gate.** New
  `opencontractserver/enrichment/services/authority_permissions.py::is_authority_admin`
  is now the one definition every authority surface funnels through; repointed the
  inline `is_superuser` checks on `AuthorityFrontierNode` / `AuthorityKeyEquivalenceNode`
  `get_queryset`, `AuthorityKeyEquivalenceService`, `AuthorityFrontierService.admin_state_counts`,
  and `RunAuthorityDiscoveryMutation` to it (single seam to widen the role later).

### Fixed
- **Loader no longer clobbers admin-edited namespaces.** `AuthorityNamespace`
  gained a `source` ownership marker (`baseline`/`manual`, migration
  `annotations/0099`) mirroring `AuthorityKeyEquivalence.source`;
  `AuthorityMappingLoader.load_namespaces` now skips `source="manual"` rows, so a
  re-load of `authority_mappings.yaml` can no longer silently overwrite a
  curator's runtime edits to a shipped body of law (the loader previously
  `update_or_create`d every non-corpus-linked global prefix). Also added
  `AuthorityNamespace.created_by` for edit provenance.
