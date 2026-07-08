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




@strawberry.type(name="RequeueAuthorityFrontierMutation", description='Re-queue a row (clears document + error) — un-sticks deferred_cap/failed.')
class RequeueAuthorityFrontierMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["AuthorityFrontierNode", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")


register_type("RequeueAuthorityFrontierMutation", RequeueAuthorityFrontierMutation, model=None)


@strawberry.type(name="ResetAuthorityFrontierMutation", description='Hard reset (clears document + provider + error) and re-queue.')
class ResetAuthorityFrontierMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["AuthorityFrontierNode", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")


register_type("ResetAuthorityFrontierMutation", ResetAuthorityFrontierMutation, model=None)


@strawberry.type(name="RerouteAuthorityFrontierMutation", description='Re-assign the provider (validated against the registry) and re-queue.')
class RerouteAuthorityFrontierMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["AuthorityFrontierNode", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")


register_type("RerouteAuthorityFrontierMutation", RerouteAuthorityFrontierMutation, model=None)


@strawberry.type(name="ApproveAuthorityFrontierMutation", description='Approve a pending_approval candidate so it re-enters the queue.')
class ApproveAuthorityFrontierMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["AuthorityFrontierNode", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")


register_type("ApproveAuthorityFrontierMutation", ApproveAuthorityFrontierMutation, model=None)


@strawberry.type(name="DeleteAuthorityFrontierMutation", description='Delete one or more frontier rows (superuser-only bulk action).')
class DeleteAuthorityFrontierMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    count: Optional[int] = strawberry.field(name="count")


register_type("DeleteAuthorityFrontierMutation", DeleteAuthorityFrontierMutation, model=None)


def _mutate_RequeueAuthorityFrontierMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:53

    Port of RequeueAuthorityFrontierMutation.mutate
    """
    raise NotImplementedError("_mutate_RequeueAuthorityFrontierMutation not yet ported — see manifest")


def m_requeue_authority_frontier(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["RequeueAuthorityFrontierMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_RequeueAuthorityFrontierMutation(RequeueAuthorityFrontierMutation, None, info, **kwargs)


def _mutate_ResetAuthorityFrontierMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:68

    Port of ResetAuthorityFrontierMutation.mutate
    """
    raise NotImplementedError("_mutate_ResetAuthorityFrontierMutation not yet ported — see manifest")


def m_reset_authority_frontier(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["ResetAuthorityFrontierMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_ResetAuthorityFrontierMutation(ResetAuthorityFrontierMutation, None, info, **kwargs)


def _mutate_RerouteAuthorityFrontierMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:101

    Port of RerouteAuthorityFrontierMutation.mutate
    """
    raise NotImplementedError("_mutate_RerouteAuthorityFrontierMutation not yet ported — see manifest")


def m_reroute_authority_frontier(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET, provider: Annotated[str, strawberry.argument(name="provider", description='Registry provider class name to route to.')] = strawberry.UNSET) -> Optional["RerouteAuthorityFrontierMutation"]:
    kwargs = strip_unset({"id": id, "provider": provider})
    return _mutate_RerouteAuthorityFrontierMutation(RerouteAuthorityFrontierMutation, None, info, **kwargs)


def _mutate_ApproveAuthorityFrontierMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:83

    Port of ApproveAuthorityFrontierMutation.mutate
    """
    raise NotImplementedError("_mutate_ApproveAuthorityFrontierMutation not yet ported — see manifest")


def m_approve_authority_frontier(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["ApproveAuthorityFrontierMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_ApproveAuthorityFrontierMutation(ApproveAuthorityFrontierMutation, None, info, **kwargs)


def _mutate_DeleteAuthorityFrontierMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:122

    Port of DeleteAuthorityFrontierMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteAuthorityFrontierMutation not yet ported — see manifest")


def m_delete_authority_frontier(info: strawberry.Info, ids: Annotated[list[strawberry.ID], strawberry.argument(name="ids", description='Global IDs of the frontier rows to delete.')] = strawberry.UNSET) -> Optional["DeleteAuthorityFrontierMutation"]:
    kwargs = strip_unset({"ids": ids})
    return _mutate_DeleteAuthorityFrontierMutation(DeleteAuthorityFrontierMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "requeue_authority_frontier": strawberry.field(resolver=m_requeue_authority_frontier, name="requeueAuthorityFrontier", description='Re-queue a row (clears document + error) — un-sticks deferred_cap/failed.'),
    "reset_authority_frontier": strawberry.field(resolver=m_reset_authority_frontier, name="resetAuthorityFrontier", description='Hard reset (clears document + provider + error) and re-queue.'),
    "reroute_authority_frontier": strawberry.field(resolver=m_reroute_authority_frontier, name="rerouteAuthorityFrontier", description='Re-assign the provider (validated against the registry) and re-queue.'),
    "approve_authority_frontier": strawberry.field(resolver=m_approve_authority_frontier, name="approveAuthorityFrontier", description='Approve a pending_approval candidate so it re-enters the queue.'),
    "delete_authority_frontier": strawberry.field(resolver=m_delete_authority_frontier, name="deleteAuthorityFrontier", description='Delete one or more frontier rows (superuser-only bulk action).'),
}
