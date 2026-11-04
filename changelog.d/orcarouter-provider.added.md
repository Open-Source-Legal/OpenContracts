- **OrcaRouter is now a first-class LLM provider.** The System Settings LLM picker
  offers an `orcarouter:` provider (`opencontractserver/pipeline/llm_providers/orcarouter_provider.py`)
  for [OrcaRouter](https://www.orcarouter.ai), an OpenAI-compatible model routing
  gateway. Set `ORCAROUTER_API_KEY` (or configure it live in System Settings →
  Pipeline Components) and use specs like `orcarouter:orcarouter/auto`. Because
  pydantic-ai has no native `orcarouter:` prefix, `build_agent_model()`
  (`opencontractserver/llms/model_factory.py::_construct_orcarouter_model`)
  always constructs a concrete OpenAI-compatible model for this provider instead
  of returning a bare spec string. With no key configured it sends an inert
  placeholder key and logs a warning, so the install's `OPENAI_API_KEY` is never
  forwarded to the gateway. Only `orcarouter/auto` is offered in the picker.
- **OrcaRouter context windows are fetched from the gateway.**
  `opencontractserver/llms/orcarouter_context.py` reads each model's context
  length from OrcaRouter's `GET /models` listing when the agent model is built
  (TTL-cached, 3s timeout, no redirects, never raises);
  `get_context_window_for_model` serves `orcarouter:` specs from that cache and
  falls back to a conservative `ORCAROUTER_FALLBACK_CONTEXT_WINDOW` (64K,
  `opencontractserver/constants/context_guardrails.py`) until a listing is
  available or when the gateway omits the model.
- **`_is_valid_base_url()` helper** (`opencontractserver/llms/model_factory.py`)
  now owns the DB `base_url` http(s) scheme check for every provider, replacing
  the inline copy in `_construct_model`.
