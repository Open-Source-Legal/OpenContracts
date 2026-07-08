- Follow-up fixes to the graphene→strawberry migration surfaced by CI:
  - Restored `opencontractserver/pipeline/embedders/test_embedder.py`, which was
    deleted as collateral in an earlier migration commit while
    `config/settings/test.py` still names it as the default embedder. The pytest
    suite masked the breakage (a session-autouse fixture disconnects the
    document post-save signals), but the live `frontend-e2e` `runserver` fires
    `calculate_embedding_for_doc_text` eagerly on the structural `Readme.CAML`
    document that corpus creation seeds, so `createCorpus` returned HTTP 500 and
    the corpus/routing/threads E2E specs failed.
  - `.pre-commit-config.yaml`: the `mypy` hook's `additional_dependencies` now
    ship `strawberry-graphql==0.320.3` (replacing the removed
    `graphene-django==3.2.3`) so the hook's isolated env can import the
    `strawberry.ext.mypy_plugin` referenced by `mypy.ini`.
  - Applied the repo's standard `pyupgrade`/`black`/`isort` formatting to the
    generated strawberry schema modules and the migration-touched test files so
    the `pre-commit` linter job passes; schema-shape parity is unchanged.
