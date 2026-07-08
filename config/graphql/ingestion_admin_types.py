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

import strawberry

from config.graphql.core.relay import (
    register_type,
)


@strawberry.type(name="AdminDocumentIngestionPageType")
class AdminDocumentIngestionPageType:
    items: list[AdminDocumentIngestionType] | None = strawberry.field(
        name="items", default=None
    )
    total_count: int | None = strawberry.field(
        name="totalCount",
        description="Total matching rows before pagination",
        default=None,
    )
    limit: int | None = strawberry.field(name="limit", default=None)
    offset: int | None = strawberry.field(name="offset", default=None)


register_type(
    "AdminDocumentIngestionPageType", AdminDocumentIngestionPageType, model=None
)


@strawberry.type(
    name="AdminDocumentIngestionType",
    description="A single document's parsing-pipeline status (content excluded).",
)
class AdminDocumentIngestionType:
    id: strawberry.ID | None = strawberry.field(name="id", default=None)
    title: str | None = strawberry.field(name="title", default=None)
    creator_username: str | None = strawberry.field(
        name="creatorUsername", default=None
    )
    creator_email: str | None = strawberry.field(name="creatorEmail", default=None)
    file_type: str | None = strawberry.field(
        name="fileType", description="MIME type", default=None
    )
    page_count: int | None = strawberry.field(name="pageCount", default=None)
    size_bytes: float | None = strawberry.field(
        name="sizeBytes",
        description="Size of the stored source file in bytes",
        default=None,
    )
    processing_status: str | None = strawberry.field(
        name="processingStatus",
        description="pending / processing / completed / failed",
        default=None,
    )
    processing_error: str | None = strawberry.field(
        name="processingError",
        description="Error message if processing failed",
        default=None,
    )
    created: datetime.datetime | None = strawberry.field(name="created", default=None)
    processing_started: datetime.datetime | None = strawberry.field(
        name="processingStarted", default=None
    )
    processing_finished: datetime.datetime | None = strawberry.field(
        name="processingFinished", default=None
    )
    elapsed_seconds: float | None = strawberry.field(
        name="elapsedSeconds",
        description="Processing duration (finished-started, or now-started if still in flight); null if processing never started",
        default=None,
    )


register_type("AdminDocumentIngestionType", AdminDocumentIngestionType, model=None)


@strawberry.type(name="AdminWorkerUploadPageType")
class AdminWorkerUploadPageType:
    items: list[AdminWorkerUploadType] | None = strawberry.field(
        name="items", default=None
    )
    total_count: int | None = strawberry.field(name="totalCount", default=None)
    limit: int | None = strawberry.field(name="limit", default=None)
    offset: int | None = strawberry.field(name="offset", default=None)


register_type("AdminWorkerUploadPageType", AdminWorkerUploadPageType, model=None)


@strawberry.type(
    name="AdminWorkerUploadType",
    description="A worker/pipeline upload staging row (content excluded).",
)
class AdminWorkerUploadType:
    id: str | None = strawberry.field(
        name="id", description="UUID of the upload", default=None
    )
    corpus_id: int | None = strawberry.field(name="corpusId", default=None)
    corpus_title: str | None = strawberry.field(name="corpusTitle", default=None)
    worker_account_name: str | None = strawberry.field(
        name="workerAccountName",
        description="Worker account behind the token used for this upload",
        default=None,
    )
    status: str | None = strawberry.field(
        name="status",
        description="PENDING / PROCESSING / COMPLETED / FAILED",
        default=None,
    )
    error_message: str | None = strawberry.field(name="errorMessage", default=None)
    file_name: str | None = strawberry.field(name="fileName", default=None)
    size_bytes: float | None = strawberry.field(
        name="sizeBytes", description="Size of the staged file in bytes", default=None
    )
    result_document_id: int | None = strawberry.field(
        name="resultDocumentId",
        description="Document created on success, if any",
        default=None,
    )
    created: datetime.datetime | None = strawberry.field(name="created", default=None)
    processing_started: datetime.datetime | None = strawberry.field(
        name="processingStarted", default=None
    )
    processing_finished: datetime.datetime | None = strawberry.field(
        name="processingFinished", default=None
    )
    elapsed_seconds: float | None = strawberry.field(
        name="elapsedSeconds", default=None
    )


register_type("AdminWorkerUploadType", AdminWorkerUploadType, model=None)


