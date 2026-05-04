"""
Tests for GraphQLJWTTokenAuthMiddleware to ensure that it correctly validates the received token
and assigns the correct user (or AnonymousUser) to the WebSocket scope.

These tests verify JWT token validation in the WebSocket middleware without exercising
the full LLM agent functionality. The unified consumer's agent initialization is mocked
to isolate the authentication behavior.
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from graphql_jwt.shortcuts import get_token

from config.websocket.auth_handshake import AuthHandshakeMixin
from config.websocket.middleware import (
    WS_AUTH_SUBPROTOCOL,
    WS_CLOSE_TOKEN_EXPIRED,
    WS_CLOSE_TOKEN_INVALID,
    JWTAuthMiddleware,
)
from opencontractserver.llms.agents.core_agents import ContentEvent, FinalEvent
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

User = get_user_model()

logger = logging.getLogger(__name__)


@pytest.mark.serial
class JWTAuthMiddlewareSubprotocolTests(WebsocketFixtureBaseTestCase):
    """Unit tests for JWTAuthMiddleware - subprotocol-only transport."""

    async def _run_middleware(self, headers: list[tuple[bytes, bytes]]) -> dict:
        """Run middleware against a synthetic scope; return the modified scope."""
        scope: dict = {
            "type": "websocket",
            "path": "/ws/test/",
            "headers": headers,
            "query_string": b"",
        }
        inner = AsyncMock()
        middleware = JWTAuthMiddleware(inner)
        await middleware(scope, AsyncMock(), AsyncMock())
        return scope

    async def test_no_subprotocol_header_yields_anonymous(self):
        scope = await self._run_middleware(headers=[])
        self.assertIsInstance(scope["user"], AnonymousUser)
        self.assertIsNone(scope["auth_error"])
        self.assertIsNone(scope.get("accepted_subprotocol"))

    async def test_subprotocol_marker_only_yields_anonymous(self):
        headers = [(b"sec-websocket-protocol", WS_AUTH_SUBPROTOCOL.encode())]
        scope = await self._run_middleware(headers=headers)
        self.assertIsInstance(scope["user"], AnonymousUser)
        self.assertIsNone(scope["auth_error"])
        self.assertEqual(scope["accepted_subprotocol"], WS_AUTH_SUBPROTOCOL)

    async def test_subprotocol_with_valid_token_authenticates(self):
        token = await database_sync_to_async(get_token)(self.user)
        proto_value = f"{WS_AUTH_SUBPROTOCOL}, {token}".encode()
        headers = [(b"sec-websocket-protocol", proto_value)]
        scope = await self._run_middleware(headers=headers)
        self.assertEqual(scope["user"].username, self.user.username)
        self.assertIsNone(scope["auth_error"])
        self.assertEqual(scope["accepted_subprotocol"], WS_AUTH_SUBPROTOCOL)

    async def test_subprotocol_with_invalid_token_sets_auth_error_4002(self):
        proto_value = f"{WS_AUTH_SUBPROTOCOL}, garbage_token".encode()
        headers = [(b"sec-websocket-protocol", proto_value)]
        scope = await self._run_middleware(headers=headers)
        self.assertIsInstance(scope["user"], AnonymousUser)
        self.assertIsNotNone(scope["auth_error"])
        self.assertEqual(scope["auth_error"]["code"], WS_CLOSE_TOKEN_INVALID)
        # Subprotocol should still be echoed (so the browser handshake succeeds
        # at the transport layer) — the consumer is responsible for closing.
        self.assertEqual(scope["accepted_subprotocol"], WS_AUTH_SUBPROTOCOL)

    async def test_query_string_token_is_ignored(self):
        """Hard-cutover regression: ?token= must not authenticate."""
        token = await database_sync_to_async(get_token)(self.user)
        scope: dict = {
            "type": "websocket",
            "path": "/ws/test/",
            "headers": [],
            "query_string": f"token={token}".encode(),
        }
        inner = AsyncMock()
        await JWTAuthMiddleware(inner)(scope, AsyncMock(), AsyncMock())
        self.assertIsInstance(scope["user"], AnonymousUser)
        self.assertIsNone(scope["auth_error"])

    async def test_authorization_header_is_ignored(self):
        """Hard-cutover regression: Authorization header must not authenticate."""
        token = await database_sync_to_async(get_token)(self.user)
        headers = [(b"authorization", f"Bearer {token}".encode())]
        scope = await self._run_middleware(headers=headers)
        self.assertIsInstance(scope["user"], AnonymousUser)
        self.assertIsNone(scope["auth_error"])


def _create_mock_agent() -> MagicMock:
    """Create a mock agent that streams a simple response."""

    async def mock_stream(query: str) -> AsyncGenerator[Any, None]:
        """Yield minimal events to satisfy the consumer's stream handling."""
        yield ContentEvent(content="Mock response to: " + query[:20])
        yield FinalEvent()

    agent = MagicMock()
    agent.stream = mock_stream
    agent.chat = AsyncMock(return_value=MagicMock(content="Mock response"))
    agent.get_conversation_id = MagicMock(return_value=None)
    # Prevent MagicMock auto-attribute from making context_exhausted truthy
    mock_conv_mgr = MagicMock()
    mock_conv_mgr.context_exhausted = False
    agent.conversation_manager = mock_conv_mgr
    return agent


