from __future__ import annotations

import logging
from functools import reduce
from typing import TYPE_CHECKING

import django
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from guardian.shortcuts import assign_perm, remove_perm

from config.graphql.permissioning.permission_annotator.middleware import combine
from opencontractserver.shared.prefetch_attrs import (
    user_group_perm_attr,
    user_perm_attr,
)
from opencontractserver.types.enums import PermissionTypes

if TYPE_CHECKING:
    from opencontractserver.users.models import User as UserModel

User = get_user_model()
logger = logging.getLogger(__name__)


def set_permissions_for_obj_to_user(
    user_val: int | str | UserModel,
    instance: django.db.models.Model,
    permissions: list[PermissionTypes],
    *,
    is_new: bool = False,
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
    """

    # logger.info(
    #     f"grant_permissions_for_obj_to_user - user ({user_val}) / obj ({instance})"
    # )

    # Provides some flexibility to use ids where passing object is not practical
    if isinstance(user_val, str) or isinstance(user_val, int):
        user = User.objects.get(id=user_val)
    else:
        user = user_val

    model_name = instance._meta.model_name
    # logger.info(f"grant_permissions_for_obj_to_user - Model name: {model_name}")

    app_name = instance._meta.app_label
    # logger.info(f"grant_permissions_for_obj_to_user - App name: {app_name}")

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
    # logger.info(
    #     f"grant_permissions_for_obj_to_user - Requested permissions: {requested_permission_set}"
    # )

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
            # logger.info("requested_permission_set - assign create permission")
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
            # logger.info("requested_permission_set - assign read permission")
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
            # logger.info("requested_permission_set - assign update permission")
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
            # logger.info("requested_permission_set - assign remove permission")
            assign_perm(f"{app_name}.remove_{model_name}", user, instance)

        if (
            len(
                {PermissionTypes.PERMISSION, PermissionTypes.ALL}.intersection(
                    requested_permission_set
                )
            )
            > 0
        ):
            # logger.info("requested_permission_set - assign permissioning permission")
            assign_perm(f"{app_name}.permission_{model_name}", user, instance)

        if (
            len(
                {PermissionTypes.COMMENT, PermissionTypes.ALL}.intersection(
                    requested_permission_set
                )
            )
            > 0
        ):
            # logger.info("requested_permission_set - assign comment permission")
            assign_perm(f"{app_name}.comment_{model_name}", user, instance)

        if (
            len(
                {PermissionTypes.PUBLISH, PermissionTypes.ALL}.intersection(
                    requested_permission_set
                )
            )
            > 0
        ):
            # logger.info("requested_permission_set - assign publish permission")
            assign_perm(f"{app_name}.publish_{model_name}", user, instance)


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
    # logger.info(
    #     f"get_permission_id_to_name_map_for_model - App name: {app_label} / model name: {model_name}"
    # )

    model_type = ContentType.objects.get(app_label=app_label, model=model_name)
    this_model_permission_objs = list(
        Permission.objects.filter(content_type_id=model_type.id).values_list(
            "id", "codename"
        )
    )
    this_model_permission_id_map: dict[int, str] = reduce(
        combine, this_model_permission_objs, {}
    )
    # logger.info(
    #     f"get_permission_id_to_name_map_for_model - resulting map: {this_model_permission_id_map}"
    # )
    return this_model_permission_id_map


def get_users_permissions_for_obj(
    user: UserModel,
    instance: django.db.models.Model,
    include_group_permissions: bool = False,
) -> set[str]:

    model_name = instance._meta.model_name
    logger.debug(
        f"get_users_permissions_for_obj() - Starting check for {user.username} with model type {model_name}"
    )

    app_label = instance._meta.app_label
    logger.debug(f"get_users_permissions_for_obj - App name: {app_label}")

    # Check if the model has django-guardian permission tables
    # Some models (like AnnotationLabel) use creator-based permissions instead
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
        return model_permissions_for_user

    # Superusers have all permissions on guardian-enabled models.
    # Guardian models support richer operations (comment, publish, permission)
    # beyond the basic CRUD set used for creator-based models above.
    if user.is_superuser:
        return {
            f"create_{model_name}",
            f"read_{model_name}",
            f"update_{model_name}",
            f"remove_{model_name}",
            f"comment_{model_name}",
            f"publish_{model_name}",
            f"permission_{model_name}",
        }

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
        return model_permissions_for_user

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

    return model_permissions_for_user


def _default_user_can(
    user_val: int | str | UserModel | AnonymousUser | None,
    instance: django.db.models.Model,
    permission: PermissionTypes,
    *,
    include_group_permissions: bool = True,
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
        - ``EDIT`` is treated as an alias for ``UPDATE`` (mirrors the old
          ``user_has_permission_for_obj`` mapping).

    Per-model overrides (e.g. ``AnnotationManager.user_can``) MUST add their
    own structural / privacy / inheritance rules before delegating here.
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

    # Centralised int/str → User resolver, also used by the per-model
    # ``user_can`` overrides (PR #1663 DRY cleanup).
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

    # Request-scoped cache lookup. Dormant outside ``permission_cache_scope``
    # (the default ``_perm_cache`` is ``None`` and ``cached_user_can``
    # returns ``MISS``). The early returns above (None/anonymous,
    # superuser, is_public+READ, creator) are already O(1) and bypass the
    # cache — only the guardian-derived answer is worth caching.
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
        # injects ``read_<model>`` into ``granted`` when ``is_public=True``
        # (see lines ~268 and ~336), so today this fold-in is a no-op.
        # We keep it explicit at the call site because the dependency is
        # otherwise invisible: if that helper is ever refactored to drop
        # the synthetic READ grant, the CRUD/ALL branch here MUST keep
        # working so public-corpus + explicit-write-grants still passes
        # the compound check. Removing this line would silently break
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


# Per-call-site dedup for the deprecation warning emitted by
# ``user_has_permission_for_obj``. With ~170 legacy call sites each
# potentially fired many times per request, an unthrottled
# ``warnings.warn`` would flood logs during the Phase B migration window.
# We track (filename, lineno) tuples for each unique caller frame and
# emit at most once per site per process. The set is bounded by the
# number of distinct call sites in the codebase (currently ~170) and
# does not grow with request/task volume, so it is safe to leave
# uncleared in long-running Celery workers. Tests that need to assert
# specific call sites still issue warnings can clear this set via
# ``_user_has_permission_for_obj_warned.clear()`` (see
# ``ShimDeprecationWarningTestCase.setUp``).
_user_has_permission_for_obj_warned: set[tuple[str, int]] = set()


def user_has_permission_for_obj(
    user_val: int | str | UserModel,
    instance: django.db.models.Model,
    permission: PermissionTypes,
    include_group_permissions: bool = False,
) -> bool:
    """Deprecation shim — delegates to ``Manager.user_can``.

    .. deprecated:: Phase A of permission-centralization (issue #1655)

        Every call emits a ``DeprecationWarning``. New code MUST use
        ``Model.objects.user_can(user, instance, permission)`` or the
        ergonomic ``instance.user_can(user, permission)``. Per-model
        overrides on ``DocumentManager``, ``AnnotationManager``,
        ``RelationshipManager``, ``NoteManager``, ``UserFeedbackManager``,
        ``ConversationManager``, ``ChatMessageManager`` (and others
        inheriting from ``BaseVisibilityManager``) now encode the
        structural / privacy / inheritance / moderator rules this
        function used to. The ``user_can`` API is the single source of
        truth that stays aligned with ``visible_to_user`` filters.

        Migration of the ~170 existing call sites is tracked in Phases
        B/C of issue #1655.

    Implementation: route the call through the instance's
    ``_default_manager.user_can``. The kwarg defaults preserve the old
    behavior — ``include_group_permissions=False`` (the legacy default,
    DIFFERENT from ``_default_user_can``'s ``True``) is forwarded
    verbatim so callers that don't pass the kwarg keep getting the same
    answer.

    ``User.objects.get(id=user_val)`` raising ``User.DoesNotExist`` for
    an unknown id is replaced with a defensive ``False`` return (the
    legacy code raised; no caller catches ``DoesNotExist`` around this
    function in the production paths).

    If the instance's ``_default_manager`` doesn't implement ``user_can``
    (i.e. the model hasn't yet been migrated to the Phase A surface), the
    shim raises ``TypeError`` with an actionable message instead of letting
    the call fall through and surface as a confusing ``AttributeError``
    deep inside the resolver. Addresses Claude review on PR #1663.
    """
    import sys
    import warnings

    from opencontractserver.shared.user_can_mixin import resolve_user_for_user_can

    # Throttle to one warning per unique call site per process. Identify
    # the caller via its frame's (filename, lineno) — cheap to compute and
    # stable for the lifetime of the process. ``sys._getframe(1)`` mirrors
    # what ``warnings.warn(stacklevel=2)`` reports, so the dedup key
    # always matches the line that actually appears in the warning text.
    caller = sys._getframe(1)
    site = (caller.f_code.co_filename, caller.f_lineno)
    if site not in _user_has_permission_for_obj_warned:
        _user_has_permission_for_obj_warned.add(site)
        warnings.warn(
            "user_has_permission_for_obj is deprecated; use "
            "Model.objects.user_can(user, instance, permission) instead "
            "(or instance.user_can(user, permission)). See issue #1655.",
            DeprecationWarning,
            stacklevel=2,
        )

    # ``resolve_user_for_user_can`` returns ``None`` for both ``None``
    # input and a missing-id lookup; both deny under the legacy contract.
    user = resolve_user_for_user_can(user_val)
    if user is None:
        return False

    manager = type(instance)._default_manager
    if not hasattr(manager, "user_can"):
        raise TypeError(
            f"{type(instance).__name__}._default_manager "
            f"({type(manager).__name__}) does not implement user_can(). "
            "Migrate the model's manager to BaseVisibilityManager / "
            "UserCanMixin (Phase A) before calling user_has_permission_for_obj."
        )
    # ``manager`` is statically typed as ``Manager[Model]`` here — the
    # ``hasattr`` guard above makes ``user_can`` safe at runtime.
    return manager.user_can(
        user,
        instance,
        permission,
        include_group_permissions=include_group_permissions,
    )
