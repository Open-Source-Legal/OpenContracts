- **Deep-research durable context management: living plan + agent memory + crash recovery.**
  The deep-research agent could exhaust its context window on long
  investigations and fail without a graceful recovery path. It now has a
  durable working surface that survives both in-run context compaction (the
  system prompt is never compacted) and a worker restart:
  - **Living plan** — `ResearchReport.plan` (new field). `update_research_plan` /
    `get_research_plan` tools let the agent maintain a high-level plan that is
    re-injected at the top of the system prompt on *every* run. Clamped to
    `MAX_RESEARCH_PLAN_CHARS` (head-preserving truncation).
  - **Memory store** — `ResearchReport.memory` (new JSON field). `write_memory`
    (replace/append), `read_memory`, `list_memory`, `delete_memory`, and a
    grep-like `search_memory` (scans memory entries *and* recorded findings)
    let the agent offload far more than fits in context. Bounded by per-key,
    per-value, key-count, and total-store caps
    (`opencontractserver/research/constants.py`), surfaced to the model as
    operational error strings (cap violations raise `ResearchMemoryLimitExceeded`;
    malformed input raises the `ResearchMemoryError` base) rather than crashing
    the job.
  - **Resume after crash** — a worker that picks up a report already in
    `RUNNING` now resumes instead of restarting: `mark_started(resuming=True)`
    preserves the original `started_at`, and `build_recovery_digest` primes the
    system prompt with the plan, a tail digest of findings, and the memory
    index. New periodic task `reap_stalled_research` (beat: every 5 min)
    re-enqueues RUNNING reports whose `last_progress_at` is colder than
    `DEEP_RESEARCH_STUCK_THRESHOLD_SECONDS` via `ResearchReportService.resume`
    (single `pk__in` fetch, no N+1).
  - Files: `opencontractserver/research/models.py` (+migrations
    `0002_researchreport_plan_memory`, `0003_rename_researchreport_indexes`),
    `.../research/constants.py`, `.../research/services/research_reports.py`,
    `opencontractserver/tasks/research_tasks.py`, `config/settings/base.py`
    (beat entry). Tests:
    `opencontractserver/tests/research/test_research_memory.py`.