@pytest.mark.serial
class GraphQLJWTTokenAuthMiddlewareTestCase(WebsocketFixtureBaseTestCase):
    """
    Test class illustrating how GraphQLJWTTokenAuthMiddleware is tested in a WebSocket context.
    Uses the WebsocketFixtureBaseTestCase to provide test data and token handling.

    Marked as serial because websocket tests use async event loops that
    can conflict with pytest-xdist workers.
    """

    @mock.patch(
        "config.websocket.consumers.unified_agent_conversation.agents.for_corpus"
    )
    @mock.patch(
        "config.websocket.consumers.unified_agent_conversation.agents.for_document"
    )
    async def test_middleware_with_valid_token(
        self, mock_for_document: AsyncMock, mock_for_corpus: AsyncMock
    ) -> None:
        """
        Verifies that providing a valid token via subprotocol results in successful
        connection and a logged-in user on the scope.  Uses a mock agent to avoid
        LLM calls.  The consumer now emits an initial AUTH_OK frame on connect which
        must be drained before sending the query.
        """
        mock_for_document.return_value = _create_mock_agent()
        mock_for_corpus.return_value = _create_mock_agent()

        self.assertTrue(hasattr(self, "doc"), "A fixture Document must be available.")

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, accepted_protocol = await communicator.connect()
        self.assertTrue(
            connected, "WebSocket should connect successfully with a valid token."
        )
        self.assertEqual(accepted_protocol, WS_AUTH_SUBPROTOCOL)

        # Drain initial AUTH_OK frame from the mixin
        raw = await communicator.receive_from(timeout=5)
        msg = json.loads(raw)
        self.assertEqual(msg["type"], "AUTH_OK")
        self.assertEqual(msg["username"], self.user.username)
        self.assertFalse(msg["anonymous"])
        self.assertFalse(msg["refreshed"])

        # Confirm scope user is authenticated
        scope_user = communicator.scope["user"]
        self.assertTrue(scope_user.is_authenticated)
        self.assertEqual(scope_user.username, self.user.username)

        await communicator.send_to(json.dumps({"query": "Please summarize the doc."}))

        messages: list[dict[str, Any]] = []
        while True:
            try:
                raw_message = await communicator.receive_from(timeout=10)
                msg_json = json.loads(raw_message)
                messages.append(msg_json)
                if msg_json.get("type") == "ASYNC_FINISH":
                    break
            except Exception:
                break

        self.assertTrue(
            len(messages) > 0, "Should receive messages from the agent query."
        )
        await communicator.disconnect()

    async def test_middleware_with_invalid_token(self) -> None:
        """
        Verifies that providing an invalid token via subprotocol closes with 4002.
        """
        self.assertTrue(hasattr(self, "doc"), "A fixture Document must be available.")
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}",
            subprotocols=[WS_AUTH_SUBPROTOCOL, "not_a_real_token"],
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected, "Connection should fail with invalid token.")
        self.assertEqual(close_code, WS_CLOSE_TOKEN_INVALID)

    async def test_middleware_without_token(self) -> None:
        """
        Verifies that an anonymous connection (marker-only subprotocol) to a
        private document is rejected with 4003 (permission denied).
        """
        self.assertTrue(hasattr(self, "doc"), "A fixture Document must be available.")
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}",
            subprotocols=[WS_AUTH_SUBPROTOCOL],
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected, "Connection should fail without token.")
        self.assertEqual(close_code, 4003)


