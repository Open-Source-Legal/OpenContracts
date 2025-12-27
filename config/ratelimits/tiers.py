"""
User tier-based rate limiting logic.

This module provides functions to determine rate limit multipliers based on
user authentication status and privileges. Used by both GraphQL and WebSocket
rate limiting.
"""

from typing import Callable

from django.contrib.auth.models import AnonymousUser

# Tier multipliers - consistent across GraphQL and WebSocket
TIER_MULTIPLIERS = {
    "superuser": 10.0,  # Superusers get 10x the base limit
    "authenticated": 2.0,  # Authenticated users get 2x the base limit
    "anonymous": 1.0,  # Anonymous users get the base limit
    "usage_capped": 0.5,  # Usage-capped users get half the limit
}


def is_user_authenticated(user) -> bool:
    """
    Check if a user is authenticated.

    Handles various user object types including AnonymousUser.

    Args:
        user: User object (may be None, AnonymousUser, or authenticated user)

    Returns:
        True if user is authenticated, False otherwise
    """
    if user is None:
        return False

    if isinstance(user, AnonymousUser):
        return False

    # Check is_authenticated - it may be a property or method
    is_auth = getattr(user, "is_authenticated", False)
    if callable(is_auth):
        return is_auth()
    return bool(is_auth)


def get_tier_multiplier(user) -> float:
    """
    Get the rate limit multiplier for a user based on their tier.

    Multipliers stack for authenticated users:
    - Base authenticated users get 2x
    - Superusers get 10x (instead of 2x)
    - Usage-capped users get 0.5x applied ON TOP of authenticated (2x * 0.5 = 1x)

    Args:
        user: User object

    Returns:
        Multiplier to apply to base rate limit
    """
    if not is_user_authenticated(user):
        return TIER_MULTIPLIERS["anonymous"]

    # Check for superuser (highest priority multiplier)
    if hasattr(user, "is_superuser") and user.is_superuser:
        return TIER_MULTIPLIERS["superuser"]

    # Start with authenticated multiplier
    multiplier = TIER_MULTIPLIERS["authenticated"]

    # Apply usage-capped reduction on top of authenticated multiplier
    if hasattr(user, "is_usage_capped") and user.is_usage_capped:
        multiplier = multiplier * TIER_MULTIPLIERS["usage_capped"]

    return multiplier


def get_user_tier_rate(operation_type: str) -> Callable:
    """
    Returns a function that determines rate limits based on user tier.

    This is the main function used by GraphQL dynamic rate limiting.
    It returns a callable that can be passed to graphql_ratelimit_dynamic.

    Args:
        operation_type: Type of operation from RateLimits class
                       (e.g., "READ_MEDIUM", "WRITE_HEAVY")

    Returns:
        Function that takes (root, info) and returns appropriate rate string

    Example:
        @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
        def resolve_documents(root, info, **kwargs):
            ...
    """
    from config.ratelimits.config import RateLimits
    from config.ratelimits.core import apply_multiplier_to_rate

    def get_rate(root, info):
        user = info.context.user
        base_rate = RateLimits.get(operation_type, RateLimits.READ_MEDIUM)
        multiplier = get_tier_multiplier(user)
        return apply_multiplier_to_rate(base_rate, multiplier)

    return get_rate
