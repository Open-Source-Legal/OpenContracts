"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

import logging

from graphql_relay import from_global_id

from config.graphql.core.auth import PermissionDenied
from opencontractserver.enrichment.services import AuthorityKeyEquivalenceService
from opencontractserver.enrichment.services.authority_mapping_service import DENIED

logger = logging.getLogger(__name__)


def _decode_pk(global_id: str) -> int | None:
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, IndexError):
        return None


@strawberry.type(name="CreateAuthorityKeyEquivalenceMutation", description='Create a manual canonical-key equivalence (superuser-only).')
class CreateAuthorityKeyEquivalenceMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["AuthorityKeyEquivalenceNode", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="obj", default=None)


register_type("CreateAuthorityKeyEquivalenceMutation", CreateAuthorityKeyEquivalenceMutation, model=None)


@strawberry.type(name="UpdateAuthorityKeyEquivalenceMutation", description='Edit a manual equivalence (superuser-only; managed rows are read-only).')
class UpdateAuthorityKeyEquivalenceMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["AuthorityKeyEquivalenceNode", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="obj", default=None)


register_type("UpdateAuthorityKeyEquivalenceMutation", UpdateAuthorityKeyEquivalenceMutation, model=None)


@strawberry.type(name="DeleteAuthorityKeyEquivalenceMutation", description='Delete a manual equivalence (superuser-only; managed rows are read-only).')
class DeleteAuthorityKeyEquivalenceMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("DeleteAuthorityKeyEquivalenceMutation", DeleteAuthorityKeyEquivalenceMutation, model=None)


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


def m_create_authority_key_equivalence(info: strawberry.Info, from_key: Annotated[str, strawberry.argument(name="fromKey", description="Source canonical key, e.g. 'irc:401'.")] = strawberry.UNSET, note: Annotated[Optional[str], strawberry.argument(name="note", description='Why this mapping exists.')] = strawberry.UNSET, to_key: Annotated[str, strawberry.argument(name="toKey", description="Equivalent canonical key, e.g. 'usc-26:401'.")] = strawberry.UNSET) -> Optional["CreateAuthorityKeyEquivalenceMutation"]:
    kwargs = strip_unset({"from_key": from_key, "note": note, "to_key": to_key})
    return _mutate_CreateAuthorityKeyEquivalenceMutation(CreateAuthorityKeyEquivalenceMutation, None, info, **kwargs)


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


def m_update_authority_key_equivalence(info: strawberry.Info, from_key: Annotated[Optional[str], strawberry.argument(name="fromKey")] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='Global ID of the row to edit.')] = strawberry.UNSET, note: Annotated[Optional[str], strawberry.argument(name="note")] = strawberry.UNSET, to_key: Annotated[Optional[str], strawberry.argument(name="toKey")] = strawberry.UNSET) -> Optional["UpdateAuthorityKeyEquivalenceMutation"]:
    kwargs = strip_unset({"from_key": from_key, "id": id, "note": note, "to_key": to_key})
    return _mutate_UpdateAuthorityKeyEquivalenceMutation(UpdateAuthorityKeyEquivalenceMutation, None, info, **kwargs)


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


def m_delete_authority_key_equivalence(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='Global ID of the row to delete.')] = strawberry.UNSET) -> Optional["DeleteAuthorityKeyEquivalenceMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteAuthorityKeyEquivalenceMutation(DeleteAuthorityKeyEquivalenceMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_authority_key_equivalence": strawberry.field(resolver=m_create_authority_key_equivalence, name="createAuthorityKeyEquivalence", description='Create a manual canonical-key equivalence (superuser-only).'),
    "update_authority_key_equivalence": strawberry.field(resolver=m_update_authority_key_equivalence, name="updateAuthorityKeyEquivalence", description='Edit a manual equivalence (superuser-only; managed rows are read-only).'),
    "delete_authority_key_equivalence": strawberry.field(resolver=m_delete_authority_key_equivalence, name="deleteAuthorityKeyEquivalence", description='Delete a manual equivalence (superuser-only; managed rows are read-only).'),
}
