"""
Base settings to build other settings files upon.
"""

import pathlib
from datetime import timedelta
from pathlib import Path

import environ

ROOT_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
# opencontractserver/
APPS_DIR = ROOT_DIR / "opencontractserver"

env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=True)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(ROOT_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "0.0.0.0", "127.0.0.1"]
)

# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)

# Storage backend selection - choose between LOCAL, AWS, or GCP
STORAGE_BACKEND = env.str("STORAGE_BACKEND", default="LOCAL").upper()

# Validate storage backend choice
VALID_STORAGE_BACKENDS = ["LOCAL", "AWS", "GCP"]
if STORAGE_BACKEND not in VALID_STORAGE_BACKENDS:
    raise ValueError(
        f"Invalid STORAGE_BACKEND: {STORAGE_BACKEND}. "
        f"Must be one of: {', '.join(VALID_STORAGE_BACKENDS)}"
    )

# Legacy support: Map old USE_AWS env var to STORAGE_BACKEND if present
# This provides backward compatibility for existing deployments
if env.bool("USE_AWS", default=None) is not None:
    import warnings

    warnings.warn(
        "USE_AWS is deprecated. Please use STORAGE_BACKEND='AWS' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    if env.bool("USE_AWS", default=False):
        STORAGE_BACKEND = "AWS"

# Activate Open Contracts Analyzer Functionality
USE_ANALYZER = env.bool("USE_ANALYZER", False)
CALLBACK_ROOT_URL_FOR_ANALYZER = env.str("CALLBACK_ROOT_URL_FOR_ANALYZER", None)

# Allow Graphene Django Debug Toolbar middleware
# Default to False for performance - only enable when actually debugging
ALLOW_GRAPHQL_DEBUG = env.bool("ALLOW_GRAPHQL_DEBUG", default=False)

# Set max file upload size to 5 GB for large corpuses
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880000
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "UTC"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n
USE_L10N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(ROOT_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
host, port = REDIS_URL[:-2].split("://")[1].split(":")
ASGI_APPLICATION = "config.asgi.application"
try:
    from channels_redis.core import RedisChannelLayer  # noqa

    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [(host, int(port))],
            },
        },
    }
except ImportError:
    print(
        "channels_redis is not installed. Please install it with: pip install channels-redis"
    )

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "daphne",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.forms",
]

THIRD_PARTY_APPS = [
    "channels",
    "corsheaders",
    "django_filters",
    "graphene_django",
    "guardian",
    "crispy_forms",
    "crispy_bootstrap5",
    "django_celery_beat",
    "rest_framework",
    "rest_framework.authtoken",
    "tree_queries",
]

LOCAL_APPS = [
    "opencontractserver.users",
    "opencontractserver.documents",
    "opencontractserver.corpuses",
    "opencontractserver.annotations",
    "opencontractserver.analyzer",
    "opencontractserver.extracts",
    "opencontractserver.feedback",
    "opencontractserver.conversations",
    "opencontractserver.badges",
    "opencontractserver.notifications",
]

# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "opencontractserver.contrib.sites.migrations"}

# USER LIMITS (FOR USERS WITH IS_USAGE_CAPPED=True)
# ------------------------------------------------------------------------------
USAGE_CAPPED_USER_DOC_CAP_COUNT = env.int(
    "USAGE_CAPPED_USER_CORPUS_CAP_COUNT", default=10
)
USAGE_CAPPED_USER_CAN_USE_ANALYZERS = env.bool(
    "USAGE_CAPPED_USER_CAN_USE_ANALYZERS", default=True
)
USAGE_CAPPED_USER_CAN_IMPORT_CORPUS = env.bool(
    "USAGE_CAPPED_USER_CAN_IMPORT_CORPUS", default=False
)
USAGE_CAPPED_USER_CAN_EXPORT_CORPUS = env.bool(
    "USAGE_CAPPED_USER_CAN_EXPORT_CORPUS", default=True
)

# UPLOAD CONTROLS
# ------------------------------------------------------------------------------
ALLOWED_DOCUMENT_MIMETYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "application/txt",
]

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
]

