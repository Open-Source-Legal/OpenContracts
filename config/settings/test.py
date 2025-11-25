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
    "SERIALIZE": False,  # Speeds up tests
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

# STATIC FILES
# ------------------------------------------------------------------------------
# Use simple static files storage that doesn't require manifest
# This avoids "Missing staticfiles manifest entry" errors in admin tests
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Telemetry
# ------------------------------------------------------------------------------
MODE = "TEST"
