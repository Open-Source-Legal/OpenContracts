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
"""

from __future__ import annotations

import logging
from typing import cast

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from config.rest_jwt_auth import GraphQLJWTAuthentication
from opencontractserver.document_imports.serializers import (
    DocumentImportSerializer,
    DocumentsZipImportSerializer,
)
from opencontractserver.document_imports.services import (
    import_document_for_user,
    import_documents_zip_for_user,
)

logger = logging.getLogger(__name__)


def _normalise_optional(value: str | None) -> str | None:
    """Treat blank-string form fields as omitted."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


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
            _normalise_optional(data.get("filename")) or uploaded.name or "upload"
        )
        file_bytes = uploaded.read()

        try:
            result = import_document_for_user(
                user=request.user,
                file_bytes=file_bytes,
                filename=filename,
                title=data["title"],
                description=_normalise_optional(data.get("description")) or "",
                custom_meta=data.get("custom_meta") or {},
                make_public=bool(data.get("make_public", False)),
                add_to_corpus_id=_normalise_optional(data.get("add_to_corpus_id")),
                add_to_folder_id=_normalise_optional(data.get("add_to_folder_id")),
                slug=_normalise_optional(data.get("slug")),
            )
        except PermissionError as e:
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_403_FORBIDDEN,
            )

        if result.error or result.document is None:
            return Response(
                {"ok": False, "error": result.error or "Import failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "ok": True,
                "document_id": result.document.id,
                "status": result.status,
            },
            status=status.HTTP_201_CREATED,
        )


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
                title_prefix=_normalise_optional(data.get("title_prefix")),
                description=_normalise_optional(data.get("description")),
                custom_meta=data.get("custom_meta") or None,
                make_public=bool(data.get("make_public", False)),
                add_to_corpus_id=_normalise_optional(data.get("add_to_corpus_id")),
            )
        except PermissionError as e:
            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_403_FORBIDDEN,
            )

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
