"""Framework-agnostic core tool functions for document and note operations."""

import logging
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from typing_extensions import NotRequired, TypedDict

if TYPE_CHECKING:
    from opencontractserver.llms.agents.core_agents import SourceNode

from opencontractserver.annotations.models import Note, NoteRevision
from opencontractserver.constants.truncation import (
    MAX_DESCRIPTION_RESPONSE_PREVIEW_LENGTH,
    MAX_LINK_TITLE_LENGTH,
    MAX_NOTE_CONTENT_PREVIEW_LENGTH,
)
from opencontractserver.corpuses.models import Corpus, CorpusDescriptionRevision
from opencontractserver.documents.models import Document
from opencontractserver.utils.compact_pawls import expand_pawls_pages
from opencontractserver.utils.text import truncate

logger = logging.getLogger(__name__)


def _token_count(text: str) -> int:
    """
    Naive token counting function. Splits on whitespace.
    Replace or augment with more robust tokenization if needed.

    Args:
        text: The text to count tokens for

    Returns:
        Number of tokens (whitespace-separated words)
    """
    return len(text.split())


def load_document_md_summary(
    document_id: int,
    truncate_length: Optional[int] = None,
    from_start: bool = True,
) -> str:
    """
    Load the content of a Document's md_summary_file field.

    Args:
        document_id: The primary key (ID) of the Document
        truncate_length: Optional number of characters to truncate. If provided,
                        returns only that many characters
        from_start: If True, return from the start up to truncate_length.
                   Otherwise, return from the end

    Returns:
        A string containing the content of the md_summary_file (possibly truncated)

    Raises:
        ValueError: If document doesn't exist or has no md_summary_file
    """
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={document_id} does not exist.")

    if not doc.md_summary_file:
        return "NO SUMMARY PREPARED"

    # Read the md_summary_file
    with doc.md_summary_file.open("r") as file_obj:
        content = file_obj.read()
        logger.debug(f"Loaded md_summary_file for document {document_id}")

    if (
        truncate_length is not None
        and isinstance(truncate_length, int)
        and truncate_length > 0
    ):
        if from_start:
            content = content[:truncate_length]
        else:
            content = content[-truncate_length:]

    return content


def get_md_summary_token_length(document_id: int) -> int:
    """
    Calculate the approximate token length of a Document's md_summary_file.
    Uses a naive whitespace-based split for tokenization.

    Args:
        document_id: The primary key (ID) of the Document

    Returns:
        An integer representing the approximate token count of the md_summary_file

    Raises:
        ValueError: If document doesn't exist or has no md_summary_file
    """
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={document_id} does not exist.")

    if not doc.md_summary_file:
        return 0

    with doc.md_summary_file.open("r") as file_obj:
        content = file_obj.read()

    return _token_count(content)