# ---------------------------------------------------------------------------
# AuthHandshakeMixin tests
# ---------------------------------------------------------------------------


class _DummyConsumer(AuthHandshakeMixin):
    """Bare consumer instance used to exercise the mixin in isolation."""

    def __init__(self, scope: dict):
        self.scope = scope
        self.sent: list[str] = []
        self.closed_with: int | None = None
        # Simulate an already-accepted connection so the mixin's grace-timer
        # close path runs without us having to drive accept_with_auth() in
        # every test.
        self._handshake_connected = True

    async def send(self, text_data: str) -> None:
        self.sent.append(text_data)

    async def close(self, code: int | None = None) -> None:
        self.closed_with = code
        self._handshake_connected = False

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accepted_subprotocol = subprotocol

    async def _validate_resource_permissions(self, user) -> bool:
        return True


@pytest.mark.serial
class AuthHandshakeMixinTests(WebsocketFixtureBaseTestCase):
    """Tests for AuthHandshakeMixin behavior in isolation."""

    async def _make_consumer(self, user) -> _DummyConsumer:
        return _DummyConsumer(
            scope={
                "user": user,
                "accepted_subprotocol": WS_AUTH_SUBPROTOCOL,
                "auth_error": None,
            }
        )

    async def test_accept_with_auth_echoes_subprotocol(self):
        c = await self._make_consumer(self.user)
        await c.accept_with_auth()
        self.assertEqual(c.accepted_subprotocol, WS_AUTH_SUBPROTOCOL)

    async def test_handle_auth_valid_same_user_sends_AUTH_OK(self):
        token = await database_sync_to_async(get_token)(self.user)
        c = await self._make_consumer(self.user)
        await c.handle_auth_message({"type": "AUTH", "token": token})
        self.assertIsNone(c.closed_with)
        self.assertTrue(any('"AUTH_OK"' in s for s in c.sent))

    async def test_handle_auth_user_mismatch_closes_4002(self):
        # Build a token for a *different* user
        other_user = await database_sync_to_async(User.objects.create_user)(
            username="other", password="x"
        )
        other_token = await database_sync_to_async(get_token)(other_user)
        c = await self._make_consumer(self.user)
        await c.handle_auth_message({"type": "AUTH", "token": other_token})
        self.assertEqual(c.closed_with, WS_CLOSE_TOKEN_INVALID)
        self.assertTrue(any('"USER_MISMATCH"' in s for s in c.sent))

    async def test_handle_auth_invalid_token_closes_4002(self):
        c = await self._make_consumer(self.user)
        await c.handle_auth_message({"type": "AUTH", "token": "garbage"})
        self.assertEqual(c.closed_with, WS_CLOSE_TOKEN_INVALID)
        self.assertTrue(any('"INVALID"' in s for s in c.sent))

    async def test_handle_auth_missing_token_field_closes_4002(self):
        c = await self._make_consumer(self.user)
        await c.handle_auth_message({"type": "AUTH"})
        self.assertEqual(c.closed_with, WS_CLOSE_TOKEN_INVALID)

    async def test_handle_auth_resource_permission_revoked_closes_4003(self):
        token = await database_sync_to_async(get_token)(self.user)
        c = await self._make_consumer(self.user)
        # Override permission check to deny
        c._validate_resource_permissions = AsyncMock(return_value=False)  # type: ignore[method-assign]
        await c.handle_auth_message({"type": "AUTH", "token": token})
        self.assertEqual(c.closed_with, 4003)
        self.assertTrue(any('"PERMISSION_REVOKED"' in s for s in c.sent))

    async def test_handle_auth_resource_permission_exception_closes_4003(self):
        """Unexpected errors in the override (e.g. DB timeout) must NOT
        leave the consumer in a half-swapped state — they should fail
        closed as PERMISSION_REVOKED, same as an explicit deny.
        """
        token = await database_sync_to_async(get_token)(self.user)
        c = await self._make_consumer(self.user)
        c._validate_resource_permissions = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("simulated DB timeout")
        )
        await c.handle_auth_message({"type": "AUTH", "token": token})
        self.assertEqual(c.closed_with, 4003)
        self.assertTrue(any('"PERMISSION_REVOKED"' in s for s in c.sent))

    async def test_nudge_refresh_emits_AUTH_REFRESH_REQUIRED(self):
        c = await self._make_consumer(self.user)
        await c.request_token_refresh(grace_seconds=1)
        self.assertTrue(any('"AUTH_REFRESH_REQUIRED"' in s for s in c.sent))

    async def test_nudge_refresh_grace_timer_closes_4001_on_timeout(self):
        c = await self._make_consumer(self.user)
        await c.request_token_refresh(grace_seconds=0.05)
        # Wait for grace timer to fire
        import asyncio

        await asyncio.sleep(0.2)
        self.assertEqual(c.closed_with, WS_CLOSE_TOKEN_EXPIRED)

    async def test_nudge_refresh_cancelled_by_auth_message(self):
        token = await database_sync_to_async(get_token)(self.user)
        c = await self._make_consumer(self.user)
        await c.request_token_refresh(grace_seconds=10)
        await c.handle_auth_message({"type": "AUTH", "token": token})
        # Timer cancelled — even after waiting, no close
        import asyncio

        await asyncio.sleep(0.1)
        self.assertIsNone(c.closed_with)


