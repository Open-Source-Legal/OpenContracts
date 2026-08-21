- **OrcaRouter is now a first-class LLM provider.** The System Settings LLM picker
  offers an `orcarouter:` provider (`opencontractserver/pipeline/llm_providers/orcarouter_provider.py`)
  for [OrcaRouter](https://www.orcarouter.ai), an OpenAI-compatible model routing
  gateway. Set `ORCAROUTER_API_KEY` (or configure it live in System Settings →
  Pipeline Components) and use specs like `orcarouter:orcarouter/auto`. Because
  pydantic-ai has no native `orcarouter:` prefix, `build_agent_model()`
  (`opencontractserver/llms/model_factory.py`) always constructs a concrete
  OpenAI-compatible model for this provider instead of returning a bare spec
  string — so a picked `orcarouter:` model can never surface an unresolvable spec.
