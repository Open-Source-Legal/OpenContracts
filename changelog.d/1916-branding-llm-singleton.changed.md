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
- The branding README agent now reuses the canonical CAML authoring guide instead
  of an ad-hoc "write GitHub markdown" prompt, so auto-branding produces a real
  CAML article. Extracted the CAML syntax/editorial/structure/output reference
  from `template_seeds.py` into a shared `opencontractserver/corpuses/caml_authoring.py`
  (`CAML_ARTICLE_SYSTEM_INSTRUCTIONS` + the tool-agnostic `CAML_AUTHORING_GUIDE`),
  reused by both the seeded "CAML Article Writer" corpus action and the branding
  agent. The guide is sliced from the full writer prompt, so the seeded prompt is
  byte-for-byte unchanged (no re-seed / production drift).
- Corpus branding degrades gracefully when the OpenAI provider is unregistered:
  `aget_provider_credentials` returns `{}` (no raise) and logo generation falls
  back to the deterministic PIL monogram; README generation is best-effort and
  never blocks corpus creation.