# ---------------------------------------------------------------------------
# End-to-end handshake / refresh tests on UnifiedAgentConsumer
# ---------------------------------------------------------------------------


@pytest.mark.serial
class UnifiedAgentHandshakeTests(WebsocketFixtureBaseTestCase):
    """End-to-end handshake/refresh tests on UnifiedAgentConsumer."""

    @mock.patch(
        "config.websocket.consumers.unified_agent_conversation.agents.for_document"
    )
    async def test_inband_refresh_succeeds_no_reconnect(self, mock_for_document):
        mock_for_document.return_value = _create_mock_agent()
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        # Drain initial AUTH_OK
        raw = await communicator.receive_from(timeout=5)
        self.assertEqual(json.loads(raw)["type"], "AUTH_OK")

        # Send AUTH refresh with same-user token
        new_token = await database_sync_to_async(get_token)(self.user)
        await communicator.send_to(json.dumps({"type": "AUTH", "token": new_token}))
        raw = await communicator.receive_from(timeout=5)
        msg = json.loads(raw)
        self.assertEqual(msg["type"], "AUTH_OK")
        self.assertTrue(msg["refreshed"])
        await communicator.disconnect()

    async def test_inband_refresh_user_mismatch_closes_4002(self):
        other_user = await database_sync_to_async(User.objects.create_user)(
            username="other_handshake", password="x"
        )
        other_token = await database_sync_to_async(get_token)(other_user)

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_from(timeout=5)  # drain AUTH_OK

        await communicator.send_to(json.dumps({"type": "AUTH", "token": other_token}))
        raw = await communicator.receive_from(timeout=5)
        self.assertIn('"USER_MISMATCH"', raw)
        # Wait for close
        await communicator.disconnect()


