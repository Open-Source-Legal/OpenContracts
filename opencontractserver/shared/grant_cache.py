"""Grant-set memoization shared by instance and request permission checks."""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import contextmanager
from copy import copy
from functools import wraps
from typing import Any, NamedTuple, TypeVar, cast
from weakref import WeakValueDictionary

from django.db import DEFAULT_DB_ALIAS, transaction

from opencontractserver.constants.permissioning import (
    INSTANCE_PERMS_CACHE_ATTR,
    MODEL_PERMS_CACHE_ATTR,
)

_Collector = TypeVar("_Collector", bound=Callable[..., set[str]])


class _RevisionState(NamedTuple):
    writes: int = 0
    commits: int = 0
    connection: Any = None


class _GrantRevision:
    """Expire dependent snapshots on writes and foreign reads again on commit."""

    def __init__(self):
        self.state = _RevisionState()

    def invalidate(self, connection):
        with _revision_lock:
            self.state = self.state._replace(writes=self.state.writes + 1)

        def committed():
            with _revision_lock:
                self.state = self.state._replace(
                    commits=self.state.commits + 1, connection=connection
                )

        if connection.in_atomic_block:
            transaction.on_commit(committed, using=connection.alias)
        else:
            committed()


_revision_lock = threading.Lock()
_revisions: WeakValueDictionary[tuple, _GrantRevision] = WeakValueDictionary()


def _revision(key):
    with _revision_lock:
        revision = _revisions.get(key)
        if revision is None:
            revision = _revisions[key] = _GrantRevision()
        return revision


def grant_revision(instance, user_id):
    """Share a revision while cached snapshots or a pending write need it."""
    if getattr(instance, "pk", None) is None:
        return None
    key = (
        getattr(getattr(instance, "_state", None), "db", None) or DEFAULT_DB_ALIAS,
        instance._meta.app_label,
        instance._meta.model_name,
        instance.pk,
        user_id,
    )
    return _revision(key)


def invalidate_actor_grants(user_ids, *, using):
    """Expire actor snapshots; ``None`` targets all permission reads for the DB.

    Reverse clears, group model-grant changes and cascade deletes use the
    conservative DB scope without querying affected actors. Pending writes
    retain revisions until commit.
    """
    connection = transaction.get_connection(using)
    for user_id in user_ids:
        _revision((connection.alias, user_id)).invalidate(connection)


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


class GrantSnapshot:
    """Connection, transaction and grant revisions observed before a read.

    Prefetch consumers may reuse committed rows across connections. Grant-set
    caches keep their existing connection-local hit rule. Neither permits an
    uncommitted snapshot to cross connections.
    """

    def __init__(self, connection, revision=None, *, user_id=None):
        connection.validate_no_broken_transaction()
        self.connection = connection
        self.transaction = _read_context(connection)
        # Permission deletion also revokes direct grants that exclude groups.
        revisions = [_revision((connection.alias, None))]
        if revision is not None:
            revisions.append(revision)
        if user_id is not None:
            revisions.append(_revision((connection.alias, user_id)))
        self.revisions = [(item, item.state) for item in revisions]

    def valid(self, connection, *, allow_committed=False):
        connection.validate_no_broken_transaction()
        marker = self.transaction
        if marker is not None and not marker.valid():
            return False
        if self.connection is not connection and not (
            allow_committed and (marker is None or marker.committed)
        ):
            return False
        # A writer's own final reads stay warm after commit. Other connections
        # may have read the old committed rows while this write was pending.
        for revision, state in self.revisions:
            current = revision.state
            if state.writes != current.writes or (
                state.commits != current.commits
                and current.connection is not self.connection
            ):
                return False
        return True


class PermissionGrantCache(dict):
    """Shared instance/request storage; values remain immutable granted sets."""

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._contexts: dict[Any, GrantSnapshot] = {}
        self._generation = 0

    def get_or_compute(
        self, key, compute, *, using=None, revision=None, user_id=None
    ) -> set[str]:
        connection = transaction.get_connection(using)
        with self._lock:
            value = self.get(key)
            context = self._contexts.get(key)
            if value is not None and context is not None and context.valid(connection):
                return set(value)
            self.pop(key, None)
            self._contexts.pop(key, None)
            generation = self._generation
        snapshot = GrantSnapshot(connection, revision, user_id=user_id)
        # ORM work stays outside the cache lock. A simultaneous invalidation
        # makes this result ineligible for reuse, even if the cache was empty.
        granted = compute()
        with self._lock:
            if generation == self._generation and snapshot.valid(connection):
                self[key] = frozenset(granted)
                self._contexts[key] = snapshot
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


def model_permission_grants(user):
    """Collect backend model grants with the same transaction/actor lifetime.

    The copy drops backend caches through PermissionStateMixin. Computing on a
    separate User avoids sharing Django's mutable caches between connections.
    """
    cache = getattr(user, MODEL_PERMS_CACHE_ATTR, None)
    if cache is None:
        cache = user.__dict__.setdefault(MODEL_PERMS_CACHE_ATTR, PermissionGrantCache())
    user_id = getattr(user, "id", None)
    return cache.get_or_compute(
        (user_id, user.is_active, user.is_superuser),
        lambda: copy(user).get_all_permissions(),
        using=getattr(getattr(user, "_state", None), "db", None),
        user_id=user_id,
    )


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
                revision=grant_revision(instance, user_id),
                user_id=user_id if include_group_permissions else None,
            )
        except Exception:
            if (
                not cache
                and getattr(instance, INSTANCE_PERMS_CACHE_ATTR, None) is cache
            ):
                delattr(instance, INSTANCE_PERMS_CACHE_ATTR)
            raise

    return cast(_Collector, cached)


def invalidate_permission_grants(instance, user_id, *, request=None):
    """Expire held snapshots now and foreign connection reads again on commit."""
    from opencontractserver.shared.prefetch_attrs import discard_permission_prefetch

    revision = grant_revision(instance, user_id)
    if revision is not None:
        revision.invalidate(transaction.get_connection(instance._state.db))
    discard_permission_prefetch(instance, user_id)
    cache = getattr(instance, INSTANCE_PERMS_CACHE_ATTR, None)
    if isinstance(cache, PermissionGrantCache):
        cache.drop_for_user(user_id)
    elif cache is not None:
        for key in [key for key in cache if key[0] == user_id]:
            cache.pop(key, None)
    if request is not None:
        from opencontractserver.utils.permission_optimizer import get_request_optimizer

        get_request_optimizer(request).invalidate(user_id=user_id, instance=instance)


@contextmanager
def permission_grant_change(instance, user_id=None, *, groups=False, request=None):
    """Commit a caller-authorized grant change and its invalidation together.

    Group edits expire permission snapshots for this database without
    enumerating members. Actor/public/creator policy stays with the caller.
    """
    using = getattr(getattr(instance, "_state", None), "db", None)
    with transaction.atomic(using):
        yield
        if groups:
            invalidate_actor_grants((None,), using=using)
        else:
            invalidate_permission_grants(instance, user_id, request=request)
