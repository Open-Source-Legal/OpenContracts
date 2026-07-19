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
import logging
from typing import Annotated, Any, cast

import strawberry
from django.utils import timezone
from graphql import GraphQLError

from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.ingestion_admin_types import (
    AdminBulkImportSessionPageType,
    AdminBulkImportSessionType,
    AdminCorpusImportPageType,
    AdminCorpusImportType,
    AdminDocumentIngestionPageType,
    AdminDocumentIngestionType,
    AdminWorkerUploadPageType,
    AdminWorkerUploadType,
)

logger = logging.getLogger(__name__)

# Same opaque denial for every admin resolver so a non-superuser cannot
# distinguish "field exists but forbidden" from anything else.
_FORBIDDEN_MSG = "You do not have permission to access this resource."


def _require_superuser(info) -> None:
    """Raise ``GraphQLError`` unless the requesting user is a superuser."""
    user = info.context.user
    if not getattr(user, "is_superuser", False):
        raise GraphQLError(_FORBIDDEN_MSG)


def _elapsed_seconds(
    started: datetime.datetime | None, finished: datetime.datetime | None
) -> float | None:
    """Processing duration in seconds.

    ``finished - started`` once finished; ``now - started`` while still in
    flight; ``None`` if processing never started. Floored at 0 so clock skew
    between ``started`` and ``finished`` never yields a negative duration.
    """
    if started is None:
        return None
    end = finished or timezone.now()
    return max((end - started).total_seconds(), 0.0)


def _safe_size(file_field: Any) -> float | None:
    """Best-effort file size in bytes.

    ``FileField.size`` issues a storage stat (a remote HEAD under S3). Returns
    ``None`` rather than raising when the field is empty or the underlying
    object is missing/unreachable, so one orphaned file can't 500 the whole
    diagnostics page.
    """
    if not file_field:
        return None
    try:
        return float(file_field.size)
    except Exception:  # noqa: BLE001 - storage backends raise assorted errors
        return None


def _document_size(document: Any) -> float | None:
    """Size of a document's stored source file (PDF, else text extract)."""
    return _safe_size(document.pdf_file) or _safe_size(document.txt_extract_file)


def _basename(name: str | None) -> str | None:
    """Trailing path segment of a storage key (the user-facing file name)."""
    if not name:
        return None
    return name.rsplit("/", 1)[-1]


