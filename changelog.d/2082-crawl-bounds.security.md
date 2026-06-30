- **Cap user/LLM-triggered `crawl_authorities` runs at the service layer.**
  `CrawlAuthoritiesService.crawl` (`opencontractserver/enrichment/services/crawl_authorities_service.py`)
  now sanitizes its own bounds, so both the LLM-tool path
  (`opencontractserver/llms/tools/core_tools/corpus_references.py`) and the Celery-task path are
  protected by one load-bearing guard instead of the tool path alone. Two clamp-polarity bugs are
  fixed: a negative/zero `token_budget` no longer clamps to `0` (the "unbounded" sentinel that
  disabled the budget check) — non-positive requests map to `CRAWL_DEFAULT_TOKEN_BUDGET` and
  positive ones clamp to `CRAWL_MAX_TOKEN_BUDGET`; and `per_jurisdiction_cap` now floors at
  `CRAWL_MIN_PER_JURISDICTION_CAP` (1) instead of `0`, which had parked every dequeued row at
  `deferred_cap` and silently halted the whole crawl. The redundant second `_sanitize_bounds`
  call in the tool wrapper is removed (the service owns sanitization), and the `frontier_drained`
  diagnostic count is scoped to the run's `canonical_keys` so a scope-restricted crawl no longer
  inflates `blocked_by_bound["min_demand_or_depth"]` with QUEUED rows from other concurrent runs.
  The numeric clamp helper moved to a reusable `opencontractserver/utils/numbers.py::clamp_int`
  (distinct from `clamp_limit`), and the corpus-scoping `crawl_keys` set is now unconditional —
  the dead `else None` fallback that would have silently re-opened the crawl to the global frontier
  is gone.
  Tests: `opencontractserver/tests/test_crawl_authorities_security.py` (incl. a Celery-task-path
  clamp regression), `opencontractserver/tests/test_numbers_utils.py`.
