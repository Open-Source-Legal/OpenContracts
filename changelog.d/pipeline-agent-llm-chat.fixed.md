- **Interactive chat now honors `AgentConfiguration.preferred_llm` (the
  per-agent model override).** `config/websocket/consumers/unified_agent_conversation.py`
  `_initialize_agent` built the agent-factory kwargs without
  `agent_preferred_llm`, so the WebSocket chat path silently fell back to the
  corpus / install-wide default model even when the selected agent pinned a
  model — diverging from the Celery (`opencontractserver/tasks/agent_tasks.py`)
  and delegation (`opencontractserver/llms/tools/delegation_tools.py`) paths,
  which already thread it. Now the consumer passes
  `agent_kwargs["agent_preferred_llm"] = self.agent_config.preferred_llm` (when
  set) into `agents.for_document`/`for_corpus`, which the factory treats as the
  top-of-chain override. Regression tests:
  `UnifiedAgentConsumerAgentLlmTestCase` in
  `opencontractserver/tests/websocket/test_unified_agent_consumer.py`.
