"""``oc-desktop`` launcher: run all of OpenContracts as one supervised process.

Phase 0 of the desktop packaging effort (see
``docs/deployment/desktop_packaging.md``). Starts the whole stack with **no
Docker and no Redis**:

* an embedded PostgreSQL+pgvector child (via the optional ``pgserver`` package)
  or an external ``DATABASE_URL`` you provide,
* ``manage.py migrate`` + a one-time first-run bootstrap (local user, pipeline
  seeding, nltk corpora),
* Daphne (ASGI + the pre-built SPA) on a free loopback port,
* a Celery worker and beat subprocess over the filesystem broker,

then opens the browser and supervises the children, tearing them down cleanly on
exit.

Run with ``python oc-desktop.py`` (repo root) or
``python -m opencontractserver.desktop.launcher``.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from opencontractserver.desktop import paths

SETTINGS_MODULE = "config.settings.desktop"
_children: list[subprocess.Popen] = []
# Open log-file handles for the child processes, closed on shutdown.
_log_handles: list = []

# Stable default port so the app's URL survives restarts (bookmarks, the
# "where did it go?" problem). Falls back to an OS-assigned ephemeral port
# when something else already holds it.
DEFAULT_PORT = 8406
# Local login account seeded by desktop_bootstrap (its --username default);
# surfaced in the startup banner so users never have to read source to log in.
LOCAL_USERNAME = "desktop"


_KEYRING_SERVICE = "OpenContracts-Desktop"
# Hard timeout for the keyring resolution — a locked GNOME Keyring / KWallet can
# block on an interactive unlock prompt rather than raising, which would hang the
# launcher before any child starts. On timeout we fall back to an ephemeral key.
_KEYRING_TIMEOUT_SECONDS = 10


def _keyring_username() -> str:
    """Keyring entry name, scoped to the data dir.

    Two desktop instances under different ``OC_DESKTOP_DATA_DIR``s (e.g. a test
    profile alongside a real one) each get their own persisted SECRET_KEY rather
    than silently sharing one. The data dir is hashed to keep the entry name
    short and backend-safe (some OS keyrings cap target-name length).
    """
    import hashlib

    digest = hashlib.sha256(str(paths.app_data_dir()).encode()).hexdigest()[:16]
    return f"django-secret-key-{digest}"


def _keyring_get_or_create() -> str:
    """Fetch (or create+persist) the SECRET_KEY in the OS keyring. Raises on error."""
    import keyring

    username = _keyring_username()
    existing = keyring.get_password(_KEYRING_SERVICE, username)
    if existing:
        return existing
    new_key = secrets.token_urlsafe(64)
    keyring.set_password(_KEYRING_SERVICE, username, new_key)
    return new_key


def _stable_secret_key() -> str:
    """A SECRET_KEY that survives restarts, stored in the OS keyring.

    A stable key matters beyond login sessions: ``PipelineSettings`` encrypts
    secrets (e.g. ``OPENAI_API_KEY``) with a Fernet key derived from
    ``SECRET_KEY`` (``opencontractserver/documents/models.py``), so a key that
    rotated every launch would make those stored secrets permanently
    unrecoverable — silently breaking the Tier-1 "set your API key once" flow on
    the next restart. We persist the key in the OS credential store (macOS
    Keychain / Windows Credential Locker / Linux Secret Service) rather than a
    plaintext file.

    The keyring call runs in a daemon thread with a hard timeout: a locked
    Linux keyring can block on an interactive unlock prompt instead of raising,
    which would otherwise hang the launcher before any child starts. On timeout
    OR any error (missing/broken backend), fall back to an ephemeral key with a
    loud warning — sessions and stored pipeline secrets then do NOT survive a
    restart.
    """
    import threading

    box: dict = {}

    def _run() -> None:
        try:
            box["key"] = _keyring_get_or_create()
        except Exception as exc:  # keyring missing or no usable backend
            box["error"] = exc

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(_KEYRING_TIMEOUT_SECONDS)

    if "key" in box:
        return box["key"]

    reason = (
        f"timed out after {_KEYRING_TIMEOUT_SECONDS}s (a locked OS keyring can "
        "block on an interactive unlock prompt)"
        if worker.is_alive()
        else f"failed ({box.get('error')})"
    )
    print(
        f"[oc-desktop] WARNING: SECRET_KEY keyring persistence {reason}; using an "
        "ephemeral key. Login sessions and stored pipeline secrets (e.g. your "
        "OpenAI API key) will NOT survive a restart. Export a stable "
        "DJANGO_SECRET_KEY to avoid this."
    )
    return secrets.token_urlsafe(64)


# --------------------------------------------------------------------------- env
def _base_env() -> dict[str, str]:
    """Environment shared by the launcher and every child process."""
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = SETTINGS_MODULE
    env["DJANGO_READ_DOT_ENV_FILE"] = "False"
    data_dir = paths.app_data_dir()
    env[paths.DATA_DIR_ENV] = str(data_dir)
    # Point nltk at the app-data corpora dir so Warp-Ingest resolves stopwords
    # / punkt offline.
    env["NLTK_DATA"] = str(paths.subdir("nltk_data"))
    # One SECRET_KEY shared by every child (Daphne/worker/beat) so sessions and
    # JWTs verify across them, persisted across restarts via the OS keyring (see
    # _stable_secret_key). A user-provided DJANGO_SECRET_KEY always wins.
    if "DJANGO_SECRET_KEY" not in env:
        env["DJANGO_SECRET_KEY"] = _stable_secret_key()
    return env


def _ensure_dirs() -> None:
    for maker in (
        paths.app_data_dir,
        paths.media_dir,
        paths.static_dir,
        paths.logs_dir,
    ):
        Path(maker()).mkdir(parents=True, exist_ok=True)
    for name in ("in", "out", "control"):
        (paths.celery_broker_dir() / name).mkdir(parents=True, exist_ok=True)


def _free_port() -> int:
    """Pick the stable ``DEFAULT_PORT`` when free, else an OS-assigned one.

    A stable port keeps the app's URL identical across restarts (bookmarks
    keep working); the ephemeral fallback keeps a second instance or a port
    squatter from blocking launch.

    Note: there is a TOCTOU window between releasing the probe socket here and
    Daphne binding the port. The caller reserves the port immediately before
    ``_start_daphne`` (after the slow worker/beat spawn) to keep that window
    near-instant. On a single-user loopback app the residual risk of another
    process grabbing it is negligible; a bind-retry loop is a Phase-1 follow-up.
    """
    for port in (DEFAULT_PORT, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return int(sock.getsockname()[1])
    raise RuntimeError("No free loopback port available")  # pragma: no cover


# ---------------------------------------------------------------------- postgres
def _start_postgres(env: dict[str, str]) -> None:
    """Ensure ``DATABASE_URL`` points at a running Postgres+pgvector.

    Preference order:
    1. An externally-provided ``DATABASE_URL`` (e.g. a Postgres you already run)
       — used as-is.
    2. The bundled embedded server via ``pgserver`` (optional dependency).

    Embedded-Postgres wiring is hardened in Phase 1; if ``pgserver`` is absent we
    fail fast with guidance rather than pretend a DB exists.
    """
    # Read from the threaded env (a copy of os.environ) for consistency with the
    # rest of the launcher — nothing mutates DATABASE_URL before this point.
    external = env.get("DATABASE_URL")
    if external:
        print(f"[oc-desktop] Using external DATABASE_URL ({external.split('@')[-1]}).")
        return

    try:
        import pgserver
    except ImportError:
        sys.exit(
            "[oc-desktop] No DATABASE_URL set and 'pgserver' is not installed.\n"
            "  Install the desktop extras (pip install -r requirements/desktop.txt)\n"
            "  or export DATABASE_URL pointing at a PostgreSQL 16 + pgvector server."
        )

    pgdata = paths.pg_data_dir()
    pgdata.mkdir(parents=True, exist_ok=True)
    print(f"[oc-desktop] Starting embedded PostgreSQL at {pgdata} …")
    server = pgserver.get_server(str(pgdata))

    def _stop_pg() -> None:
        with contextlib.suppress(Exception):
            server.cleanup()

    atexit.register(_stop_pg)
    # pgvector must be available before migrations create the vector columns.
    server.psql("CREATE EXTENSION IF NOT EXISTS vector;")
    env["DATABASE_URL"] = server.get_uri()
    print("[oc-desktop] Embedded PostgreSQL ready.")


# --------------------------------------------------------------------- manage.py
def _manage(env: dict[str, str], *args: str, check: bool = True) -> int:
    """Run ``manage.py <args>`` in-process-adjacent (subprocess) with desktop env."""
    cmd = [sys.executable, "manage.py", *args]
    proc = subprocess.run(cmd, env=env)
    if check and proc.returncode != 0:
        sys.exit(f"[oc-desktop] `manage.py {' '.join(args)}` failed.")
    return proc.returncode


def _first_run_bootstrap(env: dict[str, str]) -> None:
    marker = paths.first_run_marker()
    if marker.exists():
        return
    print("[oc-desktop] First run: bootstrapping local user + pipeline settings …")
    # The login password is handled inside ``desktop_bootstrap`` (which owns
    # the DB): an explicit OC_DESKTOP_PASSWORD wins; otherwise the command
    # prompts interactively on the inherited terminal — nobody should need to
    # know what an env var is to log in.
    # Write the first-run marker ONLY on a clean bootstrap (rc == 0). The command
    # exits non-zero if pipeline seeding failed; leaving the marker unwritten lets
    # the next launch retry (every step is idempotent) instead of permanently
    # stranding Tier-1 embeddings/chat behind a one-shot failure.
    if _manage(env, "desktop_bootstrap", check=False) == 0:
        marker.write_text("ok\n", encoding="utf-8")
    else:
        print(
            "[oc-desktop] WARNING: first-run bootstrap did not fully complete; "
            "it will retry on the next launch."
        )


# --------------------------------------------------------------------------- SPA
def _resolve_spa_dir(env: dict[str, str]) -> str:
    """Locate (or acquire) the built SPA dist/ dir and export it for settings.

    An explicit ``OC_DESKTOP_FRONTEND_DIR`` wins; otherwise ``spa_dist``
    resolves it — repo ``frontend/dist``, a previously downloaded copy in
    app-data, the GitHub release bundle, or a local yarn build — so end users
    never need a Node toolchain.
    """
    # Read from the threaded env (consistent with the rest of the launcher).
    spa = env.get("OC_DESKTOP_FRONTEND_DIR")
    if not spa:
        from opencontractserver import __version__
        from opencontractserver.desktop import spa_dist

        repo_root = Path(__file__).resolve().parents[2]
        found = spa_dist.ensure_spa(repo_root, __version__)
        if found:
            spa = str(found)
        else:
            print(
                "[oc-desktop] WARNING: no frontend bundle could be found, "
                "downloaded, or built.\n             The API will run, but "
                "the app UI will be unavailable. Check your internet\n"
                "             connection and relaunch to retry the download."
            )
    if spa:
        env["OC_DESKTOP_FRONTEND_DIR"] = spa
    return spa or ""


def _write_env_config(spa_dir: str, port: int) -> None:
    """Point the SPA's runtime config at this Daphne origin (same-origin API).

    Deliberate side effect: this rewrites ``env-config.js`` inside whatever
    dist dir was resolved — including a developer's repo-local
    ``frontend/dist`` (build output, untracked). The file is runtime config by
    design (the container deployment regenerates it the same way on boot).
    """
    if not spa_dir:
        return
    origin = f"http://127.0.0.1:{port}"
    # The SPA resolves the WS origin from window.location (same-origin), so only
    # the API root + Auth0 flag need injecting here.
    content = (
        "window._env_ = {\n"
        f'  "REACT_APP_API_ROOT_URL": "{origin}",\n'
        '  "REACT_APP_USE_AUTH0": "false",\n'
        "};\n"
    )
    with contextlib.suppress(OSError):
        (Path(spa_dir) / "env-config.js").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------- child processes
def _spawn(name: str, cmd: list[str], env: dict[str, str]) -> subprocess.Popen:
    # Redirect each child's stdout+stderr to a per-child file under the logs dir
    # so a Daphne/worker/beat crash leaves a durable traceback — essential once
    # the Phase-2 Tauri shell launches this with no attached console.
    log_path = paths.logs_dir() / f"{name}.log"
    print(f"[oc-desktop] starting {name} (log: {log_path})")
    log_file = open(log_path, "a")
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=log_file, stderr=subprocess.STDOUT)
    except Exception:
        # Don't leak the fd if process creation fails (e.g. bad executable).
        log_file.close()
        raise
    # Track for shutdown only after a successful spawn.
    _log_handles.append(log_file)
    _children.append(proc)
    return proc


def _start_daphne(env: dict[str, str], port: int) -> subprocess.Popen:
    return _spawn(
        "daphne",
        [
            sys.executable,
            "-m",
            "daphne",
            "-b",
            "127.0.0.1",
            "-p",
            str(port),
            "config.asgi:application",
        ],
        env,
    )


def _start_worker(env: dict[str, str]) -> subprocess.Popen:
    return _spawn(
        "celery-worker",
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "config.celery_app",
            "worker",
            "-l",
            "INFO",
            "--concurrency=1",
            "-Q",
            "celery,worker_uploads",
        ],
        env,
    )


def _start_beat(env: dict[str, str]) -> subprocess.Popen:
    schedule_file = str(paths.subdir("celery-broker") / "beat-schedule")
    return _spawn(
        "celery-beat",
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "config.celery_app",
            "beat",
            "-l",
            "INFO",
            "-s",
            schedule_file,
        ],
        env,
    )


# ---------------------------------------------------------------------- shutdown
def _shutdown(*_args) -> None:
    for proc in reversed(_children):
        if proc.poll() is None:
            with contextlib.suppress(Exception):
                proc.terminate()
    deadline = time.time() + 10
    for proc in reversed(_children):
        with contextlib.suppress(Exception):
            proc.wait(timeout=max(0, deadline - time.time()))
    for proc in reversed(_children):
        if proc.poll() is None:
            with contextlib.suppress(Exception):
                proc.kill()
    for handle in _log_handles:
        with contextlib.suppress(Exception):
            handle.close()


def main() -> None:
    os.chdir(Path(__file__).resolve().parents[2])  # repo root (manage.py lives here)
    env = _base_env()
    _ensure_dirs()

    _start_postgres(env)
    _manage(env, "migrate", "--noinput")
    _first_run_bootstrap(env)
    if _manage(env, "collectstatic", "--noinput", check=False) != 0:
        print(
            "[oc-desktop] WARNING: collectstatic failed; Django admin/DRF static "
            "assets may be missing (the SPA itself is served from dist/)."
        )

    spa_dir = _resolve_spa_dir(env)

    # Single teardown path: atexit runs _shutdown on every exit (normal return,
    # SystemExit from a signal, or an unhandled exception). The signal handlers
    # just raise SystemExit so they funnel through the same hook rather than
    # calling _shutdown themselves (which would run it twice).
    atexit.register(_shutdown)

    def _handle_signal(_signum, _frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    with contextlib.suppress(AttributeError, ValueError):
        signal.signal(signal.SIGTERM, _handle_signal)

    _start_worker(env)
    _start_beat(env)
    # Reserve the port immediately before Daphne binds it (not before the slow
    # worker/beat spawn) to keep the release-then-rebind window near-instant.
    port = _free_port()
    _write_env_config(spa_dir, port)
    _start_daphne(env, port)

    base = f"http://127.0.0.1:{port}"
    url = f"{base}/"
    print(f"[oc-desktop] OpenContracts is starting at {url}")
    # Health-check the API endpoint, NOT ``/``: when the SPA isn't built, ``/``
    # redirects to the (absent) :3000 dev server and every poll would error,
    # falsely reporting the server as down even though Daphne is up.
    if not _wait_for_http(f"{base}/api/health/", timeout=60):
        print(
            "[oc-desktop] WARNING: server did not answer within 60s; opening the "
            "browser anyway — it may show a connection error until Daphne is up."
        )
    print(
        "\n"
        "  ──────────────────────────────────────────────────────\n"
        f"   OpenContracts is running:  {url}\n"
        f"   Log in as user '{LOCAL_USERNAME}' with the password you chose\n"
        "   on first run.\n"
        "   To stop the app, press Ctrl+C in this window.\n"
        "  ──────────────────────────────────────────────────────\n"
    )
    with contextlib.suppress(Exception):
        webbrowser.open(url)

    # Supervise: return (atexit then tears everything down) if any child dies.
    while True:
        for proc in _children:
            if proc.poll() is not None:
                print(f"[oc-desktop] child pid {proc.pid} exited; shutting down.")
                return
        time.sleep(1)


def _wait_for_http(url: str, timeout: int = 60) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(1)
    return False


if __name__ == "__main__":
    main()
