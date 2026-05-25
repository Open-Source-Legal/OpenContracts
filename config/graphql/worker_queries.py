"""
GraphQL query mixin for worker upload management queries.

All permission and queryset-shape logic lives in the
:mod:`opencontractserver.worker_uploads.services` package; the resolvers
project service results onto the GraphQL output types.
"""

import logging
from typing import TYPE_CHECKING, Any, cast

import graphene
from graphql import GraphQLError
from graphql_jwt.decorators import login_required

from config.graphql.worker_types import (
    CorpusAccessTokenQueryType,
    WorkerAccountQueryType,
    WorkerDocumentUploadPageType,
    WorkerDocumentUploadQueryType,
)
from opencontractserver.constants.document_processing import WORKER_UPLOADS_QUERY_LIMIT
from opencontractserver.worker_uploads.services import (
    CorpusAccessTokenService,
    WorkerAccountService,
    WorkerDocumentUploadService,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


class WorkerQueryMixin:
    """Query fields and resolvers for worker upload management."""

    worker_accounts = graphene.List(
        WorkerAccountQueryType,
        name_contains=graphene.String(required=False),
        is_active=graphene.Boolean(required=False),
        description="List all worker accounts. Superuser only.",
    )

    corpus_access_tokens = graphene.List(
        CorpusAccessTokenQueryType,
        corpus_id=graphene.Int(required=True),
        is_active=graphene.Boolean(required=False),
        description="List access tokens for a corpus. Superuser or corpus creator.",
    )

    worker_document_uploads = graphene.Field(
        WorkerDocumentUploadPageType,
        corpus_id=graphene.Int(required=True),
        status=graphene.String(required=False),
        limit=graphene.Int(
            required=False,
            description=f"Max results (default/max {WORKER_UPLOADS_QUERY_LIMIT})",
        ),
        offset=graphene.Int(required=False, description="Pagination offset"),
        description="List worker uploads for a corpus. Superuser or corpus creator.",
    )

    @login_required
    def resolve_worker_accounts(self, info, name_contains=None, is_active=None) -> Any:
        """List worker accounts.

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

    @login_required
    def resolve_corpus_access_tokens(self, info, corpus_id, is_active=None) -> Any:
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

    @login_required
    def resolve_worker_document_uploads(
        self, info, corpus_id, status=None, limit=None, offset=None
    ) -> Any:
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
