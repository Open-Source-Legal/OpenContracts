"""
Tests for WebSocket rate limiting infrastructure.

Covers:
1. Shared infrastructure (parse_rate, tiers, IP extraction, cache counter)
2. WebSocket config defaults and overrides
3. RateLimitedConsumerMixin (message-level rate limiting)
4. WebSocketRateLimitMiddleware (connection-level rate limiting)
"""

import json
from importlib import reload
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import TestCase, override_settings

from config.ratelimits import (
    RateLimits,
    apply_multiplier_to_rate,
    check_rate_limit,
    format_rate_limit_message,
    get_client_ip_from_request,
    get_client_ip_from_scope,
    get_rate_limit_key,
    get_tier_multiplier,
    is_user_authenticated,
    parse_rate,
    period_to_name,
)

# =============================================================================
# 1. Shared infrastructure — pure unit tests (no Django fixtures needed)
# =============================================================================


class ParseRateTests(TestCase):
    """Tests for rate string parsing utility."""

    def test_parse_valid_rates(self):
        self.assertEqual(parse_rate("10/m"), (10, 60))
        self.assertEqual(parse_rate("100/h"), (100, 3600))
        self.assertEqual(parse_rate("5/s"), (5, 1))
        self.assertEqual(parse_rate("1/d"), (1, 86400))

    def test_parse_invalid_format(self):
        with self.assertRaises(ValueError):
            parse_rate("invalid")
        with self.assertRaises(ValueError):
            parse_rate("10/x")
        with self.assertRaises(ValueError):
            parse_rate("abc/m")

    def test_period_to_name(self):
        self.assertEqual(period_to_name(60), "minute")
        self.assertEqual(period_to_name(3600), "hour")
        self.assertEqual(period_to_name(86400), "day")
        self.assertEqual(period_to_name(1), "second")
        self.assertEqual(period_to_name(999), "period")

    def test_format_rate_limit_message(self):
        msg = format_rate_limit_message("10/m")
        self.assertIn("10", msg)
        self.assertIn("minute", msg)

    def test_format_rate_limit_message_invalid(self):
        msg = format_rate_limit_message("bad")
        self.assertIn("Rate limit exceeded", msg)


class ApplyMultiplierTests(TestCase):
    """Tests for rate multiplier application."""

    def test_double(self):
        self.assertEqual(apply_multiplier_to_rate("10/m", 2.0), "20/m")

    def test_half(self):
        self.assertEqual(apply_multiplier_to_rate("10/m", 0.5), "5/m")

    def test_minimum_is_one(self):
        self.assertEqual(apply_multiplier_to_rate("1/m", 0.1), "1/m")

    def test_invalid_rate_passthrough(self):
        self.assertEqual(apply_multiplier_to_rate("invalid", 2.0), "invalid")


class TierMultiplierTests(TestCase):
    """Tests for user tier multiplier logic."""

    def test_anonymous_user(self):
        self.assertEqual(get_tier_multiplier(None), 1.0)
        self.assertEqual(get_tier_multiplier(AnonymousUser()), 1.0)

    def test_authenticated_user(self):
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        self.assertEqual(get_tier_multiplier(user), 2.0)

    def test_superuser(self):
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = True
        self.assertEqual(get_tier_multiplier(user), 10.0)

    def test_usage_capped_user(self):
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        user.is_usage_capped = True
        # 2.0 * 0.5 = 1.0
        self.assertEqual(get_tier_multiplier(user), 1.0)


class IsUserAuthenticatedTests(TestCase):
    """Tests for authentication check helper."""

    def test_none_user(self):
        self.assertFalse(is_user_authenticated(None))

    def test_anonymous_user(self):
        self.assertFalse(is_user_authenticated(AnonymousUser()))

    def test_authenticated_user(self):
        user = MagicMock()
        user.is_authenticated = True
        self.assertTrue(is_user_authenticated(user))


# =============================================================================
# 2. IP extraction
# =============================================================================


class IPExtractionTests(TestCase):
    """Tests for IP extraction from requests and ASGI scopes."""

    def test_request_with_x_forwarded_for(self):
        request = MagicMock()
        request.META = {"HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8"}
        self.assertEqual(get_client_ip_from_request(request), "1.2.3.4")

    def test_request_with_remote_addr(self):
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "10.0.0.1"}
        self.assertEqual(get_client_ip_from_request(request), "10.0.0.1")

    def test_scope_with_x_forwarded_for(self):
        scope = {"headers": [(b"x-forwarded-for", b"203.0.113.1, 198.51.100.2")]}
        self.assertEqual(get_client_ip_from_scope(scope), "203.0.113.1")

    def test_scope_with_client_tuple(self):
        scope = {"headers": [], "client": ("192.168.1.1", 12345)}
        self.assertEqual(get_client_ip_from_scope(scope), "192.168.1.1")

    def test_scope_unknown(self):
        scope = {"headers": []}
        self.assertEqual(get_client_ip_from_scope(scope), "unknown")


