"""
User tier-based rate limiting logic.

Provides tier multipliers and helper functions used by both GraphQL
and WebSocket rate limiting.
"""

from typing import Callable

from django.contrib.auth.models import AnonymousUser

# Tier multipliers — consistent across GraphQL and WebSocket
TIER_MULTIPLIERS = {
    "superuser": 10.0,
    "authenticated": 2.0,
    "anonymous": 1.0,
    "usage_capped": 0.5,
}


def is_user_authenticated(user) -> bool:
    """
    Check if a user object represents an authenticated user.

    Handles None, AnonymousUser, and real user objects.
    """
    if user is None:
        return False

    if isinstance(user, AnonymousUser):
        return False

    is_auth = getattr(user, "is_authenticated", False)
    if callable(is_auth):
        return is_auth()
    return bool(is_auth)


def get_tier_multiplier(user) -> float:
    """
    Get the rate limit multiplier for a user based on their tier.

    - Anonymous: 1x (base rate)
    - Authenticated: 2x
    - Superuser: 10x
    - Usage-capped: authenticated * 0.5 = 1x effective
    """
    if not is_user_authenticated(user):
        return TIER_MULTIPLIERS["anonymous"]

    if hasattr(user, "is_superuser") and user.is_superuser:
        return TIER_MULTIPLIERS["superuser"]

    multiplier = TIER_MULTIPLIERS["authenticated"]

    if hasattr(user, "is_usage_capped") and user.is_usage_capped:
        multiplier = multiplier * TIER_MULTIPLIERS["usage_capped"]

    return multiplier


def get_user_tier_rate(operation_type: str) -> Callable:
    """
    Returns a callable for GraphQL dynamic rate limiting.

    The returned function takes (root, info) and returns a rate string
    adjusted for the user's tier.

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
