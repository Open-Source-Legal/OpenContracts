- `RunCorpusEnrichmentMutation` (`config/graphql/enrichment_mutations.py`) now
  validates the relay global-id type prefix: a well-formed id of the wrong type
  (e.g. `DocumentType:<pk>`) is rejected with the same generic
  "not found / no permission" message instead of letting the bare numeric pk
  flow into `start_document_analysis(corpus_pk=...)` and relying solely on the
  downstream visibility filter. Covered by
  `test_enrichment_run_mutation.test_rejects_wrong_global_id_type`.
