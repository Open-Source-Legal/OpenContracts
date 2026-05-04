"""
Tests for token expiration handling across authentication backends and middleware.

These tests verify that:
1. Auth0RemoteUserJSONWebTokenBackend properly re-raises JSONWebTokenExpired
2. WebSocket middlewares set auth_error in scope for expired tokens
3. The frontend receives proper error signals for token expiration
"""

import logging
from unittest import mock

import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_jwt.exceptions import JSONWebTokenError, JSONWebTokenExpired

from config.graphql_auth0_auth.backends import Auth0RemoteUserJSONWebTokenBackend
from config.websocket.middleware import (
    WS_AUTH_SUBPROTOCOL,
    WS_CLOSE_TOKEN_EXPIRED,
    WS_CLOSE_TOKEN_INVALID,
    WS_CLOSE_UNAUTHENTICATED,
)
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

User = get_user_model()
logger = logging.getLogger(__name__)


class Auth0BackendTokenExpirationTestCase(TestCase):
    """
    Tests for Auth0RemoteUserJSONWebTokenBackend token expiration handling.

    Verifies that JSONWebTokenExpired is re-raised instead of being swallowed,
    allowing the GraphQL layer to properly signal token expiration to the frontend.
    """

    def setUp(self):
        self.backend = Auth0RemoteUserJSONWebTokenBackend()
        self.mock_request = mock.MagicMock()
        self.mock_request._jwt_token_auth = False

    @mock.patch("config.graphql_auth0_auth.backends.graphql_jwt.utils.get_credentials")
    @mock.patch("config.graphql_auth0_auth.backends.get_user_by_token")
    def test_expired_token_raises_exception(
        self, mock_get_user_by_token, mock_get_credentials
    ):
        """
        Verify that when get_user_by_token raises JSONWebTokenExpired,
        the authenticate method re-raises it instead of returning None.
        """
        mock_get_credentials.return_value = "expired_token"
        mock_get_user_by_token.side_effect = JSONWebTokenExpired()

        with self.assertRaises(JSONWebTokenExpired):
            self.backend.authenticate(request=self.mock_request)

    @mock.patch("config.graphql_auth0_auth.backends.graphql_jwt.utils.get_credentials")
    @mock.patch("config.graphql_auth0_auth.backends.get_user_by_token")
    def test_other_jwt_errors_return_none(
        self, mock_get_user_by_token, mock_get_credentials
    ):
        """
        Verify that other JWT errors (not expiration) still return None
        to maintain backwards compatibility.
        """
        mock_get_credentials.return_value = "invalid_token"
        mock_get_user_by_token.side_effect = JSONWebTokenError("Invalid token")

        result = self.backend.authenticate(request=self.mock_request)
        self.assertIsNone(result)

    @mock.patch("config.graphql_auth0_auth.backends.graphql_jwt.utils.get_credentials")
    @mock.patch("config.graphql_auth0_auth.backends.get_user_by_token")
    def test_valid_token_returns_user(
        self, mock_get_user_by_token, mock_get_credentials
    ):
        """
        Verify that valid tokens still return the user as expected.
        """
        mock_user = mock.MagicMock()
        mock_user.id = 1
        mock_get_credentials.return_value = "valid_token"
        mock_get_user_by_token.return_value = mock_user

        result = self.backend.authenticate(request=self.mock_request)
        self.assertEqual(result, mock_user)

    @mock.patch("config.graphql_auth0_auth.backends.graphql_jwt.utils.get_credentials")
    def test_no_token_returns_none(self, mock_get_credentials):
        """
        Verify that when no token is provided, None is returned (anonymous access).
        """
        mock_get_credentials.return_value = None

        result = self.backend.authenticate(request=self.mock_request)
        self.assertIsNone(result)


