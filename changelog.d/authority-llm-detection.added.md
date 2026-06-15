- Added Tier-2b LLM detection pass to the authority-discovery enrichment pipeline.
  `EnrichmentService.discover(use_llm=True)` runs `LLMCitationExtractor` after the
  grammar tier; high-confidence (≥0.7) LLM citations merge into the main rollup with
  `detection_tier == "llm"`, low-confidence ones (needs_review=True) surface in a new
  `review_candidates` list and are never auto-promoted. `apply()` also strips
  `needs_review` detections so they cannot become persistent `CorpusReference` rows
  without human review. The `discover_authorities` LLM tool now accepts `use_llm=False`
  (default) to opt-in to the extra pass.
