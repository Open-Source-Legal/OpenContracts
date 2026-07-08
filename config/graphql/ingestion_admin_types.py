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


@strawberry.type(name="AdminDocumentIngestionPageType")
class AdminDocumentIngestionPageType:
    items: Optional[list["AdminDocumentIngestionType"]] = strawberry.field(
        name="items", default=None
    )
    total_count: Optional[int] = strawberry.field(
        name="totalCount",
        description="Total matching rows before pagination",
        default=None,
    )
    limit: Optional[int] = strawberry.field(name="limit", default=None)
    offset: Optional[int] = strawberry.field(name="offset", default=None)


register_type(
    "AdminDocumentIngestionPageType", AdminDocumentIngestionPageType, model=None
)


@strawberry.type(
    name="AdminDocumentIngestionType",
    description="A single document's parsing-pipeline status (content excluded).",
)
class AdminDocumentIngestionType:
    id: Optional[strawberry.ID] = strawberry.field(name="id", default=None)
    title: Optional[str] = strawberry.field(name="title", default=None)
    creator_username: Optional[str] = strawberry.field(
        name="creatorUsername", default=None
    )
    creator_email: Optional[str] = strawberry.field(name="creatorEmail", default=None)
    file_type: Optional[str] = strawberry.field(
        name="fileType", description="MIME type", default=None
    )
    page_count: Optional[int] = strawberry.field(name="pageCount", default=None)
    size_bytes: Optional[float] = strawberry.field(
        name="sizeBytes",
        description="Size of the stored source file in bytes",
        default=None,
    )
    processing_status: Optional[str] = strawberry.field(
        name="processingStatus",
        description="pending / processing / completed / failed",
        default=None,
    )
    processing_error: Optional[str] = strawberry.field(
        name="processingError",
        description="Error message if processing failed",
        default=None,
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
    elapsed_seconds: Optional[float] = strawberry.field(
        name="elapsedSeconds",
        description="Processing duration (finished-started, or now-started if still in flight); null if processing never started",
        default=None,
    )


register_type("AdminDocumentIngestionType", AdminDocumentIngestionType, model=None)


@strawberry.type(name="AdminWorkerUploadPageType")
class AdminWorkerUploadPageType:
    items: Optional[list["AdminWorkerUploadType"]] = strawberry.field(
        name="items", default=None
    )
    total_count: Optional[int] = strawberry.field(name="totalCount", default=None)
    limit: Optional[int] = strawberry.field(name="limit", default=None)
    offset: Optional[int] = strawberry.field(name="offset", default=None)


register_type("AdminWorkerUploadPageType", AdminWorkerUploadPageType, model=None)


@strawberry.type(
    name="AdminWorkerUploadType",
    description="A worker/pipeline upload staging row (content excluded).",
)
class AdminWorkerUploadType:
    id: Optional[str] = strawberry.field(
        name="id", description="UUID of the upload", default=None
    )
    corpus_id: Optional[int] = strawberry.field(name="corpusId", default=None)
    corpus_title: Optional[str] = strawberry.field(name="corpusTitle", default=None)
    worker_account_name: Optional[str] = strawberry.field(
        name="workerAccountName",
        description="Worker account behind the token used for this upload",
        default=None,
    )
    status: Optional[str] = strawberry.field(
        name="status",
        description="PENDING / PROCESSING / COMPLETED / FAILED",
        default=None,
    )
    error_message: Optional[str] = strawberry.field(name="errorMessage", default=None)
    file_name: Optional[str] = strawberry.field(name="fileName", default=None)
    size_bytes: Optional[float] = strawberry.field(
        name="sizeBytes", description="Size of the staged file in bytes", default=None
    )
    result_document_id: Optional[int] = strawberry.field(
        name="resultDocumentId",
        description="Document created on success, if any",
        default=None,
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
    elapsed_seconds: Optional[float] = strawberry.field(
        name="elapsedSeconds", default=None
    )


register_type("AdminWorkerUploadType", AdminWorkerUploadType, model=None)


@strawberry.type(name="AdminCorpusImportPageType")
class AdminCorpusImportPageType:
    items: Optional[list["AdminCorpusImportType"]] = strawberry.field(
        name="items", default=None
    )
    total_count: Optional[int] = strawberry.field(name="totalCount", default=None)
    limit: Optional[int] = strawberry.field(name="limit", default=None)
    offset: Optional[int] = strawberry.field(name="offset", default=None)


register_type("AdminCorpusImportPageType", AdminCorpusImportPageType, model=None)


@strawberry.type(
    name="AdminCorpusImportType",
    description="A corpus-export ZIP re-import run with per-document failure counts.",
)
class AdminCorpusImportType:
    id: Optional[strawberry.ID] = strawberry.field(
        name="id", description="PendingCorpusImport primary key", default=None
    )
    import_run_id: Optional[str] = strawberry.field(
        name="importRunId",
        description="UUID correlating the run's documents",
        default=None,
    )
    corpus_id: Optional[int] = strawberry.field(name="corpusId", default=None)
    corpus_title: Optional[str] = strawberry.field(name="corpusTitle", default=None)
    creator_username: Optional[str] = strawberry.field(
        name="creatorUsername", default=None
    )
    status: Optional[str] = strawberry.field(
        name="status",
        description="enumerating / ready / finalizing / done / failed",
        default=None,
    )
    expected_doc_count: Optional[int] = strawberry.field(
        name="expectedDocCount",
        description="Docs the run expected to create (observability; may be null)",
        default=None,
    )
    total_count_docs: Optional[int] = strawberry.field(
        name="totalCountDocs",
        description="Per-document outcome rows recorded for this run",
        default=None,
    )
    done_count: Optional[int] = strawberry.field(name="doneCount", default=None)
    failed_count: Optional[int] = strawberry.field(name="failedCount", default=None)
    pending_count: Optional[int] = strawberry.field(name="pendingCount", default=None)
    percent_failed: Optional[float] = strawberry.field(
        name="percentFailed",
        description="failed / total * 100 over recorded per-document rows",
        default=None,
    )
    created: Optional[datetime.datetime] = strawberry.field(
        name="created", description="When the run was enumerated", default=None
    )
    modified: Optional[datetime.datetime] = strawberry.field(
        name="modified", default=None
    )


register_type("AdminCorpusImportType", AdminCorpusImportType, model=None)


@strawberry.type(name="AdminBulkImportSessionPageType")
class AdminBulkImportSessionPageType:
    items: Optional[list["AdminBulkImportSessionType"]] = strawberry.field(
        name="items", default=None
    )
    total_count: Optional[int] = strawberry.field(name="totalCount", default=None)
    limit: Optional[int] = strawberry.field(name="limit", default=None)
    offset: Optional[int] = strawberry.field(name="offset", default=None)


register_type(
    "AdminBulkImportSessionPageType", AdminBulkImportSessionPageType, model=None
)


@strawberry.type(
    name="AdminBulkImportSessionType",
    description="A bulk document-zip import (chunked upload session; content excluded).",
)
class AdminBulkImportSessionType:
    id: Optional[str] = strawberry.field(
        name="id", description="UUID of the upload session", default=None
    )
    kind: Optional[str] = strawberry.field(
        name="kind", description="documents_zip / zip_to_corpus", default=None
    )
    filename: Optional[str] = strawberry.field(name="filename", default=None)
    creator_username: Optional[str] = strawberry.field(
        name="creatorUsername", default=None
    )
    status: Optional[str] = strawberry.field(
        name="status",
        description="PENDING / ASSEMBLING / COMPLETED / FAILED",
        default=None,
    )
    error_message: Optional[str] = strawberry.field(name="errorMessage", default=None)
    total_size: Optional[float] = strawberry.field(
        name="totalSize",
        description="Declared total assembled size in bytes",
        default=None,
    )
    received_size: Optional[float] = strawberry.field(
        name="receivedSize",
        description="Bytes received so far (0 once a completed session's parts are reclaimed)",
        default=None,
    )
    received_parts: Optional[int] = strawberry.field(name="receivedParts", default=None)
    total_chunks: Optional[int] = strawberry.field(name="totalChunks", default=None)
    percent_complete: Optional[float] = strawberry.field(
        name="percentComplete",
        description="Upload progress; 100 for COMPLETED sessions",
        default=None,
    )
    target_corpus_id: Optional[str] = strawberry.field(
        name="targetCorpusId",
        description="Target corpus id from the session metadata, if any",
        default=None,
    )
    created: Optional[datetime.datetime] = strawberry.field(
        name="created", default=None
    )
    modified: Optional[datetime.datetime] = strawberry.field(
        name="modified", default=None
    )


register_type("AdminBulkImportSessionType", AdminBulkImportSessionType, model=None)