# AUTH0
USE_AUTH0 = env.bool("USE_AUTH0", False)
USE_API_KEY_AUTH = env.bool("ALLOW_API_KEYS", False)

if USE_AUTH0:

    AUTH0_CLIENT_ID = env("AUTH0_CLIENT_ID")
    AUTH0_API_AUDIENCE = env("AUTH0_API_AUDIENCE")
    AUTH0_DOMAIN = env("AUTH0_DOMAIN")
    AUTH0_M2M_MANAGEMENT_API_SECRET = env("AUTH0_M2M_MANAGEMENT_API_SECRET")
    AUTH0_M2M_MANAGEMENT_API_ID = env("AUTH0_M2M_MANAGEMENT_API_ID")
    AUTH0_M2M_MANAGEMENT_GRANT_TYPE = env("AUTH0_M2M_MANAGEMENT_GRANT_TYPE")

    AUTHENTICATION_BACKENDS += [
        "config.graphql_auth0_auth.backends.Auth0RemoteUserJSONWebTokenBackend",
    ]

else:
    AUTHENTICATION_BACKENDS += [
        "graphql_jwt.backends.JSONWebTokenBackend",
    ]

if USE_API_KEY_AUTH:
    API_TOKEN_HEADER_NAME = "AUTHORIZATION"
    API_TOKEN_PREFIX = "KEY"
    AUTHENTICATION_BACKENDS += ["config.graphql_api_token_auth.backends.ApiKeyBackend"]

# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "users:redirect"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "account_login"

# Guardian Settings
# ------------------------------------------------------------------------------
GUARDIAN_AUTO_PREFETCH = True
ANONYMOUS_USER_NAME = "Anonymous"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.common.BrokenLinkEmailsMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(ROOT_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

if STORAGE_BACKEND == "LOCAL":
    # STATIC
    # ------------------------
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

    # MEDIA
    # ------------------------------------------------------------------------------
    # https://docs.djangoproject.com/en/dev/ref/settings/#media-root
    MEDIA_ROOT = str(APPS_DIR / "media")
    # https://docs.djangoproject.com/en/dev/ref/settings/#media-url
    MEDIA_URL = "/media/"
elif STORAGE_BACKEND == "AWS":
    # AWS S3 STORAGE CONFIGURATION
    # ------------------------------------------------------------------------------
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

    # Connection pooling for better performance
    # Reuse connections instead of creating new ones for each request
    AWS_S3_CONNECTION_POOL_SIZE = env.int("AWS_S3_CONNECTION_POOL_SIZE", default=10)

    # https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#cloudfront
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default=None)
    aws_s3_domain = (
        AWS_S3_CUSTOM_DOMAIN or f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
    )

    # Copied values from botos3 for OpenEdgar Crawlers rather than rewriting the crawlers (for now). Lazy :-)
    S3_ACCESS_KEY = AWS_ACCESS_KEY_ID
    S3_SECRET_KEY = AWS_SECRET_ACCESS_KEY
    S3_BUCKET = AWS_STORAGE_BUCKET_NAME
    S3_PREFIX = env("S3_PREFIX", default="documents")
    S3_COMPRESSION_LEVEL = int(env("S3_COMPRESSION_LEVEL", default=6))

    # STATIC
    # ------------------------
    # Use pooled storage backends for better performance
    STATICFILES_STORAGE = (
        "opencontractserver.utils.enhanced_storages.PooledStaticRootS3Storage"
    )
    COLLECTFAST_STRATEGY = "collectfast.strategies.boto3.Boto3Strategy"
    STATIC_URL = f"https://{aws_s3_domain}/static/"

    # MEDIA
    # ------------------------------------------------------------------------------
    # Use pooled storage backends for better performance
    DEFAULT_FILE_STORAGE = (
        "opencontractserver.utils.enhanced_storages.PooledMediaRootS3Storage"
    )
    MEDIA_URL = f"https://{aws_s3_domain}/media/"
    S3_DOCUMENT_PATH = env("S3_DOCUMENT_PATH", default="open_contracts")
    MEDIA_ROOT = str(APPS_DIR / "media")

