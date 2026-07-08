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
from opencontractserver.enrichment.services import AuthorityKeyEquivalenceService
from opencontractserver.enrichment.services.authority_mapping_service import DENIED

logger = logging.getLogger(__name__)


def _decode_pk(global_id: str) -> int | None:
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, IndexError):
        return None


@strawberry.type(
    name="CreateAuthorityKeyEquivalenceMutation",
    description="Create a manual canonical-key equivalence (superuser-only).",
)
class CreateAuthorityKeyEquivalenceMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            AuthorityKeyEquivalenceNode,
            strawberry.lazy("config.graphql.annotation_types"),
        ]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "CreateAuthorityKeyEquivalenceMutation",
    CreateAuthorityKeyEquivalenceMutation,
    model=None,
)


@strawberry.type(
    name="UpdateAuthorityKeyEquivalenceMutation",
    description="Edit a manual equivalence (superuser-only; managed rows are read-only).",
)
class UpdateAuthorityKeyEquivalenceMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            AuthorityKeyEquivalenceNode,
            strawberry.lazy("config.graphql.annotation_types"),
        ]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "UpdateAuthorityKeyEquivalenceMutation",
    UpdateAuthorityKeyEquivalenceMutation,
    model=None,
)


@strawberry.type(
    name="DeleteAuthorityKeyEquivalenceMutation",
    description="Delete a manual equivalence (superuser-only; managed rows are read-only).",
)
class DeleteAuthorityKeyEquivalenceMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type(
    "DeleteAuthorityKeyEquivalenceMutation",
    DeleteAuthorityKeyEquivalenceMutation,
    model=None,
)


def _mutate_CreateAuthorityKeyEquivalenceMutation(
    payload_cls, root, info, from_key, to_key, note=None
):
    """PORT: config/graphql/authority_mapping_mutations.py:49

    Port of CreateAuthorityKeyEquivalenceMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    result = AuthorityKeyEquivalenceService.create(
        info.context.user, from_key=from_key, to_key=to_key, note=note
    )
    return payload_cls(
        ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
    )


def m_create_authority_key_equivalence(
    info: strawberry.Info,
    from_key: Annotated[
        str,
        strawberry.argument(
            name="fromKey", description="Source canonical key, e.g. 'irc:401'."
        ),
    ] = strawberry.UNSET,
    note: Annotated[
        str | None,
        strawberry.argument(name="note", description="Why this mapping exists."),
    ] = strawberry.UNSET,
    to_key: Annotated[
        str,
        strawberry.argument(
            name="toKey", description="Equivalent canonical key, e.g. 'usc-26:401'."
        ),
    ] = strawberry.UNSET,
) -> CreateAuthorityKeyEquivalenceMutation | None:
    kwargs = strip_unset({"from_key": from_key, "note": note, "to_key": to_key})
    return _mutate_CreateAuthorityKeyEquivalenceMutation(
        CreateAuthorityKeyEquivalenceMutation, None, info, **kwargs
    )


def _mutate_UpdateAuthorityKeyEquivalenceMutation(
    payload_cls, root, info, id, from_key=None, to_key=None, note=None
):
    """PORT: config/graphql/authority_mapping_mutations.py:72

    Port of UpdateAuthorityKeyEquivalenceMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see
    # _mutate_CreateAuthorityKeyEquivalenceMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    pk = _decode_pk(id)
    if pk is None:
        return payload_cls(ok=False, message=DENIED, obj=None)
    result = AuthorityKeyEquivalenceService.update(
        info.context.user,
        pk=pk,
        from_key=from_key,
        to_key=to_key,
        note=note,
    )
    return payload_cls(
        ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
    )


def m_update_authority_key_equivalence(
    info: strawberry.Info,
    from_key: Annotated[
        str | None, strawberry.argument(name="fromKey")
    ] = strawberry.UNSET,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="Global ID of the row to edit."),
    ] = strawberry.UNSET,
    note: Annotated[str | None, strawberry.argument(name="note")] = strawberry.UNSET,
    to_key: Annotated[str | None, strawberry.argument(name="toKey")] = strawberry.UNSET,
) -> UpdateAuthorityKeyEquivalenceMutation | None:
    kwargs = strip_unset(
        {"from_key": from_key, "id": id, "note": note, "to_key": to_key}
    )
    return _mutate_UpdateAuthorityKeyEquivalenceMutation(
        UpdateAuthorityKeyEquivalenceMutation, None, info, **kwargs
    )


def _mutate_DeleteAuthorityKeyEquivalenceMutation(payload_cls, root, info, id):
    """PORT: config/graphql/authority_mapping_mutations.py:100

    Port of DeleteAuthorityKeyEquivalenceMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see
    # _mutate_CreateAuthorityKeyEquivalenceMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    pk = _decode_pk(id)
    if pk is None:
        return payload_cls(ok=False, message=DENIED)
    result = AuthorityKeyEquivalenceService.delete(info.context.user, pk=pk)
    return payload_cls(ok=result.ok, message=(result.error or "SUCCESS"))


def m_delete_authority_key_equivalence(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="Global ID of the row to delete."),
    ] = strawberry.UNSET,
) -> DeleteAuthorityKeyEquivalenceMutation | None:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteAuthorityKeyEquivalenceMutation(
        DeleteAuthorityKeyEquivalenceMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_authority_key_equivalence": strawberry.field(
        resolver=m_create_authority_key_equivalence,
        name="createAuthorityKeyEquivalence",
        description="Create a manual canonical-key equivalence (superuser-only).",
    ),
    "update_authority_key_equivalence": strawberry.field(
        resolver=m_update_authority_key_equivalence,
        name="updateAuthorityKeyEquivalence",
        description="Edit a manual equivalence (superuser-only; managed rows are read-only).",
    ),
    "delete_authority_key_equivalence": strawberry.field(
        resolver=m_delete_authority_key_equivalence,
        name="deleteAuthorityKeyEquivalence",
        description="Delete a manual equivalence (superuser-only; managed rows are read-only).",
    ),
}
