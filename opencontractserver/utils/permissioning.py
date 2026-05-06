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
from opencontractserver.types.enums import PermissionTypes

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus
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


def user_has_permission_for_obj(
    user_val: int | str | UserModel,
    instance: django.db.models.Model,
    permission: PermissionTypes,
    include_group_permissions: bool = False,
) -> bool:
    """
    Check if user has a specific permission on an object via django-guardian.

    ⚠️  IMPORTANT LIMITATION - READ THIS BEFORE USING ⚠️

    This function checks ONLY for explicit object-level permissions:
    - Django-guardian user/group permissions on the object
    - is_public flag (grants READ)
    - Superuser status

    It does NOT consider:
    - Creator status (for models with guardian permissions)
    - Corpus context / inherited permissions
    - Complex visibility rules from query resolvers

    FOR CORPUS-SCOPED OBJECTS (documents in a corpus, metadata, etc.):
    Do NOT use this function for READ/visibility checks. Instead use:
        Model.objects.visible_to_user(user).filter(id=obj_id).exists()

    The visible_to_user() pattern handles the full permission model including
    creator access, corpus membership, and other context-dependent rules.

    USE THIS FUNCTION FOR:
    - Top-level objects with explicit permissions (Corpus, Analysis, Extract)
    - Write permission checks where explicit guardian permissions are required
    - Annotation/Relationship permission checks (has special handling built-in)

    Special handling for Annotations:
    - Annotations with created_by_analysis or created_by_extract fields require permission
      to the source object (analysis/extract) in addition to document+corpus permissions.
    - Uses AnnotationQueryOptimizer for computing effective permissions.
    """
    # Provides some flexibility to use ids where passing object is not practical
    if isinstance(user_val, str) or isinstance(user_val, int):
        user = User.objects.get(id=user_val)
    else:
        user = user_val

    model_name = instance._meta.model_name
    app_label = instance._meta.app_label
    logger.debug(
        "user_has_permission_for_obj() - check %s on %s.%s for %s",
        permission,
        app_label,
        model_name,
        user.username,
    )

    # Special handling for annotations with privacy fields
    if model_name == "annotation" and app_label == "annotations":
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        if isinstance(instance, Annotation):
            # Superusers always have permission
            if user.is_superuser:
                return True

            # Structural annotations are always read-only if document is readable
            # Check this BEFORE privacy checks so structural annotations are always visible
            if instance.structural and permission != PermissionTypes.READ:
                logger.info(
                    f"User {user.username} denied write access to structural annotation {instance.id}"
                )
                return False

            # Check if this is a private annotation (but not if it's structural and we're just reading)
            if (
                instance.created_by_analysis_id or instance.created_by_extract_id
            ) and not (instance.structural and permission == PermissionTypes.READ):
                # For private annotations, permissions are limited by BOTH the source object AND doc+corpus
                # We need to check the source object permissions match or exceed what's being requested
                if instance.created_by_analysis_id:
                    source_analysis = instance.created_by_analysis
                    if source_analysis is None or not user_has_permission_for_obj(
                        user,
                        source_analysis,
                        permission,  # Check for the same permission level being requested
                        include_group_permissions=include_group_permissions,
                    ):
                        logger.info(
                            f"User {user.username} denied {permission} access to annotation {instance.id} - "
                            f"insufficient permission on analysis {instance.created_by_analysis_id}"
                        )
                        return False
                elif instance.created_by_extract_id:
                    source_extract = instance.created_by_extract
                    if source_extract is None or not user_has_permission_for_obj(
                        user,
                        source_extract,
                        permission,  # Check for the same permission level being requested
                        include_group_permissions=include_group_permissions,
                    ):
                        logger.info(
                            f"User {user.username} denied {permission} access to annotation {instance.id} - "
                            f"insufficient permission on extract {instance.created_by_extract_id}"
                        )
                        return False

            # Now check document+corpus permissions using the query optimizer.
            # An annotation without a parent document has no inheritable scope,
            # so non-superuser access is denied (the superuser branch is above).
            if instance.document_id is None:
                return False
            can_read, can_create, can_update, can_delete, can_comment = (
                AnnotationQueryOptimizer._compute_effective_permissions(
                    user=user,
                    document_id=instance.document_id,
                    corpus_id=instance.corpus_id,
                )
            )

            # Map the requested permission to the computed permissions
            if permission == PermissionTypes.READ:
                return can_read
            elif permission == PermissionTypes.CREATE:
                return can_create
            elif (
                permission == PermissionTypes.UPDATE
                or permission == PermissionTypes.EDIT
            ):
                return can_update
            elif permission == PermissionTypes.DELETE:
                return can_delete
            elif permission == PermissionTypes.COMMENT:
                return can_comment
            elif permission == PermissionTypes.CRUD:
                return can_read and can_create and can_update and can_delete
            elif permission == PermissionTypes.ALL:
                # For annotations, ALL includes COMMENT but not publish/permission
                return (
                    can_read
                    and can_create
                    and can_update
                    and can_delete
                    and can_comment
                )
            else:
                # Annotations don't support PUBLISH or PERMISSION
                return False

    # Special handling for relationships (similar to annotations)
    if model_name == "relationship" and app_label == "annotations":
        from opencontractserver.annotations.models import Relationship
        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        if isinstance(instance, Relationship):
            # Superusers always have permission
            if user.is_superuser:
                return True

            # Structural relationships are ALWAYS read-only (only superusers can modify)
            # Check this FIRST before any other permission checks
            if instance.structural and permission != PermissionTypes.READ:
                logger.info(
                    f"User {user.username} denied write access to structural relationship {instance.id}"
                )
                return False

            # Relationships inherit permissions from document+corpus.
            # Relationships without a document have no inheritable scope, so
            # we deny all non-superuser access (the superuser short-circuit
            # above is the only escape).
            if instance.document_id is None:
                return False
            can_read, can_create, can_update, can_delete, can_comment = (
                AnnotationQueryOptimizer._compute_effective_permissions(
                    user=user,
                    document_id=instance.document_id,
                    corpus_id=instance.corpus_id,
                )
            )

            # Map the requested permission to the computed permissions
            if permission == PermissionTypes.READ:
                return can_read
            elif permission == PermissionTypes.CREATE:
                return can_create
            elif (
                permission == PermissionTypes.UPDATE
                or permission == PermissionTypes.EDIT
            ):
                return can_update
            elif permission == PermissionTypes.DELETE:
                return can_delete
            elif permission == PermissionTypes.COMMENT:
                return can_comment
            elif permission == PermissionTypes.CRUD:
                return can_read and can_create and can_update and can_delete
            elif permission == PermissionTypes.ALL:
                # For relationships, ALL includes COMMENT but not publish/permission
                return (
                    can_read
                    and can_create
                    and can_update
                    and can_delete
                    and can_comment
                )
            else:
                # Relationships don't support PUBLISH or PERMISSION
                return False

    # Standard permission checking for all other models
    model_permissions_for_user = get_users_permissions_for_obj(
        user=user,
        instance=instance,
        include_group_permissions=include_group_permissions,
    )
    logger.debug(
        f"user_has_permission_for_obj - user {user} has model_permissions: {model_permissions_for_user}"
    )
    logger.debug(f"user_has_permission_for_obj - permission: {permission}")

    if permission == PermissionTypes.READ:
        return len(model_permissions_for_user.intersection({f"read_{model_name}"})) > 0
    elif permission == PermissionTypes.CREATE:
        return (
            len(model_permissions_for_user.intersection({f"create_{model_name}"})) > 0
        )
    elif permission == PermissionTypes.UPDATE or permission == PermissionTypes.EDIT:
        return (
            len(model_permissions_for_user.intersection({f"update_{model_name}"})) > 0
        )
    elif permission == PermissionTypes.DELETE:
        return (
            len(model_permissions_for_user.intersection({f"remove_{model_name}"})) > 0
        )
    elif permission == PermissionTypes.COMMENT:
        return (
            len(model_permissions_for_user.intersection({f"comment_{model_name}"})) > 0
        )
    elif permission == PermissionTypes.PUBLISH:
        return (
            len(model_permissions_for_user.intersection({f"publish_{model_name}"})) > 0
        )
    elif permission == PermissionTypes.PERMISSION:
        return (
            len(model_permissions_for_user.intersection({f"permission_{model_name}"}))
            > 0
        )
    elif permission == PermissionTypes.CRUD:
        return (
            len(
                model_permissions_for_user.intersection(
                    {
                        f"create_{model_name}",
                        f"read_{model_name}",
                        f"update_{model_name}",
                        f"remove_{model_name}",
                    }
                )
            )
            == 4
        )
    elif permission == PermissionTypes.ALL:
        return (
            len(
                model_permissions_for_user.intersection(
                    {
                        f"create_{model_name}",
                        f"read_{model_name}",
                        f"update_{model_name}",
                        f"remove_{model_name}",
                        f"comment_{model_name}",
                        f"publish_{model_name}",
                        f"permission_{model_name}",
                    }
                )
            )
            == 7
        )
    else:
        return False


