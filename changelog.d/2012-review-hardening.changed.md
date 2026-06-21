- `CorpusReference` gains a composite index on
  `(created_by_analysis, is_provisional)` (`idx_corpusref_analysis_provis`,
  migration `0097`) covering the in-flight finalize UPDATE in
  `EnrichmentService.apply()` (`filter(created_by_analysis=..., is_provisional=True)`),
  avoiding a two-single-column-index merge / seq-scan on large corpora.
- `formatJurisdiction` / `titleCase` are de-duplicated into
  `frontend/src/utils/formatters.ts` (single canonical null-returning
  signature) and shared by the Authority Sources monitor and the
  governance-graph explorer, which previously carried divergent copies that
  rendered the same jurisdiction code two different ways. Provisional/awaiting
  badge colours and the explorer canvas/vignette tones now come from
  `OS_LEGAL_COLORS` tokens instead of bare hex literals. Documents the
  `ENRICHMENT_DOC_MAX_CONCURRENCY` setting in `config/settings/base.py`.
- `EnrichmentService.apply()` now logs a warning when another enrichment
  `Analysis` is already `RUNNING` on the same corpus. Concurrent runs remain
  safe (the claim rule reclaims+finalizes provisional rows and the crawl seed
  reads finalized rows only), but the earlier run can finalize zero of its own
  rows and complete "empty"; the warning makes that otherwise-confusing outcome
  explicit in the logs. `_provider_for` also gains an explicit
  `tuple[str | None, Any, str | None]` return annotation so a future caller that
  destructures the old 2-tuple is caught at type-check time.
