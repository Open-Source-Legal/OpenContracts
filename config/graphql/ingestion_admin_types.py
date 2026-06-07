"""GraphQL projection types for the superuser ingestion-monitor dashboard.

All read-only ``graphene.ObjectType`` projections built by the resolvers in
``config/graphql/ingestion_admin_queries.py`` from service-layer results.

Byte sizes and ``elapsed_seconds`` are ``graphene.Float`` (not ``Int``): a
GraphQL ``Int`` is a signed 32-bit value, but document/upload sizes can exceed
2 GiB, so ``Int`` would overflow. ``Float`` represents integers exactly up to
2**53, which comfortably covers any realistic file size.
"""

import graphene


class AdminDocumentIngestionType(graphene.ObjectType):
    """A single document's parsing-pipeline status (content excluded)."""

    id = graphene.ID()
    title = graphene.String()
    creator_username = graphene.String()
    creator_email = graphene.String()
    file_type = graphene.String(description="MIME type")
    page_count = graphene.Int()
    size_bytes = graphene.Float(description="Size of the stored source file in bytes")
    processing_status = graphene.String(
        description="pending / processing / completed / failed"
    )
    processing_error = graphene.String(description="Error message if processing failed")
    created = graphene.DateTime()
    processing_started = graphene.DateTime()
    processing_finished = graphene.DateTime()
    elapsed_seconds = graphene.Float(
        description="Processing duration (finished-started, or now-started if "
        "still in flight); null if processing never started"
    )


class AdminDocumentIngestionPageType(graphene.ObjectType):
    items = graphene.List(graphene.NonNull(AdminDocumentIngestionType))
    total_count = graphene.Int(description="Total matching rows before pagination")
    limit = graphene.Int()
    offset = graphene.Int()


class AdminWorkerUploadType(graphene.ObjectType):
    """A worker/pipeline upload staging row (content excluded)."""

    id = graphene.String(description="UUID of the upload")
    corpus_id = graphene.Int()
    corpus_title = graphene.String()
    worker_account_name = graphene.String(
        description="Worker account behind the token used for this upload"
    )
    status = graphene.String(description="PENDING / PROCESSING / COMPLETED / FAILED")
    error_message = graphene.String()
    file_name = graphene.String()
    size_bytes = graphene.Float(description="Size of the staged file in bytes")
    result_document_id = graphene.Int(description="Document created on success, if any")
    created = graphene.DateTime()
    processing_started = graphene.DateTime()
    processing_finished = graphene.DateTime()
    elapsed_seconds = graphene.Float()


class AdminWorkerUploadPageType(graphene.ObjectType):
    items = graphene.List(graphene.NonNull(AdminWorkerUploadType))
    total_count = graphene.Int()
    limit = graphene.Int()
    offset = graphene.Int()


class AdminCorpusImportType(graphene.ObjectType):
    """A corpus-export ZIP re-import run with per-document failure counts."""

    id = graphene.ID(description="PendingCorpusImport primary key")
    import_run_id = graphene.String(description="UUID correlating the run's documents")
    corpus_id = graphene.Int()
    corpus_title = graphene.String()
    creator_username = graphene.String()
    status = graphene.String(
        description="enumerating / ready / finalizing / done / failed"
    )
    expected_doc_count = graphene.Int(
        description="Docs the run expected to create (observability; may be null)"
    )
    total_count_docs = graphene.Int(
        description="Per-document outcome rows recorded for this run"
    )
    done_count = graphene.Int()
    failed_count = graphene.Int()
    pending_count = graphene.Int()
    percent_failed = graphene.Float(
        description="failed / total * 100 over recorded per-document rows"
    )
    created = graphene.DateTime(description="When the run was enumerated")
    modified = graphene.DateTime()


class AdminCorpusImportPageType(graphene.ObjectType):
    items = graphene.List(graphene.NonNull(AdminCorpusImportType))
    total_count = graphene.Int()
    limit = graphene.Int()
    offset = graphene.Int()


class AdminBulkImportSessionType(graphene.ObjectType):
    """A bulk document-zip import (chunked upload session; content excluded)."""

    id = graphene.String(description="UUID of the upload session")
    kind = graphene.String(description="documents_zip / zip_to_corpus")
    filename = graphene.String()
    creator_username = graphene.String()
    status = graphene.String(description="PENDING / ASSEMBLING / COMPLETED / FAILED")
    error_message = graphene.String()
    total_size = graphene.Float(description="Declared total assembled size in bytes")
    received_size = graphene.Float(
        description="Bytes received so far (0 once a completed session's parts "
        "are reclaimed)"
    )
    received_parts = graphene.Int()
    total_chunks = graphene.Int()
    percent_complete = graphene.Float(
        description="Upload progress; 100 for COMPLETED sessions"
    )
    target_corpus_id = graphene.String(
        description="Target corpus id from the session metadata, if any"
    )
    created = graphene.DateTime()
    modified = graphene.DateTime()


class AdminBulkImportSessionPageType(graphene.ObjectType):
    items = graphene.List(graphene.NonNull(AdminBulkImportSessionType))
    total_count = graphene.Int()
    limit = graphene.Int()
    offset = graphene.Int()