def user_can_modify_corpus(
    user_val: int | str | UserModel | AnonymousUser | None,
    corpus: Corpus,
    *,
    include_group_permissions: bool = True,
) -> bool:
    """
    Single-source-of-truth check for "can this user modify this corpus".

    Canonical pattern, replacing inline
    ``user.is_superuser or corpus.creator_id == user.id or
    user_has_permission_for_obj(user, corpus, UPDATE, ...)`` checks
    scattered across mutations. Centralizing keeps mutation paths
    consistent as the permission model evolves (sharing, group
    inheritance, MIN(doc, corpus)).

    Returns True iff:
        - user is a superuser, OR
        - user is the corpus creator, OR
        - user has explicit guardian UPDATE on the corpus (optionally
          via group permissions).

    Anonymous / unauthenticated users always get False. A non-existent
    user id is also rejected with ``False`` (rather than raising) so
    callers can hand-resolve dangling/external ids without a try/except.

    Args:
        user_val: A user id (int or string-encoded int), a User
            instance, ``AnonymousUser``, or ``None``. ``None`` and
            unauthenticated users are rejected.
        corpus: The Corpus instance to check against.
        include_group_permissions: Whether to consult group-level
            guardian permissions in addition to user-level ones.
            Defaults to True, matching the call sites this helper
            replaces.
    """
    if user_val is None:
        return False

    if isinstance(user_val, AnonymousUser):
        return False

    if isinstance(user_val, (str, int)):
        try:
            user = User.objects.get(id=user_val)
        except User.DoesNotExist:
            return False
    else:
        user = user_val

    if not getattr(user, "is_authenticated", False):
        return False

    if user.is_superuser:
        return True

    if getattr(corpus, "creator_id", None) == user.id:
        return True

    return user_has_permission_for_obj(
        user,
        corpus,
        PermissionTypes.UPDATE,
        include_group_permissions=include_group_permissions,
    )
