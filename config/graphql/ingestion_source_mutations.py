"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
from typing import Annotated, Any

import strawberry
from django.db import IntegrityError
from graphql_relay import from_global_id

from config.graphql import enums
from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.document_types import INGESTION_SOURCE_GLOBAL_ID_TYPE
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.documents.models import (
    IngestionSource,
    IngestionSourceCategory,
)
from opencontractserver.utils.permissioning import (
    PermissionTypes,
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)
_NOT_FOUND_MSG = "Ingestion source not found"


def _parse_ingestion_source_global_id(
    global_id: str,
) -> tuple[str | None, str | None]:
    """Parse and validate a global ID for IngestionSource.

    Returns (pk, None) on success or (None, error_message) on failure.
    """
    try:
        type_name, pk = from_global_id(global_id)
    except (ValueError, TypeError):
        return None, _NOT_FOUND_MSG
    if type_name != INGESTION_SOURCE_GLOBAL_ID_TYPE:
        return None, _NOT_FOUND_MSG
    return pk, None


def _resolve_source_type(source_type) -> Any:
    """Coerce a graphene Enum to its string value, defaulting to MANUAL."""
    if source_type is None:
        return IngestionSourceCategory.MANUAL
    return source_type.value if hasattr(source_type, "value") else source_type


@strawberry.type(
    name="CreateIngestionSourceMutation",
    description="Create a new ingestion source for document lineage tracking.",
)
class CreateIngestionSourceMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    ingestion_source: None | (
        Annotated[IngestionSourceType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="ingestionSource", default=None)


register_type(
    "CreateIngestionSourceMutation", CreateIngestionSourceMutation, model=None
)


@strawberry.type(
    name="UpdateIngestionSourceMutation",
    description="Update an existing ingestion source.",
)
class UpdateIngestionSourceMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    ingestion_source: None | (
        Annotated[IngestionSourceType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="ingestionSource", default=None)


register_type(
    "UpdateIngestionSourceMutation", UpdateIngestionSourceMutation, model=None
)


@strawberry.type(
    name="DeleteIngestionSourceMutation",
    description="Delete an ingestion source. Existing DocumentPath references become NULL.",
)
class DeleteIngestionSourceMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type(
    "DeleteIngestionSourceMutation", DeleteIngestionSourceMutation, model=None
)


def _mutate_CreateIngestionSourceMutation(
    payload_cls, root, info, name, source_type=None, config=None
):
    """Port of CreateIngestionSourceMutation.mutate"""
    # @login_required — inlined (stub's payload_cls first arg does not match
    # the decorator's (root, info, ...) convention).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, name, source_type=None, config=None):
        user = info.context.user

        resolved_type = _resolve_source_type(source_type)

        # Use try/except around create() instead of exists() + create()
        # to avoid TOCTOU race condition with the unique constraint.
        try:
            source = IngestionSource.objects.create(
                name=name,
                source_type=resolved_type,
                config=config or {},
                creator=user,
            )
        except IntegrityError as exc:
            logger.debug("IntegrityError on create, falling back to error: %s", exc)
            return payload_cls(
                ok=False,
                message=f"An ingestion source named '{name}' already exists",
                ingestion_source=None,
            )

        set_permissions_for_obj_to_user(
            user, source, [PermissionTypes.CRUD], is_new=True, request=info.context
        )

        return payload_cls(
            ok=True,
            message="Success",
            ingestion_source=source,
        )

    return mutate(root, info, name, source_type=source_type, config=config)


def m_create_ingestion_source(
    info: strawberry.Info,
    config: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="config", description="Connection details, schedule, etc."
        ),
    ] = strawberry.UNSET,
    name: Annotated[
        str,
        strawberry.argument(
            name="name", description="Human-readable name (e.g. 'alpha_site_crawler')"
        ),
    ] = strawberry.UNSET,
    source_type: Annotated[
        enums.IngestionSourceTypeEnum | None,
        strawberry.argument(
            name="sourceType", description="Category of source (default: MANUAL)"
        ),
    ] = strawberry.UNSET,
) -> CreateIngestionSourceMutation | None:
    kwargs = strip_unset({"config": config, "name": name, "source_type": source_type})
    return _mutate_CreateIngestionSourceMutation(
        CreateIngestionSourceMutation, None, info, **kwargs
    )


