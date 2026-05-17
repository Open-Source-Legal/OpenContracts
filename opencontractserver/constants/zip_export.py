"""
Constants for zip file export memory management.

These tune the in-process buffering strategy used by V2 corpus exports so
that ``build_corpus_v2_zip`` does not have to materialise an entire corpus
— including every document's binary PDF content — in heap memory before
the import (or persistent write) consumes it.

All limits can be overridden via Django settings with the same name and via
the matching environment variable consumed in ``config/settings/base.py``.
Example: ``settings.EXPORT_SPOOL_MAX_SIZE_BYTES = 256 * 1024 * 1024``.
"""

from django.conf import settings

# Default in-memory threshold for the ``SpooledTemporaryFile`` used by
# ``build_corpus_v2_zip``.  Bytes written below this size stay in heap; once
# the spool exceeds it, ``tempfile`` transparently rolls over to an on-disk
# file the OS can page out.  100 MB is large enough that a typical small/
# medium corpus never touches disk, but small enough that a 200 × 5 MB-PDF
# corpus spills out of the worker's heap instead of OOM-ing it.
#
# This is the *default* — do NOT import this constant at module load and
# freeze it. Tests rely on ``@override_settings(EXPORT_SPOOL_MAX_SIZE_BYTES=
# ...)`` to force the disk-rollover path; call sites must read the current
# value via :func:`get_export_spool_max_size_bytes` so the override is
# honoured at runtime.
DEFAULT_EXPORT_SPOOL_MAX_SIZE_BYTES = 100 * 1024 * 1024


def get_export_spool_max_size_bytes() -> int:
    """Return the active spool-rollover threshold for V2 exports.

    Reads ``settings.EXPORT_SPOOL_MAX_SIZE_BYTES`` lazily so
    ``@override_settings`` and runtime settings reloads (Celery worker
    restarts, env-driven changes) take effect without re-importing the
    constants module. Falls back to
    :data:`DEFAULT_EXPORT_SPOOL_MAX_SIZE_BYTES` when unset.
    """
    return getattr(
        settings,
        "EXPORT_SPOOL_MAX_SIZE_BYTES",
        DEFAULT_EXPORT_SPOOL_MAX_SIZE_BYTES,
    )
