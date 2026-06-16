- **Run corpus reference-enrichment (and the bounded authority crawl) from the UI,
  with live job-status tracking.** A new `runCorpusEnrichment` GraphQL mutation
  (`config/graphql/enrichment_mutations.py`) dispatches the enrichment and/or crawl
  `@corpus_analyzer_task`s through the existing analyzer framework, configurable per run
  (reference types, an opt-in cost-gated LLM detection tier via a new `use_llm` input on
  `corpus_reference_enrichment`, and crawl bounds). It requires corpus **UPDATE**
  permission (enrichment writes references; crawl publishes authority documents) — an
  opt-in `require_corpus_update` gate on `AnalysisLifecycleService.start_document_analysis`.
  Each run is an `Analysis` row with the managed `RUNNING→COMPLETED/FAILED` lifecycle; an
  `Analysis` `post_save` signal (scoped to the enrichment/crawl analyzers) emits a
  `Notification` (new `Notification.analysis` FK + `ANALYSIS_RUNNING` type) that broadcasts
  over the existing notification WebSocket. Two frontend surfaces share the same components:
  a superuser `/admin/enrichment` panel (any corpus) and a "Reference enrichment" card on
  the Corpus Intelligence home (gated on `CAN_UPDATE`). The job list
  (`EnrichmentJobList` + `useEnrichmentJobs`) refetches live on `ANALYSIS_*` notifications,
  shows status badges + parsed run summaries, and surfaces optimistic RUNNING rows on
  dispatch (superseded by the authoritative fetched row); the Run button is disabled while
  a CREATED/QUEUED/RUNNING job exists for the corpus. `AnalysisFilter` gained an
  `analyzer__task_name` (`analyzer_TaskName_In`) filter to scope the list to enrichment/crawl
  analyses.
