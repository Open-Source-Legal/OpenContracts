- `ResearchReport.tool_call_log` recorded only the tools `research_tasks.py`
  builds as closures. Every tool from the agent's DEFAULT toolset —
  `similarity_search`, `list_documents`, `ask_document`, the reference-graph
  tools — was invisible, so the log held roughly half of what a run did and the
  Run details tab presented that half as the whole. Ten runs were read off that
  log as having retrieved only by exact phrase and never once by meaning, and a
  prompt was rewritten on the strength of it; the worker log showed those same
  runs embedding query after query, which only `similarity_search` does. An
  instrument that cannot see a tool reports that the tool was never used.
  `research_tasks.py::_audit_default_toolset` now wraps the resolved toolset
  after the agent is built (`FunctionSchema.call` resolves `self.function` at
  call time, so replacing it intercepts every later invocation). Verified live:
  a run's log now opens `similarity_search: 4, find_citable_passages: 2` where
  the same run previously showed the phrase tool alone.
