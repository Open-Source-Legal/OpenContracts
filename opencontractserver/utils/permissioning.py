from __future__ import annotations

import logging

import django
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import models, transaction

from opencontractserver.types.enums import PermissionTypes

User = get_user_model()
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
#                             HELPER FUNCTIONS
# -------------------------------------------------------------------------


def _get_permission_mapping() -> dict[PermissionTypes, set[str]]:
    """
    Private helper that returns the expansions for our special permission enums,
    i.e. CRUD => create, read, update, delete and ALL => create, read, update, delete, permission, publish.
    Used by both set_permissions_for_obj_to_user and filter_queryset_by_permission to maintain consistency.
    """
    logger.debug("_get_permission_mapping called")
    mapping = {
        PermissionTypes.CRUD: {"CREATE", "READ", "UPDATE", "DELETE"},
        PermissionTypes.ALL: {
            "CREATE",
            "READ",
            "UPDATE",
            "DELETE",
            "PERMISSION",
            "PUBLISH",
        },
    }
    logger.debug(f"Permission mapping: {mapping}")

    # Log all available PermissionTypes for comparison
    all_permission_types = [pt for pt in PermissionTypes]
    logger.debug(f"All available PermissionTypes: {all_permission_types}")

    return mapping


def _get_db_codename_for_action(action: str, model_name: str) -> str:
    """
    Convert an action string (e.g., "delete") to the actual database codename (e.g., "remove_corpus").
    This centralizes our permission naming conventions to avoid mismatches.
    """
    logger.debug(
        f"_get_db_codename_for_action called with action: {action}, model_name: {model_name}"
    )
    action_lower = action.lower()

    # Special case: Django models.Meta uses "remove_corpus" for the delete permission
    if action_lower == "delete":
        logger.debug("Converting 'delete' to 'remove' for Django compatibility")
        action_lower = "remove"

    codename = f"{action_lower}_{model_name}"
    logger.debug(f"Generated codename: {codename}")
    return codename


def _get_actions_for_permissions(
    permissions: PermissionTypes | list[PermissionTypes],
) -> set[str]:
    """
    Given a permission or list of permissions from PermissionTypes, returns
    the combined set of actions (strings) they represent.
    """
    # Normalize to a list.
    if not isinstance(permissions, list):
        permissions = [permissions]

    permission_mapping = _get_permission_mapping()
    actions_to_assign: set[str] = set()
    for perm in permissions:
        # For special permission types, use the mapping
        if perm in permission_mapping:
            actions = permission_mapping[perm]
        # For basic permission types, use the permission value directly
        else:
            actions = {perm.value}
        actions_to_assign.update(actions)
    return actions_to_assign


def _clear_object_level_perms(instance: models.Model) -> None:
    """
    Removes all existing object-level permissions for the given instance,
    regardless of user or group.
    """
    logger.debug(
        f"_clear_object_level_perms called for {instance._meta.model_name} {instance.pk}"
    )

    model_name = instance._meta.model_name

    # Log existing permissions before clearing
    from guardian.shortcuts import get_users_with_perms

    users_with_perms = get_users_with_perms(instance, attach_perms=True)
    logger.debug(f"Users with permissions before clearing: {users_with_perms}")

    existing_permissions = getattr(instance, f"{model_name}userobjectpermission_set")
    perm_count = existing_permissions.count()
    logger.debug(f"Found {perm_count} user object permissions to clear")
    existing_permissions.all().delete()
    logger.debug(f"Cleared {perm_count} user object permissions")

    group_permissions = getattr(
        instance, f"{model_name}groupobjectpermission_set", None
    )
    if group_permissions:
        group_perm_count = group_permissions.count()
        logger.debug(f"Found {group_perm_count} group object permissions to clear")
        group_permissions.all().delete()
        logger.debug(f"Cleared {group_perm_count} group object permissions")
    else:
        logger.debug(f"No group permissions attribute found for {model_name}")

    # Log permissions after clearing
    users_with_perms_after = get_users_with_perms(instance, attach_perms=True)
    logger.debug(f"Users with permissions after clearing: {users_with_perms_after}")


