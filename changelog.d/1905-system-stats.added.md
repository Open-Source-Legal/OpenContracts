- **Materialised install-wide statistics (`SystemStats`).** A new singleton
  model (`opencontractserver/users/models.py`) holds pre-computed headline
  counts (active users, documents with an active path, corpuses, non-structural
  annotations, conversations, chat messages), refreshed hourly by the
  `refresh_system_stats` Celery beat task
  (`opencontractserver/tasks/stats_tasks.py`;
  `SYSTEM_STATS_REFRESH_INTERVAL_SECONDS` in
  `opencontractserver/constants/stats.py`). Surfaced via the GraphQL
  `systemStats` query (`config/graphql/stats_queries.py`) so dashboards/landing
  tiles read one indexed row instead of running full-table `COUNT`s on every
  page load. These are GLOBAL (not permission-scoped) counts. The count
  definitions live in one place (`SystemStats.compute_values()`) and are shared
  by the telemetry heartbeat (`telemetry_tasks.send_usage_heartbeat`) so the two
  can never drift. Migration: `users/0031_systemstats.py`.
