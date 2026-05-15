"""Request-scoped cache for granted permission sets.

Tier 2 of the two-tier mitigation described in issue #1640 (the follow-up to
PR #1637, which centralized authorization in ``Manager.user_can`` /
``obj.user_can`` → ``_default_user_can``). The accompanying Tier 1 is the
per-instance memoization that lives inside
``opencontractserver.utils.permissioning.get_users_permissions_for_obj``.

This module mirrors the idiom established by
``opencontractserver.conversations.query_optimizer``:

- A small class with explicit ``invalidate`` / ``invalidate_caches`` methods.
- A ``get_request_optimizer(request)`` helper that lazy-attaches the
  optimizer to the request once, keyed by an attribute name shared with
  :mod:`opencontractserver.constants.permissioning`.
- ``None``-tolerant: outside the HTTP request lifecycle (Celery tasks,
  management commands) callers get a one-shot optimizer that goes away
  with the local scope.

See ``docs/architecture/query_permission_patterns.md`` for how this fits
into the wider visibility / permission stack.
"""

from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from opencontractserver.constants.permissioning import REQUEST_OPTIMIZER_ATTR


class PermissionQueryOptimizer:
    """Per-request cache for ``get_users_permissions_for_obj`` results.

    Keyed by ``(user_id, content_type_id, instance_pk, include_group_permissions)``.
    Unlike ``ConversationQueryOptimizer``, a single optimizer instance is
    shared across all users active on a request — every cache entry tags
    the ``user_id`` explicitly. This keeps the request-attribute count
    down and lets the Manager/QuerySet ``user_can`` API stay user-agnostic
    at the surface.

    The cache stores ``frozenset[str]`` (immutable). Callers receive
    ``set[str]`` copies because the consumer in ``_default_user_can``
    mutates the returned set locally when handling compound permission
    checks (CRUD / ALL).
    """

    def __init__(self) -> None:
        # instance_pk slot is ``Any`` because models may use int / UUID / str PKs.
        self._cache: dict[tuple[int, int, Any, bool], frozenset[str]] = {}

    @staticmethod
    def _resolve_content_type_id(instance: Model) -> int:
        """Return the cached content-type id for ``instance``'s model."""

        return ContentType.objects.get_for_model(type(instance)).id

    def get_granted(
        self,
        user: Any,
        instance: Model,
        *,
        include_group_permissions: bool = True,
    ) -> set[str]:
        """Return the set of guardian permission codenames the user has on
        ``instance``, consulting the request-scoped cache first.

        Anonymous / unauthenticated users bypass the cache (their state
        isn't reusable across calls and we never want to retain the
        sentinel).

        The Tier 1 per-instance cache inside
        ``get_users_permissions_for_obj`` still runs on miss; both layers
        compose without double-caching the same value.
        """

        # Lazy import to avoid pulling permissioning (which touches
        # ``get_user_model()`` at import time via the GraphQL middleware)
        # into the early startup chain.
        from opencontractserver.utils.permissioning import (
            get_users_permissions_for_obj,
        )

        user_id = getattr(user, "id", None)
        if user_id is None or not getattr(user, "is_authenticated", False):
            return get_users_permissions_for_obj(
                user=user,
                instance=instance,
                include_group_permissions=include_group_permissions,
            )

        key = (
            user_id,
            self._resolve_content_type_id(instance),
            instance.pk,
            bool(include_group_permissions),
        )
        cached = self._cache.get(key)
        if cached is not None:
            return set(cached)

        granted = get_users_permissions_for_obj(
            user=user,
            instance=instance,
            include_group_permissions=include_group_permissions,
        )
        self._cache[key] = frozenset(granted)
        return granted

    def invalidate(
        self,
        *,
        user_id: int | None = None,
        instance: Model | None = None,
        content_type_id: int | None = None,
        instance_pk: Any | None = None,
    ) -> None:
        """Drop cache entries matching the supplied coordinates.

        - No coordinates → clear the entire cache.
        - Any subset of ``user_id`` / ``content_type_id`` / ``instance_pk``
          → drop entries that match every supplied slot (others wildcard).
        - ``instance`` is a shorthand for the ``(content_type_id,
          instance_pk)`` pair. Pass ``instance`` OR the explicit ids, not
          both — mixing them raises ``ValueError``.
        """

        if instance is not None:
            if content_type_id is not None or instance_pk is not None:
                raise ValueError(
                    "Pass `instance` OR explicit `content_type_id`/`instance_pk`, not both."
                )
            content_type_id = self._resolve_content_type_id(instance)
            instance_pk = instance.pk

        if user_id is None and content_type_id is None and instance_pk is None:
            self._cache.clear()
            return

        keys_to_drop = [
            key
            for key in self._cache
            if (user_id is None or key[0] == user_id)
            and (content_type_id is None or key[1] == content_type_id)
            and (instance_pk is None or key[2] == instance_pk)
        ]
        for key in keys_to_drop:
            del self._cache[key]

    def invalidate_caches(self) -> None:
        """Clear the entire cache.

        Naming parity with ``ConversationQueryOptimizer.invalidate_caches``.
        """

        self.invalidate()


def get_request_optimizer(request: Any) -> PermissionQueryOptimizer:
    """Return the ``PermissionQueryOptimizer`` attached to ``request``,
    lazy-creating one on first call.

    ``request=None`` is supported for callers outside the HTTP lifecycle
    (Celery tasks, management commands, signal handlers): the function
    returns a fresh optimizer that the caller can use locally — it goes
    out of scope with the caller. This keeps the optimizer call shape
    uniform across HTTP and non-HTTP code paths without forcing every
    call site to branch on ``request is None``.
    """

    if request is None:
        return PermissionQueryOptimizer()

    optimizer = getattr(request, REQUEST_OPTIMIZER_ATTR, None)
    if optimizer is None:
        optimizer = PermissionQueryOptimizer()
        setattr(request, REQUEST_OPTIMIZER_ATTR, optimizer)
    return optimizer
