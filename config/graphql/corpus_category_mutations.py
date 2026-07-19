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
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
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


@strawberry.type(
    name="CreateCorpusCategory",
    description="Create a new corpus category. Superuser-only.",
)
class CreateCorpusCategory:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[CorpusCategoryType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateCorpusCategory", CreateCorpusCategory, model=None)


@strawberry.type(
    name="UpdateCorpusCategory",
    description="Update an existing corpus category. Superuser-only.",
)
class UpdateCorpusCategory:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[CorpusCategoryType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("UpdateCorpusCategory", UpdateCorpusCategory, model=None)


@strawberry.type(
    name="DeleteCorpusCategory",
    description="Delete a corpus category. Superuser-only.\n\nDeleting a category removes it from every corpus that referenced it (the\n``Corpus.categories`` M2M through-rows are cleaned up automatically) but\ndoes not affect the corpuses themselves.",
)
class DeleteCorpusCategory:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteCorpusCategory", DeleteCorpusCategory, model=None)


def _mutate_CreateCorpusCategory(
    payload_cls,
    root,
    info,
    name,
    description=None,
    icon=None,
    color=None,
    sort_order=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_category_mutations.py:82

    Port of CreateCorpusCategory.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit is applied to an inner ``mutate`` so the calling
    # convention (root, info, ...) and the rate-limit cache group ("mutate")
    # match the graphene original.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root, info, name, description=None, icon=None, color=None, sort_order=None
    ):
        user = info.context.user

        if not user.is_superuser:
            return payload_cls(ok=False, message=NOT_SUPERUSER_MESSAGE, obj=None)

        result = CorpusCategoryService.create_category(
            user,
            name=name,
            description=description,
            icon=icon,
            color=color,
            sort_order=sort_order,
        )
        if not result.ok:
            return payload_cls(ok=False, message=result.error, obj=None)
        return payload_cls(ok=True, message="Success", obj=result.value)

    return mutate(
        root,
        info,
        name=name,
        description=description,
        icon=icon,
        color=color,
        sort_order=sort_order,
    )


def m_create_corpus_category(
    info: strawberry.Info,
    color: Annotated[
        str | None,
        strawberry.argument(
            name="color",
            description="Hex color for the badge (e.g. '#3B82F6'). Defaults to blue.",
        ),
    ] = strawberry.UNSET,
    description: Annotated[
        str | None,
        strawberry.argument(
            name="description", description="Optional human-readable description"
        ),
    ] = strawberry.UNSET,
    icon: Annotated[
        str | None,
        strawberry.argument(
            name="icon",
            description="Lucide icon name (e.g. 'scroll', 'gavel'). Defaults to 'folder'.",
        ),
    ] = strawberry.UNSET,
    name: Annotated[
        str, strawberry.argument(name="name", description="Unique category name")
    ] = strawberry.UNSET,
    sort_order: Annotated[
        int | None,
        strawberry.argument(
            name="sortOrder", description="Display order; lower sorts first"
        ),
    ] = strawberry.UNSET,
) -> CreateCorpusCategory | None:
    kwargs = strip_unset(
        {
            "color": color,
            "description": description,
            "icon": icon,
            "name": name,
            "sort_order": sort_order,
        }
    )
    return _mutate_CreateCorpusCategory(CreateCorpusCategory, None, info, **kwargs)


def _mutate_UpdateCorpusCategory(
    payload_cls,
    root,
    info,
    id,
    name=None,
    description=None,
    icon=None,
    color=None,
    sort_order=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_category_mutations.py:128

    Port of UpdateCorpusCategory.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateCorpusCategory.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_CreateCorpusCategory.
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
    ):
        user = info.context.user

        if not user.is_superuser:
            return payload_cls(ok=False, message=NOT_SUPERUSER_MESSAGE, obj=None)

        category_pk = _resolve_category_pk(id)
        if category_pk is None:
            return payload_cls(ok=False, message=NOT_FOUND_MESSAGE, obj=None)

        category = CorpusCategoryService.get_category_or_none(category_pk)
        if category is None:
            return payload_cls(ok=False, message=NOT_FOUND_MESSAGE, obj=None)

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
            return payload_cls(ok=False, message=result.error, obj=None)
        return payload_cls(ok=True, message="Success", obj=result.value)

    return mutate(
        root,
        info,
        id=id,
        name=name,
        description=description,
        icon=icon,
        color=color,
        sort_order=sort_order,
    )


def m_update_corpus_category(
    info: strawberry.Info,
    color: Annotated[str | None, strawberry.argument(name="color")] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    icon: Annotated[str | None, strawberry.argument(name="icon")] = strawberry.UNSET,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="Global ID of the category"),
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    sort_order: Annotated[
        int | None, strawberry.argument(name="sortOrder")
    ] = strawberry.UNSET,
) -> UpdateCorpusCategory | None:
    kwargs = strip_unset(
        {
            "color": color,
            "description": description,
            "icon": icon,
            "id": id,
            "name": name,
            "sort_order": sort_order,
        }
    )
    return _mutate_UpdateCorpusCategory(UpdateCorpusCategory, None, info, **kwargs)


def _mutate_DeleteCorpusCategory(payload_cls, root, info, id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_category_mutations.py:183

    Port of DeleteCorpusCategory.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateCorpusCategory.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_CreateCorpusCategory.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id):
        user = info.context.user

        if not user.is_superuser:
            return payload_cls(ok=False, message=NOT_SUPERUSER_MESSAGE)

        category_pk = _resolve_category_pk(id)
        if category_pk is None:
            return payload_cls(ok=False, message=NOT_FOUND_MESSAGE)

        category = CorpusCategoryService.get_category_or_none(category_pk)
        if category is None:
            return payload_cls(ok=False, message=NOT_FOUND_MESSAGE)

        result = CorpusCategoryService.delete_category(user, category)
        if not result.ok:
            return payload_cls(ok=False, message=result.error)
        return payload_cls(ok=True, message="Success")

    return mutate(root, info, id=id)


def m_delete_corpus_category(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="Global ID of the category"),
    ] = strawberry.UNSET,
) -> DeleteCorpusCategory | None:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteCorpusCategory(DeleteCorpusCategory, None, info, **kwargs)


MUTATION_FIELDS = {
    "create_corpus_category": strawberry.field(
        resolver=m_create_corpus_category,
        name="createCorpusCategory",
        description="Create a new corpus category. Superuser-only.",
    ),
    "update_corpus_category": strawberry.field(
        resolver=m_update_corpus_category,
        name="updateCorpusCategory",
        description="Update an existing corpus category. Superuser-only.",
    ),
    "delete_corpus_category": strawberry.field(
        resolver=m_delete_corpus_category,
        name="deleteCorpusCategory",
        description="Delete a corpus category. Superuser-only.\n\nDeleting a category removes it from every corpus that referenced it (the\n``Corpus.categories`` M2M through-rows are cleaned up automatically) but\ndoes not affect the corpuses themselves.",
    ),
}
