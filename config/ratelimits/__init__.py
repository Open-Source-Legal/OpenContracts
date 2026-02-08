"""
Unified rate limiting infrastructure for OpenContracts.

Shared utilities for both GraphQL API and WebSocket connections, ensuring
consistent behavior, configuration, and tier multipliers.
"""

from config.ratelimits.cache import (
    check_rate_limit,
    check_rate_limit_async,
    get_rate_limit_key,
)
from config.ratelimits.config import RateLimits
from config.ratelimits.core import (
    PERIOD_CHAR_NAMES,
    PERIOD_NAMES,
    PERIOD_SECONDS,
    WS_CLOSE_REASON_MAX_BYTES,
    apply_multiplier_to_rate,
    format_rate_limit_message,
    parse_rate,
    period_to_name,
)
from config.ratelimits.ip import (
    get_client_ip_from_request,
    get_client_ip_from_scope,
)
from config.ratelimits.tiers import (
    TIER_MULTIPLIERS,
    get_tier_multiplier,
    get_user_tier_rate,
    is_user_authenticated,
)

__all__ = [
    # Core
    "parse_rate",
    "period_to_name",
    "format_rate_limit_message",
    "apply_multiplier_to_rate",
    "PERIOD_SECONDS",
    "PERIOD_NAMES",
    "PERIOD_CHAR_NAMES",
    "WS_CLOSE_REASON_MAX_BYTES",
    # Config
    "RateLimits",
    # Tiers
    "get_tier_multiplier",
    "get_user_tier_rate",
    "is_user_authenticated",
    "TIER_MULTIPLIERS",
    # IP
    "get_client_ip_from_request",
    "get_client_ip_from_scope",
    # Cache
    "check_rate_limit",
    "check_rate_limit_async",
    "get_rate_limit_key",
]