elif STORAGE_BACKEND == "GCP":
    # GCP CLOUD STORAGE CONFIGURATION
    # ------------------------------------------------------------------------------
    # https://django-storages.readthedocs.io/en/latest/#installation
    INSTALLED_APPS += ["storages"]  # noqa F405

    # GCS Settings
    # https://django-storages.readthedocs.io/en/latest/backends/gcloud.html#settings
    GS_BUCKET_NAME = env("GS_BUCKET_NAME")

    # Optional: Your Google Cloud project ID
    GS_PROJECT_ID = env("GS_PROJECT_ID", default=None)

    # Authentication - Can use service account JSON path or default credentials
    # For production, use workload identity/service account attached to compute
    GS_CREDENTIALS = env("GS_CREDENTIALS", default=None)

    # ACL for new files - publicRead for static files that need public access
    # For media files, we'll override this in the storage class
    GS_DEFAULT_ACL = env("GS_DEFAULT_ACL", default=None)

    # Security: Don't serve public URLs for private files
    GS_QUERYSTRING_AUTH = env.bool("GS_QUERYSTRING_AUTH", default=True)

    GS_EXPIRATION = timedelta(seconds=env.int("GS_EXPIRATION_SECONDS", default=86400))

    # File handling
    GS_FILE_OVERWRITE = env.bool("GS_FILE_OVERWRITE", default=False)

    # Maximum memory size before rolling over to disk (0 = no rollover)
    GS_MAX_MEMORY_SIZE = env.int("GS_MAX_MEMORY_SIZE", default=0)

    # Chunk size for resumable uploads (must be multiple of 256K)
    GS_BLOB_CHUNK_SIZE = env.int("GS_BLOB_CHUNK_SIZE", default=1024 * 256 * 10)  # 2.5MB

    # Optional custom endpoint
    GS_CUSTOM_ENDPOINT = env("GS_CUSTOM_ENDPOINT", default=None)

    # Location (subdirectory) for files - will be set per storage class
    GS_LOCATION = env("GS_LOCATION", default="")

    # Object parameters for cache control
    _GS_EXPIRY = 60 * 60 * 24 * 7  # 7 days
    GS_OBJECT_PARAMETERS = {
        "cache_control": f"max-age={_GS_EXPIRY}, s-maxage={_GS_EXPIRY}, must-revalidate"
    }

    # GZIP settings
    GS_IS_GZIPPED = env.bool("GS_IS_GZIPPED", default=False)
    GZIP_CONTENT_TYPES = (
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
        "image/svg+xml",
    )

    # IAM Sign Blob API for signed URLs (required when not using service account key file)
    GS_IAM_SIGN_BLOB = env.bool("GS_IAM_SIGN_BLOB", default=False)

    # Optional: Override service account email for signing
    GS_SA_EMAIL = env("GS_SA_EMAIL", default=None)

    # Build domain for URLs
    if GS_CUSTOM_ENDPOINT:
        gcs_domain = GS_CUSTOM_ENDPOINT
    else:
        gcs_domain = f"storage.googleapis.com/{GS_BUCKET_NAME}"

    # STATIC
    # ------------------------
    STATICFILES_STORAGE = (
        "opencontractserver.utils.storages.StaticRootGoogleCloudStorage"
    )
    STATIC_URL = f"https://{gcs_domain}/static/"

    # MEDIA
    # ------------------------------------------------------------------------------
    DEFAULT_FILE_STORAGE = (
        "opencontractserver.utils.storages.MediaRootGoogleCloudStorage"
    )
    MEDIA_URL = f"https://{gcs_domain}/media/"
    GCS_DOCUMENT_PATH = env("GCS_DOCUMENT_PATH", default="open_contracts")
    MEDIA_ROOT = str(APPS_DIR / "media")

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#template-dirs
        "DIRS": [str(APPS_DIR / "templates")],
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-loaders
            # https://docs.djangoproject.com/en/dev/ref/templates/api/#loader-types
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# http://django-crispy-forms.readthedocs.io/en/latest/install.html#template-packs
CRISPY_TEMPLATE_PACK = "bootstrap5"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-browser-xss-filter
SECURE_BROWSER_XSS_FILTER = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [("""JSv4""", "support@opensource.legal")]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": (
                "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] "
                "%(message)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {},
}

