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




@strawberry.type(name="AdminDocumentIngestionPageType")
class AdminDocumentIngestionPageType:
    @strawberry.field(name="items")
    def items(self, info: strawberry.Info) -> Optional[list["AdminDocumentIngestionType"]]:
        return resolve_django_list(self, info, getattr(self, "items"), "AdminDocumentIngestionType")
    total_count: Optional[int] = strawberry.field(name="totalCount", description='Total matching rows before pagination')
    limit: Optional[int] = strawberry.field(name="limit")
    offset: Optional[int] = strawberry.field(name="offset")


register_type("AdminDocumentIngestionPageType", AdminDocumentIngestionPageType, model=None)


@strawberry.type(name="AdminDocumentIngestionType", description="A single document's parsing-pipeline status (content excluded).")
class AdminDocumentIngestionType:
    @strawberry.field(name="id")
    def id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "id", None))
    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="creatorUsername")
    def creator_username(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_username", None))
    @strawberry.field(name="creatorEmail")
    def creator_email(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_email", None))
    @strawberry.field(name="fileType", description='MIME type')
    def file_type(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "file_type", None))
    page_count: Optional[int] = strawberry.field(name="pageCount")
    size_bytes: Optional[float] = strawberry.field(name="sizeBytes", description='Size of the stored source file in bytes')
    @strawberry.field(name="processingStatus", description='pending / processing / completed / failed')
    def processing_status(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "processing_status", None))
    @strawberry.field(name="processingError", description='Error message if processing failed')
    def processing_error(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "processing_error", None))
    created: Optional[datetime.datetime] = strawberry.field(name="created")
    processing_started: Optional[datetime.datetime] = strawberry.field(name="processingStarted")
    processing_finished: Optional[datetime.datetime] = strawberry.field(name="processingFinished")
    elapsed_seconds: Optional[float] = strawberry.field(name="elapsedSeconds", description='Processing duration (finished-started, or now-started if still in flight); null if processing never started')


register_type("AdminDocumentIngestionType", AdminDocumentIngestionType, model=None)


@strawberry.type(name="AdminWorkerUploadPageType")
class AdminWorkerUploadPageType:
    @strawberry.field(name="items")
    def items(self, info: strawberry.Info) -> Optional[list["AdminWorkerUploadType"]]:
        return resolve_django_list(self, info, getattr(self, "items"), "AdminWorkerUploadType")
    total_count: Optional[int] = strawberry.field(name="totalCount")
    limit: Optional[int] = strawberry.field(name="limit")
    offset: Optional[int] = strawberry.field(name="offset")


register_type("AdminWorkerUploadPageType", AdminWorkerUploadPageType, model=None)


@strawberry.type(name="AdminWorkerUploadType", description='A worker/pipeline upload staging row (content excluded).')
class AdminWorkerUploadType:
    @strawberry.field(name="id", description='UUID of the upload')
    def id(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "id", None))
    corpus_id: Optional[int] = strawberry.field(name="corpusId")
    @strawberry.field(name="corpusTitle")
    def corpus_title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "corpus_title", None))
    @strawberry.field(name="workerAccountName", description='Worker account behind the token used for this upload')
    def worker_account_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "worker_account_name", None))
    @strawberry.field(name="status", description='PENDING / PROCESSING / COMPLETED / FAILED')
    def status(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "status", None))
    @strawberry.field(name="errorMessage")
    def error_message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "error_message", None))
    @strawberry.field(name="fileName")
    def file_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "file_name", None))
    size_bytes: Optional[float] = strawberry.field(name="sizeBytes", description='Size of the staged file in bytes')
    result_document_id: Optional[int] = strawberry.field(name="resultDocumentId", description='Document created on success, if any')
    created: Optional[datetime.datetime] = strawberry.field(name="created")
    processing_started: Optional[datetime.datetime] = strawberry.field(name="processingStarted")
    processing_finished: Optional[datetime.datetime] = strawberry.field(name="processingFinished")
    elapsed_seconds: Optional[float] = strawberry.field(name="elapsedSeconds")


register_type("AdminWorkerUploadType", AdminWorkerUploadType, model=None)


