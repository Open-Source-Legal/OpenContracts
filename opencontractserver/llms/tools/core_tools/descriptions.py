"""Tools for reading or updating ``Corpus`` and ``Document`` descriptions."""

from typing import Any

from opencontractserver.constants.truncation import (
    MAX_DESCRIPTION_RESPONSE_PREVIEW_LENGTH,
)
from opencontractserver.corpuses.models import Corpus, CorpusDescriptionRevision
from opencontractserver.documents.models import Document
from opencontractserver.utils.text import truncate

from ._helpers import _apply_ndiff_patch, _db_sync_to_async

# --------------------------------------------------------------------------- #
# Corpus description helpers                                                  #
# --------------------------------------------------------------------------- #


def get_corpus_description(
    corpus_id: int,
    truncate_length: int | None = None,
    from_start: bool = True,
) -> str:
    """Return the latest markdown description for a corpus.

    Parameters
    ----------
    corpus_id: int
        Primary key of the `Corpus`.
    truncate_length: int | None, optional
        If provided, returns at most this many characters. Positive values only.
    from_start: bool
        If ``True`` truncates from the beginning; otherwise from the end.
    """

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus with id={corpus_id} does not exist.") from exc

    if not corpus.md_description:
        return ""

    with corpus.md_description.open("r") as fh:
        content = fh.read()

    if truncate_length and truncate_length > 0:
        content = (
            content[:truncate_length] if from_start else content[-truncate_length:]
        )

    return content


async def aget_corpus_description(
    corpus_id: int,
    truncate_length: int | None = None,
    from_start: bool = True,
) -> str:
    """Async implementation of :func:`get_corpus_description` using native ORM calls."""

    from opencontractserver.corpuses.models import Corpus  # local import

    try:
        corpus = await Corpus.objects.aget(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus with id={corpus_id} does not exist.") from exc

    if not corpus.md_description:
        return ""

    corpus.md_description.open("r")  # type: ignore[arg-type]
    try:
        content: str = corpus.md_description.read()
    finally:
        corpus.md_description.close()

    if truncate_length and truncate_length > 0:
        content = (
            content[:truncate_length] if from_start else content[-truncate_length:]
        )

    return content


def update_corpus_description(
    *,
    corpus_id: int,
    new_content: str | None = None,
    diff_text: str | None = None,
    author_id: int | None = None,
    author=None,
) -> CorpusDescriptionRevision | None:
    """Patch or replace a corpus markdown description.

    Provide either *new_content* or an ``ndiff`` *diff_text* that will be
    applied to the current description.  Mirrors the behaviour of
    :py:meth:`Corpus.update_description`.
    """

    if new_content is None and diff_text is None:
        raise ValueError("Provide either new_content or diff_text")

    if new_content is not None and diff_text is not None:
        raise ValueError("Provide only one of new_content or diff_text, not both")

    if author is None and author_id is None:
        raise ValueError("Provide either author or author_id.")

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus with id={corpus_id} does not exist.") from exc

    if diff_text is not None:
        # Need current content
        current = corpus._read_md_description_content()
        new_content = _apply_ndiff_patch(current, diff_text)

    return corpus.update_description(
        new_content=new_content, author=author or author_id
    )


async def aupdate_corpus_description(
    *,
    corpus_id: int,
    new_content: str | None = None,
    diff_text: str | None = None,
    author_id: int | None = None,
    author=None,
):
    """Async variant of :func:`update_corpus_description` using database_sync_to_async.

    Since Django 4.2 doesn't support async transactions, we wrap the synchronous
    version using channels' database_sync_to_async for proper database handling.
    """

    # Use the _db_sync_to_async wrapper defined above to call the sync version
    return await _db_sync_to_async(update_corpus_description)(
        corpus_id=corpus_id,
        new_content=new_content,
        diff_text=diff_text,
        author_id=author_id,
        author=author,
    )


# --------------------------------------------------------------------------- #
# Document description helpers                                                #
# --------------------------------------------------------------------------- #


def get_document_description(
    document_id: int,
    truncate_length: int | None = None,
    from_start: bool = True,
) -> str:
    """Return the description for a document.

    Parameters
    ----------
    document_id: int
        Primary key of the Document.
    truncate_length: int | None, optional
        If provided, returns at most this many characters.
    from_start: bool
        If True truncates from the beginning; otherwise from the end.

    Returns
    -------
    str
        The document description, or empty string if none exists.

    Raises
    ------
    ValueError
        If document doesn't exist.
    """
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document with id={document_id} does not exist.") from exc

    content = doc.description or ""

    if truncate_length and truncate_length > 0:
        content = (
            content[:truncate_length] if from_start else content[-truncate_length:]
        )

    return content


async def aget_document_description(
    document_id: int,
    truncate_length: int | None = None,
    from_start: bool = True,
) -> str:
    """Async version of get_document_description."""
    return await _db_sync_to_async(get_document_description)(
        document_id=document_id,
        truncate_length=truncate_length,
        from_start=from_start,
    )


def update_document_description(
    *,
    document_id: int,
    new_description: str,
) -> dict[str, Any]:
    """Update a document's description.

    Parameters
    ----------
    document_id: int
        Primary key of the Document.
    new_description: str
        The new description content.

    Returns
    -------
    dict[str, Any]
        Information about the update including previous and new description.

    Raises
    ------
    ValueError
        If document doesn't exist.
    """
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document with id={document_id} does not exist.") from exc

    old_description = doc.description or ""

    # Check if there's actually a change
    if old_description == new_description:
        return {
            "updated": False,
            "document_id": document_id,
            "message": "No change in description",
        }

    # Update the description
    doc.description = new_description
    doc.save(update_fields=["description", "modified"])

    return {
        "updated": True,
        "document_id": document_id,
        # truncate() returns "" for None/empty; convert back to None to
        # match the original contract of this response dict.
        "previous_description": truncate(
            old_description, MAX_DESCRIPTION_RESPONSE_PREVIEW_LENGTH
        )
        or None,
        "new_description_preview": truncate(
            new_description, MAX_DESCRIPTION_RESPONSE_PREVIEW_LENGTH
        )
        or None,
    }


async def aupdate_document_description(
    *,
    document_id: int,
    new_description: str,
) -> dict[str, Any]:
    """Async version of update_document_description."""
    return await _db_sync_to_async(update_document_description)(
        document_id=document_id,
        new_description=new_description,
    )
