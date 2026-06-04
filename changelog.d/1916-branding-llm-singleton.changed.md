- **Corpus auto-branding now resolves LLM config from the `PipelineSettings`
  singleton.** The README agent (`opencontractserver/corpuses/services/branding.py`)
  already routes through `agents.for_corpus`, so it now picks up the install-wide
  `default_llm` / per-corpus `preferred_llm` and live DB credentials via
  `model_factory.build_agent_model`. Logo generation
  (`opencontractserver/utils/image_generation.py`) now reads the OpenAI provider's
  live-configured `api_key` / `base_url` from the singleton (DB-wins /
  env-fallback), via the new `model_factory.aget_provider_credentials`, instead of
  reading `OPENAI_API_KEY` straight from the environment — and targets a configured
  custom/compatible gateway endpoint when set.
- Hardened the branding Celery task (`generate_corpus_branding`): use
  `async_to_sync` instead of `asyncio.run` (safe on gevent/eventlet worker pools)
  and add `soft_time_limit` / `time_limit` plus an `asyncio.wait_for` bound on the
  README agent turn so a hung LLM/tool call can never pin a worker indefinitely.
