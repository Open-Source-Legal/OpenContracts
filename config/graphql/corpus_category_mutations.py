"""
GraphQL mutations for managing :class:`CorpusCategory` records.

Corpus categories (e.g. "Case Law", "Contracts", "Legislation") are the
runtime-configurable tag set used to organise corpuses on the Discover page
and in corpus settings. They are global, admin-provisioned data with no
per-object guardian permissions, so every mutation here is gated to
superusers only — mirroring the pipeline-settings mutations.

These mutations are thin GraphQL wrappers: the superuser gate and Relay
global-id parsing stay here (GraphQL-boundary concerns), while validation,
unique-name enforcement, and all ORM access live in
:class:`~opencontractserver.corpuses.services.CorpusCategoryService` (per
CLAUDE.md rule 7). A superuser can create / update / delete categories at
runtime (via the in-app admin UI or GraphiQL) instead of editing a seed
migration or the Django admin.
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.corpus_types import CorpusCategoryType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.corpuses.services import CorpusCategoryService

logger = logging.getLogger(__name__)

# Shared not-authorized message so callers can't distinguish "doesn't exist"
# from "not permitted" beyond the superuser gate.
NOT_SUPERUSER_MESSAGE = "Only superusers can manage corpus categories."

# Shared not-found message — also returned for a well-formed global ID that
# names a different type, so the global-id namespace can't be probed.
NOT_FOUND_MESSAGE = "Category not found."


def _resolve_category_pk(global_id: str):
    """Return the PK encoded in a ``CorpusCategoryType`` global ID, or ``None``.

    Returns ``None`` for a malformed ID or a well-formed ID that names a
    different type, so a global ID for another type can't silently resolve
    against the category table.
    """
    try:
        type_name, category_pk = from_global_id(global_id)
    except Exception:
        return None
    if type_name != "CorpusCategoryType":
        return None
    return category_pk


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

        result = CorpusCategoryService.create_category(
            user,
            name=name,
            description=description,
            icon=icon,
            color=color,
            sort_order=sort_order,
        )
        if not result.ok:
            return CreateCorpusCategory(ok=False, message=result.error, obj=None)
        return CreateCorpusCategory(ok=True, message="Success", obj=result.value)


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

        category_pk = _resolve_category_pk(id)
        if category_pk is None:
            return UpdateCorpusCategory(ok=False, message=NOT_FOUND_MESSAGE, obj=None)

        category = CorpusCategoryService.get_category_or_none(category_pk)
        if category is None:
            return UpdateCorpusCategory(ok=False, message=NOT_FOUND_MESSAGE, obj=None)

        result = CorpusCategoryService.update_category(
            user,
            category,
            name=name,
            description=description,
            icon=icon,
            color=color,
            sort_order=sort_order,
        )
        if not result.ok:
            return UpdateCorpusCategory(ok=False, message=result.error, obj=None)
        return UpdateCorpusCategory(ok=True, message="Success", obj=result.value)


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

        category_pk = _resolve_category_pk(id)
        if category_pk is None:
            return DeleteCorpusCategory(ok=False, message=NOT_FOUND_MESSAGE)

        category = CorpusCategoryService.get_category_or_none(category_pk)
        if category is None:
            return DeleteCorpusCategory(ok=False, message=NOT_FOUND_MESSAGE)

        result = CorpusCategoryService.delete_category(user, category)
        if not result.ok:
            return DeleteCorpusCategory(ok=False, message=result.error)
        return DeleteCorpusCategory(ok=True, message="Success")
