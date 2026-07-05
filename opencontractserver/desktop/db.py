"""Database URL helpers for the desktop build.

Pure functions (no Django import) so they are safe to call from
``config/settings/desktop.py`` at settings-load time and are unit-testable in
isolation (importing a settings module in a test is not).
"""

from __future__ import annotations

# Django DATABASE_URL schemes that map onto SQLAlchemy's psycopg2 dialect.
_POSTGRES_SCHEMES = ("postgres", "postgresql", "postgis")


def sqlalchemy_result_backend_url(database_url: str) -> str:
    """Map a Django ``DATABASE_URL`` to a Celery SQLAlchemy result-backend URL.

    Celery's SQLAlchemy result backend expects a ``db+<dialect>://`` URL. The
    desktop build reuses the bundled Postgres for Celery results (chords need a
    real result backend and we have no Redis), so a ``postgres://…`` /
    ``postgresql://…`` Django URL becomes ``db+postgresql://…``. Any query string
    (e.g. ``?sslmode=require``) and credentials are preserved verbatim. Non-
    Postgres URLs are passed through with a ``db+`` prefix.

    >>> sqlalchemy_result_backend_url("postgres://u:p@h:5432/db")
    'db+postgresql://u:p@h:5432/db'
    >>> sqlalchemy_result_backend_url("postgresql://u@h/db?sslmode=require")
    'db+postgresql://u@h/db?sslmode=require'
    """
    scheme, sep, rest = database_url.partition("://")
    if sep and scheme in _POSTGRES_SCHEMES:
        return f"db+postgresql://{rest}"
    return f"db+{database_url}"
