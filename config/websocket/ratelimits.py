"""
WebSocket rate limiting utilities.

This module provides rate limiting for WebSocket connections and messages,
using the same django-ratelimit infrastructure as the GraphQL API.

Rate limiting is applied at two levels:
1. Connection rate limiting - limits how often a user/IP can establish new connections
2. Message rate limiting - limits how many messages a user/IP can send per time period

Uses per-user limits for authenticated users and per-IP limits for anonymous users,
consistent with the GraphQL rate limiting approach.
"""

import functools
import logging
from typing import Callable, Optional

from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches

logger = logging.getLogger(__name__)


class WebSocketRateLimitExceeded(Exception):
    """Exception raised when WebSocket rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        close_code: int = 4029,
    ):
        super().__init__(message)
        self.close_code = close_code
        self.message = message


def get_client_ip_from_scope(scope: dict) -> str:
    """
    Get the client's IP address from the WebSocket scope.
    Handles X-Forwarded-For header for requests behind proxies.

    Args:
        scope: The ASGI scope dictionary

    Returns:
        The client's IP address as a string
    """
    # Check headers for X-Forwarded-For (common when behind proxies like Traefik)
    headers = dict(scope.get("headers", []))

    # Headers are byte strings in ASGI
    x_forwarded_for = headers.get(b"x-forwarded-for", b"").decode("utf-8")
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return x_forwarded_for.split(",")[0].strip()

    # Fall back to client address from scope
    client = scope.get("client")
    if client:
        return client[0]  # (host, port) tuple

    return "unknown"


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


def parse_rate(rate: str) -> tuple[int, int]:
    """
    Parse a rate string like "10/m" into (count, seconds).

    Supported periods:
    - s: seconds
    - m: minutes
    - h: hours
    - d: days

    Args:
        rate: Rate string (e.g., "10/m" for 10 per minute)

    Returns:
        Tuple of (max_count, period_in_seconds)
    """
    parts = rate.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid rate format: {rate}")

    count = int(parts[0])
    period_char = parts[1].lower()

    period_seconds = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }.get(period_char)

    if period_seconds is None:
        raise ValueError(f"Invalid period in rate: {rate}")

    return count, period_seconds


def check_rate_limit(
    scope: dict,
    group: str,
    rate: str,
    increment: bool = True,
) -> tuple[bool, dict]:
    """
    Check if a request is rate limited using Django's cache backend.

    Args:
        scope: The ASGI scope dictionary
        group: The rate limit group name
        rate: Rate limit string (e.g., "10/m")
        increment: Whether to increment the counter

    Returns:
        Tuple of (is_limited, info_dict)
        info_dict contains: limit, remaining, reset_time
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


@database_sync_to_async
def check_rate_limit_async(
    scope: dict,
    group: str,
    rate: str,
    increment: bool = True,
) -> tuple[bool, dict]:
    """
    Async wrapper for check_rate_limit.

    Args:
        scope: The ASGI scope dictionary
        group: The rate limit group name
        rate: Rate limit string (e.g., "10/m")
        increment: Whether to increment the counter

    Returns:
        Tuple of (is_limited, info_dict)
    """
    return check_rate_limit(scope, group, rate, increment)


