"""
DocumentFolderService - Centralized service for document and folder operations.

This service consolidates all document lifecycle and folder-related business logic
into a single, DRY, permission-aware module following the QueryOptimizer pattern.

Key Design Principles:
1. DRY Permissions: Single permission check methods used by all operations
2. Transaction Safety: All mutations wrapped in transactions
3. Query Optimization: Proper use of select_related, prefetch_related, with_tree_fields
4. IDOR Protection: Consistent error messages for not-found vs permission-denied
5. One-Stop Shop: All document CRUD, folder CRUD, and corpus operations in one place

Document Lifecycle Operations:
- create_document(): Create standalone documents (not in corpus)
- upload_document_to_corpus(): Upload new content to corpus with deduplication
- add_document_to_corpus(): Add existing document to corpus (creates isolated copy)
- remove_document_from_corpus(): Soft-delete document from corpus
- check_user_upload_quota(): Verify user can create more documents

Folder Operations:
- create_folder(), update_folder(), move_folder(), delete_folder()
- get_visible_folders(), get_folder_by_id(), get_folder_tree()

Document-in-Folder Operations:
- move_document_to_folder(), move_documents_to_folder()
- soft_delete_document(), restore_document()
- get_folder_documents(), get_deleted_documents()

Permission Model (from consolidated_permissioning_guide.md):
- CorpusFolder objects inherit ALL permissions from parent Corpus
- Write operations require: User is Corpus creator OR User has UPDATE permission
- CRITICAL: corpus.is_public=True grants READ-ONLY access, NOT write access
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.db.models.signals import post_save

from opencontractserver.constants.document_processing import (
    MAX_PATH_CREATE_RETRIES,
    MAX_PATH_DISAMBIGUATION_SUFFIX,
    PATH_CONFLICT_MSG,
)
from opencontractserver.pipeline.registry import get_allowed_mime_types
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    from opencontractserver.corpuses.models import Corpus, CorpusFolder
    from opencontractserver.documents.models import Document, DocumentPath

    User = get_user_model()

logger = logging.getLogger(__name__)


class DocumentFolderService:
    """
    Centralized service for all document lifecycle and folder operations.

    This is the ONE-STOP-SHOP for:
    - Document creation (standalone and corpus imports)
    - Document-to-corpus operations (add, remove)
    - Folder CRUD operations
    - Document-in-folder operations (move, delete, restore)
    - Permission management for documents

    Follows the QueryOptimizer pattern with:
    - Static classmethod-based API
    - Centralized permission checks
    - Transaction-safe mutations
    - Query optimization for reads

    Usage:
        # Document creation
        doc, error = DocumentFolderService.create_document(user, file_bytes, filename, title)
        doc, status, error = DocumentFolderService.upload_document_to_corpus(
            user, corpus, file_bytes, filename, title, folder=folder
        )

        # Corpus operations
        corpus_doc, status, error = DocumentFolderService.add_document_to_corpus(user, doc, corpus)
        success, error = DocumentFolderService.remove_document_from_corpus(user, doc, corpus)

        # Folder operations
        folder, error = DocumentFolderService.create_folder(user, corpus, "Name")
        success, error = DocumentFolderService.move_document_to_folder(user, doc, corpus, folder)

        # Read operations
        folders = DocumentFolderService.get_visible_folders(user, corpus_id)
        documents = DocumentFolderService.get_folder_documents(user, corpus_id, folder_id)

        # Permission checks
        can_read = DocumentFolderService.check_corpus_read_permission(user, corpus)
        can_write = DocumentFolderService.check_corpus_write_permission(user, corpus)
    """

    # =========================================================================
    # PERMISSION CHECKING - DRY methods used by all operations
    # =========================================================================

    @classmethod
    def check_corpus_read_permission(
        cls,
        user: User,
        corpus: Corpus,
    ) -> bool:
        """
        Check if user can READ the corpus (and view its folders).

        Returns True if ANY of:
        - User is superuser
        - User is corpus creator
        - Corpus is public (is_public=True)
        - User has explicit READ permission via django-guardian

        Args:
            user: The user to check permissions for
            corpus: The corpus to check access to

        Returns:
            True if user has read access, False otherwise
        """
        # Superuser has all permissions
        if user.is_superuser:
            return True

        # Anonymous users can only access public corpuses
        if user.is_anonymous:
            return corpus.is_public

        # Creator has full access
        if corpus.creator_id == user.id:
            return True

        # Public corpuses are readable by all authenticated users
        if corpus.is_public:
            return True

        # Check explicit guardian permission
        return user_has_permission_for_obj(
            user_val=user,
            instance=corpus,
            permission=PermissionTypes.READ,
            include_group_permissions=True,
        )

    @classmethod
    def check_corpus_write_permission(
        cls,
        user: User,
        corpus: Corpus,
    ) -> bool:
        """
        Check if user can WRITE to corpus (create/update/move/delete folders).

        Returns True if ANY of:
        - User is superuser
        - User is corpus creator
        - User has explicit UPDATE permission via django-guardian

        CRITICAL: corpus.is_public=True does NOT grant write access.
        This is a security-critical distinction from read access.

        Args:
            user: The user to check permissions for
            corpus: The corpus to check write access to

        Returns:
            True if user has write access, False otherwise
        """
        # Superuser has all permissions
        if user.is_superuser:
            return True

        # Anonymous users NEVER have write access
        if user.is_anonymous:
            return False

        # Creator has full access
        if corpus.creator_id == user.id:
            return True

        # CRITICAL: is_public does NOT grant write access
        # Only check explicit UPDATE permission
        return user_has_permission_for_obj(
            user_val=user,
            instance=corpus,
            permission=PermissionTypes.UPDATE,
            include_group_permissions=True,
        )

    @classmethod
    def check_corpus_delete_permission(
        cls,
        user: User,
        corpus: Corpus,
    ) -> bool:
        """
        Check if user can DELETE from corpus (delete folders, soft-delete documents).

        Returns True if ANY of:
        - User is superuser
        - User is corpus creator
        - User has explicit DELETE permission via django-guardian

        Args:
            user: The user to check permissions for
            corpus: The corpus to check delete access to

        Returns:
            True if user has delete access, False otherwise
        """
        # Superuser has all permissions
        if user.is_superuser:
            return True

        # Anonymous users NEVER have delete access
        if user.is_anonymous:
            return False

        # Creator has full access
        if corpus.creator_id == user.id:
            return True

        # Check explicit DELETE permission
        return user_has_permission_for_obj(
            user_val=user,
            instance=corpus,
            permission=PermissionTypes.DELETE,
            include_group_permissions=True,
        )

    @classmethod
    def check_document_in_corpus(
        cls,
        document: Document,
        corpus: Corpus,
    ) -> bool:
        """
        Verify that a document belongs to a corpus.

        Args:
            document: The document to check
            corpus: The corpus to check membership in

        Returns:
            True if document belongs to corpus, False otherwise
        """
        from opencontractserver.documents.models import DocumentPath

        # Check DocumentPath (source of truth for corpus membership)
        return DocumentPath.objects.filter(
            document=document,
            corpus=corpus,
        ).exists()

    # =========================================================================
    # FOLDER READ OPERATIONS
    # =========================================================================

    @classmethod
    def get_visible_folders(
        cls,
        user: User,
        corpus_id: int,
        parent_id: int | None = None,
    ) -> QuerySet[CorpusFolder]:
        """
        Get folders visible to user in a corpus.

        Returns an optimized QuerySet with tree fields and related objects
        prefetched for efficient rendering.

        Args:
            user: Requesting user
            corpus_id: ID of corpus to query folders from
            parent_id: Optional parent folder ID to filter children only
                       (None returns all folders, not just root)

        Returns:
            QuerySet of CorpusFolder objects, empty if no access

        Permissions:
            Requires corpus READ permission
        """
        from opencontractserver.corpuses.models import Corpus, CorpusFolder

        # Get corpus and check permission
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return CorpusFolder.objects.none()

        if not cls.check_corpus_read_permission(user, corpus):
            return CorpusFolder.objects.none()

        # Build optimized query
        # Note: Don't use order_by("tree_path") as tree_path is a CTE annotation
        # that requires special handling. Frontend reconstructs tree from parentId.
        qs = CorpusFolder.objects.filter(corpus_id=corpus_id).select_related(
            "corpus", "creator", "parent"
        )

        # Filter to specific parent if requested
        if parent_id is not None:
            qs = qs.filter(parent_id=parent_id)

        return qs

    @classmethod
    def get_folder_by_id(
        cls,
        user: User,
        folder_id: int,
    ) -> CorpusFolder | None:
        """
        Get single folder by ID with permission check.

        Implements IDOR protection by returning None for both
        not-found and permission-denied cases.

        Args:
            user: Requesting user
            folder_id: ID of folder to retrieve

        Returns:
            CorpusFolder if found and accessible, None otherwise
        """
        from opencontractserver.corpuses.models import CorpusFolder

        try:
            folder = CorpusFolder.objects.select_related(
                "corpus", "creator", "parent"
            ).get(id=folder_id)
        except CorpusFolder.DoesNotExist:
            return None

        # Check corpus permission (folders inherit from corpus)
        if not cls.check_corpus_read_permission(user, folder.corpus):
            return None

        return folder

    @classmethod
    def get_folder_tree(
        cls,
        user: User,
        corpus_id: int,
    ) -> list[dict]:
        """
        Get full folder tree for corpus as nested dictionary structure.

        Optimized to use a single query and build tree in Python.

        Args:
            user: Requesting user
            corpus_id: ID of corpus to get tree for

        Returns:
            List of root folder dicts with nested children:
            [
                {
                    "id": 1,
                    "name": "Contracts",
                    "path": "/Contracts",
                    "documentCount": 5,
                    "children": [...]
                }
            ]
        """
        folders = cls.get_visible_folders(user, corpus_id)

        # Build lookup dict
        folder_dict: dict[int, dict] = {}
        for folder in folders:
            folder_dict[folder.id] = {
                "id": folder.id,
                "name": folder.name,
                "path": folder.get_path(),
                "documentCount": folder.get_document_count(),
                "parentId": folder.parent_id,
                "children": [],
            }

        # Build tree structure
        roots: list[dict] = []
        for folder_id, folder_data in folder_dict.items():
            parent_id = folder_data.get("parentId")
            if parent_id and parent_id in folder_dict:
                folder_dict[parent_id]["children"].append(folder_data)
            else:
                roots.append(folder_data)

        return roots

    # =========================================================================
    # DOCUMENT-IN-FOLDER READ OPERATIONS
    # =========================================================================

    @classmethod
    def get_folder_documents(
        cls,
        user: User,
        corpus_id: int,
        folder_id: int | None = None,
        include_deleted: bool = False,
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

        if not cls.check_corpus_read_permission(user, corpus):
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

        if not cls.check_corpus_read_permission(user, corpus):
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
    def get_deleted_documents(
        cls,
        user: User,
        corpus_id: int,
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

        if not cls.check_corpus_read_permission(user, corpus):
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
    def get_folder_document_count(
        cls,
        user: User,
        folder: CorpusFolder,
        include_descendants: bool = False,
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
        if not cls.check_corpus_read_permission(user, folder.corpus):
            return 0

        if include_descendants:
            return folder.get_descendant_document_count()
        return folder.get_document_count()

    # =========================================================================
    # FOLDER WRITE OPERATIONS
    # =========================================================================

    @classmethod
    def create_folder(
        cls,
        user: User,
        corpus: Corpus,
        name: str,
        parent: CorpusFolder | None = None,
        description: str = "",
        color: str | None = None,
        icon: str | None = None,
        tags: list[str] | None = None,
        is_public: bool = False,
    ) -> tuple[CorpusFolder | None, str]:
        """
        Create a new folder in corpus.

        Args:
            user: Creating user
            corpus: Parent corpus
            name: Folder name (must be unique within parent)
            parent: Parent folder (None = create at root level)
            description: Optional description
            color: Hex color for UI (e.g., "#3B82F6")
            icon: Icon identifier for UI
            tags: List of tags
            is_public: Whether folder is publicly visible

        Returns:
            (folder, error_message) - folder is None on error

        Validations:
            - User has corpus UPDATE permission
            - Name is unique within parent
            - Parent (if provided) is in same corpus

        Example:
            folder, error = DocumentFolderService.create_folder(
                user=request.user,
                corpus=corpus,
                name="Contracts",
                parent=legal_folder,
            )
            if error:
                return {"ok": False, "message": error}
        """
        from opencontractserver.corpuses.models import CorpusFolder

        # Permission check
        if not cls.check_corpus_write_permission(user, corpus):
            return (
                None,
                "Permission denied: You do not have write access to this corpus",
            )

        # Validate parent belongs to same corpus
        if parent is not None and parent.corpus_id != corpus.id:
            return None, "Parent folder must be in the same corpus"

        # Validate unique name within parent
        exists = CorpusFolder.objects.filter(
            corpus=corpus,
            parent=parent,
            name=name,
        ).exists()
        if exists:
            return None, f"A folder named '{name}' already exists in this location"

        # Create folder
        with transaction.atomic():
            folder = CorpusFolder.objects.create(
                corpus=corpus,
                parent=parent,
                name=name,
                description=description,
                color=color or "",
                icon=icon or "",
                tags=tags or [],
                is_public=is_public,
                creator=user,
            )
            logger.info(
                f"Created folder '{name}' (id={folder.id}) in corpus {corpus.id} by user {user.id}"
            )
            return folder, ""

    @classmethod
    def update_folder(
        cls,
        user: User,
        folder: CorpusFolder,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        tags: list[str] | None = None,
    ) -> tuple[bool, str]:
        """
        Update folder properties.

        Args:
            user: Updating user
            folder: Folder to update
            name: New name (if changing)
            description: New description
            color: New color
            icon: New icon
            tags: New tags list

        Returns:
            (success, error_message)

        Validations:
            - User has corpus UPDATE permission
            - Name uniqueness within parent (if name is changing)
        """
        from opencontractserver.corpuses.models import CorpusFolder

        # Permission check
        if not cls.check_corpus_write_permission(user, folder.corpus):
            return (
                False,
                "Permission denied: You do not have write access to this corpus",
            )

        # Validate name uniqueness if changing
        if name is not None and name != folder.name:
            exists = (
                CorpusFolder.objects.filter(
                    corpus=folder.corpus,
                    parent=folder.parent,
                    name=name,
                )
                .exclude(id=folder.id)
                .exists()
            )
            if exists:
                return False, f"A folder named '{name}' already exists in this location"

        # Update folder
        with transaction.atomic():
            if name is not None:
                folder.name = name
            if description is not None:
                folder.description = description
            if color is not None:
                folder.color = color
            if icon is not None:
                folder.icon = icon
            if tags is not None:
                folder.tags = tags

            folder.save()
            logger.info(f"Updated folder {folder.id} by user {user.id}")
            return True, ""

    @classmethod
    def move_folder(
        cls,
        user: User,
        folder: CorpusFolder,
        new_parent: CorpusFolder | None = None,
    ) -> tuple[bool, str]:
        """
        Move folder to new parent.

        Args:
            user: Moving user
            folder: Folder to move
            new_parent: New parent folder (None = move to root)

        Returns:
            (success, error_message)

        Validations:
            - User has corpus UPDATE permission
            - Cannot move folder into itself
            - Cannot move folder into its descendants
            - New parent must be in same corpus
        """
        # Permission check
        if not cls.check_corpus_write_permission(user, folder.corpus):
            return (
                False,
                "Permission denied: You do not have write access to this corpus",
            )

        # Cannot move to itself
        if new_parent is not None and new_parent.id == folder.id:
            return False, "Cannot move a folder into itself"

        # Cannot move into descendants
        if new_parent is not None:
            descendants = folder.descendants()
            if descendants.filter(id=new_parent.id).exists():
                return False, "Cannot move a folder into one of its descendants"

            # Validate same corpus
            if new_parent.corpus_id != folder.corpus_id:
                return False, "Cannot move folder to a different corpus"

        # Move folder
        with transaction.atomic():
            folder.parent = new_parent
            folder.save()
            logger.info(
                f"Moved folder {folder.id} to parent {new_parent.id if new_parent else 'root'} by user {user.id}"
            )
            return True, ""

    @classmethod
    def delete_folder(
        cls,
        user: User,
        folder: CorpusFolder,
        move_children_to_parent: bool = True,
    ) -> tuple[bool, str]:
        """
        Delete folder, atomically relocating all contained documents to root.

        **Atomicity guarantee**: The entire operation (document relocations,
        child folder reparenting, and folder deletion) runs inside a single
        ``transaction.atomic()`` block.  If ANY document cannot be relocated
        (e.g. path disambiguation exhausted, integrity constraint violation),
        the entire transaction is rolled back — no documents are moved, no
        child folders are reparented, and the folder is NOT deleted.  This
        prevents partial-success states where some documents end up at root
        while others remain stuck in the folder.

        **Retry safety**: Because a failed call leaves the database in its
        original state (full rollback), the caller can safely retry the
        operation without risk of double-moving already-relocated documents.

        Args:
            user: Deleting user
            folder: Folder to delete
            move_children_to_parent: If True, reparent child folders to this folder's parent
                                     If False, cascade delete child folders

        Returns:
            (success, error_message).  Returns ``(False, ...)`` if any
            document in the folder cannot be relocated to root — in that
            case the entire transaction is rolled back and no changes are
            persisted.

        Side Effects:
            - Documents in folder have their folder assignment removed (moved to root)
            - Child folders are either reparented or deleted based on flag

        Permissions:
            Requires corpus DELETE permission
        """
        from opencontractserver.documents.models import DocumentPath

        # Permission check
        if not cls.check_corpus_delete_permission(user, folder.corpus):
            return (
                False,
                "Permission denied: You do not have delete access to this corpus",
            )

        try:
            with transaction.atomic():
                # Handle child folders
                if move_children_to_parent:
                    # Reparent children to this folder's parent
                    folder.children.update(parent=folder.parent)
                # else: cascade delete will handle children automatically

                # Move documents in folder to root with history tracking.
                # select_related("document") + of=("self",) match the pattern
                # in move_documents_to_folder — see that method for the
                # rationale (N+1 avoidance, scoped row locking).
                affected_paths = list(
                    DocumentPath.objects.select_for_update(of=("self",))
                    .select_related("document")
                    .filter(
                        folder=folder,
                        is_current=True,
                        is_deleted=False,
                    )
                    .order_by("pk")
                )

                if affected_paths:
                    corpus = folder.corpus
                    # Pre-fetch all occupied paths at the corpus root with a
                    # SINGLE query, replacing the previous per-document
                    # _disambiguate_path fetch.  Because we filter to rows
                    # whose ``folder=folder`` (not root), none of
                    # ``affected_paths`` live in the root directory, so no
                    # per-row exclusion is needed — the shared mutable set
                    # captures within-batch claims on the fly (issue #1199).
                    #
                    # ORDERING INVARIANT: this fetch MUST run before the batch
                    # ``update(is_current=False)`` below.  We rely on the
                    # superseded rows still being ``is_current=True`` at fetch
                    # time so they appear in ``occupied_paths``; the shared
                    # set is then treated as authoritative by
                    # ``_disambiguate_path(occupied_override=...)``, which
                    # silently ignores ``exclude_pk``.  Reordering these two
                    # steps (fetch after deactivate) would cause the batch to
                    # re-claim its own source paths and produce duplicate
                    # DocumentPath rows.
                    occupied_paths = cls._fetch_occupied_paths_in_directory(corpus, "/")

                    planned_paths: list[tuple[DocumentPath, str]] = []
                    for current in affected_paths:
                        # Note: _compute_moved_path extracts only the filename;
                        # intermediate directory segments are dropped (the new
                        # path is derived from the target folder's tree position).
                        new_path = cls._compute_moved_path(current.path, None)
                        new_path = cls._disambiguate_path(
                            new_path,
                            corpus,
                            occupied_override=occupied_paths,
                        )
                        occupied_paths.add(new_path)
                        planned_paths.append((current, new_path))

                    # Execute all relocations in exactly TWO queries instead
                    # of ~2N individual save/create round-trips.
                    old_path_pks = [current.pk for current, _ in planned_paths]
                    DocumentPath.objects.filter(pk__in=old_path_pks).update(
                        is_current=False
                    )

                    new_path_rows = [
                        DocumentPath(
                            document=current.document,
                            corpus=corpus,
                            folder=None,  # Moved to root
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
                    cls._dispatch_document_path_created_signals(created_paths)

                # Delete folder — safe because all documents were relocated.
                folder_id = folder.id
                folder.delete()

                logger.info(f"Deleted folder {folder_id} by user {user.id}")
                return True, ""

        except (ValueError, IntegrityError) as exc:
            logger.error(
                "Atomic rollback during folder %s deletion in corpus %s: %s",
                folder.id,
                folder.corpus_id,
                exc,
            )
            return False, (
                "Cannot delete folder: document relocation failed and all "
                "changes have been rolled back; the entire deletion is "
                "safe to retry: "
                f"{exc}"
            )

    # =========================================================================
    # DOCUMENT-IN-FOLDER WRITE OPERATIONS
    # =========================================================================

    @classmethod
    def move_document_to_folder(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
        folder: CorpusFolder | None = None,
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
        if not cls.check_corpus_write_permission(user, corpus):
            return (
                False,
                "Permission denied: You do not have write access to this corpus",
            )

        # Validate document belongs to corpus
        if not cls.check_document_in_corpus(document, corpus):
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
                base_path = cls._compute_moved_path(current.path, folder)
            except ValueError as exc:
                return False, str(exc)

            # Disambiguate + create with TOCTOU race recovery: the helper
            # retries on IntegrityError from the unique_active_path_per_corpus
            # partial unique constraint, treating each losing path as
            # occupied so the next attempt picks a different suffix.
            try:
                cls._create_successor_path_with_retry(
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
        from opencontractserver.documents.models import Document, DocumentPath

        # Permission check
        if not cls.check_corpus_write_permission(user, corpus):
            return 0, "Permission denied: You do not have write access to this corpus"

        # Validate folder belongs to corpus
        if folder is not None and folder.corpus_id != corpus.id:
            return 0, "Target folder does not belong to this corpus"

        # Get documents
        documents = Document.objects.filter(id__in=document_ids)

        # Validate all documents belong to corpus
        for doc in documents:
            if not cls.check_document_in_corpus(doc, corpus):
                return 0, f"Document {doc.id} does not belong to this corpus"

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
                target_dir = cls._target_directory_string_from_path(target_folder_path)
                occupied_paths = cls._fetch_occupied_paths_in_directory(
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
                    new_path = cls._compute_moved_path(
                        current.path,
                        folder,
                        target_folder_path=target_folder_path,
                    )
                    new_path = cls._disambiguate_path(
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
                cls._dispatch_document_path_created_signals(created_paths)

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

    @staticmethod
    def _compute_moved_path(
        current_path: str,
        target_folder: CorpusFolder | None,
        target_folder_path: str | None = None,
    ) -> str:
        """
        Compute the new path string when moving a document to a different folder.

        Extracts the **filename only** (last segment after the final ``/``) from
        the current path and prepends the target folder's path, or places at root
        if ``target_folder`` is ``None``.  All intermediate directory segments
        from the original path are intentionally dropped — the new path is
        derived entirely from the target folder's tree position.

        Examples::

            _compute_moved_path("/old/dir/report.pdf", folder_with_path_Legal)
            # => "/Legal/report.pdf"  (intermediate "old/dir" dropped)

            _compute_moved_path("/report.pdf", None)
            # => "/report.pdf"  (root placement)

        Args:
            current_path: Current DocumentPath.path value (e.g. "/documents/report.pdf")
            target_folder: Target folder (None = corpus root)
            target_folder_path: Pre-computed value of ``target_folder.get_path()``.
                Pass this when invoking the method many times for the same target
                folder (e.g. inside a bulk move loop) to avoid repeated O(depth)
                ancestor traversals — ``get_path()`` issues a recursive CTE
                query on every call.  Ignored when ``target_folder`` is ``None``.
                When ``None`` (the default), the path is computed on demand via
                ``target_folder.get_path()``.  Only ``None`` triggers the
                fallback — any other value (including empty string) is used
                as-is.  The value need not be pre-stripped of leading/trailing
                slashes — ``.strip("/")`` is applied internally.

        Returns:
            New path string (e.g. "/Legal/report.pdf" or "/report.pdf")
        """
        # Guard against empty, whitespace-only, or root-only paths early.
        if not current_path or not current_path.strip() or current_path.strip() == "/":
            raise ValueError(
                f"Cannot extract filename from path {current_path!r} — "
                f"empty or root-only paths are not supported"
            )

        # Extract filename (last segment of path)
        filename = (
            current_path.rsplit("/", 1)[-1] if "/" in current_path else current_path
        )

        # Secondary guard: the rsplit may produce an empty filename for paths
        # like "/dir/" (trailing slash).
        if not filename:
            raise ValueError(
                f"Cannot extract filename from path {current_path!r} — "
                f"empty or root-only paths are not supported"
            )

        if target_folder:
            folder_path = (
                target_folder.get_path()
                if target_folder_path is None
                else target_folder_path
            ).strip("/")
            return f"/{folder_path}/{filename}"
        else:
            return f"/{filename}"

    @staticmethod
    def _target_directory_string_from_path(
        folder_path: str | None,
    ) -> str:
        """
        Return a canonical directory string from a folder path string.

        Normalises the path by stripping leading/trailing slashes and
        wrapping with ``/prefix/`` format, matching the format that
        ``_fetch_occupied_paths_in_directory`` expects.

        - ``None`` (root) → ``"/"``
        - ``"Legal/Contracts"`` → ``"/Legal/Contracts/"``
        """
        if folder_path is None:
            return "/"
        # Normalise "/" (the root-equivalent path string that
        # ``CorpusFolder.get_path()`` may return for a root folder) to the
        # canonical root directory rather than raising — callers should
        # not need to know that ``None`` is the internal root sentinel.
        if folder_path == "/":
            return "/"
        stripped = folder_path.strip("/")
        if not stripped:
            raise ValueError(
                "_target_directory_string_from_path: folder_path is empty "
                f"after stripping slashes (original: {folder_path!r})"
            )
        return f"/{stripped}/"

    @staticmethod
    def _dispatch_document_path_created_signals(
        paths: list[DocumentPath],
    ) -> None:
        """
        Manually dispatch ``post_save`` (``created=True``) for rows created via
        :meth:`DocumentPath.objects.bulk_create`.

        ``bulk_create`` bypasses per-row ``pre_save``/``post_save`` signal
        delivery, which would silently drop the document-text embedding
        side-effect wired up in
        ``documents.signals.process_doc_on_document_path_create``.  Bulk
        write paths replicate the single-row semantics by sending the signal
        themselves after the INSERT.

        Note: only ``post_save`` is replayed here. ``pre_save`` is still
        skipped — consistent with ``bulk_create``'s own contract and
        acceptable today because ``DocumentPath`` has no registered
        ``pre_save`` receivers. If a ``pre_save`` receiver is added in the
        future (e.g. to auto-populate a field or stamp a timestamp), this
        method must be extended to dispatch it before the INSERT rather
        than after.

        Args:
            paths: DocumentPath instances returned by ``bulk_create``.
        """
        # Nested import to avoid circular dependency during app initialization.
        from opencontractserver.documents.models import DocumentPath

        # All kwargs match what Django's ``Model.save()`` dispatches for a
        # newly created instance: ``created=True``, ``update_fields=None``,
        # ``raw=False``, and the actual database alias from ``_state.db``.
        # Passing ``update_fields`` explicitly (rather than omitting it)
        # ensures future signal handlers that declare it as an explicit
        # keyword argument won't raise ``TypeError``.
        for path in paths:
            post_save.send(
                sender=DocumentPath,
                instance=path,
                created=True,
                update_fields=None,
                raw=False,
                using=path._state.db,
            )

    @staticmethod
    def _fetch_occupied_paths_in_directory(
        corpus: Corpus,
        directory: str,
        exclude_pk: int | None = None,
    ) -> set[str]:
        """
        Fetch the set of occupied active-path strings in a single directory.

        Performs a **single** SQL query that matches immediate children of
        ``directory`` only (not nested subdirectories).  Used both by the
        single-doc disambiguation fast path and by batch operations that
        need to pre-fetch the entire target directory once, instead of
        once per document.

        Args:
            corpus: Corpus to query.
            directory: Directory string terminated by ``/`` (e.g. ``/Target/``
                       for folder ``Target``, or ``/`` for corpus root). An
                       empty string raises ``ValueError`` to surface caller
                       bugs that would otherwise trigger a full-table scan.
            exclude_pk: Optional DocumentPath PK to exclude from the result
                        (e.g. the record being superseded by a single move).

        Returns:
            Set of path strings currently occupied in ``directory``.
        """
        # Nested import to avoid circular dependency:
        # folder_service -> documents.models -> corpuses.models -> folder_service
        from opencontractserver.documents.models import DocumentPath

        qs = DocumentPath.objects.filter(
            corpus=corpus,
            is_current=True,
            is_deleted=False,
        )
        # Special-case root-level paths: for directory="/", path__startswith="/"
        # would match EVERY active path in the corpus.  Instead, use a regex
        # that only matches single-segment root paths (e.g. "/report.pdf"
        # but not "/folder/report.pdf").
        #
        # NOTE: These regex filters cannot use a btree index on ``path``
        # (PostgreSQL requires anchored patterns with no alternation for
        # index-only scans).  For typical corpus sizes this is fine, but
        # corpuses with thousands of files at the same directory level may
        # benefit from a GIN/pg_trgm index or a rewrite using
        # ``path__startswith`` + a slash-count annotation.
        # TODO(perf, #1199 follow-up): file a dedicated issue if this regex
        # scan shows up in profiling on large directories before adding an
        # index — the btree on ``path`` is still useful for exact-match
        # lookups and we don't want to regress write throughput.
        if directory == "/":
            qs = qs.filter(path__regex=r"^/[^/]+$")
        elif directory:
            # Match only immediate children (not nested subdirectories)
            # to avoid pulling the entire subtree into memory.
            qs = qs.filter(path__regex=rf"^{re.escape(directory)}[^/]+$")
        else:
            # directory == "" means base_path had no leading slash — structurally
            # unexpected since all stored paths start with "/".  Raise rather
            # than silently loading ALL active paths, which would mask a bug
            # in the caller and degrade performance on large corpuses.
            raise ValueError(
                f"_fetch_occupied_paths_in_directory: empty directory "
                f"for corpus {corpus.id}"
            )
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return set(qs.values_list("path", flat=True))

    @classmethod
    def _disambiguate_path(
        cls,
        base_path: str,
        corpus: Corpus,
        exclude_pk: int | None = None,
        occupied_override: set[str] | None = None,
        extra_occupied: set[str] | None = None,
    ) -> str:
        """
        Generate a unique path by appending numeric suffixes when a conflict exists.

        Given a base path like ``/Target/report.pdf``, this checks for existing
        active (``is_current=True, is_deleted=False``) DocumentPath records in the
        same corpus. If the base path is taken it tries ``/Target/report_1.pdf``,
        ``/Target/report_2.pdf``, etc. until an unused path is found.

        A hard cap (``MAX_PATH_DISAMBIGUATION_SUFFIX``) prevents unbounded loops
        if many documents share the same filename in the same folder.

        **Performance**: Uses a single query (via
        :meth:`_fetch_occupied_paths_in_directory`) to pre-fetch all occupied
        paths in the target directory, then checks candidates in memory
        (O(1) per candidate instead of O(1)-per-query).  Bulk operations may
        pass ``occupied_override`` to skip the per-call query entirely and
        share a single pre-fetched set across many disambiguations.

        **Concurrency note**: The caller's ``select_for_update()`` only prevents
        two concurrent moves of the **same** document from racing.  It does NOT
        lock target-path rows — two concurrent moves of **different** documents
        to the same target folder can both observe a candidate path as free and
        race to create it.  The database's ``unique_active_path_per_corpus``
        partial unique constraint is the real safety net: the loser's ``INSERT``
        raises ``IntegrityError``, which callers handle via savepoints.

        Args:
            base_path: The ideal path string to use.
            corpus: Corpus to check for conflicts in.
            exclude_pk: Optional DocumentPath PK to exclude from conflict check
                        (the record being superseded).  Ignored when
                        ``occupied_override`` is provided — the caller is
                        responsible for filtering their own pre-fetched set.
            occupied_override: Optional pre-fetched set of occupied paths.  When
                               provided, the per-call DB query is skipped and
                               this set is used as the authoritative occupancy
                               snapshot.  Callers in bulk operations pass a
                               shared **mutable** set and append each
                               disambiguated result to it so subsequent
                               disambiguations see the within-batch claim.
            extra_occupied: Optional set of additional paths to treat as
                           occupied. Now used only by the single-document
                           retry loop in
                           :meth:`_create_successor_path_with_retry` to
                           mark paths claimed by prior failed attempts
                           within that same call; bulk callers should use
                           ``occupied_override`` instead. Merged into the
                           DB-queried set; ignored when
                           ``occupied_override`` is provided.

        Returns:
            A path string unique among active paths in the corpus (and the
            ``occupied_override`` set, if provided) *at query time*.  This is a
            best-effort check — concurrent transactions may claim the same
            path between the SELECT and INSERT (TOCTOU race).  The database's
            ``unique_active_path_per_corpus`` partial unique constraint is the
            authoritative guarantee of uniqueness; callers must handle
            ``IntegrityError`` for the rare conflict case.

        Raises:
            ValueError: If ``base_path`` lacks a leading ``/``, or if no unique
                path can be found within the suffix limit.
        """
        # All stored DocumentPath.path values start with "/".  Reject
        # slashless paths early with a clear message rather than letting
        # them propagate to _fetch_occupied_paths_in_directory where the
        # resulting empty-directory ValueError is harder to diagnose.
        if not base_path.startswith("/"):
            raise ValueError(
                f"_disambiguate_path: base_path must start with '/' "
                f"(got {base_path!r})"
            )

        if occupied_override is not None:
            # Caller pre-fetched the occupied set — skip the DB query entirely.
            # This is the hot path for bulk operations which share a single
            # fetch across N disambiguations.
            #
            # ``occupied_override`` is treated as read-only inside this method;
            # callers are responsible for appending the returned path to the
            # set after this method returns.
            occupied = occupied_override
        else:
            # Derive the directory once so that both the fetch and the candidate
            # loop agree on which namespace we're searching.  The leading-slash
            # guard above guarantees "/" is present, so rsplit always produces a
            # non-empty directory prefix (at worst "/" for root-level paths).
            directory = base_path.rsplit("/", 1)[0] + "/"

            occupied = cls._fetch_occupied_paths_in_directory(
                corpus, directory, exclude_pk=exclude_pk
            )

            # Merge in any extra occupied paths (e.g. from within-batch claims
            # during retry loops)
            if extra_occupied:
                occupied = occupied | extra_occupied

        if base_path not in occupied:
            return base_path

        # Split into stem and extension for suffix insertion.
        # We must split the *filename* segment, not the full path, so that
        # dotfiles like ".gitignore" are handled correctly (the leading dot
        # is NOT an extension separator).
        if "/" in base_path:
            dir_part, filename = base_path.rsplit("/", 1)
        else:
            dir_part, filename = None, base_path

        # Determine whether the filename has a true extension.
        # A leading dot (e.g. ".gitignore") is not an extension separator;
        # strip it before checking, then re-prepend after the split.
        bare = filename.lstrip(".")
        leading_dots = filename[: len(filename) - len(bare)]

        def _join_stem(name_part: str) -> str:
            return f"{dir_part}/{name_part}" if dir_part is not None else name_part

        if "." in bare:
            name_stem, name_ext = bare.rsplit(".", 1)
            stem = _join_stem(f"{leading_dots}{name_stem}")
            ext = f".{name_ext}"
        else:
            stem = _join_stem(filename)
            ext = ""

        for counter in range(1, MAX_PATH_DISAMBIGUATION_SUFFIX + 1):
            candidate = f"{stem}_{counter}{ext}"
            if candidate not in occupied:
                log_prefix = (
                    f"Within-batch {PATH_CONFLICT_MSG.lower()}"
                    if occupied_override is not None or extra_occupied
                    else PATH_CONFLICT_MSG
                )
                logger.warning(
                    "%s for %r in corpus %s — disambiguated to %r",
                    log_prefix,
                    base_path,
                    corpus.id,
                    candidate,
                )
                return candidate

        logger.error(
            "Path disambiguation exhausted for %r in corpus %s after %d attempts",
            base_path,
            corpus.id,
            MAX_PATH_DISAMBIGUATION_SUFFIX,
        )
        raise ValueError(
            f"Cannot find a unique path for {base_path!r} in corpus {corpus.id} "
            f"after {MAX_PATH_DISAMBIGUATION_SUFFIX} attempts"
        )

    @classmethod
    def _create_successor_path_with_retry(
        cls,
        *,
        current: DocumentPath,
        corpus: Corpus,
        folder: CorpusFolder | None,
        base_path: str,
        user: User,
        extra_occupied: set[str] | None = None,
    ) -> tuple[DocumentPath, str]:
        """
        Atomically deactivate ``current`` and create a successor DocumentPath,
        retrying on ``IntegrityError`` from the ``unique_active_path_per_corpus``
        partial unique constraint.

        This is the TOCTOU race recovery layer for path uniqueness:
        ``_disambiguate_path`` checks for occupied paths at query time, but a
        concurrent transaction can claim the same path between the SELECT and
        the INSERT.  Each retry runs:

        1. ``_disambiguate_path`` to choose a free path (treating any
           previously-lost paths as occupied)
        2. A nested ``transaction.atomic()`` savepoint
        3. ``current.is_current = False`` save
        4. ``DocumentPath.objects.create(...)`` for the successor

        On ``IntegrityError`` the savepoint is rolled back (so ``current``
        remains the active path in the DB), the losing path is added to the
        in-memory occupied set, and the loop tries again with a fresh
        disambiguation.

        After ``MAX_PATH_CREATE_RETRIES`` consecutive failures the most
        recent ``IntegrityError`` is re-raised so the caller can roll back
        the outer transaction.

        **Caller contract**: must already be inside an outer
        ``transaction.atomic()`` block that holds a ``select_for_update``
        lock on ``current``.  The lock prevents two callers from racing on
        the *same* document; this helper only handles races on the *target
        path slot* (different documents racing for the same filename).

        Args:
            current: Currently active DocumentPath being superseded.
            corpus: Owning corpus (must equal ``current.corpus``).
            folder: Target folder for the successor (None = corpus root).
            base_path: Initial proposed path; disambiguated each attempt.
            user: User performing the operation (set as creator).
            extra_occupied: Optional set of paths already claimed by earlier
                items in a batch operation; merged into the in-memory
                occupied set on every disambiguation.

        Returns:
            ``(new_path_record, chosen_path_string)`` — the path string may
            differ from ``base_path`` after disambiguation/retries.

        Raises:
            ValueError: If ``_disambiguate_path`` exhausts its suffix cap.
            IntegrityError: If ``MAX_PATH_CREATE_RETRIES`` consecutive
                INSERT attempts all lose the race.
        """
        # Deferred to break circular import (documents -> corpuses -> documents).
        from opencontractserver.documents.models import DocumentPath

        # Track paths we've attempted unsuccessfully so disambiguation
        # avoids them on subsequent retries within the same call.
        occupied_after_loss: set[str] = set(extra_occupied or ())
        last_exc: IntegrityError | None = None

        for attempt in range(MAX_PATH_CREATE_RETRIES + 1):
            new_path = cls._disambiguate_path(
                base_path,
                corpus,
                exclude_pk=current.pk,
                extra_occupied=occupied_after_loss,
            )
            try:
                # Savepoint: both the deactivation and the create must
                # succeed together, or neither commits.  An IntegrityError
                # rolls back the savepoint without poisoning the outer
                # transaction, allowing retry.
                with transaction.atomic():
                    current.is_current = False
                    current.save(update_fields=["is_current"])

                    new_record = DocumentPath.objects.create(
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
                    return new_record, new_path
            except IntegrityError as exc:
                # Only retry for the specific partial-unique constraint;
                # other IntegrityErrors (null, FK) are real bugs and
                # should not be retried.
                #
                # Guard order: first check the psycopg2 pgcode so we only
                # inspect the error message for UniqueViolation errors
                # (pgcode 23505); then confirm the constraint name.  This
                # avoids retrying on unrelated IntegrityErrors that happen
                # to contain the constraint name as a substring, and also
                # avoids matching on non-English Postgres error messages.
                cause = getattr(exc, "__cause__", None)
                pgcode = getattr(cause, "pgcode", None)
                if pgcode != "23505" or "unique_active_path_per_corpus" not in str(exc):
                    raise
                last_exc = exc
                occupied_after_loss.add(new_path)
                # The savepoint rollback restored ``current.is_current=True``
                # in the database, but the in-memory attribute still reflects
                # the unsaved write.  Reset it so the next iteration's save()
                # actually writes ``False`` again.
                current.is_current = True
                logger.warning(
                    "IntegrityError on attempt %d/%d creating path %r for "
                    "document %s in corpus %s — concurrent path conflict, "
                    "retrying with fresh disambiguation: %s",
                    attempt + 1,
                    MAX_PATH_CREATE_RETRIES + 1,
                    new_path,
                    current.document_id,
                    corpus.id,
                    exc,
                )

        logger.error(
            "DocumentPath creation failed after %d retries for document %s "
            "in corpus %s — concurrent path conflicts could not be resolved",
            MAX_PATH_CREATE_RETRIES + 1,
            current.document_id,
            corpus.id,
        )
        # last_exc is guaranteed non-None here: the loop runs at least once
        # and only exits via return-on-success or via the except block which
        # always sets last_exc.  Guard defensively so ``python -O`` doesn't
        # silently turn this into ``raise None``.
        if last_exc is None:
            raise RuntimeError(
                "Unreachable: retry loop exited without setting last_exc"
            )
        raise last_exc

    @classmethod
    def soft_delete_document(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
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
        if not cls.check_corpus_delete_permission(user, corpus):
            return (
                False,
                "Permission denied: You do not have delete access to this corpus",
            )

        # Validate document belongs to corpus
        if not cls.check_document_in_corpus(document, corpus):
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
        if not cls.check_corpus_write_permission(user, document_path.corpus):
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
        if not cls.check_corpus_delete_permission(user, corpus):
            return (
                False,
                "Permission denied: You do not have delete access to this corpus",
            )

        # Validate document belongs to corpus (has any path record)
        if not cls.check_document_in_corpus(document, corpus):
            return False, "Document does not belong to this corpus"

        # Delegate to versioning module
        return permanently_delete_document(corpus, document, user)

    @classmethod
    def empty_trash(
        cls,
        user: User,
        corpus: Corpus,
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
        if not cls.check_corpus_delete_permission(user, corpus):
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

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    @classmethod
    def get_document_folder(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
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

        if not cls.check_corpus_read_permission(user, corpus):
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

    @classmethod
    def get_folder_path(
        cls,
        user: User,
        folder: CorpusFolder,
    ) -> str | None:
        """
        Get the full path string for a folder.

        Args:
            user: Requesting user
            folder: Folder to get path for

        Returns:
            Path string like "/Legal/Contracts/2024", None if no access
        """
        if not cls.check_corpus_read_permission(user, folder.corpus):
            return None

        return "/" + folder.get_path()

    @classmethod
    def search_folders(
        cls,
        user: User,
        corpus_id: int,
        query: str,
    ) -> QuerySet[CorpusFolder]:
        """
        Search folders by name within a corpus.

        Args:
            user: Requesting user
            corpus_id: ID of corpus to search in
            query: Search query string

        Returns:
            QuerySet of matching folders
        """
        folders = cls.get_visible_folders(user, corpus_id)

        if not query.strip():
            return folders

        return folders.filter(name__icontains=query.strip())

    @classmethod
    def create_folder_structure_from_paths(
        cls,
        user: User,
        corpus: Corpus,
        folder_paths: list[str],
        target_folder: CorpusFolder | None = None,
    ) -> tuple[dict[str, CorpusFolder], int, int, str]:
        """
        Create all folders needed for a bulk import operation.

        This method efficiently creates a folder hierarchy from a list of paths,
        reusing existing folders and creating new ones as needed. Paths must be
        sorted by depth (parents before children) for correct operation.

        Used by zip import to create the folder structure before adding documents.

        Args:
            user: User performing the import (must have write permission on corpus)
            corpus: Target corpus
            folder_paths: List of folder paths to create (e.g., ["docs", "docs/contracts"])
                          Must be sorted by depth (parents first)
            target_folder: Optional parent folder for all imports (zip root goes here)

        Returns:
            (folder_map, created_count, reused_count, error_message)
            - folder_map: Dict mapping path -> CorpusFolder for document assignment
            - created_count: Number of new folders created
            - reused_count: Number of existing folders reused
            - error_message: Error description if operation failed

        Example:
            folder_map, created, reused, error = DocumentFolderService.create_folder_structure_from_paths(
                user=user,
                corpus=corpus,
                folder_paths=["docs", "docs/contracts", "docs/legal"],
                target_folder=None,  # Create at corpus root
            )
            if error:
                raise ValueError(error)
            # folder_map = {"docs": <Folder>, "docs/contracts": <Folder>, ...}

        Permissions:
            Requires corpus UPDATE permission
        """
        from opencontractserver.corpuses.models import CorpusFolder

        # Permission check
        if not cls.check_corpus_write_permission(user, corpus):
            return (
                {},
                0,
                0,
                "Permission denied: You do not have write access to this corpus",
            )

        if not folder_paths:
            return {}, 0, 0, ""

        folder_map: dict[str, CorpusFolder] = {}
        created_count = 0
        reused_count = 0

        # Pre-fetch existing folders in corpus to minimize queries
        existing_folders = CorpusFolder.objects.filter(corpus=corpus).select_related(
            "parent"
        )

        # Build lookup for existing folders by their full path
        # We need to compute full paths for existing folders
        existing_by_path: dict[str, CorpusFolder] = {}
        for folder in existing_folders:
            path = folder.get_path()
            # Adjust for target_folder prefix if needed
            if target_folder:
                # Existing folders under target_folder need to be matched
                # relative to target_folder's path
                target_path = target_folder.get_path()
                if path.startswith(target_path + "/"):
                    relative_path = path[len(target_path) + 1 :]
                    existing_by_path[relative_path] = folder
                elif folder.id == target_folder.id:
                    # The target folder itself
                    pass
            else:
                # No target folder - match at corpus root
                existing_by_path[path] = folder

        with transaction.atomic():
            for path in folder_paths:
                # Determine parent folder
                if "/" in path:
                    # Has a parent - look it up in our map
                    parent_path = "/".join(path.split("/")[:-1])
                    parent = folder_map.get(parent_path)
                    if parent is None:
                        # Parent should have been created already (paths are sorted)
                        # Check if it exists in corpus
                        parent = existing_by_path.get(parent_path)
                    if parent is None:
                        return (
                            {},
                            created_count,
                            reused_count,
                            f"Parent folder not found for path: {path}",
                        )
                else:
                    # Root-level folder - parent is target_folder (or None)
                    parent = target_folder

                folder_name = path.split("/")[-1]

                # Check if folder already exists at this path
                if path in existing_by_path:
                    folder_map[path] = existing_by_path[path]
                    reused_count += 1
                    logger.debug(f"Reusing existing folder: {path}")
                    continue

                # Atomically get or create folder to avoid race conditions
                # between concurrent imports
                folder, was_created = CorpusFolder.objects.get_or_create(
                    corpus=corpus,
                    parent=parent,
                    name=folder_name,
                    defaults={"creator": user},
                )

                folder_map[path] = folder
                existing_by_path[path] = folder  # Add to cache

                if was_created:
                    created_count += 1
                    logger.debug(f"Created new folder: {path} (id={folder.id})")
                else:
                    reused_count += 1
                    logger.debug(f"Reusing existing folder: {path}")

        logger.info(
            f"Folder structure created for corpus {corpus.id}: "
            f"{created_count} new, {reused_count} reused"
        )

        return folder_map, created_count, reused_count, ""

    # =========================================================================
    # DOCUMENT LIFECYCLE OPERATIONS
    # =========================================================================

    @classmethod
    def check_user_upload_quota(
        cls,
        user: User,
    ) -> tuple[bool, str]:
        """
        Check if user can create more documents based on usage caps.

        Args:
            user: User to check quota for

        Returns:
            (can_upload, error_message) - True if user can upload, error if not
        """
        if not user.is_usage_capped:
            return True, ""

        from opencontractserver.documents.models import Document

        current_count = Document.objects.filter(creator=user).count()
        cap = getattr(settings, "USAGE_CAPPED_USER_DOC_CAP_COUNT", 10)

        if current_count >= cap:
            return False, (
                f"Your usage is capped at {cap} documents. "
                f"Try deleting an existing document first or contact the admin "
                f"for a higher limit."
            )

        return True, ""

    @classmethod
    def validate_file_type(
        cls,
        file_bytes: bytes,
    ) -> tuple[str | None, str]:
        """
        Validate and detect file MIME type.

        Args:
            file_bytes: Raw file bytes to analyze

        Returns:
            (mime_type, error_message) - mime_type is None if validation fails
        """
        import filetype

        from opencontractserver.utils.files import is_plaintext_content

        kind = filetype.guess(file_bytes)
        if kind is None:
            if is_plaintext_content(file_bytes):
                mime_type = "text/plain"
            else:
                return None, "Unable to determine file type"
        else:
            mime_type = kind.mime

        if mime_type not in get_allowed_mime_types():
            return None, f"Unallowed filetype: {mime_type}"

        return mime_type, ""

    @classmethod
    def create_document(
        cls,
        user: User,
        file_bytes: bytes,
        filename: str,
        title: str,
        description: str = "",
        custom_meta: dict | None = None,
        is_public: bool = False,
        slug: str | None = None,
    ) -> tuple[Document | None, str]:
        """
        Create a standalone document (not attached to any corpus).

        This is the single entry point for creating documents outside of corpus context.
        Handles file type validation, usage quota checks, and permission setup.

        Args:
            user: Creating user
            file_bytes: Raw file bytes
            filename: Original filename
            title: Document title
            description: Document description
            custom_meta: Optional custom metadata dict
            is_public: Whether document should be public
            slug: Optional URL slug

        Returns:
            (document, error_message) - document is None if creation fails

        Note:
            For corpus imports with deduplication, use upload_document_to_corpus() instead.
        """
        from django.core.files.base import ContentFile

        from opencontractserver.documents.models import Document

        # Check quota
        can_upload, quota_error = cls.check_user_upload_quota(user)
        if not can_upload:
            return None, quota_error

        # Validate file type
        mime_type, type_error = cls.validate_file_type(file_bytes)
        if not mime_type:
            return None, type_error

        try:
            with transaction.atomic():
                # Create document based on file type
                if mime_type in [
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ]:
                    pdf_file = ContentFile(file_bytes, name=filename)
                    document = Document.objects.create(
                        creator=user,
                        title=title,
                        description=description,
                        custom_meta=custom_meta or {},
                        pdf_file=pdf_file,
                        backend_lock=True,
                        is_public=is_public,
                        file_type=mime_type,
                        slug=slug,
                    )
                elif mime_type in ["text/plain", "application/txt"]:
                    txt_file = ContentFile(file_bytes, name=filename)
                    document = Document.objects.create(
                        creator=user,
                        title=title,
                        description=description,
                        custom_meta=custom_meta or {},
                        txt_extract_file=txt_file,
                        backend_lock=True,
                        is_public=is_public,
                        file_type=mime_type,
                        slug=slug,
                    )
                else:
                    return None, f"Unsupported file type: {mime_type}"

                # Set permissions for creator
                set_permissions_for_obj_to_user(user, document, [PermissionTypes.CRUD])

                logger.info(
                    f"Created standalone document {document.id} "
                    f"(type={mime_type}) by user {user.id}"
                )

                return document, ""

        except Exception as e:
            logger.exception(f"Error creating document: {e}")
            return None, f"Error creating document: {e}"

    @classmethod
    def upload_document_to_corpus(
        cls,
        user: User,
        corpus: Corpus,
        file_bytes: bytes,
        filename: str,
        title: str,
        description: str = "",
        folder: CorpusFolder | None = None,
        custom_meta: dict | None = None,
        is_public: bool = False,
        slug: str | None = None,
    ) -> tuple[Document | None, str, str]:
        """
        Upload a document to a corpus.

        This method ensures consistent versioning behavior by:
        1. First creating a standalone document in the system
        2. Then adding that document to the corpus (creating a corpus-isolated copy)

        This approach ensures documents have identical versioning behavior regardless
        of whether they were uploaded directly to a corpus or added later.

        Args:
            user: Uploading user
            corpus: Target corpus
            file_bytes: Raw file bytes
            filename: Original filename
            title: Document title
            description: Document description
            folder: Optional folder to place document in
            custom_meta: Optional custom metadata dict
            is_public: Whether document should be public
            slug: Optional URL slug

        Returns:
            (corpus_document, status, error_message) where:
            - corpus_document: The corpus-isolated document
            - status: 'added' or 'already_exists'
            - error_message: Empty if successful

        Permissions:
            Requires corpus UPDATE permission
        """
        # Check corpus write permission first
        if not cls.check_corpus_write_permission(user, corpus):
            return (
                None,
                "",
                "Permission denied: You do not have write access to this corpus",
            )

        # Step 1: Create standalone document first
        standalone_doc, create_error = cls.create_document(
            user=user,
            file_bytes=file_bytes,
            filename=filename,
            title=title,
            description=description,
            custom_meta=custom_meta,
            is_public=is_public,
            slug=slug,
        )

        if not standalone_doc:
            return None, "", create_error

        # Step 2: Add to corpus (creates isolated copy with proper versioning)
        corpus_doc, status, add_error = cls.add_document_to_corpus(
            user=user,
            document=standalone_doc,
            corpus=corpus,
            folder=folder,
        )

        if not corpus_doc:
            # If adding to corpus failed, we still have the standalone doc
            logger.warning(
                f"Document {standalone_doc.id} created but failed to add to corpus: {add_error}"
            )
            return None, "", add_error

        logger.info(
            f"Uploaded document to corpus {corpus.id} "
            f"(standalone={standalone_doc.id}, corpus_doc={corpus_doc.id}, "
            f"status={status}, folder={folder.id if folder else None}) by user {user.id}"
        )

        return corpus_doc, status, ""

    @classmethod
    def add_document_to_corpus(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
        folder: CorpusFolder | None = None,
    ) -> tuple[Document | None, str, str]:
        """
        Add an existing document to a corpus, creating a corpus-isolated copy.

        This creates a NEW document in the corpus with:
        - Its own version_tree_id (independent version tree)
        - source_document pointing to original (provenance tracking)
        - DocumentPath linking to the corpus

        Use this when you have a document (perhaps from user's library) and want
        to add it to a corpus. The original document is unchanged.

        Args:
            user: User performing the operation
            document: Source document to copy into corpus
            corpus: Target corpus
            folder: Optional folder to place document in

        Returns:
            (corpus_document, status, error_message) where:
            - corpus_document: The NEW corpus-isolated document (not the original)
            - status: 'added' or 'already_exists'

        Permissions:
            Requires corpus UPDATE permission AND document READ permission
        """
        # Check corpus write permission
        if not cls.check_corpus_write_permission(user, corpus):
            return (
                None,
                "",
                "Permission denied: You do not have write access to this corpus",
            )

        # Check document access (owner or public)
        if document.creator != user and not document.is_public:
            if not user_has_permission_for_obj(user, document, PermissionTypes.READ):
                return (
                    None,
                    "",
                    "Permission denied: You do not have access to this document",
                )

        try:
            # Use corpus.add_document for proper corpus isolation
            # The folder is passed through and stored in DocumentPath
            corpus_doc, status, path_record = corpus.add_document(
                document=document,
                user=user,
                folder=folder,
            )

            # Set permissions on the corpus-isolated copy
            set_permissions_for_obj_to_user(user, corpus_doc, [PermissionTypes.CRUD])

            logger.info(
                f"Added document {document.id} to corpus {corpus.id} as {corpus_doc.id} "
                f"(status={status}) by user {user.id}"
            )

            return corpus_doc, status, ""

        except Exception as e:
            logger.exception(f"Error adding document to corpus: {e}")
            return None, "", f"Error adding document to corpus: {e}"

    @classmethod
    def add_documents_to_corpus(
        cls,
        user: User,
        document_ids: list[int],
        corpus: Corpus,
        folder: CorpusFolder | None = None,
    ) -> tuple[int, list[int], str]:
        """
        Add multiple existing documents to a corpus.

        This is a bulk operation that creates corpus-isolated copies of each document.

        Args:
            user: User performing the operation
            document_ids: List of document IDs to add
            corpus: Target corpus
            folder: Optional folder to place documents in

        Returns:
            (added_count, added_doc_ids, error_message)

        Permissions:
            Requires corpus UPDATE permission
        """
        from opencontractserver.documents.models import Document

        # Check corpus write permission
        if not cls.check_corpus_write_permission(user, corpus):
            return (
                0,
                [],
                "Permission denied: You do not have write access to this corpus",
            )

        # Get accessible documents (owned or public)
        documents = Document.objects.filter(
            Q(pk__in=document_ids) & (Q(creator=user) | Q(is_public=True))
        )

        added_count = 0
        added_ids = []
        errors = []

        for doc in documents:
            corpus_doc, status, error = cls.add_document_to_corpus(
                user=user,
                document=doc,
                corpus=corpus,
                folder=folder,
            )
            if corpus_doc:
                added_count += 1
                added_ids.append(corpus_doc.id)
            elif error:
                errors.append(f"Doc {doc.id}: {error}")

        error_msg = "; ".join(errors) if errors else ""
        return added_count, added_ids, error_msg

    @classmethod
    def remove_document_from_corpus(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
    ) -> tuple[bool, str]:
        """
        Remove a document from a corpus (soft delete).

        This creates a soft-delete DocumentPath record maintaining history.
        The document is not permanently deleted and can be restored.

        Args:
            user: User performing the operation
            document: Document to remove
            corpus: Corpus to remove from

        Returns:
            (success, error_message)

        Permissions:
            Requires corpus UPDATE permission
        """
        # Check corpus write permission
        if not cls.check_corpus_write_permission(user, corpus):
            return (
                False,
                "Permission denied: You do not have write access to this corpus",
            )

        try:
            deleted_paths = corpus.remove_document(document=document, user=user)

            if not deleted_paths:
                return False, "Document not found in corpus"

            logger.info(
                f"Removed document {document.id} from corpus {corpus.id} "
                f"({len(deleted_paths)} paths) by user {user.id}"
            )

            return True, ""

        except Exception as e:
            logger.exception(f"Error removing document from corpus: {e}")
            return False, f"Error removing document from corpus: {e}"

    @classmethod
    def remove_documents_from_corpus(
        cls,
        user: User,
        document_ids: list[int],
        corpus: Corpus,
    ) -> tuple[int, str]:
        """
        Remove multiple documents from a corpus (soft delete).

        Args:
            user: User performing the operation
            document_ids: List of document IDs to remove
            corpus: Corpus to remove from

        Returns:
            (removed_count, error_message)

        Permissions:
            Requires corpus UPDATE permission
        """
        # Check corpus write permission
        if not cls.check_corpus_write_permission(user, corpus):
            return 0, "Permission denied: You do not have write access to this corpus"

        # Get documents that are actually in this corpus
        corpus_docs = corpus.get_documents().filter(pk__in=document_ids)

        removed_count = 0
        errors = []

        for doc in corpus_docs:
            success, error = cls.remove_document_from_corpus(
                user=user,
                document=doc,
                corpus=corpus,
            )
            if success:
                removed_count += 1
            elif error:
                errors.append(f"Doc {doc.id}: {error}")

        error_msg = "; ".join(errors) if errors else ""
        return removed_count, error_msg

    @classmethod
    def get_document_by_id(
        cls,
        user: User,
        document_id: int,
    ) -> Document | None:
        """
        Get a document by ID if user has access.

        Args:
            user: Requesting user
            document_id: Document ID

        Returns:
            Document if found and accessible, None otherwise

        Note:
            Returns same error (None) whether document doesn't exist or
            user doesn't have access (IDOR protection).
        """
        from opencontractserver.documents.models import Document

        try:
            document = Document.objects.get(pk=document_id)

            # Check access: owner, public, or has READ permission
            if document.creator == user or document.is_public:
                return document

            if user_has_permission_for_obj(user, document, PermissionTypes.READ):
                return document

            return None

        except Document.DoesNotExist:
            return None

    @classmethod
    def get_corpus_documents(
        cls,
        user: User,
        corpus: Corpus,
        include_deleted: bool = False,
    ) -> QuerySet[Document]:
        """
        Get all documents in a corpus.

        Args:
            user: Requesting user
            corpus: Corpus to get documents from
            include_deleted: Whether to include soft-deleted documents

        Returns:
            QuerySet of documents (empty if no access)

        Permissions:
            Requires corpus READ permission
        """
        from opencontractserver.documents.models import Document

        if not cls.check_corpus_read_permission(user, corpus):
            return Document.objects.none()

        if include_deleted:
            # Get all documents with any path (current or deleted)
            from opencontractserver.documents.models import DocumentPath

            doc_ids = DocumentPath.objects.filter(
                corpus=corpus, is_current=True
            ).values_list("document_id", flat=True)
            return Document.objects.filter(pk__in=doc_ids)
        else:
            return corpus.get_documents()

    @classmethod
    def set_document_permissions(
        cls,
        user: User,
        document: Document,
        target_user: User,
        permissions: list[PermissionTypes],
    ) -> tuple[bool, str]:
        """
        Set permissions for a document.

        Args:
            user: User setting permissions (must be owner or have permission control)
            document: Document to set permissions on
            target_user: User to grant permissions to
            permissions: List of PermissionTypes to grant

        Returns:
            (success, error_message)

        Permissions:
            Requires document ownership or PERMISSION permission
        """
        # Check if user can set permissions (owner or has PERMISSION perm)
        if document.creator != user:
            if not user_has_permission_for_obj(
                user, document, PermissionTypes.PERMISSION
            ):
                return (
                    False,
                    "Permission denied: Cannot modify permissions for this document",
                )

        try:
            set_permissions_for_obj_to_user(target_user, document, permissions)
            logger.info(
                f"Set permissions {permissions} on document {document.id} "
                f"for user {target_user.id} by user {user.id}"
            )
            return True, ""
        except Exception as e:
            logger.exception(f"Error setting document permissions: {e}")
            return False, f"Error setting permissions: {e}"
