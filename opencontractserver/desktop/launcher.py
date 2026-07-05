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
    # JWTs verify across them. Generated per launch when unset — an ephemeral
    # key; export DJANGO_SECRET_KEY yourself for stability across runs.
    env.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(64))
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
    """Ask the OS for a free loopback TCP port (bind :0, read, release).

    Note: there is a small TOCTOU window between releasing the probe socket here
    and Daphne binding the port below. On a single-user loopback app the risk of
    another process grabbing it in that window is negligible; hardening this into
    a bind-retry loop is a Phase-1 follow-up.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
    external = os.environ.get("DATABASE_URL")
    if external:
        env["DATABASE_URL"] = external
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
    _manage(env, "desktop_bootstrap")
    marker.write_text("ok\n", encoding="utf-8")


# --------------------------------------------------------------------------- SPA
def _resolve_spa_dir(env: dict[str, str]) -> str:
    """Locate the built SPA dist/ dir and export it for settings + WhiteNoise."""
    spa = os.environ.get("OC_DESKTOP_FRONTEND_DIR")
    if not spa:
        candidate = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        if candidate.is_dir():
            spa = str(candidate)
    if spa:
        env["OC_DESKTOP_FRONTEND_DIR"] = spa
    return spa or ""


def _write_env_config(spa_dir: str, port: int) -> None:
    """Point the SPA's runtime config at this Daphne origin (same-origin API)."""
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
    print(f"[oc-desktop] starting {name}: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, env=env)
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
    port = _free_port()
    _write_env_config(spa_dir, port)

    atexit.register(_shutdown)

    def _handle_signal(_signum, _frame):
        _shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    with contextlib.suppress(AttributeError, ValueError):
        signal.signal(signal.SIGTERM, _handle_signal)

    _start_worker(env)
    _start_beat(env)
    _start_daphne(env, port)

    url = f"http://127.0.0.1:{port}/"
    print(f"[oc-desktop] OpenContracts is starting at {url}")
    _wait_for_http(url, timeout=60)
    with contextlib.suppress(Exception):
        webbrowser.open(url)

    # Supervise: exit if any child dies.
    try:
        while True:
            for proc in _children:
                if proc.poll() is not None:
                    print(f"[oc-desktop] child pid {proc.pid} exited; shutting down.")
                    return
            time.sleep(1)
    finally:
        _shutdown()


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
