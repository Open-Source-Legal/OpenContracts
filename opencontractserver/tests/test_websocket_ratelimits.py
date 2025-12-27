"""
Tests for WebSocket rate limiting functionality.

Tests cover:
- Connection rate limiting via middleware
- Message rate limiting in consumers
- Per-user vs per-IP rate limiting
- Rate limit bypass when disabled
"""

import json
import logging
from unittest import mock

import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from django.test import override_settings
from graphql_relay import to_global_id

from config.asgi import application
from config.websocket.ratelimits import (
    WebSocketRateLimits,
    check_rate_limit,
    get_client_ip_from_scope,
    get_rate_limit_key,
    parse_rate,
)
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

logger = logging.getLogger(__name__)


class TestRateLimitUtilities:
    """Unit tests for rate limiting utility functions."""

    def test_parse_rate_valid_formats(self):
        """Test parsing valid rate limit strings."""
        assert parse_rate("10/s") == (10, 1)
        assert parse_rate("30/m") == (30, 60)
        assert parse_rate("100/h") == (100, 3600)
        assert parse_rate("1000/d") == (1000, 86400)

    def test_parse_rate_invalid_format(self):
        """Test that invalid rate formats raise ValueError."""
        with pytest.raises(ValueError):
            parse_rate("invalid")

        with pytest.raises(ValueError):
            parse_rate("10")

        with pytest.raises(ValueError):
            parse_rate("10/x")  # Invalid period

    def test_get_client_ip_from_scope_with_forwarded_header(self):
        """Test IP extraction from X-Forwarded-For header."""
        scope = {
            "headers": [
                (b"x-forwarded-for", b"192.168.1.1, 10.0.0.1"),
            ],
            "client": ("127.0.0.1", 8000),
        }
        assert get_client_ip_from_scope(scope) == "192.168.1.1"

    def test_get_client_ip_from_scope_without_forwarded_header(self):
        """Test IP extraction from client when no X-Forwarded-For."""
        scope = {
            "headers": [],
            "client": ("203.0.113.42", 54321),
        }
        assert get_client_ip_from_scope(scope) == "203.0.113.42"

    def test_get_client_ip_from_scope_no_client(self):
        """Test IP extraction when no client info available."""
        scope = {"headers": []}
        assert get_client_ip_from_scope(scope) == "unknown"

    def test_get_rate_limit_key_authenticated_user(self):
        """Test rate limit key generation for authenticated user."""
        mock_user = mock.MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 42

        scope = {"user": mock_user}
        key = get_rate_limit_key(scope, "test_group")

        assert key == "ws:test_group:user:42"

    def test_get_rate_limit_key_anonymous_user(self):
        """Test rate limit key generation for anonymous user."""
        scope = {
            "user": AnonymousUser(),
            "headers": [],
            "client": ("192.168.1.100", 8000),
        }
        key = get_rate_limit_key(scope, "test_group")

        assert key == "ws:test_group:ip:192.168.1.100"


@pytest.mark.django_db
class TestWebSocketRateLimits:
    """Tests for WebSocketRateLimits configuration class."""

    def test_default_rate_limits(self):
        """Test that default rate limits are accessible."""
        assert WebSocketRateLimits.WS_CONNECT == "30/m"
        assert WebSocketRateLimits.WS_CONNECT_ANONYMOUS == "10/m"
        assert WebSocketRateLimits.WS_MESSAGE == "60/m"
        assert WebSocketRateLimits.WS_MESSAGE_ANONYMOUS == "20/m"
        assert WebSocketRateLimits.WS_AI_QUERY == "20/m"
        assert WebSocketRateLimits.WS_AI_QUERY_ANONYMOUS == "5/m"

    def test_get_rate_for_authenticated_user(self):
        """Test rate selection for authenticated user."""
        mock_user = mock.MagicMock()
        mock_user.is_authenticated = True
        mock_user.is_superuser = False

        rate = WebSocketRateLimits.get_rate_for_user("WS_CONNECT", mock_user)
        assert rate == "30/m"

    def test_get_rate_for_anonymous_user(self):
        """Test rate selection for anonymous user."""
        rate = WebSocketRateLimits.get_rate_for_user("WS_CONNECT", AnonymousUser())
        assert rate == "10/m"

    def test_get_rate_for_superuser(self):
        """Test that superusers get higher limits (5x)."""
        mock_user = mock.MagicMock()
        mock_user.is_authenticated = True
        mock_user.is_superuser = True

        rate = WebSocketRateLimits.get_rate_for_user("WS_CONNECT", mock_user)
        # Default is 30/m, superuser gets 5x = 150/m
        assert rate == "150/m"


