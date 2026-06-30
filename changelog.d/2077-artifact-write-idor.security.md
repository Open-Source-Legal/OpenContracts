- **Gate Artifact caption/image edits on corpus visibility.**
  `ArtifactService.update_captions` and `ArtifactService.set_image`
  (`opencontractserver/corpuses/services/artifact_service.py`) fetched the artifact by slug alone,
  so a known/guessed slug could let a user mutate an artifact in a corpus they cannot read — out of
  step with the corpus-as-gate model the read paths (`get_by_slug`) already enforce. Both write
  methods now reject when `_corpus_readable` is false, before the creator/UPDATE check, so a
  private-corpus artifact is indistinguishable from a nonexistent one. Tests:
  `opencontractserver/tests/test_artifact_service.py`.
