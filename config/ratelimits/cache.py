"""
Cache-based rate limiting implementation.

This module provides direct cache-based rate limiting for contexts where
django-ratelimit cannot be used (e.g., ASGI WebSocket consumers).

Uses Django's cache backend for atomic rate limit tracking.
"""

import logging
from typing import Tuple

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches

from config.ratelimits.core import parse_rate
from config.ratelimits.ip import get_client_ip_from_scope

logger = logging.getLogger(__name__)


def get_rate_limit_key(scope: dict, group: str) -> str:
    """
    Generate a rate limit key based on user or IP.

    For authenticated users, uses user ID.
    For anonymous users, uses IP address.

    Args:
        scope: The ASGI scope dictionary
        group: The rate limit group name

    Returns:
        A string key for rate limiting
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
) -> Tuple[bool, dict]:
    """
    Check if a request is rate limited using Django's cache backend.

    This is the core rate limiting function for WebSocket consumers.
    It uses atomic cache operations to track request counts.

    Args:
        scope: The ASGI scope dictionary
        group: The rate limit group name
        rate: Rate limit string (e.g., "10/m")
        increment: Whether to increment the counter

    Returns:
        Tuple of (is_limited, info_dict)
        info_dict contains: limit, remaining, reset_time, key
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
        # Get current count
        current = cache.get(full_key, 0)

        is_limited = current >= max_count

        if increment and not is_limited:
            # Use cache.add for atomic increment with TTL
            # If key doesn't exist, set it with TTL
            if current == 0:
                cache.set(full_key, 1, period_seconds)
            else:
                # Increment existing counter
                try:
                    cache.incr(full_key)
                except ValueError:
                    # Key expired between get and incr, reset it
                    cache.set(full_key, 1, period_seconds)

            current += 1

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
        # If cache is unavailable, check RATELIMIT_FAIL_OPEN setting
        fail_open = getattr(settings, "RATELIMIT_FAIL_OPEN", False)
        if fail_open:
            logger.error(
                f"Rate limit cache error (failing open): {e}", exc_info=True
            )
            return False, {"limit": 0, "remaining": 0, "reset_time": 0}
        else:
            logger.error(
                f"Rate limit cache error (failing closed): {e}", exc_info=True
            )
            return True, {"limit": 0, "remaining": 0, "reset_time": 0}


async def check_rate_limit_async(
    scope: dict,
    group: str,
    rate: str,
    increment: bool = True,
) -> Tuple[bool, dict]:
    """
    Async wrapper for check_rate_limit.

    Uses database_sync_to_async to run the synchronous cache operations
    in a thread pool, making it safe for async WebSocket consumers.

    Args:
        scope: The ASGI scope dictionary
        group: The rate limit group name
        rate: Rate limit string (e.g., "10/m")
        increment: Whether to increment the counter

    Returns:
        Tuple of (is_limited, info_dict)
    """
    from channels.db import database_sync_to_async

    return await database_sync_to_async(check_rate_limit)(
        scope, group, rate, increment
    )
