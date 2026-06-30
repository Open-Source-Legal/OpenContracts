- Structured extraction now records a distinct `failure_mode=usage_limit_exceeded`
  when a run trips `EXTRACT_AGENT_REQUEST_LIMIT` instead of mislabelling the
  budget hit as `tool_loop_no_output`/`no_final_response`. `_structured_response_raw`
  (`opencontractserver/llms/agents/pydantic_ai_agents.py`) catches
  `UsageLimitExceeded` explicitly and logs it as a named condition (mirroring the
  streaming `chat()` path), and `_classify_none_result`
  (`opencontractserver/tasks/data_extract_tasks.py`) recognises the budget
  fingerprint from the captured message history. Lets operators tell a too-tight
  request budget from a genuine runaway loop.
- Fixed a latent footgun in `_structured_response_raw`: an explicit
  `usage_limits=None` passed by a caller no longer silently disables the request
  budget (the prior `setdefault` left the `None` in place); the default cap is now
  applied whenever the resolved value is `None`.
