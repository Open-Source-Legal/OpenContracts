"""Folder CRUD and folder-tree operations for the corpus service layer.

``FolderCRUDService`` owns folder create / read / update / move / delete, the
folder tree, folder search, and bulk folder-structure creation for imports.
``delete_folder`` has two modes: with ``move_children_to_parent=True`` it
relocates the folder's documents to the corpus root via
:class:`~opencontractserver.corpuses.services.paths.CorpusPathService` and
reparents its sub-folders; with ``move_children_to_parent=False`` (the
``deleteContents=True`` path the UI uses) it cascade-trashes the entire
sub-tree, moving every document in it to Trash (recoverable).

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

# Name of the ``CorpusFolder`` unique constraint (see ``CorpusFolder.Meta``).
# Used to tell a genuine folder-name collision apart from an unrelated
# ``IntegrityError`` raised inside the same ``transaction.atomic()`` block
# (e.g. ``reconcile_paths_after_folder_change`` losing a race to a concurrent
# import that lands on one of the rewritten document paths).
_FOLDER_NAME_CONSTRAINT = "unique_folder_name_per_parent"


def _is_folder_name_collision(exc: IntegrityError) -> bool:
    """True if ``exc`` is the folder-name uniqueness violation (not a path one).

    The DB driver embeds the violated constraint name in the error text, so a
    substring check reliably distinguishes the folder-name collision from a
    ``DocumentPath`` collision surfaced by path reconciliation in the same
    transaction.
    """
    return _FOLDER_NAME_CONSTRAINT in str(exc)


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
    def get_visible_folders_with_aggregates(
        cls,
        user: User,
        corpus_id: int,
        *,
        request: Any = None,
    ) -> list[CorpusFolder]:
        """
        Visible folders with ``_path``, ``_doc_count`` and
        ``_descendant_doc_count`` pre-attached as instance attributes.

        Used by the GraphQL ``corpus_folders`` resolver to collapse the
        per-folder query fan-out that the default ``CorpusFolderType``
        resolvers would otherwise produce on the folder-list view:

          * ``resolve_path`` -> ``CorpusFolder.get_path()`` -> recursive
            ancestor CTE per folder
          * ``resolve_document_count`` -> per-folder ``COUNT`` on
            ``DocumentPath``
          * ``resolve_descendant_document_count`` ->
            ``CorpusFolder.get_descendant_folders()`` (recursive descendant
            CTE) + ``COUNT`` per folder

        Replaces the ``4N`` per-folder roundtrips with:

          * 1 SQL query for the folder list (already done by
            :meth:`get_visible_folders`)
          * 1 ``GROUP BY folder_id`` query for direct document counts
            (mirrors :meth:`get_folder_tree` line 167-176)
          * O(N) Python passes for path resolution and descendant-count
            roll-up (no DB)

        Paths are walked via ``parent_id`` chains with memoisation so the
        ``CorpusFolder.ancestors()`` CTE never runs.  Descendant counts are
        rolled up post-order from each folder's direct count, so the
        ``CorpusFolder.descendants()`` CTE never runs either.

        Returns a list (not a queryset) because the aggregates are attached
        in Python; callers that need a queryset should keep using
        :meth:`get_visible_folders`.

        Permissions: identical to :meth:`get_visible_folders` (corpus READ).
        The folder-document counts intentionally count every
        ``DocumentPath`` row in the corpus (matching
        :meth:`get_folder_tree`'s contract), so a user who can READ the
        corpus but lacks per-document READ on every document still sees
        the corpus-wide structural total. Per-user document-visibility
        filtering would require an extra subquery on every call and is
        not part of the folder-listing surface; surfaces that must hide
        private documents (e.g. the document grid) filter elsewhere.
        """
        from django.db.models import Count

        from opencontractserver.documents.models import DocumentPath

        folders = list(cls.get_visible_folders(user, corpus_id, request=request))
        if not folders:
            return folders

        # Direct doc counts via one GROUP BY (matches the existing batched
        # pattern in get_folder_tree() so the two helpers stay query-shape
        # equivalent).
        direct_counts_by_folder_id: dict[int | None, int] = {
            row["folder_id"]: row["count"]
            for row in DocumentPath.objects.filter(
                corpus_id=corpus_id, is_current=True, is_deleted=False
            )
            .values("folder_id")
            .annotate(count=Count("id"))
        }

        # Adjacency map (parent_id -> children) for the in-memory roll-up.
        folder_by_id: dict[int, CorpusFolder] = {f.id: f for f in folders}
        children_by_parent_id: dict[int | None, list[CorpusFolder]] = {}
        for folder in folders:
            children_by_parent_id.setdefault(folder.parent_id, []).append(folder)

        # Path resolution by walking parent_id chains iteratively; if a
        # parent isn't in the visible set we stop walking (fallback to the
        # folder's own name as the path) so we never reach for an ancestor
        # CTE. Iterative avoids ``RecursionError`` on pathological trees
        # whose depth exceeds Python's default 1000-frame recursion limit.
        path_cache: dict[int, str] = {}

        def _resolve_path(folder_id: int) -> str:
            chain: list[int] = []
            cursor: int | None = folder_id
            while cursor is not None and cursor not in path_cache:
                chain.append(cursor)
                folder = folder_by_id[cursor]
                parent_id = folder.parent_id
                # Stop when the parent isn't in our visible set — the
                # walk falls back to the highest-visible folder's name.
                if parent_id and parent_id in folder_by_id:
                    cursor = parent_id
                else:
                    cursor = None
            # ``chain`` is leaf -> root order; build paths root -> leaf.
            base_path = path_cache.get(cursor or 0, "")
            current = base_path
            for fid in reversed(chain):
                name = folder_by_id[fid].name
                current = f"{current}/{name}" if current else name
                path_cache[fid] = current
            return path_cache[folder_id]

        # Descendant counts via iterative post-order DFS (explicit stack
        # for the same recursion-depth safety as ``_resolve_path``):
        #   descendants(f) = direct(f) + sum(descendants(c) for c in children(f))
        descendant_count_cache: dict[int, int] = {}

        def _resolve_descendant_count(root_folder_id: int) -> int:
            if root_folder_id in descendant_count_cache:
                return descendant_count_cache[root_folder_id]
            # Two-phase iterative DFS: first descend, then accumulate on
            # the way back up. Each folder is pushed twice — once to
            # expand its children and once (post-children) to roll up.
            stack: list[tuple[int, bool]] = [(root_folder_id, False)]
            while stack:
                folder_id, post = stack.pop()
                if folder_id in descendant_count_cache:
                    continue
                if not post:
                    stack.append((folder_id, True))
                    for child in children_by_parent_id.get(folder_id, []):
                        if child.id not in descendant_count_cache:
                            stack.append((child.id, False))
                else:
                    total = direct_counts_by_folder_id.get(folder_id, 0)
                    for child in children_by_parent_id.get(folder_id, []):
                        total += descendant_count_cache.get(child.id, 0)
                    descendant_count_cache[folder_id] = total
            return descendant_count_cache[root_folder_id]

        for folder in folders:
            folder._doc_count = direct_counts_by_folder_id.get(folder.id, 0)
            folder._descendant_doc_count = _resolve_descendant_count(folder.id)
            folder._path = _resolve_path(folder.id)

        return folders

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

        # Create folder. The ``exists()`` precheck above covers the common
        # case, but a concurrent create of the same-named folder can slip
        # between that SELECT and this INSERT (TOCTOU). The
        # ``unique_folder_name_per_parent`` constraint is the real guarantee;
        # catch its violation and surface the same friendly message instead
        # of leaking a raw IntegrityError (HTTP 500) to the caller.
        try:
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
        except IntegrityError as exc:
            # Discriminate the name-collision constraint from any other
            # IntegrityError, matching update_folder / move_folder — a
            # different constraint violation must not be mislabeled as a
            # duplicate-name error.
            if _is_folder_name_collision(exc):
                return None, f"A folder named '{name}' already exists in this location"
            logger.exception(
                "create_folder rolled back on a non-name IntegrityError: %s", exc
            )
            raise

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

        # A rename changes folder.get_path(), so capture the pre-change path
        # up front to reconcile the stored document path strings afterwards.
        name_is_changing = name is not None and name != folder.name
        old_folder_path = folder.get_path() if name_is_changing else None

        # Update folder
        try:
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

                # Keep DocumentPath.path strings consistent with the new folder
                # name for every folder-derived path in this subtree (issue:
                # folder rename left paths stale). Runs in the same transaction
                # so the rename and the path rewrites commit atomically.
                if name_is_changing:
                    # ``old_folder_path`` was captured (a str) above on the same
                    # ``name_is_changing`` branch; narrow it for the typed call.
                    # Use an explicit guard rather than ``assert`` so it survives
                    # ``python -O`` and is visible to the type checker.
                    if old_folder_path is None:  # pragma: no cover - invariant
                        raise AssertionError(
                            "old_folder_path must be set when name_is_changing"
                        )
                    CorpusPathService.reconcile_paths_after_folder_change(
                        corpus=folder.corpus,
                        root_folder=folder,
                        old_root_path=old_folder_path,
                        user=user,
                    )
        except IntegrityError as exc:
            # A concurrent rename to the same target name can lose the
            # unique_folder_name_per_parent race despite the precheck above.
            if _is_folder_name_collision(exc):
                return (
                    False,
                    f"A folder named '{name}' already exists in this location",
                )
            # A different IntegrityError (e.g. path reconciliation losing a
            # race to a concurrent import) rolled the transaction back — report
            # it as a retriable conflict rather than a folder-name collision.
            logger.warning(
                "update_folder %s rolled back on a non-name IntegrityError: %s",
                folder.id,
                exc,
            )
            return (
                False,
                "Folder update failed due to a concurrent change; please retry.",
            )

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
        from opencontractserver.corpuses.models import CorpusFolder

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

        # Reject a move that would collide with an existing sibling name at the
        # destination before attempting the write, so the caller gets a clear
        # message rather than an IntegrityError. The try/except below is the
        # authoritative guard against the TOCTOU race between this check and
        # the save (``unique_folder_name_per_parent``).
        sibling_exists = (
            CorpusFolder.objects.filter(
                corpus_id=folder.corpus_id,
                parent=new_parent,
                name=folder.name,
            )
            .exclude(id=folder.id)
            .exists()
        )
        if sibling_exists:
            return (
                False,
                f"A folder named '{folder.name}' already exists in this location",
            )

        # A reparent changes folder.get_path() (and every descendant's), so
        # capture the pre-move path to reconcile stored document paths after.
        old_folder_path = folder.get_path()

        # Move folder
        try:
            with transaction.atomic():
                folder.parent = new_parent
                folder.save()

                # Keep DocumentPath.path strings consistent with the folder's
                # new location for every folder-derived path in this subtree.
                # Runs in the same transaction so the move and the path
                # rewrites commit atomically.
                CorpusPathService.reconcile_paths_after_folder_change(
                    corpus=folder.corpus,
                    root_folder=folder,
                    old_root_path=old_folder_path,
                    user=user,
                )
        except IntegrityError as exc:
            if _is_folder_name_collision(exc):
                return (
                    False,
                    f"A folder named '{folder.name}' already exists in this location",
                )
            # Path reconciliation (or another constraint) lost a race inside the
            # same transaction — report it as retriable, not a name collision.
            logger.warning(
                "move_folder %s rolled back on a non-name IntegrityError: %s",
                folder.id,
                exc,
            )
            return (
                False,
                "Folder move failed due to a concurrent change; please retry.",
            )

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
        Delete a folder, atomically handling its contents per ``move_children_to_parent``.

        Two modes, both fully atomic (single ``transaction.atomic()`` block —
        if anything fails the whole operation rolls back and is safe to retry):

        * ``move_children_to_parent=True`` (default — ``deleteContents=False``
          at the GraphQL layer): reparent the direct child folders to this
          folder's parent and relocate the documents *directly* in this folder
          to the corpus root (history-tracked). Sub-folders survive.
        * ``move_children_to_parent=False`` (``deleteContents=True``):
          cascade-delete the ENTIRE sub-tree (this folder + every sub-folder)
          and move EVERY document in it to Trash (soft-delete), recoverable
          until the trash is emptied. This is the behaviour the folder-delete
          UI uses. Previously this branch relocated only the top folder's
          direct documents to root and let the FK cascade strand the
          sub-folders' documents — leaving orphaned sub-folders at the root.

        Args:
            user: Deleting user
            folder: Folder to delete
            move_children_to_parent: If True, reparent child folders and move
                                     this folder's direct documents to root.
                                     If False, cascade-delete the whole sub-tree
                                     and move all its documents to Trash.

        Returns:
            (success, error_message).  Returns ``(False, ...)`` if the
            operation cannot complete — in that case the entire transaction is
            rolled back and no changes are persisted.

        Side Effects:
            - move_children_to_parent=True: this folder's documents move to
              root; child folders are reparented.
            - move_children_to_parent=False: every document in the sub-tree is
              soft-deleted (Trash); the whole folder sub-tree is removed.

        Permissions:
            Requires corpus DELETE permission
        """
        # Permission check
        if not folder.corpus.user_can(user, PermissionTypes.DELETE, request=request):
            return (
                False,
                "Permission denied: You do not have delete access to this corpus",
            )

        try:
            with transaction.atomic():
                if move_children_to_parent:
                    # Reparent direct children, then relocate this folder's
                    # direct documents to the corpus root. Sub-folders survive.
                    folder.children.update(parent=folder.parent)
                    cls._relocate_folder_documents_to_root(folder, user)
                else:
                    # deleteContents=True: trash every document in the sub-tree
                    # (this folder + all descendants) BEFORE the cascade delete
                    # below removes the folders. Trashing first keeps the
                    # documents restorable from the corpus trash. The returned
                    # trashed-count is intentionally discarded — folder delete
                    # reports success/failure, not a document tally.
                    _ = cls._trash_documents_in_subtree(folder, user)

                # Delete folder. With move_children_to_parent=False the
                # self-referential FK cascade removes the whole sub-tree; with
                # True the (already reparented) children are left in place.
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
    def _relocate_folder_documents_to_root(
        cls, folder: CorpusFolder, user: User
    ) -> None:
        """Relocate the documents directly in ``folder`` to the corpus root.

        History-tracked (every move creates a successor ``DocumentPath``).
        Extracted verbatim from ``delete_folder``'s reparent branch; documents
        in sub-folders are NOT touched (that branch keeps the sub-folders, so
        their documents stay where they are). Runs inside the caller's
        ``transaction.atomic()``.
        """
        from opencontractserver.documents.models import DocumentPath

        # select_related("document") + of=("self",) match the pattern in
        # move_documents_to_folder — N+1 avoidance + scoped row locking.
        affected_paths = list(
            DocumentPath.objects.select_for_update(of=("self",))
            .select_related("document")
            .filter(folder=folder, is_current=True, is_deleted=False)
            .order_by("pk")
        )
        if not affected_paths:
            return

        corpus = folder.corpus
        # Pre-fetch all occupied paths at the corpus root with a SINGLE query.
        # Because we filter to rows whose ``folder=folder`` (not root), none of
        # ``affected_paths`` live in the root directory, so the shared mutable
        # set captures within-batch claims on the fly (issue #1199).
        #
        # ORDERING INVARIANT: this fetch MUST run before the batch
        # ``update(is_current=False)`` below so the superseded rows still count
        # as occupied; reordering would let the batch re-claim its own source
        # paths and produce duplicate DocumentPath rows.
        occupied_paths = CorpusPathService._fetch_occupied_paths_in_directory(
            corpus, "/"
        )

        planned_paths: list[tuple[DocumentPath, str]] = []
        for current in affected_paths:
            # _compute_moved_path extracts only the filename; intermediate
            # directory segments are dropped (root has no folder prefix).
            new_path = CorpusPathService._compute_moved_path(current.path, None)
            new_path = CorpusPathService.disambiguate_path(
                new_path, corpus, occupied_override=occupied_paths
            )
            occupied_paths.add(new_path)
            planned_paths.append((current, new_path))

        # Execute all relocations in exactly TWO queries.
        old_path_pks = [current.pk for current, _ in planned_paths]
        DocumentPath.objects.filter(pk__in=old_path_pks).update(is_current=False)

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
        CorpusPathService._dispatch_document_path_created_signals(created_paths)

    @classmethod
    def _trash_documents_in_subtree(cls, folder: CorpusFolder, user: User) -> int:
        """Soft-delete (move to Trash) every active document in ``folder`` and
        all of its descendant folders.

        Reuses ``Corpus.remove_document`` — the same soft-delete primitive the
        'Remove from corpus' action uses — so each trashed document gets an
        identical history node + signals and stays restorable. Runs inside the
        caller's ``transaction.atomic()``; the caller deletes the folder
        sub-tree afterwards, at which point the soft-deleted paths' ``folder``
        FK is SET_NULL (matching how a document trashed from the root has no
        folder). Returns the number of documents trashed.
        """
        from opencontractserver.documents.models import Document, DocumentPath

        corpus = folder.corpus
        # Materialise the descendant folder ids (a small, bounded set) rather
        # than feeding the tree-queries CTE queryset into ``folder_id__in`` as a
        # sub-query — keeps the document lookup a plain ``IN (...)``.
        # NOTE: ``get_descendant_folders()`` is ``descendants(include_self=True)``,
        # so ``folder`` itself is in this list — documents sitting directly in the
        # folder being deleted are trashed too (not just those in sub-folders).
        descendant_folder_ids = list(
            folder.get_descendant_folders().values_list("id", flat=True)
        )
        doc_ids = list(
            DocumentPath.objects.filter(
                corpus=corpus,
                folder_id__in=descendant_folder_ids,
                is_current=True,
                is_deleted=False,
            )
            .values_list("document_id", flat=True)
            .distinct()
        )

        trashed = 0
        # TODO(perf, deferred): batch this for large corpora —
        # ``remove_document`` issues several queries per document (history row,
        # signals, path update) and holds row locks inside the caller's
        # transaction, so a very large sub-tree can hit the DB statement timeout.
        # Same per-document-loop pattern as ``DocumentLifecycleService.empty_corpus``
        # and the legacy "empty trash" path; all three want one shared bulk-trash
        # primitive (tracked in issue #1951). Fine for typical folder sizes;
        # batch via that primitive before raising the sub-tree document-count
        # ceiling.
        for document in Document.objects.filter(pk__in=doc_ids):
            if corpus.remove_document(document=document, user=user):
                trashed += 1
        return trashed

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