def _assign_actions_to_user_for_obj(
    user: User, instance: models.Model, actions: set[str]
) -> None:
    """
    Assign each action in 'actions' (e.g. "read", "update") to the user
    for the given instance, using django-guardian's assign_perm.
    """
    import sys

    from django.contrib.auth.models import Permission
    from django.core.exceptions import ObjectDoesNotExist
    from django.db.transaction import TransactionManagementError
    from guardian.shortcuts import get_perms_for_model

    # Debug by printing available permissions for your model
    logger.debug(
        f"Available permissions for {instance.__class__}: {get_perms_for_model(instance.__class__)}"
    )
    for perm in get_perms_for_model(instance.__class__):
        logger.debug(f"Permission {perm.codename}: {perm} ")
    logger.debug(
        f"_assign_actions_to_user_for_obj called for user {user.username} with actions: {actions}"
    )

    model_name = instance._meta.model_name
    app_name = instance._meta.app_label

    logger.debug(f"Model name: {model_name}, App name: {app_name}")

    # Check if we're running in a test environment
    is_test = "test" in sys.argv or any("pytest" in arg for arg in sys.argv)
    if is_test:
        logger.debug("Running in test environment - special handling for permissions")

    # Create list to store successful permissions
    successful_permissions = []

    # Process each action and create permissions
    for action in actions:
        # Use the centralized helper to get the correct codename
        perm_codename = _get_db_codename_for_action(action, model_name)
        logger.debug(
            f"Converting action '{action}' to permission codename: '{perm_codename}'"
        )

        try:
            # Guardian expects the full permission string with app_label
            full_perm = f"{app_name}.{perm_codename}"
            logger.debug(
                f"Assigning permission '{full_perm}' to user {user.username} for {model_name} {instance.pk}"
            )

            # Create permission object directly without transaction
            obj_perm, created = assign_permission_directly(
                user, perm_codename, instance
            )
            logger.debug(f"Permission created: {created}, object: {obj_perm}")

            if obj_perm and created:
                successful_permissions.append(perm_codename)

        except (Permission.DoesNotExist, ObjectDoesNotExist) as exc:
            logger.warning(
                f"Permission '{perm_codename}' does not exist for '{model_name}'; skipping assignment. "
                f"Error: {exc}"
            )

    # After all permissions have been created, explicitly commit the transaction
    if transaction.get_autocommit() is False and not is_test:
        try:
            transaction.commit()
            logger.debug(
                "Explicitly committed transaction to ensure permissions are saved"
            )
        except TransactionManagementError:
            # We're inside an atomic block, can't commit directly
            logger.debug("Inside atomic block, can't commit transaction directly")
            # Force Django to save the permission object instead
            from django.db import connection

            connection.cursor().execute(
                "SELECT 1"
            )  # This forces a flush to the DB in most cases
            logger.debug("Attempted to flush DB operations")


def resolve_user(user: User | int | str) -> User:
    """Resolve a user given an int (id), a string (username or numeric id), or a User instance.
    If the provided user is anonymous, return it immediately.
    """
    logger = logging.getLogger(__name__)
    if hasattr(user, "is_anonymous") and user.is_anonymous:
        logger.debug("RESOLVE_USER: AnonymousUser provided; returning as is")
        return user

    try:
        if isinstance(user, str) and user.isdigit():
            logger.debug(f"RESOLVE_USER: Resolving numeric string '{user}' as user ID")
            resolved_user = User.objects.get(id=int(user))
            logger.info(
                f"RESOLVE_USER: Successfully resolved user ID {user} to user {resolved_user.username}"
            )
            return resolved_user
        elif isinstance(user, str):
            logger.debug(f"RESOLVE_USER: Resolving string '{user}' as username")
            resolved_user = User.objects.get(username=user)
            logger.info(
                f"RESOLVE_USER: Successfully resolved username '{user}' to user ID {resolved_user.id}"
            )
            return resolved_user
        elif isinstance(user, int):
            logger.debug(f"RESOLVE_USER: Resolving int {user} as user ID")
            resolved_user = User.objects.get(id=user)
            logger.info(
                f"RESOLVE_USER: Successfully resolved user ID {user} to user {resolved_user.username}"
            )
            return resolved_user
        elif hasattr(user, "id"):
            logger.debug(
                f"RESOLVE_USER: User object already provided (ID: {user.id}, username: {user.username})"
            )
            return user
        else:
            logger.error(f"RESOLVE_USER: Invalid user argument type: {type(user)}")
            raise ValueError(
                f"Invalid user argument type: {type(user)}, expected int, str, or User object"
            )
    except User.DoesNotExist as e:
        logger.error(f"RESOLVE_USER: User not found: {str(e)}")
        raise


