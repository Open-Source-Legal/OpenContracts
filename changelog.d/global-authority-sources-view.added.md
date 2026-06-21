- **Global authority-sources monitor** (`/admin/authorities`, superuser-only) —
  a read-only, instance-wide view of the `AuthorityFrontier` discovery queue:
  the crawl/ingestion state of every wanted section-root canonical key (cited
  law) across all corpora. Two lenses over one table — clickable state-count
  chips (operational monitor: queued / in_progress / discovered / ingested /
  failed / unsupported / blocked_license / unlocated / pending_approval /
  deferred_cap) and a `-mention_count` default order (ingestion backlog:
  most-cited-but-not-ingested) — with jurisdiction / type / provider filters and
  a canonical-key search. Closes the gap where authority-source ingestion status
  was only visible per-corpus (on reference-web ghost nodes); triggering still
  lives in the per-corpus `/admin/enrichment` runner.
  - Backend (`config/graphql/`): `AuthorityFrontierNode` (relay connection,
    superuser-gated `get_queryset`, backlog-first order), `AuthorityFrontierFilter`
    (explicit `CharFilter`s so `discovery_state`/`authority_type` are plain
    `String` args — not the model's `choices` enum — matching the chips' raw
    values), and `authorityFrontier` + `authorityFrontierStats` queries on the
    annotations `Query`; aggregation routed through
    `AuthorityFrontierService.admin_state_counts`.
  - Frontend: `AuthoritySourcesMonitor.tsx` (reuses the Ingestion Monitor admin
    shell), `GET_AUTHORITY_FRONTIER` + `GET_AUTHORITY_FRONTIER_STATS`, the
    `/admin/authorities` route, and an "Authority Sources" card on the
    `/admin/settings` grid.
  - Tests: `test_authority_frontier_query.py` (gating, filters, default order,
    facet-aware stats) and `AuthoritySourcesMonitor.ct.tsx` (chips, rows,
    chip-driven filtering, access-denied, empty state).
