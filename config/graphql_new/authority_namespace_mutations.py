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
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums




@strawberry.type(name="CreateAuthorityNamespaceMutation", description='Create a manual AuthorityNamespace (superuser-only).')
class CreateAuthorityNamespaceMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["AuthorityNamespaceNode", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")


register_type("CreateAuthorityNamespaceMutation", CreateAuthorityNamespaceMutation, model=None)


@strawberry.type(name="UpdateAuthorityNamespaceMutation", description="Edit an AuthorityNamespace (superuser-only; stamps source='manual').")
class UpdateAuthorityNamespaceMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["AuthorityNamespaceNode", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")


register_type("UpdateAuthorityNamespaceMutation", UpdateAuthorityNamespaceMutation, model=None)


@strawberry.type(name="SetAuthorityNamespaceAliasesMutation", description="Replace a namespace's alias set (superuser-only).")
class SetAuthorityNamespaceAliasesMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["AuthorityNamespaceNode", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")


register_type("SetAuthorityNamespaceAliasesMutation", SetAuthorityNamespaceAliasesMutation, model=None)


@strawberry.type(name="DeleteAuthorityNamespaceMutation", description='Delete an AuthorityNamespace (superuser-only; guarded against orphaning).')
class DeleteAuthorityNamespaceMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteAuthorityNamespaceMutation", DeleteAuthorityNamespaceMutation, model=None)


def _mutate_CreateAuthorityNamespaceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:63

    Port of CreateAuthorityNamespaceMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateAuthorityNamespaceMutation not yet ported — see manifest")


def m_create_authority_namespace(info: strawberry.Info, aliases: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="aliases")] = strawberry.UNSET, authority_corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="authorityCorpusId")] = strawberry.UNSET, authority_type: Annotated[Optional[str], strawberry.argument(name="authorityType")] = strawberry.UNSET, display_name: Annotated[str, strawberry.argument(name="displayName")] = strawberry.UNSET, is_global: Annotated[Optional[bool], strawberry.argument(name="isGlobal")] = True, jurisdiction: Annotated[Optional[str], strawberry.argument(name="jurisdiction")] = strawberry.UNSET, license: Annotated[Optional[str], strawberry.argument(name="license")] = strawberry.UNSET, prefix: Annotated[str, strawberry.argument(name="prefix", description="Canonical-key prefix, e.g. 'usc-15' or 'dgcl'.")] = strawberry.UNSET, provider: Annotated[Optional[str], strawberry.argument(name="provider")] = strawberry.UNSET, source_root_url: Annotated[Optional[str], strawberry.argument(name="sourceRootUrl")] = strawberry.UNSET) -> Optional["CreateAuthorityNamespaceMutation"]:
    kwargs = strip_unset({"aliases": aliases, "authority_corpus_id": authority_corpus_id, "authority_type": authority_type, "display_name": display_name, "is_global": is_global, "jurisdiction": jurisdiction, "license": license, "prefix": prefix, "provider": provider, "source_root_url": source_root_url})
    return _mutate_CreateAuthorityNamespaceMutation(CreateAuthorityNamespaceMutation, None, info, **kwargs)


def _mutate_UpdateAuthorityNamespaceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:124

    Port of UpdateAuthorityNamespaceMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateAuthorityNamespaceMutation not yet ported — see manifest")


def m_update_authority_namespace(info: strawberry.Info, aliases: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="aliases")] = strawberry.UNSET, authority_corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="authorityCorpusId")] = strawberry.UNSET, authority_type: Annotated[Optional[str], strawberry.argument(name="authorityType")] = strawberry.UNSET, display_name: Annotated[Optional[str], strawberry.argument(name="displayName")] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET, is_global: Annotated[Optional[bool], strawberry.argument(name="isGlobal")] = strawberry.UNSET, jurisdiction: Annotated[Optional[str], strawberry.argument(name="jurisdiction")] = strawberry.UNSET, license: Annotated[Optional[str], strawberry.argument(name="license")] = strawberry.UNSET, provider: Annotated[Optional[str], strawberry.argument(name="provider")] = strawberry.UNSET, source_root_url: Annotated[Optional[str], strawberry.argument(name="sourceRootUrl")] = strawberry.UNSET) -> Optional["UpdateAuthorityNamespaceMutation"]:
    kwargs = strip_unset({"aliases": aliases, "authority_corpus_id": authority_corpus_id, "authority_type": authority_type, "display_name": display_name, "id": id, "is_global": is_global, "jurisdiction": jurisdiction, "license": license, "provider": provider, "source_root_url": source_root_url})
    return _mutate_UpdateAuthorityNamespaceMutation(UpdateAuthorityNamespaceMutation, None, info, **kwargs)


def _mutate_SetAuthorityNamespaceAliasesMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:184

    Port of SetAuthorityNamespaceAliasesMutation.mutate
    """
    raise NotImplementedError("_mutate_SetAuthorityNamespaceAliasesMutation not yet ported — see manifest")


def m_set_authority_namespace_aliases(info: strawberry.Info, aliases: Annotated[list[Optional[str]], strawberry.argument(name="aliases", description='Full replacement alias list (lowercased + de-duped).')] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["SetAuthorityNamespaceAliasesMutation"]:
    kwargs = strip_unset({"aliases": aliases, "id": id})
    return _mutate_SetAuthorityNamespaceAliasesMutation(SetAuthorityNamespaceAliasesMutation, None, info, **kwargs)


def _mutate_DeleteAuthorityNamespaceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:208

    Port of DeleteAuthorityNamespaceMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteAuthorityNamespaceMutation not yet ported — see manifest")


def m_delete_authority_namespace(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteAuthorityNamespaceMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteAuthorityNamespaceMutation(DeleteAuthorityNamespaceMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_authority_namespace": strawberry.field(resolver=m_create_authority_namespace, name="createAuthorityNamespace", description='Create a manual AuthorityNamespace (superuser-only).'),
    "update_authority_namespace": strawberry.field(resolver=m_update_authority_namespace, name="updateAuthorityNamespace", description="Edit an AuthorityNamespace (superuser-only; stamps source='manual')."),
    "set_authority_namespace_aliases": strawberry.field(resolver=m_set_authority_namespace_aliases, name="setAuthorityNamespaceAliases", description="Replace a namespace's alias set (superuser-only)."),
    "delete_authority_namespace": strawberry.field(resolver=m_delete_authority_namespace, name="deleteAuthorityNamespace", description='Delete an AuthorityNamespace (superuser-only; guarded against orphaning).'),
}
