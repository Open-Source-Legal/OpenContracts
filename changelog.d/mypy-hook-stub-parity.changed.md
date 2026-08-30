- Synced the `mypy` pre-commit hook's stub pins with `requirements/local.txt`
  (`.pre-commit-config.yaml`: `django-stubs` 6.0.6 → 6.1.0,
  `djangorestframework-stubs` 3.17.0 → 3.18.0). The hook's own comment requires
  these to match the requirements pins; they had drifted, so the type-checking
  CI runs against different stubs than the dev/test image installs.
- Fixed the 7 type errors `django-stubs` 6.1.0 surfaces, none of which change
  runtime behavior:
  - `opencontractserver/shared/QuerySets.py` (6 errors, lines 466/487/655/656/672/673):
    six `permitted_ids`-style variables are assigned a lazy `values_list` queryset
    in a `try` arm and a plain `[]` in the matching `except LookupError` arm. 6.1.0
    types `values_list(..., flat=True)` precisely enough that the two arms no longer
    unify, so each variable now carries an explicit `Iterable[Any]` declaration —
    the honest common type, since every one of them is only ever fed to an `__in`
    lookup.
  - `opencontractserver/tests/test_corpus_canonical_caml_migration.py:161`:
    `apps.get_model("corpuses", "CorpusDescriptionRevision")` is deliberately
    unresolvable (the test asserts the model was dropped), but 6.1.0's plugin
    resolves `get_model()` string pairs at type-check time and errors on a miss.
    Narrowly silenced with `# type: ignore[misc]` plus a comment.
