"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

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
from typing import Optional

import strawberry

from config.graphql.core.relay import (
    register_type,
)


@strawberry.type(
    name="WorkerAccountQueryType",
    description="Worker account with computed fields for listing.",
)
class WorkerAccountQueryType:
    id: Optional[int] = strawberry.field(name="id", default=None)
    name: Optional[str] = strawberry.field(name="name", default=None)
    description: Optional[str] = strawberry.field(name="description", default=None)
    is_active: Optional[bool] = strawberry.field(name="isActive", default=None)
    creator_name: Optional[str] = strawberry.field(name="creatorName", default=None)
    created: Optional[datetime.datetime] = strawberry.field(
        name="created", default=None
    )
    modified: Optional[datetime.datetime] = strawberry.field(
        name="modified", default=None
    )
    token_count: Optional[int] = strawberry.field(
        name="tokenCount",
        description="Number of access tokens for this account",
        default=None,
    )


register_type("WorkerAccountQueryType", WorkerAccountQueryType, model=None)


@strawberry.type(
    name="CorpusAccessTokenQueryType",
    description="Corpus access token for listing. Never exposes the hashed key.",
)
class CorpusAccessTokenQueryType:
    id: Optional[int] = strawberry.field(name="id", default=None)
    key_prefix: Optional[str] = strawberry.field(
        name="keyPrefix",
        description="First 8 characters of the original token",
        default=None,
    )
    worker_account_id: Optional[int] = strawberry.field(
        name="workerAccountId", default=None
    )
    worker_account_name: Optional[str] = strawberry.field(
        name="workerAccountName", default=None
    )
    corpus_id: Optional[int] = strawberry.field(name="corpusId", default=None)
    is_active: Optional[bool] = strawberry.field(name="isActive", default=None)
    expires_at: Optional[datetime.datetime] = strawberry.field(
        name="expiresAt", default=None
    )
    rate_limit_per_minute: Optional[int] = strawberry.field(
        name="rateLimitPerMinute", default=None
    )
    created: Optional[datetime.datetime] = strawberry.field(
        name="created", default=None
    )
    upload_count_pending: Optional[int] = strawberry.field(
        name="uploadCountPending", default=None
    )
    upload_count_completed: Optional[int] = strawberry.field(
        name="uploadCountCompleted", default=None
    )
    upload_count_failed: Optional[int] = strawberry.field(
        name="uploadCountFailed", default=None
    )


register_type("CorpusAccessTokenQueryType", CorpusAccessTokenQueryType, model=None)


@strawberry.type(
    name="WorkerDocumentUploadPageType",
    description="Paginated wrapper for worker document uploads.",
)
class WorkerDocumentUploadPageType:
    items: Optional[list["WorkerDocumentUploadQueryType"]] = strawberry.field(
        name="items", default=None
    )
    total_count: Optional[int] = strawberry.field(
        name="totalCount",
        description="Total matching uploads before pagination",
        default=None,
    )
    limit: Optional[int] = strawberry.field(
        name="limit", description="Max items returned", default=None
    )
    offset: Optional[int] = strawberry.field(
        name="offset", description="Items skipped", default=None
    )


register_type("WorkerDocumentUploadPageType", WorkerDocumentUploadPageType, model=None)


@strawberry.type(
    name="WorkerDocumentUploadQueryType",
    description="Worker document upload for listing.",
)
class WorkerDocumentUploadQueryType:
    id: Optional[str] = strawberry.field(
        name="id", description="UUID of the upload", default=None
    )
    corpus_id: Optional[int] = strawberry.field(name="corpusId", default=None)
    status: Optional[str] = strawberry.field(name="status", default=None)
    error_message: Optional[str] = strawberry.field(name="errorMessage", default=None)
    result_document_id: Optional[int] = strawberry.field(
        name="resultDocumentId", default=None
    )
    created: Optional[datetime.datetime] = strawberry.field(
        name="created", default=None
    )
    processing_started: Optional[datetime.datetime] = strawberry.field(
        name="processingStarted", default=None
    )
    processing_finished: Optional[datetime.datetime] = strawberry.field(
        name="processingFinished", default=None
    )


register_type(
    "WorkerDocumentUploadQueryType", WorkerDocumentUploadQueryType, model=None
)


@strawberry.type(name="WorkerAccountType")
class WorkerAccountType:
    id: Optional[int] = strawberry.field(name="id", default=None)
    name: Optional[str] = strawberry.field(name="name", default=None)
    description: Optional[str] = strawberry.field(name="description", default=None)
    is_active: Optional[bool] = strawberry.field(name="isActive", default=None)
    created: Optional[datetime.datetime] = strawberry.field(
        name="created", default=None
    )


register_type("WorkerAccountType", WorkerAccountType, model=None)


@strawberry.type(
    name="CorpusAccessTokenCreatedType",
    description="Returned only on token creation — includes the full key.",
)
class CorpusAccessTokenCreatedType:
    id: Optional[int] = strawberry.field(name="id", default=None)
    key: Optional[str] = strawberry.field(
        name="key",
        description="Full token key. Store securely — shown only once.",
        default=None,
    )
    worker_account_name: Optional[str] = strawberry.field(
        name="workerAccountName", default=None
    )
    corpus_id: Optional[int] = strawberry.field(name="corpusId", default=None)
    expires_at: Optional[datetime.datetime] = strawberry.field(
        name="expiresAt", default=None
    )
    rate_limit_per_minute: Optional[int] = strawberry.field(
        name="rateLimitPerMinute", default=None
    )
    created: Optional[datetime.datetime] = strawberry.field(
        name="created", default=None
    )


register_type("CorpusAccessTokenCreatedType", CorpusAccessTokenCreatedType, model=None)
