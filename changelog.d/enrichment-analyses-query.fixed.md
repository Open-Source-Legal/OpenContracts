- **Corpus enrichment job list no longer triggers a "Network error" toast.**
  `GET_CORPUS_ANALYSES` (`frontend/src/graphql/queries.ts`) queried
  `analyses(corpusId:, status_Exact:)` with `$corpusId: ID!` / `$statusExact:
  String`, but the `AnalysisFilter` exposes `analyzedCorpusId` (a `String`,
  Relay-id-decoded server-side) and `status` (the `AnalyzerAnalysisStatusChoices`
  enum, not `status_Exact`). The query failed GraphQL validation on every corpus
  page that renders `CorpusEnrichmentCard` (via `useEnrichmentJobs`), surfacing
  the global Apollo error-link "Network error. Please check your connection and
  try again." toast. Corrected the argument names and variable types; the live
  job-list query now succeeds (200) with no toast.
