from __future__ import annotations

import logging
import threading
from functools import reduce
from typing import TYPE_CHECKING, Any, TypeVar

import django
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from guardian.shortcuts import assign_perm, remove_perm

from config.graphql.permissioning.permission_annotator.middleware import combine
from opencontractserver.constants.permissioning import INSTANCE_PERMS_CACHE_ATTR
from opencontractserver.shared.prefetch_attrs import (
    user_group_perm_attr,
    user_perm_attr,
)
from opencontractserver.types.enums import PermissionTypes

if TYPE_CHECKING:
    from opencontractserver.users.models import User as UserModel

User = get_user_model()
logger = logging.getLogger(__name__)

# Generic bound to ``django.db.models.Model`` so ``get_for_user_or_none`` returns
# the concrete model type back to callers (e.g. ``Extract | None`` rather than
# the abstract ``Model | None``). Without this, mypy can't see ``.name`` /
# ``.fieldset`` etc. on the helper's return value.
_T_Model = TypeVar("_T_Model", bound=django.db.models.Model)


class _InstancePermsCache(dict):
    """Thread-safe Tier 1 cache for granted permission sets.

    A ``dict`` subclass keyed by ``(user_id, include_group_permissions)``
    → ``frozenset[str]``. Subclassing ``dict`` keeps the cache transparent
    to direct callers and tests that perform membership checks, indexing,
    or ``dict(cache)`` snapshots.

    The ``_lock`` exists for *compound* operations only — namely the
    invalidate-by-user sweep in
    :func:`set_permissions_for_obj_to_user`, which iterates keys then
    deletes them and would otherwise risk ``RuntimeError: dictionary
    changed size during iteration`` under async views or any future
    code path that crosses thread or coroutine boundaries on the same
    instance. Individual ``cache[key]`` reads/writes are already atomic
    under CPython's GIL; the lock-acquire/release cost on an uncontended
    Lock is a few hundred nanoseconds on CPython — well below the cost
    of the guardian queries this layer exists to elide. The matching
    Tier 2 rationale lives in
    ``opencontractserver/utils/permission_optimizer.py``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    def drop_for_user(self, user_id: int) -> None:
        """Atomically drop every entry keyed by ``user_id``.

        Holds ``_lock`` for the iterate-then-delete sweep so a concurrent
        writer cannot trigger ``RuntimeError`` mid-iteration and so a
        concurrent reader either sees the entry fully present or fully
        gone, never a half-removed state.
        """

        with self._lock:
            for key in [k for k in self if k[0] == user_id]:
                del self[key]


def _get_or_create_instance_perms_cache(
    instance: django.db.models.Model,
) -> _InstancePermsCache:
    """Return ``instance``'s Tier 1 cache, creating one atomically if needed.

    Uses ``instance.__dict__.setdefault`` so concurrent first-touches on
    the same Python instance converge on a single cache object instead
    of stomping each other via ``getattr`` + ``setattr``. On CPython
    ``dict.setdefault`` is a single atomic operation under the GIL.
    """

    cache = getattr(instance, INSTANCE_PERMS_CACHE_ATTR, None)
    if cache is None:
        cache = instance.__dict__.setdefault(
            INSTANCE_PERMS_CACHE_ATTR, _InstancePermsCache()
        )
    return cache


def set_permissions_for_obj_to_user(
    user_val: int | str | UserModel,
    instance: django.db.models.Model,
    permissions: list[PermissionTypes],
    *,
    is_new: bool = False,
    request: Any = None,
) -> None:
    """
    Given an instance of a django Model, a user id or instance, and a list of desired permissions,
    **REPLACE** current permissions with specified permissions. Pass empty list to permissions to completely
    de-provision a user's permissions.

    This doesn't affect permissions provided from other avenues besides object-level permissions. For example, if
    they're a superuser, they'll still have permissions. Also, if an object is public, they'll still have read
    permissions (assuming they're part of the read public objects group).

    Args:
        is_new: When True, skip the upfront ``remove_perm`` sweep — safe and
            correct on freshly-created objects (no prior permissions to clear).
            Saves 7 DB ops per call. The default of False preserves the full
            replace semantics for sharing flows / permission downgrades that
            depend on prior perms being cleared (e.g. CRUD → READ-only).
            Ingest paths (``import_annotations``, ``corpus.add_document``,
            label-creation, etc.) should pass ``is_new=True``.
        request: When supplied (typically ``info.context`` from a GraphQL
            mutation), invalidate the two-tier permission cache for this
            ``(user, instance)`` pair after the grant lands so any
            subsequent ``user_can`` checks in the same request reflect
            the new state. ``None`` is safe — Celery tasks and fixtures
            never reuse the instance after mutating perms, so the cache
            won't go stale.

    Cache invalidation does NOT cover group-permission changes: calls
    such as ``user.groups.add(group)`` or ``assign_perm(perm, group, obj)``
    do not flow through this helper and therefore leave both tiers
    untouched. Any cached entry computed with
    ``include_group_permissions=True`` becomes stale until the instance
    or request goes out of scope. Callers performing those operations
    mid-request must invalidate manually (``delattr(instance,
    INSTANCE_PERMS_CACHE_ATTR)`` and/or
    ``get_request_optimizer(request).invalidate(user_id=user.id)``).
    """

    # Provides some flexibility to use ids where passing object is not practical
    if isinstance(user_val, str) or isinstance(user_val, int):
        user = User.objects.get(id=user_val)
    else:
        user = user_val

    model_name = instance._meta.model_name
    app_name = instance._meta.app_label

    # First, remove ALL existing permissions for this user on this object ############################################
    # ``is_new`` callers (ingest paths granting perms on freshly-created
    # objects) skip the upfront sweep — there's nothing to clear and
    # each ``remove_perm`` is a DB op that adds up across N annotations.
    # Sharing flows / downgrade flows leave ``is_new`` at the default
    # so that a CRUD → READ-only downgrade still clears UPDATE/DELETE.
    if not is_new:
        # List all possible permissions for this model type
        all_perms = [
            f"{app_name}.create_{model_name}",
            f"{app_name}.read_{model_name}",
            f"{app_name}.update_{model_name}",
            f"{app_name}.remove_{model_name}",
            f"{app_name}.comment_{model_name}",
            f"{app_name}.permission_{model_name}",
            f"{app_name}.publish_{model_name}",
        ]

        # Remove all existing permissions
        for perm in all_perms:
            try:
                remove_perm(perm, user, instance)
            except Exception:
                # Permission might not exist for this model type
                pass

    # Now, add specified permissions ###################################################################################
    requested_permission_set = set(permissions)

    with transaction.atomic():
        if (
            len(
                {
                    PermissionTypes.CREATE,
                    PermissionTypes.CRUD,
                    PermissionTypes.ALL,
                }.intersection(requested_permission_set)
            )
            > 0
        ):
            assign_perm(f"{app_name}.create_{model_name}", user, instance)

        if (
            len(
                {
                    PermissionTypes.READ,
                    PermissionTypes.CRUD,
                    PermissionTypes.ALL,
                }.intersection(requested_permission_set)
            )
            > 0
        ):
            assign_perm(f"{app_name}.read_{model_name}", user, instance)

        if (
            len(
                {
                    PermissionTypes.UPDATE,
                    PermissionTypes.CRUD,
                    PermissionTypes.ALL,
                }.intersection(requested_permission_set)
            )
            > 0
        ):
            assign_perm(f"{app_name}.update_{model_name}", user, instance)

        if (
            len(
                {
                    PermissionTypes.DELETE,
                    PermissionTypes.CRUD,
                    PermissionTypes.ALL,
                }.intersection(requested_permission_set)
            )
            > 0
        ):
            assign_perm(f"{app_name}.remove_{model_name}", user, instance)

        if (
            len(
                {PermissionTypes.PERMISSION, PermissionTypes.ALL}.intersection(
                    requested_permission_set
                )
            )
            > 0
        ):
            assign_perm(f"{app_name}.permission_{model_name}", user, instance)

        if (
            len(
                {PermissionTypes.COMMENT, PermissionTypes.ALL}.intersection(
                    requested_permission_set
                )
            )
            > 0
        ):
            assign_perm(f"{app_name}.comment_{model_name}", user, instance)

        if (
            len(
                {PermissionTypes.PUBLISH, PermissionTypes.ALL}.intersection(
                    requested_permission_set
                )
            )
            > 0
        ):
            assign_perm(f"{app_name}.publish_{model_name}", user, instance)

    # Drop both Tier 1 (instance) and Tier 2 (request) cache entries for this
    # ``(user, instance)`` so later ``user_can`` checks in the same request
    # see the new grants. See ``constants/permissioning.py`` for caveats.
    #
    # ``_InstancePermsCache.drop_for_user`` holds the per-cache lock for the
    # iterate-then-delete sweep so the invalidation is safe under ASGI /
    # async-view code paths that may race a concurrent reader on the same
    # Python instance. Legacy plain-``dict`` caches (instances pickled out
    # by an older worker and loaded back in mid-rollout, or hand-attached
    # test fixtures) still iterate via the same shape — we fall back to a
    # snapshot pattern so ``RuntimeError`` cannot escape this helper.
    instance_cache = getattr(instance, INSTANCE_PERMS_CACHE_ATTR, None)
    if isinstance(instance_cache, _InstancePermsCache):
        instance_cache.drop_for_user(user.id)
    elif instance_cache is not None:
        for key in [k for k in instance_cache if k[0] == user.id]:
            instance_cache.pop(key, None)
    if request is not None:
        from opencontractserver.utils.permission_optimizer import (
            get_request_optimizer,
        )

        get_request_optimizer(request).invalidate(user_id=user.id, instance=instance)


def get_users_group_ids(user_instance: UserModel) -> list[str | int]:
    """
    For a given user, return list of group ids it belongs to.
    """

    return list(user_instance.groups.all().values_list("id", flat=True))


def get_permission_id_to_name_map_for_model(
    instance: django.db.models.Model,
) -> dict[int, str]:
    """
    Constantly ran into issues with Django Guardian's helper methods, but working with the database directly I can get
    what I want... namely for each of the permission types that were created in the various models' Meta fields,
    the permission ids, which we can then get on a given object and map back to the permission names for that obj.
    """

    model_name = instance._meta.model_name
    app_label = instance._meta.app_label

    model_type = ContentType.objects.get(app_label=app_label, model=model_name)
    this_model_permission_objs = list(
        Permission.objects.filter(content_type_id=model_type.id).values_list(
            "id", "codename"
        )
    )
    this_model_permission_id_map: dict[int, str] = reduce(
        combine, this_model_permission_objs, {}
    )
    return this_model_permission_id_map


def _perm_cache_key(
    user: UserModel, include_group_permissions: bool
) -> tuple[int, bool] | None:
    """Build the per-instance Tier 1 cache key, or ``None`` to skip caching.

    Anonymous / unauthenticated users have no stable ``id`` to key on and
    their state isn't reusable across calls — return ``None`` so callers
    bypass the cache entirely for them.
    """

    user_id = getattr(user, "id", None)
    if user_id is None or not getattr(user, "is_authenticated", False):
        return None
    return (user_id, bool(include_group_permissions))


def _store_granted_on_instance(
    instance: django.db.models.Model,
    cache_key: tuple[int, bool] | None,
    granted: set[str],
) -> set[str]:
    """Cache ``granted`` on ``instance`` under ``cache_key`` and return it.

    Stores as ``frozenset`` (immutable) and returns the original ``set``
    so callers can mutate the result locally — ``_default_user_can``
    folds ``read_<model>`` into the granted set for compound CRUD/ALL
    checks.
    """

    if cache_key is None:
        return granted
    cache = _get_or_create_instance_perms_cache(instance)
    cache[cache_key] = frozenset(granted)
    return granted


def get_users_permissions_for_obj(
    user: UserModel,
    instance: django.db.models.Model,
    include_group_permissions: bool = True,
) -> set[str]:
    """Return the set of guardian permission codenames the user has on
    ``instance``.

    Tier 1 of issue #1640's caching strategy: results are memoized on the
    instance under ``INSTANCE_PERMS_CACHE_ATTR``, keyed by
    ``(user_id, include_group_permissions_bool)``. Cache lifetime equals
    the instance lifetime; ``set_permissions_for_obj_to_user`` clears
    matching entries when a grant changes. ``refresh_from_db`` does NOT
    clear the cache — callers that mutate guardian rows out-of-band and
    reuse the same Python object must drop the attribute manually.

    ``include_group_permissions`` defaults to ``True`` — same as
    :meth:`PermissionQueryOptimizer.get_granted`, :func:`_default_user_can`
    and every ``Manager.user_can`` / ``obj.user_can`` surface. One default,
    one answer: ad-hoc callers who skip the flag get group permissions
    folded in just like the rest of the authorization stack.
    """

    model_name = instance._meta.model_name
    logger.debug(
        f"get_users_permissions_for_obj() - Starting check for {user.username} with model type {model_name}"
    )

    app_label = instance._meta.app_label
    logger.debug(f"get_users_permissions_for_obj - App name: {app_label}")

    # Tier 1 lookup. Returns a defensive copy so the caller can mutate
    # without poisoning the cache (the compound-perm fold-in in
    # ``_default_user_can`` mutates the returned set locally).
    cache_key = _perm_cache_key(user, include_group_permissions)
    if cache_key is not None:
        cache = getattr(instance, INSTANCE_PERMS_CACHE_ATTR, None)
        if cache is not None and cache_key in cache:
            return set(cache[cache_key])

    # Check if the model has django-guardian permission tables
    # Some models (like AnnotationLabel) use creator-based permissions instead.
    #
    # Tier 1 safety on this branch: ``set_permissions_for_obj_to_user`` is
    # effectively a no-op on creator-based models — its only side-effect is
    # ``assign_perm`` / ``remove_perm``, both of which mutate guardian
    # tables that don't exist for these models. The cached value therefore
    # cannot go stale from the documented mutation path. The only ways for
    # it to drift are (a) re-parenting the instance (changing ``creator_id``)
    # or (b) toggling ``is_public`` — both rare, both already require the
    # caller to ``refresh_from_db`` and follow the same manual-``delattr``
    # contract that guardian-backed models honour.
    if not hasattr(instance, f"{model_name}userobjectpermission_set"):
        logger.debug(
            f"Model {model_name} does not have guardian permissions, using creator-based permissions"
        )
        # For models without guardian permissions, use creator-based permissions
        model_permissions_for_user: set[str] = set()

        # Superusers have all permissions
        if user.is_superuser:
            model_permissions_for_user = {
                f"create_{model_name}",
                f"read_{model_name}",
                f"update_{model_name}",
                f"remove_{model_name}",
            }
        # Creator has full CRUD permissions
        elif hasattr(instance, "creator_id") and instance.creator_id == user.id:
            model_permissions_for_user = {
                f"create_{model_name}",
                f"read_{model_name}",
                f"update_{model_name}",
                f"remove_{model_name}",
            }
        # Public objects are readable by all
        elif hasattr(instance, "is_public") and instance.is_public:
            model_permissions_for_user.add(f"read_{model_name}")

        logger.debug(f"Creator-based permissions: {model_permissions_for_user}")
        return _store_granted_on_instance(
            instance, cache_key, model_permissions_for_user
        )

    # Superusers have all permissions on guardian-enabled models.
    # Guardian models support richer operations (comment, publish, permission)
    # beyond the basic CRUD set used for creator-based models above.
    # NOTE: the cache key is (user_id, include_group_permissions) — it does
    # NOT include is_superuser. If a test promotes a user to superuser
    # mid-run and reuses the same Python instance, this branch's cached
    # superuser set will be returned by later calls even after promotion is
    # reverted (and vice versa). Refresh the instance from DB or
    # ``delattr(instance, INSTANCE_PERMS_CACHE_ATTR)`` to scrub the cache.
    if user.is_superuser:
        return _store_granted_on_instance(
            instance,
            cache_key,
            {
                f"create_{model_name}",
                f"read_{model_name}",
                f"update_{model_name}",
                f"remove_{model_name}",
                f"comment_{model_name}",
                f"publish_{model_name}",
                f"permission_{model_name}",
            },
        )

    # Fast path: consume per-user guardian prefetches if attached. Missing attr
    # (different user, or no prefetch) falls through to the guardian path below.
    prefetched_user_perms = getattr(instance, user_perm_attr(user.id), None)
    if prefetched_user_perms is not None:
        model_permissions_for_user = {
            perm.permission.codename for perm in prefetched_user_perms
        }
        if hasattr(instance, "is_public") and instance.is_public:
            model_permissions_for_user.add(f"read_{model_name}")

        if include_group_permissions:
            prefetched_group_perms = getattr(
                instance, user_group_perm_attr(user.id), None
            )
            if prefetched_group_perms is not None:
                for perm in prefetched_group_perms:
                    model_permissions_for_user.add(perm.permission.codename)
            else:
                # Partial prefetch: user perms cached but group perms not — fall back for groups only.
                permission_id_to_name_map = get_permission_id_to_name_map_for_model(
                    instance=instance
                )
                this_users_group_perms = getattr(
                    instance, f"{model_name}groupobjectpermission_set"
                ).filter(group_id__in=get_users_group_ids(user_instance=user))
                for perm in this_users_group_perms:
                    model_permissions_for_user.add(
                        permission_id_to_name_map[perm.permission_id]
                    )
        return _store_granted_on_instance(
            instance, cache_key, model_permissions_for_user
        )

    this_user_perms = getattr(instance, f"{model_name}userobjectpermission_set")

    logger.debug(f"get_users_permissions_for_obj - this_user_perms: {this_user_perms}")
    permission_id_to_name_map = get_permission_id_to_name_map_for_model(
        instance=instance
    )
    logger.debug(
        f"get_users_permissions_for_obj - permission_id_to_name_map: {permission_id_to_name_map}"
    )

    # Build list of permission names from the permission type ids
    model_permissions_for_user = {
        permission_id_to_name_map[perm.permission_id]
        for perm in this_user_perms.filter(user_id=user.id)
    }

    # Don't forget to throw a read permission on if object is public
    if hasattr(instance, "is_public") and instance.is_public:
        model_permissions_for_user.add(f"read_{model_name}")

    # If we're looking at group permissions... add those too
    if include_group_permissions:
        this_users_group_perms = getattr(
            instance, f"{model_name}groupobjectpermission_set"
        ).filter(group_id__in=get_users_group_ids(user_instance=user))
        logger.debug(
            f"get_users_permissions_for_obj - this_users_group_perms: {this_users_group_perms}"
        )
        for perm in this_users_group_perms:
            model_permissions_for_user.add(
                permission_id_to_name_map[perm.permission_id]
            )

    logger.debug(f"Final permissions: {model_permissions_for_user}")

    return _store_granted_on_instance(instance, cache_key, model_permissions_for_user)


def _default_user_can(
    user_val: int | str | UserModel | AnonymousUser | None,
    instance: django.db.models.Model,
    permission: PermissionTypes,
    *,
    include_group_permissions: bool = True,
    request: Any = None,
) -> bool:
    """Centralized default-branch authorization body.

    Single source of truth for "does this user have ``permission`` on
    ``instance``?" for any model that uses the standard rules. Both
    ``BaseVisibilityManager.user_can`` and ``PermissionedTreeQuerySet.user_can``
    delegate here, which keeps the filter (``visible_to_user``) and check
    (``user_can``) decisions provably aligned.

    Naming note: the leading underscore marks this as implementation-private
    to the permission subsystem (callers go through ``Manager.user_can`` /
    ``obj.user_can``), NOT as file-private. ``Managers.py``, ``QuerySets.py``,
    and ``UserCanMixin`` deliberately import it. Per-model overrides that
    need the default rules MUST delegate here rather than re-implementing
    them, so filter/check stay aligned.

    Rules:
        - ``None`` / ``AnonymousUser`` / unauthenticated → False, except READ
          on ``instance.is_public=True`` which returns True.
        - Superuser → True for every permission.
        - Authenticated, non-superuser:
            * For READ: True iff ``is_public`` or ``creator_id == user.id`` or
              the user has the corresponding guardian codename (user perms,
              optionally group perms).
            * For non-READ: True iff ``creator_id == user.id`` or the user
              has the corresponding guardian codename. ``is_public`` does NOT
              grant write permissions — preserves the read/write asymmetry
              enforced today by the deleted ``FolderService.check_corpus_*``
              helpers.
            * For ``CRUD``: requires all four base perms (CREATE, READ,
              UPDATE, DELETE). ``is_public`` is folded in locally as a
              synthetic ``read_<model>`` so a user with explicit write
              grants on a public corpus passes CRUD — preserves the same
              semantics as a series of individual ``user_can`` calls.
            * For ``ALL``: requires all seven perms (same ``is_public``
              fold-in as CRUD).
            * Creator short-circuit applies BEFORE compound checks, so the
              corpus creator passes ``CRUD`` / ``ALL`` without needing
              explicit guardian grants (mirrors the deleted FolderService
              behavior; pinned by
              ``test_creator_passes_compound_perms_without_explicit_grants``).
        - ``EDIT`` is treated as an alias for ``UPDATE``.

    Per-model overrides (e.g. ``AnnotationManager.user_can``) MUST add their
    own structural / privacy / inheritance rules before delegating here,
    and MUST forward ``request`` through so the optimization composes.

    Caching layers (issue #1640):

    1. ``permission_cache_scope`` (request-scoped boolean cache, dormant
       until Phase B activates it via middleware). Wraps the cold path so
       the same ``(user, instance, permission)`` tuple is computed at most
       once per scope.
    2. ``PermissionQueryOptimizer`` (Tier 2 active cache, opt-in via the
       optional ``request`` kwarg). When ``request is not None`` the
       granted-set lookup goes through the optimizer so multiple
       instances of the same model in one request share a cache.
    3. ``get_users_permissions_for_obj`` instance-memoized cache (Tier 1,
       always-on). Same-instance repeat checks short-circuit at the
       guardian-lookup boundary.

    The three layers compose: scope → optimizer → per-instance.
    """
    if user_val is None:
        return False

    # AnonymousUser is the common unauthenticated case (set by Django auth
    # middleware) — handle it explicitly so the int/str ID resolution below
    # doesn't run on an AnonymousUser sentinel.
    if isinstance(user_val, AnonymousUser):
        if permission == PermissionTypes.READ and getattr(instance, "is_public", False):
            return True
        return False

    # Centralised int/str → User resolver, shared with per-model
    # ``user_can`` overrides so each branch resolves identically.
    from opencontractserver.shared.user_can_mixin import resolve_user_for_user_can

    user = resolve_user_for_user_can(user_val)
    if user is None:
        return False

    # Defensive guard for exotic user-like objects that aren't AnonymousUser
    # but still report ``is_authenticated == False`` (e.g. a test double, an
    # external SSO shim, or a future custom auth backend). The AnonymousUser
    # path above is the common case; this catches the long tail.
    if not getattr(user, "is_authenticated", False):
        if permission == PermissionTypes.READ and getattr(instance, "is_public", False):
            return True
        return False

    if user.is_superuser:
        return True

    if permission == PermissionTypes.READ and getattr(instance, "is_public", False):
        return True

    if (
        hasattr(instance, "creator_id")
        and instance.creator_id is not None
        and instance.creator_id == user.id
    ):
        return True

    model_name = instance._meta.model_name
    app_label = instance._meta.app_label

    # Request-scoped boolean cache lookup. Dormant outside
    # ``permission_cache_scope`` (the default ``_perm_cache`` is ``None``
    # and ``cached_user_can`` returns ``MISS``). The early returns above
    # (None/anonymous, superuser, is_public+READ, creator) are already
    # O(1) and bypass the cache — only the guardian-derived answer is
    # worth caching.
    from opencontractserver.shared.permission_cache import (
        MISS,
        cached_user_can,
        store_user_can,
    )

    # ``_meta.model_name`` / ``_meta.app_label`` are typed as ``str | None`` in
    # the Django stubs but are always populated on concrete model instances —
    # cast to ``str`` to satisfy the cache function signatures.
    app_label_str: str = str(app_label)
    model_name_str: str = str(model_name)

    cached = cached_user_can(
        user.id,
        app_label_str,
        model_name_str,
        instance.pk,
        permission.value,
        include_group_permissions,
    )
    if cached is not MISS:
        return cached

    if request is not None:
        # Tier 2: route through the request-scoped optimizer so multiple
        # instances of the same model in one request share a cache. Lazy
        # import keeps the early ``shared.Models`` ⇄ ``users.models``
        # startup chain free of the optimizer module.
        from opencontractserver.utils.permission_optimizer import (
            get_request_optimizer,
        )

        granted = get_request_optimizer(request).get_granted(
            user,
            instance,
            include_group_permissions=include_group_permissions,
        )
    else:
        granted = get_users_permissions_for_obj(
            user=user,
            instance=instance,
            include_group_permissions=include_group_permissions,
        )

    def _cache_and_return(result: bool) -> bool:
        store_user_can(
            user.id,
            app_label_str,
            model_name_str,
            instance.pk,
            permission.value,
            include_group_permissions,
            result,
        )
        return result

    if permission == PermissionTypes.READ:
        return _cache_and_return(f"read_{model_name}" in granted)
    if permission == PermissionTypes.CREATE:
        return _cache_and_return(f"create_{model_name}" in granted)
    if permission in (PermissionTypes.UPDATE, PermissionTypes.EDIT):
        return _cache_and_return(f"update_{model_name}" in granted)
    if permission == PermissionTypes.DELETE:
        return _cache_and_return(f"remove_{model_name}" in granted)
    if permission == PermissionTypes.COMMENT:
        return _cache_and_return(f"comment_{model_name}" in granted)
    if permission == PermissionTypes.PUBLISH:
        return _cache_and_return(f"publish_{model_name}" in granted)
    if permission == PermissionTypes.PERMISSION:
        return _cache_and_return(f"permission_{model_name}" in granted)
    if permission in (PermissionTypes.CRUD, PermissionTypes.ALL):
        # Belt-and-suspenders: ``get_users_permissions_for_obj`` *already*
        # injects ``read_<model>`` into ``granted`` when ``is_public=True``,
        # so today this fold-in is a no-op. We keep it explicit at the
        # call site because the dependency is otherwise invisible: if
        # that helper is ever refactored to drop the synthetic READ
        # grant, the CRUD/ALL branch here MUST keep working so
        # public-corpus + explicit-write-grants still passes the
        # compound check. Removing this line would silently break
        # ``test_crud_satisfied_by_public_read_plus_explicit_writes``.
        if getattr(instance, "is_public", False):
            granted = granted | {f"read_{model_name}"}
        if permission == PermissionTypes.CRUD:
            required = {
                f"create_{model_name}",
                f"read_{model_name}",
                f"update_{model_name}",
                f"remove_{model_name}",
            }
        else:  # ALL
            required = {
                f"create_{model_name}",
                f"read_{model_name}",
                f"update_{model_name}",
                f"remove_{model_name}",
                f"comment_{model_name}",
                f"publish_{model_name}",
                f"permission_{model_name}",
            }
        return _cache_and_return(required.issubset(granted))
    return False


def get_for_user_or_none(
    model_cls: type[_T_Model],
    pk: Any,
    user: UserModel | AnonymousUser | None,
) -> _T_Model | None:
    """IDOR-safe object lookup for non-corpus-scoped models.

    Returns the instance iff it exists AND ``user`` can READ it, otherwise
    ``None``. The single ``None`` return collapses "pk doesn't exist" and
    "pk exists but caller lacks READ" into one indistinguishable response
    so call sites can render a single unified error message — preventing
    enumeration via timing or differential error text (CLAUDE.md "IDOR
    Prevention").

    Garbage pk input (non-integer string on an integer-pk model, ``None``,
    or anything else the ORM rejects with ``ValueError`` / ``TypeError``)
    also returns ``None`` rather than raising; callers receive untrusted
    ids from GraphQL and must not surface a 500 on malformed input.

    Caller responsibility: this helper enforces ONLY the READ gate. If the
    mutation requires UPDATE / DELETE / PERMISSION, layer the additional
    check (via ``user_can``) AFTER the helper returns and emit the same
    unified ``"<resource> not found or
    you don't have permission to <verb> it."`` message on failure so the
    UPDATE-vs-READ branches stay indistinguishable to the caller.

    For DOCUMENT lookups in a CORPUS context, prefer
    :meth:`opencontractserver.corpuses.services.corpus_documents.CorpusDocumentService.get_corpus_document_by_id`
    instead — it enforces corpus READ as the gate (the more restrictive
    check) and is the canonical service-layer entry point for the
    "is this document in this corpus, for this user" question. Phase D
    deliberately does NOT introduce a parallel doc-by-pk lookup helper
    that would race against the service.
    """

    if pk is None:
        return None
    manager = model_cls._default_manager
    if not hasattr(manager, "visible_to_user"):
        raise TypeError(
            f"{model_cls.__name__}._default_manager "
            f"({type(manager).__name__}) does not implement visible_to_user(). "
            "Use BaseVisibilityManager or implement visible_to_user before "
            "calling get_for_user_or_none()."
        )
    try:
        return manager.visible_to_user(user).filter(pk=pk).first()
    except (ValueError, TypeError):
        # Untrusted ids — guard against the ORM raising on a malformed pk
        # type so the IDOR contract ("return None on bad input") holds
        # for every garbage value, not just non-existent ones.
        return None
