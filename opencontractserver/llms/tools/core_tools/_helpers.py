"""Shared helpers used across the ``core_tools`` package.

These utilities are kept in a private module so that every category-specific
sub-module can import them without forming circular dependencies among the
public sibling modules.
"""

from functools import partial

# --------------------------------------------------------------------------- #
# Async DB helper                                                             #
#                                                                             #
# We need a robust helper that **always** executes the wrapped function in a  #
# *fresh* worker thread so the database connection opened inside that thread  #
# is guaranteed to be valid for the lifetime of the call.  Re-using the same  #
# thread between subsequent invocations (the default behaviour when           #
# ``thread_sensitive=True``) risks the connection becoming stale once Django  #
# closes it at the end of a test case – ultimately raising the dreaded "the   #
# connection is closed" OperationalError when the old thread is re-used.      #
#                                                                             #
# To avoid this we create a partially-applied wrapper with                    #
# ``thread_sensitive=False`` irrespective of whether Channels is installed.   #
# We fall back to ``asgiref.sync.sync_to_async`` when Channels is unavailable.#
# --------------------------------------------------------------------------- #

try:
    from channels.db import database_sync_to_async as _database_sync_to_async

    _db_sync_to_async = partial(_database_sync_to_async, thread_sensitive=False)
except ModuleNotFoundError:  # Channels not installed – fall back gracefully
    from asgiref.sync import sync_to_async as _sync_to_async

    _db_sync_to_async = partial(_sync_to_async, thread_sensitive=False)


def _token_count(text: str) -> int:
    """Naive whitespace-based token counting helper.

    Returns the number of whitespace-separated words in *text*.
    """
    return len(text.split())


def _apply_ndiff_patch(original: str, diff_text: str) -> str:
    """Return *patched* text by applying an ``ndiff``-style diff.

    Raises ``ValueError`` when the diff cannot be applied.
    """
    import difflib

    try:
        patched_lines = difflib.restore(diff_text.splitlines(keepends=True), 2)
        return "".join(patched_lines)
    except Exception as exc:  # pragma: no cover
        raise ValueError("Failed to apply diff_text to original note content") from exc