def filter_queryset_by_permission(
    queryset: models.QuerySet,
    user: User | AnonymousUser,
    permission: str | PermissionTypes = "read",
) -> models.QuerySet:
    """
    Returns a queryset filtered so that only objects the given user is allowed to
    access under a given permission are included.

    BIG-PICTURE CRITERIA:
      1. Superusers see all objects.
      2. Anonymous users see only objects with is_public==True.
      3. Authenticated users:
         - For "read" permission:
             * See objects that are public OR they created,
               OR for which they have an explicit Guardian permission (e.g. "read_<model>").
             * If model.INHERITS_CORPUS_PERMISSIONS is True, and the user has the *same* permission on the corpus,
               they inherit that permission on the child.
         - For non-"read" permissions:
             * See objects they created OR for which they have explicit Guardian permission (e.g. "update_<model>").
             * If model.INHERITS_CORPUS_PERMISSIONS is True, and the user has the *same* permission on the corpus,
               they inherit that permission on the child as well.
         - Special permission types:
             * CRUD => union of create, read, update, delete
             * ALL => union of create, read, update, delete, permission, publish
    """

    from django.db.models import Q

    model_name = queryset.model._meta.model_name
    logger.info(
        f"Filtering {model_name} queryset for user {user} with permission: {permission}"
    )

    # If permission is a string, convert it to lowercase
    if isinstance(permission, str):
        permission = permission.lower()
    else:
        # If it's an enum, get its lowercase string value
        permission = permission.value.lower()

    # Superuser => all
    if getattr(user, "is_superuser", False):
        logger.info("User is superuser - returning all objects")
        return queryset.all()

    # Anonymous => only public
    if getattr(user, "is_anonymous", False):
        logger.info("User is anonymous - returning only public objects")
        # No need to worry about corpus fallback for anonymous:
        # they only get is_public anyway unless explicitly handled in code for anonymous.
        return queryset.filter(is_public=True).distinct()

    # Authenticated logic:

    # Base query depends on read vs. other (e.g. update/delete)
    if permission == "read":
        base_q = Q(is_public=True) | Q(creator=user)
    else:
        base_q = Q(creator=user)

    logger.info(f"Base query: {base_q}")

    # Get the correct permission codename using our centralized helper
    permission_codename = _get_db_codename_for_action(permission, model_name)

    logger.info(f"Looking for Guardian permission: {permission_codename}")
    guardian_q = Q(
        **{
            f"{model_name}userobjectpermission__permission__codename": permission_codename,
            f"{model_name}userobjectpermission__user": user,
        }
    )

    qs = queryset.filter(base_q | guardian_q)
    logger.info(f"After base and guardian filtering: {qs.count()} objects")

    # If the model says to inherit corpus permissions, then union with all objects
    # whose corpus** is visible under the *same* permission.
    inherits_permissions = hasattr(
        queryset.model, "INHERITS_CORPUS_PERMISSIONS"
    ) and getattr(queryset.model, "INHERITS_CORPUS_PERMISSIONS", False)
    if inherits_permissions and hasattr(queryset.model, "corpus"):
        logger.info(
            "Model has 'corpus' relation and inherits corpus permissions - checking corpus-level perms"
        )
        qs = _add_corpus_fallback(qs, user, permission)

    final_qs = qs.distinct()
    logger.info(f"Final filtered queryset has {final_qs.count()} objects")
    return final_qs