def _mutate_UpdateIngestionSourceMutation(payload_cls, root, info, id, **kwargs):
    """Port of UpdateIngestionSourceMutation.mutate"""
    # @login_required — inlined (stub's payload_cls first arg does not match
    # the decorator's (root, info, ...) convention).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, id, **kwargs):
        user = info.context.user

        pk, error = _parse_ingestion_source_global_id(id)
        if pk is None:
            return payload_cls(
                ok=False,
                message=error or _NOT_FOUND_MSG,
                ingestion_source=None,
            )

        # Intentionally scoped to creator even for superusers: ingestion
        # sources may hold credential references, so admin cross-user
        # management is out of scope.
        try:
            source = IngestionSource.objects.get(pk=pk, creator=user)
        except IngestionSource.DoesNotExist:
            return payload_cls(
                ok=False,
                message=_NOT_FOUND_MSG,
                ingestion_source=None,
            )

        if "source_type" in kwargs and kwargs["source_type"] is not None:
            kwargs["source_type"] = _resolve_source_type(kwargs["source_type"])

        # Note: the `is not None` guard prevents nulling JSON fields like
        # `config` (to clear it, pass config={} instead).  Boolean fields
        # like `active` are unaffected because `False is not None` is True.
        update_fields = []
        for field in ("name", "source_type", "config", "active"):
            if field in kwargs and kwargs[field] is not None:
                setattr(source, field, kwargs[field])
                update_fields.append(field)

        if update_fields:
            # Use try/except around save() instead of a pre-flight exists()
            # check to avoid TOCTOU race on the unique (creator, name)
            # constraint — consistent with CreateIngestionSourceMutation.
            try:
                source.save(update_fields=update_fields)
            except IntegrityError as exc:
                logger.debug("IntegrityError on update, name conflict: %s", exc)
                new_name = kwargs.get("name", source.name)
                return payload_cls(
                    ok=False,
                    message=f"An ingestion source named '{new_name}' already exists",
                    ingestion_source=None,
                )

        return payload_cls(
            ok=True,
            message="Success",
            ingestion_source=source,
        )

    return mutate(root, info, id, **kwargs)


def m_update_ingestion_source(
    info: strawberry.Info,
    active: Annotated[
        bool | None, strawberry.argument(name="active")
    ] = strawberry.UNSET,
    config: Annotated[
        GenericScalar | None, strawberry.argument(name="config")
    ] = strawberry.UNSET,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    source_type: Annotated[
        enums.IngestionSourceTypeEnum | None, strawberry.argument(name="sourceType")
    ] = strawberry.UNSET,
) -> UpdateIngestionSourceMutation | None:
    kwargs = strip_unset(
        {
            "active": active,
            "config": config,
            "id": id,
            "name": name,
            "source_type": source_type,
        }
    )
    return _mutate_UpdateIngestionSourceMutation(
        UpdateIngestionSourceMutation, None, info, **kwargs
    )


def _mutate_DeleteIngestionSourceMutation(payload_cls, root, info, id):
    """Port of DeleteIngestionSourceMutation.mutate"""
    # @login_required — inlined (stub's payload_cls first arg does not match
    # the decorator's (root, info, ...) convention).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id):
        user = info.context.user

        pk, error = _parse_ingestion_source_global_id(id)
        if pk is None:
            return payload_cls(
                ok=False,
                message=error or _NOT_FOUND_MSG,
            )

        # Intentionally scoped to creator even for superusers — see
        # UpdateIngestionSourceMutation for rationale.
        try:
            source = IngestionSource.objects.get(pk=pk, creator=user)
        except IngestionSource.DoesNotExist:
            return payload_cls(
                ok=False,
                message=_NOT_FOUND_MSG,
            )

        source.delete()
        return payload_cls(ok=True, message="Success")

    return mutate(root, info, id)


def m_delete_ingestion_source(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteIngestionSourceMutation | None:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteIngestionSourceMutation(
        DeleteIngestionSourceMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_ingestion_source": strawberry.field(
        resolver=m_create_ingestion_source,
        name="createIngestionSource",
        description="Create a new ingestion source for document lineage tracking.",
    ),
    "update_ingestion_source": strawberry.field(
        resolver=m_update_ingestion_source,
        name="updateIngestionSource",
        description="Update an existing ingestion source.",
    ),
    "delete_ingestion_source": strawberry.field(
        resolver=m_delete_ingestion_source,
        name="deleteIngestionSource",
        description="Delete an ingestion source. Existing DocumentPath references become NULL.",
    ),
}
