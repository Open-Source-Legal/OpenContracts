"""
Cache-based rate limiting for ASGI contexts.

Uses Django's cache backend with atomic operations for rate limit tracking
in WebSocket consumers where django-ratelimit cannot be used.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches

from config.ratelimits.core import parse_rate
from config.ratelimits.ip import get_client_ip_from_scope

logger = logging.getLogger(__name__)


def get_rate_limit_key(scope: dict, group: str) -> str:
    """
    Generate a rate limit cache key from an ASGI scope.

    Authenticated users are keyed by user ID; anonymous users by IP.
    """
    user = scope.get("user")

    if user and not isinstance(user, AnonymousUser) and user.is_authenticated:
        return f"ws:{group}:user:{user.id}"
    else:
        ip = get_client_ip_from_scope(scope)
        return f"ws:{group}:ip:{ip}"


def check_rate_limit(
    scope: dict,
    group: str,
    rate: str,
    increment: bool = True,
) -> tuple[bool, dict]:
    """
    Check if a request is rate limited using Django's cache backend.

    Uses atomic cache.add() + cache.incr() to prevent race conditions.

    Returns:
        Tuple of (is_limited, info_dict) where info_dict contains
        limit, remaining, reset_time, and key.
    """
    if getattr(settings, "RATELIMIT_DISABLE", False):
        return False, {"limit": 0, "remaining": 0, "reset_time": 0}

    try:
        max_count, period_seconds = parse_rate(rate)
    except ValueError as e:
        logger.error(f"Invalid rate limit format: {e}")
        return False, {"limit": 0, "remaining": 0, "reset_time": 0}

    cache_name = getattr(settings, "RATELIMIT_USE_CACHE", "default")
    cache = caches[cache_name]

    key = get_rate_limit_key(scope, group)
    prefix = getattr(settings, "RATELIMIT_KEY_PREFIX", "rl")
    full_key = f"{prefix}:{key}"

    try:
        if increment:
            # Atomically create key with value 0 if it doesn't exist
            cache.add(full_key, 0, period_seconds)

            # Atomically increment
            try:
                current = cache.incr(full_key)
            except ValueError:
                # Key expired between add and incr (rare race condition)
                cache.set(full_key, 1, period_seconds)
                current = 1

            is_limited = current > max_count
        else:
            current = cache.get(full_key, 0)
            is_limited = current >= max_count

        remaining = max(0, max_count - current)

        info = {
            "limit": max_count,
            "remaining": remaining,
            "reset_time": period_seconds,
            "key": key,
        }

        if is_limited:
            logger.warning(
                f"WebSocket rate limit exceeded - Group: {group}, "
                f"Key: {key}, Rate: {rate}"
            )

        return is_limited, info

    except Exception as e:
        fail_open = getattr(settings, "RATELIMIT_FAIL_OPEN", False)
        if fail_open:
            logger.error(f"Rate limit cache error (failing open): {e}", exc_info=True)
            return False, {"limit": 0, "remaining": 0, "reset_time": 0}
        else:
            logger.error(f"Rate limit cache error (failing closed): {e}", exc_info=True)
            return True, {"limit": 0, "remaining": 0, "reset_time": 0}


async def check_rate_limit_async(
    scope: dict,
    group: str,
    rate: str,
    increment: bool = True,
) -> tuple[bool, dict]:
    """Async wrapper for check_rate_limit, safe for ASGI consumers."""
    from channels.db import database_sync_to_async

    return await database_sync_to_async(check_rate_limit)(scope, group, rate, increment)
