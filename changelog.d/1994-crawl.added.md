- Add `CrawlAuthoritiesService.crawl()` BFS engine
  (`opencontractserver/enrichment/services/crawl_authorities_service.py`):
  seeds the `AuthorityFrontier` from Wanted Authorities (depth 0), then
  iterates dequeue → discover_and_bootstrap → re-extract outbound cites →
  seed depth+1.  Stops on four hard bounds: `max_authorities`,
  `token_budget`, `per_jurisdiction_cap` (parks blocked rows at
  `deferred_cap`), and `min_demand` floor.  Returns a full summary dict
  with `stop_reason`, `outcomes`, `blocked_by_bound`, `per_jurisdiction`,
  and `frontier_residual` — no silent truncation.
- Add `crawl_authorities` Celery task (`@corpus_analyzer_task`) in
  `opencontractserver/tasks/corpus_analysis_tasks.py`: wraps
  `CrawlAuthoritiesService.crawl()` with the analyzer-framework lifecycle
  (RUNNING → COMPLETED/FAILED) and exposes all bound parameters with
  per-field defaults from `C.CRAWL_DEFAULT_*`.
- Add `CrawlAuthoritiesService` to the enrichment services `__init__.py`
  (`opencontractserver/enrichment/services/__init__.py`).
- Add comprehensive test coverage in
  `opencontractserver/tests/test_crawl_authorities.py`: idempotency
  (zero duplicate frontier rows on recrawl, ingested rows skipped,
  child seeding idempotent) and bounds termination (max_authorities,
  min_demand, max_depth, per_jurisdiction_cap, token_budget, no-silent-
  truncation summary invariant).
