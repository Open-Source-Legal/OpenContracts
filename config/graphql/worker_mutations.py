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




@strawberry.type(name="CreateWorkerAccount", description='Create a new worker service account. Superuser only.')
class CreateWorkerAccount:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    worker_account: Optional[Annotated["WorkerAccountType", strawberry.lazy("config.graphql.worker_types")]] = strawberry.field(name="workerAccount", default=None)


register_type("CreateWorkerAccount", CreateWorkerAccount, model=None)


@strawberry.type(name="DeactivateWorkerAccount", description='Deactivate a worker account (revokes all its tokens implicitly). Superuser only.')
class DeactivateWorkerAccount:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)


register_type("DeactivateWorkerAccount", DeactivateWorkerAccount, model=None)


@strawberry.type(name="ReactivateWorkerAccount", description='Reactivate a previously deactivated worker account. Superuser only.')
class ReactivateWorkerAccount:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)


register_type("ReactivateWorkerAccount", ReactivateWorkerAccount, model=None)


@strawberry.type(name="CreateCorpusAccessTokenMutation", description='Create a scoped access token granting a worker upload access to a corpus.\n\nReturns the full token key — it is only shown once.\nAllowed for superusers and the corpus creator.')
class CreateCorpusAccessTokenMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    token: Optional[Annotated["CorpusAccessTokenCreatedType", strawberry.lazy("config.graphql.worker_types")]] = strawberry.field(name="token", default=None)


register_type("CreateCorpusAccessTokenMutation", CreateCorpusAccessTokenMutation, model=None)


@strawberry.type(name="RevokeCorpusAccessTokenMutation", description='Revoke a corpus access token. Allowed for superusers and the corpus creator.')
class RevokeCorpusAccessTokenMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)


register_type("RevokeCorpusAccessTokenMutation", RevokeCorpusAccessTokenMutation, model=None)


def _mutate_CreateWorkerAccount(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:53

    Port of CreateWorkerAccount.mutate
    """
    raise NotImplementedError("_mutate_CreateWorkerAccount not yet ported — see manifest")


def m_create_worker_account(info: strawberry.Info, description: Annotated[Optional[str], strawberry.argument(name="description")] = '', name: Annotated[str, strawberry.argument(name="name")] = strawberry.UNSET) -> Optional["CreateWorkerAccount"]:
    kwargs = strip_unset({"description": description, "name": name})
    return _mutate_CreateWorkerAccount(CreateWorkerAccount, None, info, **kwargs)


def _mutate_DeactivateWorkerAccount(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:88

    Port of DeactivateWorkerAccount.mutate
    """
    raise NotImplementedError("_mutate_DeactivateWorkerAccount not yet ported — see manifest")


def m_deactivate_worker_account(info: strawberry.Info, worker_account_id: Annotated[int, strawberry.argument(name="workerAccountId")] = strawberry.UNSET) -> Optional["DeactivateWorkerAccount"]:
    kwargs = strip_unset({"worker_account_id": worker_account_id})
    return _mutate_DeactivateWorkerAccount(DeactivateWorkerAccount, None, info, **kwargs)


def _mutate_ReactivateWorkerAccount(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:109

    Port of ReactivateWorkerAccount.mutate
    """
    raise NotImplementedError("_mutate_ReactivateWorkerAccount not yet ported — see manifest")


def m_reactivate_worker_account(info: strawberry.Info, worker_account_id: Annotated[int, strawberry.argument(name="workerAccountId")] = strawberry.UNSET) -> Optional["ReactivateWorkerAccount"]:
    kwargs = strip_unset({"worker_account_id": worker_account_id})
    return _mutate_ReactivateWorkerAccount(ReactivateWorkerAccount, None, info, **kwargs)


def _mutate_CreateCorpusAccessTokenMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:139

    Port of CreateCorpusAccessTokenMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateCorpusAccessTokenMutation not yet ported — see manifest")


def m_create_corpus_access_token(info: strawberry.Info, corpus_id: Annotated[int, strawberry.argument(name="corpusId")] = strawberry.UNSET, expires_at: Annotated[Optional[datetime.datetime], strawberry.argument(name="expiresAt")] = None, rate_limit_per_minute: Annotated[Optional[int], strawberry.argument(name="rateLimitPerMinute")] = 0, worker_account_id: Annotated[int, strawberry.argument(name="workerAccountId")] = strawberry.UNSET) -> Optional["CreateCorpusAccessTokenMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "expires_at": expires_at, "rate_limit_per_minute": rate_limit_per_minute, "worker_account_id": worker_account_id})
    return _mutate_CreateCorpusAccessTokenMutation(CreateCorpusAccessTokenMutation, None, info, **kwargs)


def _mutate_RevokeCorpusAccessTokenMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:185

    Port of RevokeCorpusAccessTokenMutation.mutate
    """
    raise NotImplementedError("_mutate_RevokeCorpusAccessTokenMutation not yet ported — see manifest")


def m_revoke_corpus_access_token(info: strawberry.Info, token_id: Annotated[int, strawberry.argument(name="tokenId")] = strawberry.UNSET) -> Optional["RevokeCorpusAccessTokenMutation"]:
    kwargs = strip_unset({"token_id": token_id})
    return _mutate_RevokeCorpusAccessTokenMutation(RevokeCorpusAccessTokenMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_worker_account": strawberry.field(resolver=m_create_worker_account, name="createWorkerAccount", description='Create a new worker service account. Superuser only.'),
    "deactivate_worker_account": strawberry.field(resolver=m_deactivate_worker_account, name="deactivateWorkerAccount", description='Deactivate a worker account (revokes all its tokens implicitly). Superuser only.'),
    "reactivate_worker_account": strawberry.field(resolver=m_reactivate_worker_account, name="reactivateWorkerAccount", description='Reactivate a previously deactivated worker account. Superuser only.'),
    "create_corpus_access_token": strawberry.field(resolver=m_create_corpus_access_token, name="createCorpusAccessToken", description='Create a scoped access token granting a worker upload access to a corpus.\n\nReturns the full token key — it is only shown once.\nAllowed for superusers and the corpus creator.'),
    "revoke_corpus_access_token": strawberry.field(resolver=m_revoke_corpus_access_token, name="revokeCorpusAccessToken", description='Revoke a corpus access token. Allowed for superusers and the corpus creator.'),
}
