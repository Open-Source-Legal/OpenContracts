from __future__ import annotations

import logging
from functools import reduce
from typing import Any, Callable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)

User = get_user_model()


def combine(a: dict[Any, Any], b: tuple[Any, Any] | Any) -> dict[Any, Any]:
    c = {**a}
    if isinstance(b, tuple):
        c[b[0]] = b[1]
    return c


# Used to annotate nodes
def get_permissions_for_user_on_model_in_app(
    app_name: str, model_name: str, user: AbstractUser | None
) -> dict[str, Any]:
    # logger.info(
    #     f"get_permissions_for_user_on_model_in_app() - start for app_name {app_name} and model_name {model_name}")

    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    this_model_permission_id_map: dict[int, str] = {}
    this_user_group_ids: list[int] = []
    permissions_annotated_for_models: list[str] = []
    can_publish = False

    try:

        if user:

            # logger.info(f"get_user_model_permissions_from_info_and_model - user exists.")

            model_permissions = user.get_all_permissions()
            # logger.info(f"get_user_model_permissions_from_info_and_model - model_permissions: {model_permissions}")

            if f"{app_name}.publish_{model_name}" in model_permissions:
                # logger.info("Can publish")
                can_publish = True

            model_type = ContentType.objects.get(app_label=app_name, model=model_name)

            this_user_group_ids = list(user.groups.all().values_list("id", flat=True))
            # logger.info(f"get_user_model_permissions_from_info_and_model() - "
            #             f"this_user_group_ids: {this_user_group_ids}")

            # perms_objs = Permission.objects.filter(content_type_id=model_type.id)
            # logger.info(f"get_user_model_permissions_from_info_and_model - perms_objs: {perms_objs}")

            this_model_permission_objs = list(
                Permission.objects.filter(content_type_id=model_type.id).values_list(
                    "id", "codename"
                )
            )
            # logger.info(f"get_user_model_permissions_from_info_and_model - "
            #             f"this_model_permission_objs: {this_model_permission_objs}")

            this_model_permission_id_map = reduce(
                combine, this_model_permission_objs, {}
            )
            # logger.info(f"get_user_model_permissions_from_info_and_model - "
            #             f"this_model_permission_id_map: {this_model_permission_id_map}")

    except Exception as e:
        logger.error(
            f"Error getting object-level permissions based on {user} and with "
            f"app_name {app_name} and model_name {model_name}: {e}"
        )

    return {
        "permissions_annotated_for_models": permissions_annotated_for_models,
        "this_user_group_ids": this_user_group_ids,
        "this_model_permission_id_map": this_model_permission_id_map,
        "can_publish": can_publish,
    }


class PermissionAnnotatingMiddleware:
    def __init__(self) -> None:
        pass

    def resolve(
        self, next: Callable[..., Any], root: Any, info: Any, **kwargs: Any
    ) -> Any:

        # logger.info(f"PermissionAnnotatingMiddleware - resolve(): {root}")
        # logger.info(f"PermissionAnnotatingMiddleware - return_type:
        # {info.return_type} (type: {type(info.return_type)}")

        model_django_type = None

        try:
            if hasattr(info.return_type, "graphene_type"):
                graphene_type = info.return_type.graphene_type
                # logger.info(f"PermissionAnnotatingMiddleware - graphene_type: {graphene_type}")
                meta = graphene_type._meta
                # logger.info(f"PermissionAnnotatingMiddleware - graphene_type _meta: {meta}")

                # logger.info(f"PermissionAnnotatingMiddleware - graphene_type has node: {hasattr(meta, 'node')}")
                if hasattr(meta, "node"):
                    # logger.info(f"PermissionAnnotatingMiddleware - This is a node in a relay resolver")
                    model_django_type = meta.node._meta.model
                else:
                    # logger.info(
                    #     f"PermissionAnnotatingMiddleware - Not a node resolver...
                    #     try to see if it's a DjangoModelType")
                    if hasattr(meta, "model"):
                        # logger.info("PermissionAnnotatingMiddleware - It IS a DjangoModelType")
                        model_django_type = meta.model

        except Exception as e:
            logger.warning(
                f"PermissionAnnotatingMiddleware - could not determine the graphene_type due to error: {e}. Happens "
                f"sometimes, though still haven't quite figured out a fix."
            )

        try:

            if model_django_type is not None:

                model_name = model_django_type._meta.model_name

                if model_name in ["annotation", "relationship"]:
                    # Don't annotate annotation and relationship
                    pass

                app_name = model_django_type._meta.app_label
                full_name = f"{app_name}.{model_name}"
                # logger.info(f"PermissionAnnotatingMiddleware - full model name: {full_name}")

                if hasattr(info.context, "permission_annotations"):
                    # logger.info(
                    #     f"PermissionAnnotatingMiddleware - info.context has permission_annotations:
                    #     {info.context.permission_annotations}")
                    if full_name in info.context.permission_annotations:
                        pass
                    else:
                        info.context.permission_annotations[full_name] = (
                            get_permissions_for_user_on_model_in_app(
                                app_name, model_name, info.context.user
                            )
                        )
                else:
                    info.context.permission_annotations = {
                        full_name: get_permissions_for_user_on_model_in_app(
                            app_name, model_name, info.context.user
                        )
                    }
                # logger.info(f"Context permission_annotations: {info.context.permission_annotations}")

        except Exception as e:
            logger.warning(f"Unable to annotate with permissions due to error: {e}")

        return next(root, info, **kwargs)
