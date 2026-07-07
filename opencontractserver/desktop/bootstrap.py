"""Self-bootstrap for the one-step desktop launcher (``python oc-desktop.py``).

Standard library ONLY — this module runs before any third-party dependency is
installed. It turns a bare source checkout + a stock CPython into a running
desktop app with no manual pip/venv knowledge:

1. Verify the Python version (the embedded-Postgres wheels only cover a range).
2. Create a private virtualenv under the per-user app-data dir and
   ``pip install -r requirements/desktop.txt`` into it on first run (re-run
   automatically whenever the requirement files change).
3. Re-exec the launcher inside that virtualenv.

The heavy lifting (Postgres, migrate, Daphne, Celery) stays in
``opencontractserver.desktop.launcher``, which only ever runs once dependencies
are importable. See ``docs/deployment/desktop_packaging.md``.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

from opencontractserver.desktop import paths

# pgserver (embedded PostgreSQL) publishes wheels for CPython 3.9–3.12 only, and
# the backend targets 3.10+; outside this window ``pip install`` would try (and
# almost certainly fail) to build native packages from source on an end-user
# machine, so fail fast with a human answer instead.
MIN_PYTHON = (3, 10)
MAX_PYTHON_EXCLUSIVE = (3, 13)

# Set on the re-exec'ed child so a broken install can't recurse forever.
_REEXEC_GUARD_ENV = "OC_DESKTOP_BOOTSTRAP_CHILD"

# Local login account seeded by the desktop_bootstrap management command.
LOCAL_USERNAME = "desktop"
# Django's AUTH_PASSWORD_VALIDATORS are form/serializer-level and never run for
# this account (`create_superuser`/`set_password` bypass them), so enforce a
# floor ourselves — it is a superuser.
LOGIN_MIN_LENGTH = 8

# Prompt strings precomputed outside the password-handling flow, and NO
# identifier matching /password/i may feed a print() below: CodeQL's
# py/clear-text-logging-sensitive-data treats any such NAME as sensitive data
# (which is why the length floor is LOGIN_MIN_LENGTH, not MIN_PASSWORD_*) and
# flags the print as clear-text logging even though no secret is in the string.
_ASK_MSG = f"  Password (min {LOGIN_MIN_LENGTH} characters): "
_TOO_SHORT_MSG = f"  Too short — use at least {LOGIN_MIN_LENGTH} characters."
_NO_MATCH_MSG = "  Passwords did not match — try again."

# Modules whose presence marks the desktop requirement set as installed. Chosen
# to span the distinct dependency groups (Django stack, ASGI server, task queue,
# embedded DB, parser) so a partially-completed install is detected.
_SENTINEL_MODULES = ("django", "daphne", "celery", "pgserver", "warp_ingest")


def repo_root() -> Path:
    """The source checkout root (``manage.py``/``oc-desktop.py`` live here)."""
    return Path(__file__).resolve().parents[2]


def prompt_for_password(username: str = LOCAL_USERNAME) -> str | None:
    """Interactively choose the local login password on the attached terminal.

    Returns None when there is no TTY, or on Ctrl+D/Ctrl+C at the prompt — the
    caller falls back to the password-less path, which self-heals on the next
    interactive run. The password is never printed, logged, or written to disk.
    Shared by the early first-run prompt below and the ``desktop_bootstrap``
    management command (its fallback when the env var isn't threaded through).
    """
    if not sys.stdin.isatty():
        return None
    import getpass

    print(
        "\nChoose a password for your local OpenContracts login "
        f"(you will sign in as user '{username}')."
    )
    while True:
        try:
            password = getpass.getpass(_ASK_MSG)
            if len(password) < LOGIN_MIN_LENGTH:
                print(_TOO_SHORT_MSG)
                continue
            if password != getpass.getpass("  Repeat password: "):
                print(_NO_MATCH_MSG)
                continue
        except (EOFError, KeyboardInterrupt):
            print(
                "\n[oc-desktop] No password chosen — you can set one on the "
                "next launch."
            )
            return None
        return password


def maybe_prompt_first_run_password() -> None:
    """Ask the one interactive question UP FRONT, before the long install.

    First runs take many minutes (dependency install, database setup); the
    password prompt used to land in the middle, after the user had walked
    away, stalling everything. Asking first makes the rest unattended. The
    answer travels to ``desktop_bootstrap`` via the process env; the launcher
    drops it from the long-lived children's env after bootstrap.
    """
    if os.environ.get("OC_DESKTOP_PASSWORD") or paths.first_run_marker().exists():
        return
    password = prompt_for_password()
    if password:
        os.environ["OC_DESKTOP_PASSWORD"] = password
        print(
            "[oc-desktop] Thanks — setup now runs unattended (several minutes "
            "on a first run)."
        )


def python_version_error(version_info: tuple[int, int] | None = None) -> str | None:
    """Return a user-facing error when this Python can't run the desktop build."""
    version = version_info or sys.version_info[:2]
    if MIN_PYTHON <= version < MAX_PYTHON_EXCLUSIVE:
        return None
    low = ".".join(map(str, MIN_PYTHON))
    high = f"{MAX_PYTHON_EXCLUSIVE[0]}.{MAX_PYTHON_EXCLUSIVE[1] - 1}"
    running = ".".join(map(str, version))
    return (
        f"OpenContracts Desktop needs Python {low}–{high}; you are running "
        f"Python {running}.\n"
        f"  Install Python {high} from https://www.python.org/downloads/ and "
        "run this again with it\n"
        f"  (Windows: `py -{high} oc-desktop.py`, macOS/Linux: "
        f"`python{high} oc-desktop.py`)."
    )


def deps_ready() -> bool:
    """True when every sentinel dependency is importable in this interpreter.

    Deliberately importability-based, not version-pinned: it lets the venv
    child, a developer environment, or an installer payload run directly. The
    accepted trade-off is that an ambient interpreter that happens to have all
    five sentinels installed (at whatever versions) bypasses the fingerprinted
    private venv — if that drifts into breakage, run inside a clean Python or
    let the private venv own the deps.
    """
    return all(importlib.util.find_spec(name) is not None for name in _SENTINEL_MODULES)


def venv_dir() -> Path:
    """The private virtualenv, kept in app-data so the checkout stays pristine."""
    return paths.subdir("venv")


def venv_python(venv_path: Path) -> Path:
    """Path of the venv's interpreter for this OS."""
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def requirement_files(root: Path) -> list[Path]:
    """The requirement files whose content pins the desktop install."""
    return [
        root / "requirements" / "desktop.txt",
        root / "requirements" / "base.txt",  # pulled in via ``-r base.txt``
    ]


def requirements_fingerprint(files: list[Path]) -> str:
    """Stable hash of the requirement files, to detect when a reinstall is due."""
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def _fingerprint_marker(venv_path: Path) -> Path:
    return venv_path / ".requirements-fingerprint"


# Install-lock: guards venv creation/dependency install against a
# double-launched first run corrupting the venv with interleaved writes.
_LOCK_FILENAME = ".install-lock"
_LOCK_STALE_SECONDS = 3600


def _lock_is_stale(lock_path: Path) -> bool:
    """True when the lock's recorded holder is provably gone (or too old)."""
    try:
        pid = int(lock_path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        pid = 0
    if pid and os.name == "posix":
        try:
            os.kill(pid, 0)  # signal 0: existence probe only
            return False
        except ProcessLookupError:
            return True
        except OSError:
            return False
    # Windows (no cheap liveness probe): fall back to age.
    with contextlib.suppress(OSError):
        return (time.time() - lock_path.stat().st_mtime) > _LOCK_STALE_SECONDS
    return True


@contextlib.contextmanager
def _install_lock(venv_path: Path):
    """Cross-process mutex around first-run environment setup.

    Two concurrent launches (a double-clicked script — plausible, since the
    first console output takes a few seconds) would interleave
    ``python -m venv`` + ``pip install`` into the same directory and corrupt
    it beyond what a non-technical user can recover from.
    ``O_CREAT | O_EXCL`` is an atomic create-or-fail on every OS; a stale
    lock from a crashed holder is reclaimed via PID liveness (POSIX) or age.
    """
    paths.ensure_private_dir(venv_path.parent)
    lock_path = venv_path.parent / _LOCK_FILENAME
    for attempt in (1, 2):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"{os.getpid()}\n")
            break
        except FileExistsError:
            if attempt == 2 or not _lock_is_stale(lock_path):
                sys.exit(
                    "[oc-desktop] Another OpenContracts setup appears to be "
                    "running already.\n  Wait for it to finish. If you are "
                    "sure none is running, delete\n  "
                    f"{lock_path}\n  and run this again."
                )
            with contextlib.suppress(OSError):
                lock_path.unlink()
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock_path.unlink()


def _install_dependencies(root: Path, venv_path: Path) -> None:  # pragma: no cover
    """Create/refresh the private venv and install the desktop requirements."""
    vpy = venv_python(venv_path)
    if not vpy.exists():
        print(
            "[oc-desktop] First run: creating a private Python environment under\n"
            f"             {venv_path}\n"
            "             (your system Python is not modified)."
        )
        # Pre-create the venv dir (and the app-data root) with user-private
        # permissions BEFORE `python -m venv` runs — venv would otherwise be
        # the first thing to create the app-data root, with umask defaults
        # that a later mkdir(mode=..., exist_ok=True) can never tighten.
        paths.ensure_private_dir(venv_path)
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                check=True,
            )
        except subprocess.CalledProcessError:
            # Debian/Ubuntu system Pythons ship without the venv module unless
            # python3-venv is installed — give the exact fix, not pip guidance.
            sys.exit(
                "[oc-desktop] Could not create the private Python environment "
                "(see the output above).\n  On Ubuntu/Debian this usually means "
                "the venv module is missing — run\n  `sudo apt install "
                "python3-venv` (or `python3.12-venv` matching your Python)\n  "
                "and then run this again."
            )
    print(
        "[oc-desktop] Installing OpenContracts and its dependencies — this is a "
        "one-time step\n             and can take several minutes on a normal "
        "connection …"
    )
    # Deliberately NO --upgrade: reinstalls are gated by the requirements
    # fingerprint below, so already-satisfied range pins (pgserver, warp-ingest)
    # must not be drive-by upgraded on an unrelated requirements change.
    subprocess.run(
        [
            str(vpy),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(root / "requirements" / "desktop.txt"),
        ],
        check=True,
        cwd=str(root),
    )
    _fingerprint_marker(venv_path).write_text(
        requirements_fingerprint(requirement_files(root)), encoding="utf-8"
    )


