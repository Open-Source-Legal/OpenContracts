"""Analysis lifecycle service — analysis CRUD beyond the read-only optimizer.

The Phase-3 :class:`opencontractserver.analyzer.services.analysis_service.AnalysisService`
covers read-side visibility (``get_visible_analyses``, ``check_analysis_permission``,
``get_analysis_annotations``). :class:`AnalysisLifecycleService` covers the
*write* surface — starting an analysis, making it public, and deleting it —
that used to live inline in ``config/graphql/analysis_mutations.py``.

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import (
    ServiceResult,
    get_for_user_or_none,
)
from opencontractserver.types.enums import PermissionTypes

if TYPE_CHECKING:
    from opencontractserver.analyzer.models import Analysis

logger = logging.getLogger(__name__)


class AnalysisLifecycleService(BaseService):
    """Analysis lifecycle operations — start, make public, delete.

    Reads are owned by :class:`AnalysisService` (Phase 3); this service owns
    the mutating surface. Every method takes an optional ``request`` kwarg so
    permission checks share the Tier-2 cache when called from a GraphQL
    resolver / mutation.
    """

    # The unified IDOR-safe message used by ``delete_analysis``. Surfacing the
    # same string whether the analysis doesn't exist, the caller can't see
    # it, or they can see it but lack DELETE blocks enumeration of analysis
    # pks (Phase D IDOR pattern).
    _DELETE_NOT_FOUND_MSG = (
        "Analysis not found or you don't have permission to delete it."
    )

    @classmethod
    def make_public(
        cls,
        user: Any,
        analysis_pk: Any,
        *,
        request: Any = None,
    ) -> ServiceResult[str]:
        """Kick off the make-public task for an analysis. **Superuser only.**

        Returns ``ServiceResult.success`` with the user-facing status
        message once the Celery task is dispatched. The superuser gate is
        enforced in-service (defence-in-depth) so internal callers
        (management commands, Celery tasks) cannot bypass it by skipping
        the ``user_passes_test`` decorator on the GraphQL mutation.

        ``request`` is accepted for API consistency with every other
        Phase-5 service method; this method does not consult the
        permission cache (no per-instance gate is run here).
        """
        from opencontractserver.tasks.permissioning_tasks import (
            make_analysis_public_task,
        )

        if not getattr(user, "is_superuser", False):
            return ServiceResult.failure("Only superusers can make analyses public.")

        logger.info(
            "Dispatching make-public for Analysis(id=%s) by user=%s",
            analysis_pk,
            getattr(user, "id", user),
        )
        make_analysis_public_task.si(analysis_id=analysis_pk).apply_async()
        return ServiceResult.success(
            "Starting an OpenContracts worker to make your analysis public! "
            "Underlying corpus must be made public too!"
        )

    @classmethod
    def start_document_analysis(
        cls,
        user: Any,
        *,
        analyzer_pk: Any,
        document_pk: Any | None = None,
        corpus_pk: Any | None = None,
        analysis_input_data: dict[str, Any] | None = None,
        request: Any = None,
    ) -> ServiceResult[Analysis]:
        """Start a document or corpus analysis using the specified analyzer.

        Validates that the caller can READ the target document and/or corpus
        before dispatching ``process_analyzer``. Returns a unified IDOR-safe
        failure message ("Resource not found or you do not have permission")
        when any visibility check fails.

        At least one of ``document_pk`` or ``corpus_pk`` MUST be provided —
        ``process_analyzer`` itself enforces this, but the service surfaces
        a clear failure so the caller doesn't reach the worker layer with a
        malformed payload.
        """
        from opencontractserver.analyzer.models import Analyzer
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.tasks.corpus_tasks import process_analyzer

        if document_pk is None and corpus_pk is None:
            return ServiceResult.failure(
                "One of document_pk and corpus_pk must be provided"
            )

        not_found_msg = "Resource not found or you do not have permission."

        if document_pk is not None:
            if (
                not Document.objects.visible_to_user(user)
                .filter(pk=document_pk)
                .exists()
            ):
                return ServiceResult.failure(not_found_msg)

        if corpus_pk is not None:
            if not Corpus.objects.visible_to_user(user).filter(pk=corpus_pk).exists():
                return ServiceResult.failure(not_found_msg)

        try:
            analyzer = Analyzer.objects.get(pk=analyzer_pk)
        except Analyzer.DoesNotExist:
            return ServiceResult.failure(not_found_msg)

        analysis = process_analyzer(
            user_id=user.id,
            analyzer=analyzer,
            corpus_id=corpus_pk,
            document_ids=[document_pk] if document_pk else None,
            corpus_action=None,
            analysis_input_data=analysis_input_data,
        )
        if analysis is None:
            return ServiceResult.failure("Analyzer could not be started.")
        cls.log_action("Started", analysis, user)
        return ServiceResult.success(analysis)

    @classmethod
    def delete_analysis(
        cls,
        user: Any,
        analysis_pk: Any,
        *,
        request: Any = None,
    ) -> ServiceResult[None]:
        """Delete an analysis (asynchronously via the standard task).

        Performs three gates in order:

        1. IDOR-safe lookup (``get_for_user_or_none``) — same response for
           not-found and not-permitted.
        2. ``user_lock`` check — the lock is observable state to anyone who
           can READ the analysis, so a distinct error is OK here. Backend
           locks (``user_lock`` set by another user) reject; the lock-holder
           may proceed (so users can abandon hung analyses).
        3. DELETE permission — checked via the Tier-0 manager so the lookup
           and the gate stay in agreement.

        Dispatches ``delete_analysis_and_annotations_task`` and returns
        ``ServiceResult.success(None)``; the actual delete is asynchronous.
        """
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.tasks import delete_analysis_and_annotations_task

        analysis = get_for_user_or_none(Analysis, analysis_pk, user)
        if analysis is None:
            return ServiceResult.failure(cls._DELETE_NOT_FOUND_MSG)

        if analysis.user_lock is not None and analysis.user_lock_id != getattr(
            user, "id", None
        ):
            return ServiceResult.failure(
                "Specified object is locked by another user. Cannot be deleted."
            )

        if not analysis.user_can(user, PermissionTypes.DELETE, request=request):
            return ServiceResult.failure(cls._DELETE_NOT_FOUND_MSG)

        delete_analysis_and_annotations_task.si(analysis_pk=analysis_pk).apply_async()
        cls.log_action("Dispatched delete for", analysis, user)
        return ServiceResult.success(None)
