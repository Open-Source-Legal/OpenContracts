import logging
from typing import TYPE_CHECKING, Any, cast

import graphene
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Model
from graphene.types.generic import GenericScalar

from config.graphql.permissioning.permission_annotator.middleware import (
    get_permissions_for_user_on_model_in_app,
)
from opencontractserver.shared.prefetch_attrs import (
    user_group_perm_attr,
    user_perm_attr,
)

User = get_user_model()

logger = logging.getLogger(__name__)


class AnnotatePermissionsForReadMixin:
    """Adds ``my_permissions``, ``is_published``, and ``object_shared_with``
    fields to GraphQL types for Django models that carry guardian permission
    tables.

    The mixin is always combined with a ``DjangoObjectType`` whose ``_meta.model``
    is a Django ``Model`` subclass — so ``self._meta``, ``self.is_public``, and
    the related ``*userobjectpermission_set`` / ``*groupobjectpermission_set``
    accessors exist at runtime. The ``TYPE_CHECKING`` block below tells mypy
    about that contract without affecting runtime behaviour.
    """

    if TYPE_CHECKING:
        # Provided by the Django model the GraphQL type wraps.
        _meta: Any
        is_public: bool

    my_permissions = GenericScalar()
    is_published = graphene.Boolean()
    object_shared_with = GenericScalar()

    def resolve_object_shared_with(self, info) -> list[dict[str, Any]]:

        logger.info(f"resolve_shared_with - self: {self} / type: {type(self)}")
        logger.info(f"resolve_shared_with - info: {info} / type: {type(info)}")
        logger.info(
            f"resolve_shared_with - info context permissions: {info.context.permission_annotations}"
        )

        values: list[dict[str, Any]] = []
        # ``get_anonymous`` is added to the User model by django-guardian's
        # ``GuardianUserMixin``; not visible to mypy without guardian stubs.
        anon = User.get_anonymous()  # type: ignore[attr-defined]
        context = info.context

        if context and hasattr(context, "user"):
            user = context.user
            if user.id == anon.id:
                return []

        try:

            permission_annotations = context.permission_annotations
            this_model_permission_id_map = permission_annotations.get(
                "this_model_permission_id_map", {}
            )
            user_permission_map: dict[int, dict[str, Any]] = {}
            model_name = self._meta.model_name
            this_user_perms = getattr(self, f"{model_name}userobjectpermission_set")

            # ``select_related("user")`` collapses what was an N+1 across
            # ``perm.user.slug`` for shared corpuses with many collaborators
            # into a single JOIN — only the slug is read per user, never PII.
            for perm in this_user_perms.select_related("user").all():

                logger.info(f"perm: {perm}")

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
                    # Only the case-sensitive ``slug`` is exposed for the
                    # users an object is shared with — never ``email`` or
                    # ``username``. The slug is the public handle; emitting
                    # email here previously leaked PII to every viewer of
                    # any shared corpus / document / labelset.
                    user_permission_map[perm.user_id] = {
                        "id": perm.user_id,
                        "slug": perm.user.slug,
                        "permissions": seed_permission,
                    }

            for value in user_permission_map.values():
                logger.info(f"Value in user_permission_map.values(): {value}")
                values.append(
                    {
                        "id": value["id"],
                        "slug": value["slug"],
                        "permissions": list(value["permissions"].values()),
                    }
                )

        except AttributeError as ae:
            logger.error(f"resolve_shared_with - Attribute Error: {ae}")
            pass

        logger.info(f"Values: {values}")

        return values

    def resolve_my_permissions(self, info) -> list[str]:

        # logger.info(f"resolve_my_permissions() - Start")
        # ``get_anonymous`` is added to the User model by django-guardian's
        # ``GuardianUserMixin``; not visible to mypy without guardian stubs.
        anon = User.get_anonymous()  # type: ignore[attr-defined]
        # logger.info(f"resolve_my_permissions() - anon: {anon}")
        context = info.context
        # logger.info(f"resolve_my_permissions() - context: {context}")
        user = None

        if context and hasattr(context, "user"):
            # logger.info(f"resolve_my_permissions() - context has attribute user")
            user = context.user
            # logger.info(f"resolve_my_permissions() - user is: {user}")
            if user.id == anon.id:
                # logger.info(f"resolve_my_permissions() - user is anon user")
                return []

        # Check if permissions were pre-computed by query optimizer
        # These are annotated as _can_read, _can_create, _can_update, _can_delete
        # Applies to Annotation, Relationship, and DocumentRelationship models
        # (DocumentRelationship has no guardian tables — permissions are inherited
        # from source/target documents + corpus and pre-computed by the optimizer)
        model_name = self._meta.model_name

        if model_name in [
            "annotation",
            "relationship",
            "documentrelationship",
        ] and hasattr(self, "_can_read"):
            # logger.info("resolve_my_permissions() - Using pre-computed permissions from query optimizer")
            permissions = set()

            # Map the boolean flags to backend permission format
            if getattr(self, "_can_read", False):
                permissions.add(f"read_{model_name}")
            if getattr(self, "_can_create", False):
                permissions.add(f"create_{model_name}")
            if getattr(self, "_can_update", False):
                permissions.add(f"update_{model_name}")
            if getattr(self, "_can_delete", False):
                permissions.add(f"remove_{model_name}")
            if getattr(self, "_can_comment", False):
                permissions.add(f"comment_{model_name}")

            # Check for publish permission if available
            if getattr(self, "_can_publish", False):
                permissions.add(f"publish_{model_name}")

            return list(permissions)

        # Looking up permissions in each resolve call is wasteful and slow. A lot of times,
        # where we're getting the permissions on a list of the same object types, we can look up
        # these permissions types ahead of time and then just check the permissions' metadata in these
        # objs loaded into memory. This is done in the middleware... we check for the DjangoModelType model
        # being requested and add to the context the types of permissions applicable to it.
        # NOTE - this falls down in GraphQL (as opposed to a similar approach I used with REST) where you
        # start to request nested objs WITH permissions (as we do in old OpenContractsServer in some cases).
        # for now, my solution to this is to fall back to lookup obj-level permissions in this mixin where
        # the context preloaded_model_types does not include {app_name}.{model_name}.
        #
        # There is certainly a way to try to preload these lookups in the middleware and create a more
        # complex context lookup datastructure to check for preloaded permissions for each model. I don't
        # really have the time or inclination to do this at the moment.
        permission_annotations = (
            context.permission_annotations
            if hasattr(context, "permission_annotations")
            else {}
        )

        model_name = self._meta.model_name
        app_label = self._meta.app_label
        full_name = f"{app_label}.{model_name}"

        permissions = set()

        if self.is_public:
            permissions.add(f"read_{model_name}")

        # logger.info(
        #     f"resolve_my_permissions() - permission_annotations: {permission_annotations}"
        # )

        try:

            # logger.info("resolve_my_permissions() - Proceed to analyze obj-level permissions")
            # If we managed to find the user obj... return its permissions to given obj... otherwise return empty array
            if user:

                try:

                    # logger.info(f"resolve_my_permissions() - _meta: {dir(self._meta)}")
                    # logger.info(f"resolve_my_permissions() - Full name: {full_name}")

                    # Superuser won't have explicit rights in the permission object set YET
                    # superusers have ALL permissions available in django. If user is making
                    # request, annotate all permissions for user
                    if user.is_superuser:
                        # logger.info(
                        #     "resolve_my_permissions() - permissions values "
                        #     f":{permission_annotations[full_name]['this_model_permission_id_map'].values()}"
                        # )
                        permissions.add("superuser")

                        if (
                            full_name in permission_annotations
                            and "this_model_permission_id_map"
                            in permission_annotations[full_name]
                        ):
                            # logger.info(f"resolve_my_permissions() - Fold in permission_annotations...")
                            permissions = permissions.union(
                                {
                                    v
                                    for v in list(
                                        permission_annotations[full_name][
                                            "this_model_permission_id_map"
                                        ].values()
                                    )
                                }
                            )
                        # logger.info(
                        #     f"resolve_my_permissions() - permissions: {permissions}"
                        # )

                    else:

                        # logger.info(
                        #     "resolve_my_permissions() - user is not super user."
                        # )

                        if full_name not in permission_annotations:
                            # logger.warning(
                            #     f"resolve_my_permissions() - trying to annotate but {full_name} "
                            #     f"not in permission map... manually query"
                            # )

                            # Manual lookup here from database
                            model_permissions = (
                                get_permissions_for_user_on_model_in_app(
                                    app_label, model_name, info.context.user
                                )
                            )

                        else:
                            # logger.info(
                            #     f"resolve_my_permissions() - {full_name} is in permission_annoations"
                            # )
                            model_permissions = permission_annotations[full_name]

                        # logger.info(
                        #     f"resolve_my_permissions() - model_name: {model_name}"
                        # )
                        # logger.info(
                        #     f"resolve_my_permissions() - model permissions: {model_permissions}"
                        # )

                        # GET PERMISSION IDS FOR MODEL ####
                        this_user_group_ids = model_permissions.get(
                            "this_user_group_ids", []
                        )
                        # logger.info(
                        #     f"resolve_my_permissions() - this_user_group_ids: {this_user_group_ids}"
                        # )

                        this_model_permission_id_map = model_permissions.get(
                            "this_model_permission_id_map", {}
                        )
                        # logger.info(
                        #     f"resolve_my_permissions() - this_model_permission_id_map:"
                        #     f"{this_model_permission_id_map}"
                        # )

                        can_publish_model_type = model_permissions.get(
                            "can_publish_model_type", False
                        )
                        # logger.info(
                        #     f"resolve_my_permissions() - can_publish_model_type:"
                        #     f"{can_publish_model_type}"
                        # )
                        #####################################################################

                        # Prefer per-user prefetch (set by _apply_document_prefetches);
                        # ``.filter()`` on the related manager bypasses the cache.
                        prefetched_user_perms_attr = user_perm_attr(user.id)
                        if hasattr(self, prefetched_user_perms_attr):
                            this_user_perms = getattr(self, prefetched_user_perms_attr)
                        else:
                            this_user_perms = getattr(
                                self, f"{model_name}userobjectpermission_set"
                            ).filter(user_id=user.id)

                        prefetched_group_perms_attr = user_group_perm_attr(user.id)
                        if hasattr(self, prefetched_group_perms_attr):
                            this_users_group_perms = getattr(
                                self, prefetched_group_perms_attr
                            )
                        else:
                            this_users_group_perms = getattr(
                                self, f"{model_name}groupobjectpermission_set"
                            ).filter(group_id__in=this_user_group_ids)
                        # logger.info(
                        #     f"resolve_my_permissions() - this_users_group_perms:"
                        #     f"{this_users_group_perms}"
                        # )

                        # logger.info(
                        #     "resolve_my_permissions() - Analyze this_user_perms"
                        # )
                        for perm in this_user_perms:
                            # logger.info(f"resolve_my_permissions() - Analyze: {perm}")
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
                                    f"resolve_my_permissions() - Error trying to add this_users_group_perms "
                                    f"to model_permission_id_map: {e}"
                                )

                        if can_publish_model_type:
                            try:
                                permissions.add(f"publish_{model_name}")
                            except Exception:
                                pass

                    # logger.info(f"resolve_my_permissions() - final permission list: {permission_list}")

                except Exception as e:
                    logger.error(
                        f"resolve_my_permissions() - Error getting my_permissions: {e}"
                    )

        except Exception as e:
            logger.error(
                f"resolve_my_permissions() - unexpected failure in outer try/except: {e}"
            )

        # Return permissions in backend format (read_annotation, update_annotation, etc.)
        return list(permissions)

    def resolve_is_published(self, obj) -> bool:

        from guardian.shortcuts import get_groups_with_perms

        # ``self`` is always a Django Model instance at runtime (the mixin is
        # combined with a ``DjangoObjectType``). ``get_groups_with_perms`` is
        # typed in django-guardian-stubs to return ``Group | dict``, but with
        # ``attach_perms=False`` (the default) it always returns a queryset
        # of ``Group``s.
        groups = cast(
            "Any",
            get_groups_with_perms(cast(Model, self), attach_perms=False),
        )
        return groups.filter(name=settings.DEFAULT_PERMISSIONS_GROUP).count() == 1
