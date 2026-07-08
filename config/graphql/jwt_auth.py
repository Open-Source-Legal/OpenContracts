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




@strawberry.type(name="Verify")
class Verify:
    payload: GenericScalar = strawberry.field(name="payload", default=None)


register_type("Verify", Verify, model=None)


@strawberry.type(name="Refresh")
class Refresh:
    payload: GenericScalar = strawberry.field(name="payload", default=None)
    refresh_expires_in: int = strawberry.field(name="refreshExpiresIn", default=None)
    @strawberry.field(name="token")
    def token(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "token", None))
    @strawberry.field(name="refreshToken")
    def refresh_token(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "refresh_token", None))


register_type("Refresh", Refresh, model=None)


def _mutate_Verify(payload_cls, root, info, **kwargs):
    """PORT: graphql_jwt.mutations.Verify.mutate

    Port of Verify.mutate
    """
    raise NotImplementedError("_mutate_Verify not yet ported — see manifest")


def m_verify_token(info: strawberry.Info, token: Annotated[Optional[str], strawberry.argument(name="token")] = strawberry.UNSET) -> Optional["Verify"]:
    kwargs = strip_unset({"token": token})
    return _mutate_Verify(Verify, None, info, **kwargs)


def _mutate_Refresh(payload_cls, root, info, **kwargs):
    """PORT: graphql_jwt.mutations.Refresh.mutate

    Port of Refresh.mutate
    """
    raise NotImplementedError("_mutate_Refresh not yet ported — see manifest")


def m_refresh_token(info: strawberry.Info, refresh_token: Annotated[Optional[str], strawberry.argument(name="refreshToken")] = strawberry.UNSET) -> Optional["Refresh"]:
    kwargs = strip_unset({"refresh_token": refresh_token})
    return _mutate_Refresh(Refresh, None, info, **kwargs)



MUTATION_FIELDS = {
    "verify_token": strawberry.field(resolver=m_verify_token, name="verifyToken"),
    "refresh_token": strawberry.field(resolver=m_refresh_token, name="refreshToken"),
}
