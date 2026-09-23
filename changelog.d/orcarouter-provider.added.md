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
  forwarded to the gateway. Only `orcarouter/auto` is offered in the picker; it
  gets a conservative 64K `MODEL_CONTEXT_WINDOWS` entry
  (`opencontractserver/constants/context_guardrails.py`) because the routed
  model's window is unknowable per request.
- **`_is_valid_base_url()` helper** (`opencontractserver/llms/model_factory.py`)
  now owns the DB `base_url` http(s) scheme check for every provider, replacing
  the inline copy in `_construct_model`.