def _venv_is_current(root: Path, venv_path: Path) -> bool:
    marker = _fingerprint_marker(venv_path)
    if not venv_python(venv_path).exists() or not marker.exists():
        return False
    return marker.read_text(encoding="utf-8").strip() == requirements_fingerprint(
        requirement_files(root)
    )


def _reexec_in_venv(
    root: Path, venv_path: Path, argv: list[str]
) -> int:  # pragma: no cover
    """Run the launcher inside the venv as a child and relay its exit code.

    A child process (not ``os.execv``) keeps behaviour identical on Windows,
    where exec replaces the console process in surprising ways. Ctrl+C is
    delivered to the whole console process group, so the child shuts the stack
    down while we simply keep waiting for it.
    """
    env = os.environ.copy()
    env[_REEXEC_GUARD_ENV] = "1"
    child = subprocess.Popen(
        [str(venv_python(venv_path)), str(root / "oc-desktop.py"), *argv],
        cwd=str(root),
        env=env,
    )
    interrupts = 0
    while True:
        try:
            return child.wait()
        except KeyboardInterrupt:
            # The child received the same Ctrl+C and is tearing down; wait for
            # it. Escape hatch: a third Ctrl+C force-kills a hung child so a
            # user is never stuck with an unstoppable terminal.
            interrupts += 1
            if interrupts >= 3:
                print("[oc-desktop] Force-stopping …")
                child.kill()
            continue


