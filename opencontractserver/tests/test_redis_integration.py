"""
Redis integration tests for django-redis, channels-redis, and Celery.

These tests require a real Redis instance (provided by test.yml) and must be run
with DJANGO_SETTINGS_MODULE=config.settings.test_integration.

WARNING: These tests use flushdb() for isolation and are NOT safe to run with
pytest-xdist parallel workers (-n). They are marked @pytest.mark.serial to
prevent parallel execution. The CI workflow runs them without -n.

Run:
    docker compose -f test.yml run \
      -e DJANGO_SETTINGS_MODULE=config.settings.test_integration \
      django pytest opencontractserver/tests/test_redis_integration.py -v
"""

import asyncio
import time

import pytest
from asgiref.sync import async_to_sync
from celery.result import AsyncResult
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase
from django_redis import get_redis_connection

from config.celery_app import app as celery_app

# Skip entire module when running under standard test.py settings (which use
# LocMemCache). These tests require config.settings.test_integration with real
# Redis backends. Without this guard, get_redis_connection() would fail during
# normal pytest discovery.
#
# Also mark serial: these tests use flushdb() which is not safe under
# pytest-xdist parallel workers.
pytestmark = [
    pytest.mark.skipif(
        "django_redis" not in settings.CACHES.get("default", {}).get("BACKEND", ""),
        reason="Requires DJANGO_SETTINGS_MODULE=config.settings.test_integration",
    ),
    pytest.mark.serial,
]


def _flush_redis():
    """Flush the Redis test DB to ensure isolation between tests."""
    conn = get_redis_connection("default")
    conn.flushdb()


class TestDjangoRedisCache(TestCase):
    """Test django-redis cache backend against a real Redis instance.

    Validates that cache operations work correctly with the current redis-py
    version, particularly under RESP3 protocol where return types changed
    (dicts instead of flat lists, sets instead of lists, etc.).
    """

    def setUp(self):
        _flush_redis()

    def tearDown(self):
        _flush_redis()

    def test_cache_set_get_string(self):
        """String round-trip through django-redis."""
        cache.set("test_key", "test_value", timeout=30)
        result = cache.get("test_key")
        assert result == "test_value"

    def test_cache_set_get_dict(self):
        """Dict serialization round-trip — sensitive to RESP3 type changes."""
        data = {"name": "test", "count": 42, "nested": {"a": 1}}
        cache.set("test_dict", data, timeout=30)
        result = cache.get("test_dict")
        assert result == data
        assert isinstance(result, dict)

    def test_cache_set_get_list(self):
        """List serialization round-trip — sensitive to RESP3 type changes."""
        data = [1, "two", 3.0, None, {"nested": True}]
        cache.set("test_list", data, timeout=30)
        result = cache.get("test_list")
        assert result == data
        assert isinstance(result, list)

    def test_cache_delete(self):
        """Key deletion."""
        cache.set("delete_me", "value", timeout=30)
        assert cache.get("delete_me") == "value"
        cache.delete("delete_me")
        assert cache.get("delete_me") is None

    def test_cache_ttl_expiry(self):
        """TTL-based expiration."""
        cache.set("expiring_key", "value", timeout=1)
        assert cache.get("expiring_key") == "value"
        # Sleep 3s for a 1s TTL: generous margin avoids flaky failures on
        # slow CI runners where Redis expiry checks may lag.
        time.sleep(3.0)
        assert cache.get("expiring_key") is None

    def test_cache_incr_decr(self):
        """Atomic increment/decrement — used by rate limiting."""
        cache.set("counter", 10, timeout=30)
        new_val = cache.incr("counter")
        assert new_val == 11
        new_val = cache.decr("counter")
        assert new_val == 10


