"""Constants for community stats caching."""

# Cache community stats for 2 minutes. These are aggregate platform
# metrics (user counts, annotation counts, message counts) that don't
# need real-time accuracy. The landing page polls every 5 minutes, so
# a 2-minute TTL provides freshness while avoiding 7+ expensive COUNT
# queries on every page load.
COMMUNITY_STATS_CACHE_TTL = 120
