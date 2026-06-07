- **Corpus "Annotations" tab: structural annotations showed "Unknown Document" and produced broken deep links.**
  Structural annotations carry `document_id=NULL` and reach their document only
  through the shared `StructuralAnnotationSet`. Two bugs combined to break the
  corpus annotation cards for them:
  (1) **The document never resolved at all.** `AnnotationType` relied on
  graphene-django's auto-generated FK field for `document`, whose resolver
  (`graphene_django/converter.py`) reads the raw `document_id` column and
  short-circuits to `None` when it is NULL — so `AnnotationType.resolve_document`
  was never invoked for structural annotations and every card rendered the
  frontend's "Unknown Document" fallback. Fixed by declaring `document` as an
  explicit `graphene.Field` on `AnnotationType` (`config/graphql/annotation_types.py`)
  so the custom resolver always runs (lazy type ref avoids the
  `annotation_types`↔`document_types` import cycle).
  (2) **Once resolving, it picked the wrong document.** A `StructuralAnnotationSet`
  is deduplicated by content hash and shared across the standalone import source
  AND every corpus-isolated copy (potentially in other corpuses), so the unscoped
  `structural_set.documents.first()` returned an arbitrary, non-corpus-local
  document — breaking the deep link. Fixed with a new
  `AnnotationService.structural_document_prefetch(corpus_id, document_id)`
  (`opencontractserver/annotations/services/annotation_service.py`) that scopes
  `structural_set__documents` to the queried corpus (via `path_records`, ordered
  by slug for determinism), wired into `resolve_annotations`
  (`config/graphql/annotation_queries.py`) and the `resolve_semantic_search`
  re-fetch (`config/graphql/search_queries.py`). Mirrors the corpus-scoped lookup
  already used by `opencontractserver/mcp/tools.py::search_corpus`.
  No added per-row queries (one scoped prefetch replaces the previous unscoped
  one); the semantic-search path also sheds a latent per-row N+1.
  Frontend: `CorpusAnnotationCards` falls back to the opened corpus when building
  the deep link (`frontend/src/components/annotations/CorpusAnnotationCards.tsx`),
  so structural annotations (whose `corpus` is null) open in the corpus context
  (`/d/<user>/<corpus>/<doc>`) instead of standalone. Regression test:
  `opencontractserver/tests/test_corpus_cards_structural_document_resolution.py`.
