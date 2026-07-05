#!/usr/bin/env python
"""Entry point for the single-user OpenContracts desktop build.

Runs the whole stack (embedded PostgreSQL+pgvector, Daphne serving the API and
the pre-built SPA, a Celery worker + beat) as one supervised process with no
Docker and no Redis, then opens the browser.

    python oc-desktop.py

See ``docs/deployment/desktop_packaging.md`` and
``opencontractserver/desktop/launcher.py``.
"""

from opencontractserver.desktop.launcher import main

if __name__ == "__main__":
    main()