def main(argv: list[str] | None = None) -> None:  # pragma: no cover
    argv = list(sys.argv[1:] if argv is None else argv)

    error = python_version_error()
    if error:
        sys.exit(error)

    # Ask the single interactive question before anything slow happens, so the
    # rest of the first run needs no attention.
    maybe_prompt_first_run_password()

    if deps_ready():
        # Already inside a fully-provisioned environment (the venv child, a dev
        # environment, or an installer payload) — just run the launcher.
        from opencontractserver.desktop.launcher import main as launch

        launch()
        return

    if os.environ.get(_REEXEC_GUARD_ENV):
        sys.exit(
            "[oc-desktop] Dependencies are still missing after the automatic "
            "install.\n  Something is wrong with the Python environment — please "
            "report this at\n  "
            "https://github.com/Open-Source-Legal/OpenContracts/issues with the "
            "output above."
        )

    root = repo_root()
    venv_path = venv_dir()
    if not _venv_is_current(root, venv_path):
        try:
            _run_locked_install(root, venv_path)
        except OSError as exc:
            sys.exit(
                f"[oc-desktop] Could not write to the app's data folder ({exc}).\n"
                "  Usual causes: the disk is full, or the location is "
                "read-only.\n"
                f"  Data folder: {paths.app_data_dir()}\n"
                "  (Advanced: set OC_DESKTOP_DATA_DIR to use a different "
                "location.)"
            )
    sys.exit(_reexec_in_venv(root, venv_path, argv))


def _run_locked_install(root: Path, venv_path: Path) -> None:  # pragma: no cover
    """First-run install under the cross-process lock, with re-check."""
    with _install_lock(venv_path):
        # Re-check under the lock: a concurrent launch may have just finished
        # the install while we waited to acquire it.
        if not _venv_is_current(root, venv_path):
            try:
                _install_dependencies(root, venv_path)
            except subprocess.CalledProcessError:
                sys.exit(
                    "[oc-desktop] Automatic dependency install failed (see "
                    "the pip output above).\n  Common causes: no internet "
                    "connection, or a proxy blocking https://pypi.org.\n  "
                    "Fix the connection and run `python3 oc-desktop.py` "
                    "again — it resumes where it left off."
                )
