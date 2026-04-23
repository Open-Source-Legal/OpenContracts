"""
Settings module used exclusively by `mypy_django_plugin` during type checking.

The plugin imports this module at startup to introspect `INSTALLED_APPS` and
model metadata. It does **not** run the ORM, so the database URL below is a
dummy value that only needs to parse cleanly through `django-environ`.

Keeping a dedicated module here (instead of pointing the plugin at
`config.settings.test`) means contributors do not need to set `DATABASE_URL`
to run mypy locally or via pre-commit.
"""

import os

# `env.db(...)` in `config.settings.base` raises unless DATABASE_URL is set.
# Set it *and* keep a local copy so we can reassert it after the test
# import below, in case `config.settings.test` (or any of its transitive
# imports) ever grows a DATABASE_URL override that runs before we re-read
# the env.
_MYPY_DUMMY_DATABASE_URL = "postgres://mypy:mypy@localhost:5432/mypy_dummy_db"
os.environ.setdefault("DATABASE_URL", _MYPY_DUMMY_DATABASE_URL)

# As of 2026-04, `config.settings.test` only requires DATABASE_URL from
# the environment. If a future change adds another required env var to
# the test chain, add a matching os.environ.setdefault() above.
from .test import *  # noqa: E402, F401, F403

# Defensive: if the test-settings import chain ever pops DATABASE_URL from
# the environment (unlikely but cheap to guard), put it back so the rest of
# the plugin start-up doesn't explode on a later env.db() call.
os.environ.setdefault("DATABASE_URL", _MYPY_DUMMY_DATABASE_URL)
