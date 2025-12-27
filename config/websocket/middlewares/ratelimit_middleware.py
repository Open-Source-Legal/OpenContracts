"""
WebSocket Rate Limiting Middleware.

This middleware applies connection-level rate limiting to all WebSocket connections.
It runs before consumers are instantiated, preventing excessive connection attempts.

Rate limiting is applied per-user for authenticated users and per-IP for anonymous users.
"""

import logging
from typing import Any, Callable

from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from config.ratelimits import parse_rate, period_to_name
from config.ratelimits.cache import check_rate_limit
from config.ratelimits.ip import get_client_ip_from_scope
from config.websocket.ratelimits import WebSocketRateLimits

logger = logging.getLogger(__name__)


class WebSocketRateLimitMiddleware(BaseMiddleware):
    """
    Middleware that applies rate limiting to WebSocket connections.

    This middleware checks connection rate limits before allowing
    a WebSocket connection to proceed. If the rate limit is exceeded,
    the connection is rejected with close code 4029.

    Configuration:
        - RATELIMIT_DISABLE: Set to True to disable rate limiting
        - WEBSOCKET_RATE_LIMIT_OVERRIDES: Dict of rate limit overrides

    The middleware uses:
        - WS_CONNECT rate for authenticated users
        - WS_CONNECT_ANONYMOUS rate for anonymous users
    """

    async def __call__(
        self, scope: dict[str, Any], receive: Callable, send: Callable
    ) -> Any:
        """
        Check rate limit before allowing the connection.

        Args:
            scope: The ASGI scope dictionary
            receive: The receive callable
            send: The send callable

        Returns:
            The result of the inner application, or closes connection if rate limited
        """
        # Only apply to websocket connections
        if scope["type"] != "websocket":
            return await super().__call__(scope, receive, send)

        # Skip if rate limiting is disabled
        if getattr(settings, "RATELIMIT_DISABLE", False):
            return await super().__call__(scope, receive, send)

        # Get user from scope (set by auth middleware)
        user = scope.get("user")
        is_authenticated = (
            user
            and not isinstance(user, AnonymousUser)
            and hasattr(user, "is_authenticated")
            and user.is_authenticated
        )

        # Determine which rate limit to apply
        if is_authenticated:
            rate = WebSocketRateLimits.get_rate_for_user("WS_CONNECT", user)
        else:
            rate = WebSocketRateLimits.WS_CONNECT_ANONYMOUS

        # Check rate limit (synchronous check is fine for connection middleware)
        is_limited, info = check_rate_limit(scope, "ws_connect", rate, increment=True)

        if is_limited:
            # Log the rate limit hit
            client_ip = get_client_ip_from_scope(scope)
            user_id = getattr(user, "id", "anonymous") if user else "anonymous"

            logger.warning(
                f"WebSocket connection rate limited - "
                f"IP: {client_ip}, User: {user_id}, Rate: {rate}, "
                f"Path: {scope.get('path', 'unknown')}"
            )

            # Reject the connection
            await self._reject_connection(send, rate)
            return

        # Allow the connection to proceed
        return await super().__call__(scope, receive, send)

    async def _reject_connection(self, send: Callable, rate: str) -> None:
        """
        Reject the WebSocket connection due to rate limiting.

        Sends a close message with code 4029 (custom code for rate limiting).

        Args:
            send: The ASGI send callable
            rate: The rate limit that was exceeded (for logging)
        """
        # Send WebSocket close message
        # Code 4029 is a custom close code indicating rate limiting
        # (4000-4999 range is reserved for application use)
        try:
            count, period_seconds = parse_rate(rate)
            reason = f"Rate limit exceeded: {count}/{period_to_name(period_seconds)}"
        except (ValueError, TypeError):
            reason = "Rate limit exceeded"

        # For WebSocket, we need to accept then close, or just deny
        # Sending close without accept is the cleanest approach
        await send(
            {
                "type": "websocket.close",
                "code": 4029,
                "reason": reason[:123],  # Close reason max 123 bytes
            }
        )


def RateLimitMiddleware(inner):
    """
    Factory function to create rate limit middleware.

    This allows the middleware to be used in the same style as
    other Channels middleware:

        RateLimitMiddleware(URLRouter(...))

    Args:
        inner: The inner ASGI application to wrap

    Returns:
        WebSocketRateLimitMiddleware wrapping the inner application
    """
    return WebSocketRateLimitMiddleware(inner)
