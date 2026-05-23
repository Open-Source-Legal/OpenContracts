"""Tools that operate on a document's place within a corpus folder hierarchy."""

from typing import Any

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

from ._helpers import _db_sync_to_async


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
