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
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from config.websocket.middleware import WS_CLOSE_TOKEN_INVALID
from opencontractserver.llms.agents.core_agents import ContentEvent, FinalEvent
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

User = get_user_model()

logger = logging.getLogger(__name__)


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
        Verifies that providing a valid token results in successful connection
        and a logged-in user on the scope. Uses a mock agent to avoid LLM calls.
        """
        mock_for_document.return_value = _create_mock_agent()
        mock_for_corpus.return_value = _create_mock_agent()

        self.assertTrue(hasattr(self, "doc"), "A fixture Document must be available.")

        # Use unified agent-chat endpoint with document_id query param
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}&token={self.token}",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(
            connected,
            "WebSocket should connect successfully with a valid token.",
        )

        # Confirm that the scope user is authenticated
        scope_user = communicator.scope["user"]
        self.assertTrue(scope_user.is_authenticated, "User must be authenticated.")
        self.assertEqual(scope_user.username, self.user.username)

        # Send a test query to verify the connection works end-to-end
        await communicator.send_to(json.dumps({"query": "Please summarize the doc."}))

        # Gather messages until we encounter ASYNC_FINISH
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
        Verifies that providing an invalid token will lead to the connection being closed
        with code 4002 (WS_CLOSE_TOKEN_INVALID), signaling the client should re-authenticate.
        """
        self.assertTrue(hasattr(self, "doc"), "A fixture Document must be available.")

        # Use unified agent-chat endpoint with invalid token
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}&token=not_a_real_token",
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected, "Connection should fail with invalid token.")
        self.assertEqual(
            close_code,
            WS_CLOSE_TOKEN_INVALID,
            "WebSocket should reject the connection with 4002 for an invalid token.",
        )

    async def test_middleware_without_token(self) -> None:
        """
        Verifies that providing no token will lead to connection close with permission denied.

        When no token is provided, the user is anonymous. The unified consumer checks
        permissions and returns 4003 (permission denied) for anonymous users attempting
        to access private documents, which is the expected security behavior.
        """
        self.assertTrue(hasattr(self, "doc"), "A fixture Document must be available.")

        # Use unified agent-chat endpoint without token
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}",  # No token param
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected, "Connection should fail without token.")
        # 4003 = permission denied (anonymous can't access private document)
        self.assertEqual(
            close_code,
            4003,
            "WebSocket should reject anonymous access to private document with code 4003.",
        )