def _add_corpus_fallback(
    child_queryset: models.QuerySet,
    user: User,
    permission: str,
) -> models.QuerySet:
    """
    Return child_queryset enhanced with objects whose corpus is permitted to the user
    under the *same* 'permission'.

    1) Build a set of corpus PKs the user can access under `permission`.
    2) Return a queryset that includes objects whose corpus is in the permitted set.
    """

    from django.db.models import Q, Subquery

    from opencontractserver.corpuses.models import Corpus

    logger.debug(
        f"_add_corpus_fallback called for user {user} with permission {permission}"
    )

    # If user is superuser, all corpora are permitted
    if user.is_superuser:
        logger.debug("User is superuser - all corpora are permitted")
        # No need to filter further for superusers
        return child_queryset

    # If user is anonymous, no fallback
    elif user.is_anonymous:
        logger.debug("User is anonymous - no corpus fallback")
        # Normally anonymous users only get is_public anyway.
        # We won't add anything here.
        return child_queryset
    else:
        # Build a base corpus Q
        if permission.lower() == "read":
            # read => public or own or guardian read
            corpus_base_q = Q(is_public=True) | Q(creator=user)
        else:
            corpus_base_q = Q(creator=user)

        corpus_codename = f"{permission.lower()}_corpus"
        guardian_corpus_q = Q(
            **{
                "corpususerobjectpermission__permission__codename": corpus_codename,
                "corpususerobjectpermission__user": user,
            }
        )

        # Get the IDs of permitted corpora
        permitted_corpora = Corpus.objects.filter(
            corpus_base_q | guardian_corpus_q
        ).distinct()
        permitted_corpus_ids = list(permitted_corpora.values_list("pk", flat=True))

        logger.debug(
            f"Found {len(permitted_corpus_ids)} permitted corpus IDs for user {user}"
        )

        if not permitted_corpus_ids:
            # No permitted corpora, return original queryset
            logger.debug("No permitted corpora found - returning original queryset")
            return child_queryset

        # Create a new condition to include objects with permitted corpus
        # Use Q objects to create a more compatible query structure
        model = child_queryset.model
        model_name = model._meta.model_name

        logger.debug(f"Adding corpus fallback condition for model {model_name}")

        # Create a new queryset with the same base as the original but with an additional filter
        # This avoids creating incompatible query structures
        enhanced_qs = model.objects.filter(
            Q(pk__in=Subquery(child_queryset.values("pk")))
            | Q(corpus__in=permitted_corpus_ids)
        ).distinct()

        logger.debug("Enhanced queryset created with corpus fallback")

        return enhanced_qs


def user_has_permission_for_obj(
    user_val: int | str | User,
    instance: models.Model,
    permission: PermissionTypes,
    include_group_permissions: bool = True,  # currently not used separately
) -> bool:
    """
    Check if a user has the given permission on an object.

    This function reuses the central permission filtering logic by constructing
    a queryset for the instance and filtering it using filter_queryset_by_permission.

    Args:
        user_val: A User instance, an int (ID) or a str (ID or username).
        instance: The Django model instance to check.
        permission: The permission to check (from PermissionTypes).
        include_group_permissions: (Not separately used here since the helper already includes group permissions)

    Returns:
        True if the object is visible under the given permission; False otherwise.
    """
    user = resolve_user(user_val)
    logger.debug(
        f"user_has_permission_for_obj called for user {user.username} on {instance._meta.model_name} {instance.pk}"
    )
    logger.debug(f"Checking permission: {permission}")

    # Special handling for composite permission types (ALL, CRUD)
    if permission in [PermissionTypes.ALL, PermissionTypes.CRUD]:
        logger.debug(f"Special handling for composite permission type: {permission}")
        # Get the component permissions
        permission_mapping = _get_permission_mapping()
        component_permissions = permission_mapping.get(permission, set())
        logger.debug(f"Component permissions to check: {component_permissions}")

        # Check if the user has all the component permissions
        for component in component_permissions:
            logger.debug(f"Checking component permission: {component}")
            # Convert string permission to enum
            try:
                component_enum = getattr(PermissionTypes, component)
                logger.debug(f"Converted to enum: {component_enum}")
                if not user_has_permission_for_obj(user, instance, component_enum):
                    logger.debug(
                        f"User does not have component permission: {component}"
                    )
                    return False
            except AttributeError:
                logger.error(f"Invalid permission type: {component}")
                return False

        logger.debug(f"User has all component permissions for {permission}")
        return True

    # For direct permission checks, use get_users_permissions_for_obj
    # This is more reliable than filter_queryset_by_permission for individual objects
    model_name = instance._meta.model_name
    perm_codename = _get_db_codename_for_action(permission.value.lower(), model_name)
    logger.debug(f"Checking for permission codename: {perm_codename}")

    user_perms = get_users_permissions_for_obj(
        user, instance, include_group_permissions
    )
    logger.debug(f"User permissions: {user_perms}")

    # Check if the user has the specific permission
    has_perm = perm_codename in user_perms
    logger.debug(f"Permission check result: {has_perm}")

    # If not found directly, try the queryset approach as a fallback
    if not has_perm:
        logger.debug("Permission not found directly, trying queryset approach")
        qs = instance.__class__.objects.filter(pk=instance.pk)
        perm_str = permission.value.lower()
        visible_qs = filter_queryset_by_permission(qs, user, perm_str)
        has_perm = visible_qs.exists()
        logger.debug(f"Queryset approach result: {has_perm}")

    return has_perm


