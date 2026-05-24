"""``WorkerDocumentUpload`` service — per-corpus upload listing.

Worker document uploads are the staging table drained by the batch processor
Celery task. Listing them is **superuser-or-corpus-creator gated**.

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


class WorkerDocumentUploadService(BaseService):
    """Per-corpus worker-upload listing."""

    @classmethod
    def list_for_corpus(
        cls,
        user: Any,
        corpus_id: Any,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        request: Any = None,
    ) -> ServiceResult[tuple[QuerySet, int, int, int]]:
        """List worker uploads for a corpus.

        Authorisation: superuser OR corpus creator. The unified IDOR-safe
        "Not found or permission denied." surface is returned via
        ``ServiceResult.failure``.

        Returns ``ServiceResult.success`` whose value is a 4-tuple
        ``(page_queryset, total_count, effective_limit, effective_offset)``
        — the resolver builds the projection types from the page slice and
        echoes the limit/offset back to the client.
        """
        from opencontractserver.constants.document_processing import (
            WORKER_UPLOADS_QUERY_LIMIT,
        )
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.worker_uploads.models import WorkerDocumentUpload

        qs = Corpus.objects.filter(id=corpus_id)
        if not getattr(user, "is_superuser", False):
            qs = qs.filter(creator=user)
        corpus = qs.first()
        if corpus is None:
            return ServiceResult.failure("Not found or permission denied.")

        upload_qs = WorkerDocumentUpload.objects.filter(corpus=corpus).order_by(
            "-created"
        )
        if status:
            upload_qs = upload_qs.filter(status=status.upper())

        total_count = upload_qs.count()

        effective_limit = min(
            limit or WORKER_UPLOADS_QUERY_LIMIT, WORKER_UPLOADS_QUERY_LIMIT
        )
        effective_offset = max(offset or 0, 0)
        page = upload_qs[effective_offset : effective_offset + effective_limit]

        return ServiceResult.success(
            (page, total_count, effective_limit, effective_offset)
        )
