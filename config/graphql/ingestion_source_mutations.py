"""
GraphQL mutations for IngestionSource CRUD operations.
"""

import logging
from typing import Any

import graphene
from django.db import IntegrityError
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.document_types import (
    INGESTION_SOURCE_GLOBAL_ID_TYPE,
    IngestionSourceType,
    IngestionSourceTypeEnum,
)
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


class CreateIngestionSourceMutation(graphene.Mutation):
    """Create a new ingestion source for document lineage tracking."""

    class Arguments:
        name = graphene.String(
            required=True,
            description="Human-readable name (e.g. 'alpha_site_crawler')",
        )
        source_type = IngestionSourceTypeEnum(
            required=False,
            description="Category of source (default: MANUAL)",
        )
        config = GenericScalar(
            required=False,
            description="Connection details, schedule, etc.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    ingestion_source = graphene.Field(IngestionSourceType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(
        _root, info, name, source_type=None, config=None
    ) -> "CreateIngestionSourceMutation":
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
            return CreateIngestionSourceMutation(
                ok=False,
                message=f"An ingestion source named '{name}' already exists",
                ingestion_source=None,
            )

        set_permissions_for_obj_to_user(user, source, [PermissionTypes.CRUD])

        return CreateIngestionSourceMutation(
            ok=True,
            message="Success",
            ingestion_source=source,
        )


class UpdateIngestionSourceMutation(graphene.Mutation):
    """Update an existing ingestion source."""

    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String(required=False)
        source_type = IngestionSourceTypeEnum(required=False)
        config = GenericScalar(required=False)
        active = graphene.Boolean(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    ingestion_source = graphene.Field(IngestionSourceType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(_root, info, id, **kwargs) -> "UpdateIngestionSourceMutation":
        user = info.context.user

        pk, error = _parse_ingestion_source_global_id(id)
        if pk is None:
            return UpdateIngestionSourceMutation(
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
            return UpdateIngestionSourceMutation(
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
                return UpdateIngestionSourceMutation(
                    ok=False,
                    message=f"An ingestion source named '{new_name}' already exists",
                    ingestion_source=None,
                )

        return UpdateIngestionSourceMutation(
            ok=True,
            message="Success",
            ingestion_source=source,
        )


class DeleteIngestionSourceMutation(graphene.Mutation):
    """Delete an ingestion source. Existing DocumentPath references become NULL."""

    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(_root, info, id) -> "DeleteIngestionSourceMutation":
        user = info.context.user

        pk, error = _parse_ingestion_source_global_id(id)
        if pk is None:
            return DeleteIngestionSourceMutation(
                ok=False,
                message=error or _NOT_FOUND_MSG,
            )

        # Intentionally scoped to creator even for superusers — see
        # UpdateIngestionSourceMutation for rationale.
        try:
            source = IngestionSource.objects.get(pk=pk, creator=user)
        except IngestionSource.DoesNotExist:
            return DeleteIngestionSourceMutation(
                ok=False,
                message=_NOT_FOUND_MSG,
            )

        source.delete()
        return DeleteIngestionSourceMutation(ok=True, message="Success")
