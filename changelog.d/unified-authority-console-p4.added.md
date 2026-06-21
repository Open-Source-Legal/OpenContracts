- **Authority Console — Phase 4 (scrapers visibility + dead-state retirement).**
  Added a read surface for the authority **source providers** (the "scrapers"):
  `AuthoritySourceProviderService.list_providers` + the `authoritySourceProviders`
  GraphQL query expose the auto-discovered providers (US Code / eCFR / Federal
  Register / agentic web locator) with their supported prefixes, license,
  priority, `enabled` / `requires_approval` flags, and a `has_credentials` flag
  derived from the existing encrypted-secrets vault — surfaced read-only in the
  console's new **Scrapers** tab. The providers previously had no DB row and no
  API surface at all (fully invisible to operators). Credentials remain edited
  through the single existing component-secrets vault (System Settings), not a
  parallel store.

### Removed
- **Retired the dead `discovered` / `resolved` AuthorityFrontier states**
  (migration `annotations/0100`). No production code path ever assigned them
  (discovery jumps `in_progress → ingested`; the resolution outcome lives on the
  relink result / `Analysis`, not the frontier row), so they were a
  dead-vocabulary trap in `DISCOVERY_STATE_CHOICES`; removed from the model and
  the frontend state-tone vocab.
