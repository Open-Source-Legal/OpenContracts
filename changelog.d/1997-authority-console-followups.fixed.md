- **Authority Console — review follow-ups (gap/omission fixes).**
  - **Registry list N+1 eliminated.** `GET_AUTHORITY_NAMESPACES`
    (`frontend/src/graphql/queries.ts`) no longer selects `effectiveProvider` /
    `equivalenceCount` / `frontierCount` — three per-row resolver-backed fields
    (each fires its own COUNT / `can_handle()` loop in
    `config/graphql/annotation_types.py:AuthorityNamespaceNode`) that the master
    table never rendered, so a 50-row page no longer triggers ~150 wasted
    queries. They remain on `GET_AUTHORITY_NAMESPACE_DETAIL`.
  - **Frontier admin verbs guard `in_progress`.**
    `AuthorityFrontierService.requeue/reset/reroute`
    (`opencontractserver/enrichment/services/authority_frontier_service.py`) now
    refuse a row a crawl worker is actively ingesting (matching `approve`'s
    state guard), so an admin can no longer flip an `in_progress` row back to
    `queued` mid-pass.
  - **Malformed `authorityCorpusId` is now an error, not a silent global.**
    `createAuthorityNamespace` / `updateAuthorityNamespace`
    (`config/graphql/authority_namespace_mutations.py`) return
    `ok=false, "Invalid authority_corpus_id."` when a non-empty corpus global id
    fails to decode, instead of silently creating a global namespace (create) or
    unlinking the corpus (update). An explicit `""` still clears the link.
  - **Deleted-panel routes redirect instead of 404.**
    `/admin/authorities`, `/admin/authority-mappings`, and `/admin/enrichment`
    now `Navigate` to the equivalent console tab (`frontend/src/App.tsx`); the
    user docs (`docs/guides/ingesting-authorities.md`,
    `docs/architecture/reference-web-enrichment.md`) were repointed to
    `/admin/authority`.
  - **Reroute is constrained to the registry.** The Discovery Queue reroute
    (`frontend/src/components/admin/authority/DiscoveryQueueTab.tsx`) validates
    the chosen provider against `authoritySourceProviders` client-side (fail-fast
    on a typo) and seeds the provider filter from the full registry rather than
    only the providers on the loaded page.
  - **DRY + dead-code cleanup.** Extracted the duplicated namespace-search
    predicate into `authority_namespace_search_q()` (shared by
    `AuthorityNamespaceService.stats()` and `config/graphql/filters.py` so chip
    counts can never desync from the list); removed the orphaned
    `AUTHORITY_DISCOVERY_POLL_MS` / `_WINDOW_MS` constants (only the deleted
    `AuthoritySourcesMonitor` used them); and corrected stale `discovery_state`
    vocabulary (`discovered`/`resolved` retired by migration 0100) in the
    `GovernanceGraphNode` GraphQL schema description + frontend type comments.
  - **Tests.** Added GraphQL-layer coverage for the five frontier mutations + the
    `authoritySourceProviders` query, the `in_progress` guard, both remaining
    `mark()` mutual-exclusivity pairs, the malformed-corpus-id rejection, and a
    Registry create-form Playwright CT.
