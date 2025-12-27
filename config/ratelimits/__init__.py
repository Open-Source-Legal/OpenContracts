"""
Unified rate limiting infrastructure for OpenContracts.

This package provides shared rate limiting utilities for both GraphQL API
and WebSocket connections. It ensures consistent behavior, configuration,
and user tier multipliers across all rate-limited endpoints.

Usage:
    # Access rate limit configuration
    from config.ratelimits import RateLimits
    rate = RateLimits.WRITE_MEDIUM  # "10/m"

    # Get user-tier-aware rate for GraphQL
    from config.ratelimits import get_user_tier_rate
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))

    # Parse and format rates
    from config.ratelimits import parse_rate, format_rate_limit_message
    count, seconds = parse_rate("10/m")  # (10, 60)
    message = format_rate_limit_message("10/m")

    # WebSocket cache-based rate limiting
    from config.ratelimits import check_rate_limit_async
    is_limited, info = await check_rate_limit_async(scope, "ws_connect", "30/m")
"""

# Cache-based rate limiting (for WebSocket)
from config.ratelimits.cache import (
    check_rate_limit,
    check_rate_limit_async,
    get_rate_limit_key,
)

# Configuration
from config.ratelimits.config import RateLimits

# Core utilities
from config.ratelimits.core import (
    PERIOD_CHAR_NAMES,
    PERIOD_NAMES,
    PERIOD_SECONDS,
    apply_multiplier_to_rate,
    format_rate_limit_message,
    parse_rate,
    period_char_to_name,
    period_to_name,
)

# IP extraction
from config.ratelimits.ip import (
    get_client_ip_from_request,
    get_client_ip_from_scope,
)

# User tier logic
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
    "period_char_to_name",
    "format_rate_limit_message",
    "apply_multiplier_to_rate",
    "PERIOD_SECONDS",
    "PERIOD_NAMES",
    "PERIOD_CHAR_NAMES",
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