class WebSocketRateLimits:
    """
    WebSocket rate limit configurations.

    Provides default rate limits that can be overridden via settings.
    """

    _defaults = {
        # Connection rate limits
        "WS_CONNECT": "30/m",  # 30 connection attempts per minute
        "WS_CONNECT_ANONYMOUS": "10/m",  # 10 for anonymous users
        # Message rate limits
        "WS_MESSAGE": "60/m",  # 60 messages per minute
        "WS_MESSAGE_ANONYMOUS": "20/m",  # 20 for anonymous users
        # AI query rate limits (for agent consumers)
        "WS_AI_QUERY": "20/m",  # 20 AI queries per minute
        "WS_AI_QUERY_ANONYMOUS": "5/m",  # 5 for anonymous users
    }

    def __init__(self):
        # Apply overrides from settings if available
        overrides = getattr(settings, "WEBSOCKET_RATE_LIMIT_OVERRIDES", {})
        for key, default_value in self._defaults.items():
            setattr(self, key, overrides.get(key, default_value))

    def __getattr__(self, name):
        if name in self._defaults:
            return self._defaults[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    def get_rate_for_user(self, rate_type: str, user) -> str:
        """
        Get the appropriate rate limit based on user authentication status.

        Args:
            rate_type: Base rate type (e.g., "WS_CONNECT", "WS_MESSAGE")
            user: The user object from scope

        Returns:
            The rate limit string to apply
        """
        is_authenticated = (
            user
            and not isinstance(user, AnonymousUser)
            and user.is_authenticated
        )

        if is_authenticated:
            # Check for superuser - give them higher limits
            if hasattr(user, "is_superuser") and user.is_superuser:
                base_rate = getattr(self, rate_type, self._defaults.get(rate_type, "60/m"))
                count, period = parse_rate(base_rate)
                return f"{count * 5}/{period}"  # 5x for superusers
            return getattr(self, rate_type, self._defaults.get(rate_type, "60/m"))
        else:
            # Use anonymous rate limit
            anon_type = f"{rate_type}_ANONYMOUS"
            return getattr(
                self, anon_type, self._defaults.get(anon_type, "10/m")
            )


# Singleton instance
WebSocketRateLimits = WebSocketRateLimits()


def websocket_ratelimit(
    group: Optional[str] = None,
    rate: Optional[str] = None,
    rate_type: str = "WS_MESSAGE",
):
    """
    Decorator for rate limiting WebSocket consumer methods.

    Can be applied to connect() or receive() methods.

    Args:
        group: Optional group name for shared rate limits
        rate: Optional explicit rate (e.g., "10/m"). If not provided,
              uses rate_type to look up from WebSocketRateLimits.
        rate_type: Rate limit type from WebSocketRateLimits
                   (e.g., "WS_CONNECT", "WS_MESSAGE", "WS_AI_QUERY")

    Example:
        class MyConsumer(AsyncWebsocketConsumer):
            @websocket_ratelimit(rate_type="WS_CONNECT")
            async def connect(self):
                await self.accept()

            @websocket_ratelimit(rate_type="WS_MESSAGE")
            async def receive(self, text_data):
                # Handle message
                pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Skip if rate limiting is disabled
            if getattr(settings, "RATELIMIT_DISABLE", False):
                return await func(self, *args, **kwargs)

            scope = self.scope
            user = scope.get("user")

            # Determine rate to use
            effective_rate = rate
            if effective_rate is None:
                effective_rate = WebSocketRateLimits.get_rate_for_user(rate_type, user)

            # Determine group name
            effective_group = group or f"{rate_type}:{func.__name__}"

            # Check rate limit
            is_limited, info = await check_rate_limit_async(
                scope, effective_group, effective_rate, increment=True
            )

            if is_limited:
                # Format error message
                count, period = parse_rate(effective_rate)
                period_name = {1: "second", 60: "minute", 3600: "hour", 86400: "day"}.get(
                    period, "period"
                )

                error_msg = (
                    f"Rate limit exceeded: Max {count} requests per {period_name}. "
                    "Please try again later."
                )

                # For connect method, close the connection
                if func.__name__ == "connect":
                    logger.warning(
                        f"WebSocket connection rate limited - "
                        f"Key: {info.get('key', 'unknown')}, Rate: {effective_rate}"
                    )
                    await self.close(code=4029)
                    return

                # For receive method, send error and continue
                logger.warning(
                    f"WebSocket message rate limited - "
                    f"Key: {info.get('key', 'unknown')}, Rate: {effective_rate}"
                )

                # Try to send error message if connection is open
                try:
                    import json

                    await self.send(
                        json.dumps(
                            {
                                "type": "RATE_LIMITED",
                                "content": error_msg,
                                "data": {
                                    "limit": info.get("limit", 0),
                                    "remaining": 0,
                                    "retry_after": info.get("reset_time", 60),
                                },
                            }
                        )
                    )
                except Exception:
                    pass  # Connection might be closed

                return

            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


class RateLimitedConsumerMixin:
    """
    Mixin class that adds rate limiting to WebSocket consumers.

    Automatically applies rate limiting to connect() and receive() methods.

    Usage:
        class MyConsumer(RateLimitedConsumerMixin, AsyncWebsocketConsumer):
            # Rate limiting is automatically applied

            async def connect(self):
                await super().connect()  # Rate limit check happens here
                await self.accept()

            async def receive(self, text_data):
                await super().receive(text_data)  # Rate limit check happens here
                # Handle message
    """

    # Override these in subclasses to customize rate limits
    connect_rate_type: str = "WS_CONNECT"
    message_rate_type: str = "WS_MESSAGE"

    async def _check_rate_limit(self, rate_type: str) -> bool:
        """
        Check rate limit and return True if allowed, False if limited.

        Args:
            rate_type: The rate limit type to check

        Returns:
            True if request is allowed, False if rate limited
        """
        if getattr(settings, "RATELIMIT_DISABLE", False):
            return True

        scope = self.scope
        user = scope.get("user")
        rate = WebSocketRateLimits.get_rate_for_user(rate_type, user)

        is_limited, info = await check_rate_limit_async(
            scope, rate_type, rate, increment=True
        )

        if is_limited:
            count, period = parse_rate(rate)
            period_name = {1: "second", 60: "minute", 3600: "hour", 86400: "day"}.get(
                period, "period"
            )
            self._rate_limit_info = {
                "message": f"Rate limit exceeded: Max {count} requests per {period_name}.",
                "limit": info.get("limit", 0),
                "retry_after": info.get("reset_time", 60),
            }
            return False

        return True

    async def check_connect_rate_limit(self) -> bool:
        """
        Check connection rate limit.

        Returns:
            True if connection is allowed, False if rate limited
        """
        return await self._check_rate_limit(self.connect_rate_type)

    async def check_message_rate_limit(self) -> bool:
        """
        Check message rate limit.

        Returns:
            True if message is allowed, False if rate limited
        """
        return await self._check_rate_limit(self.message_rate_type)

    def get_rate_limit_error(self) -> dict:
        """
        Get the last rate limit error info.

        Returns:
            Dict with error details or empty dict
        """
        return getattr(self, "_rate_limit_info", {})
