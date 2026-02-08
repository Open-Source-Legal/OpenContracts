"""
WebSocket connection-level rate limiting middleware.

Runs before consumers are instantiated. Rejects excessive connection
attempts with close code 4029. Applies per-user (authenticated) or
per-IP (anonymous) rate limits.
"""

import logging
from typing import Any, Callable

from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from config.ratelimits import WS_CLOSE_REASON_MAX_BYTES, parse_rate, period_to_name
from config.ratelimits.cache import check_rate_limit
from config.ratelimits.ip import get_client_ip_from_scope
from config.websocket.ratelimits import WebSocketRateLimits

logger = logging.getLogger(__name__)


class WebSocketRateLimitMiddleware(BaseMiddleware):
    """
    ASGI middleware that enforces connection rate limits on WebSocket handshakes.

    Rejects connections with close code 4029 when the limit is exceeded.
    """

    async def __call__(
        self, scope: dict[str, Any], receive: Callable, send: Callable
    ) -> Any:
        if scope["type"] != "websocket":
            return await super().__call__(scope, receive, send)

        if getattr(settings, "RATELIMIT_DISABLE", False):
            return await super().__call__(scope, receive, send)

        user = scope.get("user")
        is_authenticated = (
            user
            and not isinstance(user, AnonymousUser)
            and hasattr(user, "is_authenticated")
            and user.is_authenticated
        )

        if is_authenticated:
            rate = WebSocketRateLimits.get_rate_for_user("WS_CONNECT", user)
        else:
            rate = WebSocketRateLimits.WS_CONNECT_ANONYMOUS

        is_limited, info = check_rate_limit(scope, "ws_connect", rate, increment=True)

        if is_limited:
            client_ip = get_client_ip_from_scope(scope)
            user_id = getattr(user, "id", "anonymous") if user else "anonymous"

            logger.warning(
                f"WebSocket connection rate limited - "
                f"IP: {client_ip}, User: {user_id}, Rate: {rate}, "
                f"Path: {scope.get('path', 'unknown')}"
            )

            await self._reject_connection(send, rate)
            return

        return await super().__call__(scope, receive, send)

    async def _reject_connection(self, send: Callable, rate: str) -> None:
        """Send a websocket.close with code 4029 (rate limited)."""
        try:
            count, period_seconds = parse_rate(rate)
            reason = f"Rate limit exceeded: {count}/{period_to_name(period_seconds)}"
        except (ValueError, TypeError):
            reason = "Rate limit exceeded"

        await send(
            {
                "type": "websocket.close",
                "code": 4029,
                "reason": reason[:WS_CLOSE_REASON_MAX_BYTES],
            }
        )


def RateLimitMiddleware(inner):
    """
    Factory function for use in ASGI routing:

        RateLimitMiddleware(URLRouter(...))
    """
    return WebSocketRateLimitMiddleware(inner)
