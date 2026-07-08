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
from typing import cast

from graphql import GraphQLError

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


def q_worker_accounts(info: strawberry.Info, name_contains: Annotated[Optional[str], strawberry.argument(name="nameContains")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["WorkerAccountQueryType", strawberry.lazy("config.graphql.worker_types")]]]]:
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


def q_corpus_access_tokens(info: strawberry.Info, corpus_id: Annotated[int, strawberry.argument(name="corpusId")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["CorpusAccessTokenQueryType", strawberry.lazy("config.graphql.worker_types")]]]]:
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


def q_worker_document_uploads(info: strawberry.Info, corpus_id: Annotated[int, strawberry.argument(name="corpusId")] = strawberry.UNSET, status: Annotated[Optional[str], strawberry.argument(name="status")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit", description='Max results (default/max 100)')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset", description='Pagination offset')] = strawberry.UNSET) -> Optional[Annotated["WorkerDocumentUploadPageType", strawberry.lazy("config.graphql.worker_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "status": status, "limit": limit, "offset": offset})
    return _resolve_Query_worker_document_uploads(None, info, **kwargs)



QUERY_FIELDS = {
    "worker_accounts": strawberry.field(resolver=q_worker_accounts, name="workerAccounts", description='List all worker accounts. Superuser only.'),
    "corpus_access_tokens": strawberry.field(resolver=q_corpus_access_tokens, name="corpusAccessTokens", description='List access tokens for a corpus. Superuser or corpus creator.'),
    "worker_document_uploads": strawberry.field(resolver=q_worker_document_uploads, name="workerDocumentUploads", description='List worker uploads for a corpus. Superuser or corpus creator.'),
}
