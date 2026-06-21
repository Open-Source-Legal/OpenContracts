- **Enrichment now persists references incrementally ("in-flight") instead of in
  one bulk write at the end of a run.** `EnrichmentService.apply`
  (`opencontractserver/enrichment/services/enrichment_service.py`) writes each
  document's references as detection completes, marked `is_provisional` (new
  `CorpusReference.is_provisional` field, migration
  `annotations/0090_corpusreference_is_provisional` — schema-only, default
  `False` so every existing row is finalized). On success the run flips its own
  rows finalized in one atomic update keyed on `created_by_analysis`; a run that
  dies mid-flight (e.g. a Celery worker warm-shutdown) leaves its rows
  provisional, and the writer's claim rule (`EnrichmentWriter._ensure_corpus_reference`)
  lets the next successful run reclaim + finalize them — so a long LLM pass that
  is interrupted at minute *N* no longer loses all *N* minutes of work. The crawl
  seed (`AuthorityFrontierService.seed_from_wanted_authorities` via
  `CorpusReferenceService.wanted_authorities(finalized_only=True)`) acts on
  finalized references only, while the References panel / governance graph surface
  in-flight rows (`isProvisional` exposed on `CorpusReferenceType`). Design:
  `docs/superpowers/specs/2026-06-17-in-flight-authority-detection-design.md`.
