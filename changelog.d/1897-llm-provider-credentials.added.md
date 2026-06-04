- **Live, DB-configurable LLM provider credentials & endpoints.**
  LLM providers (`opencontractserver/pipeline/llm_providers/*.py`) are now
  full pipeline components with a nested `Settings` dataclass carrying an
  encrypted `api_key` (`SECRET`) and, where applicable, a `base_url`
  (`OPTIONAL`) — built via the new `llm_api_key_field` / `llm_base_url_field`
  helpers on `BaseLLMProvider` (`opencontractserver/pipeline/base/llm_provider.py`).
  Superusers can set or rotate a provider's API key and point it at a custom /
  OpenAI-compatible endpoint **live in System Settings → Pipeline Components**,
  with no environment-variable change or redeploy. Credentials are stored (key
  encrypted) in the `PipelineSettings` singleton, reusing the existing Fernet
  secret machinery and GraphQL secret mutations — no schema migration required.
  - New resolver `opencontractserver/llms/model_factory.py`
    (`build_agent_model` / `abuild_agent_model`) implements **DB-wins /
    env-fallback**: when a provider has DB-configured credentials it builds a
    concrete pydantic-ai model with an explicit `Provider(api_key=…,
    base_url=…)`; otherwise it returns the bare `"{provider}:{model}"` spec
    string so pydantic-ai resolves the credential from the environment exactly
    as before. Any construction failure degrades to the env-fallback string,
    so a misconfiguration can never break the chat path. Adding a new provider
    branch is signposted at the fall-through warning.
  - Wired into all five `make_pydantic_ai_agent` call sites — document, corpus
    and structured-output agents (`opencontractserver/llms/agents/pydantic_ai_agents.py`)
    plus the memory-curation tasks (`opencontractserver/tasks/memory_tasks.py`).
  - Frontend: the System Settings component library renders the generic
    secret/config panel from each component's `settingsSchema`, so provider
    `api_key`/`base_url` editing surfaces automatically; updated the "API key"
    badge tooltip in
    `frontend/src/components/admin/system_settings/ComponentLibrary.tsx` to
    reflect live configurability.
  - `_construct_model` handles only `google-gla` (AI-Studio, API-key auth);
    `google-vertex` uses service-account ADC credentials rather than an API key,
    so it falls through to the env-fallback path instead of being grouped with
    `google-gla`.
  - Tests: `opencontractserver/tests/test_llm_model_factory.py` covers provider
    settings-schema extraction, DB-wins/env-fallback resolution, construction
    failure degradation, and the GraphQL-facing secret status surface.
