"""
Django settings for the remote-ingest worker (``scripts/remote_ingest``).

The remote worker runs the OpenContracts parsing pipeline (DoclingParser) on a
beefy off-cluster host and streams finished documents to a target instance via
the worker-upload REST API. It NEVER touches the target's database — it only
needs Django importable so the real parser code (and its model imports) loads.

To keep the remote host dependency-free (no Postgres, no Redis), this module
points ``DATABASE_URL`` at a throwaway SQLite file. No migrations are run, so the
tables do not exist — but the only DB access on the parse path is
``PipelineComponentBase._load_settings`` querying ``PipelineSettings``, which
catches the resulting error and falls back to dataclass defaults + the
``DOCLING_*`` / ``EMBEDDINGS_*`` environment variables. The parse itself
(``DoclingParser.parse_pdf_bytes``) is entirely database-free.

If a deployment prefers a real database (e.g. to pin parser settings via the
``PipelineSettings`` table), point ``DATABASE_URL`` at any reachable Postgres —
this module's only job is to provide safe defaults so Django boots without one.
"""

import os

# These MUST be set before importing base.py: base reads ``DATABASE_URL`` via
# ``env.db(...)`` (no default) at import time. A throwaway SQLite path keeps the
# remote host free of any database service.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/oc_remote_worker.sqlite3")
os.environ.setdefault("DJANGO_SECRET_KEY", "remote-worker-not-a-secret-no-web-surface")

from .base import *  # noqa: E402,F401,F403

# The worker exposes no web/admin surface, runs no Celery, serves no requests.
DEBUG = False

# Belt-and-suspenders: never run ATOMIC_REQUESTS against the placeholder DB.
DATABASES["default"]["ATOMIC_REQUESTS"] = False  # noqa: F405
