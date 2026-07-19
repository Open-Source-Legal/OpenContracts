"""DRF-serializer-backed mutation implementations.

Faithful ports of ``config.graphql.base.DRFMutation.mutate`` and
``config.graphql.base.DRFDeletion.mutate`` operating on strawberry payload
classes. Generated mutation resolvers call these with the values that were
previously declared on the graphene ``IOSettings`` inner class.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Sequence
from typing import Any

from graphql_relay import from_global_id, to_global_id
from rest_framework import serializers

from config.graphql.core.auth import PermissionDenied
from config.ratelimit.decorators import graphql_ratelimit
from config.ratelimit.rates import RateLimits
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


def format_validation_error(ve: serializers.ValidationError) -> str:
    """Port of ``DRFMutation.format_validation_error``."""
    if isinstance(ve.detail, dict):
        errors = "; ".join(
            f"{field}: {', '.join(str(e) for e in errs)}"
            for field, errs in ve.detail.items()
        )
    elif isinstance(ve.detail, list):
        errors = "; ".join(str(e) for e in ve.detail)
    else:
        errors = str(ve.detail)
    return f"Mutation failed due to error: {errors}"


def _require_login(info: Any) -> None:
    if not info.context.user.is_authenticated:
        raise PermissionDenied()


def drf_mutation(
    *,
    payload_cls: type,
    model: type,
    serializer: type,
    type_name: str,
    pk_fields: Sequence[str] = (),
    lookup_field: str = "id",
    root: Any = None,
    info: Any = None,
    kwargs: dict[str, Any],
) -> Any:
    """Port of ``DRFMutation.mutate`` (create/update via DRF serializer)."""
    _require_login(info)
    # ``group="mutate"`` keeps DRF-routed mutations in the SAME fixed-window
    # rate bucket as every hand-ported ``mutate`` resolver. Without it the
    # decorator derives the group from ``func.__name__`` — here a ``lambda``,
    # i.e. ``"<lambda>"`` — splitting these off into a separate counter and
    # roughly doubling a user's combined write budget. Matches the graphene
    # baseline, where all mutations shared the one ``"mutate"`` group.
    _ratelimited = graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM, group="mutate")(
        lambda _root, _info, **kw: _drf_mutation_body(
            payload_cls=payload_cls,
            model=model,
            serializer=serializer,
            type_name=type_name,
            pk_fields=pk_fields,
            lookup_field=lookup_field,
            info=_info,
            kwargs=kw,
        )
    )
    return _ratelimited(root, info, **kwargs)


def _drf_mutation_body(
    *,
    payload_cls: type,
    model: type,
    serializer: type,
    type_name: str,
    pk_fields: Sequence[str],
    lookup_field: str,
    info: Any,
    kwargs: dict[str, Any],
) -> Any:
    ok = False
    obj_id = None

    try:
        if info.context.user:
            kwargs["creator"] = info.context.user.id
        else:
            raise ValueError("No user in this request...")

        for pk_field in pk_fields:
            if pk_field in kwargs:
                raw_value = kwargs[pk_field]
                if isinstance(raw_value, list):
                    kwargs[pk_field] = [
                        from_global_id(global_id)[1] for global_id in raw_value
                    ]
                else:
                    kwargs[pk_field] = from_global_id(raw_value)[1]

        is_update = lookup_field in kwargs

        if is_update:
            lookup_pk = from_global_id(kwargs[lookup_field])[1]
            obj = BaseService.get_or_none(
                model, lookup_pk, info.context.user, request=info.context
            )
            if obj is None:
                raise model.DoesNotExist(  # type: ignore[attr-defined]
                    f"{model.__name__} matching query does not exist."
                )

            if hasattr(obj, "user_lock") and obj.user_lock is not None:
                if info.context.user.id != obj.user_lock_id:
                    raise PermissionError(
                        "Specified object is locked by another user. Cannot be "
                        "updated / edited."
                    )

            if hasattr(obj, "backend_lock") and obj.backend_lock:
                raise PermissionError(
                    "This object has been locked by the backend for processing. "
                    "You cannot edit it at the moment."
                )

            permission_error = BaseService.require_permission(
                obj,
                info.context.user,
                PermissionTypes.UPDATE,
                request=info.context,
                error_message="You do not have permission to modify this object",
            )
            if permission_error:
                raise PermissionError(permission_error)

            obj_serializer = serializer(obj, data=kwargs, partial=True)
            obj_serializer.is_valid(raise_exception=True)
            obj_serializer.save()
            ok = True
            message = "Success"
            obj_id = to_global_id(type_name, obj.id)

        else:
            obj_serializer = serializer(data=kwargs)
            obj_serializer.is_valid(raise_exception=True)
            obj = obj_serializer.save()

            set_permissions_for_obj_to_user(
                info.context.user,
                obj,
                [PermissionTypes.CRUD],
                is_new=True,
                request=info.context,
            )

            ok = True
            message = "Success"
            obj_id = to_global_id(type_name, obj.id)

    except serializers.ValidationError as ve:
        logger.warning(f"Validation error in mutation: {ve.detail}")
        message = format_validation_error(ve)

    except Exception:
        logger.error(traceback.format_exc())
        message = "Mutation failed due to an internal error."

    return payload_cls(ok=ok, message=message, obj_id=obj_id)


def drf_deletion(
    *,
    payload_cls: type,
    model: type,
    lookup_field: str = "id",
    root: Any = None,
    info: Any = None,
    kwargs: dict[str, Any],
) -> Any:
    """Port of ``DRFDeletion.mutate`` — errors intentionally propagate raw."""
    _require_login(info)
    # See ``drf_mutation``: pin the shared ``"mutate"`` rate bucket rather than
    # inheriting the lambda's ``"<lambda>"`` group.
    _ratelimited = graphql_ratelimit(rate=RateLimits.WRITE_LIGHT, group="mutate")(
        lambda _root, _info, **kw: _drf_deletion_body(
            payload_cls=payload_cls,
            model=model,
            lookup_field=lookup_field,
            info=_info,
            kwargs=kw,
        )
    )
    return _ratelimited(root, info, **kwargs)


def _drf_deletion_body(
    *,
    payload_cls: type,
    model: type,
    lookup_field: str,
    info: Any,
    kwargs: dict[str, Any],
) -> Any:
    lookup_value = kwargs.get(lookup_field)
    if lookup_value is None:
        raise ValueError(
            f"'{lookup_field}' is required to identify the object to delete."
        )
    pk = from_global_id(lookup_value)[1]
    obj = BaseService.get_or_none(model, pk, info.context.user, request=info.context)
    if obj is None:
        raise model.DoesNotExist(  # type: ignore[attr-defined]
            f"{model.__name__} matching query does not exist."
        )

    if hasattr(obj, "user_lock") and obj.user_lock is not None:
        if info.context.user.id != obj.user_lock_id:
            raise PermissionError(
                "Specified object is locked by another user. Cannot be " "deleted."
            )

    permission_error = BaseService.require_permission(
        obj,
        info.context.user,
        PermissionTypes.DELETE,
        request=info.context,
        error_message=(
            "You do not have sufficient permissions to delete requested object"
        ),
    )
    if permission_error:
        raise PermissionError(permission_error)

    obj.delete()
    return payload_cls(ok=True, message="Success!")
