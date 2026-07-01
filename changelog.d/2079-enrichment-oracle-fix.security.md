- **Close an active-job oracle in `RunCorpusEnrichmentMutation`.** The
  duplicate-job guard (`AnalysisLifecycleService.active_analysis_exists`) previously
  ran before any corpus permission check, so a caller with no READ access to a
  corpus could still learn whether it had an active enrichment/crawl job by
  comparing the "already queued or running" message against the generic
  not-found/no-permission message. `config/graphql/enrichment_mutations.py` now
  runs an explicit `CorpusService.get_or_none(Corpus, corpus_pk, user, request=...)`
  visibility gate immediately after the relay-ID decode and before any
  corpus-specific branching, returning the same IDOR-safe generic message for
  both "corpus not visible" and "corpus visible, no active job" — closing the
  oracle without weakening the existing TOCTOU-safe duplicate-job lock. Also adds
  missing test coverage for the crawl-branch duplicate-job guard (previously only
  the enrichment branch was tested) and replaces a raw `"COMPLETED"` status
  literal with `JobStatus.COMPLETED.value` in
  `opencontractserver/tests/test_enrichment_run_mutation.py`.
