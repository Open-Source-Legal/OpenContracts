- **Non-streaming `agent.chat()` now reports tool calls in `metadata["timeline"]`.**
  `PydanticAICoreAgent._chat_raw` (`opencontractserver/llms/agents/pydantic_ai_agents.py`)
  returned `{"usage": ..., "framework": "pydantic_ai"}` with no `"timeline"` key at
  all, even when the run invoked tools. The streaming path (`_stream_core` via
  `TimelineStreamMixin`) already populated `metadata["timeline"]` with
  `{"type": "tool_call", "tool": ..., "args": ...}` entries, but any caller using
  the plain `agent.chat(...)` non-streaming API — e.g.
  `opencontractserver/benchmarks/traversal_benchmark.py::run_one`, which reads
  `metadata.get("timeline")` and filters for `type == "tool_call"` — silently saw
  zero tool calls regardless of how many the model actually made. Added
  `_extract_tool_call_timeline` (same file, near `_usage_to_dict`), which walks
  `run_result.all_messages()` for `ToolCallPart` instances and reconstructs the
  same timeline-entry shape the streaming path emits; `_chat_raw` now calls it and
  includes the result under `metadata["timeline"]`. Regression test:
  `opencontractserver/tests/test_pydantic_ai_agents.py::TestPydanticAIAgents::test_chat_metadata_includes_tool_call_timeline`.
