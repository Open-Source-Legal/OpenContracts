- Harden the bounded authority crawl against a concurrency race and provenance
  bloat (issue #2027, a code review of the Phase-5 BFS engine):
  - **Atomic dequeue claim.**
    `AuthorityFrontierService.dequeue_queued()`
    (`opencontractserver/enrichment/services/authority_frontier_service.py`)
    was a plain `filter(discovery_state="queued")` read — the `in_progress`
    transition only happened later inside `discover_and_bootstrap`, leaving a
    TOCTOU window where two concurrent `crawl_authorities` tasks (e.g. two
    manual triggers on the same corpus) could dequeue the SAME frontier row and
    `discover_and_bootstrap` it twice (wasted provider calls, distorted summary
    counters). It now claims the rows it returns inside a single
    `SELECT … FOR UPDATE SKIP LOCKED` transaction, flipping them to
    `in_progress`; a second worker skips locked rows and grabs the next ones.
    Rows excluded by `max_depth` / `min_demand` are never claimed, so the
    `frontier_drained` residual census still counts them as `queued`.
  - **One provenance `Analysis` per authority corpus.** Every section of an
    authority bootstraps into ONE corpus (the provider `title` is a constant —
    all `usc-*` sections land in the single "United States Code" corpus), so the
    BFS calls `EnrichmentService.apply()` on that corpus once per ingested
    section. Each call previously minted a fresh `Analysis`
    (`_get_analysis` → `Analysis.objects.create`), so a deep crawl left dozens
    of provenance rows on one corpus. `CrawlAuthoritiesService.crawl()`
    (`opencontractserver/enrichment/services/crawl_authorities_service.py`) now
    caches the `Analysis` the first apply creates per corpus and threads it back
    into the rest via `apply(analysis=…)`, capping it at one per corpus. A
    misleading "this apply scan is bounded (one small document per section)"
    comment was corrected.
  - **Honest `blocked_by_bound` accounting.** Clarified (in comments) that
    `blocked_by_bound["min_demand_or_depth"]` is populated only on the
    `frontier_drained` stop — where every residual `queued` row is provably
    bound-excluded — and intentionally NOT on the `max_authorities` /
    `token_budget` early stops, whose unreached rows may be perfectly eligible
    and are accounted for by the `frontier_residual` census instead.
  - **Uniform tool signature.** `crawl_authorities` / `acrawl_authorities`
    (`opencontractserver/llms/tools/core_tools/corpus_references.py`) now apply
    `C.CRAWL_DEFAULT_*` constants to all five bound parameters instead of using
    `None` sentinels for two of them and constants for the other three.
- Regression tests: `test_authority_frontier.py` (dequeue atomically claims
  returned rows / leaves filtered-out rows `queued`) and
  `test_crawl_authorities.py::ApplyAnalysisReuseTests` (a crawl that ingests
  multiple sections of one authority reuses a single provenance `Analysis`).
