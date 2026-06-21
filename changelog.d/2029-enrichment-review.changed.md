- **The enrichment job list no longer silently truncates history (issue #2029 —
  PR #2008 review).** `GET_CORPUS_ANALYSES` now requests `totalCount`
  (`frontend/src/graphql/queries.ts`) and `EnrichmentJobList`
  (`frontend/src/components/admin/enrichment/EnrichmentJobList.tsx`) renders a
  "Showing the N most recent of M runs" note whenever the server holds more
  analyses than the `first: 50` page cap returns. `totalCount` is threaded
  through `useEnrichmentJobs` → `useOptimisticRows` to both the Admin panel and
  the corpus enrichment card.
- **Multi-minute enrichment elapsed times now read as `Nm Ns` / `Nh Nm`
  (`frontend/src/components/admin/enrichment/EnrichmentJobList.tsx`).** A crawl
  that ran 127 seconds previously rendered as the unscannable "127s"; it now
  renders "2m 7s". Sub-minute durations are unchanged ("47s").
- **Crawl-bound number inputs reject fractional values
  (`frontend/src/components/admin/enrichment/EnrichmentRunner.tsx`).** Added
  `step={1}` to the Advanced crawl-bound inputs so the browser flags
  non-integer entries at the UI layer before they reach the `graphene.Int`
  mutation schema.
