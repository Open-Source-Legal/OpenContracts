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
from typing import Annotated, cast

import strawberry
from graphql import GraphQLError

from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.worker_types import (
    CorpusAccessTokenQueryType,
    WorkerAccountQueryType,
    WorkerDocumentUploadPageType,
    WorkerDocumentUploadQueryType,
)
from opencontractserver.worker_uploads.services import (
    CorpusAccessTokenService,
    WorkerAccountService,
    WorkerDocumentUploadService,
)

logger = logging.getLogger(__name__)


@login_required
def _resolve_Query_worker_accounts(root, info, name_contains=None, is_active=None):
    """Port of WorkerQueryMixin.resolve_worker_accounts

    List worker accounts.

    Intentionally accessible to all authenticated users so that corpus
    creators can populate the worker-account dropdown when creating
    access tokens. The frontend gates the admin management page to
    superusers; non-superusers only see active accounts with
    ``tokenCount`` hidden (forced to 0).
    """
    user = info.context.user
    qs = WorkerAccountService.list_visible_accounts(
        user,
        name_contains=name_contains,
        is_active=is_active,
        request=info.context,
    )
    is_superuser = bool(getattr(user, "is_superuser", False))

    return [
        WorkerAccountQueryType(
            id=a.id,
            name=a.name,
            description=a.description,
            is_active=a.is_active,
            creator_name=a.creator.slug if a.creator else None,
            created=a.created,
            modified=a.modified,
            # ``_token_count`` is annotated by the service; zeroed for
            # non-superusers (sensitive — leaks per-account fan-out).
            token_count=a._token_count if is_superuser else 0,
        )
        for a in qs
    ]


def q_worker_accounts(
    info: strawberry.Info,
    name_contains: Annotated[
        str | None, strawberry.argument(name="nameContains")
    ] = strawberry.UNSET,
    is_active: Annotated[
        bool | None, strawberry.argument(name="isActive")
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (
            Annotated[
                WorkerAccountQueryType, strawberry.lazy("config.graphql.worker_types")
            ]
        )
    ]
):
    kwargs = strip_unset({"name_contains": name_contains, "is_active": is_active})
    return _resolve_Query_worker_accounts(None, info, **kwargs)


@login_required
def _resolve_Query_corpus_access_tokens(root, info, corpus_id, is_active=None):
    """Port of WorkerQueryMixin.resolve_corpus_access_tokens"""
    result = CorpusAccessTokenService.list_for_corpus(
        info.context.user,
        corpus_id,
        is_active=is_active,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)

    # ``result.ok`` invariant: success carries a non-None value. ``cast``
    # narrows the ``Optional`` for mypy without relying on ``assert``
    # (which is stripped under ``python -O``). The queryset is left
    # unparameterised because the service annotates ``_pending`` /
    # ``_completed`` / ``_failed`` dynamically — those are not fields on
    # the model, so a typed ``QuerySet[CorpusAccessToken]`` cast would
    # make the attribute access fail mypy.
    tokens = cast("QuerySet", result.value)
    return [
        CorpusAccessTokenQueryType(
            id=t.id,
            key_prefix=t.key_prefix,
            worker_account_id=t.worker_account_id,
            worker_account_name=t.worker_account.name,
            corpus_id=t.corpus_id,
            is_active=t.is_active,
            expires_at=t.expires_at,
            rate_limit_per_minute=t.rate_limit_per_minute,
            created=t.created,
            upload_count_pending=t._pending,
            upload_count_completed=t._completed,
            upload_count_failed=t._failed,
        )
        for t in tokens
    ]


def q_corpus_access_tokens(
    info: strawberry.Info,
    corpus_id: Annotated[int, strawberry.argument(name="corpusId")] = strawberry.UNSET,
    is_active: Annotated[
        bool | None, strawberry.argument(name="isActive")
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (
            Annotated[
                CorpusAccessTokenQueryType,
                strawberry.lazy("config.graphql.worker_types"),
            ]
        )
    ]
):
    kwargs = strip_unset({"corpus_id": corpus_id, "is_active": is_active})
    return _resolve_Query_corpus_access_tokens(None, info, **kwargs)


@login_required
def _resolve_Query_worker_document_uploads(
    root, info, corpus_id, status=None, limit=None, offset=None
):
    """Port of WorkerQueryMixin.resolve_worker_document_uploads"""
    result = WorkerDocumentUploadService.list_for_corpus(
        info.context.user,
        corpus_id,
        status=status,
        limit=limit,
        offset=offset,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)

    # ``result.ok`` invariant: success carries a non-None value. ``cast``
    # narrows the ``Optional`` for mypy without relying on ``assert``
    # (which is stripped under ``python -O``).
    page, total_count, effective_limit, effective_offset = cast(
        "tuple[QuerySet, int, int, int]", result.value
    )
    items = [
        WorkerDocumentUploadQueryType(
            id=str(u.id),
            corpus_id=u.corpus_id,
            status=u.status,
            error_message=u.error_message,
            result_document_id=u.result_document_id,
            created=u.created,
            processing_started=u.processing_started,
            processing_finished=u.processing_finished,
        )
        for u in page
    ]
    return WorkerDocumentUploadPageType(
        items=items,
        total_count=total_count,
        limit=effective_limit,
        offset=effective_offset,
    )


def q_worker_document_uploads(
    info: strawberry.Info,
    corpus_id: Annotated[int, strawberry.argument(name="corpusId")] = strawberry.UNSET,
    status: Annotated[
        str | None, strawberry.argument(name="status")
    ] = strawberry.UNSET,
    limit: Annotated[
        int | None,
        strawberry.argument(name="limit", description="Max results (default/max 100)"),
    ] = strawberry.UNSET,
    offset: Annotated[
        int | None,
        strawberry.argument(name="offset", description="Pagination offset"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        WorkerDocumentUploadPageType, strawberry.lazy("config.graphql.worker_types")
    ]
):
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "status": status, "limit": limit, "offset": offset}
    )
    return _resolve_Query_worker_document_uploads(None, info, **kwargs)


QUERY_FIELDS = {
    "worker_accounts": strawberry.field(
        resolver=q_worker_accounts,
        name="workerAccounts",
        description="List all worker accounts. Superuser only.",
    ),
    "corpus_access_tokens": strawberry.field(
        resolver=q_corpus_access_tokens,
        name="corpusAccessTokens",
        description="List access tokens for a corpus. Superuser or corpus creator.",
    ),
    "worker_document_uploads": strawberry.field(
        resolver=q_worker_document_uploads,
        name="workerDocumentUploads",
        description="List worker uploads for a corpus. Superuser or corpus creator.",
    ),
}
