"""Tools for loading slices of a document's plain-text extract."""

import logging
from datetime import datetime  # noqa: F401  (used in type comment below)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Plain-text extract helpers                                                  #
# --------------------------------------------------------------------------- #

# Cache stores a tuple of (last_modified timestamp, file contents) so we can
# transparently invalidate entries when the underlying file changes.
_DOC_TXT_CACHE: dict[int, tuple["datetime", str]] = {}


def get_cached_txt_extract_length(document_id: int) -> int:
    """Return the character length of a document's cached text extract.

    Returns ``0`` when the document has not been cached yet (e.g. no
    ``aload_document_txt_extract`` call has populated it). Callers in
    other modules use this in place of poking ``_DOC_TXT_CACHE`` directly
    so the cache's storage shape can evolve (e.g. move to Redis or wrap
    in an async-safe structure) without rippling across the codebase.

    Note: a return value of ``0`` is ambiguous between "never cached"
    and "cached but the document's text-extract is empty". Use
    :func:`is_txt_extract_cached` when that distinction matters.
    """
    cached = _DOC_TXT_CACHE.get(document_id)
    return len(cached[1]) if cached else 0


def is_txt_extract_cached(document_id: int) -> bool:
    """Return ``True`` iff the document's text extract is in the cache.

    Distinguishes a genuinely empty document (cached as ``""``) from
    one that has never been loaded. Callers that key off ``length == 0``
    to decide whether to populate the cache must use this predicate
    instead, otherwise a 0-byte document triggers a redundant
    re-population on every call.
    """
    return document_id in _DOC_TXT_CACHE


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
        content_bytes = doc.txt_extract_file.read()
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
        content_str = doc.txt_extract_file.read().decode("utf-8")
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