# Celery
# ------------------------------------------------------------------------------
if USE_TZ:
    # http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = REDIS_URL
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ["json"]
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = "json"
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = "json"
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#task-time-limit
# TODO: set to whatever value is adequate in your circumstances
# CELERY_TASK_TIME_LIMIT = 5 * 3600
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#task-soft-time-limit
# TODO: set to whatever value is adequate in your circumstances
# CELERY_TASK_SOFT_TIME_LIMIT = 3600
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#beat-scheduler
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 14240000  # 14 GB (thousands of kilobytes)
CELERY_MAX_TASKS_PER_CHILD = 4
CELERY_PREFETCH_MULTIPLIER = 1
CELERY_RESULT_BACKEND_MAX_RETRIES = 10
# django-rest-framework
# -------------------------------------------------------------------------------
# django-rest-framework - https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
}


# Base configuration
BASE_PATH = "./"
DATA_PATH = pathlib.Path(BASE_PATH, "data")
MODEL_PATH = pathlib.Path(BASE_PATH, "model")

# Graphene
# ------------------------------------------------------------------------------
# Start with the base middleware that we always want
GRAPHENE_MIDDLEWARE = [
    "config.graphql.permissioning.permission_annotator.middleware.PermissionAnnotatingMiddleware",
]

# Add JWT middleware if using Auth0
if USE_AUTH0:
    GRAPHENE_MIDDLEWARE.append("graphql_jwt.middleware.JSONWebTokenMiddleware")

# Add API Key middleware if enabled
if USE_API_KEY_AUTH:
    GRAPHENE_MIDDLEWARE.append(
        "config.graphql_api_token_auth.middleware.ApiKeyTokenMiddleware"
    )

# Add Django Debug Middleware if enabled
if ALLOW_GRAPHQL_DEBUG:
    GRAPHENE_MIDDLEWARE.append("graphene_django.debug.DjangoDebugMiddleware")

# Configure Graphene with the constructed middleware list
GRAPHENE = {
    "SCHEMA": "config.graphql.schema.schema",
    "MIDDLEWARE": GRAPHENE_MIDDLEWARE,
    # Increased from 10 for better performance with larger datasets
    "RELAY_CONNECTION_MAX_LIMIT": 100,
}

GRAPHQL_JWT = {
    "JWT_AUTH_HEADER_PREFIX": "Bearer",
    "JWT_VERIFY_EXPIRATION": True,
    "JWT_LONG_RUNNING_REFRESH_TOKEN": True,
    "JWT_EXPIRATION_DELTA": timedelta(days=7),
    "JWT_REFRESH_EXPIRATION_DELTA": timedelta(days=14),
    "JWT_ALGORITHM": "HS256",
    # "JWT_ALLOW_ANY_HANDLER": "config.graphql.jwt_overrides.allow_any",
}

# Reserved top-level user slugs (extendable)
RESERVED_USER_SLUGS = {
    "corpuses",
    "corpus",
    "documents",
    "document",
    "settings",
    "login",
    "logout",
    "admin",
    "api",
    "graphql",
}

# Constants for Permissioning
DEFAULT_PERMISSIONS_GROUP = "Public Objects Access"

# Embeddings / Semantic Search - TODO move to EMBEDDER_KWARGS and use like PARSER_KWARGS
# Microservice URLs - read from environment with defaults
EMBEDDINGS_MICROSERVICE_URL = env("EMBEDDINGS_MICROSERVICE_URL")
VECTOR_EMBEDDER_API_KEY = env("VECTOR_EMBEDDER_API_KEY", default="abc123")
DOCLING_PARSER_SERVICE_URL = env("DOCLING_PARSER_SERVICE_URL")
DOCLING_PARSER_TIMEOUT = env.int(
    "DOCLING_PARSER_TIMEOUT", default=300  # 5 minutes default
)
use_cloud_run_iam_auth = True

