- **Enrichment reference web — denormalization hardening (5 fixes).**
  - `DocumentRelationship` rollups are now a *reconciled projection* of resolved
    doc→doc `CorpusReference` rows: `EnrichmentWriter._reconcile_document_graph`
    (`opencontractserver/enrichment/writer.py`) rebuilds the doc-graph edges on
    every run — stale enrichment-owned edges (recognized by the `analysis_id`
    marker in `data`) are pruned, missing ones created, and user-authored rows
    are never deleted or shadowed. Previously an edge whose backing reference
    disappeared survived forever (orphaned doc-graph edges after re-runs).
  - `link_url` slug drift is now repaired: the cross-corpus linking pass
    (`EnrichmentService._link_external` →
    `_restamp_mention_links`, `opencontractserver/enrichment/services/enrichment_service.py`)
    recomputes the canonical `/d/{creator}/{corpus}/{doc}` path for **every**
    resolved LAW/DOCUMENT reference from current slugs, instead of stamping only
    newly-resolved refs. A corpus rename no longer leaves mention links 404ing
    forever. Result dicts gain `links_restamped`.
  - Defined-term definition sites are mention-only: the writer no longer creates
    `CorpusReference` rows for `DEFINED_TERM` (the `OC_REF_TERM` annotation
    already carries `term:<slug>` in its `data`; a definition site has no
    target). Rows return when usage→definition linking lands.
  - `CorpusReference.save()` now enforces the `reference_type` ↔ mention-label
    invariant (`opencontractserver/annotations/models.py`): the column
    denormalizes the mention's `OC_REF_*` label for indexing, and a row where
    the two disagree raises `ValidationError`. Query-free on the writer's hot
    path (uses in-memory relations).
  - New partial unique constraint `uniq_corpusref_source_type_nullkey`
    (`annotations/0079`): Postgres treats NULLs as distinct, so the existing
    (source_annotation, reference_type, canonical_key) constraint never guarded
    keyless rows against concurrent duplication. Migration dedupes existing
    keyless rows before adding the constraint.
- **Enrichment analyzer tests fail on freshly migrated DBs (pre-existing).**
  The `analyzer/0009`+`0013` data migrations auto-sync the corpus-analyzer row
  during `migrate`, so `test_enrichment_analyzer_integration.py`'s local
  `_make_analysis` helper collided with the pre-synced row on the `task_name`
  unique constraint (6/7 tests failed on any `--create-db` run). The converge
  logic now lives once in `EnrichmentService.get_or_create_analyzer()` and the
  test helper reuses it; the clean-slate auto-sync test clears the pre-synced
  row explicitly.
