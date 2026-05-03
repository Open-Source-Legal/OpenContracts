"""
WebSocket JWT authentication middleware.

Uses the unified jwt_utils module for token validation, ensuring consistent
authentication behavior across REST, GraphQL, and WebSocket API surfaces.

Automatically handles both Auth0 and standard graphql_jwt tokens based on
the USE_AUTH0 setting.
"""

import logging
from typing import Any
from urllib.parse import parse_qsl

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from graphql_jwt.exceptions import JSONWebTokenError, JSONWebTokenExpired

from config.jwt_utils import get_user_from_jwt_token

logger = logging.getLogger(__name__)

# WebSocket close codes for authentication errors
# Standard codes 1000-1015 are reserved; 4000-4999 are for application use
WS_CLOSE_UNAUTHENTICATED = 4000  # No token or generic auth failure
WS_CLOSE_TOKEN_EXPIRED = 4001  # Token has expired, client should refresh
WS_CLOSE_TOKEN_INVALID = 4002  # Token is invalid, client should re-authenticate
WS_CLOSE_RATE_LIMITED = 4029  # Connection rejected due to rate limiting


@database_sync_to_async
def _get_user_from_token(token: str):
    """
    Async wrapper around the unified JWT validation function.

    Returns the user or raises JWT exceptions.
    """
    return get_user_from_jwt_token(token)


class JWTAuthMiddleware(BaseMiddleware):
    """
    WebSocket middleware that authenticates users via JWT tokens.

    Supports both Auth0 and standard graphql_jwt tokens based on
    the USE_AUTH0 setting. Uses the same validation logic as the
    REST API and GraphQL layers.

    Token extraction:
        - Authorization header: Authorization: Bearer <jwt> (preferred)
        - Query string: ws://host/path/?token=<jwt> (browser fallback;
          browsers can't set headers on the WebSocket upgrade so the
          query string is unavoidable for direct ``new WebSocket(...)``
          callers — be aware tokens passed this way are visible to any
          proxy or access log on the path).

    On authentication failure, sets scope['auth_error'] with details:
    - 'code': WS_CLOSE_TOKEN_EXPIRED (4001) or WS_CLOSE_TOKEN_INVALID (4002)
    - 'message': Human-readable error message

    Consumers can check scope['auth_error'] and close the connection with
    the appropriate code to signal the client to refresh or re-authenticate.
    """

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        """
        Extract token from query string or headers and authenticate user.
        """
        # Initialize with AnonymousUser and no auth error
        scope["user"] = AnonymousUser()
        scope["auth_error"] = None

        # Extract token from query string
        token = self._extract_token_from_query_string(scope)

        # Fall back to Authorization header if no query string token
        if not token:
            token = self._extract_token_from_headers(scope)

        if not token:
            logger.debug("No token provided in WebSocket connection")
            return await super().__call__(scope, receive, send)

        # Authenticate with the token
        try:
            logger.debug("Attempting WebSocket JWT authentication")
            user = await _get_user_from_token(token)
            scope["user"] = user
            logger.debug(f"WebSocket authenticated user: {user.username}")

        except JSONWebTokenExpired as e:
            logger.warning(f"WebSocket auth failed - token expired: {e}")
            scope["auth_error"] = {
                "code": WS_CLOSE_TOKEN_EXPIRED,
                "message": "Token has expired. Please refresh your session.",
            }

        except JSONWebTokenError as e:
            logger.warning(f"WebSocket auth failed - invalid token: {e}")
            scope["auth_error"] = {
                "code": WS_CLOSE_TOKEN_INVALID,
                "message": f"Invalid token: {e}",
            }

        except Exception as e:
            logger.error(f"WebSocket auth error: {e}", exc_info=True)
            scope["auth_error"] = {
                "code": WS_CLOSE_TOKEN_INVALID,
                "message": "Authentication error occurred.",
            }

        return await super().__call__(scope, receive, send)

    def _extract_token_from_query_string(self, scope: dict[str, Any]) -> str | None:
        """Extract token from WebSocket query string."""
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = dict(parse_qsl(query_string))
        return query_params.get("token")

    def _extract_token_from_headers(self, scope: dict[str, Any]) -> str | None:
        """Extract token from Authorization header."""
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8")

        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2:
            return None

        if parts[0].upper() not in ("JWT", "BEARER"):
            return None

        return parts[1]
