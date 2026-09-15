"""Constants used by the permissioning subsystem.

Centralizes the attribute names used to attach per-instance and per-request
permission caches so that the cache producer (``get_users_permissions_for_obj``,
``PermissionQueryOptimizer``) and the cache invalidator
(``set_permissions_for_obj_to_user``) stay in sync without anyone
hard-coding the strings.
"""

from __future__ import annotations

MODEL_PERMS_CACHE_ATTR = "_oc_model_permissions_cache"
"""Backend model-grant cache on a User, governed by shared grant snapshots."""

INSTANCE_PERMS_CACHE_ATTR = "_oc_granted_perms_cache"
"""Attribute on a model instance that stores the per-instance memoization
of ``get_users_permissions_for_obj`` results, keyed by
``(user_id, include_group_permissions_bool)`` → ``frozenset[str]``.

Backed by ``shared.grant_cache.PermissionGrantCache``. Both cache tiers use
the same connection/savepoint tracking and invalidation protocol. Rolled-back
reads and fills that finish after invalidation cannot become reusable answers.
``set_permissions_for_obj_to_user`` invalidates the supplied instance and request
before committing; row/user revisions expire other held instance/request snapshots
in this process and the document manager's permission prefetches. Django's
membership/model-permission m2m APIs invalidate actor/group-dependent snapshots.
Raw Guardian grants, creator/public fields and caller-supplied private prefetch
attributes retain explicit invalidation duties; see the permission guide.

``refresh_from_db()`` does not clear this attribute. Model serialization via
``PermissionStateMixin.__getstate__`` strips it and permission prefetch data; pass
task IDs and re-fetch rows inside workers.
"""

REQUEST_OPTIMIZER_ATTR = "_permission_query_optimizer"
"""Attribute on a Django/Graphene request that stores the shared
``PermissionQueryOptimizer`` instance for the request lifetime.

Tier 2 of the two-tier mitigation — the request lazily acquires one shared
``PermissionQueryOptimizer`` instance for its lifetime via
``get_request_optimizer``.

Non-HTTP staleness boundary: Tier 2 is *absent* (not stale) for callers
outside the HTTP lifecycle — ``get_request_optimizer(None)`` returns a
fresh one-shot optimizer that goes out of scope with the local block.
Celery tasks, management commands, and signal handlers therefore rely
on Tier 1 only; ``user_can(..., request=None)`` skips this tier
entirely rather than reusing a stale dict from a previous task.
"""