# =============================================================================
# 3. Cache-based rate limiting
# =============================================================================


class CacheRateLimitTests(TestCase):
    """Tests for cache-based rate limit counter."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _make_scope(self, user=None, ip="127.0.0.1"):
        scope = {
            "headers": [],
            "client": (ip, 12345),
        }
        if user:
            scope["user"] = user
        return scope

    def test_not_rate_limited_under_threshold(self):
        scope = self._make_scope()
        is_limited, info = check_rate_limit(scope, "test_group", "10/m")
        self.assertFalse(is_limited)
        self.assertEqual(info["limit"], 10)
        self.assertEqual(info["remaining"], 9)

    def test_rate_limited_when_exceeding_threshold(self):
        scope = self._make_scope()
        for _ in range(10):
            check_rate_limit(scope, "test_exceed", "10/m")

        is_limited, info = check_rate_limit(scope, "test_exceed", "10/m")
        self.assertTrue(is_limited)
        self.assertEqual(info["remaining"], 0)

    def test_authenticated_user_keyed_by_user_id(self):
        user = MagicMock()
        user.is_authenticated = True
        user.id = 42
        scope = self._make_scope(user=user)

        key = get_rate_limit_key(scope, "test")
        self.assertIn("user:42", key)

    def test_anonymous_keyed_by_ip(self):
        scope = self._make_scope(ip="10.0.0.99")
        key = get_rate_limit_key(scope, "test")
        self.assertIn("ip:10.0.0.99", key)

    @override_settings(RATELIMIT_DISABLE=True)
    def test_disabled_rate_limiting(self):
        scope = self._make_scope()
        is_limited, _ = check_rate_limit(scope, "test_disabled", "1/m")
        self.assertFalse(is_limited)

    @override_settings(RATELIMIT_FAIL_OPEN=True)
    def test_fail_open_on_cache_error(self):
        scope = self._make_scope()
        with patch("config.ratelimits.cache.caches") as mock_caches:
            mock_caches.__getitem__ = MagicMock(side_effect=Exception("cache down"))
            is_limited, _ = check_rate_limit(scope, "test_fail_open", "1/m")
            self.assertFalse(is_limited)

    @override_settings(RATELIMIT_FAIL_OPEN=False)
    def test_fail_closed_on_cache_error(self):
        scope = self._make_scope()
        with patch("config.ratelimits.cache.caches") as mock_caches:
            mock_caches.__getitem__ = MagicMock(side_effect=Exception("cache down"))
            is_limited, _ = check_rate_limit(scope, "test_fail_closed", "1/m")
            self.assertTrue(is_limited)


# =============================================================================
# 4. RateLimits config
# =============================================================================


class RateLimitsConfigTests(TestCase):
    """Tests for the unified RateLimits configuration."""

    def test_graphql_defaults_present(self):
        self.assertEqual(RateLimits.AUTH_LOGIN, "5/m")
        self.assertEqual(RateLimits.READ_MEDIUM, "30/m")

    def test_websocket_defaults_present(self):
        self.assertEqual(RateLimits.WS_CONNECT, "30/m")
        self.assertEqual(RateLimits.WS_AI_QUERY, "20/m")
        self.assertEqual(RateLimits.WS_MESSAGE, "60/m")
        self.assertEqual(RateLimits.WS_CONNECT_ANONYMOUS, "10/m")

    def test_get_with_default(self):
        self.assertEqual(RateLimits.get("NONEXISTENT", "99/h"), "99/h")
        self.assertEqual(RateLimits.get("WS_CONNECT"), "30/m")

    def test_get_ws_rate_for_authenticated_user(self):
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        rate = RateLimits.get_ws_rate_for_user("WS_AI_QUERY", user)
        # authenticated = 2x multiplier: 20 * 2 = 40
        self.assertEqual(rate, "40/m")

    def test_get_ws_rate_for_anonymous_user(self):
        rate = RateLimits.get_ws_rate_for_user("WS_AI_QUERY", None)
        # Returns WS_AI_QUERY_ANONYMOUS
        self.assertEqual(rate, "5/m")

    def test_get_ws_rate_for_superuser(self):
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = True
        rate = RateLimits.get_ws_rate_for_user("WS_CONNECT", user)
        # superuser = 10x: 30 * 10 = 300
        self.assertEqual(rate, "300/m")

    def test_unknown_attribute_raises(self):
        with self.assertRaises(AttributeError):
            _ = RateLimits.NONEXISTENT_RATE

    def test_websocket_overrides(self):
        import config.ratelimits.config as config_module

        with self.settings(WEBSOCKET_RATE_LIMIT_OVERRIDES={"WS_CONNECT": "100/m"}):
            reload(config_module)
            self.assertEqual(config_module.RateLimits.WS_CONNECT, "100/m")

            # Restore
            reload(config_module)


# =============================================================================
# 5. RateLimitedConsumerMixin
# =============================================================================


class RateLimitedConsumerMixinTests(TestCase):
    """Tests for the mixin that adds message-level rate limiting."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @pytest.mark.asyncio
    async def test_mixin_allows_messages_under_limit(self):
        from config.websocket.ratelimits import RateLimitedConsumerMixin

        consumer = MagicMock(spec=RateLimitedConsumerMixin)
        consumer.message_rate_type = "WS_MESSAGE"
        consumer.scope = {
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "user": None,
        }
        consumer.check_message_rate_limit = (
            RateLimitedConsumerMixin.check_message_rate_limit.__get__(consumer)
        )
        consumer.send = AsyncMock()

        result = await consumer.check_message_rate_limit()
        self.assertTrue(result)
        consumer.send.assert_not_called()

    @pytest.mark.asyncio
    @override_settings(RATELIMIT_DISABLE=True)
    async def test_mixin_allows_when_disabled(self):
        from config.websocket.ratelimits import RateLimitedConsumerMixin

        consumer = MagicMock(spec=RateLimitedConsumerMixin)
        consumer.message_rate_type = "WS_MESSAGE"
        consumer.scope = {
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
        consumer.check_message_rate_limit = (
            RateLimitedConsumerMixin.check_message_rate_limit.__get__(consumer)
        )

        result = await consumer.check_message_rate_limit()
        self.assertTrue(result)

    @pytest.mark.asyncio
    async def test_mixin_sends_rate_limited_response(self):
        """When over limit, the mixin sends RATE_LIMITED and returns False."""
        from config.websocket.ratelimits import RateLimitedConsumerMixin

        consumer = MagicMock(spec=RateLimitedConsumerMixin)
        consumer.message_rate_type = "WS_MESSAGE"
        consumer.scope = {
            "headers": [],
            "client": ("10.10.10.10", 12345),
            "user": None,
        }
        consumer.check_message_rate_limit = (
            RateLimitedConsumerMixin.check_message_rate_limit.__get__(consumer)
        )
        consumer.send = AsyncMock()

        # Patch check_rate_limit_async to return limited
        with patch(
            "config.websocket.ratelimits.check_rate_limit_async",
            new_callable=AsyncMock,
            return_value=(
                True,
                {"limit": 20, "remaining": 0, "reset_time": 60, "key": "test"},
            ),
        ):
            result = await consumer.check_message_rate_limit()
            self.assertFalse(result)
            consumer.send.assert_called_once()
            sent_data = json.loads(consumer.send.call_args[0][0])
            self.assertEqual(sent_data["type"], "RATE_LIMITED")
            self.assertIn("Rate limit exceeded", sent_data["content"])


# =============================================================================
# 6. WebSocketRateLimitMiddleware
# =============================================================================


class RateLimitMiddlewareTests(TestCase):
    """Tests for connection-level rate limiting middleware."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @pytest.mark.asyncio
    async def test_non_websocket_passes_through(self):
        from config.websocket.middlewares.ratelimit_middleware import (
            WebSocketRateLimitMiddleware,
        )

        inner = AsyncMock()
        middleware = WebSocketRateLimitMiddleware(inner)

        scope = {"type": "http", "path": "/api/"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        inner.assert_called_once()

    @pytest.mark.asyncio
    @override_settings(RATELIMIT_DISABLE=True)
    async def test_disabled_passes_through(self):
        from config.websocket.middlewares.ratelimit_middleware import (
            WebSocketRateLimitMiddleware,
        )

        inner = AsyncMock()
        middleware = WebSocketRateLimitMiddleware(inner)

        scope = {
            "type": "websocket",
            "path": "/ws/test/",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        inner.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_when_rate_limited(self):
        from config.websocket.middlewares.ratelimit_middleware import (
            WebSocketRateLimitMiddleware,
        )

        inner = AsyncMock()
        middleware = WebSocketRateLimitMiddleware(inner)

        scope = {
            "type": "websocket",
            "path": "/ws/test/",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
        receive = AsyncMock()
        send = AsyncMock()

        with patch(
            "config.websocket.middlewares.ratelimit_middleware.check_rate_limit",
            return_value=(True, {"limit": 10, "remaining": 0, "reset_time": 60}),
        ):
            await middleware(scope, receive, send)
            # Should send close, not pass through
            inner.assert_not_called()
            send.assert_called_once()
            close_msg = send.call_args[0][0]
            self.assertEqual(close_msg["type"], "websocket.close")
            self.assertEqual(close_msg["code"], 4029)

    @pytest.mark.asyncio
    async def test_passes_through_when_not_limited(self):
        from config.websocket.middlewares.ratelimit_middleware import (
            WebSocketRateLimitMiddleware,
        )

        inner = AsyncMock()
        middleware = WebSocketRateLimitMiddleware(inner)

        scope = {
            "type": "websocket",
            "path": "/ws/test/",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
        receive = AsyncMock()
        send = AsyncMock()

        with patch(
            "config.websocket.middlewares.ratelimit_middleware.check_rate_limit",
            return_value=(False, {"limit": 10, "remaining": 9, "reset_time": 60}),
        ):
            await middleware(scope, receive, send)
            inner.assert_called_once()


# =============================================================================
# 7. Connection middleware unit tests (mocked cache for speed)
# =============================================================================


class ConnectionRateLimitIntegrationTests(TestCase):
    """Tests for middleware rejecting connections at the ASGI level."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @pytest.mark.asyncio
    async def test_middleware_close_code_is_4029(self):
        """Middleware sends close code 4029 when connection rate exceeded."""
        from config.websocket.middlewares.ratelimit_middleware import (
            WebSocketRateLimitMiddleware,
        )

        inner = AsyncMock()
        middleware = WebSocketRateLimitMiddleware(inner)

        scope = {
            "type": "websocket",
            "path": "/ws/agent-chat/",
            "headers": [],
            "client": ("192.168.1.1", 54321),
        }
        send = AsyncMock()

        with patch(
            "config.websocket.middlewares.ratelimit_middleware.check_rate_limit",
            return_value=(True, {"limit": 10, "remaining": 0, "reset_time": 60}),
        ):
            await middleware(scope, AsyncMock(), send)

            close_msg = send.call_args[0][0]
            self.assertEqual(close_msg["code"], 4029)
            self.assertIn("Rate limit exceeded", close_msg["reason"])

    @pytest.mark.asyncio
    async def test_middleware_uses_anonymous_rate_for_unauthenticated(self):
        """Anonymous connections use the lower WS_CONNECT_ANONYMOUS rate."""
        from config.websocket.middlewares.ratelimit_middleware import (
            WebSocketRateLimitMiddleware,
        )

        inner = AsyncMock()
        middleware = WebSocketRateLimitMiddleware(inner)

        scope = {
            "type": "websocket",
            "path": "/ws/test/",
            "headers": [],
            "client": ("10.0.0.1", 12345),
            "user": AnonymousUser(),
        }

        with patch(
            "config.websocket.middlewares.ratelimit_middleware.check_rate_limit",
            return_value=(False, {}),
        ) as mock_check:
            await middleware(scope, AsyncMock(), AsyncMock())
            # The rate passed should be the anonymous rate
            call_args = mock_check.call_args
            rate_used = call_args[0][2]  # third positional arg is rate
            self.assertEqual(rate_used, "10/m")

    @pytest.mark.asyncio
    async def test_middleware_uses_auth_rate_for_authenticated(self):
        """Authenticated connections use the higher WS_CONNECT rate with tier multiplier."""
        from config.websocket.middlewares.ratelimit_middleware import (
            WebSocketRateLimitMiddleware,
        )

        inner = AsyncMock()
        middleware = WebSocketRateLimitMiddleware(inner)

        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        user.id = 42

        scope = {
            "type": "websocket",
            "path": "/ws/test/",
            "headers": [],
            "client": ("10.0.0.1", 12345),
            "user": user,
        }

        with patch(
            "config.websocket.middlewares.ratelimit_middleware.check_rate_limit",
            return_value=(False, {}),
        ) as mock_check:
            await middleware(scope, AsyncMock(), AsyncMock())
            call_args = mock_check.call_args
            rate_used = call_args[0][2]
            # authenticated 2x multiplier on WS_CONNECT (30/m) = 60/m
            self.assertEqual(rate_used, "60/m")
