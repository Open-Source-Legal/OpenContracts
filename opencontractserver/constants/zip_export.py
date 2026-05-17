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

# In-memory threshold for the ``SpooledTemporaryFile`` used by
# ``build_corpus_v2_zip``.  Bytes written below this size stay in heap; once
# the spool exceeds it, ``tempfile`` transparently rolls over to an on-disk
# file the OS can page out.  100 MB is large enough that a typical small/
# medium corpus never touches disk, but small enough that a 200 × 5 MB-PDF
# corpus spills out of the worker's heap instead of OOM-ing it.
EXPORT_SPOOL_MAX_SIZE_BYTES = getattr(
    settings, "EXPORT_SPOOL_MAX_SIZE_BYTES", 100 * 1024 * 1024
)
