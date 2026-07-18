from .base import *  # noqa
from .base import SECURE_CSP_DIRECTIVES, env

# GENERAL
# ------------------------------------------------------------------------------
USE_SILK = False

# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="XA3MPNT1srMGeX0nDKTtL10T5D1k3oLednwShggYSbvFvI3ASF5ew39rnKqemnMu",
)

# CACHES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#caches
CACHES = {
    "default": {
        # Use Redis cache if available, otherwise fallback to local memory
        "BACKEND": (
            "django.core.cache.backends.redis.RedisCache"
            if env("REDIS_URL", default=None)
            else "django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": (
            env("REDIS_URL", default="") if env("REDIS_URL", default=None) else ""
        ),
        "TIMEOUT": 300,  # 5 minutes default timeout
    }
}

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# django-extensions
# ------------------------------------------------------------------------------
# https://django-extensions.readthedocs.io/en/latest/installation_instructions.html#configuration
INSTALLED_APPS += ["django_extensions"]  # noqa F405

# Celery
# ------------------------------------------------------------------------------
CELERY_TASK_EAGER_PROPAGATES = (
    True  # If this is True, eagerly executed tasks will propagate exceptions
)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = False
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = False
# https://docs.djangoproject.com

# Allow WebSocket connections to the local Vite HMR / Django Channels dev
# server.  Scoped to localhost to avoid opening connections to arbitrary
# external hosts.  Production base.py restricts connect-src to 'self' only
# (which covers same-origin wss:// when served over HTTPS).
#
# NOTE: This EXTENDS base.py's connect-src — which already includes the Auth0
# tenant domain when USE_AUTH0=True — with the dev WebSocket sources, rather
# than replacing it.  A wholesale replace dropped the Auth0 domain and broke
# the Auth0 login token exchange (POST https://<tenant>/oauth/token) with a
# CSP connect-src violation on the Django-served auth0_login.html page.
#
# Shallow copy is safe here because we assign a new list rather than mutating
# the existing one (list(...) + [...] builds a fresh list, leaving base.py's
# connect-src list untouched).
_csp = SECURE_CSP_DIRECTIVES.copy() if SECURE_CSP_DIRECTIVES else {}
_csp["connect-src"] = list(_csp.get("connect-src", ["'self'"])) + [
    "ws://localhost:*",
    "wss://localhost:*",
]
SECURE_CSP_DIRECTIVES = _csp

# Set DEBUG based on env variable, defaulting to False for better performance
# You can override this with DJANGO_DEBUG=True in your .env file when needed
DEBUG = env.bool("DJANGO_DEBUG", False)

# Your stuff...
# ------------------------------------------------------------------------------
if DEBUG and USE_SILK:
    MIDDLEWARE += [
        "django_cprofile_middleware.middleware.ProfilerMiddleware",
        "silk.middleware.SilkyMiddleware",
    ]
    SILKY_PYTHON_PROFILER = True

# In local dev, use simple static file serving (no manifest required).
# The base.py CompressedManifestStaticFilesStorage requires collectstatic
# which is unnecessary when runserver serves static files directly.
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}
