- **Metadata columns: authorize deletion against the parent corpus, not the child `Column`.**
  `DeleteMetadataColumn` (`config/graphql/extract_mutations.py`) previously gated on
  `require_permission(column, DELETE)`, so a user holding a direct creator/`Column`-level DELETE
  grant could delete a corpus-scoped metadata column — cascade-deleting its `Datacell` values —
  without holding corpus-level DELETE. Metadata schemas are corpus-scoped objects, so the
  destructive check now runs against the parent corpus (`require_permission(corpus, DELETE)`).
  The column lookup stays READ-gated through the service layer
  (`BaseService.get_or_none(Column, …)`, mirroring `CreateMetadataColumn`/`UpdateMetadataColumn`),
  and the response is the same unified "not found or no permission" message whether the column is
  missing or invisible (IDOR-safe). Regression tests:
  `opencontractserver/tests/test_metadata_columns_graphql.py::DeleteMetadataColumnTestCase`
  (column-DELETE-without-corpus-DELETE is refused; corpus-DELETE-without-column-DELETE succeeds).
