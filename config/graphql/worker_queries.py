"""
GraphQL query mixin for worker upload management queries.
"""

import logging
from typing import Any

import graphene
from django.db.models import Count, Q
from graphql import GraphQLError
from graphql_jwt.decorators import login_required

from config.graphql.worker_types import (
    CorpusAccessTokenQueryType,
    WorkerAccountQueryType,
    WorkerDocumentUploadPageType,
    WorkerDocumentUploadQueryType,
)
from opencontractserver.constants.document_processing import WORKER_UPLOADS_QUERY_LIMIT
from opencontractserver.corpuses.models import Corpus
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    WorkerAccount,
    WorkerDocumentUpload,
)

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
        access tokens.  The frontend gates the admin management page to
        superusers; non-superusers only see active accounts with
        tokenCount hidden (forced to 0).
        """
        user = info.context.user

        qs = WorkerAccount.objects.select_related("creator").order_by("-created")

        # Non-superusers see only active accounts (for the token-creation dropdown).
        # Sensitive fields (tokenCount) are zeroed out below.
        if not user.is_superuser:
            qs = qs.filter(is_active=True)
        else:
            if is_active is not None:
                qs = qs.filter(is_active=is_active)

        qs = qs.annotate(_token_count=Count("access_tokens"))

        if name_contains:
            qs = qs.filter(name__icontains=name_contains)

        return [
            WorkerAccountQueryType(
                id=a.id,
                name=a.name,
                description=a.description,
                is_active=a.is_active,
                creator_name=a.creator.slug if a.creator else None,
                created=a.created,
                modified=a.modified,
                token_count=a._token_count if user.is_superuser else 0,
            )
            for a in qs
        ]

    @login_required
    def resolve_corpus_access_tokens(self, info, corpus_id, is_active=None) -> Any:
        user = info.context.user
        qs = Corpus.objects.filter(id=corpus_id)
        if not user.is_superuser:
            qs = qs.filter(creator=user)
        corpus = qs.first()
        if corpus is None:
            raise GraphQLError("Not found or permission denied.")

        qs = (
            CorpusAccessToken.objects.filter(corpus=corpus)
            .select_related("worker_account")
            .order_by("-created")
        )
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        qs = qs.annotate(
            _pending=Count("uploads", filter=Q(uploads__status="PENDING")),
            _completed=Count("uploads", filter=Q(uploads__status="COMPLETED")),
            _failed=Count("uploads", filter=Q(uploads__status="FAILED")),
        )

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
            for t in qs
        ]

    @login_required
    def resolve_worker_document_uploads(
        self, info, corpus_id, status=None, limit=None, offset=None
    ) -> Any:
        user = info.context.user
        qs = Corpus.objects.filter(id=corpus_id)
        if not user.is_superuser:
            qs = qs.filter(creator=user)
        corpus = qs.first()
        if corpus is None:
            raise GraphQLError("Not found or permission denied.")

        qs = WorkerDocumentUpload.objects.filter(corpus=corpus).order_by("-created")
        if status:
            qs = qs.filter(status=status.upper())

        total_count = qs.count()

        effective_limit = min(
            limit or WORKER_UPLOADS_QUERY_LIMIT, WORKER_UPLOADS_QUERY_LIMIT
        )
        effective_offset = max(offset or 0, 0)
        page = qs[effective_offset : effective_offset + effective_limit]

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
