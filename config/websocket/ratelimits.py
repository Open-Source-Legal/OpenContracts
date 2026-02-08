"""
WebSocket rate limiting mixin and utilities.

Provides a RateLimitedConsumerMixin that adds rate limiting to any
AsyncWebsocketConsumer, plus a WebSocketRateLimits convenience accessor.

Rate limiting is applied at two levels:
1. Connection rate limiting — via middleware (see middlewares/ratelimit_middleware.py)
2. Message rate limiting — via the mixin in each consumer's receive()
"""

import json
import logging

from django.conf import settings

from config.ratelimits import (
    RateLimits,
    check_rate_limit_async,
    parse_rate,
    period_to_name,
)

logger = logging.getLogger(__name__)


class _WebSocketRateLimits:
    """
    WebSocket-specific rate limit accessor.

    Delegates to the unified RateLimits config, providing a convenient
    get_rate_for_user() method for WebSocket consumers.
    """

    def get_rate_for_user(self, rate_type: str, user) -> str:
        """Get rate limit string adjusted for user's auth status and tier."""
        return RateLimits.get_ws_rate_for_user(rate_type, user)

    def __getattr__(self, name):
        return getattr(RateLimits, name)


# Singleton instance
WebSocketRateLimits = _WebSocketRateLimits()


class RateLimitedConsumerMixin:
    """
    Mixin that adds message-level rate limiting to AsyncWebsocketConsumer subclasses.

    Override `message_rate_type` to control which rate config is used.
    Call `await self.check_message_rate_limit()` at the top of receive().

    Usage:
        class MyConsumer(RateLimitedConsumerMixin, AsyncWebsocketConsumer):
            message_rate_type = "WS_AI_QUERY"

            async def receive(self, text_data):
                if not await self.check_message_rate_limit():
                    return
                # ... handle message
    """

    # Override in subclasses for consumer-specific rate types
    message_rate_type: str = "WS_MESSAGE"

    async def check_message_rate_limit(self) -> bool:
        """
        Check message rate limit.

        Returns True if the message is allowed, False if rate limited
        (sends a RATE_LIMITED message to the client and returns False).
        """
        if getattr(settings, "RATELIMIT_DISABLE", False):
            return True

        user = self.scope.get("user")
        rate = WebSocketRateLimits.get_rate_for_user(self.message_rate_type, user)

        is_limited, info = await check_rate_limit_async(
            self.scope, self.message_rate_type.lower(), rate, increment=True
        )

        if is_limited:
            try:
                count, period_seconds = parse_rate(rate)
                period_name = period_to_name(period_seconds)
                error_msg = (
                    f"Rate limit exceeded: Max {count} requests per {period_name}. "
                    "Please try again later."
                )
            except ValueError:
                error_msg = "Rate limit exceeded. Please try again later."

            logger.warning(
                f"WebSocket message rate limited - "
                f"Key: {info.get('key', 'unknown')}, Rate: {rate}"
            )

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

            return False

        return True
