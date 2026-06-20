- **Removed the registry-bypassing `SimpleLLMClient`** (`opencontractserver/llms/client.py`)
  and its `LLM_CLIENT_PROVIDER` / `LLM_CLIENT_MODEL` / `LLM_CLIENT_TEMPERATURE`
  / `LLM_CLIENT_MAX_TOKENS` settings. It was an OpenAI-only chat wrapper that
  hardcoded `gpt-4o-mini` and never consulted the LLM Singleton registry; its
  sole production caller (conversation-title generation) now uses the
  registry-backed `agenerate_text`. The dead-code `SimpleLLMClient` typing tests
  were dropped and the `docs/architecture/llms/README.md` "SimpleLLMClient"
  section now documents `agenerate_text` instead.
