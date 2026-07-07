#!/usr/bin/env python3
"""One-step entry point for the single-user OpenContracts desktop build.

    python oc-desktop.py

That single command is the whole setup: on first run it creates a private
Python environment, installs the dependencies, fetches the pre-built app UI,
starts the embedded database, asks you to choose a login password, and opens
your browser. Later runs skip straight to launch. Press Ctrl+C to stop.

See ``docs/deployment/desktop_packaging.md``,
``opencontractserver/desktop/bootstrap.py`` (first-run environment setup) and
``opencontractserver/desktop/launcher.py`` (process supervision).
"""

import sys

if __name__ == "__main__":
    if sys.version_info < (3, 8):
        # Too old even to import the bootstrap module — bail with a plain
        # message rather than a SyntaxError. The bootstrap enforces the real
        # supported window (see opencontractserver.desktop.bootstrap).
        sys.exit(
            "OpenContracts Desktop needs a newer Python. Install Python 3.12 "
            "from https://www.python.org/downloads/ and run this again."
        )
    from opencontractserver.desktop.bootstrap import main

    main()
