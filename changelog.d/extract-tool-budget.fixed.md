- **Extraction: cap runaway agent tool-looping.** With no request budget, a weak model
  could make dozens-to-hundreds of redundant `similarity_search` calls on a hard or absent
  value before pydantic-ai gave up — observed at **100 tool calls / 770 KB message logs /
  ~100 s per cell**, surfacing as `failure_mode=tool_loop_no_output`. The structured run
  (`opencontractserver/llms/agents/pydantic_ai_agents.py::_structured_response_raw`) now
  applies a default request ceiling — `UsageLimits(request_limit=EXTRACT_AGENT_REQUEST_LIMIT)`
  (=20, in `opencontractserver/constants/llm.py`), tightening pydantic-ai's own default of 50
  — via `run_kwargs.setdefault(...)` so any caller may override it per call (e.g. a
  corpus-wide structured analytic that legitimately needs more round-trips) and so the
  explicit value can never collide with a pass-through `usage_limits` into a duplicate-keyword
  `TypeError`.
