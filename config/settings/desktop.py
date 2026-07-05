"""Settings for the single-user *desktop* build.

This profile collapses the docker-compose topology into one supervised Python
process: Daphne serves the ASGI app AND the pre-built React SPA, background work
runs without Redis, and PostgreSQL+pgvector runs as a bundled child process.
Compared to ``config.settings.production`` it drops every network service:

* **Redis → gone.** Cache falls back to in-memory; the Celery broker uses the
  kombu *filesystem* transport and results go to the bundled Postgres via
  SQLAlchemy (chords need a real result backend); the Channels layer is
  in-process.
* **PostgreSQL** is a bundled child process (``pgserver``) on a per-user data
  dir; ``DATABASE_URL`` is injected by the ``oc-desktop`` launcher.
* **Storage** is local files under the per-user app-data directory.
* **Auth0 → off.** A single local Django user + graphql_jwt is used.
* **ML microservices → gone.** PDF parsing runs in-process via Warp-Ingest and
  embeddings via an OpenAI-compatible endpoint (see ``desktop_bootstrap``).

The launcher exports ``DATABASE_URL`` and ``OC_DESKTOP_*`` before this module is
imported. Defaults below keep ``manage.py check`` importable without the
launcher. See ``docs/deployment/desktop_packaging.md``.
"""

import os

from opencontractserver.desktop import paths

# Env defaults so the profile imports cleanly under a bare ``manage.py`` (the
# launcher overrides DATABASE_URL with the embedded-Postgres connection). Set
# BEFORE importing base, which reads DATABASE_URL with no default of its own.
os.environ.setdefault("DJANGO_READ_DOT_ENV_FILE", "False")
os.environ.setdefault(
    "DATABASE_URL",
    "postgres://opencontracts:opencontracts@127.0.0.1:5464/opencontracts",
)

from .base import *  # noqa: E402,F401,F403
from .base import SECURE_CSP_DIRECTIVES, env  # noqa: E402

# GENERAL
# ------------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", default=False)

# A desktop app is reachable only on the loopback interface.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# SECRET_KEY comes from the environment only. The ``oc-desktop`` launcher
# generates ONE key and exports it to every child process (Daphne/worker/beat)
# so they share it within a run. When unset (e.g. a bare ``manage.py``), we fall
# back to an ephemeral in-process key so import never fails; sessions/tokens then
# reset across restarts. We deliberately do NOT persist the secret to a plaintext
# file — set ``DJANGO_SECRET_KEY`` (the launcher does) for a stable key. Secure
# at-rest persistence (OS keyring) is a Phase-1 follow-up.
SECRET_KEY = env("DJANGO_SECRET_KEY", default=None)
if not SECRET_KEY:
    import secrets as _secrets
    import warnings

    SECRET_KEY = _secrets.token_urlsafe(64)
    warnings.warn(
        "DJANGO_SECRET_KEY is not set; using an ephemeral key. Sessions and "
        "tokens will not survive a restart. Set DJANGO_SECRET_KEY (the "
        "oc-desktop launcher does this automatically) for a stable key.",
        RuntimeWarning,
        stacklevel=1,
    )

# Local, single-user auth — no Auth0 tenant.
USE_AUTH0 = False

# CACHES — no Redis; process-local memory cache.
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "oc-desktop",
        "TIMEOUT": 300,
    }
}

# STORAGE — local files under the per-user app-data directory.
# ------------------------------------------------------------------------------
STORAGE_BACKEND = "LOCAL"
MEDIA_ROOT = str(paths.media_dir())
STATIC_ROOT = str(paths.static_dir())

# PIPELINE — offline / in-process components (no ML microservices).
# ------------------------------------------------------------------------------
# PDFs parse in-process with Warp-Ingest; embeddings come from an OpenAI-
# compatible endpoint (cloud key OR a local server via OPENAI_API_BASE_URL).
# These become the seed defaults for the PipelineSettings singleton on first
# boot (see the ``desktop_bootstrap`` management command). DOCX/PPTX/XLSX still
# route to the (absent) Docling parser and are a follow-up for the desktop build.
_WARP_PARSER = "opencontractserver.pipeline.parsers.warp_ingest_parser.WarpIngestParser"
_TXT_PARSER = "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser"
_MD_PARSER = "opencontractserver.pipeline.parsers.oc_markdown_parser.MarkdownParser"
_OPENAI_EMBEDDER = (
    "opencontractserver.pipeline.embedders.openai_embedder.OpenAIEmbedder"
)