@strawberry.type(name="AdminCorpusImportPageType")
class AdminCorpusImportPageType:
    items: list[AdminCorpusImportType] | None = strawberry.field(
        name="items", default=None
    )
    total_count: int | None = strawberry.field(name="totalCount", default=None)
    limit: int | None = strawberry.field(name="limit", default=None)
    offset: int | None = strawberry.field(name="offset", default=None)


register_type("AdminCorpusImportPageType", AdminCorpusImportPageType, model=None)


@strawberry.type(
    name="AdminCorpusImportType",
    description="A corpus-export ZIP re-import run with per-document failure counts.",
)
class AdminCorpusImportType:
    id: strawberry.ID | None = strawberry.field(
        name="id", description="PendingCorpusImport primary key", default=None
    )
    import_run_id: str | None = strawberry.field(
        name="importRunId",
        description="UUID correlating the run's documents",
        default=None,
    )
    corpus_id: int | None = strawberry.field(name="corpusId", default=None)
    corpus_title: str | None = strawberry.field(name="corpusTitle", default=None)
    creator_username: str | None = strawberry.field(
        name="creatorUsername", default=None
    )
    status: str | None = strawberry.field(
        name="status",
        description="enumerating / ready / finalizing / done / failed",
        default=None,
    )
    expected_doc_count: int | None = strawberry.field(
        name="expectedDocCount",
        description="Docs the run expected to create (observability; may be null)",
        default=None,
    )
    total_count_docs: int | None = strawberry.field(
        name="totalCountDocs",
        description="Per-document outcome rows recorded for this run",
        default=None,
    )
    done_count: int | None = strawberry.field(name="doneCount", default=None)
    failed_count: int | None = strawberry.field(name="failedCount", default=None)
    pending_count: int | None = strawberry.field(name="pendingCount", default=None)
    percent_failed: float | None = strawberry.field(
        name="percentFailed",
        description="failed / total * 100 over recorded per-document rows",
        default=None,
    )
    created: datetime.datetime | None = strawberry.field(
        name="created", description="When the run was enumerated", default=None
    )
    modified: datetime.datetime | None = strawberry.field(name="modified", default=None)


register_type("AdminCorpusImportType", AdminCorpusImportType, model=None)


@strawberry.type(name="AdminBulkImportSessionPageType")
class AdminBulkImportSessionPageType:
    items: list[AdminBulkImportSessionType] | None = strawberry.field(
        name="items", default=None
    )
    total_count: int | None = strawberry.field(name="totalCount", default=None)
    limit: int | None = strawberry.field(name="limit", default=None)
    offset: int | None = strawberry.field(name="offset", default=None)


register_type(
    "AdminBulkImportSessionPageType", AdminBulkImportSessionPageType, model=None
)


@strawberry.type(
    name="AdminBulkImportSessionType",
    description="A bulk document-zip import (chunked upload session; content excluded).",
)
class AdminBulkImportSessionType:
    id: str | None = strawberry.field(
        name="id", description="UUID of the upload session", default=None
    )
    kind: str | None = strawberry.field(
        name="kind", description="documents_zip / zip_to_corpus", default=None
    )
    filename: str | None = strawberry.field(name="filename", default=None)
    creator_username: str | None = strawberry.field(
        name="creatorUsername", default=None
    )
    status: str | None = strawberry.field(
        name="status",
        description="PENDING / ASSEMBLING / COMPLETED / FAILED",
        default=None,
    )
    error_message: str | None = strawberry.field(name="errorMessage", default=None)
    total_size: float | None = strawberry.field(
        name="totalSize",
        description="Declared total assembled size in bytes",
        default=None,
    )
    received_size: float | None = strawberry.field(
        name="receivedSize",
        description="Bytes received so far (0 once a completed session's parts are reclaimed)",
        default=None,
    )
    received_parts: int | None = strawberry.field(name="receivedParts", default=None)
    total_chunks: int | None = strawberry.field(name="totalChunks", default=None)
    percent_complete: float | None = strawberry.field(
        name="percentComplete",
        description="Upload progress; 100 for COMPLETED sessions",
        default=None,
    )
    target_corpus_id: str | None = strawberry.field(
        name="targetCorpusId",
        description="Target corpus id from the session metadata, if any",
        default=None,
    )
    created: datetime.datetime | None = strawberry.field(name="created", default=None)
    modified: datetime.datetime | None = strawberry.field(name="modified", default=None)


register_type("AdminBulkImportSessionType", AdminBulkImportSessionType, model=None)
