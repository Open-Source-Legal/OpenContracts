"""
Integration test settings that use real Redis backends.

These settings inherit from test.py but override the three in-memory backends
(cache, channels, Celery) to point at the real Redis instance in test.yml.

Usage:
    docker compose -f test.yml run \
      -e DJANGO_SETTINGS_MODULE=config.settings.test_integration \
      django pytest opencontractserver/tests/test_redis_integration.py -v
"""

from typing import Any

from .test import *  # noqa
from .test import env

# Redis
# ------------------------------------------------------------------------------
# Re-read from env (test.py overrides to in-memory, we want real Redis)
REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

# Cache — real django-redis instead of LocMemCache
# ------------------------------------------------------------------------------
_caches: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "test_integration",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}
CACHES = _caches

# Channels — real Redis instead of InMemoryChannelLayer
# ------------------------------------------------------------------------------
# Use a dict host (not a bare URL string) so socket_timeout can be set.
# redis-py 8.0 defaults socket_timeout to 5s, which makes channels-redis'
# 5s idle blocking pop time out client-side and crash the consumer (the 1011
# reconnect churn in #1886). Mirror the base.py fix so integration tests run
# against the corrected config (and so test_redis_integration's idle-receive
# regression test exercises it). socket_timeout=None disables the client read
# deadline for these long-lived idle channel-layer reads. See issue #1886.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [{"address": REDIS_URL, "socket_timeout": None}],
        },
    },
}

# Celery — real Redis broker instead of memory://
# ------------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
