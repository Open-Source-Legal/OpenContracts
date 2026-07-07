- **`uploadDocument` crashed with a Python `TypeError` when `customMeta` was omitted.**
  `UploadDocument.custom_meta` is declared `required=False` in the GraphQL
  schema, but the resolver had no Python default for it, so a caller whose
  query didn't include `customMeta` at all (graphene only passes arguments a
  query actually names) got `missing 1 required positional argument:
  'custom_meta'` instead of a clean response. Fixed by defaulting
  `custom_meta=None` in `UploadDocument.mutate`
  (`config/graphql/document_mutations.py`), matching the sibling
  `UploadDocumentsZip` mutation's existing pattern. Added regression coverage
  in `opencontractserver/tests/test_document_uploads.py`.