# LLM SETTING
OPENAI_API_KEY = env.str("OPENAI_API_KEY", default="")
OPENAI_MODEL = env.str("OPENAI_MODEL", default="gpt-4o")
EMBEDDINGS_MODEL = env.str("EMBEDDINGS_MODEL", default="gpt-4o")
HF_TOKEN = env.str("HF_TOKEN", default="")
HF_EMBEDDINGS_ENDPOINT = env.str("HF_EMBEDDINGS_ENDPOINT", default="")

# CORS
# ------------------------------------------------------------------------------
# django-cors-headers v4.x settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "https://127.0.0.1:3000",
    "http://localhost:5173",
    "https://localhost:5173",
    "http://127.0.0.1:5173",
    "https://127.0.0.1:5173",
]

# Allow only HTTP methods here
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

# If you send custom headers from the frontend, list them here. Defaults already
# include 'authorization' and 'content-type', but we explicitly add CSRF aliases.
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-csrf-token",
    "x-requested-with",
]

CORS_EXPOSE_HEADERS = [
    "my-custom-header",
]

# When allowing credentials, do not use allow-all origins. Keep explicit list above.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# Django requires this for cross-site cookies/POSTs from your Vite dev server
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

DEFAULT_IMAGE = """data:image/png;base64,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"""  # noqa

# Model paths
DOCLING_MODELS_PATH = env.str("DOCLING_MODELS_PATH", default="/models/docling")
SENTENCE_TRANSFORMER_MODELS_PATH = env.str(
    "SENTENCE_TRANSFORMER_MODELS_PATH", default="/models/sentence-transformers"
)

# Preferred parsers for each MIME type
PREFERRED_PARSERS = {
    "application/pdf": "opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser",
    "text/plain": "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser",
    "application/txt": "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser",  # noqa
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser",  # noqa
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser",  # noqa
}

# Thumbnail extraction tasks
THUMBNAIL_TASKS = {
    "application/pdf": "opencontractserver.tasks.doc_tasks.extract_pdf_thumbnail",
    "application/txt": "opencontractserver.tasks.doc_tasks.extract_txt_thumbnail",
    "text/plain": "opencontractserver.tasks.doc_tasks.extract_txt_thumbnail",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "opencontractserver.tasks.doc_tasks.extract_docx_thumbnail",  # noqa
    # Add other MIME types and their thumbnail tasks as needed
}

# Mapping of MIME types to annotation label types
ANNOTATION_LABELS = {
    "application/pdf": "TOKEN_LABEL",
    "application/txt": "SPAN_LABEL",
    "text/plain": "SPAN_LABEL",
    "text/markdown": "SPAN_LABEL",
    "text/x-python": "SPAN_LABEL",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "SPAN_LABEL",  # noqa
    # "text/html": "SPAN_LABEL",  # Removed as we don't support HTML
    # Add other MIME types as needed
}

# Map of MIME types to label types
MIMETYPE_TO_LABEL_TYPE = {
    "application/pdf": "SPAN_LABEL",
    "text/plain": "SPAN_LABEL",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "SPAN_LABEL",
    # "text/html": "SPAN_LABEL",  # Removed as we don't support HTML
}

# Map of MIME types to preferred embedders
PREFERRED_EMBEDDERS = {
    "application/pdf": "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",  # noqa:
    "text/plain": "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",  # noqa:
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",  # noqa:
    # "text/html": "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",  # Removed as we don't support HTML  # noqa:
}

# Default embedder to use if no preferred embedder is found
DEFAULT_EMBEDDER = "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder"

# Default embedding dimension to use if no dimension is specified
DEFAULT_EMBEDDING_DIMENSION = 768

# Map of MIME types to default embedders for different dimensions
DEFAULT_EMBEDDERS_BY_FILETYPE = {
    "application/pdf": "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
    "text/plain": "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",  # noqa
}

# Default runner
TEST_RUNNER = "opencontractserver.tests.runner.TerminateConnectionsTestRunner"

