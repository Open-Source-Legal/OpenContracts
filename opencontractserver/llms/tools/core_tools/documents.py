"""Agent tools for managing documents as files within a corpus.

These corpus-scoped *file management* tools let an LLM agent treat the
documents in a corpus like files in a filesystem: search/list them, move them
between folders, rename them, and delete them (soft-delete to the corpus
trash). They are the agent-facing counterpart of the corpus file browser and
all route through the canonical corpus service layer
(``opencontractserver.corpuses.services``), which performs the precise
permission check for each operation.

Permissioning mirrors the human surfaces:

* ``search_corpus_documents`` is read-only — it returns only documents the
  user can see at BOTH the corpus and document level
  (``MIN(document_permission, corpus_permission)``).
* ``move_document`` / ``rename_document`` change a document's place/name in the
  corpus filesystem and require corpus UPDATE.
* ``delete_document`` soft-deletes (to the restorable corpus trash) and
  requires corpus DELETE.

The write tools (move/rename/delete) are flagged ``requires_write_permission``
(filtered out for users without corpus WRITE) and ``requires_approval`` (a
human confirms the call before it executes).

Parameter naming follows ``build_inject_params_for_context`` in
``opencontractserver.llms.tools.tool_factory`` — ``corpus_id``, ``user_id`` /
``author_id``, and ``document_id`` are auto-injected by the tool wrapper and
hidden from the LLM's schema. On a corpus agent ``document_id`` is injected as
``None`` so the LLM picks which document to operate on; on a document agent it
is pinned to the current document.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q

from opencontractserver.constants.tools import (
    CORPUS_FILE_SEARCH_DEFAULT_LIMIT,
    CORPUS_FILE_SEARCH_MAX_LIMIT,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath

from ._helpers import (
    _db_sync_to_async,
    clamp_limit,
    get_user_or_none,
    require_user,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Search (read-only)                                                          #
# --------------------------------------------------------------------------- #


def search_corpus_documents(
    *,
    corpus_id: int,
    query: str | None = None,
    folder_id: int | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Search the documents (files) in a corpus by name.

    Returns one row per matching document with its current corpus path,
    folder, title and file type — enough for the agent to pick a
    ``document_id`` to move/rename/delete, or to answer "what files are in
    this corpus?".

    Matching is case-insensitive against BOTH the document title and its
    corpus filesystem path (filename). Omit ``query`` to list everything
    (still subject to ``limit``). Pass ``folder_id`` to restrict to a single
    folder, or ``include_deleted=True`` to include files currently in the
    corpus trash.

    Args:
        corpus_id: ID of the corpus to search within.
        query: Optional case-insensitive substring matched against the
            document title or path. Omit to list all documents.
        folder_id: Optional folder ID to restrict the search to one folder.
        include_deleted: Include soft-deleted (trashed) documents when True.
        limit: Max number of results (default 25, capped at 200).

    Returns:
        A list of dicts with keys ``document_id``, ``title``, ``path``,
        ``folder_id``, ``folder_name``, ``file_type`` and ``is_deleted``.
    """
    user = get_user_or_none(user_id)

    # IDOR: identical error whether the corpus is missing or merely hidden.
    corpus = Corpus.objects.visible_to_user(user).filter(pk=corpus_id).first()
    if corpus is None:
        raise ValueError(
            f"Corpus with id={corpus_id} does not exist or is not accessible."
        )

    from opencontractserver.corpuses.services import CorpusDocumentService

    # MIN(document, corpus) visibility — never leak a private document that
    # merely happens to live in a corpus the user can read. Keep this lazy: it
    # feeds the DocumentPath filter below as a SQL subquery rather than being
    # materialised into a Python set + large IN (...) clause.
    visible_docs = CorpusDocumentService.get_corpus_documents_visible_to_user(
        user, corpus, include_deleted=include_deleted
    )

    capped_limit = clamp_limit(
        limit, CORPUS_FILE_SEARCH_DEFAULT_LIMIT, CORPUS_FILE_SEARCH_MAX_LIMIT
    )

    # DocumentPath is the source of truth for a file's name/location in the
    # corpus, so drive the listing off the current paths of the visible docs
    # (an empty visible set simply yields an empty result set).
    path_qs = DocumentPath.objects.filter(
        corpus=corpus, is_current=True, document__in=visible_docs
    ).select_related("document", "folder")
    if not include_deleted:
        path_qs = path_qs.filter(is_deleted=False)
    if folder_id is not None:
        path_qs = path_qs.filter(folder_id=folder_id)
    if query and query.strip():
        term = query.strip()
        path_qs = path_qs.filter(
            Q(path__icontains=term) | Q(document__title__icontains=term)
        )

    results: list[dict[str, Any]] = []
    for path in path_qs.order_by("path")[:capped_limit]:
        results.append(
            {
                "document_id": path.document_id,
                "title": path.document.title,
                "path": path.path,
                "folder_id": path.folder_id,
                "folder_name": path.folder.name if path.folder else None,
                "file_type": path.document.file_type,
                "is_deleted": path.is_deleted,
            }
        )
    return results


