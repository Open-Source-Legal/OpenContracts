- **Desktop packaging is now one step: `python oc-desktop.py`** (goal: a
  minimally technical user gets from a source download to the app in a browser
  with a single command, cross-platform).
  - `opencontractserver/desktop/bootstrap.py` (new, stdlib-only): guards the
    Python version window (3.10–3.12 — `pgserver` publishes no 3.13 wheels),
    creates a private virtualenv under the per-user app-data dir, installs
    `requirements/desktop.txt` into it on first run (re-installs automatically
    when the requirement files change, tracked by a content fingerprint), and
    re-execs the launcher inside that venv. `oc-desktop.py` now routes through
    it, so no manual pip/venv knowledge is required.
  - `opencontractserver/desktop/spa_dist.py` (new): removes the Node/yarn
    requirement for end users. The launcher now resolves the built SPA in
    order: repo `frontend/dist` → previously downloaded copy in app-data →
    download `opencontracts-frontend-dist.zip` from the GitHub release matching
    `opencontractserver.__version__` (falling back to the latest release) →
    `yarn build` if a Node toolchain is present (developers). Zip extraction
    refuses path-traversal members.
  - `.github/workflows/docker-build-release.yml`: new `build-frontend-dist` job
    attaches the built SPA as `opencontracts-frontend-dist.zip` to every
    release so the download path above works.
  - `opencontractserver/desktop/launcher.py`: on first run with no
    `OC_DESKTOP_PASSWORD` set, interactively prompts for the local login
    password (TTY only; env var still wins) instead of silently creating a
    passwordless superuser; prints a startup banner with the URL, username,
    and how to stop the app (Ctrl+C).
  - `README.md` Quick Start now includes a "Desktop (no Docker)" path;
    `docs/deployment/desktop_packaging.md` updated to the one-command flow.
  - Tests: `opencontractserver/tests/test_desktop_packaging.py` gains
    `BootstrapTests` and `SpaDistTests` (version window, venv paths,
    requirements fingerprint, tag-candidate mapping, asset resolution,
    zip-slip guard, SPA resolution order).
