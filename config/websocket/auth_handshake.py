"""
AuthHandshakeMixin — adds in-band token-refresh and re-validation behavior to
any AsyncWebsocketConsumer.

Wire protocol (frames in addition to whatever the consumer already speaks):

  Client -> Server:
    {"type": "AUTH", "token": "<jwt>"}

  Server -> Client:
    {"type": "AUTH_OK", "user_id": int|null, "username": str|null,
     "anonymous": bool, "refreshed": bool}
    {"type": "AUTH_FAILED", "reason":
        "EXPIRED" | "INVALID" | "USER_MISMATCH" | "PERMISSION_REVOKED"}
    {"type": "AUTH_REFRESH_REQUIRED", "grace_seconds": float}

Security guarantees enforced by handle_auth_message():
  1. A live socket bound to user A cannot be re-bound to user B (USER_MISMATCH).
  2. If the user has lost access to a bound resource since connect, the next
     AUTH frame closes 4003 (PERMISSION_REVOKED).
  3. An expired/invalid AUTH frame closes the socket (4001/4002) and never
     leaves the consumer in an inconsistent state.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from graphql_jwt.exceptions import JSONWebTokenError, JSONWebTokenExpired

from config.jwt_utils import get_user_from_jwt_token
from config.websocket.middleware import (
    WS_CLOSE_PERMISSION_DENIED,
    WS_CLOSE_TOKEN_EXPIRED,
    WS_CLOSE_TOKEN_INVALID,
)
from opencontractserver.constants.auth import WS_AUTH_REFRESH_GRACE_SECONDS

logger = logging.getLogger(__name__)

# Minimum interval between accepted AUTH frames on a single connection.
# Auth0 silent renewal happens on the order of every 50 minutes, so a 1-second
# floor cannot interfere with legitimate refreshes but stops a malicious client
# from spamming AUTH frames to burn DB queries (issue raised in PR #1502 review).
_MIN_AUTH_FRAME_INTERVAL_SEC = 1.0


@database_sync_to_async
def _get_user_from_token(token: str):
    return get_user_from_jwt_token(token)


class AuthHandshakeMixin:
    """
    Mix this into an AsyncWebsocketConsumer to opt into in-band auth refresh.

    Consumers using this mixin should:
      1. Replace ``await self.accept()`` with ``await self.accept_with_auth()``.
      2. In ``receive()``, dispatch frames whose top-level "type" == "AUTH" to
         ``await self.handle_auth_message(payload)`` BEFORE any other handling.
      3. Optionally override ``_validate_resource_permissions(user)`` to re-run
         resource-level access checks on refresh; default is permissive.
      4. Optionally call ``await self.request_token_refresh()`` from streaming
         code that catches a JSONWebTokenExpired mid-flight.
    """

    # Populated by accept_with_auth() and updated by handle_auth_message().
    _refresh_grace_task: asyncio.Task | None = None
    _initial_auth_sent: bool = False
    # Tracks whether the handshake has accepted but not yet been cleaned up.
    # The grace-timer guard uses this to avoid calling close() on a socket
    # that has already been disconnected through other paths.
    _handshake_connected: bool = False
    # Monotonic timestamp of the last AUTH frame we accepted; used to throttle
    # spam at the per-connection level before any DB work runs.
    _last_auth_frame_at: float = 0.0

    @property
    def current_user(self):
        return self.scope.get("user")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    #  Connection accept
    # ------------------------------------------------------------------ #

    async def accept_with_auth(self) -> None:
        """Accept the connection echoing the negotiated subprotocol."""
        subprotocol = self.scope.get("accepted_subprotocol")  # type: ignore[attr-defined]
        await self.accept(subprotocol=subprotocol)  # type: ignore[attr-defined]
        self._handshake_connected = True
        await self._send_initial_auth_ok()

    async def _send_initial_auth_ok(self) -> None:
        if self._initial_auth_sent:
            return
        user = self.current_user
        is_anon = (
            isinstance(user, AnonymousUser)
            or user is None
            or not getattr(user, "is_authenticated", False)
        )
        await self.send(  # type: ignore[attr-defined]
            text_data=json.dumps(
                {
                    "type": "AUTH_OK",
                    "user_id": None if is_anon else user.pk,
                    "username": None if is_anon else user.username,
                    "anonymous": is_anon,
                    "refreshed": False,
                }
            )
        )
        self._initial_auth_sent = True

    # ------------------------------------------------------------------ #
    #  Refresh: client-driven
    # ------------------------------------------------------------------ #

    async def handle_auth_message(self, payload: dict[str, Any]) -> None:
        """
        Process a ``{"type":"AUTH","token":...}`` frame from the client.

        Validates the token, refuses user-pk swap, re-validates resource
        permissions, swaps scope["user"] on success, and cancels any pending
        server-nudge grace timer.

        Enforces a per-connection cooldown so a malicious client cannot spam
        AUTH frames to burn DB queries on token validation + permission checks.
        Frames arriving inside the cooldown window are silently dropped without
        touching the database.
        """
        now = time.monotonic()
        if now - self._last_auth_frame_at < _MIN_AUTH_FRAME_INTERVAL_SEC:
            logger.debug("Dropping AUTH frame: per-connection cooldown active")
            return
        self._last_auth_frame_at = now

        token = payload.get("token")
        if not token or not isinstance(token, str):
            await self._fail_auth("INVALID", WS_CLOSE_TOKEN_INVALID)
            return

        try:
            new_user = await _get_user_from_token(token)
        except JSONWebTokenExpired:
            await self._fail_auth("EXPIRED", WS_CLOSE_TOKEN_EXPIRED)
            return
        except JSONWebTokenError:
            await self._fail_auth("INVALID", WS_CLOSE_TOKEN_INVALID)
            return
        except Exception:
            logger.exception("Unexpected error validating refresh token")
            await self._fail_auth("INVALID", WS_CLOSE_TOKEN_INVALID)
            return

        # User-pk swap is forbidden — defense in depth.
        current = self.current_user
        current_is_anon = (
            isinstance(current, AnonymousUser)
            or current is None
            or not getattr(current, "is_authenticated", False)
        )
        if not current_is_anon and current.pk != new_user.pk:
            await self._fail_auth("USER_MISMATCH", WS_CLOSE_TOKEN_INVALID)
            return

        # Re-validate resource permissions. Treat any unexpected error
        # (DB timeout, stale FK lookup, etc.) as a permission denial so
        # the consumer is never left in a half-swapped state — better to
        # close the socket and let the client reconnect than to keep
        # serving a connection whose authorization we can't confirm.
        try:
            permitted = await self._validate_resource_permissions(new_user)
        except Exception:
            logger.exception(
                "Unexpected error in _validate_resource_permissions during "
                "AUTH refresh; treating as PERMISSION_REVOKED"
            )
            permitted = False
        if not permitted:
            await self._fail_auth("PERMISSION_REVOKED", WS_CLOSE_PERMISSION_DENIED)
            return

        # Success — swap, ack, cancel any pending grace timer.
        self.scope["user"] = new_user  # type: ignore[attr-defined]
        self._cancel_refresh_grace_timer()
        await self.send(  # type: ignore[attr-defined]
            text_data=json.dumps(
                {
                    "type": "AUTH_OK",
                    "user_id": new_user.pk,
                    "username": new_user.username,
                    "anonymous": False,
                    "refreshed": True,
                }
            )
        )

    async def _validate_resource_permissions(self, user) -> bool:
        """
        Override in consumers that have resource-level access requirements
        (e.g., document/corpus/conversation membership). Default permits.
        """
        return True

    async def _fail_auth(self, reason: str, close_code: int) -> None:
        try:
            await self.send(  # type: ignore[attr-defined]
                text_data=json.dumps(
                    {
                        "type": "AUTH_FAILED",
                        "reason": reason,
                    }
                )
            )
        except Exception:
            pass
        await self.close(code=close_code)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    #  Refresh: server-nudged
    # ------------------------------------------------------------------ #

    async def request_token_refresh(
        self, grace_seconds: float = WS_AUTH_REFRESH_GRACE_SECONDS
    ) -> None:
        """
        Ask the client to send a fresh token. If the client doesn't respond
        with a successful AUTH frame within ``grace_seconds``, close 4001.
        """
        await self.send(  # type: ignore[attr-defined]
            text_data=json.dumps(
                {
                    "type": "AUTH_REFRESH_REQUIRED",
                    "grace_seconds": grace_seconds,
                }
            )
        )
        self._cancel_refresh_grace_timer()
        self._refresh_grace_task = asyncio.create_task(
            self._refresh_grace_timeout(grace_seconds)
        )

    async def _refresh_grace_timeout(self, grace_seconds: float) -> None:
        try:
            await asyncio.sleep(grace_seconds)
        except asyncio.CancelledError:
            return
        if self._handshake_connected:
            logger.info("Refresh grace timer expired; closing 4001")
            await self.close(code=WS_CLOSE_TOKEN_EXPIRED)  # type: ignore[attr-defined]

    def _cancel_refresh_grace_timer(self) -> None:
        task = self._refresh_grace_task
        if task is not None and not task.done():
            task.cancel()
        self._refresh_grace_task = None

    # ------------------------------------------------------------------ #
    #  Cleanup
    # ------------------------------------------------------------------ #

    async def cleanup_auth_handshake(self) -> None:
        """Consumers should call this from their ``disconnect()``."""
        self._handshake_connected = False
        self._cancel_refresh_grace_timer()
