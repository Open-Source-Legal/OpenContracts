- Migration `0093_load_authority_namespaces_baseline` now upserts
  `AuthorityNamespace` rows via `apps.get_model` (the historical model) instead
  of calling the live `AuthorityMappingLoader` service, so a fresh-database
  `migrate` runs against the schema as of that migration — a later
  `AuthorityNamespace` schema change can no longer break fresh-DB migrate / CI /
  onboarding (matches the fix already applied to 0092).
- `GovernanceGraphExplorer` now calls `d3.interrupt(svgEl)` in its zoom effect
  cleanup, cancelling any in-flight zoom/reset transition on unmount so a tween
  can no longer fire `setTransform` on an unmounted component (React warning +
  leak when navigating away mid-transition).
- The concurrent enrichment orchestrator (`EnrichmentService._aresolve_documents`,
  `opencontractserver/enrichment/services/enrichment_service.py`) now isolates
  per-document failures instead of letting one document's error abort the whole
  run. Previously a bare `asyncio.gather(...)` propagated the first exception and
  cancelled every other in-flight document coroutine, so a single transient LLM
  timeout / network blip on one document discarded the entire corpus's concurrent
  work — the opposite of the in-flight-persistence resilience this path exists
  for. Each document's extraction+write is now wrapped so a failure is logged and
  skipped (its references are reclaimed by a later run); only when *every*
  attempted document fails is the run re-raised as FAILED, so a systemic error
  (bad API key, provider outage) is never silently finalized as an empty result.
  Covered by `ConcurrentLLMFailureIsolationTests` and a finalized-NULL-analysis
  orphan case in `WriterClaimRuleTests`
  (`opencontractserver/tests/test_enrichment_in_flight.py`).