async def asearch_corpus_documents(
    *,
    corpus_id: int,
    query: str | None = None,
    folder_id: int | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Async variant of :func:`search_corpus_documents`."""
    return await _db_sync_to_async(search_corpus_documents)(
        corpus_id=corpus_id,
        query=query,
        folder_id=folder_id,
        include_deleted=include_deleted,
        limit=limit,
        user_id=user_id,
    )


# --------------------------------------------------------------------------- #
# Move (read/write — folder placement)                                        #
# --------------------------------------------------------------------------- #


def move_document(
    document_id: int,
    corpus_id: int,
    # author_id is always injected from agent context (never LLM-provided),
    # so it is required (int) rather than the int | None = None convention
    # used by tools where the parameter may be absent.
    author_id: int,
    target_folder_id: int | None = None,
) -> dict[str, Any]:
    """
    Move a document to a different folder within the current corpus.

    Updates the document's path in the corpus folder hierarchy. Pass
    target_folder_id=None (or omit it) to move the document to the corpus root.
    Requires write permission on the corpus.

    Args:
        document_id: ID of the document to move
        corpus_id: ID of the corpus the document belongs to
        author_id: ID of the user performing the move
        target_folder_id: ID of the destination folder, or None for corpus root

    Returns:
        A dictionary describing the move result

    Raises:
        ValueError: If any referenced object does not exist or the move fails
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.corpuses.services import (
        FolderCRUDService,
        FolderDocumentService,
    )

    User = get_user_model()

    # Resolve entities — resolve user first so we can scope subsequent lookups
    # to objects visible to that user (IDOR prevention per CLAUDE.md).
    try:
        user = User.objects.get(pk=author_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={author_id} does not exist.")

    try:
        corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
    except Corpus.DoesNotExist:
        raise ValueError(
            f"Corpus with id={corpus_id} does not exist or is not accessible."
        )

    try:
        document = Document.objects.visible_to_user(user).get(pk=document_id)
    except Document.DoesNotExist:
        raise ValueError(
            f"Document with id={document_id} does not exist or is not accessible."
        )

    target_folder = None
    if target_folder_id is not None:
        target_folder = FolderCRUDService.get_folder_by_id(user, target_folder_id)
        # Early cross-corpus check: reject folders from other corpuses with
        # the same generic error as not-found/inaccessible (IDOR prevention).
        # Note: move_document_to_folder also validates this, but we check here
        # first to keep the error surface consistent — without this guard a
        # readable-but-wrong-corpus folder would produce a different error
        # message than an inaccessible one, leaking information.
        if target_folder is None or target_folder.corpus_id != corpus.id:
            raise ValueError(
                f"Folder with id={target_folder_id} does not exist "
                "or is not accessible."
            )

    success, error = FolderDocumentService.move_document_to_folder(
        user=user,
        document=document,
        corpus=corpus,
        folder=target_folder,
    )

    if not success:
        raise ValueError(f"Move failed: {error}")

    destination = (
        f"folder '{target_folder.name}' (id={target_folder.id})"
        if target_folder
        else "corpus root"
    )

    return {
        "status": "moved",
        "document_id": document_id,
        "corpus_id": corpus_id,
        "target_folder_id": target_folder_id,
        "message": f"Document {document_id} moved to {destination} in corpus {corpus_id}.",
    }


async def amove_document(
    document_id: int,
    corpus_id: int,
    # See move_document() for why author_id is int (not int | None = None).
    author_id: int,
    target_folder_id: int | None = None,
) -> dict[str, Any]:
    """Async wrapper around :func:`move_document`."""
    return await _db_sync_to_async(move_document)(
        document_id=document_id,
        corpus_id=corpus_id,
        author_id=author_id,
        target_folder_id=target_folder_id,
    )


# --------------------------------------------------------------------------- #
# Rename (write — filename only)                                              #
# --------------------------------------------------------------------------- #


def rename_document(
    *,
    document_id: int,
    corpus_id: int,
    new_name: str,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Rename a document's file within the current corpus.

    Changes only the filename (the last path segment); the document stays in
    its current folder. Provide ``new_name`` as the desired filename — if you
    omit the extension it is preserved from the current name (e.g. renaming
    "report.pdf" to "Q3 Summary" yields "Q3_Summary.pdf"). Names are
    sanitised, so characters other than letters/digits/``-_.`` (including
    slashes) become ``_``; use ``move_document`` to change folders.

    Requires write (UPDATE) permission on the corpus.

    Args:
        document_id: ID of the document to rename.
        corpus_id: ID of the corpus the document belongs to.
        new_name: New filename for the document.
        user_id: ID of the user performing the rename.

    Returns:
        A dict with keys ``status``, ``document_id``, ``corpus_id``, ``path``
        (the resulting path string) and a human-readable ``message``.
        ``status`` is ``"renamed"`` when the filename actually changed and
        ``"unchanged"`` for a no-op (the sanitised name matched the current
        one), so the agent does not retry thinking the write failed.

    Raises:
        PermissionError: If there is no authenticated user.
        ValueError: If the document/corpus is not accessible or the rename
            fails.
    """
    user = require_user(user_id, "rename_document")

    corpus = Corpus.objects.visible_to_user(user).filter(pk=corpus_id).first()
    if corpus is None:
        raise ValueError(
            f"Corpus with id={corpus_id} does not exist or is not accessible."
        )

    document = Document.objects.visible_to_user(user).filter(pk=document_id).first()
    if document is None:
        raise ValueError(
            f"Document with id={document_id} does not exist or is not accessible."
        )

    from opencontractserver.corpuses.services import FolderDocumentService

    # The service reports whether the filename actually changed via ``changed``,
    # so the tool no longer snapshots the pre-rename path to infer a no-op — this
    # drops an extra query and closes the snapshot/service race that could mislabel
    # a concurrent rename's status.
    success, error, new_path, changed = FolderDocumentService.rename_document(
        user=user,
        document=document,
        corpus=corpus,
        new_name=new_name,
    )
    if not success:
        raise ValueError(f"Rename failed: {error}")

    return {
        "status": "renamed" if changed else "unchanged",
        "document_id": document_id,
        "corpus_id": corpus_id,
        "path": new_path,
        "message": (
            f"Document {document_id} renamed to '{new_path}' in corpus {corpus_id}."
            if changed
            else f"Document {document_id} already named '{new_path}' in corpus "
            f"{corpus_id}; no change made."
        ),
    }


async def arename_document(
    *,
    document_id: int,
    corpus_id: int,
    new_name: str,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Async wrapper around :func:`rename_document`."""
    return await _db_sync_to_async(rename_document)(
        document_id=document_id,
        corpus_id=corpus_id,
        new_name=new_name,
        user_id=user_id,
    )


# --------------------------------------------------------------------------- #
# Delete (write — soft-delete to corpus trash)                                #
# --------------------------------------------------------------------------- #


def delete_document(
    *,
    document_id: int,
    corpus_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Soft-delete a document from the current corpus (move it to the trash).

    The document is moved to the corpus trash, not erased — it keeps its full
    path history and can be restored later from the corpus file browser.
    Requires DELETE permission on the corpus.

    Args:
        document_id: ID of the document to delete.
        corpus_id: ID of the corpus to remove the document from.
        user_id: ID of the user performing the deletion.

    Returns:
        A dict with keys ``status``, ``document_id``, ``corpus_id`` and a
        human-readable ``message``.

    Raises:
        PermissionError: If there is no authenticated user.
        ValueError: If the document/corpus is not accessible or the delete
            fails.
    """
    user = require_user(user_id, "delete_document")

    corpus = Corpus.objects.visible_to_user(user).filter(pk=corpus_id).first()
    if corpus is None:
        raise ValueError(
            f"Corpus with id={corpus_id} does not exist or is not accessible."
        )

    document = Document.objects.visible_to_user(user).filter(pk=document_id).first()
    if document is None:
        raise ValueError(
            f"Document with id={document_id} does not exist or is not accessible."
        )

    from opencontractserver.corpuses.services import DocumentLifecycleService

    success, error = DocumentLifecycleService.soft_delete_document(
        user=user,
        document=document,
        corpus=corpus,
    )
    if not success:
        raise ValueError(f"Delete failed: {error}")

    return {
        "status": "deleted",
        "document_id": document_id,
        "corpus_id": corpus_id,
        "message": (
            f"Document {document_id} moved to trash in corpus {corpus_id}. "
            "It can be restored from the corpus trash."
        ),
    }


async def adelete_document(
    *,
    document_id: int,
    corpus_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Async wrapper around :func:`delete_document`."""
    return await _db_sync_to_async(delete_document)(
        document_id=document_id,
        corpus_id=corpus_id,
        user_id=user_id,
    )
