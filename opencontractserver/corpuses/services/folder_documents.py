"""Document-in-folder placement and queries for the corpus service layer.

``FolderDocumentService`` owns the relationship between documents and folders:
listing the documents in a folder, counting them, finding a document's current
folder, and moving documents between folders. Moves are implemented as
immutable :class:`DocumentPath` history nodes via
:class:`~opencontractserver.corpuses.services.paths.CorpusPathService`.

Folder CRUD and the folder tree live in the sibling
:class:`~opencontractserver.corpuses.services.folders.FolderCRUDService`.

Split out of the former ``corpus_objs_service.py`` monolith — see
``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``
(issue #1716, service-layer centralization Phase 2).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from opencontractserver.constants.document_processing import PATH_CONFLICT_MSG
from opencontractserver.corpuses.services.corpus_documents import (
    CorpusDocumentService,
)
from opencontractserver.corpuses.services.paths import CorpusPathService
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus, CorpusFolder
    from opencontractserver.documents.models import Document
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class FolderDocumentService(BaseService):
    """Document-in-folder listing, counting, lookup, and move operations.

    Read methods require corpus READ; the move operations require corpus
    UPDATE.
    """

    @classmethod
    def get_folder_documents(
        cls,
        user: User,
        corpus_id: int,
        folder_id: int | None = None,
        include_deleted: bool = False,
        *,
        request: Any = None,
    ) -> QuerySet[Document]:
        """
        Get documents in a specific folder with permission filtering.

        Args:
            user: Requesting user
            corpus_id: ID of corpus context
            folder_id: Folder ID to get documents from
                       None = corpus root (documents with no folder)
            include_deleted: If True, include soft-deleted documents

        Returns:
            QuerySet of Document objects, empty if no access

        Permissions:
            Requires corpus READ permission
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document, DocumentPath

        # Get corpus and check permission
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return Document.objects.none()

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
            return Document.objects.none()

        # Build filters for DocumentPath
        path_filters = Q(corpus_id=corpus_id, is_current=True)
        if not include_deleted:
            path_filters &= Q(is_deleted=False)

        if folder_id is None:
            # Root level: documents with no folder
            path_filters &= Q(folder__isnull=True)
        else:
            path_filters &= Q(folder_id=folder_id)

        # Get document IDs from DocumentPath
        doc_ids = DocumentPath.objects.filter(path_filters).values_list(
            "document_id", flat=True
        )

        return Document.objects.filter(id__in=doc_ids).select_related("creator")

    @classmethod
    def get_folder_document_ids(
        cls,
        user: User,
        corpus_id: int,
        folder_id: int | None = None,
        *,
        request: Any = None,
    ) -> set[int]:
        """
        Get document IDs in a folder (optimized for filtering).

        This is a lightweight version of get_folder_documents that returns
        only IDs, useful for QuerySet filtering.

        Args:
            user: Requesting user
            corpus_id: ID of corpus context
            folder_id: Folder ID (None = root level)

        Returns:
            Set of document IDs in the folder
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import DocumentPath

        # Get corpus and check permission
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return set()

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
            return set()

        # Build filters for DocumentPath
        path_filters = Q(corpus_id=corpus_id, is_current=True, is_deleted=False)
        if folder_id is None:
            path_filters &= Q(folder__isnull=True)
        else:
            path_filters &= Q(folder_id=folder_id)

        return set(
            DocumentPath.objects.filter(path_filters).values_list(
                "document_id", flat=True
            )
        )

    @classmethod
    def get_folder_document_count(
        cls,
        user: User,
        folder: CorpusFolder,
        include_descendants: bool = False,
        *,
        request: Any = None,
    ) -> int:
        """
        Get count of documents in folder.

        Uses the optimized CorpusFolder.get_document_count() method
        which properly handles dual-system filtering.

        Args:
            user: Requesting user
            folder: Folder to count documents in
            include_descendants: If True, include documents in subfolders

        Returns:
            Document count, 0 if no access
        """
        if not folder.corpus.user_can(user, PermissionTypes.READ, request=request):
            return 0

        if include_descendants:
            return folder.get_descendant_document_count()
        return folder.get_document_count()

    @classmethod
    def move_document_to_folder(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
        folder: CorpusFolder | None = None,
        *,
        request: Any = None,
    ) -> tuple[bool, str]:
        """
        Move single document to folder, creating a new DocumentPath history node.

        This creates a new DocumentPath record linked to the previous one via
        ``parent``, implementing the path tree audit trail:

        - Every lifecycle event creates a new node (immutable history).
        - Each new node links to its predecessor via ``parent`` for traversal.
        - The old node is marked ``is_current=False`` so only one node is active.
        - ``version_number`` is preserved (moves do not bump the version).

        **TOCTOU race recovery**: The successor insert runs in a savepoint
        and is retried (with a freshly disambiguated path) on
        ``IntegrityError`` from the ``unique_active_path_per_corpus``
        partial unique index — see ``_create_successor_path_with_retry``.

        Args:
            user: Moving user
            document: Document to move
            corpus: Corpus context
            folder: Target folder (None = move to root)

        Returns:
            (success, error_message)

        Validations:
            - User has corpus UPDATE permission
            - Document belongs to corpus
            - Folder (if provided) belongs to corpus
        """
        from opencontractserver.documents.models import DocumentPath

        # Permission check
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
            return (
                False,
                "Permission denied: You do not have write access to this corpus",
            )

        # Validate document belongs to corpus
        if not CorpusDocumentService._check_document_in_corpus(document, corpus):
            return False, "Document does not belong to this corpus"

        # Validate folder belongs to corpus
        if folder is not None and folder.corpus_id != corpus.id:
            return False, "Target folder does not belong to this corpus"

        # Outer transaction holds the select_for_update lock on `current`
        # across the inner savepoint so no other operation can modify this
        # path while we create the successor node.
        with transaction.atomic():
            current = (
                DocumentPath.objects.select_for_update(of=("self",))
                .filter(
                    document=document,
                    corpus=corpus,
                    is_current=True,
                    is_deleted=False,
                )
                .first()
            )

            if not current:
                return False, "No active document path found"

            # Skip if already in the target folder
            if current.folder_id == (folder.id if folder else None):
                return True, ""

            # Compute new base path reflecting the folder location.
            # Note: _compute_moved_path extracts only the filename;
            # intermediate directory segments are dropped (the new path is
            # derived entirely from the target folder's tree position).
            try:
                base_path = CorpusPathService._compute_moved_path(current.path, folder)
            except ValueError as exc:
                return False, str(exc)

            # Disambiguate + create with TOCTOU race recovery: the helper
            # retries on IntegrityError from the unique_active_path_per_corpus
            # partial unique constraint, treating each losing path as
            # occupied so the next attempt picks a different suffix.
            try:
                CorpusPathService._create_successor_path_with_retry(
                    current=current,
                    corpus=corpus,
                    folder=folder,
                    base_path=base_path,
                    user=user,
                )
            except ValueError as exc:
                return False, str(exc)
            except IntegrityError as exc:
                logger.warning(
                    "IntegrityError creating path for document %s in "
                    "corpus %s after exhausting retries — concurrent path "
                    "conflict could not be resolved: %s",
                    document.id,
                    corpus.id,
                    exc,
                )
                return False, f"{PATH_CONFLICT_MSG}, please retry: {exc}"

            logger.info(
                f"Moved document {document.id} to folder {folder.id if folder else 'root'} "
                f"in corpus {corpus.id} by user {user.id}"
            )
            return True, ""

    @classmethod
    def move_documents_to_folder(
        cls,
        user: User,
        document_ids: list[int],
        corpus: Corpus,
        folder: CorpusFolder | None = None,
        *,
        request: Any = None,
    ) -> tuple[int, str]:
        """
        Bulk move documents to folder, creating DocumentPath history nodes.

        Each document gets a new DocumentPath record linked to its previous one,
        implementing the path tree audit trail (see ``move_document_to_folder``
        for design rationale).

        **Atomicity guarantee**: The entire batch runs inside a single
        ``transaction.atomic()`` block.  If ANY document fails to move
        (e.g. path disambiguation exhausted, integrity constraint violation,
        within-batch path conflict), the entire transaction is rolled back —
        no documents are moved.  This prevents partial-success states where
        some documents end up in the target folder while others remain in
        their original locations.

        **Within-batch conflict detection**: All target paths are planned
        in a single pass before any DB writes.  A shared ``occupied_paths``
        set (pre-fetched once via ``_fetch_occupied_paths_in_directory``)
        is mutated after each disambiguation so that two documents with
        the same filename (e.g. two ``report.pdf`` files being moved to
        the same folder) receive distinct suffixes.

        **TOCTOU race note**: A concurrent transaction can claim a path
        between the occupied-paths pre-fetch and the ``bulk_create``.
        If that happens, the ``unique_active_path_per_corpus`` partial
        unique constraint raises ``IntegrityError``, which rolls back
        the entire batch.  The caller can safely retry because the full
        rollback leaves the database in its original state.

        **Retry safety**: Because a failed call leaves the database in its
        original state (full rollback), the caller can safely retry the
        operation without risk of double-moving already-relocated documents.

        Args:
            user: Moving user
            document_ids: List of document IDs to move
            corpus: Corpus context
            folder: Target folder (None = move to root)

        Returns:
            (moved_count, error_message) — ``moved_count`` reflects only
            documents that were actually relocated (documents already in the
            target folder are skipped and not counted).  On failure,
            ``moved_count`` is 0 because the transaction is rolled back.

        Validations:
            - User has corpus UPDATE permission
            - All documents belong to corpus
            - Folder (if provided) belongs to corpus
        """
        from opencontractserver.documents.models import DocumentPath

        # Permission check
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
            return 0, "Permission denied: You do not have write access to this corpus"

        # Validate folder belongs to corpus
        if folder is not None and folder.corpus_id != corpus.id:
            return 0, "Target folder does not belong to this corpus"

        target_folder_id = folder.id if folder else None

        try:
            with transaction.atomic():
                # Get all current paths for these documents.
                # ORDER BY pk to acquire row locks in a deterministic order,
                # preventing deadlocks when concurrent calls overlap on the
                # same document set.  select_related("document") avoids an
                # N+1 when building successor rows (``current.document`` is
                # read for each entry in the loop below).  ``of=("self",)``
                # scopes the row lock to the DocumentPath table so we don't
                # accidentally lock Document rows for the duration of the
                # transaction.
                current_paths = list(
                    DocumentPath.objects.select_for_update(of=("self",))
                    .select_related("document")
                    .filter(
                        document_id__in=document_ids,
                        corpus=corpus,
                        is_current=True,
                        is_deleted=False,
                    )
                    .order_by("pk")
                )

                # Validate corpus membership in a single comparison against the
                # query we just ran — the filter above already proves membership
                # for each document_id present. Folded into the locked atomic
                # block so the membership check and the move are TOCTOU-coherent.
                found_doc_ids = {p.document_id for p in current_paths}
                missing = set(document_ids) - found_doc_ids
                if missing:
                    return (
                        0,
                        "The following documents do not belong to this corpus: "
                        + ", ".join(str(pk) for pk in sorted(missing)),
                    )

                # Filter to only paths that need moving
                paths_to_move = [
                    p for p in current_paths if p.folder_id != target_folder_id
                ]

                if not paths_to_move:
                    return 0, ""

                # Resolve the target folder's path once up front.  Each
                # invocation of CorpusFolder.get_path() walks ancestors via
                # a recursive CTE query, so doing it inside the loop would
                # cost O(N) round trips for an O(1) value.  We reuse the
                # same value for both _target_directory_string_from_path and
                # _compute_moved_path to guarantee exactly one CTE query.
                target_folder_path = folder.get_path() if folder is not None else None

                # Pre-fetch all occupied paths in the target directory with a
                # SINGLE query, instead of letting each _disambiguate_path call
                # re-fetch them.  Because we filtered out paths whose folder
                # already equals the target, none of ``paths_to_move`` lives
                # in the target directory — so no per-row exclusion is needed.
                #
                # ORDERING INVARIANT: this fetch MUST run before the batch
                # ``update(is_current=False)`` below.  Bulk callers pass the
                # resulting set to ``_disambiguate_path(occupied_override=...)``,
                # which silently ignores ``exclude_pk``.  Reordering these
                # steps (fetch after deactivate) would cause the batch to
                # re-claim its own source paths and produce duplicate
                # DocumentPath rows.
                target_dir = CorpusPathService._target_directory_string_from_path(
                    target_folder_path
                )
                occupied_paths = CorpusPathService._fetch_occupied_paths_in_directory(
                    corpus, target_dir
                )

                # Pre-compute all target paths and detect within-batch
                # conflicts up front.  ``occupied_paths`` is mutated after each
                # disambiguation so that two documents with the same filename
                # get distinct suffixes (within-batch conflict resolution).
                planned_paths: list[tuple[DocumentPath, str]] = []

                for current in paths_to_move:
                    # Note: _compute_moved_path extracts only the filename;
                    # intermediate directory segments are dropped.
                    new_path = CorpusPathService._compute_moved_path(
                        current.path,
                        folder,
                        target_folder_path=target_folder_path,
                    )
                    new_path = CorpusPathService._disambiguate_path(
                        new_path,
                        corpus,
                        occupied_override=occupied_paths,
                    )
                    # Claim this candidate so subsequent siblings in the same
                    # batch resolve to a different disambiguated suffix.
                    occupied_paths.add(new_path)
                    planned_paths.append((current, new_path))

                # Execute all moves in exactly TWO queries:
                #   1. Batch-deactivate every superseded path
                #   2. Batch-insert every new successor row
                # This replaces the previous O(N) save/create loop which
                # issued ~2N round-trips for a batch of N documents
                # (see issue #1199).
                old_path_pks = [current.pk for current, _ in planned_paths]
                DocumentPath.objects.filter(pk__in=old_path_pks).update(
                    is_current=False
                )

                new_path_rows = [
                    DocumentPath(
                        document=current.document,
                        corpus=corpus,
                        folder=folder,
                        path=new_path,
                        version_number=current.version_number,
                        parent=current,
                        is_current=True,
                        is_deleted=False,
                        creator=user,
                    )
                    for current, new_path in planned_paths
                ]
                created_paths = DocumentPath.objects.bulk_create(new_path_rows)

                # bulk_create bypasses per-row post_save signals, so we fire
                # them manually to preserve the text-embedding side effect
                # wired up in ``documents.signals.connect_corpus_document_signals``.
                # The handler's ``transaction.on_commit`` callbacks still run
                # against the outer atomic block, matching legacy semantics.
                CorpusPathService._dispatch_document_path_created_signals(created_paths)

                moved_count = len(created_paths)

                logger.info(
                    f"Bulk moved {moved_count} documents to folder "
                    f"{folder.id if folder else 'root'} in corpus {corpus.id} "
                    f"by user {user.id}"
                )
                return moved_count, ""

        except (ValueError, IntegrityError) as exc:
            logger.error(
                "Atomic rollback during bulk move of %d documents to "
                "folder %s in corpus %s: %s",
                len(document_ids),
                folder.id if folder else "root",
                corpus.id,
                exc,
            )
            return 0, (
                "Bulk move failed and all changes have been rolled back; "
                "the entire batch is safe to retry: "
                f"{exc}"
            )

    @classmethod
    def get_document_folder(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> CorpusFolder | None:
        """
        Get the current folder for a document in a corpus.

        Args:
            user: Requesting user
            document: Document to get folder for
            corpus: Corpus context

        Returns:
            CorpusFolder if document is in a folder, None if at root or no access
        """
        from opencontractserver.documents.models import DocumentPath

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
            return None

        try:
            path = DocumentPath.objects.select_related("folder").get(
                document=document,
                corpus=corpus,
                is_current=True,
                is_deleted=False,
            )
            return path.folder
        except DocumentPath.DoesNotExist:
            return None
