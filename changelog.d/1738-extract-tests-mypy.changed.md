- **Graduated the `extract` test domain out of the mypy baseline (#1738).**
  Removed the 6 `[mypy-opencontractserver.tests.test_*]` `ignore_errors` blocks
  for the structured-data-extraction feature — Extracts plus their
  Fieldsets/Columns, Datacells, and metadata columns (all in
  `opencontractserver/extracts/models.py`): `test_extract_mutations`,
  `test_extract_queries`, `test_extract_tasks`, `test_datacell_mutations`,
  `test_column_mutations`, `test_metadata_columns_graphql`. Pruned the
  corresponding 57 lines from `docs/typing/mypy_baseline.txt` (3648 → 3591) and
  fixed the 42 errors that surface. Every error was the same one: a
  `graphene.test.Client` assigned to `self.client` shadows
  `django.test.TestCase.client` (which has no `.execute()`), so `self.client`
  was renamed to `self.graphene_client` in the 5 GraphQL test modules — a
  behaviour-equivalent rename, since the assignment already shadowed the Django
  client at runtime and every read was `.execute()`. `test_extract_tasks` needed
  no code change: its historical `set_permissions_for_obj_to_user` arg-type
  errors no longer reproduce under `django-stubs==6.0.5`. The full project
  surface (`mypy --config-file mypy.ini opencontractserver config`) stays clean
  under both the pre-commit pin (`mypy==2.0.0`) and CI's pin (`mypy==2.1.0`).
