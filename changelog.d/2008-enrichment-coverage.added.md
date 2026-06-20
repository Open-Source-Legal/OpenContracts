- Added frontend tests for the corpus-enrichment runner UI to close the PR 2008
  patch-coverage gap: `frontend/tests/EnrichmentJobList.ct.tsx` covers every
  `EnrichmentJobList` status/result/elapsed/label branch (52% → 100% lines),
  `frontend/tests/AdminEnrichment.ct.tsx` covers the page's superuser access
  gates and shell (40% → 88%), and
  `frontend/src/components/admin/enrichment/__tests__/useEnrichmentJobs.test.ts`
  exercises the `ANALYSIS_COMPLETE` → `refetch()` notification path (review
  item T-1) — matching corpus, missing-corpus fallback, mismatched corpus, and
  non-analysis notification types.
