- **`components_with_secrets` no longer leaks agent-tool secret keys.** Component
  secrets and agent-tool secrets (e.g. `tool:web_search`) share one encrypted
  store on `PipelineSettings`. The GraphQL resolver and the
  update/reset/component-secret mutations built the component list from raw
  `get_secrets().keys()`, so `tool:`-prefixed keys leaked into the admin
  Component Library's per-component secret indicators. Added
  `PipelineSettings.get_components_with_secrets()`
  (`opencontractserver/documents/models.py`) — the inverse of
  `get_tools_with_secrets()` — and routed `config/graphql/pipeline_queries.py`
  and the four mutation return sites through it. Tests:
  `test_get_components_with_secrets_excludes_tool_keys`,
  `test_pipeline_settings_query_excludes_tool_secret_keys`.
