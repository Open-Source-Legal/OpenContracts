- **Desktop packaging is now one step: `python oc-desktop.py`** (goal: a
  minimally technical user gets from a source download to the app in a browser
  with a single command, cross-platform). Validated by a clean-room usability
  test role-playing a non-technical user against the previous flow (which
  required Node/yarn, pip/venv knowledge, env vars, and died at an
  un-googleable migration failure — see the `pg_trgm` fragment).
  - `opencontractserver/desktop/bootstrap.py` (new, stdlib-only): guards the
    Python version window (3.10–3.12 — `pgserver` publishes no 3.13 wheels
    and outside the window end users hit cryptic native build failures),
    creates a private virtualenv under the per-user app-data dir, installs
    `requirements/desktop.txt` into it on first run (re-installs automatically
    when the requirement files change, tracked by a content fingerprint), and
    re-execs the launcher inside that venv. `oc-desktop.py` now routes through
    it, so no manual pip/venv knowledge is required.
  - `opencontractserver/desktop/spa_dist.py` (new): removes the Node/yarn
    requirement for end users. The launcher resolves the built SPA in order:
    repo `frontend/dist` → previously downloaded copy in app-data → download
    `opencontracts-frontend-dist.zip` from the GitHub release matching
    `opencontractserver.__version__` (falling back to the latest release) →
    `yarn install && yarn build` if a Node toolchain is present (developers).
    Zip extraction refuses path-traversal members.
  - `.github/workflows/docker-build-release.yml`: new `build-frontend-dist`
    job attaches the built SPA as `opencontracts-frontend-dist.zip` to every
    release so the download path above works.
  - `desktop_bootstrap` (`opencontractserver/documents/management/commands/`):
    the local login password now comes from `OC_DESKTOP_PASSWORD` *or an
    interactive first-run prompt* (min 8 chars, confirmed twice) — users no
    longer need to know what an env var is, and a password-less account left
    over from a headless first run self-heals on the next launch.
  - `opencontractserver/desktop/launcher.py`: stable default port (8406, with
    ephemeral fallback) so the URL survives restarts; startup banner stating
    the URL, the `desktop` username (previously documented nowhere), and that
    Ctrl+C stops the app; SPA auto-acquisition wired into `_resolve_spa_dir`.
  - Discoverability: README gains a "Desktop — run it on your computer (no
    Docker)" Quick Start section; `docs/quick_start.md` cross-links it;
    `docs/deployment/desktop_packaging.md` rewritten around the one-command
    flow; the page is now in the mkdocs nav (it was previously unreachable
    from the docs site).
  - Tests: `BootstrapTests`, `SpaDistTests`, `TrigramMigrationGuardTests`, and
    prompt/self-heal coverage in `DesktopBootstrapTests`
    (`opencontractserver/tests/test_desktop_packaging.py`).
