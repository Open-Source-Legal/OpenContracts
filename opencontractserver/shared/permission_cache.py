"""Request-scoped permission cache for ``_default_user_can``.

Phase A of permission-centralization (issue #1655) introduces a single
default-branch authorization body — ``_default_user_can`` — that all
``Manager.user_can`` overrides delegate to. Many request lifecycles call
that body redundantly for the same ``(user, instance, permission)`` tuple
(e.g. a GraphQL resolver that fans out permission checks across a list of
documents); this module gives the hot path a read-only cache that the
caller opts into via :func:`permission_cache_scope`.

Design constraints:

- **Dormant by default.** The cache is keyed by a ``ContextVar`` whose
  default is ``None``. Without an active scope, ``cached_user_can``
  returns the miss sentinel and ``_default_user_can`` runs as today.
- **Read-only inside scope.** Callers MUST NOT mutate permissions
  (``set_permissions_for_obj_to_user``, ``assign_perm``, etc.) inside
  an active scope — the cache does not invalidate on writes. Mutations
  should happen at mutation boundaries, before entering the scope.
- **Cache key includes ``include_group_permissions``**. Flipping that
  flag changes the answer for group-shared objects, so it MUST be part
  of the key. Forgetting it would silently return stale answers when
  one caller passes ``False`` and another passes ``True`` on the same
  instance within the same request.
- **Unsaved instances are skipped.** Instances with ``pk is None``
  cannot be uniquely keyed, so ``store_user_can`` is a no-op and
  ``cached_user_can`` returns ``MISS``.

The cache is intentionally simple: a plain dict held on a ``ContextVar``.
Issue #1640 tracks a more elaborate two-tier request-scoped optimizer;
this module ships the minimum that ``_default_user_can`` needs.

**Activation status (Phase A):** the scope is implemented but no
production caller enters it yet — no GraphQL middleware, WebSocket
handler, or Celery task wraps work in ``permission_cache_scope()``.
The cache stays dormant until a future Phase B change wires it in.
This is intentional: shipping the cache primitive separately lets us
verify the API surface and key shape with invariant tests before
activating it in the request path. Tracking issue: #1655 follow-up.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any

_SENTINEL_MISS = object()

# Exported so callers can perform an explicit ``is MISS`` identity check.
# ``cached_user_can`` returns this sentinel on both "no active scope" and
# "key not in cache" — semantically the same: the caller must compute.
MISS = _SENTINEL_MISS

_perm_cache: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "opencontracts_permission_cache",
    default=None,
)


# TODO(issue #1655): activate this scope in Phase B by wrapping the
# GraphQL request/Celery-task/WebSocket entrypoints. Until that happens
# this function has no production callers and the request-scoped cache
# is dormant. The activation audit lives in the parent issue —
# every wrap site must enter the scope *after* mutations land (see the
# mutation-invalidation contract in the docstring below).
@contextmanager
def permission_cache_scope():
    """Enter a read-only request-scoped permission cache.

    Inside the scope, ``_default_user_can`` will reuse prior boolean
    answers for the same ``(user_id, app_label, model_name, pk,
    permission, include_group_permissions)`` tuple instead of re-running
    the guardian lookup.

    The scope is read-only: callers MUST NOT mutate permissions inside
    it. Typical usage wraps a GraphQL request, a Celery task, or a
    WebSocket message handler — entering before any permission check
    runs and exiting before any mutation.

    **Mutation-invalidation contract (Phase B activation hazard).** The
    cache does NOT invalidate on writes. Calling
    ``set_permissions_for_obj_to_user``, guardian's ``assign_perm`` /
    ``remove_perm``, or anything that adds the user to a group inside
    the scope leaves stale boolean answers in the cache. Any subsequent
    ``user_can`` check on the same ``(user, instance, permission)`` tuple
    will return the pre-mutation value until the scope exits. The Phase B
    wire-up MUST therefore enter the scope **after** all mutations land
    (or split read- and write-phases of the request) — there is no
    safety net here. This intentional simplicity is the reason the
    scope ships dormant in Phase A: it gives us time to audit every
    activation site for accidental mid-scope writes before flipping it
    on.

    Nested scopes are supported (each ``set`` allocates a fresh dict
    bound to the outer scope's token); on exit, the previous scope's
    cache is restored. The default ``None`` is restored at the outermost
    exit, so accidental misuse outside a scope is safe (it just bypasses
    the cache).

    **Nested scopes do NOT inherit the parent scope's cached entries.**
    Each ``permission_cache_scope()`` allocates a fresh empty dict, so a
    permission computed in an outer scope is re-computed if the same
    tuple is queried inside an inner scope. This is safe (no stale
    answers) but means nesting offers no caching benefit until/unless a
    future variant joins existing scopes.
    """
    token = _perm_cache.set({})
    try:
        yield
    finally:
        _perm_cache.reset(token)


def cached_user_can(
    user_id: Any,
    app_label: str,
    model_name: str,
    pk: Any,
    permission: str,
    include_group_permissions: bool,
) -> Any:
    """Return a cached boolean answer or :data:`MISS` if not cached.

    Returns :data:`MISS` (a sentinel) when:
    - no scope is active (``_perm_cache`` default ``None``);
    - the instance has ``pk is None`` (unsaved, cannot key);
    - the tuple is not in the scope's dict.

    Callers MUST use ``is`` identity to test the miss sentinel — a
    cached ``False`` is a legitimate hit.
    """
    cache = _perm_cache.get()
    if cache is None or pk is None:
        return _SENTINEL_MISS
    return cache.get(
        (user_id, app_label, model_name, pk, permission, include_group_permissions),
        _SENTINEL_MISS,
    )


def store_user_can(
    user_id: Any,
    app_label: str,
    model_name: str,
    pk: Any,
    permission: str,
    include_group_permissions: bool,
    result: bool,
) -> None:
    """Store a boolean answer for the next ``cached_user_can`` lookup.

    No-op when no scope is active or the instance has ``pk is None``
    (unsaved). Always returns ``None``; the result parameter is the
    cached value, not a return passthrough.
    """
    cache = _perm_cache.get()
    if cache is None or pk is None:
        return
    cache[
        (user_id, app_label, model_name, pk, permission, include_group_permissions)
    ] = result
