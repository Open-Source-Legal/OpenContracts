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

import datetime
import logging
from typing import Annotated, cast

import strawberry
from graphql import GraphQLError

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.worker_types import (
    CorpusAccessTokenCreatedType,
    WorkerAccountType,
)
from opencontractserver.worker_uploads.services import (
    CorpusAccessTokenService,
    WorkerAccountService,
)

logger = logging.getLogger(__name__)


@strawberry.type(
    name="CreateWorkerAccount",
    description="Create a new worker service account. Superuser only.",
)
class CreateWorkerAccount:
    ok: bool | None = strawberry.field(name="ok", default=None)
    worker_account: None | (
        Annotated[WorkerAccountType, strawberry.lazy("config.graphql.worker_types")]
    ) = strawberry.field(name="workerAccount", default=None)


register_type("CreateWorkerAccount", CreateWorkerAccount, model=None)


@strawberry.type(
    name="DeactivateWorkerAccount",
    description="Deactivate a worker account (revokes all its tokens implicitly). Superuser only.",
)
class DeactivateWorkerAccount:
    ok: bool | None = strawberry.field(name="ok", default=None)


register_type("DeactivateWorkerAccount", DeactivateWorkerAccount, model=None)


@strawberry.type(
    name="ReactivateWorkerAccount",
    description="Reactivate a previously deactivated worker account. Superuser only.",
)
class ReactivateWorkerAccount:
    ok: bool | None = strawberry.field(name="ok", default=None)


register_type("ReactivateWorkerAccount", ReactivateWorkerAccount, model=None)


@strawberry.type(
    name="CreateCorpusAccessTokenMutation",
    description="Create a scoped access token granting a worker upload access to a corpus.\n\nReturns the full token key — it is only shown once.\nAllowed for superusers and the corpus creator.",
)
class CreateCorpusAccessTokenMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    token: None | (
        Annotated[
            CorpusAccessTokenCreatedType,
            strawberry.lazy("config.graphql.worker_types"),
        ]
    ) = strawberry.field(name="token", default=None)


register_type(
    "CreateCorpusAccessTokenMutation", CreateCorpusAccessTokenMutation, model=None
)


@strawberry.type(
    name="RevokeCorpusAccessTokenMutation",
    description="Revoke a corpus access token. Allowed for superusers and the corpus creator.",
)
class RevokeCorpusAccessTokenMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)


register_type(
    "RevokeCorpusAccessTokenMutation", RevokeCorpusAccessTokenMutation, model=None
)


def _mutate_CreateWorkerAccount(payload_cls, root, info, name, description=""):
    """Port of CreateWorkerAccount.mutate"""
    # @user_passes_test(lambda user: user.is_superuser) — inlined.
    if not getattr(info.context.user, "is_superuser", False):
        raise PermissionDenied()

    result = WorkerAccountService.create_worker_account(
        info.context.user,
        name=name,
        description=description,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)

    # ``result.ok`` invariant: success carries a non-None value. ``cast``
    # narrows the type for mypy without relying on ``assert`` (which is
    # stripped under ``python -O``).
    account = cast("WorkerAccount", result.value)
    return payload_cls(
        ok=True,
        worker_account=WorkerAccountType(
            id=account.id,
            name=account.name,
            description=account.description,
            is_active=account.is_active,
            created=account.created,
        ),
    )


def m_create_worker_account(
    info: strawberry.Info,
    description: Annotated[str | None, strawberry.argument(name="description")] = "",
    name: Annotated[str, strawberry.argument(name="name")] = strawberry.UNSET,
) -> CreateWorkerAccount | None:
    kwargs = strip_unset({"description": description, "name": name})
    return _mutate_CreateWorkerAccount(CreateWorkerAccount, None, info, **kwargs)


def _mutate_DeactivateWorkerAccount(payload_cls, root, info, worker_account_id):
    """Port of DeactivateWorkerAccount.mutate"""
    # @user_passes_test(lambda user: user.is_superuser) — inlined.
    if not getattr(info.context.user, "is_superuser", False):
        raise PermissionDenied()

    result = WorkerAccountService.set_active(
        info.context.user,
        worker_account_id,
        active=False,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)
    return payload_cls(ok=True)


def m_deactivate_worker_account(
    info: strawberry.Info,
    worker_account_id: Annotated[
        int, strawberry.argument(name="workerAccountId")
    ] = strawberry.UNSET,
) -> DeactivateWorkerAccount | None:
    kwargs = strip_unset({"worker_account_id": worker_account_id})
    return _mutate_DeactivateWorkerAccount(
        DeactivateWorkerAccount, None, info, **kwargs
    )


