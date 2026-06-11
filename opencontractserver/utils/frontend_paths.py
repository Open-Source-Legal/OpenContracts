"""Canonical site-relative frontend paths for backend-written links.

The frontend serves slug-shaped routes only (``frontend/src/App.tsx``):
``/d/:userIdent/:corpusIdent/:docIdent`` for a document in a corpus, with the
first segment being the CORPUS creator's slug (mirrors the frontend's
``buildCanonicalPath`` in ``navigationUtils.ts`` — corpus slugs are unique per
creator and the document slug resolves within that corpus). Any other shape
falls through to the ``*`` catch-all and renders the 404 page, so backend
writers must emit this canonical form.
"""

from __future__ import annotations


def document_in_corpus_path(
    *,
    corpus_creator_slug: str | None,
    corpus_slug: str | None,
    document_slug: str | None,
) -> str | None:
    """Return ``/d/{corpus_creator_slug}/{corpus_slug}/{document_slug}``.

    Returns ``None`` when any slug is missing — callers should skip the link
    rather than write a path that 404s.
    """
    if not (corpus_creator_slug and corpus_slug and document_slug):
        return None
    return f"/d/{corpus_creator_slug}/{corpus_slug}/{document_slug}"