def set_permissions_for_obj_to_user(
    user_val: int | str | User,
    instance: django.db.models.Model,
    permissions: PermissionTypes | list[PermissionTypes],
) -> None:
    """
    Given a Django model instance, a user (or user id), and either a single or a list of desired
    permissions, REPLACE current object-level permissions with the specified ones.
    Special Cases:
      - CRUD assigns: create, read, update, delete.
      - ALL assigns: create, read, update, delete, permission, publish.
    """
    # Resolve user
    user = resolve_user(user_val)
    logger.debug(
        f"set_permissions_for_obj_to_user called for user {user.username} on {instance._meta.model_name} {instance.pk}"
    )
    logger.debug(f"Permissions to set: {permissions}")

    # Convert the user-specified PermissionTypes into underlying actions
    logger.debug("Converting permission types to actions")
    actions_to_assign = _get_actions_for_permissions(permissions)
    logger.debug(f"Actions to assign: {actions_to_assign}")

    # Now assign them to the user
    logger.debug(f"Assigning actions to user {user.username}")
    with transaction.atomic():
        _assign_actions_to_user_for_obj(user, instance, actions_to_assign)

    # Log the final permissions
    from guardian.shortcuts import get_perms

    final_perms = get_perms(user, instance)
    logger.debug(
        f"Final permissions for user {user.username} on {instance._meta.model_name} {instance.pk}: {final_perms}"
    )

    # Also log the permissions from our custom function
    custom_perms = get_users_permissions_for_obj(user, instance)
    logger.debug(f"Custom get_users_permissions_for_obj result: {custom_perms}")


