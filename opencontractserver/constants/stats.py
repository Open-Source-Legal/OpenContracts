"""Constants for the materialised system-statistics surface (issue #1908).

Install-wide headline metrics (document/corpus/annotation counts, …) are too
expensive to recompute on every page load once annotation volume reaches the
hundreds of thousands. ``opencontractserver.users.models.SystemStats`` holds a
singleton snapshot refreshed on a schedule by
``opencontractserver.tasks.stats_tasks.refresh_system_stats``; readers fetch
the pre-computed row in a single indexed PK lookup.
"""

# How often the periodic Celery beat task recomputes the SystemStats snapshot.
# Hourly matches the freshness the headline tiles need without hammering the
# database with full-table COUNTs. Kept as a constant so the beat schedule in
# ``config/settings/base.py`` and any docs/tests reference one source of truth.
SYSTEM_STATS_REFRESH_INTERVAL_SECONDS = 60 * 60  # 60 minutes
