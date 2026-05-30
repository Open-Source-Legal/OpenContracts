"""
GraphQL mutations for managing :class:`CorpusCategory` records.

Corpus categories (e.g. "Case Law", "Contracts", "Legislation") are the
runtime-configurable tag set used to organise corpuses on the Discover page
and in corpus settings. They are global, admin-provisioned data with no
per-object guardian permissions, so every mutation here is gated to
superusers only — mirroring the pipeline-settings mutations.

These mutations let a superuser create / update / delete categories at
runtime (via the in-app admin UI or GraphiQL) instead of editing a seed
migration or the Django admin.
"""

import logging
import re
from typing import Optional

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.corpus_types import CorpusCategoryType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.corpuses.models import CorpusCategory

logger = logging.getLogger(__name__)

# Validation constants. Kept in sync with the field definitions on
# ``CorpusCategory`` (opencontractserver/corpuses/models.py).
MAX_CATEGORY_NAME_LENGTH = 255
MAX_CATEGORY_ICON_LENGTH = 100
# Hex color in the form ``#RRGGBB`` — matches the ``color`` field width (7).
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Default appearance values, mirroring the model field defaults so create
# mutations that omit ``icon`` / ``color`` land on the same look as a direct
# ORM create.
DEFAULT_CATEGORY_ICON = "folder"
DEFAULT_CATEGORY_COLOR = "#3B82F6"

# Shared not-authorized message so callers can't distinguish "doesn't exist"
# from "not permitted" beyond the superuser gate.
NOT_SUPERUSER_MESSAGE = "Only superusers can manage corpus categories."


