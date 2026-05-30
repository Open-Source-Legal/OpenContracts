"""
Multipart/form-data REST endpoints for document imports.

Replaces the base64-over-GraphQL upload paths from the frontend, which were
hitting Apollo's "Payload allocation size overflow" invariant for large
files (the entire base64 string had to be allocated as a JS string and
JSON-stringified into the GraphQL request body before any network I/O).

Endpoints
---------

POST /api/imports/documents/
    Single-document import. Body: multipart/form-data with ``file`` and
    metadata fields. See :class:`DocumentImportSerializer`.

POST /api/imports/documents-zip/
    Bulk zip import. Stages the archive via ``TemporaryFileHandle`` and
    queues ``process_documents_zip`` (see
    ``opencontractserver/tasks/import_tasks.py``). Returns a ``job_id``
    for status polling via the existing GraphQL job-status resolver.

POST /api/imports/zip-to-corpus/
    Bulk zip import **preserving folder structure** into a specific
    corpus. Queues ``import_zip_with_folder_structure``. Returns a
    ``job_id`` for status polling.

POST /api/imports/corpus/
    OpenContracts corpus-export zip import. Creates a new corpus owned
    by the requester and queues ``import_corpus`` to hydrate it from
    the export. Returns the placeholder ``corpus_id``.
"""

from __future__ import annotations

import logging
from typing import Callable, cast

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from config.rest_jwt_auth import GraphQLJWTAuthentication
from opencontractserver.document_imports.serializers import (
    ChunkedUploadPartSerializer,
    ChunkedUploadStartSerializer,
    CorpusExportImportSerializer,
    DocumentImportSerializer,
    DocumentsZipImportSerializer,
    ZipToCorpusImportSerializer,
)
from opencontractserver.document_imports.services import (
    ChunkedUploadError,
    CorpusImportResult,
    DocumentImportPermissionError,
    ImportResult,
    ZipImportResult,
    complete_chunked_upload,
    get_chunked_session_status,
    import_corpus_export_for_user,
    import_document_for_user,
    import_documents_zip_for_user,
    import_zip_to_corpus_for_user,
    normalise_optional,
    start_chunked_upload,
    store_chunk,
)

logger = logging.getLogger(__name__)


def _public_permission_message(code: str) -> str:
    """Map a service-layer permission-error code to a fixed, public-safe
    response string.

    The response body is built from these literals — never from
    ``str(exception)`` — so exception-derived data does not flow into the
    HTTP response (CodeQL: ``py/stack-trace-exposure``).
    """
    if code == DocumentImportPermissionError.USAGE_CAP:
        return (
            f"Your usage is capped at {settings.USAGE_CAPPED_USER_DOC_CAP_COUNT} "
            f"documents. Try deleting an existing document first or contact "
            f"the admin for a higher limit."
        )
    if code == DocumentImportPermissionError.BULK_UPLOAD_DENIED:
        return (
            "By default, usage-capped users cannot bulk upload documents. "
            "Please contact the admin to authorize your account."
        )
    return "You are not authorized to perform this import."


class DocumentImportThrottle(UserRateThrottle):
    """
    Per-endpoint throttle for document import requests.

    Default global ``user`` rate (1000/hour) is far too permissive for an
    upload endpoint where a single request can be hundreds of MB. The
    ``document_imports`` scope rate is read from
    ``REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`` and is shared by both
    the single-document and bulk-zip views.
    """

    scope = "document_imports"


