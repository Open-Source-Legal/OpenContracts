- **Removed the dead `Artifact.is_public` override surface (docstring/behavior
  mismatch flagged in a post-merge review of #2077).** The `Artifact` model's
  docstring (`opencontractserver/corpuses/models.py`) claimed visibility was
  "corpus-as-gate OR `is_public`", but no read path ever implemented the
  `is_public` branch: `ArtifactService._corpus_readable`
  (`opencontractserver/corpuses/services/artifact_service.py`) — the sole gate
  used by `get_by_slug`, `list_for_corpus`, `update_captions`, `set_image` —
  checks only the source corpus's visibility. `ArtifactService.create`'s
  `is_public: bool = True` parameter was passed straight to
  `Artifact.objects.create(...)` but never consulted by anything, and the
  `CreateArtifact` GraphQL mutation didn't even expose it as an argument.
  Not exploitable (the code was already more restrictive than documented,
  never less), but a footgun: a future change that "fixed" the code to match
  the documented OR-semantic would have silently reopened an IDOR (a
  public-flagged artifact on a private corpus leaking that corpus's data to
  anyone with the artifact's slug). Removed the `is_public` parameter from
  `ArtifactService.create` and its `Artifact.objects.create(...)` kwarg, the
  `is_public` field from `ArtifactType` (`config/graphql/corpus_types.py`) and
  `_artifact_to_type` (`config/graphql/corpus_queries.py`), and the `isPublic`
  field from the `ArtifactNode` interface/queries in
  `frontend/src/graphql/queries.ts` (fetched but never branched on by any
  component). Corrected the three docstrings that repeated the OR-semantic
  claim to state the actual corpus-as-gate-ONLY behavior. Note: the
  `is_public` *column* itself is inherited from `BaseOCModel` (every
  BaseOCModel subclass — Document, Corpus, Annotation, etc. — has its own copy
  via abstract-base inheritance) and is used generically by
  `BaseVisibilityManager`/`visible_to_user()` elsewhere in the system; dropping
  it from the database would require decoupling `Artifact` from `BaseOCModel`
  entirely, which is out of scope here, so the column stays present but is no
  longer read, set, or documented as meaningful for `Artifact` specifically. No
  migration was needed. (#2095)
