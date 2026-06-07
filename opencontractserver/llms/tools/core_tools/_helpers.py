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


def get_user_or_none(user_id: int | None):
    """Return the ``User`` row for ``user_id`` or ``None`` (anonymous / missing).

    Shared by the tool modules so the "resolve the injected ``user_id`` into a
    user, tolerating ``None`` and stale ids" step is written once.

    Return type is intentionally inferred — ``User`` here is the result of
    ``get_user_model()`` (a runtime variable, not a type alias) so a quoted
    annotation would still trip mypy's ``valid-type`` check.
    """
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    if user_id is None:
        return None
    try:
        return user_model.objects.get(pk=user_id)
    except user_model.DoesNotExist:
        return None


def require_user(user_id: int | None, caller: str):
    """Resolve ``user_id`` to a ``User`` or raise ``PermissionError``.

    The write tools (e.g. ``rename_document`` / ``delete_document``) require an
    authenticated, existing user. This collapses the two distinct guard
    branches those tools repeated into one helper, preserving the same
    ``caller``-specific messages for each failure mode:

    * ``user_id is None`` (no user injected at all) →
      ``"<caller> requires an authenticated user."``
    * a stale/unknown id (no matching row) → ``"User <id> not found."``

    Read-only tools that tolerate anonymous access keep using
    :func:`get_user_or_none` instead (it returns ``None`` rather than raising).

    Return type is intentionally inferred — see :func:`get_user_or_none`.
    """
    if user_id is None:
        raise PermissionError(f"{caller} requires an authenticated user.")
    user = get_user_or_none(user_id)
    if user is None:
        raise PermissionError(f"User {user_id} not found.")
    return user


def clamp_limit(limit: int | None, default: int, maximum: int) -> int:
    """Clamp a caller-supplied ``limit`` into ``[1, maximum]``.

    Returns ``default`` when ``limit`` is ``None``, non-positive, or not
    coercible to ``int``. Shared by the listing / discovery tools so they
    all treat an LLM-supplied ``limit`` identically (an LLM occasionally
    passes ``0`` or a string).
    """
    if limit is None:
        return default
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, maximum)


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
