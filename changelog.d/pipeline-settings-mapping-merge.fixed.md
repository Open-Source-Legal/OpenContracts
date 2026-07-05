- **`updatePipelineSettings` silently wiped sibling MIME-type/component entries.**
  Setting one MIME type's preferred parser (e.g. assigning `application/pdf` to
  a new parser) replaced the entire `preferred_parsers` mapping wholesale,
  silently dropping every other MIME type's parser/embedder/thumbnailer
  assignment (and likewise for `parser_kwargs` / `component_settings`, keyed
  per component class path). The admin System Settings GUI masked this because
  it always resubmits the full object, but any direct API caller updating a
  single entry lost every sibling entry. Fixed by shallow-merging the incoming
  mapping over the existing one for all five mapping fields
  (`config/graphql/pipeline_settings_mutations.py`); the JSON-size guard now
  checks the merged result so repeated small updates can't accumulate past the
  cap. Removing an entry remains out of scope for this mutation (unchanged —
  matches the existing update/delete split for secrets). Added regression
  coverage in `opencontractserver/tests/test_pipeline_settings.py`.
