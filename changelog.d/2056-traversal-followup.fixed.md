- Corrected the non-streaming `agent.chat()` tool-call timeline
  (`opencontractserver/llms/agents/pydantic_ai_agents.py::_extract_tool_call_timeline`):
  it read `run_result.all_messages()`, which includes the `message_history`
  `_chat_raw` forwards, so a multi-turn conversation re-counted every prior
  turn's tool calls (turn N reporting the tool calls of turns 1..N). It now
  reads `new_messages()` — only the current run's messages.
- Extended the graph-navigation bad-ID guard to `find_documents_citing`
  (`opencontractserver/llms/tools/core_tools/graph_navigation.py`): a
  `document_id` anchor that does not resolve to a visible document now returns
  an explicit error instead of a false-empty "nobody cites this" envelope,
  matching the fix already applied to `get_document_references`.
