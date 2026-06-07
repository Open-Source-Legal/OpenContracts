"""Superuser-only ingestion / corpus-import diagnostics listing.

Powers the admin "Ingestion Monitor" dashboard. These listings are
**install-wide** (every user's rows) and gated to superusers — they are a
diagnostics surface, not a permission-scoped user view, so they deliberately
do NOT go through ``visible_to_user``. The superuser gate IS the
authorisation boundary and is enforced in-service (defence-in-depth) so any
future internal caller cannot bypass it by skipping the resolver gate.

Two subjects live here because both models live in ``documents.models``:

- ``list_documents``: per-document parsing-pipeline status (the ``Document``
  ``processing_status`` / ``processing_error`` / timing fields).
- ``list_corpus_imports``: corpus-export ZIP re-import runs
  (``PendingCorpusImport``) enriched with per-run document failure counts
  aggregated from ``PendingDocumentAnnotations``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencontractserver.constants.document_processing import (
    ADMIN_INGESTION_DEFAULT_PAGE_SIZE,
    ADMIN_INGESTION_MAX_PAGE_SIZE,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)

_SUPERUSER_ONLY_MSG = "Superuser privileges required."


class IngestionAdminService(BaseService):
    """Install-wide ingestion + corpus-import diagnostics (superuser-only)."""

    @classmethod
    def list_documents(
        cls,
        user: Any,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        request: Any = None,
    ) -> ServiceResult[tuple[QuerySet, int, int, int]]:
        """List documents across all users by parsing-pipeline status.

        ``request`` is accepted for service-layer call-convention consistency
        (resolvers uniformly pass ``request=info.context``) but is intentionally
        unused: this is a superuser-bypass listing that does not go through
        ``visible_to_user`` / ``user_can``, so there is no Tier-2 permission
        cache to engage.

        Ordered newest-activity-first (``-modified``) so recently failed or
        in-flight ingestions surface at the top. ``status`` (case-insensitive)
        filters on ``Document.processing_status``. Returns a 4-tuple
        ``(page_queryset, total_count, effective_limit, effective_offset)``;
        the resolver projects each row (including the per-row ``size_bytes``
        storage stat) onto the GraphQL output type.
        """
        from opencontractserver.documents.models import Document

        if not getattr(user, "is_superuser", False):
            return ServiceResult.failure(_SUPERUSER_ONLY_MSG)

        qs = Document.objects.select_related("creator").order_by("-modified")
        if status:
            qs = qs.filter(processing_status=status.lower())

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

    @classmethod
    def list_corpus_imports(
        cls,
        user: Any,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        request: Any = None,
    ) -> ServiceResult[tuple[list, dict, int, int, int]]:
        """List corpus-export ZIP re-import runs with per-run failure counts.

        Each ``PendingCorpusImport`` is a re-import run; the per-document
        outcome rows live in ``PendingDocumentAnnotations`` correlated by
        ``ingestion_run_id == import_run_id``. Counts are aggregated in a
        single grouped query over just the page's run ids (no N+1).

        Caveat: a relationship-free re-import run mints a run id but creates no
        ``PendingCorpusImport`` row, so such runs do not appear here — only the
        per-document counts (``total``/``failed``/...) exist for them. This
        surface intentionally tracks the coordinated runs.

        Returns ``(page_list, counts_by_run_id, total_count, limit, offset)``
        where ``counts_by_run_id`` maps ``import_run_id`` (UUID) to a dict with
        ``total``/``failed``/``done``/``pending`` ints.

        ``request`` is accepted for call-convention consistency but unused — see
        the note on ``list_documents`` (superuser-bypass, no Tier-2 cache).
        """
        from django.db.models import Count, Q

        from opencontractserver.documents.models import (
            PendingCorpusImport,
            PendingDocumentAnnotations,
        )

        if not getattr(user, "is_superuser", False):
            return ServiceResult.failure(_SUPERUSER_ONLY_MSG)

        qs = PendingCorpusImport.objects.select_related("corpus", "creator").order_by(
            "-created_at"
        )
        if status:
            qs = qs.filter(status=status.lower())

        total_count = qs.count()
        effective_limit, effective_offset = cls.clamp_pagination(
            limit,
            offset,
            default=ADMIN_INGESTION_DEFAULT_PAGE_SIZE,
            maximum=ADMIN_INGESTION_MAX_PAGE_SIZE,
        )
        page = list(qs[effective_offset : effective_offset + effective_limit])

        run_ids = [pci.import_run_id for pci in page]
        counts_by_run: dict = {}
        if run_ids:
            Status = PendingDocumentAnnotations.Status
            agg = (
                PendingDocumentAnnotations.objects.filter(ingestion_run_id__in=run_ids)
                .values("ingestion_run_id")
                .annotate(
                    total=Count("id"),
                    failed=Count("id", filter=Q(status=Status.FAILED)),
                    done=Count("id", filter=Q(status=Status.DONE)),
                    pending=Count("id", filter=Q(status=Status.PENDING)),
                )
            )
            counts_by_run = {row["ingestion_run_id"]: row for row in agg}

        return ServiceResult.success(
            (page, counts_by_run, total_count, effective_limit, effective_offset)
        )
