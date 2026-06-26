- **Extraction: cap runaway agent tool-looping.** With no request budget, a weak model
  could make dozens-to-hundreds of redundant `similarity_search` calls on a hard or absent
  value before pydantic-ai gave up — observed at **100 tool calls / 770 KB message logs /
  ~100 s per cell**, surfacing as `failure_mode=tool_loop_no_output`. The structured run
  (`opencontractserver/llms/agents/pydantic_ai_agents.py::_structured_response_raw`) now
  passes `UsageLimits(request_limit=EXTRACT_AGENT_REQUEST_LIMIT)` (=20, in
  `opencontractserver/constants/llm.py`), bounding cost/latency for the pathological case
  while leaving headroom for legitimate multi-search + `final_result` retries.
