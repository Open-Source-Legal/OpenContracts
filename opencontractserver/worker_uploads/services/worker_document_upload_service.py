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

    @classmethod
    def list_all_for_admin(
        cls,
        user: Any,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        request: Any = None,
    ) -> ServiceResult[tuple[QuerySet, int, int, int]]:
        """Install-wide worker-upload queue listing. **Superuser-only.**

        Unlike :meth:`list_for_corpus` (corpus-creator scoped, per-corpus),
        this is the cross-corpus diagnostics view for the admin ingestion
        monitor: every worker upload across every corpus, newest first. The
        superuser gate is enforced in-service (defence-in-depth) and returns
        the standard "Not found or permission denied." surface for anyone
        else. ``status`` (case-insensitive) filters on ``UploadStatus``.

        Returns ``(page_queryset, total_count, effective_limit,
        effective_offset)``; the resolver projects each row (including the
        per-row ``size_bytes`` storage stat) onto the GraphQL output type.

        ``request`` is accepted for service-layer call-convention consistency
        (resolvers uniformly pass ``request=info.context``) but is intentionally
        unused: this superuser-bypass listing does not go through
        ``visible_to_user`` / ``user_can``, so there is no Tier-2 permission
        cache to engage.
        """
        from opencontractserver.constants.document_processing import (
            ADMIN_INGESTION_DEFAULT_PAGE_SIZE,
            ADMIN_INGESTION_MAX_PAGE_SIZE,
        )
        from opencontractserver.worker_uploads.models import WorkerDocumentUpload

        if not getattr(user, "is_superuser", False):
            return ServiceResult.failure("Not found or permission denied.")

        qs = WorkerDocumentUpload.objects.select_related(
            "corpus", "corpus_access_token__worker_account"
        ).order_by("-created")
        if status:
            qs = qs.filter(status=status.upper())

        total_count = qs.count()
        effective_limit, effective_offset = cls.clamp_pagination(
            limit,
            offset,
            default=ADMIN_INGESTION_DEFAULT_PAGE_SIZE,
            maximum=ADMIN_INGESTION_MAX_PAGE_SIZE,
        )
        page = qs[effective_offset : effective_offset + effective_limit]
        return ServiceResult.success(
            (page, total_count, effective_limit, effective_offset)
        )
