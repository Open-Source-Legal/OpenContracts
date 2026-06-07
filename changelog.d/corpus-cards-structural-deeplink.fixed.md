- **Corpus "Annotations" tab: structural annotations showed "Unknown Document" and produced broken deep links.**
  Structural annotations carry `document_id=NULL` and reach their document only
  through the shared `StructuralAnnotationSet`, which is deduplicated by content
  hash and therefore shared across the standalone import source AND every
  corpus-isolated copy (potentially in different corpuses). Two distinct bugs
  combined to break this. First, `AnnotationType.resolve_document`
  (`config/graphql/annotation_types.py`) was never actually executed for the
  `document` field: because `DocumentType` overrides `get_queryset`,
  graphene-django's foreign-key converter (`convert_field_to_djangomodel`)
  installs a `custom_resolver` that resolves the FK purely from
  `root.document_id` and ignores the type's `resolve_*` method — and
  structural annotations have `document_id=NULL`, so the field always returned
  `None` (the frontend's "Unknown Document"). Fix: decorate `resolve_document`
  with `@bypass_get_queryset` so graphene-django runs the custom resolver.
  Second, even once it runs, `resolve_document` resolved structural
  annotations with an *unscoped*, non-deterministic
  `structural_set.documents.first()`, which could return the standalone source
  or another corpus's copy. Fix: resolution is now scoped to the context being
  queried via a new
  `AnnotationService.structural_document_prefetch(corpus_id, document_id)`
  helper (`opencontractserver/annotations/services/annotation_service.py`),
  wired into the corpus/document annotation query
  (`config/graphql/annotation_queries.py::resolve_annotations`) and the
  semantic-search re-fetch (`config/graphql/search_queries.py::resolve_semantic_search`).
  The prefetch joins `path_records` to return the corpus-local copy (ordered by
  slug for determinism), mirroring the corpus-scoped lookup already used by
  `opencontractserver/mcp/tools.py::search_corpus`. This adds no per-row queries
  (a single scoped prefetch replaces the previous unscoped one) and removes a
  latent per-row N+1 in the semantic-search path by prefetching
  `structural_set__documents`. On the frontend, `CorpusAnnotationCards` now
  falls back to the opened corpus when building the deep link
  (`frontend/src/components/annotations/CorpusAnnotationCards.tsx`), so
  structural annotations (whose `annotation.corpus` is null) open in the corpus
  context (`/d/<user>/<corpus>/<doc>`) rather than standalone. Regression test:
  `opencontractserver/tests/test_corpus_cards_structural_document_resolution.py`.