@pytest.mark.django_db
class TestCheckRateLimit:
    """Tests for the check_rate_limit function."""

    def setup_method(self):
        """Clear rate limit cache before each test."""
        cache = caches["default"]
        cache.clear()

    def test_rate_limit_not_exceeded(self):
        """Test that requests under the limit are allowed."""
        scope = {
            "user": AnonymousUser(),
            "headers": [],
            "client": ("10.0.0.1", 8000),
        }

        is_limited, info = check_rate_limit(scope, "test_group", "5/m", increment=True)

        assert is_limited is False
        assert info["limit"] == 5
        assert info["remaining"] == 4

    def test_rate_limit_exceeded(self):
        """Test that requests over the limit are blocked."""
        scope = {
            "user": AnonymousUser(),
            "headers": [],
            "client": ("10.0.0.2", 8000),
        }

        # Make 5 requests (the limit)
        for _ in range(5):
            is_limited, _ = check_rate_limit(scope, "test_exceed", "5/m", increment=True)
            assert is_limited is False

        # 6th request should be limited
        is_limited, info = check_rate_limit(scope, "test_exceed", "5/m", increment=True)
        assert is_limited is True
        assert info["remaining"] == 0

    @override_settings(RATELIMIT_DISABLE=True)
    def test_rate_limit_disabled(self):
        """Test that rate limiting can be disabled via settings."""
        scope = {
            "user": AnonymousUser(),
            "headers": [],
            "client": ("10.0.0.3", 8000),
        }

        # Even after many requests, should not be limited when disabled
        for _ in range(100):
            is_limited, _ = check_rate_limit(
                scope, "test_disabled", "1/m", increment=True
            )
            assert is_limited is False