def get_user_permissions_table_data(
    users: list[User], instance: models.Model
) -> dict[int, dict[str, bool]]:
    """
    Return a dictionary mapping each user's ID to a dictionary of permission-type -> bool,
    indicating whether they hold each of the table's permission columns (CREATE, READ, UPDATE,
    DELETE, PERMISSION, PUBLISH, CRUD, ALL) for the given instance.

    This function uses a single pass at collecting the user's codenames by calling
    get_users_permissions_for_obj(user, instance), and then infers whether a user has each
    permission type. Composite permissions (CRUD, ALL) are expanded by checking the relevant
    individual codenames.
    """
    # These are the same permission types used in generate_permissions_md_table_for_object
    permission_types = [
        PermissionTypes.CREATE,
        PermissionTypes.READ,
        PermissionTypes.UPDATE,
        PermissionTypes.DELETE,
        PermissionTypes.PERMISSION,
        PermissionTypes.PUBLISH,
        PermissionTypes.CRUD,
        PermissionTypes.ALL,
    ]

    # A helper for expanding composite permission types
    # (CRUD => create, read, update, delete, ALL => + permission, publish)
    composite_mapping = (
        _get_permission_mapping()
    )  # {CRUD: {CREATE, READ, UPDATE, DELETE}, ALL: {...}}
    # Turn the sets of uppercase members into sets of string-lower for codenames
    # e.g. CRUD => {"create", "read", "update", "delete"}, then we'll build codenames with _get_db_codename_for_action
    composite_dict = {
        perm_type: {action.lower() for action in composite_mapping[perm_type]}
        for perm_type in composite_mapping
    }

    # We'll store the final: { user.id: { "CREATE": bool, "READ": bool, ... } }
    results: dict[int, dict[str, bool]] = {}

    # For naming the underlying model codenames
    model_name = instance._meta.model_name

    for user_obj in users:

        if user_obj.id is None:
            logger.warning(f"User {user_obj.username} has no ID - skipping")
            continue

        # Fetch all raw codenames (e.g. "read_<model>") for this user on this instance
        codenames = get_users_permissions_for_obj(
            user_obj, instance, include_group_permissions=True
        )

        # Build a sub-dict for each permission type: True/False
        user_data: dict[str, bool] = {}

        for perm in permission_types:
            # If we're dealing with a composite (CRUD or ALL):
            if perm in composite_dict:
                # e.g. if perm == PermissionTypes.CRUD, we see if user has create_<model>, read_<model>, ...
                # for each action in composite_dict[perm], build codename and check membership
                needed_actions = composite_dict[perm]
                has_all = True
                for action in needed_actions:
                    codename = _get_db_codename_for_action(action, model_name)
                    if codename not in codenames:
                        has_all = False
                        break
                user_data[perm.value] = has_all
            else:
                # Normal permission (create, read, etc.): check if its codename is in codenames
                codename = _get_db_codename_for_action(perm.value.lower(), model_name)
                user_data[perm.value] = codename in codenames

        results[user_obj.id] = user_data

    return results


