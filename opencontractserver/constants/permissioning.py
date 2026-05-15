"""Constants used by the permissioning subsystem.

Centralizes the attribute names used to attach per-instance and per-request
permission caches so that the cache producer (``get_users_permissions_for_obj``,
``PermissionQueryOptimizer``) and the cache invalidator
(``set_permissions_for_obj_to_user``) stay in sync without anyone
hard-coding the strings.
"""

from __future__ import annotations

INSTANCE_PERMS_CACHE_ATTR = "_oc_granted_perms_cache"
"""Attribute on a model instance that stores the per-instance memoization
of ``get_users_permissions_for_obj`` results, keyed by
``(user_id, include_group_permissions_bool)`` → ``frozenset[str]``.

Tier 1 of the two-tier mitigation described in issue #1640. Transparent to
all callers: any code that goes through ``get_users_permissions_for_obj``
benefits automatically. Cache lifetime equals the instance lifetime; the
only path that mutates underlying state mid-request is
``set_permissions_for_obj_to_user``, which clears the relevant entries
when given the active request.
"""

REQUEST_OPTIMIZER_ATTR = "_permission_query_optimizer"
"""Attribute on a Django/Graphene request that stores the shared
``PermissionQueryOptimizer`` instance for the request lifetime.

Tier 2 of the two-tier mitigation. Mirrors the
``_conversation_query_optimizer`` naming used by
``opencontractserver.conversations.query_optimizer.get_request_optimizer``.
"""
