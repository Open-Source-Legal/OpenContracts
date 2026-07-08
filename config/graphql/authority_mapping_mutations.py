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


def _mutate_CreateAuthorityKeyEquivalenceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:48

    Port of CreateAuthorityKeyEquivalenceMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateAuthorityKeyEquivalenceMutation not yet ported — see manifest")


def m_create_authority_key_equivalence(info: strawberry.Info, from_key: Annotated[str, strawberry.argument(name="fromKey", description="Source canonical key, e.g. 'irc:401'.")] = strawberry.UNSET, note: Annotated[Optional[str], strawberry.argument(name="note", description='Why this mapping exists.')] = strawberry.UNSET, to_key: Annotated[str, strawberry.argument(name="toKey", description="Equivalent canonical key, e.g. 'usc-26:401'.")] = strawberry.UNSET) -> Optional["CreateAuthorityKeyEquivalenceMutation"]:
    kwargs = strip_unset({"from_key": from_key, "note": note, "to_key": to_key})
    return _mutate_CreateAuthorityKeyEquivalenceMutation(CreateAuthorityKeyEquivalenceMutation, None, info, **kwargs)


def _mutate_UpdateAuthorityKeyEquivalenceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:71

    Port of UpdateAuthorityKeyEquivalenceMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateAuthorityKeyEquivalenceMutation not yet ported — see manifest")


def m_update_authority_key_equivalence(info: strawberry.Info, from_key: Annotated[Optional[str], strawberry.argument(name="fromKey")] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='Global ID of the row to edit.')] = strawberry.UNSET, note: Annotated[Optional[str], strawberry.argument(name="note")] = strawberry.UNSET, to_key: Annotated[Optional[str], strawberry.argument(name="toKey")] = strawberry.UNSET) -> Optional["UpdateAuthorityKeyEquivalenceMutation"]:
    kwargs = strip_unset({"from_key": from_key, "id": id, "note": note, "to_key": to_key})
    return _mutate_UpdateAuthorityKeyEquivalenceMutation(UpdateAuthorityKeyEquivalenceMutation, None, info, **kwargs)


def _mutate_DeleteAuthorityKeyEquivalenceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:99

    Port of DeleteAuthorityKeyEquivalenceMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteAuthorityKeyEquivalenceMutation not yet ported — see manifest")


def m_delete_authority_key_equivalence(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='Global ID of the row to delete.')] = strawberry.UNSET) -> Optional["DeleteAuthorityKeyEquivalenceMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteAuthorityKeyEquivalenceMutation(DeleteAuthorityKeyEquivalenceMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_authority_key_equivalence": strawberry.field(resolver=m_create_authority_key_equivalence, name="createAuthorityKeyEquivalence", description='Create a manual canonical-key equivalence (superuser-only).'),
    "update_authority_key_equivalence": strawberry.field(resolver=m_update_authority_key_equivalence, name="updateAuthorityKeyEquivalence", description='Edit a manual equivalence (superuser-only; managed rows are read-only).'),
    "delete_authority_key_equivalence": strawberry.field(resolver=m_delete_authority_key_equivalence, name="deleteAuthorityKeyEquivalence", description='Delete a manual equivalence (superuser-only; managed rows are read-only).'),
}