PREFERRED_PARSERS = {
    "application/pdf": _WARP_PARSER,
    "text/plain": _TXT_PARSER,
    "application/txt": _TXT_PARSER,
    "text/markdown": _MD_PARSER,
}
PREFERRED_EMBEDDERS = {
    "application/pdf": _OPENAI_EMBEDDER,
    "text/plain": _OPENAI_EMBEDDER,
    "text/markdown": _OPENAI_EMBEDDER,
}
DEFAULT_EMBEDDER = _OPENAI_EMBEDDER
# text-embedding-3-small → 1536 dims, which maps to the HNSW-indexed
# ``Embedding.vector_1536`` column. Keep in sync with the seeded embedder model.
DEFAULT_EMBEDDING_DIMENSION = 1536

# CHANNELS — in-process layer (no Redis).
# ------------------------------------------------------------------------------
# NOTE(desktop, task #3): InMemoryChannelLayer only delivers when the emitter and
# consumer share the same asyncio loop. The notification signal + thread-agent
# task fire ``group_send`` from a non-Daphne loop, so real-time notification
# toasts are NOT yet delivered under this layer — that loop-safe transport
# (Postgres LISTEN/NOTIFY) is the immediate follow-up. The agent-chat stream is
# unaffected (it streams inline in the consumer, no channel layer). See
# docs/deployment/desktop_packaging.md#real-time-eventing.
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}

# CELERY — no Redis broker/result backend.
# ------------------------------------------------------------------------------
# Broker: kombu filesystem transport (a spool dir, no server). Result backend:
# the bundled Postgres via SQLAlchemy — a real result backend is required for
# the ingest/extract *chords* (eager execution breaks chord orchestration, so it
# is deliberately NOT used here). The launcher runs a single worker subprocess.
_broker_in = str(paths.subdir("celery-broker", "in", create=False))
_broker_out = str(paths.subdir("celery-broker", "out", create=False))
CELERY_BROKER_URL = "filesystem://"
# Fresh dict of str→str paths; base.py's value is str→int (visibility_timeout),
# so the reassignment is typed differently on purpose.
_broker_transport_options = {
    "data_folder_in": _broker_in,
    "data_folder_out": _broker_out,
    "control_folder": str(paths.subdir("celery-broker", "control", create=False)),
}
CELERY_BROKER_TRANSPORT_OPTIONS = _broker_transport_options  # type: ignore[assignment]


def _sqlalchemy_result_url(database_url: str) -> str:
    """Map a Django ``DATABASE_URL`` to a Celery SQLAlchemy result backend URL."""
    scheme, _, rest = database_url.partition("://")
    if scheme in ("postgres", "postgresql", "postgis"):
        return f"db+postgresql://{rest}"
    return f"db+{database_url}"


CELERY_RESULT_BACKEND = _sqlalchemy_result_url(env("DATABASE_URL"))
CELERY_TASK_EAGER_PROPAGATES = True
# Use the file-based PersistentScheduler so beat needs no django_celery_beat DB
# rows. The launcher runs a ``celery beat`` subprocess against it (Phase 0);
# collapsing beat into an in-process APScheduler is a Phase-1 follow-up.
CELERY_BEAT_SCHEDULER = "celery.beat:PersistentScheduler"

# EMAIL — no SMTP server on a desktop; log to the console.
# ------------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# STATIC / SPA SERVING
# ------------------------------------------------------------------------------
# The catch-all view in config/urls.py (config.spa.spa_fallback) serves the
# built SPA's assets and returns index.html for client-side routes from this
# dir. Set by the launcher after ``yarn build`` is staged; when unset, SPA
# serving is disabled (API only).
OC_DESKTOP_SPA_ROOT = env("OC_DESKTOP_FRONTEND_DIR", default="")

# CSP / CORS — same-origin localhost.
# ------------------------------------------------------------------------------
# The SPA is served same-origin, so no cross-origin GraphQL/WS is needed; allow
# loopback WebSocket sources for defence-in-depth on http://127.0.0.1:<port>.
_csp = SECURE_CSP_DIRECTIVES.copy() if SECURE_CSP_DIRECTIVES else {}
_csp["connect-src"] = list(_csp.get("connect-src", ["'self'"])) + [
    "ws://localhost:*",
    "ws://127.0.0.1:*",
]
SECURE_CSP_DIRECTIVES = _csp

# Cookies over plain http on loopback.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