PARSER_KWARGS = {
    "opencontractserver.pipeline.parsers.docling_parser.DoclingParser": {
        "force_ocr": False,
        "roll_up_groups": True,
        "llm_enhanced_hierarchy": False,
    },
    "opencontractserver.pipeline.parsers.nlm_ingest_parser.NLMIngestParser": {
        "endpoint": "http://nlm-ingestor:5001",
        "api_key": "",
        "use_ocr": True,
    },
}

# Analyzers
# ------------------------------------------------------------------------------
ANALYZER_KWARGS = {
    "opencontractserver.tasks.doc_analysis_tasks.agentic_highlighter_claude": {
        "ANTHROPIC_API_KEY": env.str("ANTHROPIC_API_KEY", default=""),
    },
}

# Minnesota Case Law ModernBERT embedder settings
MINN_MODERNBERT_EMBEDDERS = {
    "application/pdf": "opencontractserver.pipeline.embedders.minn_modern_bert_embedder.MinnModernBERTEmbedder768",
    "text/plain": "opencontractserver.pipeline.embedders.minn_modern_bert_embedder.MinnModernBERTEmbedder768",
    "text/html": "opencontractserver.pipeline.embedders.minn_modern_bert_embedder.MinnModernBERTEmbedder768",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "opencontractserver.pipeline.embedders.minn_modern_bert_embedder.MinnModernBERTEmbedder768",  # noqa
}


# Pipeline-specific settings that override global settings
# These are only set if you want to override the global settings for specific components
# Otherwise, components will fall back to the global settings (which read from env vars)
PIPELINE_SETTINGS = {
    # Example: To override settings for a specific component:
    # "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder": {
    #     "embeddings_microservice_url": "https://custom-url-for-this-component",
    #     "vector_embedder_api_key": "custom-key",
    # },
    # Currently no overrides - all components use global settings which read from env vars
}

LLMS_DEFAULT_AGENT_FRAMEWORK = "pydantic_ai"

# Default Agent Instructions
# ------------------------------------------------------------------------------
DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  ABSOLUTE REQUIREMENTS - NO EXCEPTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. You have ZERO prior knowledge of this document's contents.
2. You MUST use tools to examine the document before answering ANY question.
3. NEVER say you don't know what document is being discussed.
4. NEVER refuse to answer because you 'lack context' - USE THE TOOLS to get context.
5. Every answer MUST be grounded in information retrieved via tools with specific citations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 RECOMMENDED SEARCH STRATEGY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For most questions, follow this workflow:

STEP 1 - GET OVERVIEW:
  • Use `load_document_summary` to understand the document's structure and main topics
  • Use `get_document_text_length` to check the document size
  • This helps you plan your detailed search strategy

STEP 2 - BROAD SEARCH (Semantic Understanding):
  • Use `similarity_search` (vector search) to find semantically relevant sections
  • Great for: conceptual questions, themes, related ideas, paraphrased content
  • Returns: annotated passages with page numbers and similarity scores

STEP 3 - DETAILED EXAMINATION:
  • Use `load_document_text` to read large sections (5K-50K chars) of relevant areas
  • Identify the specific character ranges from Step 1-2, then load those sections
  • Read enough context to thoroughly understand the relevant passages

  🔴 MANDATORY CITATION STEP - DO NOT SKIP:
  After reading ANY bulk text with `load_document_text`, you MUST:
  1. Identify the 3-5 most relevant exact quotes/passages for your answer
  2. Extract the EXACT text of each key passage (5-50 words each)
  3. Call `search_exact_text` with these exact strings to create proper citations
  4. This converts raw text into citable sources with page numbers

  WHY THIS MATTERS: `load_document_text` returns raw text WITHOUT creating sources.
  Only `search_exact_text` creates proper citations. Without this step, your answer
  will have NO SOURCES even though you read the document!

STEP 4 - PRECISE LOCATION (Exact Matching):
  • Use `search_exact_text` to find specific terms, phrases, or quoted language
  • Great for: finding exact wording, specific terminology, quoted passages, defined terms
  • Returns: all occurrences with page numbers and bounding boxes (PDFs)
  • Use this to provide precise citations with exact page locations
  • CRITICAL: Always use this AFTER bulk text loading to create proper source citations

