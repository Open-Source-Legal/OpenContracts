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
from collections.abc import Iterable
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

        Delegates the soft-delete to :meth:`bulk_soft_delete_documents`, the
        shared bulk-trash primitive (the batched counterpart of
        ``Corpus.remove_document``), so trashed documents get identical history
        nodes + signals and remain restorable.

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
        from opencontractserver.documents.models import DocumentPath

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

            # Batched soft-delete: a fixed handful of queries regardless of the
            # document count, replacing the old per-document ``remove_document``
            # loop that issued several queries each and held row locks for the
            # whole loop inside this single transaction — a multi-thousand-
            # document corpus could hit the DB statement/connection timeout
            # (issue #1951).
            trashed = cls.bulk_soft_delete_documents(corpus, doc_ids, user)

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

    @classmethod
    def bulk_soft_delete_documents(
        cls,
        corpus: Corpus,
        document_ids: Iterable[int],
        user: User,
    ) -> int:
        """Bulk soft-delete (move to Trash) every active path of the given docs.

        This is the shared **bulk-trash primitive** behind
        :meth:`empty_corpus` and
        ``FolderCRUDService._trash_documents_in_subtree`` (folder cascade-delete)
        — the batched counterpart of ``Corpus.remove_document(document=...)``.
        For every active, non-deleted ``DocumentPath`` of the in-scope documents
        it:

        1. flips the current row to ``is_current=False`` (one bulk ``UPDATE``),
        2. inserts an immutable soft-delete history node
           (``is_deleted=True, is_current=True``, parented to the superseded
           row) via a single ``bulk_create``, then
        3. replays the ``post_save(created=True)`` signal for each new row — the
           same mechanism the bulk move/reconcile paths use — so the
           document-text embedding and ``Readme.CAML`` cache-refresh
           side-effects fire exactly as they do on the per-document path, and
        4. revokes ``is_public`` on documents no longer in any public corpus
           (the batched equivalent of ``Corpus.remove_document``'s tail).

        The query count is independent of the document count (a fixed handful of
        statements instead of several per document), so it stays well clear of
        the statement/connection timeout the per-document loop risked on
        multi-thousand-document corpora (issue #1951). Restorability is
        unchanged: the history nodes are identical to those
        ``Corpus.remove_document`` produces, so trashed documents stay in the
        trash listing and remain restorable.

        NOTE: This is an internal primitive that performs **no permission
        check** — callers (``empty_corpus``, folder cascade-delete) must already
        have verified corpus DELETE permission. It does not touch the folder
        tree; folder teardown stays with the caller.

        Args:
            corpus: Corpus the documents live in.
            document_ids: Documents whose active paths should be trashed. ALL
                active, non-deleted paths of each document in this corpus are
                soft-deleted (matching ``remove_document(document=...)``).
            user: User performing the operation (creator/audit on the new
                history nodes).

        Returns:
            Number of distinct documents moved to trash.
        """
        from opencontractserver.corpuses.services.paths import CorpusPathService
        from opencontractserver.documents.models import Document, DocumentPath

        document_ids = list(document_ids)
        if not document_ids:
            return 0

        # Self-contained transaction so a standalone/test caller still gets
        # all-or-nothing semantics; when invoked from within a caller's
        # ``transaction.atomic()`` (empty_corpus, folder cascade-delete) this is
        # a cheap nested savepoint — matching ``Corpus.remove_document``'s own
        # self-contained design.
        with transaction.atomic():
            # Lock + load the active head paths in one query. ``of=("self",)``
            # locks only the DocumentPath rows (not the joined Document), and
            # ``select_related("document")`` caches ``document`` so the replayed
            # embedding signal (which reads ``instance.document``) doesn't issue
            # a query per row.
            #
            # ``document_ids`` is a caller-supplied snapshot (e.g. empty_corpus's
            # ``values_list``); this locked SELECT re-validates active state, so a
            # document concurrently trashed/removed after the snapshot is simply
            # absent here (skipped, never double-trashed) and one added after it
            # is left alone — the same semantics as the prior per-document loop.
            active_paths = list(
                DocumentPath.objects.select_for_update(of=("self",))
                .select_related("document")
                .filter(
                    corpus=corpus,
                    document_id__in=document_ids,
                    is_current=True,
                    is_deleted=False,
                )
                .order_by("pk")
            )
            if not active_paths:
                return 0

            # Distinct documents in scope — derived purely from the locked
            # ``active_paths``, so compute it once up front (clearer data flow
            # than recomputing after the writes).
            trashed_doc_ids = {p.document_id for p in active_paths}

            # 1) Supersede every current head in a single UPDATE. This bulk
            #    ``.update()`` deliberately skips the per-row
            #    ``post_save(created=False)`` that ``remove_document``'s
            #    ``save(update_fields=["is_current"])`` would fire — safe because
            #    every DocumentPath post_save receiver either early-returns on
            #    created=False or recomputes from the new head created in step 2
            #    (see the superseded-rows INVARIANT on
            #    ``_dispatch_document_path_created_signals``).
            DocumentPath.objects.filter(pk__in=[p.pk for p in active_paths]).update(
                is_current=False
            )

            # 2) Insert the soft-delete successor nodes in a single bulk_create.
            #    Passing ``document=p.document`` / ``corpus=corpus`` keeps those
            #    related objects cached on the new rows for the signal replay
            #    below (no per-row dereference query). The fields mirror exactly
            #    what ``Corpus.remove_document`` writes for a soft delete.
            deleted_rows = [
                DocumentPath(
                    document=p.document,
                    corpus=corpus,
                    folder_id=p.folder_id,
                    path=p.path,
                    version_number=p.version_number,
                    parent=p,
                    is_deleted=True,
                    is_current=True,
                    creator=user,
                )
                for p in active_paths
            ]
            created = DocumentPath.objects.bulk_create(deleted_rows)

            # 3) bulk_create bypasses per-row post_save; replay it so the
            #    embedding + CAML-cache side-effects fire (same helper the bulk
            #    move/reconcile paths use). Both receivers defer their actual
            #    work via ``transaction.on_commit``, so dispatching here (before
            #    commit / before the step-4 revocation) is rollback-safe: if this
            #    atomic block rolls back, Django discards those on_commit
            #    callbacks and no embedding job runs for uncommitted rows.
            CorpusPathService._dispatch_document_path_created_signals(created)

            # 4) Revoke is_public for documents no longer in any public corpus —
            #    one query pair for the whole batch (mirrors the tail of
            #    ``Corpus.remove_document``). Runs after the writes above so the
            #    just-trashed heads are already ``is_current=False`` and are
            #    correctly excluded from the "still public" probe.
            if corpus.is_public:
                still_in_public = set(
                    DocumentPath.objects.filter(
                        document_id__in=trashed_doc_ids,
                        corpus__is_public=True,
                        is_current=True,
                        is_deleted=False,
                    ).values_list("document_id", flat=True)
                )
                revoke_ids = [d for d in trashed_doc_ids if d not in still_in_public]
                if revoke_ids:
                    Document.objects.filter(id__in=revoke_ids, is_public=True).update(
                        is_public=False
                    )

        logger.info(
            "Bulk soft-deleted %s document(s) in corpus %s by user %s",
            len(trashed_doc_ids),
            corpus.id,
            user.id,
        )
        return len(trashed_doc_ids)
