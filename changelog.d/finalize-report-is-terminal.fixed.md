- `finalize_report` is documented as terminal — "once you call it, the run
  ends" — but nothing enforced it, and a second call is not a no-op. It re-runs
  composition, so the stored report becomes the LATER body while both passes'
  warnings accumulate. Observed live: a run finalized twice 25 seconds apart
  and its report carried each warning twice, the two passes disagreeing about
  how many sentences had lost their citations (5, then 3) — a reader cannot
  tell that is one report composed twice rather than two distinct problems. The
  tool now refuses a second call once the report is COMPLETED
  (`research_tasks.py`). `ResearchReportService.finalize` itself stays
  non-idempotent on purpose: the salvage path depends on finalizing a report
  the agent never finished. A test pins that service behaviour so the guard is
  not later removed as redundant.