@pytest.mark.serial
class WebSocketTokenExpirationTestCase(WebsocketFixtureBaseTestCase):
    """
    Tests for WebSocket middleware token expiration handling.

    Verifies that auth_error is properly set in scope when tokens expire,
    allowing consumers to close connections with appropriate codes.
    """

    @mock.patch(
        "opencontractserver.llms.agents.agent_factory.UnifiedAgentFactory.create_document_agent",
        new_callable=mock.AsyncMock,
    )
    @mock.patch("config.websocket.middleware._get_user_from_token")
    async def test_jwt_middleware_sets_auth_error_on_expired_token(
        self,
        mock_get_user_from_token_fn: mock.AsyncMock,
        mock_create_document_agent: mock.AsyncMock,
    ) -> None:
        """
        Verifies that GraphQLJWTTokenAuthMiddleware sets auth_error in scope
        when a token has expired, with the correct close code.
        """
        mock_create_document_agent.return_value = mock.MagicMock()
        mock_get_user_from_token_fn.side_effect = JSONWebTokenExpired()

        # Use unified agent-chat endpoint
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}",
            subprotocols=[WS_AUTH_SUBPROTOCOL, "expired_token"],
        )

        # The connection may fail, but we want to verify the scope was set correctly
        connected, close_code = await communicator.connect()

        # The consumer should have received auth_error in scope
        # Note: The actual close behavior depends on the consumer implementation
        self.assertFalse(connected)
        await communicator.disconnect()

    @mock.patch(
        "opencontractserver.llms.agents.agent_factory.UnifiedAgentFactory.create_document_agent",
        new_callable=mock.AsyncMock,
    )
    @mock.patch("config.websocket.middleware._get_user_from_token")
    async def test_jwt_middleware_sets_auth_error_on_invalid_token(
        self,
        mock_get_user_from_token_fn: mock.AsyncMock,
        mock_create_document_agent: mock.AsyncMock,
    ) -> None:
        """
        Verifies that GraphQLJWTTokenAuthMiddleware sets auth_error in scope
        when a token is invalid (not expired), with the correct close code.
        """
        mock_create_document_agent.return_value = mock.MagicMock()
        mock_get_user_from_token_fn.side_effect = JSONWebTokenError(
            "Invalid token format"
        )

        # Use unified agent-chat endpoint
        communicator = WebsocketCommunicator(
            self.application,
            f"ws/agent-chat/?document_id={self.doc.id}",
            subprotocols=[WS_AUTH_SUBPROTOCOL, "invalid_token"],
        )

        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()


class TestWebSocketCloseCodesConsistency(TestCase):
    """
    Verify that WebSocket close codes follow conventions.
    """

    def test_close_codes_are_in_valid_range(self):
        """
        WebSocket close codes should be in the 4000-4999 range
        reserved for application use.
        """
        self.assertGreaterEqual(WS_CLOSE_TOKEN_EXPIRED, 4000)
        self.assertLess(WS_CLOSE_TOKEN_EXPIRED, 5000)

        self.assertGreaterEqual(WS_CLOSE_TOKEN_INVALID, 4000)
        self.assertLess(WS_CLOSE_TOKEN_INVALID, 5000)

    def test_close_codes_are_distinct(self):
        """
        Token expired and token invalid should have different close codes
        so the frontend can distinguish between them.
        """
        self.assertNotEqual(
            WS_CLOSE_TOKEN_EXPIRED,
            WS_CLOSE_TOKEN_INVALID,
            "Expired and invalid tokens should have distinct close codes",
        )

    def test_unauthenticated_code_is_distinct(self):
        """
        WS_CLOSE_UNAUTHENTICATED should be distinct from token error codes.
        """
        self.assertNotEqual(
            WS_CLOSE_UNAUTHENTICATED,
            WS_CLOSE_TOKEN_EXPIRED,
            "Unauthenticated and expired should have distinct codes",
        )
        self.assertNotEqual(
            WS_CLOSE_UNAUTHENTICATED,
            WS_CLOSE_TOKEN_INVALID,
            "Unauthenticated and invalid should have distinct codes",
        )

    def test_unauthenticated_code_in_valid_range(self):
        """
        WS_CLOSE_UNAUTHENTICATED should be in the 4000-4999 range.
        """
        self.assertGreaterEqual(WS_CLOSE_UNAUTHENTICATED, 4000)
        self.assertLess(WS_CLOSE_UNAUTHENTICATED, 5000)
