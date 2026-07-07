- **`updatePipelineSettings` now rejects cross-stage component assignments.**
  `validate_component_mapping` (`config/graphql/pipeline_settings_mutations.py`)
  only checked registry membership, so a raw GraphQL call could assign e.g. a
  parser class as a `preferred_thumbnailers`/`preferred_embedders`/`preferred_parsers`
  entry. Registry membership is insufficient: the wrong component type has no
  `.generate_thumbnail` / `.embed_text` and blows up at ingest with an
  `AttributeError`, marking every affected document FAILED. The validator now
  takes an expected `ComponentType` and rejects the mismatch up front (mirroring
  the stricter guard already applied to `default_file_converter`). The GUI
  dropdowns can never produce this, but the API previously accepted it. Test:
  `test_update_preferred_thumbnailer_rejects_wrong_component_type`.
