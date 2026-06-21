- **The Tier-2b LLM enrichment pass now runs concurrently across documents and
  chunks instead of strictly serially.** Previously every ~2,000-char chunk of
  every document was a sequential `await` (one corpus measured ~2,900 serial
  calls, ~72 min, and a worker restart lost the lot). Now
  `LLMCitationExtractor.aextract`
  (`opencontractserver/enrichment/llm_citation_extractor.py`) runs its chunks via
  `asyncio.gather` behind a semaphore, the sliding-window grew from 2,000→8,000
  chars (≈4× fewer chunks, less redundant overlap), and a new
  `EnrichmentService._aresolve_documents` orchestrator extracts ALL documents
  concurrently under one *global* chunk-semaphore (`LLM_MAX_CONCURRENCY`, default
  8) — bounding total provider load while filling the lanes across documents,
  and still writing each document the moment its detection completes (the
  per-document path serialized them, so a corpus with a few large documents
  bottlenecked). Measured: the same 75-document / 4.5 MB corpus went from ~72 min
  (which then died) to **~4 minutes**, completing with all references finalized.
  DB writes are marshaled through `sync_to_async` (thread-sensitive) so the ORM
  writes serialize and never race; only the LLM calls run concurrently.
