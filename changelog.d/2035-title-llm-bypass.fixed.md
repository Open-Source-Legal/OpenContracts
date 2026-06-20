- **Conversation-title generation now honours the configured LLM instead of a
  hardcoded `gpt-4o-mini`.** `UnifiedAgentConsumer._generate_conversation_title`
  (`config/websocket/consumers/unified_agent_conversation.py`) called the
  OpenAI-only `SimpleLLMClient`, which hardcoded `gpt-4o-mini` and ignored the
  corpus `preferred_llm` and the install-wide `PipelineSettings.default_llm` —
  the one runtime LLM path that bypassed the Singleton registry. It now routes
  through a new provider-agnostic, registry-backed helper
  `opencontractserver.llms.completions.agenerate_text`, which walks the same
  resolution chain as the agent factory (per-call → `corpus_preferred` →
  install-wide default → Django settings) and builds the model via the
  credential-aware `model_factory`, so titles use whichever LLM the corpus is
  configured for (OpenAI, Anthropic, Google, Ollama, …).
