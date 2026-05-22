"""Folder CRUD and folder-tree operations for the corpus service layer.

``FolderCRUDService`` owns folder create / read / update / move / delete, the
folder tree, folder search, and bulk folder-structure creation for imports.
``delete_folder`` relocates any documents it contains to the corpus root via
:class:`~opencontractserver.corpuses.services.paths.CorpusPathService`.

Document-in-folder placement and queries live in the sibling
:class:`~opencontractserver.corpuses.services.folder_documents.FolderDocumentService`.

Split out of the former ``corpus_objs_service.py`` monolith — see
``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``
(issue #1716, service-layer centralization Phase 2).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from opencontractserver.corpuses.services.paths import CorpusPathService
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus, CorpusFolder
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class FolderCRUDService(BaseService):
    """Folder CRUD, the folder tree, search, and bulk structure creation.

    Read methods require corpus READ; write methods require corpus UPDATE,
    except ``delete_folder`` which requires corpus DELETE.
    """

    @classmethod
    def get_visible_folders(
        cls,
        user: User,
        corpus_id: int,
        parent_id: int | None = None,
        *,
        request: Any = None,
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

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
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
        *,
        request: Any = None,
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
        if not folder.corpus.user_can(user, PermissionTypes.READ, request=request):
            return None

        return folder

    @classmethod
    def get_folder_tree(
        cls,
        user: User,
        corpus_id: int,
        *,
        request: Any = None,
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
        from django.db.models import Count

        from opencontractserver.documents.models import DocumentPath

        folders = list(cls.get_visible_folders(user, corpus_id, request=request))

        # Bulk-aggregate direct document counts per folder in a single GROUP BY
        # query instead of one COUNT per folder (was the N+1 flagged for
        # follow-up on PR #1685).
        doc_count_rows = (
            DocumentPath.objects.filter(
                corpus_id=corpus_id, is_current=True, is_deleted=False
            )
            .values("folder_id")
            .annotate(count=Count("id"))
        )
        doc_counts: dict[int | None, int] = {
            row["folder_id"]: row["count"] for row in doc_count_rows
        }

        # Build per-folder dict; defer ``path`` until the parent map is fully
        # populated so we can walk parent_id chains in Python and avoid the
        # recursive CTE that ``CorpusFolder.get_path()`` would otherwise run
        # per node.
        folder_dict: dict[int, dict] = {}
        for folder in folders:
            folder_dict[folder.id] = {
                "id": folder.id,
                "name": folder.name,
                "path": "",
                "documentCount": doc_counts.get(folder.id, 0),
                "parentId": folder.parent_id,
                "children": [],
            }

        # Resolve paths by walking parent ids — O(depth) per folder, fully in
        # memory, no DB hits. Memoise so deep trees still cost O(N) overall.
        path_cache: dict[int, str] = {}

        def _resolve_path(folder_id: int) -> str:
            cached = path_cache.get(folder_id)
            if cached is not None:
                return cached
            entry = folder_dict[folder_id]
            parent_id = entry["parentId"]
            if parent_id and parent_id in folder_dict:
                path = f"{_resolve_path(parent_id)}/{entry['name']}"
            else:
                path = entry["name"]
            path_cache[folder_id] = path
            return path

        for folder_id, folder_data in folder_dict.items():
            folder_data["path"] = _resolve_path(folder_id)

        # Build tree structure
        roots: list[dict] = []
        for folder_id, folder_data in folder_dict.items():
            parent_id = folder_data.get("parentId")
            if parent_id and parent_id in folder_dict:
                folder_dict[parent_id]["children"].append(folder_data)
            else:
                roots.append(folder_data)

        return roots

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
        *,
        request: Any = None,
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
            folder, error = FolderCRUDService.create_folder(
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
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
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
        *,
        request: Any = None,
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
        if not folder.corpus.user_can(user, PermissionTypes.UPDATE, request=request):
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
        *,
        request: Any = None,
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
        if not folder.corpus.user_can(user, PermissionTypes.UPDATE, request=request):
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
        *,
        request: Any = None,
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
        if not folder.corpus.user_can(user, PermissionTypes.DELETE, request=request):
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
                    occupied_paths = (
                        CorpusPathService._fetch_occupied_paths_in_directory(
                            corpus, "/"
                        )
                    )

                    planned_paths: list[tuple[DocumentPath, str]] = []
                    for current in affected_paths:
                        # Note: _compute_moved_path extracts only the filename;
                        # intermediate directory segments are dropped (the new
                        # path is derived from the target folder's tree position).
                        new_path = CorpusPathService._compute_moved_path(
                            current.path, None
                        )
                        new_path = CorpusPathService._disambiguate_path(
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
                    CorpusPathService._dispatch_document_path_created_signals(
                        created_paths
                    )

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

    @classmethod
    def get_folder_path(
        cls,
        user: User,
        folder: CorpusFolder,
        *,
        request: Any = None,
    ) -> str | None:
        """
        Get the full path string for a folder.

        Args:
            user: Requesting user
            folder: Folder to get path for

        Returns:
            Path string like "/Legal/Contracts/2024", None if no access
        """
        if not folder.corpus.user_can(user, PermissionTypes.READ, request=request):
            return None

        return "/" + folder.get_path()

    @classmethod
    def search_folders(
        cls,
        user: User,
        corpus_id: int,
        query: str,
        *,
        request: Any = None,
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
        folders = cls.get_visible_folders(user, corpus_id, request=request)

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
        *,
        request: Any = None,
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
            folder_map, created, reused, error = (
                FolderCRUDService.create_folder_structure_from_paths(
                    user=user,
                    corpus=corpus,
                    folder_paths=["docs", "docs/contracts", "docs/legal"],
                    target_folder=None,  # Create at corpus root
                )
            )
            if error:
                raise ValueError(error)
            # folder_map = {"docs": <Folder>, "docs/contracts": <Folder>, ...}

        Permissions:
            Requires corpus UPDATE permission
        """
        from opencontractserver.corpuses.models import CorpusFolder

        # Permission check
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
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