def _validate_category_fields(
    *,
    name: Optional[str] = None,
    icon: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[str]:
    """Validate the user-supplied category fields.

    Returns an error message string if any field is invalid, else ``None``.
    Only validates the fields that are actually provided (non-``None``) so it
    works for both create (all fields) and partial update.
    """
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            return "Category name cannot be empty."
        if len(cleaned) > MAX_CATEGORY_NAME_LENGTH:
            return (
                f"Category name exceeds maximum length of "
                f"{MAX_CATEGORY_NAME_LENGTH} characters."
            )
    if icon is not None and len(icon) > MAX_CATEGORY_ICON_LENGTH:
        return (
            f"Icon name exceeds maximum length of "
            f"{MAX_CATEGORY_ICON_LENGTH} characters."
        )
    if color is not None and not HEX_COLOR_PATTERN.match(color):
        return f"Invalid color '{color}'. Expected a hex value like '#3B82F6'."
    return None


class CreateCorpusCategory(graphene.Mutation):
    """Create a new corpus category. Superuser-only."""

    class Arguments:
        name = graphene.String(required=True, description="Unique category name")
        description = graphene.String(
            required=False, description="Optional human-readable description"
        )
        icon = graphene.String(
            required=False,
            description="Lucide icon name (e.g. 'scroll', 'gavel'). Defaults to 'folder'.",
        )
        color = graphene.String(
            required=False,
            description="Hex color for the badge (e.g. '#3B82F6'). Defaults to blue.",
        )
        sort_order = graphene.Int(
            required=False, description="Display order; lower sorts first"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusCategoryType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        name,
        description=None,
        icon=None,
        color=None,
        sort_order=None,
    ) -> "CreateCorpusCategory":
        user = info.context.user

        if not user.is_superuser:
            return CreateCorpusCategory(
                ok=False, message=NOT_SUPERUSER_MESSAGE, obj=None
            )

        validation_error = _validate_category_fields(name=name, icon=icon, color=color)
        if validation_error:
            return CreateCorpusCategory(ok=False, message=validation_error, obj=None)

        cleaned_name = name.strip()
        if CorpusCategory.objects.filter(name=cleaned_name).exists():
            return CreateCorpusCategory(
                ok=False,
                message=f"A category named '{cleaned_name}' already exists.",
                obj=None,
            )

        category = CorpusCategory.objects.create(
            name=cleaned_name,
            description=(description or "").strip(),
            icon=icon or DEFAULT_CATEGORY_ICON,
            color=color or DEFAULT_CATEGORY_COLOR,
            sort_order=sort_order if sort_order is not None else 0,
            creator=user,
            # Categories are globally visible structural data.
            is_public=True,
        )
        logger.info(
            "Superuser %s created corpus category %s (%s)",
            user.id,
            category.id,
            category.name,
        )
        return CreateCorpusCategory(ok=True, message="Success", obj=category)


class UpdateCorpusCategory(graphene.Mutation):
    """Update an existing corpus category. Superuser-only."""

    class Arguments:
        id = graphene.ID(required=True, description="Global ID of the category")
        name = graphene.String(required=False)
        description = graphene.String(required=False)
        icon = graphene.String(required=False)
        color = graphene.String(required=False)
        sort_order = graphene.Int(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusCategoryType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        id,
        name=None,
        description=None,
        icon=None,
        color=None,
        sort_order=None,
    ) -> "UpdateCorpusCategory":
        user = info.context.user

        if not user.is_superuser:
            return UpdateCorpusCategory(
                ok=False, message=NOT_SUPERUSER_MESSAGE, obj=None
            )

        not_found_msg = "Category not found."
        try:
            category_pk = from_global_id(id)[1]
        except Exception:
            return UpdateCorpusCategory(ok=False, message=not_found_msg, obj=None)

        category = CorpusCategory.objects.filter(pk=category_pk).first()
        if category is None:
            return UpdateCorpusCategory(ok=False, message=not_found_msg, obj=None)

        validation_error = _validate_category_fields(name=name, icon=icon, color=color)
        if validation_error:
            return UpdateCorpusCategory(ok=False, message=validation_error, obj=None)

        update_fields = ["modified"]

        if name is not None:
            cleaned_name = name.strip()
            # Enforce the unique-name constraint with a friendly message
            # rather than letting the IntegrityError bubble up.
            if (
                CorpusCategory.objects.filter(name=cleaned_name)
                .exclude(pk=category.pk)
                .exists()
            ):
                return UpdateCorpusCategory(
                    ok=False,
                    message=f"A category named '{cleaned_name}' already exists.",
                    obj=None,
                )
            category.name = cleaned_name
            update_fields.append("name")
        if description is not None:
            category.description = description.strip()
            update_fields.append("description")
        if icon is not None:
            category.icon = icon
            update_fields.append("icon")
        if color is not None:
            category.color = color
            update_fields.append("color")
        if sort_order is not None:
            category.sort_order = sort_order
            update_fields.append("sort_order")

        category.save(update_fields=update_fields)
        logger.info(
            "Superuser %s updated corpus category %s (%s)",
            user.id,
            category.id,
            category.name,
        )
        return UpdateCorpusCategory(ok=True, message="Success", obj=category)


class DeleteCorpusCategory(graphene.Mutation):
    """Delete a corpus category. Superuser-only.

    Deleting a category removes it from every corpus that referenced it (the
    ``Corpus.categories`` M2M through-rows are cleaned up automatically) but
    does not affect the corpuses themselves.
    """

    class Arguments:
        id = graphene.ID(required=True, description="Global ID of the category")

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id) -> "DeleteCorpusCategory":
        user = info.context.user

        if not user.is_superuser:
            return DeleteCorpusCategory(ok=False, message=NOT_SUPERUSER_MESSAGE)

        not_found_msg = "Category not found."
        try:
            category_pk = from_global_id(id)[1]
        except Exception:
            return DeleteCorpusCategory(ok=False, message=not_found_msg)

        category = CorpusCategory.objects.filter(pk=category_pk).first()
        if category is None:
            return DeleteCorpusCategory(ok=False, message=not_found_msg)

        category_name = category.name
        category.delete()
        logger.info(
            "Superuser %s deleted corpus category %s (%s)",
            user.id,
            category_pk,
            category_name,
        )
        return DeleteCorpusCategory(ok=True, message="Success")
