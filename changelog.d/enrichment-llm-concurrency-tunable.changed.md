- **The Tier-2b LLM enrichment concurrency cap is now ops-tunable.** The
  cross-document orchestrator's global chunk-semaphore was pinned to the
  `LLM_MAX_CONCURRENCY` constant (8). A new `ENRICHMENT_LLM_MAX_CONCURRENCY`
  env var / Django setting (default `None`) overrides it via
  `opencontractserver.enrichment.constants.llm_max_concurrency()`, which falls
  back to the constant — so a deployment can raise LLM throughput (at higher
  provider rate-limit / cost exposure) without a code change. The constant stays
  the single numeric default; both `EnrichmentService._aresolve_documents` and
  `LLMCitationExtractor`'s default route through the resolver, and an explicit
  constructor argument still wins.
