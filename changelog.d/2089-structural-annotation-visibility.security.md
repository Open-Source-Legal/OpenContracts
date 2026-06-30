- **Stop structural annotations leaking a private document via their shared structural set.**
  `StructuralAnnotationSet` rows are content-hash deduplicated and therefore shared across
  documents AND owners, so resolving a structural annotation's `document` field through the
  unscoped set (`structural_set.documents.first()`) could surface a private copy owned by
  another user. `AnnotationType.resolve_document`
  (`config/graphql/annotation_types.py`) now resolves only documents the requesting user may
  READ: the structural prefetch is gated at build time in
  `AnnotationService.structural_document_prefetch`
  (`opencontractserver/annotations/services/annotation_service.py`), which now requires a
  `user` (keyword-only) and intersects candidates with `Document.objects.visible_to_user(user)`;
  the degraded DB fallback applies `BaseService.filter_visible_qs`. The non-structural
  (`document_id`) path returns the already `select_related`-cached FK (no per-row query)
  and the structural path trusts the once-per-page user-scoped prefetch, so the fix adds no
  N+1. An empty (fully-filtered) prefetch now falls through to the corpus-scoped fallback
  instead of short-circuiting to `null`. `SemanticSearchResultType.resolve_document`
  (`config/graphql/social_types.py`) delegated its raw-FK access to the same gated resolver,
  closing the convenience field's bypass. Regression tests:
  `opencontractserver/tests/test_corpus_cards_structural_document_resolution.py`. Consolidates
  the fix from the closed duplicate PR #2088.
