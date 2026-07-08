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
from opencontractserver.enrichment.services import AuthorityNamespaceService
from opencontractserver.enrichment.services.authority_permissions import DENIED

logger = logging.getLogger(__name__)


def _decode_pk(global_id: str) -> int | None:
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, IndexError):
        return None


def _partial(**kwargs):
    """Drop ``None`` (omitted) args; keep ``""`` / ``[]`` (explicit clears)."""
    return {k: v for k, v in kwargs.items() if v is not None}


@strawberry.type(name="CreateAuthorityNamespaceMutation", description='Create a manual AuthorityNamespace (superuser-only).')
class CreateAuthorityNamespaceMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["AuthorityNamespaceNode", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="obj", default=None)


register_type("CreateAuthorityNamespaceMutation", CreateAuthorityNamespaceMutation, model=None)


@strawberry.type(name="UpdateAuthorityNamespaceMutation", description="Edit an AuthorityNamespace (superuser-only; stamps source='manual').")
class UpdateAuthorityNamespaceMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["AuthorityNamespaceNode", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="obj", default=None)


register_type("UpdateAuthorityNamespaceMutation", UpdateAuthorityNamespaceMutation, model=None)


@strawberry.type(name="SetAuthorityNamespaceAliasesMutation", description="Replace a namespace's alias set (superuser-only).")
class SetAuthorityNamespaceAliasesMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["AuthorityNamespaceNode", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="obj", default=None)


register_type("SetAuthorityNamespaceAliasesMutation", SetAuthorityNamespaceAliasesMutation, model=None)


@strawberry.type(name="DeleteAuthorityNamespaceMutation", description='Delete an AuthorityNamespace (superuser-only; guarded against orphaning).')
class DeleteAuthorityNamespaceMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("DeleteAuthorityNamespaceMutation", DeleteAuthorityNamespaceMutation, model=None)


def _mutate_CreateAuthorityNamespaceMutation(
    payload_cls,
    root,
    info,
    prefix,
    display_name,
    jurisdiction=None,
    authority_type=None,
    aliases=None,
    is_global=True,
    authority_corpus_id=None,
    provider=None,
    source_root_url=None,
    license=None,
):
    """PORT: config/graphql/authority_namespace_mutations.py:63

    Port of CreateAuthorityNamespaceMutation.mutate
    """
    # @login_required — inlined because mutate stubs take ``payload_cls`` as
    # their first positional argument, which does not match core.auth's
    # ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    # A non-empty corpus id must decode; a truthy-but-undecodable value is a
    # caller error, not a silent fall-through to "global namespace".
    corpus_pk = None
    if authority_corpus_id:
        corpus_pk = _decode_pk(authority_corpus_id)
        if corpus_pk is None:
            return payload_cls(
                ok=False, message="Invalid authority_corpus_id.", obj=None
            )
    result = AuthorityNamespaceService.create(
        info.context.user,
        prefix=prefix,
        display_name=display_name,
        jurisdiction=jurisdiction,
        authority_type=authority_type,
        aliases=aliases,
        is_global=is_global,
        authority_corpus_id=corpus_pk,
        provider=provider,
        source_root_url=source_root_url,
        license=license,
    )
    return payload_cls(
        ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
    )


def m_create_authority_namespace(info: strawberry.Info, aliases: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="aliases")] = strawberry.UNSET, authority_corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="authorityCorpusId")] = strawberry.UNSET, authority_type: Annotated[Optional[str], strawberry.argument(name="authorityType")] = strawberry.UNSET, display_name: Annotated[str, strawberry.argument(name="displayName")] = strawberry.UNSET, is_global: Annotated[Optional[bool], strawberry.argument(name="isGlobal")] = True, jurisdiction: Annotated[Optional[str], strawberry.argument(name="jurisdiction")] = strawberry.UNSET, license: Annotated[Optional[str], strawberry.argument(name="license")] = strawberry.UNSET, prefix: Annotated[str, strawberry.argument(name="prefix", description="Canonical-key prefix, e.g. 'usc-15' or 'dgcl'.")] = strawberry.UNSET, provider: Annotated[Optional[str], strawberry.argument(name="provider")] = strawberry.UNSET, source_root_url: Annotated[Optional[str], strawberry.argument(name="sourceRootUrl")] = strawberry.UNSET) -> Optional["CreateAuthorityNamespaceMutation"]:
    kwargs = strip_unset({"aliases": aliases, "authority_corpus_id": authority_corpus_id, "authority_type": authority_type, "display_name": display_name, "is_global": is_global, "jurisdiction": jurisdiction, "license": license, "prefix": prefix, "provider": provider, "source_root_url": source_root_url})
    return _mutate_CreateAuthorityNamespaceMutation(CreateAuthorityNamespaceMutation, None, info, **kwargs)


