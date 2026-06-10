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

# ---------------------------------------------------------------------------
# Corpus Intelligence home (document-relationship graph + insight panel)
# ---------------------------------------------------------------------------

# Node cap for the corpus document-relationship graph *glimpse* on the corpus
# landing page. Documents are ranked by degree (relationship count) and the
# top-N are returned; the rest are summarised via ``truncated`` + the
# total counts, and the user follows the "Explore the full graph" escape hatch.
# 60 keeps a force-directed SVG readable and the payload small.
CORPUS_DOCUMENT_GRAPH_MAX_NODES = 60

# How many distinct annotation labels to surface in the IntelligencePanel's
# label-distribution mini-chart before collapsing the long tail.
CORPUS_INTELLIGENCE_LABEL_DISTRIBUTION_TOP_N = 8
