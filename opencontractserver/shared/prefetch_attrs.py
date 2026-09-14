"""User-scoped Guardian prefetches with a shared grant-snapshot lifetime.

``Managers._apply_document_prefetches`` records the snapshot before permission
SQL. The grant collector and GraphQL permission fields consume it through
``permission_prefetch``. Caller-supplied private attributes without a snapshot
retain their explicit invalidation contract. Serialized models carry neither
these snapshots nor prefetched grants; workers should re-fetch by ID.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.query import ModelIterable

from opencontractserver.constants.permissioning import (
    INSTANCE_PERMS_CACHE_ATTR,
    MODEL_PERMS_CACHE_ATTR,
)
from opencontractserver.shared.grant_cache import GrantSnapshot, grant_revision

_PREFETCH_READS_ATTR = "_oc_permission_prefetch_reads"


def user_perm_attr(user_id: int | str) -> str:
    """Attr name for the user's prefetched ``*UserObjectPermission`` rows."""
    return f"_prefetched_user_perms_uid_{user_id}"


def user_group_perm_attr(user_id: int | str) -> str:
    """Attr name for the user's prefetched ``*GroupObjectPermission`` rows."""
    return f"_prefetched_user_group_perms_uid_{user_id}"


class _PermissionPrefetchIterable(ModelIterable):
    def __iter__(self):
        user_id = getattr(self.queryset.query, "_oc_permission_prefetch_user_id")
        for instance in super().__iter__():
            # ModelIterable runs before Django's separate permission prefetch
            # queries, including when the queryset is consumed in chunks.
            snapshots = instance.__dict__.setdefault(_PREFETCH_READS_ATTR, {})
            snapshots[user_id] = GrantSnapshot(
                transaction.get_connection(instance._state.db),
                grant_revision(instance, user_id),
                user_id=user_id,
            )
            yield instance


def track_permission_prefetches(queryset, user_id):
    # Query.clone() preserves this metadata. Keep an actual ModelIterable class
    # for nested Prefetch validation and queryset serialization.
    queryset.query._oc_permission_prefetch_user_id = user_id
    queryset._iterable_class = _PermissionPrefetchIterable
    return queryset


def discard_permission_prefetch(instance, user_id):
    instance.__dict__.pop(user_perm_attr(user_id), None)
    instance.__dict__.pop(user_group_perm_attr(user_id), None)
    getattr(instance, _PREFETCH_READS_ATTR, {}).pop(user_id, None)


def permission_prefetch(instance, user_id, *, groups=False):
    """Return current prefetched rows, or let the caller query them afresh."""
    snapshot = getattr(instance, _PREFETCH_READS_ATTR, {}).get(user_id)
    if snapshot is not None and not snapshot.valid(
        transaction.get_connection(instance._state.db), allow_committed=True
    ):
        discard_permission_prefetch(instance, user_id)
    attr = user_group_perm_attr(user_id) if groups else user_perm_attr(user_id)
    return getattr(instance, attr, None)


def discard_serialized_permission_state(state):
    for attr in (
        INSTANCE_PERMS_CACHE_ATTR,
        MODEL_PERMS_CACHE_ATTR,
        _PREFETCH_READS_ATTR,
        "_perm_cache",
        "_user_perm_cache",
        "_group_perm_cache",
    ):
        state.pop(attr, None)
    prefixes = (user_perm_attr(""), user_group_perm_attr(""))
    for key in [key for key in state if key.startswith(prefixes)]:
        del state[key]
