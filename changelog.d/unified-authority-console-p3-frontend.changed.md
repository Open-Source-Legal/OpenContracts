- **Authority Console — Phase 3 frontend (discovery queue absorption).** The
  standalone `/admin/authorities` panel (`AuthoritySourcesMonitor.tsx`) is now
  **absorbed** into the console's **Discovery Queue** tab and **deleted** (panel +
  CT + test wrapper + route + export). The tab reuses the shared console chrome +
  `FacetedStatsChips` + `useFacetedRelayList` and adds **per-row admin verbs** —
  requeue / reset / reroute / approve (on `pending_approval`) / delete — wired to
  the Phase-3 `AuthorityFrontierService` mutations, alongside the existing
  multi-select "Run discovery" and a bulk delete. Frontend mutation docs added to
  `frontend/src/graphql/mutations.ts`. Playwright CT cover the discovery-queue
  render + per-row verbs.
