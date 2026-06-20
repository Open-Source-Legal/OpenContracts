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
