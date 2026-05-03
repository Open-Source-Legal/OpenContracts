"""Tools for reading, diffing, and updating document summary revisions."""

from typing import Any

from ._helpers import _db_sync_to_async


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

    # Use the model's update_summary method. The early guard above ensures at
    # least one of `author` / `author_id` is set, so the narrowed value is
    # never None here.
    summary_author = author if author is not None else author_id
    assert summary_author is not None
    revision = doc.update_summary(
        new_content=new_content, author=summary_author, corpus=corpus
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
