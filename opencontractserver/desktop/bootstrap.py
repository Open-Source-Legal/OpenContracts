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

import hashlib
import importlib.util
import os
import subprocess
import sys
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

# Modules whose presence marks the desktop requirement set as installed. Chosen
# to span the distinct dependency groups (Django stack, ASGI server, task queue,
# embedded DB, parser) so a partially-completed install is detected.
_SENTINEL_MODULES = ("django", "daphne", "celery", "pgserver", "warp_ingest")


def repo_root() -> Path:
    """The source checkout root (``manage.py``/``oc-desktop.py`` live here)."""
    return Path(__file__).resolve().parents[2]


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
    """True when every sentinel dependency is importable in this interpreter."""
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


def _install_dependencies(root: Path, venv_path: Path) -> None:  # pragma: no cover
    """Create/refresh the private venv and install the desktop requirements."""
    vpy = venv_python(venv_path)
    if not vpy.exists():
        print(
            "[oc-desktop] First run: creating a private Python environment under\n"
            f"             {venv_path}\n"
            "             (your system Python is not modified)."
        )
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
    while True:
        try:
            return child.wait()
        except KeyboardInterrupt:
            # The child received the same Ctrl+C and is tearing down; wait for it.
            continue


def main(argv: list[str] | None = None) -> None:  # pragma: no cover
    argv = list(sys.argv[1:] if argv is None else argv)

    error = python_version_error()
    if error:
        sys.exit(error)

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
            _install_dependencies(root, venv_path)
        except subprocess.CalledProcessError:
            sys.exit(
                "[oc-desktop] Automatic dependency install failed (see the pip "
                "output above).\n  Common causes: no internet connection, or a "
                "proxy blocking https://pypi.org.\n  Fix the connection and run "
                "`python3 oc-desktop.py` again — it resumes where it left off."
            )
    sys.exit(_reexec_in_venv(root, venv_path, argv))
