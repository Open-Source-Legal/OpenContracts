"""
With these settings, tests run faster.
"""

from .base import *  # noqa
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="q1JMhn0BHYv6DB4QTeSuvO06R3cMWn362D3DJhnNqSO3CO9z4aMbPqPgd8yKUNf8",
)

# Database
# ------------------------------------------------------------------------------
# Update database connection settings for tests
DATABASES["default"]["CONN_MAX_AGE"] = 0  # Disable connection pooling
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["OPTIONS"] = {
    **DATABASES["default"].get("OPTIONS", {}),
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 5,
    "keepalives_count": 5,
}
DATABASES["default"]["TEST"] = {
    **DATABASES["default"].get("TEST", {}),
    # pytest-xdist creates worker-specific databases automatically (test_db_gw0, test_db_gw1, etc.)
}

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES[-1]["OPTIONS"]["loaders"] = [  # type: ignore[index] # noqa F405
    (
        "django.template.loaders.cached.Loader",
        [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ],
    )
]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Celery
# ------------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache"
CELERY_CACHE_BACKEND = "memory"

# Need these values for testing (even though they are not used)
# https://django-storages.readthedocs.io/en/latest/#installation
INSTALLED_APPS += ["storages"]  # noqa F405
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#settings
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="dummy-key")
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#settings
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="dummy-secret")
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#settings
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="dummy-bucket")
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#settings
AWS_QUERYSTRING_AUTH = True
# DO NOT change these unless you know what you're doing.
_AWS_EXPIRY = 60 * 60 * 24 * 7
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#settings
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": f"max-age={_AWS_EXPIRY}, s-maxage={_AWS_EXPIRY}, must-revalidate"
}
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#settings
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default=None)
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#cloudfront
AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default=None)
aws_s3_domain = AWS_S3_CUSTOM_DOMAIN or f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"

# Test redis setup
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Cache configuration for tests
# Use LocMemCache for tests to ensure proper isolation between test methods
# Note: This means rate limiting tests won't test Redis integration, but they will
# test the rate limiting logic correctly
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-test-cache",
    }
}

# Rate limiting
# ------------------------------------------------------------------------------
# Disable rate limiting by default in tests for performance
# Individual tests can enable it with @override_settings(RATELIMIT_DISABLE=False)
RATELIMIT_DISABLE = True

# STORAGES
# ------------------------------------------------------------------------------
# Use simple static files storage that doesn't require manifest
# This avoids "Missing staticfiles manifest entry" errors in admin tests
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Telemetry
# ------------------------------------------------------------------------------
# Explicitly disable telemetry in tests to prevent polluting PostHog with test data
MODE = "TEST"
TELEMETRY_ENABLED = False

# Embedder settings for tests
# ------------------------------------------------------------------------------
# Use fast TestEmbedder by default for all tests. This avoids HTTP calls to
# the vector-embedder microservice and makes tests run ~2x faster.
#
# Integration tests that need to verify actual service connectivity should
# explicitly instantiate the real embedder class (e.g., MicroserviceEmbedder).
#
# Intentionally env-overridable: benchmark runs via the test.yml compose
# stack (see opencontractserver/benchmarks/) need to swap in a real embedder
# at runtime without editing settings.
#
# Footgun guard (issue #1410): the override only takes effect when the
# explicit ``BENCHMARK_MODE`` env var is also set. Without this guard, any
# stray ``DEFAULT_EMBEDDER`` value in CI's environment would silently push
# the regular test suite onto a real embedder and start making live
# network calls. Forcing operators to set ``BENCHMARK_MODE=1`` makes the
# escape hatch deliberate.
_OC_TEST_EMBEDDER_DEFAULT = (
    "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder"
)
if env.bool("BENCHMARK_MODE", default=False):
    DEFAULT_EMBEDDER = env("DEFAULT_EMBEDDER", default=_OC_TEST_EMBEDDER_DEFAULT)
else:
    DEFAULT_EMBEDDER = _OC_TEST_EMBEDDER_DEFAULT

# Auth0 settings for tests
# ------------------------------------------------------------------------------
# These are required for importing Auth0 modules even if USE_AUTH0 is False.
# They are only used if USE_AUTH0 is True in the test environment.
AUTH0_CLIENT_ID = env("AUTH0_CLIENT_ID", default="test-client-id")
AUTH0_API_AUDIENCE = env("AUTH0_API_AUDIENCE", default="test-audience")
AUTH0_DOMAIN = env("AUTH0_DOMAIN", default="test.auth0.com")
AUTH0_M2M_MANAGEMENT_API_SECRET = env(
    "AUTH0_M2M_MANAGEMENT_API_SECRET", default="test-secret"
)
AUTH0_M2M_MANAGEMENT_API_ID = env("AUTH0_M2M_MANAGEMENT_API_ID", default="test-api-id")
AUTH0_M2M_MANAGEMENT_GRANT_TYPE = env(
    "AUTH0_M2M_MANAGEMENT_GRANT_TYPE", default="client_credentials"
)

# Silence the AUTH0_SUPERUSER_SUB_ALLOWLIST emptiness warning during tests.
# Individual tests that exercise the allowlist behaviour override
# ``AUTH0_SUPERUSER_SUB_ALLOWLIST`` explicitly via ``override_settings``; the
# system check is only useful at production startup.
#
# Note: ``TestAuth0SuperuserAllowlistSystemCheck`` calls
# ``check_auth0_superuser_allowlist`` directly rather than going through
# Django's check runner, so it bypasses this silencing and verifies the
# warning is emitted under USE_AUTH0=True with an empty allowlist. The
# silencing here only suppresses the warning during normal test startup.
SILENCED_SYSTEM_CHECKS = ["users.W001", "users.E001"]
