- **Close data-loss and IDOR gaps in `CorpusReference` visibility filters.**
  `CorpusReferenceService.visible_to_user` / `visible_to_user_by_source`
  (`opencontractserver/enrichment/services/corpus_reference_service.py`) filtered
  source/target annotations with `__document__in=visible_documents`. Because `Annotation.document` is
  NULL for structural annotations in shared sets and NULL is never a member of an `__in` list, every
  structural-annotation-sourced/targeted reference — including the corpus owner's own — was silently
  dropped from `corpusReferences`, `wanted_authorities`, and the governance graph. NULL-document
  guards now retain them. Separately, the filters checked only the source/target annotation's
  *document*, so an annotation whose document was public but whose **corpus** was private leaked its
  FK; the filters now enforce `MIN(document, corpus)` on both `source_annotation__corpus` and
  `target_annotation__corpus` (NULL-safe) via shared `_source_visible_q` / `_target_visible_q`
  builders, with `_build_visibility_querysets` evaluated once per call. The authority crawler's
  frontier-seed query (`crawl_authorities_service.py`), a canonical-key-only consumer, now uses
  `for_corpus_by_source` so a reference to an unseen target is ghosted/seeded rather than silently
  dropped — matching the governance graph. Tests cover the structural-annotation, source-corpus and
  target-corpus IDOR, and guardian-grant paths in
  `opencontractserver/tests/test_corpus_reference_model.py`.
