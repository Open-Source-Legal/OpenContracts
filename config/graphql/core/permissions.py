"""Permission-annotation field resolvers (``myPermissions`` /
``isPublished`` / ``objectSharedWith``).

Faithful port of
``config.graphql.permissioning.permission_annotator.mixins
.AnnotatePermissionsForReadMixin`` — the resolvers operate on the Django
model instance (the GraphQL root object) and keep the same per-request
caching contract the graphene middleware provided: the per-model
permission map is memoised on ``info.context.permission_annotations``.
Under graphene that map was eagerly populated by
``PermissionAnnotatingMiddleware`` on every resolved model field; here it
is populated lazily on first use, which preserves observable behaviour
(same data, same query count for requests that read these fields) without
a per-field middleware.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model

from config.graphql.permissioning.permission_annotator.middleware import (
    get_permissions_for_user_on_model_in_app,
)
from opencontractserver.shared.prefetch_attrs import (
    user_group_perm_attr,
    user_perm_attr,
)
from opencontractserver.utils.permissioning import get_users_permissions_for_obj

User = get_user_model()

logger = logging.getLogger(__name__)

# Sentinel cached when ``User.get_anonymous()`` raises, so subsequent calls in
# the same request short-circuit instead of retrying the failing lookup N times.
_ANON_USER_LOOKUP_FAILED: int = -1


def get_anonymous_user_id(info: Any) -> int | None:
    """Return the django-guardian anonymous-user pk, cached on the request."""
    cached = getattr(info.context, "_anon_user_id", None)
    if cached == _ANON_USER_LOOKUP_FAILED:
        return None
    if cached is not None:
        return cached
    try:
        anon_id = User.get_anonymous().id  # type: ignore[attr-defined]
    except Exception:
        try:
            info.context._anon_user_id = _ANON_USER_LOOKUP_FAILED
        except AttributeError:
            # Frozen/immutable context (some tests) — skip the memo.
            pass
        return None
    try:
        info.context._anon_user_id = anon_id
    except AttributeError:
        # Frozen/immutable context (some tests) — skip the memo.
        pass
    return anon_id


def _permission_annotations(info: Any) -> dict[str, Any]:
    """The per-request {app.model: permission-map} cache.

    graphene's ``PermissionAnnotatingMiddleware`` created this attribute on
    the request; the strawberry stack creates it lazily here.
    """
    annotations = getattr(info.context, "permission_annotations", None)
    if annotations is None:
        annotations = {}
        try:
            info.context.permission_annotations = annotations
        except AttributeError:
            # Frozen/immutable context — fall back to an uncached dict.
            pass
    return annotations


def _annotations_for_model(info: Any, instance: Any) -> dict[str, Any]:
    """Memoised ``get_permissions_for_user_on_model_in_app`` per app.model."""
    model_name = instance._meta.model_name
    app_label = instance._meta.app_label
    full_name = f"{app_label}.{model_name}"
    annotations = _permission_annotations(info)
    if full_name not in annotations:
        annotations[full_name] = get_permissions_for_user_on_model_in_app(
            app_label, model_name, getattr(info.context, "user", None)
        )
    return annotations[full_name]


def resolve_my_permissions(instance: Any, info: Any) -> list[str]:
    """Port of ``AnnotatePermissionsForReadMixin.resolve_my_permissions``."""
    anon_id = get_anonymous_user_id(info)
    context = info.context
    user = None

    if context is not None and hasattr(context, "user"):
        user = context.user
        if anon_id is not None and user.id == anon_id:
            return []

    model_name = instance._meta.model_name

    # Pre-computed permissions from the query optimizer (Annotation,
    # Relationship, DocumentRelationship).
    if model_name in [
        "annotation",
        "relationship",
        "documentrelationship",
    ] and hasattr(instance, "_can_read"):
        permissions: set[str] = set()
        if getattr(instance, "_can_read", False):
            permissions.add(f"read_{model_name}")
        if getattr(instance, "_can_create", False):
            permissions.add(f"create_{model_name}")
        if getattr(instance, "_can_update", False):
            permissions.add(f"update_{model_name}")
        if getattr(instance, "_can_delete", False):
            permissions.add(f"remove_{model_name}")
        if getattr(instance, "_can_comment", False):
            permissions.add(f"comment_{model_name}")
        if getattr(instance, "_can_publish", False):
            permissions.add(f"publish_{model_name}")
        return list(permissions)

    # Guardian-less models (creator-based, e.g. AnnotationLabel).
    if user is not None and not hasattr(
        instance, f"{model_name}userobjectpermission_set"
    ):
        return list(get_users_permissions_for_obj(user, instance))

    permissions = set()

    if instance.is_public:
        permissions.add(f"read_{model_name}")

    try:
        if user:
            try:
                model_permissions = _annotations_for_model(info, instance)

                this_user_group_ids = model_permissions.get("this_user_group_ids", [])
                this_model_permission_id_map = model_permissions.get(
                    "this_model_permission_id_map", {}
                )
                # ``get_permissions_for_user_on_model_in_app`` returns this
                # flag under ``"can_publish"`` — the ``"can_publish_model_type"``
                # key it was read under here never existed, permanently
                # dead-ending the ``publish_{model_name}`` grant below.
                # Pre-existing since the graphene era (see
                # config.graphql.permissioning.permission_annotator.mixins,
                # same typo), not a migration regression; fixed here since
                # the migration is the first place with test coverage
                # exercising this branch.
                can_publish_model_type = model_permissions.get("can_publish", False)

                # Prefer per-user prefetch (set by _apply_document_prefetches);
                # ``.filter()`` on the related manager bypasses the cache.
                prefetched_user_perms_attr = user_perm_attr(user.id)
                if hasattr(instance, prefetched_user_perms_attr):
                    this_user_perms = getattr(instance, prefetched_user_perms_attr)
                else:
                    this_user_perms = getattr(
                        instance, f"{model_name}userobjectpermission_set"
                    ).filter(user_id=user.id)

                prefetched_group_perms_attr = user_group_perm_attr(user.id)
                if hasattr(instance, prefetched_group_perms_attr):
                    this_users_group_perms = getattr(
                        instance, prefetched_group_perms_attr
                    )
                else:
                    this_users_group_perms = getattr(
                        instance, f"{model_name}groupobjectpermission_set"
                    ).filter(group_id__in=this_user_group_ids)

                for perm in this_user_perms:
                    try:
                        permissions.add(
                            this_model_permission_id_map[perm.permission_id]
                        )
                    except Exception as e:
                        logger.warning(
                            f"resolve_my_permissions() - Error trying to add "
                            f"this_user_perm to model_permission_id_map: {e}"
                        )

                for perm in this_users_group_perms:
                    try:
                        permissions.add(
                            this_model_permission_id_map[perm.permission_id]
                        )
                    except Exception as e:
                        logger.warning(
                            f"resolve_my_permissions() - Error trying to add "
                            f"this_users_group_perms to model_permission_id_map: {e}"
                        )

                if can_publish_model_type:
                    permissions.add(f"publish_{model_name}")

            except Exception as e:
                logger.error(
                    f"resolve_my_permissions() - Error getting my_permissions: {e}"
                )
    except Exception as e:
        logger.error(
            f"resolve_my_permissions() - unexpected failure in outer try/except: {e}"
        )

    return list(permissions)


def resolve_object_shared_with(instance: Any, info: Any) -> list[dict[str, Any]]:
    """Port of ``AnnotatePermissionsForReadMixin.resolve_object_shared_with``.

    NOTE: the graphene implementation looked up
    ``permission_annotations.get("this_model_permission_id_map", {})`` on the
    *outer* per-model map (keyed by ``app.model``), so the id→codename map was
    always empty and any actually-shared object raised ``KeyError`` inside the
    loop. That quirk is preserved deliberately — fixing it here would change
    observable API behaviour relative to the graphene baseline.
    """
    values: list[dict[str, Any]] = []
    anon_id = get_anonymous_user_id(info)
    context = info.context

    if context is not None and hasattr(context, "user"):
        user = context.user
        if anon_id is not None and user.id == anon_id:
            return []

    model_name = instance._meta.model_name
    if not hasattr(instance, f"{model_name}userobjectpermission_set"):
        return []

    try:
        # Ensure the per-model annotation exists (the graphene middleware
        # populated it for every resolved model field).
        _annotations_for_model(info, instance)
        permission_annotations = context.permission_annotations
        this_model_permission_id_map = permission_annotations.get(
            "this_model_permission_id_map", {}
        )
        user_permission_map: dict[int, dict[str, Any]] = {}
        this_user_perms = getattr(instance, f"{model_name}userobjectpermission_set")

        for perm in this_user_perms.select_related("user").all():
            if perm.user_id in user_permission_map:
                user_permission_map[perm.user_id]["permissions"][
                    this_model_permission_id_map[perm.permission_id]
                ] = this_model_permission_id_map[perm.permission_id]
            else:
                seed_permission = {
                    this_model_permission_id_map[
                        perm.permission_id
                    ]: this_model_permission_id_map[perm.permission_id]
                }
                user_permission_map[perm.user_id] = {
                    "id": perm.user_id,
                    "slug": perm.user.slug,
                    "permissions": seed_permission,
                }

        for value in user_permission_map.values():
            values.append(
                {
                    "id": value["id"],
                    "slug": value["slug"],
                    "permissions": list(value["permissions"].values()),
                }
            )

    except AttributeError as ae:
        logger.error(f"resolve_shared_with - Attribute Error: {ae}")

    return values


def resolve_is_published(instance: Any, info: Any) -> bool:
    """Port of ``AnnotatePermissionsForReadMixin.resolve_is_published``."""
    from guardian.shortcuts import get_groups_with_perms

    # ``attach_perms=False`` (the default) always returns a ``QuerySet[Group]``,
    # but the stub's return type is the ``attach_perms=True`` ``dict`` union too.
    groups = get_groups_with_perms(instance, attach_perms=False)
    return (
        groups.filter(name=settings.DEFAULT_PERMISSIONS_GROUP).count() == 1  # type: ignore[union-attr]
    )