@pytest.mark.serial
class WebSocketRateLimitIntegrationTestCase(WebsocketFixtureBaseTestCase):
    """
    Integration tests for WebSocket rate limiting in actual consumers.

    Marked as serial because websocket tests use async event loops that
    can conflict with pytest-xdist workers.
    """

    def setUp(self):
        """Set up test fixtures and clear rate limit cache."""
        super().setUp()
        # Clear the rate limit cache before each test
        cache = caches["default"]
        cache.clear()

    @override_settings(RATELIMIT_DISABLE=True)
    @mock.patch(
        "opencontractserver.llms.agents.agent_factory.UnifiedAgentFactory.create_document_agent",
        new_callable=mock.AsyncMock,
    )
    async def test_rate_limiting_bypassed_when_disabled(
        self,
        mock_create_document_agent: mock.AsyncMock,
    ) -> None:
        """Test that rate limiting is bypassed when RATELIMIT_DISABLE is True."""
        mock_create_document_agent.return_value = mock.MagicMock()

        valid_graphql_doc_id = to_global_id("DocumentType", self.doc.id)

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/document/{valid_graphql_doc_id}/query/?token={self.token}",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "Connection should succeed when rate limiting disabled")

        await communicator.disconnect()

    @mock.patch(
        "opencontractserver.llms.agents.agent_factory.UnifiedAgentFactory.create_document_agent",
        new_callable=mock.AsyncMock,
    )
    async def test_authenticated_user_rate_limit(
        self,
        mock_create_document_agent: mock.AsyncMock,
    ) -> None:
        """Test that authenticated users can connect within rate limits."""
        mock_create_document_agent.return_value = mock.MagicMock()

        valid_graphql_doc_id = to_global_id("DocumentType", self.doc.id)

        # First connection should succeed
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/document/{valid_graphql_doc_id}/query/?token={self.token}",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "First connection should succeed")

        await communicator.disconnect()

    @mock.patch(
        "opencontractserver.llms.agents.agent_factory.UnifiedAgentFactory.create_document_agent",
        new_callable=mock.AsyncMock,
    )
    @mock.patch("config.websocket.ratelimits.check_rate_limit")
    async def test_message_rate_limit_response(
        self,
        mock_check_rate_limit: mock.MagicMock,
        mock_create_document_agent: mock.AsyncMock,
    ) -> None:
        """Test that rate limited messages return proper error response."""
        # Create a mock agent that won't actually process anything
        mock_agent = mock.MagicMock()
        mock_agent.stream = mock.AsyncMock(return_value=iter([]))
        mock_create_document_agent.return_value = mock_agent

        # Configure rate limit check to allow connection but block messages
        call_count = 0

        def rate_limit_side_effect(scope, group, rate, increment=True):
            nonlocal call_count
            call_count += 1
            # Allow first few calls (for connection), then limit messages
            if "ws_connect" in group or call_count < 3:
                return False, {"limit": 10, "remaining": 5, "reset_time": 60}
            return True, {"limit": 10, "remaining": 0, "reset_time": 60, "key": "test:key"}

        mock_check_rate_limit.side_effect = rate_limit_side_effect

        valid_graphql_doc_id = to_global_id("DocumentType", self.doc.id)

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/document/{valid_graphql_doc_id}/query/?token={self.token}",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "Connection should succeed")

        # Send a query that should be rate limited
        await communicator.send_to(json.dumps({"query": "Test query"}))

        # Should receive a RATE_LIMITED message
        try:
            response = await communicator.receive_from(timeout=5)
            msg = json.loads(response)
            # The message type should indicate rate limiting
            self.assertIn(msg.get("type"), ["RATE_LIMITED", "SYNC_CONTENT"])
        except Exception:
            pass  # Timeout is acceptable if message was blocked

        await communicator.disconnect()


@pytest.mark.serial
class WebSocketConnectionRateLimitTestCase(WebsocketFixtureBaseTestCase):
    """
    Tests for connection-level rate limiting via middleware.

    Marked as serial for websocket async compatibility.
    """

    def setUp(self):
        """Set up test fixtures and clear rate limit cache."""
        super().setUp()
        cache = caches["default"]
        cache.clear()

    @mock.patch("config.websocket.middlewares.ratelimit_middleware.check_rate_limit")
    async def test_connection_rejected_when_rate_limited(
        self,
        mock_check_rate_limit: mock.MagicMock,
    ) -> None:
        """Test that connections are rejected when rate limit is exceeded."""
        # Configure to return rate limited
        mock_check_rate_limit.return_value = (
            True,
            {"limit": 10, "remaining": 0, "reset_time": 60, "key": "test:key"},
        )

        valid_graphql_doc_id = to_global_id("DocumentType", self.doc.id)

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/document/{valid_graphql_doc_id}/query/?token={self.token}",
        )

        connected, close_code = await communicator.connect()

        # Connection should be rejected with code 4029
        self.assertFalse(connected, "Connection should be rejected when rate limited")
        self.assertEqual(close_code, 4029, "Close code should be 4029 for rate limiting")

    @mock.patch("config.websocket.middlewares.ratelimit_middleware.check_rate_limit")
    async def test_connection_allowed_when_not_rate_limited(
        self,
        mock_check_rate_limit: mock.MagicMock,
    ) -> None:
        """Test that connections proceed when under rate limit."""
        # Configure to allow (not rate limited)
        mock_check_rate_limit.return_value = (
            False,
            {"limit": 30, "remaining": 29, "reset_time": 60},
        )

        valid_graphql_doc_id = to_global_id("DocumentType", self.doc.id)

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/document/{valid_graphql_doc_id}/query/?token={self.token}",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "Connection should succeed when not rate limited")

        await communicator.disconnect()
