- Fixed `Corpus.corpus_agent_instructions` and `Corpus.document_agent_instructions`
  being silently discarded on every corpus and document agent
  (`opencontractserver/llms/agents/agent_factory.py`,
  `opencontractserver/llms/agents/core_agents.py`). Both `_inject_temporal_grounding`
  and `_inject_corpus_memory` wrote straight to `config.system_prompt` before
  `CoreCorpusAgentFactory.create_context` / `CoreDocumentAgentFactory.create_context`
  resolved their default prompt via `if config.system_prompt is None`, consuming
  that "was a prompt supplied?" signal before it could be read. The configured
  persona round-tripped through the database and API correctly, so any check of
  the form "are the instructions set?" passed while the agent ran without them —
  measured on a real corpus, a 657-character prompt (temporal grounding only)
  instead of the expected 16,072 characters including the persona.

  `AgentConfig` gains `computed_preamble`: both injectors now stash there when
  no prompt has been resolved yet, and `_apply_computed_preamble` appends it to
  `system_prompt` after the default resolves. Behavior for callers passing an
  explicit `system_prompt` is unchanged.
