"""
Integration test settings that use real Redis backends.

These settings inherit from test.py but override the three in-memory backends
(cache, channels, Celery) to point at the real Redis instance in test.yml.

Usage:
    docker compose -f test.yml run \
      -e DJANGO_SETTINGS_MODULE=config.settings.test_integration \
      django pytest opencontractserver/tests/test_redis_integration.py -v
"""

from .test import *  # noqa
from .test import env

# Redis
# ------------------------------------------------------------------------------
# Re-read from env (test.py overrides to in-memory, we want real Redis)
REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

# Cache — real django-redis instead of LocMemCache
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "test_integration",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Channels — real Redis instead of InMemoryChannelLayer
# channels_redis supports URL strings directly in the hosts list.
# ------------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Celery — real Redis broker instead of memory://
# ------------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