def _mutate_UpdateAuthorityNamespaceMutation(
    payload_cls,
    root,
    info,
    id,
    display_name=None,
    jurisdiction=None,
    authority_type=None,
    aliases=None,
    is_global=None,
    authority_corpus_id=None,
    provider=None,
    source_root_url=None,
    license=None,
):
    """PORT: config/graphql/authority_namespace_mutations.py:124

    Port of UpdateAuthorityNamespaceMutation.mutate
    """
    # @login_required — inlined (see _mutate_CreateAuthorityNamespaceMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    pk = _decode_pk(id)
    if pk is None:
        return payload_cls(ok=False, message=DENIED, obj=None)
    partial = _partial(
        display_name=display_name,
        jurisdiction=jurisdiction,
        authority_type=authority_type,
        aliases=aliases,
        is_global=is_global,
        provider=provider,
        source_root_url=source_root_url,
        license=license,
    )
    if authority_corpus_id is not None:
        if authority_corpus_id == "":
            # Explicit unlink (the partial-update "clear" sentinel for ids).
            partial["authority_corpus_id"] = None
        else:
            corpus_pk = _decode_pk(authority_corpus_id)
            if corpus_pk is None:
                return payload_cls(
                    ok=False, message="Invalid authority_corpus_id.", obj=None
                )
            partial["authority_corpus_id"] = corpus_pk
    result = AuthorityNamespaceService.update(info.context.user, pk=pk, **partial)
    return payload_cls(
        ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
    )


def m_update_authority_namespace(info: strawberry.Info, aliases: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="aliases")] = strawberry.UNSET, authority_corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="authorityCorpusId")] = strawberry.UNSET, authority_type: Annotated[Optional[str], strawberry.argument(name="authorityType")] = strawberry.UNSET, display_name: Annotated[Optional[str], strawberry.argument(name="displayName")] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET, is_global: Annotated[Optional[bool], strawberry.argument(name="isGlobal")] = strawberry.UNSET, jurisdiction: Annotated[Optional[str], strawberry.argument(name="jurisdiction")] = strawberry.UNSET, license: Annotated[Optional[str], strawberry.argument(name="license")] = strawberry.UNSET, provider: Annotated[Optional[str], strawberry.argument(name="provider")] = strawberry.UNSET, source_root_url: Annotated[Optional[str], strawberry.argument(name="sourceRootUrl")] = strawberry.UNSET) -> Optional["UpdateAuthorityNamespaceMutation"]:
    kwargs = strip_unset({"aliases": aliases, "authority_corpus_id": authority_corpus_id, "authority_type": authority_type, "display_name": display_name, "id": id, "is_global": is_global, "jurisdiction": jurisdiction, "license": license, "provider": provider, "source_root_url": source_root_url})
    return _mutate_UpdateAuthorityNamespaceMutation(UpdateAuthorityNamespaceMutation, None, info, **kwargs)


def _mutate_SetAuthorityNamespaceAliasesMutation(payload_cls, root, info, id, aliases):
    """PORT: config/graphql/authority_namespace_mutations.py:184

    Port of SetAuthorityNamespaceAliasesMutation.mutate
    """
    # @login_required — inlined (see _mutate_CreateAuthorityNamespaceMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    pk = _decode_pk(id)
    if pk is None:
        return payload_cls(ok=False, message=DENIED, obj=None)
    result = AuthorityNamespaceService.set_aliases(
        info.context.user, pk=pk, aliases=aliases
    )
    return payload_cls(
        ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
    )


def m_set_authority_namespace_aliases(info: strawberry.Info, aliases: Annotated[list[Optional[str]], strawberry.argument(name="aliases", description='Full replacement alias list (lowercased + de-duped).')] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["SetAuthorityNamespaceAliasesMutation"]:
    kwargs = strip_unset({"aliases": aliases, "id": id})
    return _mutate_SetAuthorityNamespaceAliasesMutation(SetAuthorityNamespaceAliasesMutation, None, info, **kwargs)


def _mutate_DeleteAuthorityNamespaceMutation(payload_cls, root, info, id):
    """PORT: config/graphql/authority_namespace_mutations.py:208

    Port of DeleteAuthorityNamespaceMutation.mutate
    """
    # @login_required — inlined (see _mutate_CreateAuthorityNamespaceMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    pk = _decode_pk(id)
    if pk is None:
        return payload_cls(ok=False, message=DENIED)
    result = AuthorityNamespaceService.delete(info.context.user, pk=pk)
    return payload_cls(ok=result.ok, message=(result.error or "SUCCESS"))


def m_delete_authority_namespace(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteAuthorityNamespaceMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteAuthorityNamespaceMutation(DeleteAuthorityNamespaceMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_authority_namespace": strawberry.field(resolver=m_create_authority_namespace, name="createAuthorityNamespace", description='Create a manual AuthorityNamespace (superuser-only).'),
    "update_authority_namespace": strawberry.field(resolver=m_update_authority_namespace, name="updateAuthorityNamespace", description="Edit an AuthorityNamespace (superuser-only; stamps source='manual')."),
    "set_authority_namespace_aliases": strawberry.field(resolver=m_set_authority_namespace_aliases, name="setAuthorityNamespaceAliases", description="Replace a namespace's alias set (superuser-only)."),
    "delete_authority_namespace": strawberry.field(resolver=m_delete_authority_namespace, name="deleteAuthorityNamespace", description='Delete an AuthorityNamespace (superuser-only; guarded against orphaning).'),
}
