"""Tools that read, create, update, or search :class:`Note` objects."""

from typing import Any, Optional

from opencontractserver.annotations.models import Note, NoteRevision
from opencontractserver.constants.truncation import MAX_NOTE_CONTENT_PREVIEW_LENGTH
from opencontractserver.documents.models import Document
from opencontractserver.utils.text import truncate

from ._helpers import _apply_ndiff_patch, _db_sync_to_async, _token_count


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
) -> list[dict[str, str | int | None]]:

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
) -> list[dict[str, str | int | None]]:
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

    results: list[dict[str, str | int | None]] = []
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
