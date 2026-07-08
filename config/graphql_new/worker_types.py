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




@strawberry.type(name="WorkerAccountQueryType", description='Worker account with computed fields for listing.')
class WorkerAccountQueryType:
    id: Optional[int] = strawberry.field(name="id")
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "description", None))
    is_active: Optional[bool] = strawberry.field(name="isActive")
    @strawberry.field(name="creatorName")
    def creator_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_name", None))
    created: Optional[datetime.datetime] = strawberry.field(name="created")
    modified: Optional[datetime.datetime] = strawberry.field(name="modified")
    token_count: Optional[int] = strawberry.field(name="tokenCount", description='Number of access tokens for this account')


register_type("WorkerAccountQueryType", WorkerAccountQueryType, model=None)


@strawberry.type(name="CorpusAccessTokenQueryType", description='Corpus access token for listing. Never exposes the hashed key.')
class CorpusAccessTokenQueryType:
    id: Optional[int] = strawberry.field(name="id")
    @strawberry.field(name="keyPrefix", description='First 8 characters of the original token')
    def key_prefix(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "key_prefix", None))
    worker_account_id: Optional[int] = strawberry.field(name="workerAccountId")
    @strawberry.field(name="workerAccountName")
    def worker_account_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "worker_account_name", None))
    corpus_id: Optional[int] = strawberry.field(name="corpusId")
    is_active: Optional[bool] = strawberry.field(name="isActive")
    expires_at: Optional[datetime.datetime] = strawberry.field(name="expiresAt")
    rate_limit_per_minute: Optional[int] = strawberry.field(name="rateLimitPerMinute")
    created: Optional[datetime.datetime] = strawberry.field(name="created")
    upload_count_pending: Optional[int] = strawberry.field(name="uploadCountPending")
    upload_count_completed: Optional[int] = strawberry.field(name="uploadCountCompleted")
    upload_count_failed: Optional[int] = strawberry.field(name="uploadCountFailed")


register_type("CorpusAccessTokenQueryType", CorpusAccessTokenQueryType, model=None)


@strawberry.type(name="WorkerDocumentUploadPageType", description='Paginated wrapper for worker document uploads.')
class WorkerDocumentUploadPageType:
    @strawberry.field(name="items")
    def items(self, info: strawberry.Info) -> Optional[list["WorkerDocumentUploadQueryType"]]:
        return resolve_django_list(self, info, getattr(self, "items"), "WorkerDocumentUploadQueryType")
    total_count: Optional[int] = strawberry.field(name="totalCount", description='Total matching uploads before pagination')
    limit: Optional[int] = strawberry.field(name="limit", description='Max items returned')
    offset: Optional[int] = strawberry.field(name="offset", description='Items skipped')


register_type("WorkerDocumentUploadPageType", WorkerDocumentUploadPageType, model=None)


@strawberry.type(name="WorkerDocumentUploadQueryType", description='Worker document upload for listing.')
class WorkerDocumentUploadQueryType:
    @strawberry.field(name="id", description='UUID of the upload')
    def id(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "id", None))
    corpus_id: Optional[int] = strawberry.field(name="corpusId")
    @strawberry.field(name="status")
    def status(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "status", None))
    @strawberry.field(name="errorMessage")
    def error_message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "error_message", None))
    result_document_id: Optional[int] = strawberry.field(name="resultDocumentId")
    created: Optional[datetime.datetime] = strawberry.field(name="created")
    processing_started: Optional[datetime.datetime] = strawberry.field(name="processingStarted")
    processing_finished: Optional[datetime.datetime] = strawberry.field(name="processingFinished")


register_type("WorkerDocumentUploadQueryType", WorkerDocumentUploadQueryType, model=None)


@strawberry.type(name="WorkerAccountType")
class WorkerAccountType:
    id: Optional[int] = strawberry.field(name="id")
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "description", None))
    is_active: Optional[bool] = strawberry.field(name="isActive")
    created: Optional[datetime.datetime] = strawberry.field(name="created")


register_type("WorkerAccountType", WorkerAccountType, model=None)


@strawberry.type(name="CorpusAccessTokenCreatedType", description='Returned only on token creation — includes the full key.')
class CorpusAccessTokenCreatedType:
    id: Optional[int] = strawberry.field(name="id")
    @strawberry.field(name="key", description='Full token key. Store securely — shown only once.')
    def key(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "key", None))
    @strawberry.field(name="workerAccountName")
    def worker_account_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "worker_account_name", None))
    corpus_id: Optional[int] = strawberry.field(name="corpusId")
    expires_at: Optional[datetime.datetime] = strawberry.field(name="expiresAt")
    rate_limit_per_minute: Optional[int] = strawberry.field(name="rateLimitPerMinute")
    created: Optional[datetime.datetime] = strawberry.field(name="created")


register_type("CorpusAccessTokenCreatedType", CorpusAccessTokenCreatedType, model=None)

