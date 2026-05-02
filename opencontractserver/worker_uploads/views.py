"""
REST API views for worker document uploads.

POST /api/worker-uploads/documents/     — submit a new document upload
GET  /api/worker-uploads/documents/     — list uploads for the authenticated token
GET  /api/worker-uploads/documents/<id> — check status of a specific upload
"""

import json
import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from opencontractserver.worker_uploads.auth import WorkerTokenAuthentication
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    UploadStatus,
    WorkerDocumentUpload,
)
from opencontractserver.worker_uploads.serializers import (
    WorkerDocumentUploadSerializer,
    WorkerDocumentUploadStatusSerializer,
)
from opencontractserver.worker_uploads.tasks import process_pending_uploads

logger = logging.getLogger(__name__)


class IsValidWorkerToken(permissions.BasePermission):
    """
    Ensure the request was authenticated with a valid CorpusAccessToken.

    WorkerTokenAuthentication already validates is_active, account status,
    and expiry before returning successfully. This permission class only
    needs to confirm that the auth backend actually ran (i.e. request.auth
    is a CorpusAccessToken, not a session or JWT token that happened to pass
    through a different backend).
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        return isinstance(request.auth, CorpusAccessToken)


class WorkerDocumentUploadView(APIView):
    """
    Accept a single-document upload from an external worker.

    The document and metadata are staged in the database for asynchronous
    processing by the batch drain task. Returns 202 Accepted immediately.

    Rate limiting is best-effort: the count check and subsequent create are
    not atomic, so under concurrent burst a token holder can exceed their
    limit by a small margin. This is acceptable because worker tokens are
    issued to trusted internal workers, not adversarial external clients.
    For hardened rate limiting, use a reverse proxy (e.g. nginx limit_req).
    """

    authentication_classes = [WorkerTokenAuthentication]
    permission_classes = [IsValidWorkerToken]
    parser_classes = [MultiPartParser]

    def post(self, request: Request) -> Response:
        token: CorpusAccessToken = request.auth

        # Enforce file size limit
        max_size = settings.MAX_WORKER_UPLOAD_SIZE_BYTES
        uploaded_file = request.FILES.get("file")
        if max_size and uploaded_file and uploaded_file.size > max_size:
            return Response(
                {
                    "error": "File too large.",
                    "detail": (
                        f"Maximum upload size is {max_size} bytes "
                        f"({max_size // (1024 * 1024)} MB)."
                    ),
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Enforce metadata size limit
        max_metadata_size = settings.MAX_WORKER_METADATA_SIZE_BYTES
        if max_metadata_size:
            raw_metadata = request.data.get("metadata", "")
            if isinstance(raw_metadata, dict):
                metadata_size = len(json.dumps(raw_metadata).encode())
            else:
                metadata_size = len(str(raw_metadata).encode())
            if metadata_size > max_metadata_size:
                return Response(
                    {
                        "error": "Metadata too large.",
                        "max_bytes": max_metadata_size,
                    },
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )

        # Best-effort rate limit: the count-then-create is intentionally
        # non-atomic. Under concurrent burst traffic a caller can marginally
        # exceed the limit. This is acceptable for trusted internal workers;
        # for strict enforcement use a reverse proxy (e.g. nginx limit_req).
        if token.rate_limit_per_minute > 0:
            window_start = timezone.now() - timedelta(minutes=1)
            recent_count = WorkerDocumentUpload.objects.filter(
                corpus_access_token=token,
                created__gte=window_start,
            ).count()
            if recent_count >= token.rate_limit_per_minute:
                return Response(
                    {
                        "error": "Rate limit exceeded.",
                        "detail": (
                            f"Token allows {token.rate_limit_per_minute} "
                            f"uploads per minute."
                        ),
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={"Retry-After": "60"},
                )

        serializer = WorkerDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        upload = WorkerDocumentUpload.objects.create(
            corpus_access_token=token,
            corpus=token.corpus,
            file=serializer.validated_data["file"],
            metadata=serializer.validated_data["metadata"],
            status=UploadStatus.PENDING,
        )

        logger.info(
            f"Worker upload staged: {upload.id} for corpus {token.corpus_id} "
            f"(token={token.id}, worker={token.worker_account.name})"
        )

        # Trigger the batch processor if not already running.
        # This is a lightweight nudge — Beat also schedules periodic drains
        # to catch uploads that arrive during task-worker downtime.
        process_pending_uploads.apply_async(
            queue="worker_uploads",
            ignore_result=True,
        )

        response_serializer = WorkerDocumentUploadStatusSerializer(upload)
        return Response(response_serializer.data, status=status.HTTP_202_ACCEPTED)


class WorkerDocumentUploadStatusView(RetrieveAPIView):
    """Check the status of a specific upload."""

    authentication_classes = [WorkerTokenAuthentication]
    permission_classes = [IsValidWorkerToken]
    serializer_class = WorkerDocumentUploadStatusSerializer
    lookup_field = "id"
    lookup_url_kwarg = "upload_id"

    def get_queryset(self) -> "QuerySet[WorkerDocumentUpload]":
        token: CorpusAccessToken = self.request.auth
        return WorkerDocumentUpload.objects.select_related(
            "result_document", "corpus_access_token"
        ).filter(corpus_access_token=token)


class WorkerUploadPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class WorkerDocumentUploadListView(ListAPIView):
    """List uploads for the authenticated token (paginated)."""

    authentication_classes = [WorkerTokenAuthentication]
    permission_classes = [IsValidWorkerToken]
    serializer_class = WorkerDocumentUploadStatusSerializer
    pagination_class = WorkerUploadPagination

    def get_queryset(self) -> "QuerySet[WorkerDocumentUpload]":
        token: CorpusAccessToken = self.request.auth
        qs = WorkerDocumentUpload.objects.select_related(
            "result_document", "corpus_access_token"
        ).filter(corpus_access_token=token)

        # Optional status filter
        status_filter = self.request.query_params.get("status")
        if status_filter and status_filter in UploadStatus.values:
            qs = qs.filter(status=status_filter)

        return qs.order_by("-created")