def _enforce_size_cap(uploaded: UploadedFile) -> Response | None:
    """
    Reject oversized uploads with an explicit 413 before invoking the
    service layer.

    Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE`` excludes file-upload data
    from its accounting, so it does not bound the size of a multipart
    file. ``MAX_DOCUMENT_IMPORT_SIZE_BYTES`` is the per-endpoint cap;
    set it to 0 to disable the check.
    """
    limit = getattr(settings, "MAX_DOCUMENT_IMPORT_SIZE_BYTES", 0)
    if limit > 0 and uploaded.size is not None and uploaded.size > limit:
        return Response(
            {
                "ok": False,
                "error": "File too large.",
                "max_bytes": limit,
            },
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    return None


# --- Result -> Response builders --------------------------------------------
#
# Shared by the direct (single-request) import views *and* the chunked
# ``complete`` view, so each import kind has exactly one response contract no
# matter how the bytes arrived. ``status`` on the document path is the
# ``'created'``/``'updated'`` flag from ``import_content``.


def _document_result_response(result: ImportResult) -> Response:
    if result.error or result.document is None:
        return Response(
            {"ok": False, "error": result.error or "Import failed"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {"ok": True, "document_id": result.document.id, "status": result.status},
        status=status.HTTP_201_CREATED,
    )


def _zip_result_response(result: ZipImportResult) -> Response:
    if result.error or result.job_id is None:
        return Response(
            {"ok": False, "error": result.error or "Import failed"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {
            "ok": True,
            "job_id": result.job_id,
            "message": f"Import started. Job ID: {result.job_id}",
        },
        status=status.HTTP_202_ACCEPTED,
    )


def _corpus_result_response(result: CorpusImportResult) -> Response:
    if result.error or result.corpus is None:
        return Response(
            {"ok": False, "error": result.error or "Import failed"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {"ok": True, "corpus_id": result.corpus.id, "message": "Import started."},
        status=status.HTTP_202_ACCEPTED,
    )


class DocumentImportView(APIView):
    """Single-document multipart import endpoint."""

    # Pinned explicitly: bearer JWT only. Inheriting the global tuple
    # would also expose Session and Token auth on these endpoints, which
    # widens the threat model (CSRF surface, credential types) without
    # any caller actually needing it. The frontend ``importHttp.ts``
    # always sends ``Authorization: Bearer <jwt>``.
    authentication_classes = [GraphQLJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [DocumentImportThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = DocumentImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        uploaded: UploadedFile = cast(UploadedFile, data["file"])
        oversize = _enforce_size_cap(uploaded)
        if oversize is not None:
            return oversize

        # ``UploadedFile.name`` is typed Optional but the serializer guarantees a
        # file was provided, so we fall back to a sentinel only to satisfy the
        # type checker — the service relies on it for MIME-extension hints.
        filename: str = (
            normalise_optional(data.get("filename")) or uploaded.name or "upload"
        )
        file_bytes = uploaded.read()

        try:
            result = import_document_for_user(
                user=request.user,
                file_bytes=file_bytes,
                filename=filename,
                title=data["title"],
                description=normalise_optional(data.get("description")) or "",
                custom_meta=data.get("custom_meta") or {},
                make_public=bool(data.get("make_public", False)),
                add_to_corpus_id=normalise_optional(data.get("add_to_corpus_id")),
                add_to_folder_id=normalise_optional(data.get("add_to_folder_id")),
                slug=normalise_optional(data.get("slug")),
            )
        except DocumentImportPermissionError as e:
            logger.info("Document import denied", extra={"code": e.code})
            return Response(
                {"ok": False, "error": _public_permission_message(e.code)},
                status=status.HTTP_403_FORBIDDEN,
            )

        return _document_result_response(result)


class DocumentsZipImportView(APIView):
    """Bulk zip-archive multipart import endpoint."""

    # Pinned explicitly: bearer JWT only. Inheriting the global tuple
    # would also expose Session and Token auth on these endpoints, which
    # widens the threat model (CSRF surface, credential types) without
    # any caller actually needing it. The frontend ``importHttp.ts``
    # always sends ``Authorization: Bearer <jwt>``.
    authentication_classes = [GraphQLJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [DocumentImportThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = DocumentsZipImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        uploaded: UploadedFile = cast(UploadedFile, data["file"])
        oversize = _enforce_size_cap(uploaded)
        if oversize is not None:
            return oversize

        try:
            result = import_documents_zip_for_user(
                user=request.user,
                zip_source=uploaded,
                zip_filename=uploaded.name,
                title_prefix=normalise_optional(data.get("title_prefix")),
                description=normalise_optional(data.get("description")),
                custom_meta=data.get("custom_meta") or None,
                make_public=bool(data.get("make_public", False)),
                add_to_corpus_id=normalise_optional(data.get("add_to_corpus_id")),
            )
        except DocumentImportPermissionError as e:
            logger.info("Bulk-zip import denied", extra={"code": e.code})
            return Response(
                {"ok": False, "error": _public_permission_message(e.code)},
                status=status.HTTP_403_FORBIDDEN,
            )

        return _zip_result_response(result)


class ZipToCorpusImportView(APIView):
    """
    Bulk-zip import that **preserves folder structure** into a specific
    corpus. Replaces the legacy ``ImportZipToCorpus`` GraphQL mutation.

    Auth and throttling intentionally match the other ``/api/imports/*``
    views — bearer JWT only, ``DocumentImportThrottle`` scope.
    """

    authentication_classes = [GraphQLJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [DocumentImportThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = ZipToCorpusImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        uploaded: UploadedFile = cast(UploadedFile, data["file"])
        oversize = _enforce_size_cap(uploaded)
        if oversize is not None:
            return oversize

        try:
            result = import_zip_to_corpus_for_user(
                user=request.user,
                zip_source=uploaded,
                corpus_id=data["corpus_id"],
                target_folder_id=normalise_optional(data.get("target_folder_id")),
                title_prefix=normalise_optional(data.get("title_prefix")),
                description=normalise_optional(data.get("description")),
                custom_meta=data.get("custom_meta") or None,
                make_public=bool(data.get("make_public", False)),
            )
        except DocumentImportPermissionError as e:
            logger.info("Zip-to-corpus import denied", extra={"code": e.code})
            return Response(
                {"ok": False, "error": _public_permission_message(e.code)},
                status=status.HTTP_403_FORBIDDEN,
            )

        return _zip_result_response(result)


class CorpusExportImportView(APIView):
    """
    OpenContracts corpus-export zip import. Replaces the legacy
    ``UploadCorpusImportZip`` GraphQL mutation.

    Creates a new placeholder corpus owned by the requester and queues
    ``import_corpus`` to hydrate it from the uploaded export.
    """

    authentication_classes = [GraphQLJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [DocumentImportThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = CorpusExportImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        uploaded: UploadedFile = cast(UploadedFile, data["file"])
        oversize = _enforce_size_cap(uploaded)
        if oversize is not None:
            return oversize

        try:
            result = import_corpus_export_for_user(
                user=request.user,
                zip_source=uploaded,
            )
        except DocumentImportPermissionError as e:
            logger.info("Corpus-export import denied", extra={"code": e.code})
            return Response(
                {"ok": False, "error": _public_permission_message(e.code)},
                status=status.HTTP_403_FORBIDDEN,
            )

        return _corpus_result_response(result)


# ---------------------------------------------------------------------------
# Chunked (resumable) uploads
# ---------------------------------------------------------------------------
#
# Work around the 100 MB per-request body ceiling on upstream proxies
# (Cloudflare): the client POSTs ``start`` (declaring size + part count), PUTs
# each sub-ceiling part, then POSTs ``complete`` to reassemble + import. The
# heavy lifting lives in the service layer; these views are pure transport.


class ChunkedUploadPartThrottle(UserRateThrottle):
    """
    Looser throttle for individual part uploads.

    A single large file fans out into many part requests, so the strict
    ``document_imports`` scope (sized for whole-file imports) would
    throttle a legitimate multi-part upload. ``start`` and ``complete``
    stay on the strict scope; only the high-frequency part PUTs use this.
    """

    scope = "document_import_chunks"


# Per-kind result -> response builders for the ``complete`` step. Keyed by the
# ``ChunkedUploadSession.kind`` value the service returns. Typed with
# ``Callable[..., Response]`` so the heterogeneous dispatch (each builder takes
# a different result dataclass) type-checks against the returned result union.
_CHUNKED_RESPONSE_BUILDERS: dict[str, Callable[..., Response]] = {
    "document": _document_result_response,
    "documents_zip": _zip_result_response,
    "zip_to_corpus": _zip_result_response,
    "corpus_export": _corpus_result_response,
}


def _chunked_error_response(exc: ChunkedUploadError) -> Response:
    """Build the response body for a service-raised chunked-upload error."""
    body: dict = {"ok": False, "error": exc.message}
    if exc.http_status == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
        body["max_bytes"] = getattr(settings, "MAX_DOCUMENT_IMPORT_SIZE_BYTES", 0)
    return Response(body, status=exc.http_status)


class ChunkedUploadStartView(APIView):
    """POST /api/imports/chunked/start/ — open a chunked-upload session."""

    authentication_classes = [GraphQLJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [DocumentImportThrottle]
    parser_classes = [JSONParser]

    def post(self, request: Request) -> Response:
        serializer = ChunkedUploadStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            session = start_chunked_upload(
                user=request.user,
                kind=data["kind"],
                filename=data["filename"],
                total_size=data["total_size"],
                chunk_size=data["chunk_size"],
                total_chunks=data["total_chunks"],
                metadata=data.get("metadata") or {},
            )
        except DocumentImportPermissionError as e:
            logger.info("Chunked upload start denied", extra={"code": e.code})
            return Response(
                {"ok": False, "error": _public_permission_message(e.code)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ChunkedUploadError as e:
            return _chunked_error_response(e)

        return Response(
            {
                "ok": True,
                "upload_id": str(session.id),
                "chunk_size": session.chunk_size,
                "total_chunks": session.total_chunks,
            },
            status=status.HTTP_201_CREATED,
        )


class ChunkedUploadPartView(APIView):
    """
    PUT/POST /api/imports/chunked/<upload_id>/parts/<index>/ — upload one part.

    Both verbs are accepted: PUT is the natural idempotent semantic, but
    some proxies/clients are friendlier to POST for multipart bodies.
    """

    authentication_classes = [GraphQLJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChunkedUploadPartThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request: Request, upload_id: str, index: int) -> Response:
        serializer = ChunkedUploadPartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chunk_file: UploadedFile = serializer.validated_data["file"]

        try:
            info = store_chunk(
                user=request.user,
                upload_id=upload_id,
                index=index,
                chunk_file=chunk_file,
            )
        except ChunkedUploadError as e:
            return _chunked_error_response(e)

        return Response(
            {
                "ok": True,
                "index": index,
                "received_chunks": info.received_chunks,
                "total_chunks": info.total_chunks,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request, upload_id: str, index: int) -> Response:
        return self.put(request, upload_id, index)


class ChunkedUploadCompleteView(APIView):
    """POST /api/imports/chunked/<upload_id>/complete/ — reassemble + import."""

    authentication_classes = [GraphQLJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [DocumentImportThrottle]
    # ``complete`` carries no request body — the upload id comes from the URL —
    # so a single JSON parser is sufficient. Declaring the multipart parsers
    # would make DRF attempt multipart parsing on an empty body for nothing.
    parser_classes = [JSONParser]

    def post(self, request: Request, upload_id: str) -> Response:
        try:
            kind, result = complete_chunked_upload(
                user=request.user, upload_id=upload_id
            )
        except DocumentImportPermissionError as e:
            logger.info("Chunked upload complete denied", extra={"code": e.code})
            return Response(
                {"ok": False, "error": _public_permission_message(e.code)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ChunkedUploadError as e:
            return _chunked_error_response(e)

        return _CHUNKED_RESPONSE_BUILDERS[kind](result)


class ChunkedUploadStatusView(APIView):
    """GET /api/imports/chunked/<upload_id>/ — progress (for resuming)."""

    authentication_classes = [GraphQLJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChunkedUploadPartThrottle]

    def get(self, request: Request, upload_id: str) -> Response:
        try:
            info = get_chunked_session_status(user=request.user, upload_id=upload_id)
        except ChunkedUploadError as e:
            return _chunked_error_response(e)

        return Response(
            {
                "ok": True,
                "upload_id": info.session_id,
                "kind": info.kind,
                "status": info.status,
                "received_chunks": info.received_chunks,
                "total_chunks": info.total_chunks,
                "received_size": info.received_size,
                "total_size": info.total_size,
            },
            status=status.HTTP_200_OK,
        )