class TestChannelsRedisLayer(TestCase):
    """Test channels-redis channel layer against a real Redis instance.

    Validates that WebSocket pub/sub operations work correctly with the
    current redis-py version. The notification broadcast path
    (signals.py -> group_send) relies on this layer.

    Channel layer uses default expiry (60s) and capacity (100 messages),
    which are adequate for these correctness tests.
    """

    # Timeout for receive calls. Without this, a dropped message would cause
    # the test to hang for the full channel expiry (60s). The 15-minute CI
    # timeout would eventually catch it, but a 5s timeout gives a faster,
    # more informative TimeoutError.
    RECEIVE_TIMEOUT_SECONDS = 5.0

    def setUp(self):
        _flush_redis()
        self.channel_layer = get_channel_layer()

    def tearDown(self):
        _flush_redis()

    def _timed_receive(self, channel_name):
        """Receive with a timeout to prevent hanging on dropped messages."""

        async def _receive():
            return await asyncio.wait_for(
                self.channel_layer.receive(channel_name),
                timeout=self.RECEIVE_TIMEOUT_SECONDS,
            )

        return async_to_sync(_receive)()

    def _timed_receive_or_none(self, channel_name, timeout=2.0):
        """Receive with a timeout, returning None if nothing arrives.

        Unlike _timed_receive which raises on timeout, this returns None --
        useful for asserting that no message was delivered.
        """

        async def _receive():
            try:
                return await asyncio.wait_for(
                    self.channel_layer.receive(channel_name),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                return None

        return async_to_sync(_receive)()

    def test_send_receive(self):
        """Basic channel send/receive round-trip."""
        channel_name = async_to_sync(self.channel_layer.new_channel)()
        message = {"type": "test.message", "text": "hello"}

        async_to_sync(self.channel_layer.send)(channel_name, message)
        received = self._timed_receive(channel_name)

        assert received["type"] == "test.message"
        assert received["text"] == "hello"

    def test_group_send_receive(self):
        """Group send/receive — mirrors the notification broadcast path.

        This is the exact pattern used in notifications/signals.py:
        group_add -> group_send -> receive
        """
        group_name = "test_notification_group"
        channel_name = async_to_sync(self.channel_layer.new_channel)()

        # Join group
        async_to_sync(self.channel_layer.group_add)(group_name, channel_name)

        # Send to group (mirrors broadcast_notification_via_websocket)
        message = {
            "type": "notification.message",
            "notification_type": "test",
            "data": {"id": 1, "text": "Test notification"},
        }
        async_to_sync(self.channel_layer.group_send)(group_name, message)

        # Receive from the channel
        received = self._timed_receive(channel_name)
        assert received["type"] == "notification.message"
        assert received["data"]["id"] == 1

        # Cleanup
        async_to_sync(self.channel_layer.group_discard)(group_name, channel_name)

    def test_group_discard(self):
        """After group_discard, messages are no longer received."""
        group_name = "test_discard_group"
        channel_name = async_to_sync(self.channel_layer.new_channel)()

        # Join, then leave
        async_to_sync(self.channel_layer.group_add)(group_name, channel_name)
        async_to_sync(self.channel_layer.group_discard)(group_name, channel_name)

        # Send to group
        async_to_sync(self.channel_layer.group_send)(
            group_name,
            {"type": "test.message", "text": "should not arrive"},
        )

        # Receive should timeout (nothing to receive after discard)
        result = self._timed_receive_or_none(channel_name)
        assert result is None


class TestCeleryRedisBackend(TestCase):
    """Test Celery broker connection and result backend against real Redis.

    Validates that Celery's Redis broker connectivity and result
    serialization/deserialization work correctly with redis-py 7.x.
    Tests the broker connection directly and exercises the result backend's
    store/retrieve path, which is the code path sensitive to RESP3 changes.

    These tests deliberately bypass actual task dispatch (no worker needed)
    by calling store_result() / AsyncResult() directly. This isolates the
    RESP3 serialization path without requiring a running Celery worker.
    """

    def setUp(self):
        _flush_redis()

    def tearDown(self):
        _flush_redis()

    def test_broker_connection(self):
        """Celery can connect to Redis as a message broker."""
        conn = celery_app.connection()
        conn.ensure_connection(max_retries=3)
        conn.close()

    def test_result_backend_string(self):
        """String result round-trip through Redis result backend."""
        task_id = "test-string-result"
        celery_app.backend.store_result(task_id, "hello", "SUCCESS")

        retrieved = AsyncResult(task_id, app=celery_app)
        assert retrieved.result == "hello"
        assert retrieved.status == "SUCCESS"

    def test_result_backend_dict(self):
        """Dict result round-trip — sensitive to RESP3 type changes."""
        task_id = "test-dict-result"
        data = {"status": "ok", "count": 42, "items": [1, 2, 3]}
        celery_app.backend.store_result(task_id, data, "SUCCESS")

        retrieved = AsyncResult(task_id, app=celery_app)
        assert isinstance(retrieved.result, dict)
        assert retrieved.result == data
        assert retrieved.result["items"] == [1, 2, 3]

    def test_result_backend_failure(self):
        """Failure state stored and retrieved correctly from Redis."""
        task_id = "test-failure-result"
        exc = ValueError("Intentional test failure")
        celery_app.backend.mark_as_failure(task_id, exc)

        retrieved = AsyncResult(task_id, app=celery_app)
        assert retrieved.status == "FAILURE"
        assert "Intentional test failure" in str(retrieved.result)

    def test_result_backend_status_lifecycle(self):
        """Status transitions persist correctly through Redis backend."""
        task_id = "test-lifecycle"

        # PENDING is the implicit state for tasks with no backend record
        result = AsyncResult(task_id, app=celery_app)
        assert result.status == "PENDING"

        # Transition to SUCCESS and verify round-trip
        celery_app.backend.store_result(task_id, 42, "SUCCESS")
        success = AsyncResult(task_id, app=celery_app)
        assert success.status == "SUCCESS"
        assert success.result == 42
