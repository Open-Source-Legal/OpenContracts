- Deep research: the closures built in `research_tasks.py` were audited
  **twice**. They are handed to the agent factory as caller tools and land in
  the same resolved toolset `_audit_default_toolset` walks, so every
  `record_finding` / `find_citable_passages` / `finalize_report` call wrote two
  audit rows — visible as `finalize_report: 2` on runs that can only call it
  once. Not cosmetic: the step-budget counter reads the log length, so a run at
  27 real tool calls was told "54 of 60 used" and pushed to finalize with half
  its budget unspent.
  The first attempt at a guard did not work. It marked an attribute on this
  module's wrapper, but the factory RE-WRAPS caller tools, so the callable
  reachable at `Tool.function_schema.function` is the factory's wrapper and
  carries no marker; the unit test passed only because it placed our wrapper
  there directly. The skip is now by NAME (`already_audited`), which does not
  depend on surviving a wrapper we do not control, with the attribute check
  kept as a second line of defence. Any tool-count comparison spanning commits
  `e50015cc4`–`c61ce1b7e` mixes the two counting regimes.
