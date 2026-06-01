"""
Extended tests for the MCP module: telemetry, TTLLRUCache, RateLimiter,
formatters, config, and permissions.

Complements the existing mcp/tests/test_mcp.py with coverage of previously
untested sub-modules.
"""

import asyncio
import hashlib
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from opencontractserver.mcp.config import (
    CACHE_TTL,
    DEFAULT_PAGE_SIZE,
    MAX_RESULTS_PER_PAGE,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW,
    SLUG_PATTERN,
    get_mcp_setting,
    validate_slug,
)
from opencontractserver.mcp.formatters import (
    format_annotation,
    format_corpus_summary,
    format_document_summary,
    format_message,
    format_message_with_replies,
    format_thread_summary,
)
from opencontractserver.mcp.permissions import (
    get_anonymous_user,
    sanitize_and_validate_slugs,
)
from opencontractserver.mcp.permissions import validate_slug as perm_validate_slug
from opencontractserver.mcp.server import TTLLRUCache, URIParser
from opencontractserver.mcp.telemetry import (
    IP_HASH_LENGTH,
    MAX_USER_AGENT_LENGTH,
    _get_request_context,
    _hash_ip,
    arecord_mcp_request,
    arecord_mcp_resource_read,
    arecord_mcp_tool_call,
    clear_request_context,
    get_claimed_client_ip_from_scope,
    get_user_agent_from_scope,
    isolated_telemetry_context,
    record_mcp_request,
    record_mcp_resource_read,
    record_mcp_tool_call,
    set_request_context,
)


# --------------------------------------------------------------------------
# Telemetry tests
# --------------------------------------------------------------------------
class TestTelemetryContext(TestCase):
    """Tests for MCP telemetry context management."""

    def tearDown(self):
        clear_request_context()

    def test_set_and_clear_context(self):
        set_request_context(client_ip="1.2.3.4", transport="streamable_http")

        ctx = _get_request_context()
        self.assertEqual(ctx["transport"], "streamable_http")
        self.assertIsNotNone(ctx["client_ip_hash"])

        clear_request_context()
        ctx = _get_request_context()
        self.assertEqual(ctx, {})

    def test_set_context_without_ip(self):
        set_request_context(transport="stdio")

        ctx = _get_request_context()
        self.assertIsNone(ctx["client_ip_hash"])
        self.assertEqual(ctx["transport"], "stdio")

    def test_set_context_with_user_agent(self):
        set_request_context(
            client_ip="1.2.3.4", transport="http", user_agent="Claude-Code/1.0"
        )

        ctx = _get_request_context()
        self.assertEqual(ctx["user_agent"], "Claude-Code/1.0")

    def test_set_context_without_user_agent(self):
        set_request_context(client_ip="1.2.3.4", transport="http")

        ctx = _get_request_context()
        self.assertIsNone(ctx["user_agent"])

    def test_isolated_telemetry_context(self):
        set_request_context(client_ip="10.0.0.1", transport="test")
        with isolated_telemetry_context():
            # Context should be cleared on entry
            ctx = _get_request_context()
            self.assertEqual(ctx, {})

            # Set something inside
            set_request_context(client_ip="10.0.0.2", transport="inner")
        # After exit, context should be cleared

        ctx = _get_request_context()
        self.assertEqual(ctx, {})

    def test_isolated_context_cleans_up_on_exception(self):
        try:
            with isolated_telemetry_context():
                set_request_context(client_ip="10.0.0.3", transport="error")
                raise RuntimeError("test error")
        except RuntimeError:
            pass

        ctx = _get_request_context()
        self.assertEqual(ctx, {})


class TestIpHashing(TestCase):
    """Tests for IP address hashing in telemetry."""

    def test_hash_ip_returns_string(self):
        result = _hash_ip("1.2.3.4")
        self.assertIsInstance(result, str)

    def test_hash_ip_truncated_to_length(self):
        result = _hash_ip("1.2.3.4")
        self.assertEqual(len(result), IP_HASH_LENGTH)

    def test_hash_ip_deterministic(self):
        result1 = _hash_ip("1.2.3.4")
        result2 = _hash_ip("1.2.3.4")
        self.assertEqual(result1, result2)

    def test_hash_ip_different_ips_different_hashes(self):
        result1 = _hash_ip("1.2.3.4")
        result2 = _hash_ip("5.6.7.8")
        self.assertNotEqual(result1, result2)

    @override_settings(TELEMETRY_IP_SALT="custom-salt")
    def test_hash_ip_uses_salt(self):
        expected = hashlib.sha256(b"custom-salt:1.2.3.4").hexdigest()[:IP_HASH_LENGTH]
        result = _hash_ip("1.2.3.4")
        self.assertEqual(result, expected)


