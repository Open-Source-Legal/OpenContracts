"""Per-user, per-OS application-data paths for the desktop build.

Pure standard library (no third-party dependency) so it is safe to import from
``config/settings/desktop.py`` at settings-load time. All locations can be
overridden with the ``OC_DESKTOP_DATA_DIR`` environment variable; the launcher
sets that once and every component (settings, Postgres data dir, media/static,
Celery filesystem broker) derives from it.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

APP_NAME = "OpenContracts"
# Environment variable the launcher exports so settings + launcher agree on the
# root without recomputing platform rules twice.
DATA_DIR_ENV = "OC_DESKTOP_DATA_DIR"


def default_app_data_dir() -> Path:
    """Return the conventional per-user data directory for this OS.

    * Windows: ``%LOCALAPPDATA%\\OpenContracts``
    * macOS:   ``~/Library/Application Support/OpenContracts``
    * Linux:   ``$XDG_DATA_HOME/OpenContracts`` (default ``~/.local/share``)
    """
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return (
            Path(os.path.expanduser("~")) / "Library" / "Application Support" / APP_NAME
        )
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path(os.path.expanduser("~")) / ".local" / "share"
    return base / APP_NAME


def app_data_dir() -> Path:
    """Resolved data dir: the ``OC_DESKTOP_DATA_DIR`` override or the OS default."""
    override = os.environ.get(DATA_DIR_ENV)
    return Path(override) if override else default_app_data_dir()


def ensure_private_dir(path: Path) -> Path:
    """``mkdir -p`` with ``0o700`` applied to EVERY level under the app-data root.

    ``Path.mkdir(mode=...)`` silently skips the mode on pre-existing dirs
    (``exist_ok=True``) and on intermediate parents (``parents=True``), so a
    tree first touched by something else — e.g. ``python -m venv`` creating
    the app-data root with umask defaults on a first run — would keep
    world-listable permissions forever. Chmod explicitly and idempotently
    instead: the app-data tree holds the full local database and uploaded
    documents, so other local accounts on a shared machine get no access.
    Chmod failures are ignored (Windows has no POSIX modes).
    """
    root = app_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    targets = [root]
    with contextlib.suppress(ValueError):
        current = root
        for part in path.relative_to(root).parts:
            current = current / part
            targets.append(current)
    for target in targets:
        with contextlib.suppress(OSError):
            os.chmod(target, 0o700)
    return path


def subdir(*parts: str, create: bool = False) -> Path:
    """Return ``app_data_dir()/parts``, optionally creating it user-private.

    See :func:`ensure_private_dir` for the permission semantics.
    """
    path = app_data_dir().joinpath(*parts)
    if create:
        ensure_private_dir(path)
    return path


# Well-known locations, all under the single data dir.
def pg_data_dir() -> Path:
    return subdir("pgdata")


def media_dir() -> Path:
    return subdir("media")


def static_dir() -> Path:
    return subdir("staticfiles")


def celery_broker_dir() -> Path:
    return subdir("celery-broker")


def logs_dir() -> Path:
    return subdir("logs")


def first_run_marker() -> Path:
    return app_data_dir() / ".bootstrapped"