def generate_permissions_md_table_for_object(
    users: list[User], instance: models.Model
) -> str:
    """
    Generate a Markdown table summarizing the effective permissions on a given object for each user.
    This is a thin wrapper that collects all data via get_user_permissions_table_data() and then
    produces a Markdown-formatted string.

    For each user in the list, the following permission types are evaluated:
      - CREATE
      - READ
      - UPDATE
      - DELETE
      - PERMISSION
      - PUBLISH
      - CRUD
      - ALL

    The returned table has one row per user, columns for each permission type, with "Yes"/"No"
    in each cell depending on whether the permission is granted.
    """
    # We re-use the same set of permission types for columns
    permission_types = [
        PermissionTypes.CREATE,
        PermissionTypes.READ,
        PermissionTypes.UPDATE,
        PermissionTypes.DELETE,
        PermissionTypes.PERMISSION,
        PermissionTypes.PUBLISH,
        PermissionTypes.CRUD,
        PermissionTypes.ALL,
    ]

    # Prepare headers
    headers = ["Username"] + [perm.value for perm in permission_types]

    # Collect all user-permission data in a single pass
    table_data = get_user_permissions_table_data(users, instance)

    md_lines = []
    md_lines.append("| " + " | ".join(headers) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for user_obj in users:

        if user_obj.id is None:
            logger.warning(f"User {user_obj.username} has no ID - skipping")
            continue

        username = getattr(user_obj, "username", str(user_obj))
        row = [username]

        # Retrieve the already-computed booleans for each permission type
        user_data = table_data.get(user_obj.id, {})
        for perm in permission_types:
            row.append("Yes" if user_data.get(perm.value, False) else "No")

        md_lines.append("| " + " | ".join(row) + " |")

    return "\n".join(md_lines)


def get_users_permissions_for_obj(
    user_val: User | int | str,
    instance: models.Model,
    include_group_permissions: bool = False,
) -> set[str]:
    """
    Return a set of effective permission codenames for the given user on the provided model instance.

    This function performs a SINGLE pass at collecting all relevant object-level codenames
    rather than calling user_has_permission_for_obj() repeatedly. By doing so, it is more
    performant for scenarios where you need to know every permission the user has at once.

    -------------
    LOGIC SUMMARY:
      1) If user is superuser: return all codenames for 'create', 'read', 'update', 'delete',
         'permission', and 'publish'.
      2) If user is AnonymousUser: only add "read_<model>" if:
         - The instance is marked is_public=True, OR
         - The corpus fallback is relevant and that corpus is public.
      3) For authenticated users:
         - If user == instance.creator, add CRUD automatically.
         - If instance is public, add "read_<model>".
         - If the object is linked to a corpus that is visible, add "read_<model>".
         - Then add any object-level guardian permissions from userobjectpermission
           and (optionally) groupobjectpermission.
    """
    from guardian.models import GroupObjectPermission, UserObjectPermission

    from opencontractserver.corpuses.models import Corpus

    user = resolve_user(user_val)
    logger.debug(
        f"get_users_permissions_for_obj called for user {user.username} on {instance._meta.model_name} {instance.pk}"
    )

    # Extract model info
    model_name = instance._meta.model_name
    app_label = instance._meta.app_label
    logger.debug(f"Model name: {model_name}, App label: {app_label}")

    final_codenames: set[str] = set()

    # 1) SUPERUSER => all codenames
    if getattr(user, "is_superuser", False):
        logger.debug(f"User {user.username} is superuser - granting all permissions")
        for action in ["create", "read", "update", "delete", "permission", "publish"]:
            final_codenames.add(_get_db_codename_for_action(action, model_name))
        logger.debug(f"Final codenames for superuser: {final_codenames}")
        return final_codenames

    # 2) ANONYMOUS => read only if public or corpus fallback
    if isinstance(user, AnonymousUser):
        logger.debug("User is anonymous")
        if getattr(instance, "is_public", False):
            logger.debug("Instance is public - granting read permission")
            final_codenames.add(_get_db_codename_for_action("read", model_name))
        else:
            # corpus fallback
            logger.debug("Instance is not public - checking corpus fallback")
            if hasattr(instance, "corpus") and instance.corpus:
                logger.debug(f"Instance has corpus attribute: {instance.corpus}")
                if Corpus.objects.filter(
                    pk=instance.corpus.pk, is_public=True
                ).exists():
                    logger.debug("Corpus is public - granting read permission")
                    final_codenames.add(_get_db_codename_for_action("read", model_name))
            elif hasattr(instance, "corpus_set"):
                logger.debug("Instance has corpus_set attribute")
                if instance.corpus_set.filter(is_public=True).exists():
                    logger.debug(
                        "Corpus set contains public corpus - granting read permission"
                    )
                    final_codenames.add(_get_db_codename_for_action("read", model_name))
        logger.debug(f"Final codenames for anonymous user: {final_codenames}")
        return final_codenames

    # 3) AUTHENTICATED USERS
    logger.debug(f"Processing authenticated user {user.username}")

    # 3.1) Creator => gets CRUD
    if getattr(instance, "creator_id", None) == user.id:
        logger.debug("User is creator - granting CRUD permissions")
        for action in ["create", "read", "update", "delete"]:
            final_codenames.add(_get_db_codename_for_action(action, model_name))

    # 3.2) is_public => read
    if getattr(instance, "is_public", False):
        logger.debug("Instance is public - granting read permission")
        final_codenames.add(_get_db_codename_for_action("read", model_name))

    # 3.3) corpus fallback => read
    # Single object approach:
    if hasattr(instance, "corpus") and instance.corpus:
        logger.debug(f"Instance has corpus attribute: {instance.corpus}")
        visible_corpora = Corpus.objects.visible_to_user(user).filter(
            pk=instance.corpus.pk
        )
        if visible_corpora.exists():
            logger.debug("Corpus is visible to user - granting read permission")
            final_codenames.add(_get_db_codename_for_action("read", model_name))

    # 3.4) Guardian permissions (user + optional groups)
    logger.debug(
        f"Checking Guardian permissions for app_label: {app_label}, model_name: {model_name}"
    )
    user_perm_codenames = set()

    # user-level perms - try both the generic and model-specific permission classes
    # 1. Standard guardian check
    user_perms = UserObjectPermission.objects.filter(
        object_pk=str(instance.pk),
        user=user,
        content_type__app_label=app_label,
        content_type__model=model_name,
    )
    logger.debug(f"UserObjectPermission permissions: {user_perms}")

    # 2. Check model-specific permission class if standard check returns nothing
    if not user_perms.exists():
        try:
            from django.apps import apps

            # Try to get the model-specific permission class
            permission_class_name = f"{model_name}UserObjectPermission"
            try:
                permission_class = apps.get_model(app_label, permission_class_name)
                logger.debug(
                    f"Checking model-specific permission class: {permission_class}"
                )

                # Check for permissions in the model-specific class
                model_specific_perms = permission_class.objects.filter(
                    user=user,
                    content_object=instance,
                )

                if model_specific_perms.exists():
                    logger.debug(
                        f"Found permissions in model-specific class: {model_specific_perms}"
                    )
                    # Extract the permission codenames
                    for perm in model_specific_perms:
                        user_perm_codenames.add(perm.permission.codename)
                    logger.debug(f"Model-specific permissions: {user_perm_codenames}")
                else:
                    logger.debug("No permissions found in model-specific class")
            except LookupError:
                logger.debug(
                    f"Model-specific permission class {permission_class_name} not found"
                )
        except Exception as e:
            logger.debug(f"Error checking model-specific permissions: {e}")

    # Process the standard guardian permissions
    user_perms = user_perms.values_list("permission__codename", flat=True)
    logger.debug(f"Direct user permissions from Guardian: {list(user_perms)}")
    user_perm_codenames.update(user_perms)

    # group-level perms (optional)
    if include_group_permissions and hasattr(user, "id") and user.id is not None:
        logger.debug("Including group permissions")
        user_groups = user.groups.all()
        logger.debug(f"User groups: {[g.name for g in user_groups]}")

        group_perms = GroupObjectPermission.objects.filter(
            object_pk=str(instance.pk),
            group__in=user_groups,
            content_type__app_label=app_label,
            content_type__model=model_name,
        ).values_list("permission__codename", flat=True)
        logger.debug(f"Group permissions from Guardian: {list(group_perms)}")
        user_perm_codenames.update(group_perms)

    # Add all the guardian perms to our final set
    logger.debug(f"All Guardian permissions: {user_perm_codenames}")
    final_codenames.update(user_perm_codenames)

    logger.debug(f"Final codenames for user {user.username}: {final_codenames}")
    return final_codenames


def assign_permission_directly(user, perm_codename, instance):
    """Create permission object directly rather than using guardian shortcut"""
    from django.apps import apps
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from guardian.models import UserObjectPermission as GuardianUserObjectPermission

    app_label = instance._meta.app_label
    model_name = instance._meta.model_name

    # Get the Permission object
    content_type = ContentType.objects.get_for_model(instance)
    permission = Permission.objects.get(
        content_type=content_type, codename=perm_codename
    )

    # Determine the UserObjectPermission class name
    permission_class_name = f"{model_name}UserObjectPermission"

    # Use Django's app registry instead of importing the module
    try:
        permission_class = apps.get_model(app_label, permission_class_name)
        logger.debug(f"Found specific permission class: {permission_class}")
    except LookupError as e:
        logger.warning(
            f"Could not find permission class {permission_class_name} in {app_label}: {e}"
        )
        logger.warning("Falling back to guardian base UserObjectPermission class")
        permission_class = GuardianUserObjectPermission

    # Create the UserObjectPermission record
    try:
        if permission_class == GuardianUserObjectPermission:
            # If using the base class, we need to set content_type and object_pk manually
            obj_perm, created = permission_class.objects.get_or_create(
                permission=permission,
                user=user,
                content_type=content_type,
                object_pk=str(instance.pk),
            )
        else:
            # Using the model-specific class which has content_object field
            obj_perm, created = permission_class.objects.get_or_create(
                permission=permission, user=user, content_object=instance
            )

        logger.debug(
            f"Direct permission creation: {created}, {permission_class.__name__}"
        )
        return obj_perm, created
    except Exception as e:
        logger.error(f"Error creating permission object: {e}")
        return None, False
