"""Constants for community stats caching."""

import os

__all__ = ["COMMUNITY_STATS_CACHE_TTL"]

# Cache community stats for 1 hour by default. These are aggregate platform
# metrics (user counts, annotation counts, message counts) that don't need
# real-time accuracy. Configurable via COMMUNITY_STATS_CACHE_TTL env var
# (value in seconds) to allow tuning without code changes.
COMMUNITY_STATS_CACHE_TTL = int(os.environ.get("COMMUNITY_STATS_CACHE_TTL", "3600"))
