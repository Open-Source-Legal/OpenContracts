- **Admin GUI control for the install-wide post-retrieval reranker
  (`PipelineSettings.default_reranker`).** The backend has persisted, validated,
  cache-busted and *read* this setting at runtime for reranking
  (`opencontractserver/llms/vector_stores/core_vector_stores.py`
  `_get_reranker`), but the admin Pipeline Configuration surface never exposed
  it — `GET_PIPELINE_SETTINGS`/`UPDATE_PIPELINE_SETTINGS` omitted the field and
  there was no widget, so an operator could only change it via a raw GraphQL
  call or DB edit. Added a "Default Reranker" picker to
  `frontend/src/components/admin/system_settings/FiletypeDefaults.tsx` (mirroring
  the File Converter / Default LLM rows; empty = reranking disabled), wired
  `defaultReranker` through `graphql.ts` (query + `UPDATE`/`RESET` mutations) and
  surfaced the registered rerankers via a new `pipelineComponents.rerankers`
  selection. Also filled in the previously-omitted `defaultLlm`/`defaultReranker`
  fields on the `UPDATE`/`RESET` mutation return selections. Verified end-to-end
  against a live stack (set → persisted to DB → revert). Covered by
  `frontend/tests/system-settings-flows.ct.tsx`.
