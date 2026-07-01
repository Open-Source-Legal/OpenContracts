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
  the degraded DB fallback (now `AnnotationService.resolve_structural_document_fallback`)
  applies `BaseService.filter_visible_qs` and returns `None` outright when the annotation
  carries no `corpus_id` to scope against, rather than risking a cross-corpus pick. The
  non-structural (`document_id`) path returns the already `select_related`-cached FK (no
  per-row query, via `AnnotationService.resolve_owned_document` when not cached) and the
  structural path trusts the once-per-page user-scoped prefetch — including an *empty*
  prefetch result, which is a definitive "nothing visible in this context" and is now
  returned directly instead of falling through to a redundant, identically-scoped DB query.
  `SemanticSearchResultType.resolve_document`
  (`config/graphql/social_types.py`) delegated its raw-FK access to the same gated resolver,
  closing the convenience field's bypass. Regression tests:
  `opencontractserver/tests/test_corpus_cards_structural_document_resolution.py`, including a
  corpus-scoped-prefetch variant with a captured-query-count assertion guarding against a
  silent N+1 regression in the `_prefetched_objects_cache` detection. Consolidates the fix
  from the closed duplicate PR #2088.
