"""
Document Query Optimizer for OpenContracts.

Provides optimized queries for document-related actions (extracts, analysis rows, corpus actions).
Follows the least-privilege permission model.
"""

from typing import TYPE_CHECKING, Optional

from django.db.models import QuerySet

if TYPE_CHECKING:
    pass


class DocumentActionsQueryOptimizer:
    """
    Optimized queries for document-related actions (extracts, analysis rows, corpus actions).

    Follows the least-privilege model from AnnotationQueryOptimizer:
    - Document permissions are primary
    - Corpus permissions are secondary
    - Effective permission = MIN(document_permission, corpus_permission)

    This optimizer centralizes permission logic so developers don't need to
    understand the permissioning system when retrieving document-related objects.
    """

    @classmethod
    def get_document_actions(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
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

        Returns:
            dict with:
            - corpus_actions: list of CorpusAction objects
            - extracts: list of Extract objects
            - analysis_rows: list of DocumentAnalysisRow objects
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
            ExtractQueryOptimizer,
        )
        from opencontractserver.corpuses.models import Corpus, CorpusAction
        from opencontractserver.documents.models import Document

        result = {
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
        if not cls._check_document_permission(user, document):
            return result

        # Get corpus if provided and check permission
        corpus = None
        if corpus_id:
            try:
                corpus = Corpus.objects.get(id=corpus_id)
                if not cls._check_corpus_permission(user, corpus):
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

        # Get extracts using ExtractQueryOptimizer
        visible_extracts = ExtractQueryOptimizer.get_visible_extracts(
            user, corpus_id=corpus_id
        )
        # Filter to extracts that include this document
        result["extracts"] = list(visible_extracts.filter(documents=document))

        # Get analysis rows
        # Filter to analyses user can see, then get their rows for this document
        visible_analyses = AnalysisQueryOptimizer.get_visible_analyses(
            user, corpus_id=corpus_id
        )
        result["analysis_rows"] = list(
            document.rows.filter(analysis__in=visible_analyses).select_related(
                "analysis", "analysis__analyzer"
            )
        )

        return result

    @classmethod
    def _check_document_permission(cls, user, document) -> bool:
        """
        Check if user has READ permission on document.

        Users can read a document if:
        - They are superuser
        - Document is public
        - They are the creator
        - They have explicit READ permission

        Args:
            user: The requesting user
            document: The Document object

        Returns:
            True if user can read the document, False otherwise
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Superusers can access everything
        if hasattr(user, "is_superuser") and user.is_superuser:
            return True

        # Anonymous users can only access public documents
        if user is None or (hasattr(user, "is_anonymous") and user.is_anonymous):
            return document.is_public

        # Public documents are accessible to all authenticated users
        if document.is_public:
            return True

        # Creators can always access their own documents
        if hasattr(document, "creator_id") and document.creator_id == user.id:
            return True

        # Check explicit READ permission
        return user_has_permission_for_obj(
            user, document, PermissionTypes.READ, include_group_permissions=True
        )

    @classmethod
    def _check_corpus_permission(cls, user, corpus) -> bool:
        """
        Check if user has READ permission on corpus.

        Users can read a corpus if:
        - They are superuser
        - Corpus is public
        - They are the creator
        - They have explicit READ permission

        Args:
            user: The requesting user
            corpus: The Corpus object

        Returns:
            True if user can read the corpus, False otherwise
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Superusers can access everything
        if hasattr(user, "is_superuser") and user.is_superuser:
            return True

        # Anonymous users can only access public corpuses
        if user is None or (hasattr(user, "is_anonymous") and user.is_anonymous):
            return corpus.is_public

        # Public corpuses are accessible to all authenticated users
        if corpus.is_public:
            return True

        # Creators can always access their own corpuses
        if hasattr(corpus, "creator_id") and corpus.creator_id == user.id:
            return True

        # Check explicit READ permission
        return user_has_permission_for_obj(
            user, corpus, PermissionTypes.READ, include_group_permissions=True
        )

    @classmethod
    def get_corpus_actions_for_corpus(
        cls,
        user,
        corpus_id: int,
    ) -> QuerySet:
        """
        Get all corpus actions for a corpus with permission filtering.

        Args:
            user: The requesting user
            corpus_id: The corpus ID

        Returns:
            QuerySet of CorpusAction objects
        """
        from opencontractserver.corpuses.models import Corpus, CorpusAction

        # Check corpus permission first
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return CorpusAction.objects.none()

        if not cls._check_corpus_permission(user, corpus):
            return CorpusAction.objects.none()

        # Use visible_to_user manager method
        return CorpusAction.objects.visible_to_user(user).filter(corpus=corpus)

    @classmethod
    def get_extracts_for_document(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
    ) -> QuerySet:
        """
        Get extracts that include a specific document.

        Args:
            user: The requesting user
            document_id: The document ID
            corpus_id: Optional corpus to filter by

        Returns:
            QuerySet of Extract objects
        """
        from opencontractserver.annotations.query_optimizer import (
            ExtractQueryOptimizer,
        )
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import Extract

        # Check document permission
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return Extract.objects.none()

        if not cls._check_document_permission(user, document):
            return Extract.objects.none()

        # Get visible extracts
        visible_extracts = ExtractQueryOptimizer.get_visible_extracts(
            user, corpus_id=corpus_id
        )

        # Filter to those that include this document
        return visible_extracts.filter(documents=document)

    @classmethod
    def get_analysis_rows_for_document(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
    ) -> QuerySet:
        """
        Get analysis rows for a specific document.

        Args:
            user: The requesting user
            document_id: The document ID
            corpus_id: Optional corpus to filter by

        Returns:
            QuerySet of DocumentAnalysisRow objects
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
        )
        from opencontractserver.documents.models import Document, DocumentAnalysisRow

        # Check document permission
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return DocumentAnalysisRow.objects.none()

        if not cls._check_document_permission(user, document):
            return DocumentAnalysisRow.objects.none()

        # Get visible analyses
        visible_analyses = AnalysisQueryOptimizer.get_visible_analyses(
            user, corpus_id=corpus_id
        )

        # Get rows for this document from visible analyses
        return document.rows.filter(analysis__in=visible_analyses).select_related(
            "analysis", "analysis__analyzer"
        )
