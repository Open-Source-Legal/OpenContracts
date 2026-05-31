"""Tools for reading or updating ``Corpus`` and ``Document`` descriptions."""

from typing import Any

from opencontractserver.constants.truncation import (
    MAX_DESCRIPTION_RESPONSE_PREVIEW_LENGTH,
)
from opencontractserver.corpuses.models import Corpus
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

    Reads the corpus's canonical ``Readme.CAML`` Document body via the
    service layer (``CorpusDocumentService.get_corpus_caml_articles``)
    rather than the legacy ``Corpus.md_description`` FileField. Returns
    ``""`` when the corpus has no CAML article yet.

    Parameters
    ----------
    corpus_id: int
        Primary key of the `Corpus`.
    truncate_length: int | None, optional
        If provided, returns at most this many characters. Positive values only.
    from_start: bool
        If ``True`` truncates from the beginning; otherwise from the end.
    """
    from opencontractserver.corpuses.services.corpus_documents import (
        CorpusDocumentService,
    )
    from opencontractserver.corpuses.services.description_cache import (
        read_caml_body,
    )

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus with id={corpus_id} does not exist.") from exc

    # NOTE (accepted risk): the CAML lookup is performed as ``corpus.creator``
    # rather than the calling agent's user. This tool takes only ``corpus_id``
    # (no user is injected by the agent framework today), and an agent is only
    # ever built for a corpus its owning user can already reach — so the
    # description (a corpus-level README, not per-document data) is effectively
    # gated upstream. Threading the live caller through here for defence-in-depth
    # would require a tool-signature + injection change and is tracked as a
    # follow-up rather than done inline.  TODO(#1848): thread the invoking user
    # through ``get_corpus_description`` once the agent framework injects it,
    # and drop the ``corpus.creator`` fallback.
    #
    # Defensive: ``corpus.creator`` can be NULL if the creating user was hard-
    # deleted/deactivated. Without a creator there is no identity to scope the
    # CAML lookup to, so treat it as "no readable description" rather than
    # letting a ``None`` user reach ``get_corpus_caml_articles``.
    if corpus.creator is None:
        return ""
    caml_doc = CorpusDocumentService.get_corpus_caml_articles(
        corpus.creator, corpus
    ).first()
    if caml_doc is None:
        return ""

    content = read_caml_body(caml_doc)

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
    """Async variant of :func:`get_corpus_description`.

    Delegates to the synchronous implementation via ``_db_sync_to_async``
    so the CAML read path (queryset + file I/O) runs in a worker thread
    with its own DB connection. The CAML lookup uses
    ``CorpusDocumentService.get_corpus_caml_articles`` whose ``user_can``
    check is sync-only, so wrapping the whole helper is simpler than
    threading an async equivalent.
    """
    return await _db_sync_to_async(get_corpus_description)(
        corpus_id=corpus_id,
        truncate_length=truncate_length,
        from_start=from_start,
    )


def update_corpus_description(
    *,
    corpus_id: int,
    new_content: str | None = None,
    diff_text: str | None = None,
    author_id: int | None = None,
    author=None,
) -> Document | None:
    """Patch or replace a corpus markdown description.

    Provide either *new_content* or an ``ndiff`` *diff_text* that will be
    applied to the current ``Readme.CAML`` body before writing.

    Routes through :meth:`CorpusService.update_description`, which uses
    :func:`opencontractserver.documents.versioning.import_document` to
    create a new version-tree sibling of the corpus's ``Readme.CAML``
    Document (Task 8 of the canonical-CAML refactor). Permission gating
    happens inside the service.

    Returns the new head :class:`Document` when the content changed, or
    ``None`` when ``new_content`` is byte-identical to the current CAML
    body (no new version created). Raises ``ValueError`` on bad input
    or when the service returns a permission/lookup failure.
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.corpuses.services.corpus_service import (
        CorpusService,
    )

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
        # Derive the "current" body from the canonical CAML read path so
        # the ndiff patch is applied to exactly what ``CorpusService``
        # would observe before writing.
        current = get_corpus_description(corpus_id)
        new_content = _apply_ndiff_patch(current, diff_text)

    if author is None:
        # Guarded above by the "both None" check, but use an explicit raise
        # rather than ``assert`` — assertions are stripped under ``python -O``
        # (production containers), which would silently pass ``None`` into
        # ``get(pk=None)`` and surface as a confusing DoesNotExist.
        if author_id is None:
            raise ValueError("Provide either author or author_id.")
        author = get_user_model().objects.get(pk=author_id)

    result = CorpusService.update_description(author, corpus, new_content or "")

    # ``CorpusService.update_description`` returns a
    # ``ServiceResult[Document | None]``. Surface permission/lookup
    # failures as ``ValueError`` so the tool's historical contract
    # (raise on failure, return ``Document | None`` on success) is
    # preserved.
    if not result.ok:
        raise ValueError(result.error)

    return result.value


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