def get_notes_for_document_corpus(
    document_id: int,
    corpus_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Retrieve all Note objects for a given document and (optionally) a specific corpus.

    Args:
        document_id: The primary key (ID) of the Document
        corpus_id: The primary key (ID) of the Corpus, or None if unspecified

    Returns:
        A list of dictionaries, each containing Note data (content truncated to 512 chars):
        [
            {
                "id": <note_id>,
                "title": <title>,
                "content": <content>,
                "creator_id": <creator_id>,
                "created": <created_datetime_iso>,
                "modified": <modified_datetime_iso>,
            },
            ...
        ]

    Raises:
        ValueError: If document doesn't exist
    """
    # Verify document exists
    if not Document.objects.filter(pk=document_id).exists():
        raise ValueError(f"Document with id={document_id} does not exist.")

    note_query = Note.objects.filter(document_id=document_id)
    if corpus_id is not None:
        note_query = note_query.filter(corpus_id=corpus_id)

    notes = note_query.order_by("created")
    return [
        {
            "id": note.id,
            "title": note.title,
            "content": truncate(note.content, MAX_NOTE_CONTENT_PREVIEW_LENGTH),
            "creator_id": note.creator_id,
            "created": note.created.isoformat() if note.created else None,
            "modified": note.modified.isoformat() if note.modified else None,
        }
        for note in notes
    ]


def get_note_content_token_length(note_id: int) -> int:
    """
    Calculate the approximate token length of a Note's content using naive whitespace-based split.

    Args:
        note_id: The primary key (ID) of the Note

    Returns:
        An integer representing the approximate token count of the note's content

    Raises:
        ValueError: If note doesn't exist
    """
    try:
        note = Note.objects.get(pk=note_id)
    except Note.DoesNotExist:
        raise ValueError(f"Note with id={note_id} does not exist.")

    return _token_count(note.content or "")


def get_partial_note_content(
    note_id: int,
    start: int = 0,
    end: int = 500,
) -> str:
    """
    Retrieve a substring of the note's content from index 'start' to index 'end'.

    Args:
        note_id: The primary key (ID) of the Note
        start: The starting position for extraction
        end: The position at which to stop before extraction (non-inclusive)

    Returns:
        A string representing the specified portion of the note's content

    Raises:
        ValueError: If note doesn't exist or invalid start/end indices
    """
    try:
        note = Note.objects.get(pk=note_id)
    except Note.DoesNotExist:
        raise ValueError(f"Note with id={note_id} does not exist.")

    content = note.content or ""

    if start < 0:
        start = 0
    if end < start:
        raise ValueError("End index must be greater than or equal to start index.")

    return content[start:end]


async def aget_note_content_token_length(note_id: int) -> int:
    """
    Calculate the approximate token length of a Note's content using naive whitespace-based split.

    Args:
        note_id: The primary key (ID) of the Note

    Returns:
        An integer representing the approximate token count of the note's content

    Raises:
        ValueError: If note doesn't exist
    """
    try:
        note = await Note.objects.aget(pk=note_id)
    except Note.DoesNotExist:
        raise ValueError(f"Note with id={note_id} does not exist.")

    return _token_count(note.content or "")


async def aget_partial_note_content(
    note_id: int,
    start: int = 0,
    end: int = 500,
) -> str:
    """
    Retrieve a substring of the note's content from index 'start' to index 'end'.

    Args:
        note_id: The primary key (ID) of the Note
        start: The starting position for extraction
        end: The position at which to stop before extraction (non-inclusive)

    Returns:
        A string representing the specified portion of the note's content

    Raises:
        ValueError: If note doesn't exist or invalid start/end indices
    """
    try:
        note = await Note.objects.aget(pk=note_id)
    except Note.DoesNotExist:
        raise ValueError(f"Note with id={note_id} does not exist.")

    content = note.content or ""

    if start < 0:
        start = 0
    if end < start:
        raise ValueError("End index must be greater than or equal to start index.")

    return content[start:end]


async def aget_md_summary_token_length(document_id: int) -> int:
    """
    Async version: Calculate the approximate token length of a Document's md_summary_file.
    Uses a naive whitespace-based split for tokenization.

    Args:
        document_id: The primary key (ID) of the Document

    Returns:
        An integer representing the approximate token count of the md_summary_file

    Raises:
        ValueError: If document doesn't exist or has no md_summary_file
    """
    try:
        from opencontractserver.documents.models import Document

        doc = await Document.objects.aget(pk=document_id)
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={document_id} does not exist.")

    if not doc.md_summary_file:
        return 0

    with doc.md_summary_file.open("r") as file_obj:
        content = file_obj.read()

    return _token_count(content)


async def aload_document_md_summary(
    document_id: int,
    truncate_length: Optional[int] = None,
    from_start: bool = True,
) -> str:
    """
    Async version: Load and return the content of a Document's md_summary_file.

    Args:
        document_id: The primary key (ID) of the Document
        truncate_length: Optional length to truncate the content
        from_start: If True, truncate from start; if False, truncate from end

    Returns:
        The content of the md_summary_file as a string

    Raises:
        ValueError: If document doesn't exist or has no md_summary_file
    """
    try:
        from opencontractserver.documents.models import Document

        doc = await Document.objects.aget(pk=document_id)
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={document_id} does not exist.")

    if not doc.md_summary_file:
        return "NO SUMMARY PREPARED"

    with doc.md_summary_file.open("r") as file_obj:
        content = file_obj.read()
        logger.debug(f"Loaded md_summary_file for document {document_id}")

    if (
        truncate_length is not None
        and isinstance(truncate_length, int)
        and truncate_length > 0
    ):
        if from_start:
            content = content[:truncate_length]
        else:
            content = content[-truncate_length:]

    return content


async def aget_notes_for_document_corpus(
    document_id: int,
    corpus_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Async version: Retrieve all Note objects for a given document and (optionally) a specific corpus.

    Args:
        document_id: The primary key (ID) of the Document
        corpus_id: The primary key (ID) of the Corpus, or None if unspecified

    Returns:
        A list of dictionaries, each containing Note data

    Raises:
        ValueError: If document doesn't exist
    """
    from opencontractserver.annotations.models import Note

    if not await Document.objects.filter(pk=document_id).aexists():
        raise ValueError(f"Document with id={document_id} does not exist.")

    queryset = Note.objects.filter(document_id=document_id)

    if corpus_id is not None:
        queryset = queryset.filter(corpus_id=corpus_id)

    notes = []
    async for note in queryset.order_by("created"):
        notes.append(
            {
                "id": note.id,
                "title": note.title,
                "content": truncate(note.content, MAX_NOTE_CONTENT_PREVIEW_LENGTH),
                "creator_id": note.creator_id,
                "created": note.created.isoformat() if note.created else None,
                "modified": note.modified.isoformat() if note.modified else None,
            }
        )

    return notes


# --------------------------------------------------------------------------- #
# We need a robust helper that **always** executes the wrapped function in a
# *fresh* worker thread so the database connection opened inside that thread is
# guaranteed to be valid for the lifetime of the call.  Re-using the same
# thread between subsequent invocations (the default behaviour when
# ``thread_sensitive=True``) risks the connection becoming stale once Django
# closes it at the end of a test case – ultimately raising the dreaded
# "the connection is closed" OperationalError when the old thread is re-used.
#
# To avoid this we create a partially-applied wrapper with
# ``thread_sensitive=False`` irrespective of whether Channels is installed.  We
# fall back to ``asgiref.sync.sync_to_async`` when Channels is unavailable,
# applying the same parameter.
# --------------------------------------------------------------------------- #

try:
    from channels.db import (
        database_sync_to_async as _database_sync_to_async,  # type: ignore
    )

    _db_sync_to_async = partial(_database_sync_to_async, thread_sensitive=False)  # type: ignore
except ModuleNotFoundError:  # Channels not installed – fall back gracefully
    from asgiref.sync import sync_to_async as _sync_to_async  # type: ignore

    _db_sync_to_async = partial(_sync_to_async, thread_sensitive=False)  # type: ignore


# --------------------------------------------------------------------------- #
# Plain-text extract helpers                                                  #
# --------------------------------------------------------------------------- #

# Cache now stores a tuple of (last_modified timestamp, file contents) so we can
# transparently invalidate entries when the underlying file changes.
_DOC_TXT_CACHE: dict[int, tuple["datetime", str]] = {}


def load_document_txt_extract(
    document_id: int,
    start: int | None = None,
    end: int | None = None,
    *,
    refresh: bool = False,
) -> str:
    """Load the plain-text extraction stored in a Document's ``txt_extract_file``.

    The returned string can be sliced by providing *start* and *end* character
    indices. Supplying *refresh=True* forces a cache miss, re-reading the file
    from disk even if a cached copy exists.

    Parameters
    ----------
    document_id:
        Primary key of the :class:`~opencontractserver.documents.models.Document`.
    start:
        Optional inclusive start index. Defaults to ``0`` when *None*.
    end:
        Optional exclusive end index. Defaults to the end of the file when
        *None*.
    refresh:
        If ``True`` the cached content for *document_id* is discarded and the
        file is read from disk again.

    Returns
    -------
    str
        The requested slice of the document's text extract.

    Raises
    ------
    ValueError
        If the document does not exist, has no ``txt_extract_file`` attached, or
        if *start*/*end* indices are invalid.
    """
    from opencontractserver.documents.models import (  # local import to avoid circular deps
        Document,
    )

    # Retrieve the document regardless – we need its `modified` timestamp to
    # determine cache validity.
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document with id={document_id} does not exist.") from exc

    if not doc.txt_extract_file:
        raise ValueError("No txt_extract_file attached to this document.")

    # Decide whether to use the cached value.
    use_cache = False
    if not refresh and document_id in _DOC_TXT_CACHE:
        cached_ts, _ = _DOC_TXT_CACHE[document_id]
        use_cache = cached_ts == doc.modified

    if not use_cache:
        # (Re)load from storage.
        content_bytes = doc.txt_extract_file.read()  # type: ignore[arg-type]
        content_str = content_bytes.decode("utf-8")
        _DOC_TXT_CACHE[document_id] = (doc.modified, content_str)

        logger.debug(
            "(Re)cached txt_extract_file for document %s (%d characters, ts=%s)",
            document_id,
            len(content_str),
            doc.modified,
        )

    # Unpack cached tuple.
    content = _DOC_TXT_CACHE[document_id][1]

    # Normalise indices.
    start_idx = 0 if start is None else max(0, start)
    end_idx = len(content) if end is None else end

    if end_idx < start_idx:
        raise ValueError("End index must be greater than or equal to start index.")

    return content[start_idx:end_idx]


async def aload_document_txt_extract(
    document_id: int,
    start: int | None = None,
    end: int | None = None,
    *,
    refresh: bool = False,
) -> str:
    """Asynchronously load a slice of a document's ``txt_extract_file``.

    This implementation avoids the thread-pool wrapper by relying on Django's
    native async ORM utilities (``aget`` et al.). Only file IO remains
    synchronous which is acceptable given the typically small size of the
    text-extract payload.
    """

    from opencontractserver.documents.models import Document  # local import

    # Hard timestamp-aware cache validation.
    if refresh and document_id in _DOC_TXT_CACHE:
        _DOC_TXT_CACHE.pop(document_id, None)

    try:
        doc = await Document.objects.aget(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document with id={document_id} does not exist.") from exc

    if not doc.txt_extract_file:
        raise ValueError("No txt_extract_file attached to this document.")

    use_cache = False
    if not refresh and document_id in _DOC_TXT_CACHE:
        cached_ts, _ = _DOC_TXT_CACHE[document_id]
        use_cache = cached_ts == doc.modified

    if not use_cache:
        content_str = doc.txt_extract_file.read().decode("utf-8")  # type: ignore[arg-type]
        _DOC_TXT_CACHE[document_id] = (doc.modified, content_str)

        logger.debug(
            "(Re)cached txt_extract_file for document %s (%d characters, ts=%s)",
            document_id,
            len(content_str),
            doc.modified,
        )

    content = _DOC_TXT_CACHE[document_id][1]

    # Normalise indices and slice.
    start_idx = 0 if start is None else max(0, start)
    end_idx = len(content) if end is None else end

    if end_idx < start_idx:
        raise ValueError("End index must be greater than or equal to start index.")

    return content[start_idx:end_idx]


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


# --------------------------------------------------------------------------- #
# Document summary helpers                                                    #
# --------------------------------------------------------------------------- #


def get_document_summary(
    document_id: int,
    corpus_id: int,
    truncate_length: int | None = None,
    from_start: bool = True,
) -> str:
    """Return the latest summary content for a document in a specific corpus.

    Parameters
    ----------
    document_id: int
        Primary key of the Document.
    corpus_id: int
        Primary key of the Corpus.
    truncate_length: int | None, optional
        If provided, returns at most this many characters.
    from_start: bool
        If True truncates from the beginning; otherwise from the end.

    Returns
    -------
    str
        The latest summary content, or empty string if none exists.

    Raises
    ------
    ValueError
        If document or corpus doesn't exist.
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document with id={document_id} does not exist.") from exc

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus with id={corpus_id} does not exist.") from exc

    # Use the model's method to get summary
    content = doc.get_summary_for_corpus(corpus=corpus)

    if truncate_length and truncate_length > 0:
        content = (
            content[:truncate_length] if from_start else content[-truncate_length:]
        )

    return content


def get_document_summary_versions(
    document_id: int,
    corpus_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Get the version history for a document's summaries in a specific corpus.

    Parameters
    ----------
    document_id: int
        Primary key of the Document.
    corpus_id: int
        Primary key of the Corpus.
    limit: int | None, optional
        Maximum number of versions to return (most recent first).

    Returns
    -------
    list[dict[str, Any]]
        List of revision data including version, author, created date, and checksums.

    Raises
    ------
    ValueError
        If document doesn't exist.
    """
    from opencontractserver.documents.models import Document, DocumentSummaryRevision

    if not Document.objects.filter(pk=document_id).exists():
        raise ValueError(f"Document with id={document_id} does not exist.")

    query = DocumentSummaryRevision.objects.filter(
        document_id=document_id, corpus_id=corpus_id
    ).order_by("-version")

    if limit and limit > 0:
        query = query[:limit]

    return [
        {
            "id": rev.id,
            "version": rev.version,
            "author_id": rev.author_id,
            "created": rev.created.isoformat() if rev.created else None,
            "checksum_base": rev.checksum_base,
            "checksum_full": rev.checksum_full,
            "has_snapshot": bool(rev.snapshot),
            "has_diff": bool(rev.diff),
        }
        for rev in query
    ]


def get_document_summary_diff(
    document_id: int,
    corpus_id: int,
    from_version: int,
    to_version: int,
) -> dict[str, Any]:
    """Get the diff between two summary versions.

    Parameters
    ----------
    document_id: int
        Primary key of the Document.
    corpus_id: int
        Primary key of the Corpus.
    from_version: int
        Starting version number.
    to_version: int
        Ending version number.

    Returns
    -------
    dict[str, Any]
        Dictionary containing the diff and version information.

    Raises
    ------
    ValueError
        If document, versions don't exist or versions are invalid.
    """
    import difflib

    from opencontractserver.documents.models import Document, DocumentSummaryRevision

    if not Document.objects.filter(pk=document_id).exists():
        raise ValueError(f"Document with id={document_id} does not exist.")

    try:
        from_rev = DocumentSummaryRevision.objects.get(
            document_id=document_id, corpus_id=corpus_id, version=from_version
        )
        to_rev = DocumentSummaryRevision.objects.get(
            document_id=document_id, corpus_id=corpus_id, version=to_version
        )
    except DocumentSummaryRevision.DoesNotExist as exc:
        raise ValueError(
            f"Revision version {from_version} or {to_version} not found for "
            f"document_id={document_id}, corpus_id={corpus_id}"
        ) from exc

    # Get content from snapshots
    from_content = from_rev.snapshot or ""
    to_content = to_rev.snapshot or ""

    # Generate diff
    diff_lines = list(
        difflib.unified_diff(
            from_content.splitlines(keepends=True),
            to_content.splitlines(keepends=True),
            fromfile=f"Version {from_version}",
            tofile=f"Version {to_version}",
            lineterm="",
        )
    )

    return {
        "from_version": from_version,
        "to_version": to_version,
        "from_author_id": from_rev.author_id,
        "to_author_id": to_rev.author_id,
        "from_created": from_rev.created.isoformat() if from_rev.created else None,
        "to_created": to_rev.created.isoformat() if to_rev.created else None,
        "diff": "\n".join(diff_lines),
        "from_content": from_content,
        "to_content": to_content,
    }


def update_document_summary(
    *,
    document_id: int,
    corpus_id: int,
    new_content: str,
    author_id: int | None = None,
    author=None,
) -> dict[str, Any]:
    """Create a new summary revision for a document in a specific corpus.

    Parameters
    ----------
    document_id: int
        Primary key of the Document.
    corpus_id: int
        Primary key of the Corpus.
    new_content: str
        The new summary content.
    author_id: int | None
        User ID of the author (if author object not provided).
    author: User | None
        User object of the author.

    Returns
    -------
    dict[str, Any]
        Information about the created revision including version number.

    Raises
    ------
    ValueError
        If document/corpus doesn't exist or neither author nor author_id provided.
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    if author is None and author_id is None:
        raise ValueError("Provide either author or author_id.")

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document with id={document_id} does not exist.") from exc

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus with id={corpus_id} does not exist.") from exc

    # Use the model's update_summary method
    revision = doc.update_summary(
        new_content=new_content, author=author or author_id, corpus=corpus
    )

    if revision is None:
        # No change was made
        latest_version = (
            doc.summary_revisions.filter(corpus_id=corpus_id)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        ) or 0

        return {
            "created": False,
            "version": latest_version,
            "message": "No change in content",
        }

    return {
        "created": True,
        "version": revision.version,
        "revision_id": revision.id,
        "author_id": revision.author_id,
        "created_at": revision.created.isoformat() if revision.created else None,
        "checksum": revision.checksum_full,
    }


def get_document_summary_at_version(
    document_id: int,
    corpus_id: int,
    version: int,
) -> str:
    """Get the summary content at a specific version.

    Parameters
    ----------
    document_id: int
        Primary key of the Document.
    corpus_id: int
        Primary key of the Corpus.
    version: int
        The version number to retrieve.

    Returns
    -------
    str
        The summary content at the specified version.

    Raises
    ------
    ValueError
        If document or version doesn't exist.
    """
    from opencontractserver.documents.models import Document, DocumentSummaryRevision

    if not Document.objects.filter(pk=document_id).exists():
        raise ValueError(f"Document with id={document_id} does not exist.")

    try:
        revision = DocumentSummaryRevision.objects.get(
            document_id=document_id, corpus_id=corpus_id, version=version
        )
    except DocumentSummaryRevision.DoesNotExist as exc:
        raise ValueError(
            f"Version {version} not found for document_id={document_id}, corpus_id={corpus_id}"
        ) from exc

    return revision.snapshot or ""


# Async versions
async def aget_document_summary(
    document_id: int,
    corpus_id: int,
    truncate_length: int | None = None,
    from_start: bool = True,
) -> str:
    """Async version of get_document_summary."""
    return await _db_sync_to_async(get_document_summary)(
        document_id=document_id,
        corpus_id=corpus_id,
        truncate_length=truncate_length,
        from_start=from_start,
    )


async def aget_document_summary_versions(
    document_id: int,
    corpus_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Async version of get_document_summary_versions."""
    return await _db_sync_to_async(get_document_summary_versions)(
        document_id=document_id,
        corpus_id=corpus_id,
        limit=limit,
    )


async def aget_document_summary_diff(
    document_id: int,
    corpus_id: int,
    from_version: int,
    to_version: int,
) -> dict[str, Any]:
    """Async version of get_document_summary_diff."""
    return await _db_sync_to_async(get_document_summary_diff)(
        document_id=document_id,
        corpus_id=corpus_id,
        from_version=from_version,
        to_version=to_version,
    )


async def aupdate_document_summary(
    *,
    document_id: int,
    corpus_id: int,
    new_content: str,
    author_id: int | None = None,
    author=None,
) -> dict[str, Any]:
    """Async version of update_document_summary."""
    return await _db_sync_to_async(update_document_summary)(
        document_id=document_id,
        corpus_id=corpus_id,
        new_content=new_content,
        author_id=author_id,
        author=author,
    )


async def aget_document_summary_at_version(
    document_id: int,
    corpus_id: int,
    version: int,
) -> str:
    """Async version of get_document_summary_at_version."""
    return await _db_sync_to_async(get_document_summary_at_version)(
        document_id=document_id,
        corpus_id=corpus_id,
        version=version,
    )


# --------------------------------------------------------------------------- #
# Note creation / updating                                                    #
# --------------------------------------------------------------------------- #


def add_document_note(
    *,
    document_id: int,
    title: str,
    content: str,
    creator_id: int,
    corpus_id: int | None = None,
) -> Note:
    """Create and return a new Note for a given document."""

    try:
        Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document with id={document_id} does not exist.") from exc

    note = Note.objects.create(
        document_id=document_id,
        corpus_id=corpus_id,
        title=title,
        content=content,
        creator_id=creator_id,
    )

    return note


async def aadd_document_note(
    *,
    document_id: int,
    title: str,
    content: str,
    creator_id: int,
    corpus_id: int | None = None,
):
    """Create a new :class:`~opencontractserver.annotations.models.Note` asynchronously."""

    from opencontractserver.annotations.models import Note
    from opencontractserver.documents.models import Document

    # Ensure the document exists first.
    exists = await Document.objects.filter(pk=document_id).aexists()
    if not exists:
        raise ValueError(f"Document with id={document_id} does not exist.")

    note = await Note.objects.acreate(
        document_id=document_id,
        corpus_id=corpus_id,
        title=title,
        content=content,
        creator_id=creator_id,
    )

    return note


def _apply_ndiff_patch(original: str, diff_text: str) -> str:
    """Return *patched* text by applying an ``ndiff``-style diff.

    Raises ``ValueError`` when the diff cannot be applied.
    """

    import difflib

    try:
        patched_lines = difflib.restore(diff_text.splitlines(keepends=True), 2)
        return "".join(patched_lines)
    except Exception as exc:  # pragma: no cover
        raise ValueError("Failed to apply diff_text to original note content") from exc


def update_document_note(
    *,
    note_id: int,
    new_content: str | None = None,
    diff_text: str | None = None,
    author_id: int | None = None,
) -> NoteRevision | None:
    """Version‐up a note.

    Provide either *new_content* **or** *diff_text* (produced via
    ``difflib.ndiff``). When *diff_text* is given the function patches the
    current content to obtain the updated text.
    """

    if new_content is None and diff_text is None:
        raise ValueError("Provide either new_content or diff_text")

    if new_content is not None and diff_text is not None:
        raise ValueError("Provide only one of new_content or diff_text, not both")

    try:
        note = Note.objects.get(pk=note_id)
    except Note.DoesNotExist as exc:
        raise ValueError(f"Note with id={note_id} does not exist.") from exc

    if diff_text is not None:
        new_content = _apply_ndiff_patch(note.content or "", diff_text)

    return note.version_up(new_content=new_content, author=author_id)


async def aupdate_document_note(
    *,
    note_id: int,
    new_content: str | None = None,
    diff_text: str | None = None,
    author_id: int | None = None,
):
    """Async variant of :func:`update_document_note` using database_sync_to_async.

    Since Django 4.2 doesn't support async transactions, we wrap the synchronous
    version using channels' database_sync_to_async for proper database handling.
    """

    # Use the _db_sync_to_async wrapper defined above to call the sync version
    return await _db_sync_to_async(update_document_note)(
        note_id=note_id,
        new_content=new_content,
        diff_text=diff_text,
        author_id=author_id,
    )


def search_document_notes(
    document_id: int,
    search_term: str,
    *,
    corpus_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, str | int]]:

    import django

    """Return notes for *document_id* whose title or content contains *search_term* (case-insensitive)."""

    if not Document.objects.filter(pk=document_id).exists():
        raise ValueError(f"Document with id={document_id} does not exist.")

    notes_qs = Note.objects.filter(document_id=document_id)

    if corpus_id is not None:
        notes_qs = notes_qs.filter(corpus_id=corpus_id)

    notes_qs = notes_qs.filter(
        django.db.models.Q(title__icontains=search_term)
        | django.db.models.Q(content__icontains=search_term)
    ).order_by("-modified")

    if limit and limit > 0:
        notes_qs = notes_qs[:limit]

    return [
        {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "creator_id": note.creator_id,
            "created": note.created.isoformat() if note.created else None,
            "modified": note.modified.isoformat() if note.modified else None,
        }
        for note in notes_qs
    ]


async def asearch_document_notes(
    document_id: int,
    search_term: str,
    *,
    corpus_id: int | None = None,
    limit: int | None = None,
):
    """Async search for notes matching *search_term* within a document."""

    import django

    from opencontractserver.annotations.models import Note
    from opencontractserver.documents.models import Document

    # Validate document existence.
    exists = await Document.objects.filter(pk=document_id).aexists()
    if not exists:
        raise ValueError(f"Document with id={document_id} does not exist.")

    notes_qs = Note.objects.filter(document_id=document_id)

    if corpus_id is not None:
        notes_qs = notes_qs.filter(corpus_id=corpus_id)

    notes_qs = notes_qs.filter(
        django.db.models.Q(title__icontains=search_term)
        | django.db.models.Q(content__icontains=search_term)
    ).order_by("-modified")

    if limit and limit > 0:
        notes_qs = notes_qs[:limit]

    results: list[dict[str, str | int]] = []
    async for note in notes_qs:
        results.append(
            {
                "id": note.id,
                "title": note.title,
                "content": note.content,
                "creator_id": note.creator_id,
                "created": note.created.isoformat() if note.created else None,
                "modified": note.modified.isoformat() if note.modified else None,
            }
        )

    return results


# --------------------------------------------------------------------------- #
# Annotation duplication helpers                                              #
# --------------------------------------------------------------------------- #


def duplicate_annotations_with_label(
    annotation_ids: list[int],
    *,
    new_label_text: str,
    creator_id: int,
    label_type: str | None = None,
) -> list[int]:
    """Duplicate existing annotations applying *new_label_text* (synchronous).

    This synchronous variant ensures the required label-set and label exist on
    each annotation's corpus *without* relying on any helper methods grafted
    onto the :class:`~opencontractserver.corpuses.models.Corpus` model.

    Parameters
    ----------
    annotation_ids:
        Primary keys of the annotations to duplicate.
    new_label_text:
        The text of the label to assign to the duplicates. Case-sensitive.
    creator_id:
        User identifier recorded as *creator* for both the duplicates and for
        any label/label-set created on-the-fly.
    label_type:
        Optional label type (defaults to ``TOKEN_LABEL`` when *None*).

    Returns
    -------
    list[int]
        Primary keys of the newly created annotations in the same order as the
        input list.
    """

    from django.db import transaction

    from opencontractserver.annotations.models import (
        TOKEN_LABEL,
        Annotation,
        AnnotationLabel,
        LabelSet,
    )

    if label_type is None:
        label_type = TOKEN_LABEL

    # Fetch annotations; keep their database objects in memory while
    # preserving the order of *annotation_ids*.
    annotations = list(
        Annotation.objects.filter(pk__in=annotation_ids).select_related(
            "corpus", "document"
        )
    )

    if len(annotations) != len(annotation_ids):
        missing = set(annotation_ids) - {a.pk for a in annotations}
        raise ValueError(f"Annotation(s) not found: {sorted(missing)}")

    new_ids: list[int] = []
    label_cache: dict[int, AnnotationLabel] = {}

    with transaction.atomic():
        for ann in annotations:
            if ann.corpus_id is None:
                raise ValueError(
                    f"Annotation id={ann.pk} is not associated with a corpus and "
                    "cannot be duplicated with a corpus label."
                )

            corpus = ann.corpus  # already fetched via select_related

            # Obtain / create label for this corpus (use cache to minimise DB chatter).
            label = label_cache.get(corpus.pk)
            if label is None:
                # Ensure corpus has a label-set.
                if corpus.label_set_id is None:
                    corpus.label_set = LabelSet.objects.create(
                        title=f"LabelSet for Corpus {corpus.pk}",
                        description="",
                        creator_id=creator_id,
                    )
                    corpus.save(update_fields=["label_set", "modified"])

                # Look for existing label with given text & type.
                label_qs = corpus.label_set.annotation_labels.filter(
                    text=new_label_text, label_type=label_type
                )
                label = label_qs.first()

                if label is None:
                    label = AnnotationLabel.objects.create(
                        text=new_label_text,
                        label_type=label_type,
                        color="#05313d",
                        description="",
                        icon="tags",
                        creator_id=creator_id,
                    )
                    corpus.label_set.annotation_labels.add(label)

                label_cache[corpus.pk] = label

            # Create the duplicate annotation.
            duplicate = Annotation.objects.create(
                page=ann.page,
                raw_text=ann.raw_text,
                json=ann.json,
                parent=ann.parent,
                annotation_type=ann.annotation_type,
                annotation_label=label,
                document=ann.document,
                corpus=corpus,
                structural=ann.structural,
                creator_id=creator_id,
            )

            new_ids.append(duplicate.pk)

    return new_ids


async def aduplicate_annotations_with_label(
    annotation_ids: list[int],
    *,
    new_label_text: str,
    creator_id: int,
    label_type: str | None = None,
):
    """Async wrapper around :func:`duplicate_annotations_with_label`."""
    return await _db_sync_to_async(duplicate_annotations_with_label)(
        annotation_ids,
        new_label_text=new_label_text,
        creator_id=creator_id,
        label_type=label_type,
    )


# --------------------------------------------------------------------------- #
# Exact-string annotation helper for PDFs                                     #
# --------------------------------------------------------------------------- #


class AnnotationItem(TypedDict):
    """Single annotation request for exact-string matching."""

    label_text: str
    exact_string: str


def add_annotations_from_exact_strings(
    items: list[AnnotationItem],
    *,
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
) -> list[int]:
    """Create annotations for exact string matches in documents.

    Each *item* is a dict with keys:
    - ``label_text`` (str): The label to apply.
    - ``exact_string`` (str): The exact text to find in the document.

    Args:
        document_id: The document to annotate (injected from context).
        corpus_id: The corpus the document belongs to (injected from context).
        creator_id: The user creating annotations (injected from context).
        corpus_action_id: Optional corpus action that triggered this (injected from context).

    • PDF (application/pdf): builds token‐level annotations (TOKEN_LABEL) via PlasmaPDF.
    • Plain-text (application/txt, text/plain): builds span annotations (SPAN_LABEL).

    Other file types raise ``ValueError``.
    """

    import json

    from django.db import transaction
    from plasmapdf.models.PdfDataLayer import build_translation_layer
    from plasmapdf.models.types import SpanAnnotation, TextSpan

    from opencontractserver.annotations.models import (
        SPAN_LABEL,
        TOKEN_LABEL,
        Annotation,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    # Collect (label_text, exact_string) pairs for the single doc/corpus.
    tuples: list[tuple[str, str]] = []
    for item in items:
        tuples.append((str(item["label_text"]), str(item["exact_string"])))

    created_ids: list[int] = []

    doc_id = document_id

    # Validate document & corpus linkage.
    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document id={doc_id} does not exist") from exc

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus id={corpus_id} does not exist") from exc

    if not corpus.get_documents().filter(pk=doc_id).exists():
        raise ValueError(
            f"Document id={doc_id} is not linked to corpus id={corpus_id}."
        )

    file_type = (doc.file_type or "").lower()
    if not file_type:
        raise ValueError(
            f"Document id={doc_id} has no file_type set; cannot create index."
        )

    if file_type == "application/pdf":
        if not doc.pawls_parse_file:
            raise ValueError(
                f"PDF document id={doc_id} lacks a PAWLS layer; cannot annotate."
            )

        # Load PAWLS tokens once per document.
        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        doc_text = pdf_layer.doc_text

        label_type_const = TOKEN_LABEL

        def _create_annotation(pos: int, end_idx: int, label_obj):
            span = TextSpan(
                id=str(uuid4()), start=pos, end=end_idx, text=doc_text[pos:end_idx]
            )
            span_annotation = SpanAnnotation(span=span, annotation_label=label_obj.text)
            oc_ann = pdf_layer.create_opencontract_annotation_from_span(span_annotation)

            return Annotation(
                raw_text=oc_ann["rawText"],
                page=oc_ann.get("page", 1),
                json=oc_ann["annotation_json"],
                annotation_label=label_obj,
                document=doc,
                corpus=corpus,
                creator_id=creator_id,
                corpus_action_id=corpus_action_id,
                annotation_type=TOKEN_LABEL,
                structural=False,
            )

    elif file_type in {"application/txt", "text/plain"}:
        if not doc.txt_extract_file:
            raise ValueError(
                f"Text document id={doc_id} lacks txt_extract_file; cannot annotate."
            )
        with doc.txt_extract_file.open("r") as f:
            doc_text = f.read()

        label_type_const = SPAN_LABEL

        def _create_annotation(pos: int, end_idx: int, label_obj):
            return Annotation(
                raw_text=doc_text[pos:end_idx],
                page=1,
                json={"start": pos, "end": end_idx},
                annotation_label=label_obj,
                document=doc,
                corpus=corpus,
                creator_id=creator_id,
                corpus_action_id=corpus_action_id,
                annotation_type=SPAN_LABEL,
                structural=False,
            )

    else:
        raise ValueError(
            f"Unsupported file_type {doc.file_type} for document id={doc_id}"
        )

    # Common creation loop (works for both PDF and text).
    with transaction.atomic():
        for label_text, exact_str in tuples:
            label_obj = corpus.ensure_label_and_labelset(
                label_text=label_text,
                creator_id=creator_id,
                label_type=label_type_const,
            )

            start_idx = 0
            while True:
                pos = doc_text.find(exact_str, start_idx)
                if pos == -1:
                    break

                end_idx = pos + len(exact_str)

                annot_obj = _create_annotation(pos, end_idx, label_obj)
                annot_obj.save()

                created_ids.append(annot_obj.pk)

                start_idx = end_idx

    return created_ids


async def aadd_annotations_from_exact_strings(
    items: list[AnnotationItem],
    *,
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
):
    """Async wrapper around :func:`add_annotations_from_exact_strings`."""
    return await _db_sync_to_async(add_annotations_from_exact_strings)(
        items,
        document_id=document_id,
        corpus_id=corpus_id,
        creator_id=creator_id,
        corpus_action_id=corpus_action_id,
    )


# --------------------------------------------------------------------------- #
# Document index creation                                                     #
# --------------------------------------------------------------------------- #


class IndexEntryItem(TypedDict):
    """Single entry for building a hierarchical document index."""

    title: str
    exact_string: str
    long_description: NotRequired[str]
    parent_index: NotRequired[int]  # -1 for root entries, otherwise index into the list


def create_document_index(
    entries: list[IndexEntryItem],
    *,
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
) -> list[int]:
    """Create a hierarchical document index from exact string matches.

    Each *entry* is a dict with keys:
    - ``title`` (str): Section heading text.
    - ``exact_string`` (str): The exact text to anchor this section in the
      document.
    - ``long_description`` (str): Markdown summary of the section content.
    - ``parent_index`` (int): Index into *entries* pointing to this entry's
      parent.  Use ``-1`` for root-level entries.

    Annotations are created with the ``OC_SECTION`` label and linked via the
    ``parent`` FK to form a hierarchy.

    .. note::
        ``exact_string`` matching uses the *first* occurrence in the document.
        If the same string appears multiple times, later occurrences cannot be
        targeted.  Use a longer, unique surrounding snippet when ambiguity is
        possible.

    Args:
        entries: List of index entries to create.
        document_id: Target document (injected from context).
        corpus_id: Target corpus (injected from context).
        creator_id: User creating the index (injected from context).
        corpus_action_id: Optional corpus action that triggered this.

    Returns:
        List of created Annotation PKs in the same order as *entries*.
    """

    import json

    from django.db import transaction
    from plasmapdf.models.PdfDataLayer import build_translation_layer
    from plasmapdf.models.types import SpanAnnotation, TextSpan

    from opencontractserver.annotations.models import (
        SPAN_LABEL,
        TOKEN_LABEL,
        Annotation,
    )
    from opencontractserver.constants.annotations import (
        DOCUMENT_ANNOTATION_INDEX_LIMIT,
        OC_SECTION_LABEL,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    if len(entries) > DOCUMENT_ANNOTATION_INDEX_LIMIT:
        raise ValueError(
            f"entries list ({len(entries)}) exceeds maximum allowed size "
            f"of {DOCUMENT_ANNOTATION_INDEX_LIMIT}."
        )

    # Validate document and corpus.
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document id={document_id} does not exist") from exc

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus id={corpus_id} does not exist") from exc

    if not corpus.get_documents().filter(pk=document_id).exists():
        raise ValueError(
            f"Document id={document_id} is not linked to corpus id={corpus_id}."
        )

    file_type = (doc.file_type or "").lower()
    if not file_type:
        raise ValueError(
            f"Document id={document_id} has no file_type set; cannot create index."
        )

    if file_type == "application/pdf":
        if not doc.pawls_parse_file:
            raise ValueError(
                f"PDF document id={document_id} lacks a PAWLS layer; "
                "cannot create index."
            )
        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        doc_text = pdf_layer.doc_text
        label_type_const = TOKEN_LABEL

        def _make_annotation(pos, end_idx, label_obj, title, description):
            span = TextSpan(
                id=str(uuid4()),
                start=pos,
                end=end_idx,
                text=doc_text[pos:end_idx],
            )
            span_annotation = SpanAnnotation(span=span, annotation_label=label_obj.text)
            oc_ann = pdf_layer.create_opencontract_annotation_from_span(span_annotation)
            return Annotation(
                raw_text=title,
                long_description=description,
                page=oc_ann.get("page", 1),
                json=oc_ann["annotation_json"],
                annotation_label=label_obj,
                document=doc,
                corpus=corpus,
                creator_id=creator_id,
                corpus_action_id=corpus_action_id,
                annotation_type=TOKEN_LABEL,
                structural=False,
            )

    elif file_type in {"application/txt", "text/plain"}:
        if not doc.txt_extract_file:
            raise ValueError(
                f"Text document id={document_id} lacks txt_extract_file; "
                "cannot create index."
            )
        with doc.txt_extract_file.open("r") as f:
            doc_text = f.read()

        label_type_const = SPAN_LABEL

        def _make_annotation(pos, end_idx, label_obj, title, description):
            return Annotation(
                raw_text=title,
                long_description=description,
                page=1,
                json={"start": pos, "end": end_idx},
                annotation_label=label_obj,
                document=doc,
                corpus=corpus,
                creator_id=creator_id,
                corpus_action_id=corpus_action_id,
                annotation_type=SPAN_LABEL,
                structural=False,
            )

    else:
        raise ValueError(
            f"Unsupported file_type {doc.file_type} for document id={document_id}"
        )

    # ---- Validate all entries before any DB writes ----

    # Build parent_idx map and check for cycles up-front.
    parent_map: dict[int, int] = {}
    for i, entry in enumerate(entries):
        parent_idx = int(entry.get("parent_index", -1))
        if parent_idx >= 0:
            if parent_idx == i:
                raise ValueError(f"Entry {i} references itself as parent")
            if parent_idx >= len(entries):
                raise ValueError(
                    f"parent_index {parent_idx} out of range for entry {i}"
                )
            parent_map[i] = parent_idx

    for start in parent_map:
        visited: set[int] = set()
        current = start
        while current in parent_map:
            if current in visited:
                raise ValueError(
                    f"Cycle detected in parent_index references "
                    f"involving entry {current}"
                )
            visited.add(current)
            current = parent_map[current]

    # Validate exact strings and build (pos, end_idx) pairs.
    spans: list[tuple[int, int]] = []
    for entry in entries:
        exact_str = str(entry["exact_string"])
        pos = doc_text.find(exact_str)
        if pos == -1:
            raise ValueError(
                f"Exact string not found in document: {repr(exact_str[:80])}"
            )
        if doc_text.find(exact_str, pos + 1) != -1:
            logger.warning(
                "exact_string %r appears multiple times in document "
                "id=%d; anchoring to first occurrence.",
                exact_str[:80],
                document_id,
            )
        spans.append((pos, pos + len(exact_str)))

    # ---- All validation passed — perform DB writes ----

    with transaction.atomic():
        label_obj = corpus.ensure_label_and_labelset(
            label_text=OC_SECTION_LABEL,
            creator_id=creator_id,
            label_type=label_type_const,
        )

        annotations = [
            _make_annotation(
                pos,
                end_idx,
                label_obj,
                str(entry["title"]),
                entry.get("long_description") or None,
            )
            for (pos, end_idx), entry in zip(spans, entries)
        ]
        created = Annotation.objects.bulk_create(annotations)

        # Wire up parent hierarchy in bulk.
        to_update = []
        for i, parent_idx in parent_map.items():
            created[i].parent = created[parent_idx]
            to_update.append(created[i])
        if to_update:
            Annotation.objects.bulk_update(to_update, ["parent"])

    return [a.pk for a in created]


async def acreate_document_index(
    entries: list[IndexEntryItem],
    *,
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
) -> list[int]:
    """Async wrapper around :func:`create_document_index`."""
    return await _db_sync_to_async(create_document_index)(
        entries,
        document_id=document_id,
        corpus_id=corpus_id,
        creator_id=creator_id,
        corpus_action_id=corpus_action_id,
    )


# --------------------------------------------------------------------------- #
# Exact-text search returning SourceNode objects                             #
# --------------------------------------------------------------------------- #


def search_exact_text_as_sources(
    document_id: int,
    search_strings: list[str],
    corpus_id: int | None = None,
) -> list["SourceNode"]:
    """Find exact text matches and return them as SourceNode objects.

    This function reuses the same document loading logic as
    :func:`add_annotations_from_exact_strings` but returns source objects
    instead of creating annotations.

    For PDFs: Uses PAWLS layer + PlasmaPDF to get token positions, pages, bounding boxes.
    For Text: Uses txt_extract file to get character spans.

    Parameters
    ----------
    document_id: int
        Primary key of the Document to search.
    search_strings: list[str]
        List of exact strings to find. All occurrences of each string will be found.
    corpus_id: int | None
        Optional corpus context. Used for metadata only (not for validation).

    Returns
    -------
    list[SourceNode]
        Flattened list of all matches as SourceNode objects with:
        - annotation_id: Synthetic negative ID (unique per match)
        - content: The matched text
        - similarity_score: 1.0 (perfect match)
        - metadata: document_id, corpus_id, page, position info, search_string

    Raises
    ------
    ValueError
        If document doesn't exist or has unsupported file type.
    """
    import json

    from plasmapdf.models.PdfDataLayer import build_translation_layer
    from plasmapdf.models.types import SpanAnnotation, TextSpan

    # Import SourceNode from core_agents to avoid circular dependencies
    from opencontractserver.llms.agents.core_agents import SourceNode

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document id={document_id} does not exist") from exc

    file_type = (doc.file_type or "").lower()
    sources: list[SourceNode] = []
    synthetic_id_counter = -1  # Start with negative IDs

    if file_type == "application/pdf":
        if not doc.pawls_parse_file:
            raise ValueError(
                f"PDF document id={document_id} lacks a PAWLS layer; cannot search."
            )

        # Load PAWLS tokens once
        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        doc_text = pdf_layer.doc_text

        # Find all matches for each search string
        for search_str in search_strings:
            start_idx = 0
            while True:
                pos = doc_text.find(search_str, start_idx)
                if pos == -1:
                    break

                end_idx = pos + len(search_str)

                # Create TextSpan and SpanAnnotation to get bounding box info
                span = TextSpan(
                    id=str(uuid4()),
                    start=pos,
                    end=end_idx,
                    text=doc_text[pos:end_idx],
                )

                span_annotation = SpanAnnotation(
                    span=span, annotation_label=""  # No label needed for search results
                )

                # Get OpenContracts annotation structure (has page, bounding_box, etc.)
                oc_ann = pdf_layer.create_opencontract_annotation_from_span(
                    span_annotation
                )

                # Build SourceNode
                sources.append(
                    SourceNode(
                        annotation_id=synthetic_id_counter,
                        content=doc_text[pos:end_idx],
                        similarity_score=1.0,  # Perfect match
                        metadata={
                            "document_id": document_id,
                            "corpus_id": corpus_id,
                            "page": oc_ann.get("page", 1),
                            "annotation_json": oc_ann[
                                "annotation_json"
                            ],  # Full MultipageAnnotationJson from PlasmaPDF
                            "search_string": search_str,
                            "char_start": pos,
                            "char_end": end_idx,
                            "bounding_box": oc_ann.get("bounds"),
                            "match_type": "exact_text_pdf",
                        },
                    )
                )

                synthetic_id_counter -= 1
                start_idx = end_idx

    elif file_type in {"application/txt", "text/plain"}:
        if not doc.txt_extract_file:
            raise ValueError(
                f"Text document id={document_id} lacks txt_extract_file; cannot search."
            )

        with doc.txt_extract_file.open("r") as f:
            doc_text = f.read()

        # Find all matches for each search string
        for search_str in search_strings:
            start_idx = 0
            while True:
                pos = doc_text.find(search_str, start_idx)
                if pos == -1:
                    break

                end_idx = pos + len(search_str)

                # Build SourceNode (text files = page 1, no bounding box)
                sources.append(
                    SourceNode(
                        annotation_id=synthetic_id_counter,
                        content=doc_text[pos:end_idx],
                        similarity_score=1.0,  # Perfect match
                        metadata={
                            "document_id": document_id,
                            "corpus_id": corpus_id,
                            "page": 1,
                            "search_string": search_str,
                            "char_start": pos,
                            "char_end": end_idx,
                            "match_type": "exact_text_plain",
                        },
                    )
                )

                synthetic_id_counter -= 1
                start_idx = end_idx

    else:
        raise ValueError(
            f"Unsupported file_type {doc.file_type} for document id={document_id}"
        )

    return sources


async def asearch_exact_text_as_sources(
    document_id: int,
    search_strings: list[str],
    corpus_id: int | None = None,
):
    """Async wrapper around :func:`search_exact_text_as_sources`."""
    return await _db_sync_to_async(search_exact_text_as_sources)(
        document_id=document_id,
        search_strings=search_strings,
        corpus_id=corpus_id,
    )


def get_page_image(
    document_id: int,
    page_number: int,
    image_format: str = "jpeg",
    dpi: int = 150,
) -> str:
    """
    Get a specific page from a PDF document as a base64-encoded image.
    This allows agents to visually inspect pages for diagrams, images, tables, and other visual content.

    Args:
        document_id: The primary key (ID) of the Document
        page_number: The page number to render (1-indexed)
        image_format: The image format to use ('jpeg' or 'png'), defaults to 'jpeg'
        dpi: The resolution in dots per inch (default 150, higher values = better quality but larger files)

    Returns:
        A base64-encoded string of the page image

    Raises:
        ValueError: If document doesn't exist, has no PDF file, page number is invalid, or format is unsupported
    """
    import base64
    import io

    from pdf2image import convert_from_bytes

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={document_id} does not exist.")

    # Check if document is a PDF
    if doc.file_type != "application/pdf":
        raise ValueError(
            f"Document {document_id} is not a PDF (file_type: {doc.file_type}). "
            "Page imaging is only supported for PDF documents."
        )

    if not doc.pdf_file:
        raise ValueError(f"Document {document_id} has no PDF file attached.")

    # Validate page number
    if page_number < 1:
        raise ValueError(f"Invalid page number {page_number}. Page numbers start at 1.")

    if doc.page_count and page_number > doc.page_count:
        raise ValueError(
            f"Page number {page_number} exceeds document page count ({doc.page_count})."
        )

    # Validate image format
    valid_formats = {"jpeg", "png"}
    image_format = image_format.lower()
    if image_format not in valid_formats:
        raise ValueError(
            f"Unsupported image format '{image_format}'. Must be one of: {valid_formats}"
        )

    try:
        # Read PDF file
        with doc.pdf_file.open("rb") as pdf_file:
            pdf_bytes = pdf_file.read()

        # Convert the specified page to an image
        images = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            first_page=page_number,
            last_page=page_number,
            fmt=image_format,
        )

        if not images:
            raise ValueError(
                f"Failed to render page {page_number} of document {document_id}"
            )

        # Get the first (and only) image
        page_image = images[0]

        # Convert to bytes
        image_io = io.BytesIO()
        # Use uppercase format name for PIL
        pil_format = "JPEG" if image_format == "jpeg" else "PNG"
        page_image.save(image_io, format=pil_format)
        image_io.seek(0)

        # Encode to base64
        image_bytes = image_io.getvalue()
        base64_encoded = base64.b64encode(image_bytes).decode("utf-8")

        logger.info(
            f"Successfully rendered page {page_number} of document {document_id} "
            f"(format: {image_format}, dpi: {dpi}, size: {len(base64_encoded)} chars)"
        )

        return base64_encoded

    except Exception as e:
        logger.error(
            f"Error rendering page {page_number} of document {document_id}: {e}"
        )
        raise ValueError(
            f"Failed to render page {page_number} of document {document_id}: {str(e)}"
        )


async def aget_page_image(
    document_id: int,
    page_number: int,
    image_format: str = "jpeg",
    dpi: int = 150,
) -> str:
    """Async wrapper around :func:`get_page_image`."""
    return await _db_sync_to_async(get_page_image)(
        document_id=document_id,
        page_number=page_number,
        image_format=image_format,
        dpi=dpi,
    )


def create_markdown_link(
    entity_type: str,
    entity_id: int,
) -> str:
    """
    Create a markdown link for a given entity (annotation, corpus, document, or conversation/thread).

    This tool generates markdown-formatted links following OpenContracts URL routing patterns.
    The generated links can be used in notes, summaries, or agent responses to reference
    specific entities within the system.

    Args:
        entity_type: Type of entity - one of: "annotation", "corpus", "document", "conversation"
        entity_id: The primary key (ID) of the entity

    Returns:
        A markdown-formatted link string: [Entity Title](URL)

        Examples:
            - Annotation: [Annotation 123](/d/john/my-corpus/my-doc?ann=123)
            - Corpus: [Legal Contracts](/c/john-doe/legal-contracts)
            - Document: [Contract.pdf](/d/john-doe/my-corpus/contract-pdf)
            - Conversation: [Discussion about X](/c/john/corpus/discussions/thread-123)

    Raises:
        ValueError: If entity_type is invalid, entity doesn't exist, or required slugs are missing

    Note:
        - Documents can be standalone or belong to a corpus (link includes corpus if available)
        - Annotations always include their parent document context in the link
        - Conversations/threads must be associated with a corpus for proper URL generation
        - All URLs use slugs for human-readable links (e.g., /c/john/my-corpus)
    """
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.conversations.models import Conversation
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    # Validate entity_type
    valid_types = {"annotation", "corpus", "document", "conversation"}
    if entity_type not in valid_types:
        raise ValueError(
            f"Invalid entity_type '{entity_type}'. Must be one of: {valid_types}"
        )

    try:
        if entity_type == "annotation":
            # Annotation link: /d/{userSlug}/{corpusSlug}/{docSlug}?ann={annotationId}
            # or /d/{userSlug}/{docSlug}?ann={annotationId} for standalone docs
            annotation = Annotation.objects.select_related(
                "document", "document__creator", "corpus", "corpus__creator"
            ).get(pk=entity_id)

            if not annotation.document:
                raise ValueError(
                    f"Annotation {entity_id} has no associated document and cannot be linked."
                )

            doc = annotation.document
            corpus = annotation.corpus

            # Get user slug from document creator
            if not doc.creator or not doc.creator.username:
                raise ValueError(
                    f"Document {doc.id} has no creator and cannot generate a link."
                )
            user_slug = doc.creator.username

            # Build document path
            if corpus and corpus.slug:
                # Document within corpus: /d/{userSlug}/{corpusSlug}/{docSlug}?ann={annotationId}
                if not doc.slug:
                    raise ValueError(
                        f"Document {doc.id} has no slug and cannot generate a link."
                    )
                url = f"/d/{user_slug}/{corpus.slug}/{doc.slug}?ann={entity_id}"
            else:
                # Standalone document: /d/{userSlug}/{docSlug}?ann={annotationId}
                if not doc.slug:
                    raise ValueError(
                        f"Document {doc.id} has no slug and cannot generate a link."
                    )
                url = f"/d/{user_slug}/{doc.slug}?ann={entity_id}"

            # Create title from annotation's raw_text or generic label
            title = (
                annotation.raw_text
                if annotation.raw_text
                else f"Annotation {entity_id}"
            )
            title = truncate(title, MAX_LINK_TITLE_LENGTH, suffix="...")

            return f"[{title}]({url})"

        elif entity_type == "corpus":
            # Corpus link: /c/{userSlug}/{corpusSlug}
            corpus = Corpus.objects.select_related("creator").get(pk=entity_id)

            if not corpus.creator or not corpus.creator.username:
                raise ValueError(
                    f"Corpus {entity_id} has no creator and cannot generate a link."
                )
            if not corpus.slug:
                raise ValueError(
                    f"Corpus {entity_id} has no slug and cannot generate a link."
                )

            user_slug = corpus.creator.username
            url = f"/c/{user_slug}/{corpus.slug}"
            title = corpus.title if corpus.title else f"Corpus {entity_id}"

            return f"[{title}]({url})"

        elif entity_type == "document":
            # Document link: /d/{userSlug}/{corpusSlug}/{docSlug} (if in corpus)
            # or /d/{userSlug}/{docSlug} (standalone)
            doc = Document.objects.select_related("creator").get(pk=entity_id)

            if not doc.creator or not doc.creator.username:
                raise ValueError(
                    f"Document {entity_id} has no creator and cannot generate a link."
                )
            if not doc.slug:
                raise ValueError(
                    f"Document {entity_id} has no slug and cannot generate a link."
                )

            user_slug = doc.creator.username

            # Check if document belongs to a corpus (via annotations)
            # Documents don't have direct corpus FK, but annotations do
            corpus = None
            first_annotation = (
                Annotation.objects.filter(document=doc)
                .exclude(corpus__isnull=True)
                .select_related("corpus")
                .first()
            )
            if first_annotation and first_annotation.corpus:
                corpus = first_annotation.corpus

            if corpus and corpus.slug:
                url = f"/d/{user_slug}/{corpus.slug}/{doc.slug}"
            else:
                url = f"/d/{user_slug}/{doc.slug}"

            title = doc.title if doc.title else f"Document {entity_id}"

            return f"[{title}]({url})"

        elif entity_type == "conversation":
            # Conversation/thread link: /c/{userSlug}/{corpusSlug}/discussions/{conversationId}
            conversation = Conversation.objects.select_related(
                "chat_with_corpus", "chat_with_corpus__creator"
            ).get(pk=entity_id)

            # Conversations require a corpus context for URL generation
            if not conversation.chat_with_corpus:
                raise ValueError(
                    f"Conversation {entity_id} has no associated corpus and cannot generate a discussion link. "
                    "Only corpus-scoped conversations can be linked."
                )

            corpus = conversation.chat_with_corpus
            if not corpus.creator or not corpus.creator.username:
                raise ValueError(
                    f"Corpus {corpus.id} has no creator and cannot generate a link."
                )
            if not corpus.slug:
                raise ValueError(
                    f"Corpus {corpus.id} has no slug and cannot generate a link."
                )

            user_slug = corpus.creator.username
            url = f"/c/{user_slug}/{corpus.slug}/discussions/{entity_id}"
            title = (
                conversation.title if conversation.title else f"Discussion {entity_id}"
            )

            return f"[{title}]({url})"

    except Annotation.DoesNotExist:
        raise ValueError(f"Annotation with id={entity_id} does not exist.")
    except Corpus.DoesNotExist:
        raise ValueError(f"Corpus with id={entity_id} does not exist.")
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={entity_id} does not exist.")
    except Conversation.DoesNotExist:
        raise ValueError(f"Conversation with id={entity_id} does not exist.")


async def acreate_markdown_link(
    entity_type: str,
    entity_id: int,
) -> str:
    """
    Async version: Create a markdown link for a given entity.

    See :func:`create_markdown_link` for detailed documentation.

    Args:
        entity_type: Type of entity - one of: "annotation", "corpus", "document", "conversation"
        entity_id: The primary key (ID) of the entity

    Returns:
        A markdown-formatted link string: [Entity Title](URL)

    Raises:
        ValueError: If entity_type is invalid, entity doesn't exist, or required slugs are missing
    """
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.conversations.models import Conversation
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    # Validate entity_type
    valid_types = {"annotation", "corpus", "document", "conversation"}
    if entity_type not in valid_types:
        raise ValueError(
            f"Invalid entity_type '{entity_type}'. Must be one of: {valid_types}"
        )

    try:
        if entity_type == "annotation":
            annotation = await Annotation.objects.select_related(
                "document", "document__creator", "corpus", "corpus__creator"
            ).aget(pk=entity_id)

            if not annotation.document:
                raise ValueError(
                    f"Annotation {entity_id} has no associated document and cannot be linked."
                )

            doc = annotation.document
            corpus = annotation.corpus

            if not doc.creator or not doc.creator.username:
                raise ValueError(
                    f"Document {doc.id} has no creator and cannot generate a link."
                )
            user_slug = doc.creator.username

            if corpus and corpus.slug:
                if not doc.slug:
                    raise ValueError(
                        f"Document {doc.id} has no slug and cannot generate a link."
                    )
                url = f"/d/{user_slug}/{corpus.slug}/{doc.slug}?ann={entity_id}"
            else:
                if not doc.slug:
                    raise ValueError(
                        f"Document {doc.id} has no slug and cannot generate a link."
                    )
                url = f"/d/{user_slug}/{doc.slug}?ann={entity_id}"

            title = (
                annotation.raw_text
                if annotation.raw_text
                else f"Annotation {entity_id}"
            )
            title = truncate(title, MAX_LINK_TITLE_LENGTH, suffix="...")

            return f"[{title}]({url})"

        elif entity_type == "corpus":
            corpus = await Corpus.objects.select_related("creator").aget(pk=entity_id)

            if not corpus.creator or not corpus.creator.username:
                raise ValueError(
                    f"Corpus {entity_id} has no creator and cannot generate a link."
                )
            if not corpus.slug:
                raise ValueError(
                    f"Corpus {entity_id} has no slug and cannot generate a link."
                )

            user_slug = corpus.creator.username
            url = f"/c/{user_slug}/{corpus.slug}"
            title = corpus.title if corpus.title else f"Corpus {entity_id}"

            return f"[{title}]({url})"

        elif entity_type == "document":
            doc = await Document.objects.select_related("creator").aget(pk=entity_id)

            if not doc.creator or not doc.creator.username:
                raise ValueError(
                    f"Document {entity_id} has no creator and cannot generate a link."
                )
            if not doc.slug:
                raise ValueError(
                    f"Document {entity_id} has no slug and cannot generate a link."
                )

            user_slug = doc.creator.username

            corpus = None
            first_annotation = await (
                Annotation.objects.filter(document=doc)
                .exclude(corpus__isnull=True)
                .select_related("corpus")
                .afirst()
            )
            if first_annotation and first_annotation.corpus:
                corpus = first_annotation.corpus

            if corpus and corpus.slug:
                url = f"/d/{user_slug}/{corpus.slug}/{doc.slug}"
            else:
                url = f"/d/{user_slug}/{doc.slug}"

            title = doc.title if doc.title else f"Document {entity_id}"

            return f"[{title}]({url})"

        elif entity_type == "conversation":
            conversation = await Conversation.objects.select_related(
                "chat_with_corpus", "chat_with_corpus__creator"
            ).aget(pk=entity_id)

            if not conversation.chat_with_corpus:
                raise ValueError(
                    f"Conversation {entity_id} has no associated corpus and cannot generate a discussion link. "
                    "Only corpus-scoped conversations can be linked."
                )

            corpus = conversation.chat_with_corpus
            if not corpus.creator or not corpus.creator.username:
                raise ValueError(
                    f"Corpus {corpus.id} has no creator and cannot generate a link."
                )
            if not corpus.slug:
                raise ValueError(
                    f"Corpus {corpus.id} has no slug and cannot generate a link."
                )

            user_slug = corpus.creator.username
            url = f"/c/{user_slug}/{corpus.slug}/discussions/{entity_id}"
            title = (
                conversation.title if conversation.title else f"Discussion {entity_id}"
            )

            return f"[{title}]({url})"

    except Annotation.DoesNotExist:
        raise ValueError(f"Annotation with id={entity_id} does not exist.")
    except Corpus.DoesNotExist:
        raise ValueError(f"Corpus with id={entity_id} does not exist.")
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={entity_id} does not exist.")
    except Conversation.DoesNotExist:
        raise ValueError(f"Conversation with id={entity_id} does not exist.")
