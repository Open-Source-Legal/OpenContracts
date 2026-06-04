- **Removed the blanket `mypy.ini` suppression for `test_discover_search_graphql` by fixing the root-cause type error (issue #1919).**
  PR #1908 added `[mypy-opencontractserver.tests.test_discover_search_graphql]
  ignore_errors = True` to silence 8 `"Client" has no attribute "execute"`
  errors. The real cause was a name collision: the test stored its
  `graphene.test.Client` on `self.client`, which `django-stubs` types as
  `django.test.Client` (inherited from `TestCase`) — a class with no
  `.execute()`. Renaming the attribute to `self.graphene_client` (the
  convention already used by the mypy-clean `test_document_queries.py`) makes
  the file type-check cleanly, so the per-module suppression is deleted rather
  than carried forward as a precedent for brand-new code. Verified with a
  full-project `mypy --config-file=mypy.ini opencontractserver config` run.
