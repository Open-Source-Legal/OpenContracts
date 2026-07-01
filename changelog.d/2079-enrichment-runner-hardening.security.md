- **Secure the corpus enrichment / authority-crawl runner (`RunCorpusEnrichmentMutation`).**
  `config/graphql/enrichment_mutations.py` now gates the dispatch mutation behind rate
  limiting (`RateLimits.AI_ANALYSIS`), an authority-admin gate on the LLM detection tier,
  crawl-bound validation (`max_depth` capped at the new `CRAWL_MAX_ALLOWED_DEPTH`; the
  expensive `max_authorities` / `per_jurisdiction_cap` / `token_budget` capped at their safe
  defaults), and a per-corpus duplicate-job guard. The duplicate-job guard is now TOCTOU-safe:
  the check-and-create runs inside one `transaction.atomic()` holding a `select_for_update`
  lock on the corpus row (new `AnalysisLifecycleService.lock_corpus_for_dispatch` and
  `active_analysis_exists` in
  `opencontractserver/analyzer/services/analysis_lifecycle_service.py`), so two concurrent
  requests for the same corpus can no longer both read "no active job" and double-dispatch.
  `min_demand` carries only a floor (a higher value is *more* selective and cheaper, never a
  resource risk), matching the crawl analyzer input schema. The duplicate-job ORM query moved
  out of `config/graphql/` into the service layer per the service-layer invariant. Regression
  coverage: `opencontractserver/tests/test_enrichment_run_mutation.py`.