# ---------------------------------------------------------------------------
# ThreadUpdatesConsumer handshake tests
# ---------------------------------------------------------------------------


@pytest.mark.serial
class ThreadUpdatesHandshakeTests(WebsocketFixtureBaseTestCase):
    async def _make_conversation(self):
        from opencontractserver.conversations.models import Conversation

        return await database_sync_to_async(Conversation.objects.create)(
            creator=self.user,
            chat_with_corpus=self.corpus,
            title="Test",
        )

    async def test_handshake_valid_token_authenticates(self):
        convo = await self._make_conversation()
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/thread-updates/?conversation_id={convo.pk}",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        raw = await communicator.receive_from(timeout=5)
        self.assertIn('"AUTH_OK"', raw)
        await communicator.disconnect()

    async def test_handshake_no_token_closes_4000(self):
        convo = await self._make_conversation()
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/thread-updates/?conversation_id={convo.pk}",
            subprotocols=[WS_AUTH_SUBPROTOCOL],
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4000)

    async def test_inband_refresh_succeeds(self):
        convo = await self._make_conversation()
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/thread-updates/?conversation_id={convo.pk}",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        # Drain initial AUTH_OK + CONNECTED frames
        await communicator.receive_from(timeout=5)
        await communicator.receive_from(timeout=5)

        new_token = await database_sync_to_async(get_token)(self.user)
        await communicator.send_to(json.dumps({"type": "AUTH", "token": new_token}))
        raw = await communicator.receive_from(timeout=5)
        msg = json.loads(raw)
        self.assertEqual(msg["type"], "AUTH_OK")
        self.assertTrue(msg["refreshed"])
        await communicator.disconnect()


# ---------------------------------------------------------------------------
# NotificationUpdatesConsumer handshake tests
# ---------------------------------------------------------------------------


@pytest.mark.serial
class NotificationUpdatesHandshakeTests(WebsocketFixtureBaseTestCase):
    async def test_handshake_valid_token_emits_AUTH_OK_then_CONNECTED(self):
        communicator = WebsocketCommunicator(
            self.application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        raw1 = await communicator.receive_from(timeout=5)
        raw2 = await communicator.receive_from(timeout=5)
        types = {json.loads(r)["type"] for r in (raw1, raw2)}
        self.assertEqual(types, {"AUTH_OK", "CONNECTED"})
        await communicator.disconnect()

    async def test_handshake_no_token_closes_4000(self):
        communicator = WebsocketCommunicator(
            self.application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL],
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        # NotificationUpdatesConsumer.connect() closes 4000 (UNAUTHENTICATED)
        # when there is no token at all. 4001 (TOKEN_EXPIRED) is reserved for
        # the case where the middleware decoded a token and found it stale —
        # using 4001 for "no token sent" caused the frontend hook to treat
        # every anonymous-mount as "session expired" and stop reconnecting.
        self.assertEqual(close_code, 4000)

    async def test_inband_refresh_succeeds(self):
        communicator = WebsocketCommunicator(
            self.application,
            "ws/notification-updates/",
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        # Drain initial AUTH_OK + CONNECTED
        await communicator.receive_from(timeout=5)
        await communicator.receive_from(timeout=5)

        new_token = await database_sync_to_async(get_token)(self.user)
        await communicator.send_to(json.dumps({"type": "AUTH", "token": new_token}))
        raw = await communicator.receive_from(timeout=5)
        msg = json.loads(raw)
        self.assertEqual(msg["type"], "AUTH_OK")
        self.assertTrue(msg["refreshed"])
        await communicator.disconnect()
