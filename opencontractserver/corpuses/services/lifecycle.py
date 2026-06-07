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

from django.db import IntegrityError, transaction
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

        from opencontractserver.corpuses.services.paths import CorpusPathService

        # disambiguate->insert is a TOCTOU: a concurrent claim on the freshly
        # chosen path trips ``unique_active_path_per_corpus``. Catch it (the
        # atomic block rolls back) and signal a retry instead of a raw 500.
        try:
            with transaction.atomic():
                # The original path may have been reused by a new document while
                # this one sat in the trash (the importer only blocks active,
                # non-deleted rows, so uploading to a soft-deleted path is allowed).
                # Restoring onto the original path would then violate
                # ``unique_active_path_per_corpus`` (an uncaught IntegrityError /
                # HTTP 500) or require clobbering the new occupant. Instead
                # disambiguate to a fresh unique path so BOTH documents survive —
                # the restored one comes back at e.g. ``/Report_1.pdf``.
                restore_path = CorpusPathService.disambiguate_path(
                    document_path.path, document_path.corpus
                )

                # Mark current deleted path as non-current
                document_path.is_current = False
                document_path.save()

                # Create new restored path (immutable history node)
                DocumentPath.objects.create(
                    document=document_path.document,
                    corpus=document_path.corpus,
                    creator=user,
                    folder=document_path.folder,
                    path=restore_path,
                    version_number=document_path.version_number,
                    parent=document_path,
                    is_deleted=False,
                    is_current=True,
                )
        except IntegrityError:
            return False, "Path was claimed concurrently; please retry"

        if restore_path != document_path.path:
            logger.info(
                "Restored document %s in corpus %s to disambiguated path %r "
                "(original path %r now occupied) by user %s",
                document_path.document_id,
                document_path.corpus_id,
                restore_path,
                document_path.path,
                user.id,
            )
        else:
            logger.info(
                "Restored document %s in corpus %s by user %s",
                document_path.document_id,
                document_path.corpus_id,
                user.id,
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

    @classmethod
    def empty_corpus(
        cls,
        user: User,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> tuple[int, str]:
        """
        Move EVERY document in a corpus to Trash and remove ALL of its folders.

        This is the "empty everything" action: it resets the corpus back to an
        empty root in a single step. Documents are *soft-deleted* (they land in
        the trash and stay restorable until the trash is emptied), while the
        folder tree is hard-removed (folders are not versioned). It does NOT
        permanently delete anything — call :meth:`empty_trash` afterwards for
        that.

        Reuses ``Corpus.remove_document`` per document — the same soft-delete
        primitive 'Remove from corpus' uses — so trashed documents get
        identical history nodes + signals and remain restorable.

        Args:
            user: User performing the operation
            corpus: Corpus to empty

        Returns:
            (trashed_count, error_message) — ``trashed_count`` is the number of
            documents moved to trash. ``error_message`` is empty on success.

        Permissions:
            Requires corpus DELETE permission
        """
        from opencontractserver.corpuses.models import CorpusFolder
        from opencontractserver.documents.models import Document, DocumentPath

        # Permission check
        if not corpus.user_can(user, PermissionTypes.DELETE, request=request):
            return (
                0,
                "Permission denied: You do not have delete access to this corpus",
            )

        with transaction.atomic():
            # Every document with an active, non-deleted path in the corpus
            # (root or any folder, including CAML articles) is in scope.
            doc_ids = list(
                DocumentPath.objects.filter(
                    corpus=corpus,
                    is_current=True,
                    is_deleted=False,
                )
                .values_list("document_id", flat=True)
                .distinct()
            )

            trashed = 0
            # TODO(perf, deferred): batch this for large corpora —
            # ``remove_document`` issues several queries per document (history
            # row, signals, path update) and holds row locks for the whole loop
            # inside this single transaction, so a multi-thousand-document
            # corpus can hit the DB statement/connection timeout. This is the
            # same per-document-loop pattern as the legacy "empty trash" path
            # and ``FolderCRUDService._trash_documents_in_subtree`` (folder
            # cascade-delete); all three want one shared bulk-trash primitive
            # (tracked in issue #1951). Fine for typical corpus sizes; batch via
            # that primitive before raising the interactive document-count ceiling.
            for document in Document.objects.filter(pk__in=doc_ids):
                if corpus.remove_document(document=document, user=user):
                    trashed += 1

            # Remove the whole folder tree; the just-trashed paths' folder FK is
            # SET_NULL by this delete, so the trashed documents simply show no
            # original folder (consistent with a document trashed from root).
            CorpusFolder.objects.filter(corpus=corpus).delete()

        logger.info(
            "Emptied corpus %s: trashed %s document(s) and removed all folders "
            "by user %s",
            corpus.id,
            trashed,
            user.id,
        )
        return trashed, ""
