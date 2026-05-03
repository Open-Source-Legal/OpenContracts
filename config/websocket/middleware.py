"""
WebSocket JWT authentication middleware (subprotocol transport).

Tokens are read ONLY from the Sec-WebSocket-Protocol handshake header. The
historical query-string and Authorization-header paths have been removed
because the URL is logged in too many places (nginx, browser history,
Sentry, CDN) and browsers cannot set custom headers on WS connections.

Subprotocol format (negotiated by the JS WebSocket constructor):
    new WebSocket(url, ["opencontracts.jwt.v1", "<jwt>"])

The server MUST echo a selected subprotocol or browsers fail the handshake.
We always echo "opencontracts.jwt.v1" when the marker is present, even on
auth failure, so the consumer can close the socket cleanly with the right
4xxx code instead of failing at the transport layer.
"""

import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from graphql_jwt.exceptions import JSONWebTokenError, JSONWebTokenExpired

from config.jwt_utils import get_user_from_jwt_token

logger = logging.getLogger(__name__)

# Subprotocol marker the client sends and the server echoes.
# Versioned so we can roll a v2 protocol without breaking existing clients.
WS_AUTH_SUBPROTOCOL = "opencontracts.jwt.v1"

# WebSocket close codes (1000-1015 reserved; 4000-4999 application).
WS_CLOSE_UNAUTHENTICATED = 4000
WS_CLOSE_TOKEN_EXPIRED = 4001
WS_CLOSE_TOKEN_INVALID = 4002
WS_CLOSE_RATE_LIMITED = 4029


@database_sync_to_async
def _get_user_from_token(token: str):
    """Async wrapper around the unified JWT validator."""
    return get_user_from_jwt_token(token)


def _parse_subprotocol_token(
    headers: list[tuple[bytes, bytes]],
) -> tuple[bool, str | None]:
    """
    Parse the Sec-WebSocket-Protocol header.

    Returns (marker_present, token_or_None). Marker presence determines whether
    we echo the subprotocol back; token presence determines whether we attempt
    auth at all.
    """
    raw: bytes | None = None
    for name, value in headers:
        if name.lower() == b"sec-websocket-protocol":
            raw = value
            break
    if raw is None:
        return (False, None)

    parts = [
        p.strip() for p in raw.decode("utf-8", errors="ignore").split(",") if p.strip()
    ]
    if WS_AUTH_SUBPROTOCOL not in parts:
        return (False, None)

    # Token is any non-marker, non-empty entry. Take the first.
    for p in parts:
        if p != WS_AUTH_SUBPROTOCOL:
            return (True, p)
    return (True, None)


class JWTAuthMiddleware(BaseMiddleware):
    """
    Channels middleware that authenticates WS connections via JWT carried on
    the Sec-WebSocket-Protocol header.

    On success: scope["user"] = User, scope["accepted_subprotocol"] = marker.
    On no/invalid/expired token: scope["user"] = AnonymousUser, with
    scope["auth_error"] populated for the consumer to act on.
    """

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        scope["user"] = AnonymousUser()
        scope["auth_error"] = None
        scope["accepted_subprotocol"] = None

        marker_present, token = _parse_subprotocol_token(scope.get("headers", []))

        if marker_present:
            scope["accepted_subprotocol"] = WS_AUTH_SUBPROTOCOL

        if not token:
            return await super().__call__(scope, receive, send)

        try:
            user = await _get_user_from_token(token)
            scope["user"] = user
            logger.debug(f"WS handshake authenticated user={user.username}")
        except JSONWebTokenExpired as e:
            logger.warning(f"WS handshake auth failed - token expired: {e}")
            scope["auth_error"] = {
                "code": WS_CLOSE_TOKEN_EXPIRED,
                "message": "Token has expired. Please refresh your session.",
            }
        except JSONWebTokenError as e:
            logger.warning(f"WS handshake auth failed - invalid token: {e}")
            scope["auth_error"] = {
                "code": WS_CLOSE_TOKEN_INVALID,
                "message": f"Invalid token: {e}",
            }
        except Exception as e:
            logger.error(f"WS handshake auth error: {e}", exc_info=True)
            scope["auth_error"] = {
                "code": WS_CLOSE_TOKEN_INVALID,
                "message": "Authentication error occurred.",
            }

        return await super().__call__(scope, receive, send)


# Backwards-compat alias kept until consumers stop importing it.
GraphQLJWTTokenAuthMiddleware = JWTAuthMiddleware