STEP 5 - CROSS-REFERENCE:
  • Use `get_document_notes` to check for existing analysis or annotations
  • Combine findings from multiple tools to ensure completeness

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 TOOL SELECTION GUIDE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Use `similarity_search` when:
  → Question asks about concepts, themes, or ideas (not exact words)
  → You need to find related content even if worded differently
  → Looking for passages that discuss a topic

Use `search_exact_text` when:
  → User asks about specific terms, phrases, or exact wording
  → You need to verify if specific language appears in the document
  → Providing citations that require exact page locations
  → Finding defined terms or quoted material

Use `load_document_text` when:
  → You need to read substantial sections for full context
  → Initial searches identified relevant areas to examine in detail
  → Question requires understanding flow, structure, or relationships
  ⚠️  ALWAYS follow with `search_exact_text` on key passages to create citations!

Use `load_document_summary` when:
  → Starting your analysis (always good first step)
  → Need high-level overview of document structure
  → Understanding document organization before detailed search

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ RESPONSE REQUIREMENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Provide complete, accurate answers based on document contents
• Include specific citations (page numbers, quotes) from tool results
• 🔴 CRITICAL: If you used `load_document_text`, you MUST use `search_exact_text`
  on key passages to generate proper citations. Otherwise your answer will have NO SOURCES.
• If information isn't in the document, explicitly state it was not found
• Use multiple search strategies to ensure thoroughness
• Present findings clearly with proper attribution to sources"""

DEFAULT_CORPUS_AGENT_INSTRUCTIONS = """You are a helpful corpus analysis assistant.
Your role is to help users understand and analyze collections of documents by coordinating across
multiple documents and using the tools available to you.

**CRITICAL RULES:**
1. ALWAYS use tools to gather information before answering
2. You have access to multiple documents - use them effectively
3. ALWAYS cite sources from specific documents when making claims

**Available Tools:**
- **Document-Specific Tools**: Available via `ask_document(document_id, question)`
- **Corpus-Level Tools**: `list_documents()` to see all available documents
- **Cross-Document Search**: Semantic search across the entire corpus

**Recommended Strategy:**
1. If the corpus has a description, use it as context
2. If the corpus description is empty BUT has documents:
   - Start by using `list_documents()` to see what's available
   - Use `ask_document()` to query specific documents
   - Use cross-document vector search for themes across documents
3. Synthesize information from multiple sources
4. Always cite which document(s) your information comes from

**When Corpus Has No Description:**
Don't just say "the corpus description is empty" - that's not helpful! Instead:
1. List available documents
2. Ask the user which documents they want to know about
3. OR proactively examine key documents to provide a useful summary

Always prioritize being helpful and use your tools to provide value."""

# LLM Client Provider Settings
# ------------------------------------------------------------------------------
LLM_CLIENT_PROVIDER = env.str("LLM_CLIENT_PROVIDER", default="openai")
LLM_CLIENT_MODEL = env.str("LLM_CLIENT_MODEL", default="gpt-4o-mini")
LLM_CLIENT_TEMPERATURE = env.float("LLM_CLIENT_TEMPERATURE", default=0.7)
LLM_CLIENT_MAX_TOKENS = env.int("LLM_CLIENT_MAX_TOKENS", default=None)

# Rate Limiting Configuration
# ------------------------------------------------------------------------------
# Import rate limiting settings
from config.settings.ratelimit import *  # noqa: F401, F403, E402

# Telemetry Configuration
# ------------------------------------------------------------------------------
# Please check out the telemtry package or its usage if you want more details.
# You absolutely can disable this. We are collecting frequence of high-level action
# per installation (identified by a UUID with no PII) to help improve the application.
TELEMETRY_ENABLED = env.bool("TELEMETRY_ENABLED", default=True)
# IF you wanted to use your own telemetry, use your API key and host here.
POSTHOG_API_KEY = env.str(
    "POSTHOG_API_KEY", default="phc_wsTXvOFv6QLDMOA3yLl16awF4DTgILi4MSVLwhwyDeJ"
)
POSTHOG_HOST = env.str("POSTHOG_HOST", default="https://us.i.posthog.com")
MODE = "LOCAL"
