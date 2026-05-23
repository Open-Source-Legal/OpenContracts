"""Document actions service — extracts, analysis rows, and corpus actions.

``DocumentActionsService`` is the permission-aware entry point for
document-related actions. It follows the least-privilege model:

- Document permissions are primary.
- Corpus permissions are secondary.
- Effective permission = ``MIN(document_permission, corpus_permission)``.

Callers do not need to understand the permissioning system to retrieve
document-related objects — the service centralises that logic.

Migrated from ``documents/query_optimizer.py`` as Phase 4 of the
service-layer centralization roadmap — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from typing import Any, Optional

from django.db.models import QuerySet

from opencontractserver.shared.services import BaseService


class DocumentActionsService(BaseService):
    """Permission-aware queries for document-related actions."""

    @classmethod
    def get_document_actions(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
        *,
        request: Optional[Any] = None,
    ) -> dict:
        """
        Get all actions/extracts/analyses for a document with proper permission filtering.

        This method follows the least-privilege model:
        1. First checks document permission
        2. If corpus_id provided, also checks corpus permission
        3. Returns only objects the user has access to

        Args:
            user: The requesting user
            document_id: The document ID to get actions for
            corpus_id: Optional corpus ID to filter by
            request: Optional request object (``info.context``) threaded into
                ``user_can`` and downstream service helpers so the Tier-2
                request-scoped permission cache applies.

        Returns:
            dict with:
            - corpus_actions: list of CorpusAction objects
            - extracts: list of Extract objects
            - analysis_rows: list of DocumentAnalysisRow objects
        """
        from opencontractserver.analyzer.services import AnalysisService
        from opencontractserver.corpuses.models import Corpus, CorpusAction
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.services import ExtractService

        result: dict[str, list[Any]] = {
            "corpus_actions": [],
            "extracts": [],
            "analysis_rows": [],
        }

        # Get document first
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return result

        # Check document permission
        from opencontractserver.types.enums import PermissionTypes

        if not document.user_can(user, PermissionTypes.READ, request=request):
            return result

        # Get corpus if provided and check permission
        corpus = None
        if corpus_id:
            try:
                corpus = Corpus.objects.get(id=corpus_id)
                if not corpus.user_can(user, PermissionTypes.READ, request=request):
                    return result
            except Corpus.DoesNotExist:
                # No corpus found, but document permission passed
                # Return document-only results (no corpus actions)
                pass

        # Get corpus actions (only if corpus is provided and accessible)
        if corpus:
            result["corpus_actions"] = list(
                CorpusAction.objects.visible_to_user(user).filter(corpus=corpus)
            )

        # Get extracts using ExtractService.
        # ``context=request`` (not ``request=request``) is intentional: the
        # service's ``get_visible_extracts`` signature still uses ``context=``
        # (carried over from the legacy ``ExtractQueryOptimizer`` API).
        visible_extracts = ExtractService.get_visible_extracts(
            user, corpus_id=corpus_id, context=request
        )
        # Filter to extracts that include this document
        result["extracts"] = list(visible_extracts.filter(documents=document))

        # Get analysis rows
        # Filter to analyses user can see, then get their rows for this document
        visible_analyses = AnalysisService.get_visible_analyses(
            user, corpus_id=corpus_id, context=request
        )
        result["analysis_rows"] = list(
            document.rows.filter(analysis__in=visible_analyses).select_related(
                "analysis", "analysis__analyzer"
            )
        )

        return result

    @classmethod
    def get_corpus_actions_for_corpus(
        cls,
        user,
        corpus_id: int,
        *,
        request: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get all corpus actions for a corpus with permission filtering.

        Args:
            user: The requesting user
            corpus_id: The corpus ID
            request: Optional request object threaded into ``user_can`` so the
                Tier-2 request-scoped permission cache applies.

        Returns:
            QuerySet of CorpusAction objects
        """
        from opencontractserver.corpuses.models import Corpus, CorpusAction
        from opencontractserver.types.enums import PermissionTypes

        # Check corpus permission first
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return CorpusAction.objects.none()

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
            return CorpusAction.objects.none()

        # Use visible_to_user manager method
        return CorpusAction.objects.visible_to_user(user).filter(corpus=corpus)

    @classmethod
    def get_extracts_for_document(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
        *,
        request: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get extracts that include a specific document.

        Args:
            user: The requesting user
            document_id: The document ID
            corpus_id: Optional corpus to filter by
            request: Optional request object threaded into ``user_can`` and the
                extract optimizer so the Tier-2 permission cache applies.

        Returns:
            QuerySet of Extract objects
        """
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import Extract
        from opencontractserver.extracts.services import ExtractService
        from opencontractserver.types.enums import PermissionTypes

        # Check document permission
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return Extract.objects.none()

        if not document.user_can(user, PermissionTypes.READ, request=request):
            return Extract.objects.none()

        # Get visible extracts
        visible_extracts = ExtractService.get_visible_extracts(
            user, corpus_id=corpus_id, context=request
        )

        # Filter to those that include this document
        return visible_extracts.filter(documents=document)

    @classmethod
    def get_analysis_rows_for_document(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
        *,
        request: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get analysis rows for a specific document.

        Args:
            user: The requesting user
            document_id: The document ID
            corpus_id: Optional corpus to filter by
            request: Optional request object threaded into ``user_can`` and the
                analysis optimizer so the Tier-2 permission cache applies.

        Returns:
            QuerySet of DocumentAnalysisRow objects
        """
        from opencontractserver.analyzer.services import AnalysisService
        from opencontractserver.documents.models import Document, DocumentAnalysisRow
        from opencontractserver.types.enums import PermissionTypes

        # Check document permission
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return DocumentAnalysisRow.objects.none()

        if not document.user_can(user, PermissionTypes.READ, request=request):
            return DocumentAnalysisRow.objects.none()

        # Get visible analyses
        visible_analyses = AnalysisService.get_visible_analyses(
            user, corpus_id=corpus_id, context=request
        )

        # Get rows for this document from visible analyses
        return document.rows.filter(analysis__in=visible_analyses).select_related(
            "analysis", "analysis__analyzer"
        )
