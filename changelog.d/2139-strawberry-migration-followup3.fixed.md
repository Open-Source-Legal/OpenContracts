- Further follow-up fixes to the graphene→strawberry migration, found via a live
  GUI smoke test and a targeted diff sweep:
  - Restored three per-field relay connection `max_limit` overrides that the
    port silently dropped (all three call `resolve_django_connection(...)`
    without the graphene original's `max_limit=` kwarg, so each fell back to
    the global 100-record cap):
    - `documentRelationships` (`config/graphql/document_queries.py`) — needs
      `DOCUMENT_RELATIONSHIP_QUERY_MAX_LIMIT` (500) for the Table of Contents /
      document-relationships panel, which broke ("Requesting 500 records...
      exceeds the `first` limit of 100 records") for any corpus with more than
      100 relationship rows.
    - `annotations` (`config/graphql/annotation_queries.py`) — needs
      `DOCUMENT_ANNOTATION_INDEX_LIMIT` (500) for the Document Annotation Index.
    - `extracts` (`config/graphql/extract_queries.py`) — needs
      `EXTRACT_LIST_MAX_PAGE_SIZE` (20, the PR #1602 pagination-stuck-page
      ceiling); lower than the 100 default so it didn't manifest as a visible
      bug, but the deliberate page-size cap was gone.
  - `config/graphql/document_types.py`: re-exposed `DocumentType._assert_user_can_read`
    as a class attribute (`staticmethod` delegating to the existing ported
    module-level function) — the graphene original was a bound method callable
    as `DocumentType._assert_user_can_read(doc, info)`, which
    `opencontractserver/tests/test_document_type_read_permission.py` calls
    directly; the port kept the logic but only as a private module function,
    breaking that call convention (`AttributeError`).
  - `opencontractserver/tests/test_file_url_prewarm.py`: updated to import
    `FileUrlPrewarmExtension` (the strawberry `SchemaExtension` the port
    correctly replaced the graphene-era `FileUrlPrewarmMiddleware` with) instead
    of the deleted class name; behavior/`_prewarm` signature unchanged.
  - `opencontractserver/tests/test_mentions.py`: fixed a pre-existing (not
    migration-related) test-fixture bug — `conversation_type="THREAD"` used the
    wrong case (`ConversationTypeChoices.THREAD.value` is the lowercase
    `"thread"`; Django doesn't validate `choices=` on `.save()`, so the
    mismatched value persisted silently). This made
    `ConversationQuerySet.visible_to_user`'s `conversation_type=` check miss the
    row entirely for non-creator viewers, independent of `is_public`/context
    inheritance. Fixed to use the `ConversationTypeChoices.THREAD` enum, and
    made the test conversation `is_public=True` so both viewers in
    `test_permission_enforcement_corpus` can reach the message (the test
    exercises `mentionedResources`' per-viewer corpus filtering, not message
    visibility itself).
  - `config/settings/base.py`: removed a dead, commented-out
    `JWT_ALLOW_ANY_HANDLER` setting pointing at the deleted
    `config.graphql.jwt_overrides` module.
  - `opencontractserver/tests/test_pipeline_component_queries.py`: this test
    class overwrites `opencontractserver/pipeline/embedders/test_embedder.py`
    with dummy component code in `setUpClass` and previously `os.remove()`'d it
    in `tearDownClass` — but that path is the real, permanent `TestEmbedder`
    named as `DEFAULT_EMBEDDER` in `config/settings/test.py`, not a scratch
    file. Any full-suite run that reached this test class left the shared
    default embedder module permanently missing for the remainder of the run
    (across all xdist workers, which share one checkout), cascading into ~90
    unrelated failures (`ValueError: get_embedder() resolved no embedder_path`)
    across agent/pydantic-ai/vector-store/extract tests. This is the same
    file already restored once as CI collateral damage
    (`changelog.d/2139-strawberry-migration-ci.fixed.md`) — that fix addressed
    the symptom; this one backs up and restores the file's real content around
    the test class instead of deleting it, fixing the root cause.
