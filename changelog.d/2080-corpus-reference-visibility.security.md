- **Close data-loss and IDOR gaps in `CorpusReference` visibility filters.**
  `CorpusReferenceService.visible_to_user` / `visible_to_user_by_source`
  (`opencontractserver/enrichment/services/corpus_reference_service.py`) filtered
  source/target annotations with `__document__in=visible_documents`. Because `Annotation.document` is
  NULL for structural annotations in shared sets and NULL is never a member of an `__in` list, every
  structural-annotation-sourced/targeted reference — including the corpus owner's own — was silently
  dropped from `corpusReferences`, `wanted_authorities`, and the governance graph. NULL-document
  guards now retain them. Separately, `visible_to_user` checked only the target annotation's
  *document*, so an annotation whose document was public but whose **corpus** was private leaked its
  FK; the filter now also enforces `MIN(document, corpus)` on `target_annotation__corpus` (NULL-safe).
  The duplicated `visible_to_user()` queryset construction is consolidated into a
  `_build_visibility_querysets` helper. Tests cover the structural-annotation, target-corpus IDOR,
  and guardian-grant paths in `opencontractserver/tests/test_corpus_reference_model.py`.
