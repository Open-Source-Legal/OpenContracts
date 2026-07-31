- Deep research: a run is capped at `request_limit = report.max_steps` MODEL
  REQUESTS as well as at a token budget, and the agent could not see that
  counter. A run that walked into it was cut off before it could call
  `finalize_report`, and the salvage composition that replaced its report body
  silently dropped work the agent had recorded nowhere else (observed: exactly
  60 of 60 permitted requests, and a salvaged body that dropped two of the four
  ramp steps the task asked it to walk). Every tool return now carries a
  step-budget notice past `DEEP_RESEARCH_STEP_BUDGET_WARN_RATIO`, and a
  finalize-now notice past `DEEP_RESEARCH_STEP_BUDGET_FINAL_RATIO`
  (`opencontractserver/research/constants.py::build_step_budget_notice`,
  attached in `research_tasks.py::_audited` — the one place every tool call
  passes through). `ResearchReportService.append_tool_call` now returns the new
  log length, which is the running count it warns from.
- Deep research: every ending that was not an explicit `finalize_report` was
  recorded as the single warning `budget_exhausted`, which reads as "ran out of
  context" and was taken to mean it. It covers three unrelated endings — the
  token budget, the step budget, and an agent that simply stopped — and the
  report kept no evidence of which, because `CoreAgent.chat()` swallows the
  framework exception (so there is no traceback in the worker log either). A
  run cut off at the step limit was diagnosed as a context runaway on that
  basis, and the compaction ratio was tuned in response to a limit it cannot
  move. Reports now also carry `terminal_reason: …`
  (`research_tasks.py::_terminal_reason`), and `CoreAgent.chat()` puts
  `error_type` in its response metadata — parity with the streaming wrapper,
  which already did.
