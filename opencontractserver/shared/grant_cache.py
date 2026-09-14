"""Grant-set memoization shared by instance and request permission checks."""

from __future__ import annotations

import threading
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from django.db import transaction

from opencontractserver.constants.permissioning import INSTANCE_PERMS_CACHE_ATTR

_Collector = TypeVar("_Collector", bound=Callable[..., set[str]])


class _TransactionRead:
    """One commit callback shared by reads in the current savepoint scope.

    Django removes callbacks on rollback. Inspecting its callback queue also
    catches rollback when an Atomic object is reused, without adding SQL or
    wrapping callers' transactions. One indexed comparison validates a read;
    a changed callback position conservatively expires it.
    """

    def __init__(self, connection):
        self.connection = connection
        self.savepoints = tuple(connection.savepoint_ids)
        self.committed = False
        self.callback: Callable[[], None] | None = self._commit
        self.index = len(connection.run_on_commit)
        transaction.on_commit(self.callback, using=connection.alias)

    def _commit(self):
        self.committed = True
        self.callback = None

    def valid(self):
        pending = self.connection.run_on_commit
        return self.committed or (
            self.index < len(pending) and pending[self.index][1] is self.callback
        )


def _read_context(connection):
    if not connection.in_atomic_block:
        return None
    marker = getattr(connection, "_oc_grant_cache_transaction", None)
    if (
        marker is None
        or marker.committed
        or marker.savepoints != tuple(connection.savepoint_ids)
        or not marker.valid()
    ):
        marker = _TransactionRead(connection)
        connection._oc_grant_cache_transaction = marker
    return marker


class PermissionGrantCache(dict):
    """Shared instance/request storage; values remain immutable granted sets."""

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._contexts: dict[Any, tuple[Any, _TransactionRead | None]] = {}
        self._generation = 0

    def get_or_compute(self, key, compute, *, using=None) -> set[str]:
        connection = transaction.get_connection(using)
        connection.validate_no_broken_transaction()
        with self._lock:
            value = self.get(key)
            context = self._contexts.get(key)
            if (
                value is not None
                and context is not None
                and (
                    context[0] is connection
                    and (context[1] is None or context[1].valid())
                )
            ):
                return set(value)
            self.pop(key, None)
            self._contexts.pop(key, None)
            generation = self._generation
        marker = _read_context(connection)
        # ORM work stays outside the cache lock. A simultaneous invalidation
        # makes this result ineligible for reuse, even if the cache was empty.
        granted = compute()
        with self._lock:
            if generation == self._generation and (marker is None or marker.valid()):
                self[key] = frozenset(granted)
                self._contexts[key] = (connection, marker)
        return granted

    def discard_where(self, matches):
        with self._lock:
            self._generation += 1
            for key in [key for key in self if matches(key)]:
                del self[key]
                self._contexts.pop(key, None)

    def drop_for_user(self, user_id):
        self.discard_where(lambda key: key[0] == user_id)

    def clear(self):
        self.discard_where(lambda key: True)


def cached_permission_grants(collect: _Collector) -> _Collector:
    """Memoize an instance's grant collector using the shared transaction rules."""

    @wraps(collect)
    def cached(user, instance, include_group_permissions=True):
        user_id = getattr(user, "id", None)
        if user_id is None or not getattr(user, "is_authenticated", False):
            return collect(user, instance, include_group_permissions)
        cache = getattr(instance, INSTANCE_PERMS_CACHE_ATTR, None)
        if cache is None:
            cache = instance.__dict__.setdefault(
                INSTANCE_PERMS_CACHE_ATTR, PermissionGrantCache()
            )
        elif not isinstance(cache, PermissionGrantCache):
            # Legacy dictionaries have no transaction provenance; re-read them.
            cache = PermissionGrantCache()
            setattr(instance, INSTANCE_PERMS_CACHE_ATTR, cache)
        try:
            return cache.get_or_compute(
                (user_id, bool(include_group_permissions)),
                lambda: collect(user, instance, include_group_permissions),
                using=getattr(getattr(instance, "_state", None), "db", None),
            )
        except Exception:
            if (
                not cache
                and getattr(instance, INSTANCE_PERMS_CACHE_ATTR, None) is cache
            ):
                delattr(instance, INSTANCE_PERMS_CACHE_ATTR)
            raise

    return cast(_Collector, cached)