class TestTelemetryRecording(TestCase):
    """Tests for telemetry event recording functions."""

    def tearDown(self):
        clear_request_context()

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_record_mcp_tool_call_success(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            set_request_context(client_ip="1.2.3.4", transport="http")
            result = record_mcp_tool_call("list_public_corpuses", success=True)
        self.assertTrue(result)
        mock_record.assert_called_once()
        args = mock_record.call_args
        self.assertEqual(args[0][0], "mcp_tool_call")
        props = args[0][1]
        self.assertEqual(props["tool_name"], "list_public_corpuses")
        self.assertTrue(props["success"])
        self.assertEqual(props["transport"], "http")
        self.assertIn("client_ip_hash", props)

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_record_mcp_tool_call_with_resource_slugs(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            result = record_mcp_tool_call(
                "list_documents",
                success=True,
                corpus_slug="my-corpus",
                document_slug="my-doc",
            )
        self.assertTrue(result)
        props = mock_record.call_args[0][1]
        self.assertEqual(props["corpus_slug"], "my-corpus")
        self.assertEqual(props["document_slug"], "my-doc")

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_record_mcp_tool_call_omits_none_slugs(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            record_mcp_tool_call("list_public_corpuses", success=True)
        props = mock_record.call_args[0][1]
        self.assertNotIn("corpus_slug", props)
        self.assertNotIn("document_slug", props)

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_record_mcp_tool_call_failure(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            result = record_mcp_tool_call(
                "search_corpus", success=False, error_type="ValueError"
            )
        self.assertTrue(result)
        props = mock_record.call_args[0][1]
        self.assertFalse(props["success"])
        self.assertEqual(props["error_type"], "ValueError")

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_record_mcp_resource_read(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            result = record_mcp_resource_read("corpus", success=True)
        self.assertTrue(result)
        props = mock_record.call_args[0][1]
        self.assertEqual(props["resource_type"], "corpus")

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_record_mcp_resource_read_with_slugs(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            result = record_mcp_resource_read(
                "document",
                success=True,
                corpus_slug="my-corpus",
                document_slug="my-doc",
            )
        self.assertTrue(result)
        props = mock_record.call_args[0][1]
        self.assertEqual(props["resource_type"], "document")
        self.assertEqual(props["corpus_slug"], "my-corpus")
        self.assertEqual(props["document_slug"], "my-doc")

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_record_mcp_resource_read_omits_none_slugs(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            record_mcp_resource_read("corpus", success=True)
        props = mock_record.call_args[0][1]
        self.assertNotIn("corpus_slug", props)
        self.assertNotIn("document_slug", props)

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_record_mcp_request(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            result = record_mcp_request("/mcp", method="POST", success=True)
        self.assertTrue(result)
        props = mock_record.call_args[0][1]
        self.assertEqual(props["endpoint"], "/mcp")
        self.assertEqual(props["method"], "POST")

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_error_type_not_included_on_success(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            record_mcp_tool_call("test", success=True, error_type="ShouldNotAppear")
        props = mock_record.call_args[0][1]
        self.assertNotIn("error_type", props)

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_no_ip_hash_when_no_context(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            record_mcp_tool_call("test", success=True)
        props = mock_record.call_args[0][1]
        self.assertNotIn("client_ip_hash", props)

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_user_agent_included_in_tool_call(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            set_request_context(
                client_ip="1.2.3.4",
                transport="http",
                user_agent="Claude-Code/1.0",
            )
            record_mcp_tool_call("list_documents", success=True)
        props = mock_record.call_args[0][1]
        self.assertEqual(props["user_agent"], "Claude-Code/1.0")

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_user_agent_included_in_resource_read(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            set_request_context(
                client_ip="1.2.3.4",
                transport="http",
                user_agent="cursor/0.45",
            )
            record_mcp_resource_read("corpus", success=True)
        props = mock_record.call_args[0][1]
        self.assertEqual(props["user_agent"], "cursor/0.45")

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_user_agent_included_in_request(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            set_request_context(
                client_ip="1.2.3.4",
                transport="http",
                user_agent="Googlebot/2.1",
            )
            record_mcp_request("/mcp", success=True)
        props = mock_record.call_args[0][1]
        self.assertEqual(props["user_agent"], "Googlebot/2.1")

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_user_agent_omitted_when_none(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            set_request_context(client_ip="1.2.3.4", transport="http")
            record_mcp_tool_call("test", success=True)
        props = mock_record.call_args[0][1]
        self.assertNotIn("user_agent", props)


class TestAsyncTelemetryRecording(TestCase):
    """Tests for async telemetry event recording functions."""

    def tearDown(self):
        clear_request_context()

    def _run(self, coro):
        return asyncio.run(coro)

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_tool_call_success(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                set_request_context(client_ip="1.2.3.4", transport="http")
                return await arecord_mcp_tool_call("list_public_corpuses", success=True)

        result = self._run(_test())
        self.assertTrue(result)
        mock_arecord.assert_called_once()
        args = mock_arecord.call_args
        self.assertEqual(args[0][0], "mcp_tool_call")
        props = args[0][1]
        self.assertEqual(props["tool_name"], "list_public_corpuses")
        self.assertTrue(props["success"])
        self.assertEqual(props["transport"], "http")
        self.assertIn("client_ip_hash", props)

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_tool_call_with_slugs(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                return await arecord_mcp_tool_call(
                    "list_documents",
                    success=True,
                    corpus_slug="my-corpus",
                    document_slug="my-doc",
                )

        result = self._run(_test())
        self.assertTrue(result)
        props = mock_arecord.call_args[0][1]
        self.assertEqual(props["corpus_slug"], "my-corpus")
        self.assertEqual(props["document_slug"], "my-doc")

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_tool_call_failure(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                return await arecord_mcp_tool_call(
                    "search_corpus", success=False, error_type="ValueError"
                )

        result = self._run(_test())
        self.assertTrue(result)
        props = mock_arecord.call_args[0][1]
        self.assertFalse(props["success"])
        self.assertEqual(props["error_type"], "ValueError")

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_resource_read_success(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                set_request_context(client_ip="1.2.3.4", transport="http")
                return await arecord_mcp_resource_read("corpus", success=True)

        result = self._run(_test())
        self.assertTrue(result)
        props = mock_arecord.call_args[0][1]
        self.assertEqual(props["resource_type"], "corpus")
        self.assertTrue(props["success"])

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_resource_read_with_slugs(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                return await arecord_mcp_resource_read(
                    "document",
                    success=True,
                    corpus_slug="my-corpus",
                    document_slug="my-doc",
                )

        result = self._run(_test())
        self.assertTrue(result)
        props = mock_arecord.call_args[0][1]
        self.assertEqual(props["corpus_slug"], "my-corpus")
        self.assertEqual(props["document_slug"], "my-doc")

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_resource_read_failure(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                return await arecord_mcp_resource_read(
                    "corpus", success=False, error_type="PermissionError"
                )

        result = self._run(_test())
        self.assertTrue(result)
        props = mock_arecord.call_args[0][1]
        self.assertFalse(props["success"])
        self.assertEqual(props["error_type"], "PermissionError")

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_request_success(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                set_request_context(client_ip="1.2.3.4", transport="http")
                return await arecord_mcp_request("/mcp", method="POST", success=True)

        result = self._run(_test())
        self.assertTrue(result)
        props = mock_arecord.call_args[0][1]
        self.assertEqual(props["endpoint"], "/mcp")
        self.assertEqual(props["method"], "POST")
        self.assertTrue(props["success"])

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_request_failure(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                return await arecord_mcp_request(
                    "/mcp", success=False, error_type="TimeoutError"
                )

        result = self._run(_test())
        self.assertTrue(result)
        props = mock_arecord.call_args[0][1]
        self.assertFalse(props["success"])
        self.assertEqual(props["error_type"], "TimeoutError")

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_arecord_mcp_tool_call_user_agent_in_context(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                set_request_context(
                    client_ip="1.2.3.4",
                    transport="http",
                    user_agent="Claude-Code/1.0",
                )
                return await arecord_mcp_tool_call("list_documents", success=True)

        self._run(_test())
        props = mock_arecord.call_args[0][1]
        self.assertEqual(props["user_agent"], "Claude-Code/1.0")


class TestUserAgentTruncation(TestCase):
    """Tests for User-Agent length bounding."""

    def tearDown(self):
        clear_request_context()

    def test_set_request_context_truncates_long_user_agent(self):
        long_ua = "A" * (MAX_USER_AGENT_LENGTH + 500)
        set_request_context(client_ip="1.2.3.4", transport="http", user_agent=long_ua)
        ctx = _get_request_context()
        self.assertEqual(len(ctx["user_agent"]), MAX_USER_AGENT_LENGTH)

    def test_set_request_context_preserves_short_user_agent(self):
        short_ua = "Claude-Code/1.0"
        set_request_context(client_ip="1.2.3.4", transport="http", user_agent=short_ua)
        ctx = _get_request_context()
        self.assertEqual(ctx["user_agent"], short_ua)

    def test_set_request_context_empty_string_user_agent(self):
        set_request_context(client_ip="1.2.3.4", transport="http", user_agent="")
        ctx = _get_request_context()
        self.assertIsNone(ctx["user_agent"])

    def test_get_user_agent_from_scope_truncates_long_value(self):
        long_ua = ("B" * (MAX_USER_AGENT_LENGTH + 1000)).encode()
        scope = {"headers": [(b"user-agent", long_ua)]}
        result = get_user_agent_from_scope(scope)
        self.assertEqual(len(result), MAX_USER_AGENT_LENGTH)

    def test_get_user_agent_from_scope_preserves_short_value(self):
        scope = {"headers": [(b"user-agent", b"cursor/0.45")]}
        result = get_user_agent_from_scope(scope)
        self.assertEqual(result, "cursor/0.45")


class TestEmptySlugFiltering(TestCase):
    """Tests that empty-string slugs are excluded from telemetry properties."""

    def tearDown(self):
        clear_request_context()

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_empty_corpus_slug_omitted(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            record_mcp_tool_call("test", success=True, corpus_slug="")
        props = mock_record.call_args[0][1]
        self.assertNotIn("corpus_slug", props)

    @patch("opencontractserver.mcp.telemetry.record_event")
    def test_empty_document_slug_omitted(self, mock_record):
        mock_record.return_value = True
        with isolated_telemetry_context():
            record_mcp_resource_read("corpus", success=True, document_slug="")
        props = mock_record.call_args[0][1]
        self.assertNotIn("document_slug", props)

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_async_empty_corpus_slug_omitted(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                return await arecord_mcp_tool_call("test", success=True, corpus_slug="")

        asyncio.run(_test())
        props = mock_arecord.call_args[0][1]
        self.assertNotIn("corpus_slug", props)

    @patch("opencontractserver.mcp.telemetry.arecord_event")
    def test_async_empty_document_slug_omitted(self, mock_arecord):
        async def _test():
            mock_arecord.return_value = True
            with isolated_telemetry_context():
                return await arecord_mcp_resource_read(
                    "corpus", success=True, document_slug=""
                )

        asyncio.run(_test())
        props = mock_arecord.call_args[0][1]
        self.assertNotIn("document_slug", props)


class TestGetUserAgentFromScope(TestCase):
    """Tests for extracting User-Agent from ASGI scope."""

    def test_user_agent_present(self):
        scope = {"headers": [(b"user-agent", b"Claude-Code/1.0")]}
        result = get_user_agent_from_scope(scope)
        self.assertEqual(result, "Claude-Code/1.0")

    def test_user_agent_missing(self):
        scope = {"headers": [(b"content-type", b"application/json")]}
        result = get_user_agent_from_scope(scope)
        self.assertIsNone(result)

    def test_empty_headers(self):
        scope = {"headers": []}
        result = get_user_agent_from_scope(scope)
        self.assertIsNone(result)

    def test_empty_scope(self):
        result = get_user_agent_from_scope({})
        self.assertIsNone(result)

    def test_user_agent_whitespace_stripped(self):
        scope = {"headers": [(b"user-agent", b"  cursor/0.45  ")]}
        result = get_user_agent_from_scope(scope)
        self.assertEqual(result, "cursor/0.45")


class TestGetClientIpFromScope(TestCase):
    """Tests for extracting client IP from ASGI scope."""

    def test_x_forwarded_for_single(self):
        scope = {"headers": [(b"x-forwarded-for", b"1.2.3.4")]}
        result = get_claimed_client_ip_from_scope(scope)
        self.assertEqual(result, "1.2.3.4")

    def test_x_forwarded_for_multiple(self):
        scope = {"headers": [(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8, 9.10.11.12")]}
        result = get_claimed_client_ip_from_scope(scope)
        self.assertEqual(result, "1.2.3.4")

    def test_x_real_ip(self):
        scope = {"headers": [(b"x-real-ip", b"10.0.0.1")]}
        result = get_claimed_client_ip_from_scope(scope)
        self.assertEqual(result, "10.0.0.1")

    def test_x_forwarded_for_takes_precedence(self):
        scope = {
            "headers": [
                (b"x-forwarded-for", b"1.2.3.4"),
                (b"x-real-ip", b"5.6.7.8"),
            ]
        }
        result = get_claimed_client_ip_from_scope(scope)
        self.assertEqual(result, "1.2.3.4")

    def test_direct_client_connection(self):
        scope = {"headers": [], "client": ("192.168.1.1", 12345)}
        result = get_claimed_client_ip_from_scope(scope)
        self.assertEqual(result, "192.168.1.1")

    def test_no_ip_available(self):
        scope = {"headers": []}
        result = get_claimed_client_ip_from_scope(scope)
        self.assertIsNone(result)

    def test_empty_scope(self):
        result = get_claimed_client_ip_from_scope({})
        self.assertIsNone(result)


# --------------------------------------------------------------------------
# TTLLRUCache tests
# --------------------------------------------------------------------------
class TestTTLLRUCache(TestCase):
    """Tests for the TTLLRUCache async cache implementation."""

    def _run(self, coro):
        """Helper to run async code in tests."""
        return asyncio.run(coro)

    def test_set_and_get(self):
        cache = TTLLRUCache(maxsize=10, ttl_seconds=60)

        async def _test():
            await cache.set("key1", "value1")
            result = await cache.get("key1")
            return result

        result = self._run(_test())
        self.assertEqual(result, "value1")

    def test_get_missing_key(self):
        cache = TTLLRUCache(maxsize=10, ttl_seconds=60)

        async def _test():
            return await cache.get("nonexistent")

        result = self._run(_test())
        self.assertIsNone(result)

    def test_remove(self):
        cache = TTLLRUCache(maxsize=10, ttl_seconds=60)

        async def _test():
            await cache.set("key1", "value1")
            removed = await cache.remove("key1")
            after = await cache.get("key1")
            return removed, after

        removed, after = self._run(_test())
        self.assertTrue(removed)
        self.assertIsNone(after)

    def test_remove_nonexistent(self):
        cache = TTLLRUCache(maxsize=10, ttl_seconds=60)

        async def _test():
            return await cache.remove("nonexistent")

        result = self._run(_test())
        self.assertFalse(result)

    def test_clear(self):
        cache = TTLLRUCache(maxsize=10, ttl_seconds=60)

        async def _test():
            await cache.set("k1", "v1")
            await cache.set("k2", "v2")
            await cache.clear()
            r1 = await cache.get("k1")
            r2 = await cache.get("k2")
            return r1, r2

        r1, r2 = self._run(_test())
        self.assertIsNone(r1)
        self.assertIsNone(r2)

    def test_ttl_expiration(self):
        cache = TTLLRUCache(maxsize=10, ttl_seconds=0.05)

        async def _test():
            await cache.set("key1", "value1")
            await asyncio.sleep(0.5)
            return await cache.get("key1")

        result = self._run(_test())
        self.assertIsNone(result)

    def test_lru_eviction(self):
        cache = TTLLRUCache(maxsize=2, ttl_seconds=60)

        async def _test():
            await cache.set("k1", "v1")
            await cache.set("k2", "v2")
            await cache.set("k3", "v3")  # Should evict k1
            r1 = await cache.get("k1")
            r3 = await cache.get("k3")
            return r1, r3

        r1, r3 = self._run(_test())
        self.assertIsNone(r1)  # Evicted
        self.assertEqual(r3, "v3")

    def test_overwrite_existing_key(self):
        cache = TTLLRUCache(maxsize=10, ttl_seconds=60)

        async def _test():
            await cache.set("key1", "old")
            await cache.set("key1", "new")
            return await cache.get("key1")

        result = self._run(_test())
        self.assertEqual(result, "new")

    def test_len(self):
        cache = TTLLRUCache(maxsize=10, ttl_seconds=60)

        async def _test():
            await cache.set("k1", "v1")
            await cache.set("k2", "v2")
            return len(cache)

        result = self._run(_test())
        self.assertEqual(result, 2)


# --------------------------------------------------------------------------
# RateLimiter tests (now using shared engine)
# --------------------------------------------------------------------------
class TestRateLimiter(TestCase):
    """Tests for MCP rate limiting via the shared config.ratelimit engine."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    @override_settings(RATELIMIT_DISABLE=False)
    def test_allows_under_limit(self):
        from config.ratelimit.engine import is_rate_limited

        with patch("config.ratelimit.engine.time") as mock_time:
            mock_time.time.return_value = 1000000.0
            for _ in range(5):
                self.assertFalse(is_rate_limited("mcp:test", "client1", "5/m"))

    @override_settings(RATELIMIT_DISABLE=False)
    def test_blocks_over_limit(self):
        from config.ratelimit.engine import is_rate_limited

        with patch("config.ratelimit.engine.time") as mock_time:
            mock_time.time.return_value = 1000000.0
            for _ in range(3):
                is_rate_limited("mcp:test", "client1", "3/m")
            self.assertTrue(is_rate_limited("mcp:test", "client1", "3/m"))

    @override_settings(RATELIMIT_DISABLE=False)
    def test_different_clients_independent(self):
        from config.ratelimit.engine import is_rate_limited

        with patch("config.ratelimit.engine.time") as mock_time:
            mock_time.time.return_value = 1000000.0
            for _ in range(2):
                is_rate_limited("mcp:test", "client1", "2/m")
            # client1 is at limit
            self.assertTrue(is_rate_limited("mcp:test", "client1", "2/m"))
            # client2 should still be allowed
            self.assertFalse(is_rate_limited("mcp:test", "client2", "2/m"))


# --------------------------------------------------------------------------
# Config tests
# --------------------------------------------------------------------------
class TestMcpConfig(TestCase):
    """Tests for MCP config module."""

    def test_constants(self):
        self.assertGreater(MAX_RESULTS_PER_PAGE, 0)
        self.assertGreater(DEFAULT_PAGE_SIZE, 0)
        self.assertLessEqual(DEFAULT_PAGE_SIZE, MAX_RESULTS_PER_PAGE)
        self.assertGreater(RATE_LIMIT_REQUESTS, 0)
        self.assertGreater(RATE_LIMIT_WINDOW, 0)
        self.assertGreater(CACHE_TTL, 0)

    def test_slug_pattern(self):
        self.assertTrue(SLUG_PATTERN.match("valid-slug-123"))
        self.assertFalse(SLUG_PATTERN.match("invalid slug!"))
        self.assertFalse(SLUG_PATTERN.match(""))

    def test_validate_slug_valid(self):
        self.assertTrue(validate_slug("my-corpus"))
        self.assertTrue(validate_slug("ABC-123"))

    def test_validate_slug_invalid(self):
        self.assertFalse(validate_slug("has spaces"))
        self.assertFalse(validate_slug("special@chars"))
        self.assertFalse(validate_slug(""))

    @override_settings(MCP_SERVER={"MAX_RESULTS_PER_PAGE": 200})
    def test_get_mcp_setting_from_settings(self):
        result = get_mcp_setting("MAX_RESULTS_PER_PAGE")
        self.assertEqual(result, 200)

    def test_get_mcp_setting_default(self):
        result = get_mcp_setting("NONEXISTENT_KEY", default=42)
        self.assertEqual(result, 42)

    def test_get_mcp_setting_no_settings(self):
        result = get_mcp_setting("SOME_KEY")
        self.assertIsNone(result)


# --------------------------------------------------------------------------
# Permissions tests
# --------------------------------------------------------------------------
class TestMcpPermissions(TestCase):
    """Tests for MCP permissions module."""

    def test_validate_slug_valid(self):
        self.assertTrue(perm_validate_slug("valid-slug"))

    def test_validate_slug_invalid(self):
        self.assertFalse(perm_validate_slug("invalid slug"))

    def test_sanitize_and_validate_slugs_valid(self):
        corpus, doc = sanitize_and_validate_slugs("my-corpus", "my-doc")
        self.assertEqual(corpus, "my-corpus")
        self.assertEqual(doc, "my-doc")

    def test_sanitize_and_validate_slugs_corpus_only(self):
        corpus, doc = sanitize_and_validate_slugs("my-corpus")
        self.assertEqual(corpus, "my-corpus")
        self.assertIsNone(doc)

    def test_sanitize_and_validate_slugs_invalid_corpus(self):
        with self.assertRaises(ValueError) as ctx:
            sanitize_and_validate_slugs("invalid slug!")
        self.assertIn("corpus", str(ctx.exception).lower())

    def test_sanitize_and_validate_slugs_invalid_document(self):
        with self.assertRaises(ValueError) as ctx:
            sanitize_and_validate_slugs("valid-corpus", "invalid doc!")
        self.assertIn("document", str(ctx.exception).lower())

    def test_get_anonymous_user(self):
        user = get_anonymous_user()
        self.assertTrue(user.is_anonymous)


# --------------------------------------------------------------------------
# Formatter tests
# --------------------------------------------------------------------------
class TestFormatCorpusSummary(TestCase):
    """Tests for format_corpus_summary formatter."""

    def test_basic_format(self):
        corpus = MagicMock()
        corpus.slug = "test-corpus"
        corpus.title = "Test Corpus"
        corpus.description = "A test corpus"
        corpus.created = MagicMock()
        corpus.created.isoformat.return_value = "2025-01-01T00:00:00"
        corpus.document_count.return_value = 5

        result = format_corpus_summary(corpus)
        self.assertEqual(result["slug"], "test-corpus")
        self.assertEqual(result["title"], "Test Corpus")
        self.assertEqual(result["description"], "A test corpus")
        self.assertEqual(result["document_count"], 5)
        self.assertEqual(result["created"], "2025-01-01T00:00:00")

    def test_none_description(self):
        corpus = MagicMock()
        corpus.slug = "s"
        corpus.title = "T"
        corpus.description = None
        corpus.created = None
        corpus.document_count.return_value = 0

        result = format_corpus_summary(corpus)
        self.assertEqual(result["description"], "")
        self.assertIsNone(result["created"])

    def test_no_document_count_method(self):
        corpus = MagicMock(spec=[])
        corpus.slug = "s"
        corpus.title = "T"
        corpus.description = ""
        corpus.created = None

        result = format_corpus_summary(corpus)
        self.assertEqual(result["document_count"], 0)


class TestFormatDocumentSummary(TestCase):
    """Tests for format_document_summary formatter."""

    def test_basic_format(self):
        doc = MagicMock()
        doc.slug = "test-doc"
        doc.title = "Test Doc"
        doc.description = "A test document"
        doc.page_count = 10
        doc.file_type = "application/pdf"
        doc.created = MagicMock()
        doc.created.isoformat.return_value = "2025-01-01T00:00:00"

        result = format_document_summary(doc)
        self.assertEqual(result["slug"], "test-doc")
        self.assertEqual(result["title"], "Test Doc")
        self.assertEqual(result["page_count"], 10)
        self.assertEqual(result["file_type"], "application/pdf")

    def test_none_values(self):
        doc = MagicMock()
        doc.slug = "s"
        doc.title = None
        doc.description = None
        doc.page_count = None
        doc.file_type = None
        doc.created = None

        result = format_document_summary(doc)
        self.assertEqual(result["title"], "")
        self.assertEqual(result["description"], "")
        self.assertEqual(result["page_count"], 0)
        self.assertEqual(result["file_type"], "unknown")
        self.assertIsNone(result["created"])


class TestFormatAnnotation(TestCase):
    """Tests for format_annotation formatter."""

    def test_with_label(self):
        annotation = MagicMock()
        annotation.id = 42
        annotation.page = 3
        annotation.raw_text = "sample text"
        annotation.structural = False
        annotation.created = MagicMock()
        annotation.created.isoformat.return_value = "2025-01-01T00:00:00"
        annotation.annotation_label.text = "Important"
        annotation.annotation_label.color = "#FF0000"
        annotation.annotation_label.label_type = "TOKEN_LABEL"

        result = format_annotation(annotation)
        self.assertEqual(result["id"], "42")
        self.assertEqual(result["page"], 3)
        self.assertEqual(result["raw_text"], "sample text")
        self.assertFalse(result["structural"])
        self.assertEqual(result["annotation_label"]["text"], "Important")
        self.assertEqual(result["annotation_label"]["label_type"], "TOKEN_LABEL")
        # Lean AI-facing payload deliberately omits ``color`` (low signal,
        # high token cost). See format_annotation docstring.
        self.assertNotIn("color", result["annotation_label"])

    def test_without_label(self):
        annotation = MagicMock()
        annotation.id = 1
        annotation.page = 1
        annotation.raw_text = None
        annotation.annotation_label = None
        annotation.structural = True
        annotation.created = None

        result = format_annotation(annotation)
        self.assertIsNone(result["annotation_label"])
        self.assertEqual(result["raw_text"], "")
        self.assertTrue(result["structural"])

    def test_label_omits_color(self):
        """The lean payload exposes label text/type but never ``color``."""
        annotation = MagicMock()
        annotation.id = 1
        annotation.page = 1
        annotation.raw_text = "text"
        annotation.structural = False
        annotation.created = None
        annotation.annotation_label.text = "Label"
        annotation.annotation_label.color = None
        annotation.annotation_label.label_type = "TOKEN_LABEL"

        result = format_annotation(annotation)
        self.assertEqual(result["annotation_label"]["text"], "Label")
        self.assertEqual(result["annotation_label"]["label_type"], "TOKEN_LABEL")
        self.assertNotIn("color", result["annotation_label"])


class TestFormatThreadSummary(TestCase):
    """Tests for format_thread_summary formatter."""

    def test_basic_format(self):
        thread = MagicMock()
        thread.id = 10
        thread.title = "Discussion"
        thread.description = "About something"
        thread.message_count = 5
        thread.is_pinned = True
        thread.is_locked = False
        thread.created = MagicMock()
        thread.created.isoformat.return_value = "2025-01-01"
        thread.modified = MagicMock()
        thread.modified.isoformat.return_value = "2025-01-02"

        result = format_thread_summary(thread)
        self.assertEqual(result["id"], "10")
        self.assertEqual(result["title"], "Discussion")
        self.assertEqual(result["message_count"], 5)
        self.assertTrue(result["is_pinned"])
        self.assertFalse(result["is_locked"])

    def test_none_values(self):
        thread = MagicMock()
        thread.id = 1
        thread.title = None
        thread.description = None
        thread.is_pinned = False
        thread.is_locked = False
        thread.created = None
        thread.modified = None
        # message_count is accessed via getattr with default
        del thread.message_count

        result = format_thread_summary(thread)
        self.assertEqual(result["title"], "")
        self.assertEqual(result["description"], "")
        self.assertEqual(result["message_count"], 0)


class TestFormatMessage(TestCase):
    """Tests for format_message formatter."""

    def test_basic_format(self):
        msg = MagicMock()
        msg.id = 100
        msg.content = "Hello, world!"
        msg.msg_type = "human"
        msg.created_at = MagicMock()
        msg.created_at.isoformat.return_value = "2025-01-01T12:00:00"
        msg.upvote_count = 3
        msg.downvote_count = 1

        result = format_message(msg)
        self.assertEqual(result["id"], "100")
        self.assertEqual(result["content"], "Hello, world!")
        self.assertEqual(result["msg_type"], "human")
        self.assertEqual(result["upvote_count"], 3)
        self.assertEqual(result["downvote_count"], 1)


class TestFormatMessageWithReplies(TestCase):
    """Tests for format_message_with_replies recursive formatter."""

    def _make_msg(self, msg_id, content, replies=None):
        msg = MagicMock()
        msg.id = msg_id
        msg.content = content
        msg.msg_type = "human"
        msg.created_at = None
        msg.upvote_count = 0
        msg.downvote_count = 0

        if replies is not None:
            msg.replies.all.return_value = replies
        else:
            msg.replies.all.return_value = []

        return msg

    def test_no_replies(self):
        msg = self._make_msg(1, "Hello")
        result = format_message_with_replies(msg, user=None)
        self.assertEqual(result["id"], "1")
        self.assertEqual(result["replies"], [])

    def test_with_replies(self):
        reply = self._make_msg(2, "Reply")
        msg = self._make_msg(1, "Parent", replies=[reply])
        result = format_message_with_replies(msg, user=None)
        self.assertEqual(len(result["replies"]), 1)
        self.assertEqual(result["replies"][0]["content"], "Reply")

    def test_max_depth_limits_recursion(self):
        deep_reply = self._make_msg(3, "Deep")
        deep_reply.replies.exists.return_value = True

        reply = self._make_msg(2, "Reply", replies=[deep_reply])
        msg = self._make_msg(1, "Parent", replies=[reply])

        result = format_message_with_replies(msg, user=None, max_depth=2)
        # depth 0: msg, depth 1: reply, depth 2: should stop
        deep_result = result["replies"][0]["replies"][0]
        self.assertEqual(deep_result["replies"], [])
        self.assertTrue(deep_result["has_more_replies"])


# --------------------------------------------------------------------------
# URI Parser extended tests
# --------------------------------------------------------------------------
class TestURIParserExtended(TestCase):
    """Extended tests for URIParser edge cases."""

    def test_corpus_with_numbers(self):
        result = URIParser.parse_corpus("corpus://my-corpus-123")
        self.assertEqual(result, "my-corpus-123")

    def test_corpus_case_sensitive(self):
        result = URIParser.parse_corpus("corpus://MyCorpus")
        self.assertEqual(result, "MyCorpus")

    def test_document_valid(self):
        result = URIParser.parse_document("document://corp/doc")
        self.assertEqual(result, ("corp", "doc"))

    def test_annotation_valid(self):
        result = URIParser.parse_annotation("annotation://corp/doc/42")
        self.assertEqual(result, ("corp", "doc", 42))

    def test_thread_valid(self):
        result = URIParser.parse_thread("thread://corp/threads/7")
        self.assertEqual(result, ("corp", 7))

    def test_invalid_uri_scheme(self):
        self.assertIsNone(URIParser.parse_corpus("http://my-corpus"))

    def test_empty_slug(self):
        self.assertIsNone(URIParser.parse_corpus("corpus://"))

    def test_document_missing_doc_slug(self):
        self.assertIsNone(URIParser.parse_document("document://corp"))

    def test_annotation_missing_id(self):
        self.assertIsNone(URIParser.parse_annotation("annotation://corp/doc"))

    def test_annotation_non_numeric_id(self):
        self.assertIsNone(URIParser.parse_annotation("annotation://corp/doc/abc"))

    def test_thread_non_numeric_id(self):
        self.assertIsNone(URIParser.parse_thread("thread://corp/threads/abc"))

    def test_corpus_with_path_traversal(self):
        self.assertIsNone(URIParser.parse_corpus("corpus://../../etc/passwd"))

    def test_corpus_with_special_chars(self):
        self.assertIsNone(URIParser.parse_corpus("corpus://test<script>"))


class TestAnyUrlCustomSchemes(TestCase):
    """Pin the contract that pydantic's ``AnyUrl`` accepts the custom URI
    schemes the MCP server emits when listing resources (``corpus://``,
    ``document://`` and ``thread://``). Pre-#1486 the resource-uri payload
    used plain strings; the typing graduation introduces ``AnyUrl(...)``
    construction at three call sites in ``mcp/server.py``. If pydantic
    ever tightens its URI validation, this test fails immediately rather
    than producing a runtime error during a live MCP ``list_resources``
    call.
    """

    def test_corpus_uri_constructs(self) -> None:
        from pydantic import AnyUrl

        url = AnyUrl("corpus://my-corpus-slug")
        self.assertEqual(str(url), "corpus://my-corpus-slug")

    def test_document_uri_constructs(self) -> None:
        from pydantic import AnyUrl

        url = AnyUrl("document://my-corpus/my-doc")
        self.assertEqual(str(url), "document://my-corpus/my-doc")

    def test_thread_uri_constructs(self) -> None:
        from pydantic import AnyUrl

        url = AnyUrl("thread://my-corpus/threads/42")
        self.assertEqual(str(url), "thread://my-corpus/threads/42")

    def test_corpus_uri_with_uuid_slug(self) -> None:
        """Real-world slug shapes (uuid-y, dotted, hyphenated) — they all
        live under the ``[a-z0-9-]`` slug regex enforced upstream and
        must remain accepted by AnyUrl."""
        from pydantic import AnyUrl

        url = AnyUrl("corpus://abc-123-def-4567")
        self.assertEqual(str(url), "corpus://abc-123-def-4567")