@strawberry.type(name="AdminCorpusImportPageType")
class AdminCorpusImportPageType:
    @strawberry.field(name="items")
    def items(self, info: strawberry.Info) -> Optional[list["AdminCorpusImportType"]]:
        return resolve_django_list(self, info, getattr(self, "items"), "AdminCorpusImportType")
    total_count: Optional[int] = strawberry.field(name="totalCount")
    limit: Optional[int] = strawberry.field(name="limit")
    offset: Optional[int] = strawberry.field(name="offset")


register_type("AdminCorpusImportPageType", AdminCorpusImportPageType, model=None)


@strawberry.type(name="AdminCorpusImportType", description='A corpus-export ZIP re-import run with per-document failure counts.')
class AdminCorpusImportType:
    @strawberry.field(name="id", description='PendingCorpusImport primary key')
    def id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "id", None))
    @strawberry.field(name="importRunId", description="UUID correlating the run's documents")
    def import_run_id(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "import_run_id", None))
    corpus_id: Optional[int] = strawberry.field(name="corpusId")
    @strawberry.field(name="corpusTitle")
    def corpus_title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "corpus_title", None))
    @strawberry.field(name="creatorUsername")
    def creator_username(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_username", None))
    @strawberry.field(name="status", description='enumerating / ready / finalizing / done / failed')
    def status(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "status", None))
    expected_doc_count: Optional[int] = strawberry.field(name="expectedDocCount", description='Docs the run expected to create (observability; may be null)')
    total_count_docs: Optional[int] = strawberry.field(name="totalCountDocs", description='Per-document outcome rows recorded for this run')
    done_count: Optional[int] = strawberry.field(name="doneCount")
    failed_count: Optional[int] = strawberry.field(name="failedCount")
    pending_count: Optional[int] = strawberry.field(name="pendingCount")
    percent_failed: Optional[float] = strawberry.field(name="percentFailed", description='failed / total * 100 over recorded per-document rows')
    created: Optional[datetime.datetime] = strawberry.field(name="created", description='When the run was enumerated')
    modified: Optional[datetime.datetime] = strawberry.field(name="modified")


register_type("AdminCorpusImportType", AdminCorpusImportType, model=None)


@strawberry.type(name="AdminBulkImportSessionPageType")
class AdminBulkImportSessionPageType:
    @strawberry.field(name="items")
    def items(self, info: strawberry.Info) -> Optional[list["AdminBulkImportSessionType"]]:
        return resolve_django_list(self, info, getattr(self, "items"), "AdminBulkImportSessionType")
    total_count: Optional[int] = strawberry.field(name="totalCount")
    limit: Optional[int] = strawberry.field(name="limit")
    offset: Optional[int] = strawberry.field(name="offset")


register_type("AdminBulkImportSessionPageType", AdminBulkImportSessionPageType, model=None)


@strawberry.type(name="AdminBulkImportSessionType", description='A bulk document-zip import (chunked upload session; content excluded).')
class AdminBulkImportSessionType:
    @strawberry.field(name="id", description='UUID of the upload session')
    def id(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "id", None))
    @strawberry.field(name="kind", description='documents_zip / zip_to_corpus')
    def kind(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "kind", None))
    @strawberry.field(name="filename")
    def filename(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "filename", None))
    @strawberry.field(name="creatorUsername")
    def creator_username(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_username", None))
    @strawberry.field(name="status", description='PENDING / ASSEMBLING / COMPLETED / FAILED')
    def status(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "status", None))
    @strawberry.field(name="errorMessage")
    def error_message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "error_message", None))
    total_size: Optional[float] = strawberry.field(name="totalSize", description='Declared total assembled size in bytes')
    received_size: Optional[float] = strawberry.field(name="receivedSize", description="Bytes received so far (0 once a completed session's parts are reclaimed)")
    received_parts: Optional[int] = strawberry.field(name="receivedParts")
    total_chunks: Optional[int] = strawberry.field(name="totalChunks")
    percent_complete: Optional[float] = strawberry.field(name="percentComplete", description='Upload progress; 100 for COMPLETED sessions')
    @strawberry.field(name="targetCorpusId", description='Target corpus id from the session metadata, if any')
    def target_corpus_id(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "target_corpus_id", None))
    created: Optional[datetime.datetime] = strawberry.field(name="created")
    modified: Optional[datetime.datetime] = strawberry.field(name="modified")


register_type("AdminBulkImportSessionType", AdminBulkImportSessionType, model=None)