@login_required
def _resolve_Query_admin_document_ingestion(
    root, info, status=None, limit=None, offset=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/ingestion_admin_queries.py:141

    Port of IngestionAdminQueryMixin.resolve_admin_document_ingestion
    """
    from opencontractserver.documents.services import IngestionAdminService

    _require_superuser(info)
    result = IngestionAdminService.list_documents(
        info.context.user,
        status=status,
        limit=limit,
        offset=offset,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)
    # ``result.ok`` guarantees a non-None value; ``cast`` narrows the
    # Optional for mypy (matching config/graphql/worker_queries.py). The
    # page element is left ``Any`` so iterating rows that carry service
    # annotations does not trip attribute checks.
    page, total_count, effective_limit, effective_offset = cast(
        "tuple[Any, int, int, int]", result.value
    )

    items = [
        AdminDocumentIngestionType(
            id=doc.id,
            title=doc.title,
            creator_username=doc.creator.username if doc.creator else None,
            creator_email=doc.creator.email if doc.creator else None,
            file_type=doc.file_type,
            page_count=doc.page_count,
            size_bytes=_document_size(doc),
            processing_status=doc.processing_status,
            processing_error=doc.processing_error or None,
            created=doc.created,
            processing_started=doc.processing_started,
            processing_finished=doc.processing_finished,
            elapsed_seconds=_elapsed_seconds(
                doc.processing_started, doc.processing_finished
            ),
        )
        for doc in page
    ]
    return AdminDocumentIngestionPageType(
        items=items,
        total_count=total_count,
        limit=effective_limit,
        offset=effective_offset,
    )


def q_admin_document_ingestion(
    info: strawberry.Info,
    status: Annotated[
        str | None,
        strawberry.argument(
            name="status",
            description="Filter by processing status (pending/processing/completed/failed).",
        ),
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        AdminDocumentIngestionPageType,
        strawberry.lazy("config.graphql.ingestion_admin_types"),
    ]
):
    kwargs = strip_unset({"status": status, "limit": limit, "offset": offset})
    return _resolve_Query_admin_document_ingestion(None, info, **kwargs)


@login_required
def _resolve_Query_admin_worker_uploads(
    root, info, status=None, limit=None, offset=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/ingestion_admin_queries.py:192

    Port of IngestionAdminQueryMixin.resolve_admin_worker_uploads
    """
    from opencontractserver.worker_uploads.services import (
        WorkerDocumentUploadService,
    )

    _require_superuser(info)
    result = WorkerDocumentUploadService.list_all_for_admin(
        info.context.user,
        status=status,
        limit=limit,
        offset=offset,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)
    # ``result.ok`` guarantees a non-None value; ``cast`` narrows the
    # Optional for mypy (matching config/graphql/worker_queries.py). The
    # page element is left ``Any`` so iterating rows that carry service
    # annotations does not trip attribute checks.
    page, total_count, effective_limit, effective_offset = cast(
        "tuple[Any, int, int, int]", result.value
    )

    items: list = []
    for upload in page:
        token = upload.corpus_access_token
        worker_name = (
            token.worker_account.name if token and token.worker_account_id else None
        )
        items.append(
            AdminWorkerUploadType(
                id=str(upload.id),
                corpus_id=upload.corpus_id,
                corpus_title=upload.corpus.title if upload.corpus else None,
                worker_account_name=worker_name,
                status=upload.status,
                error_message=upload.error_message or None,
                file_name=_basename(upload.file.name if upload.file else None),
                size_bytes=_safe_size(upload.file),
                result_document_id=upload.result_document_id,
                created=upload.created,
                processing_started=upload.processing_started,
                processing_finished=upload.processing_finished,
                elapsed_seconds=_elapsed_seconds(
                    upload.processing_started, upload.processing_finished
                ),
            )
        )
    return AdminWorkerUploadPageType(
        items=items,
        total_count=total_count,
        limit=effective_limit,
        offset=effective_offset,
    )


def q_admin_worker_uploads(
    info: strawberry.Info,
    status: Annotated[
        str | None, strawberry.argument(name="status")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        AdminWorkerUploadPageType,
        strawberry.lazy("config.graphql.ingestion_admin_types"),
    ]
):
    kwargs = strip_unset({"status": status, "limit": limit, "offset": offset})
    return _resolve_Query_admin_worker_uploads(None, info, **kwargs)


@login_required
def _resolve_Query_admin_corpus_imports(
    root, info, status=None, limit=None, offset=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/ingestion_admin_queries.py:250

    Port of IngestionAdminQueryMixin.resolve_admin_corpus_imports
    """
    from opencontractserver.documents.services import IngestionAdminService

    _require_superuser(info)
    result = IngestionAdminService.list_corpus_imports(
        info.context.user,
        status=status,
        limit=limit,
        offset=offset,
        request=info.context,
    )
    if not result.ok:
        raise GraphQLError(result.error)
    (
        page,
        counts_by_run,
        total_count,
        effective_limit,
        effective_offset,
    ) = cast("tuple[Any, dict, int, int, int]", result.value)

    items: list = []
    for pci in page:
        counts = counts_by_run.get(pci.import_run_id, {})
        total_docs = counts.get("total", 0)
        failed = counts.get("failed", 0)
        percent_failed = (failed / total_docs * 100.0) if total_docs else 0.0
        items.append(
            AdminCorpusImportType(
                id=pci.id,
                import_run_id=str(pci.import_run_id),
                corpus_id=pci.corpus_id,
                corpus_title=pci.corpus.title if pci.corpus else None,
                creator_username=pci.creator.username if pci.creator else None,
                status=pci.status,
                expected_doc_count=pci.expected_doc_count,
                total_count_docs=total_docs,
                done_count=counts.get("done", 0),
                failed_count=failed,
                pending_count=counts.get("pending", 0),
                percent_failed=percent_failed,
                created=pci.created_at,
                modified=pci.updated_at,
            )
        )
    return AdminCorpusImportPageType(
        items=items,
        total_count=total_count,
        limit=effective_limit,
        offset=effective_offset,
    )


def q_admin_corpus_imports(
    info: strawberry.Info,
    status: Annotated[
        str | None, strawberry.argument(name="status")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        AdminCorpusImportPageType,
        strawberry.lazy("config.graphql.ingestion_admin_types"),
    ]
):
    kwargs = strip_unset({"status": status, "limit": limit, "offset": offset})
    return _resolve_Query_admin_corpus_imports(None, info, **kwargs)


@login_required
def _resolve_Query_admin_bulk_import_sessions(
    root, info, status=None, limit=None, offset=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/ingestion_admin_queries.py:305

    Port of IngestionAdminQueryMixin.resolve_admin_bulk_import_sessions
    """
    from opencontractserver.document_imports.models import ChunkedUploadStatus
    from opencontractserver.document_imports.services import (
        list_chunked_sessions_for_admin,
    )

    _require_superuser(info)
    result = list_chunked_sessions_for_admin(
        info.context.user,
        status=status,
        limit=limit,
        offset=offset,
    )
    if not result.ok:
        raise GraphQLError(result.error)
    page, total_count, effective_limit, effective_offset = cast(
        "tuple[Any, int, int, int]", result.value
    )

    items: list = []
    for session in page:
        received = float(session.received_size or 0)
        if session.status == ChunkedUploadStatus.COMPLETED:
            percent_complete = 100.0
        elif session.total_size:
            percent_complete = min(100.0, received / float(session.total_size) * 100.0)
        else:
            percent_complete = 0.0
        metadata = session.metadata or {}
        corpus_id = metadata.get("corpus_id")
        items.append(
            AdminBulkImportSessionType(
                id=str(session.id),
                kind=session.kind,
                filename=session.filename,
                creator_username=(
                    session.creator.username if session.creator else None
                ),
                status=session.status,
                error_message=session.error_message or None,
                total_size=(
                    float(session.total_size)
                    if session.total_size is not None
                    else None
                ),
                received_size=received,
                received_parts=session.received_parts or 0,
                total_chunks=session.total_chunks,
                percent_complete=percent_complete,
                target_corpus_id=(str(corpus_id) if corpus_id is not None else None),
                created=session.created,
                modified=session.modified,
            )
        )
    return AdminBulkImportSessionPageType(
        items=items,
        total_count=total_count,
        limit=effective_limit,
        offset=effective_offset,
    )


def q_admin_bulk_import_sessions(
    info: strawberry.Info,
    status: Annotated[
        str | None, strawberry.argument(name="status")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        AdminBulkImportSessionPageType,
        strawberry.lazy("config.graphql.ingestion_admin_types"),
    ]
):
    kwargs = strip_unset({"status": status, "limit": limit, "offset": offset})
    return _resolve_Query_admin_bulk_import_sessions(None, info, **kwargs)


QUERY_FIELDS = {
    "admin_document_ingestion": strawberry.field(
        resolver=q_admin_document_ingestion,
        name="adminDocumentIngestion",
        description="Per-document parsing-pipeline status across all users. Superuser only.",
    ),
    "admin_worker_uploads": strawberry.field(
        resolver=q_admin_worker_uploads,
        name="adminWorkerUploads",
        description="Worker/pipeline upload queue across all corpuses. Superuser only.",
    ),
    "admin_corpus_imports": strawberry.field(
        resolver=q_admin_corpus_imports,
        name="adminCorpusImports",
        description="Corpus-export ZIP re-import runs with per-document failure counts. Superuser only.",
    ),
    "admin_bulk_import_sessions": strawberry.field(
        resolver=q_admin_bulk_import_sessions,
        name="adminBulkImportSessions",
        description="Bulk document-zip import sessions across all users. Superuser only.",
    ),
}