def _mutate_ReactivateWorkerAccount(payload_cls, root, info, worker_account_id):
    """Port of ReactivateWorkerAccount.mutate"""
    # @user_passes_test(lambda user: user.is_superuser) — inlined.
    if not getattr(info.context.user, "is_superuser", False):
        raise PermissionDenied()

    result = WorkerAccountService.set_active(
        info.context.user,
        worker_account_id,
        active=True,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)
    return payload_cls(ok=True)


def m_reactivate_worker_account(
    info: strawberry.Info,
    worker_account_id: Annotated[
        int, strawberry.argument(name="workerAccountId")
    ] = strawberry.UNSET,
) -> ReactivateWorkerAccount | None:
    kwargs = strip_unset({"worker_account_id": worker_account_id})
    return _mutate_ReactivateWorkerAccount(
        ReactivateWorkerAccount, None, info, **kwargs
    )


def _mutate_CreateCorpusAccessTokenMutation(
    payload_cls,
    root,
    info,
    worker_account_id,
    corpus_id,
    expires_at=None,
    rate_limit_per_minute=0,
):
    """Port of CreateCorpusAccessTokenMutation.mutate"""
    # @login_required — inlined.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    result = CorpusAccessTokenService.create_token(
        info.context.user,
        worker_account_id=worker_account_id,
        corpus_id=corpus_id,
        expires_at=expires_at,
        rate_limit_per_minute=rate_limit_per_minute,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)

    # ``result.ok`` invariant: success carries a non-None value. ``cast``
    # narrows the type for mypy without relying on ``assert`` (which is
    # stripped under ``python -O``).
    token, plaintext_key = cast("tuple[CorpusAccessToken, str]", result.value)
    return payload_cls(
        ok=True,
        token=CorpusAccessTokenCreatedType(
            id=token.id,
            key=plaintext_key,
            worker_account_name=token.worker_account.name,
            corpus_id=token.corpus_id,
            expires_at=token.expires_at,
            rate_limit_per_minute=token.rate_limit_per_minute,
            created=token.created,
        ),
    )


def m_create_corpus_access_token(
    info: strawberry.Info,
    corpus_id: Annotated[int, strawberry.argument(name="corpusId")] = strawberry.UNSET,
    expires_at: Annotated[
        datetime.datetime | None, strawberry.argument(name="expiresAt")
    ] = None,
    rate_limit_per_minute: Annotated[
        int | None, strawberry.argument(name="rateLimitPerMinute")
    ] = 0,
    worker_account_id: Annotated[
        int, strawberry.argument(name="workerAccountId")
    ] = strawberry.UNSET,
) -> CreateCorpusAccessTokenMutation | None:
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "expires_at": expires_at,
            "rate_limit_per_minute": rate_limit_per_minute,
            "worker_account_id": worker_account_id,
        }
    )
    return _mutate_CreateCorpusAccessTokenMutation(
        CreateCorpusAccessTokenMutation, None, info, **kwargs
    )


def _mutate_RevokeCorpusAccessTokenMutation(payload_cls, root, info, token_id):
    """Port of RevokeCorpusAccessTokenMutation.mutate"""
    # @login_required — inlined.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    result = CorpusAccessTokenService.revoke_token(
        info.context.user, token_id, request=info.context
    )
    if not result.ok:
        raise GraphQLError(result.error)
    return payload_cls(ok=True)


def m_revoke_corpus_access_token(
    info: strawberry.Info,
    token_id: Annotated[int, strawberry.argument(name="tokenId")] = strawberry.UNSET,
) -> RevokeCorpusAccessTokenMutation | None:
    kwargs = strip_unset({"token_id": token_id})
    return _mutate_RevokeCorpusAccessTokenMutation(
        RevokeCorpusAccessTokenMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_worker_account": strawberry.field(
        resolver=m_create_worker_account,
        name="createWorkerAccount",
        description="Create a new worker service account. Superuser only.",
    ),
    "deactivate_worker_account": strawberry.field(
        resolver=m_deactivate_worker_account,
        name="deactivateWorkerAccount",
        description="Deactivate a worker account (revokes all its tokens implicitly). Superuser only.",
    ),
    "reactivate_worker_account": strawberry.field(
        resolver=m_reactivate_worker_account,
        name="reactivateWorkerAccount",
        description="Reactivate a previously deactivated worker account. Superuser only.",
    ),
    "create_corpus_access_token": strawberry.field(
        resolver=m_create_corpus_access_token,
        name="createCorpusAccessToken",
        description="Create a scoped access token granting a worker upload access to a corpus.\n\nReturns the full token key — it is only shown once.\nAllowed for superusers and the corpus creator.",
    ),
    "revoke_corpus_access_token": strawberry.field(
        resolver=m_revoke_corpus_access_token,
        name="revokeCorpusAccessToken",
        description="Revoke a corpus access token. Allowed for superusers and the corpus creator.",
    ),
}
