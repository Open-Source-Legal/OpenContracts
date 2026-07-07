- **`updatePipelineSettings` silently wiped sibling MIME-type/component entries.**
  Setting one MIME type's preferred parser (e.g. assigning `application/pdf` to
  a new parser) replaced the entire `preferred_parsers` mapping wholesale,
  silently dropping every other MIME type's parser/thumbnailer/enricher
  assignment (and likewise for `parser_kwargs` / `component_settings`, keyed
  per component class path). Fixed by shallow-merging the incoming mapping
  over the existing one for all six mapping fields
  (`config/graphql/pipeline_settings_mutations.py`); the JSON-size guard now
  checks the merged result so repeated small updates can't accumulate past the
  cap. An explicit `null` value for a key is a delete marker (drops that key
  from the merged result) — required by the admin System Settings GUI's
  "-- Unassigned --" filetype-default option and enricher-chain removal
  (`frontend/src/components/admin/SystemSettings.tsx` `handleAssign` /
  `handleAssignEnrichers`), which now send only the single changed MIME type
  instead of resubmitting the full mapping. Also removed a duplicate,
  narrower "assigned components must stay enabled" check left over from a
  concurrent merge — the broader `_find_disabled_but_assigned` check (added
  for issue #2116) already supersedes it and is now the sole implementation,
  fixed to read the merged `settings_instance` state instead of the raw
  per-call request args. Added regression coverage in
  `opencontractserver/tests/test_pipeline_settings.py` and
  `frontend/tests/system-settings-flows.ct.tsx`.
