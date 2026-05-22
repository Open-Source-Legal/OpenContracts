"""Corpus-scoped document lifecycle (soft-delete / restore / trash).

``DocumentLifecycleService`` owns the trash workflow for documents inside a
corpus: listing soft-deleted documents, soft-deleting, restoring, and
permanently deleting (individually or by emptying the whole trash). Each
lifecycle event creates an immutable :class:`DocumentPath` history node.

Split out of the former ``corpus_objs_service.py`` monolith — see
``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``
(issue #1716, service-layer centralization Phase 2).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import QuerySet

from opencontractserver.corpuses.services.corpus_documents import (
    CorpusDocumentService,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document, DocumentPath
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class DocumentLifecycleService(BaseService):
    """Soft-delete / restore / permanent-delete for documents in a corpus.

    Read methods require corpus READ; soft-delete and permanent-delete
    require corpus DELETE; restore requires corpus UPDATE.
    """

    @classmethod
    def get_deleted_documents(
        cls,
        user: User,
        corpus_id: int,
        *,
        request: Any = None,
    ) -> QuerySet[DocumentPath]:
        """
        Get soft-deleted documents for "trash" view.

        Returns DocumentPath records (not Documents) because we need
        the path metadata for restore operations.

        Args:
            user: Requesting user
            corpus_id: ID of corpus to get deleted documents from

        Returns:
            QuerySet of DocumentPath records with is_deleted=True

        Permissions:
            Requires corpus READ permission
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import DocumentPath

        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return DocumentPath.objects.none()

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
            return DocumentPath.objects.none()

        return (
            DocumentPath.objects.filter(
                corpus_id=corpus_id,
                is_current=True,
                is_deleted=True,
            )
            .select_related("document", "folder", "document__creator")
            .order_by("-modified")
        )

    @classmethod
    def soft_delete_document(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> tuple[bool, str]:
        """
        Soft-delete document (move to trash).

        Creates a new DocumentPath with ``is_deleted=True`` (every lifecycle
        event creates an immutable history node).

        Args:
            user: Deleting user
            document: Document to soft-delete
            corpus: Corpus context

        Returns:
            (success, error_message)

        Permissions:
            Requires corpus DELETE permission
        """
        from opencontractserver.documents.models import DocumentPath

        # Permission check
        if not corpus.user_can(user, PermissionTypes.DELETE, request=request):
            return (
                False,
                "Permission denied: You do not have delete access to this corpus",
            )

        # Validate document belongs to corpus
        if not CorpusDocumentService._check_document_in_corpus(document, corpus):
            return False, "Document does not belong to this corpus"

        with transaction.atomic():
            # Get current path
            try:
                current_path = DocumentPath.objects.get(
                    document=document,
                    corpus=corpus,
                    is_current=True,
                    is_deleted=False,
                )
            except DocumentPath.DoesNotExist:
                return False, "Document has no active path in this corpus"

            # Mark current as non-current
            current_path.is_current = False
            current_path.save()

            # Create new deleted path (immutable history node)
            DocumentPath.objects.create(
                document=document,
                corpus=corpus,
                creator=user,
                folder=current_path.folder,
                path=current_path.path,
                version_number=current_path.version_number,
                parent=current_path,
                is_deleted=True,
                is_current=True,
            )

            logger.info(
                f"Soft-deleted document {document.id} in corpus {corpus.id} by user {user.id}"
            )
            return True, ""

    @classmethod
    def restore_document(
        cls,
        user: User,
        document_path: DocumentPath,
        *,
        request: Any = None,
    ) -> tuple[bool, str]:
        """
        Restore soft-deleted document.

        Creates a new DocumentPath with ``is_deleted=False`` (immutable history node).

        Args:
            user: Restoring user
            document_path: The deleted DocumentPath to restore from

        Returns:
            (success, error_message)

        Permissions:
            Requires corpus UPDATE permission
        """
        from opencontractserver.documents.models import DocumentPath

        # Permission check
        if not document_path.corpus.user_can(
            user, PermissionTypes.UPDATE, request=request
        ):
            return (
                False,
                "You do not have permission to restore documents in this corpus",
            )

        # Validate path is deleted
        if not document_path.is_deleted:
            return False, "Document is not deleted"

        if not document_path.is_current:
            return False, "Document path is not current"

        with transaction.atomic():
            # Mark current deleted path as non-current
            document_path.is_current = False
            document_path.save()

            # Create new restored path (immutable history node)
            DocumentPath.objects.create(
                document=document_path.document,
                corpus=document_path.corpus,
                creator=user,
                folder=document_path.folder,
                path=document_path.path,
                version_number=document_path.version_number,
                parent=document_path,
                is_deleted=False,
                is_current=True,
            )

            logger.info(
                f"Restored document {document_path.document_id} in corpus "
                f"{document_path.corpus_id} by user {user.id}"
            )
            return True, ""

    @classmethod
    def permanently_delete_document(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> tuple[bool, str]:
        """
        Permanently delete a soft-deleted document from corpus.

        This is IRREVERSIBLE and removes:
        - All DocumentPath history for the document in this corpus
        - User annotations (non-structural) on the document
        - Relationships involving those annotations
        - DocumentSummaryRevision records
        - The Document itself if no other corpus references it

        Args:
            user: User performing the deletion
            document: Document to permanently delete
            corpus: Corpus context

        Returns:
            (success, error_message)

        Permissions:
            Requires corpus DELETE permission
        """
        from opencontractserver.documents.versioning import permanently_delete_document

        # Permission check - same as soft delete
        if not corpus.user_can(user, PermissionTypes.DELETE, request=request):
            return (
                False,
                "Permission denied: You do not have delete access to this corpus",
            )

        # Validate document belongs to corpus (has any path record)
        if not CorpusDocumentService._check_document_in_corpus(document, corpus):
            return False, "Document does not belong to this corpus"

        # Delegate to versioning module
        return permanently_delete_document(corpus, document, user)

    @classmethod
    def empty_trash(
        cls,
        user: User,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> tuple[int, str]:
        """
        Permanently delete ALL soft-deleted documents in a corpus.

        This empties the trash by permanently deleting all documents
        that are currently soft-deleted.

        Args:
            user: User performing the deletion
            corpus: Corpus to empty trash for

        Returns:
            (deleted_count, error_message)

        Permissions:
            Requires corpus DELETE permission
        """
        from opencontractserver.documents.versioning import (
            permanently_delete_all_in_trash,
        )

        # Permission check
        if not corpus.user_can(user, PermissionTypes.DELETE, request=request):
            return (
                0,
                "Permission denied: You do not have delete access to this corpus",
            )

        # Delegate to versioning module
        deleted_count, errors = permanently_delete_all_in_trash(corpus, user)

        if errors:
            error_msg = f"Deleted {deleted_count} documents with {len(errors)} errors: {'; '.join(errors[:3])}"
            if len(errors) > 3:
                error_msg += f" (and {len(errors) - 3} more)"
            return deleted_count, error_msg

        return deleted_count, ""
