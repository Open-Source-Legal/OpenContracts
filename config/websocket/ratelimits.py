"""
WebSocket rate limiting decorators and utilities.

This module provides rate limiting for WebSocket connections and messages.
It uses the shared config.ratelimits infrastructure for consistency with
the GraphQL rate limiting.

Rate limiting is applied at two levels:
1. Connection rate limiting - limits how often a user/IP can establish new connections
2. Message rate limiting - limits how many messages a user/IP can send per time period
"""

import functools
import json
import logging
from typing import Callable, Optional

from django.conf import settings

# Import from shared module
from config.ratelimits import (
    RateLimits,
    check_rate_limit_async,
    parse_rate,
    period_to_name,
)
from config.ratelimits.cache import check_rate_limit, get_rate_limit_key
from config.ratelimits.ip import get_client_ip_from_scope

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "WebSocketRateLimitExceeded",
    "get_client_ip_from_scope",
    "get_rate_limit_key",
    "parse_rate",
    "check_rate_limit",
    "check_rate_limit_async",
    "WebSocketRateLimits",
    "websocket_ratelimit",
    "RateLimitedConsumerMixin",
]


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


class _WebSocketRateLimits:
    """
    WebSocket-specific rate limit accessor.

    Provides a convenient interface to access WebSocket rate limits
    from the unified RateLimits configuration.
    """

    def get_rate_for_user(self, rate_type: str, user) -> str:
        """
        Get the appropriate rate limit based on user authentication status.

        Args:
            rate_type: Base rate type (e.g., "WS_CONNECT", "WS_MESSAGE")
            user: The user object from scope

        Returns:
            The rate limit string to apply
        """
        return RateLimits.get_ws_rate_for_user(rate_type, user)

    def __getattr__(self, name):
        """Delegate attribute access to the unified RateLimits."""
        return getattr(RateLimits, name)


# Singleton instance for backward compatibility
WebSocketRateLimits = _WebSocketRateLimits()


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
              uses rate_type to look up from RateLimits.
        rate_type: Rate limit type from RateLimits
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
                try:
                    count, period_seconds = parse_rate(effective_rate)
                    period_name = period_to_name(period_seconds)
                    error_msg = (
                        f"Rate limit exceeded: Max {count} requests per {period_name}. "
                        "Please try again later."
                    )
                except ValueError:
                    error_msg = "Rate limit exceeded. Please try again later."

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

    Provides helper methods for checking rate limits in connect() and receive().

    Usage:
        class MyConsumer(RateLimitedConsumerMixin, AsyncWebsocketConsumer):
            connect_rate_type = "WS_CONNECT"
            message_rate_type = "WS_AI_QUERY"

            async def connect(self):
                if not await self.check_connect_rate_limit():
                    return
                await self.accept()

            async def receive(self, text_data):
                if not await self.check_message_rate_limit():
                    return
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
            try:
                count, period_seconds = parse_rate(rate)
                period_name = period_to_name(period_seconds)
                message = (
                    f"Rate limit exceeded: Max {count} requests per {period_name}."
                )
            except ValueError:
                message = "Rate limit exceeded."

            self._rate_limit_info = {
                "message": message,
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
