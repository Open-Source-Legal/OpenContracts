"""Canonical site-relative frontend paths for backend-written links.

The frontend serves slug-shaped routes only (``frontend/src/App.tsx``):
``/d/:userIdent/:corpusIdent/:docIdent`` for a document in a corpus, with the
first segment being the CORPUS creator's slug (mirrors the frontend's
``buildCanonicalPath`` in ``navigationUtils.ts`` — corpus slugs are unique per
creator and the document slug resolves within that corpus). Any other shape
falls through to the ``*`` catch-all and renders the 404 page, so backend
writers must emit this canonical form.

A link may pin a specific document version with ``?v=N`` (``N`` is the
``DocumentPath.version_number`` of the target in that corpus). The route
manager already threads ``?v=`` into ``documentInCorpusBySlugs(versionNumber:)``,
whose resolver drops its ``is_current`` constraint when a version is given —
so a pinned link keeps resolving after the target is superseded, whereas a
bare slug link 404s once its version is no longer current (slugs are minted
per version). Backend writers that link to a *resolved* target should
therefore always pin: see ``docs/architecture/reference-web-versioning.md``.
"""

from __future__ import annotations

from urllib.parse import urlencode

DOCUMENT_VERSION_QUERY_PARAM = "v"


def document_in_corpus_path(
    *,
    corpus_creator_slug: str | None,
    corpus_slug: str | None,
    document_slug: str | None,
    version_number: int | None = None,
) -> str | None:
    """Return ``/d/{corpus_creator_slug}/{corpus_slug}/{document_slug}[?v=N]``.

    Returns ``None`` when any slug is missing — callers should skip the link
    rather than write a path that 404s. ``version_number`` is appended as
    ``?v=N`` when it is a positive integer and ignored otherwise.
    """
    if not (corpus_creator_slug and corpus_slug and document_slug):
        return None
    path = f"/d/{corpus_creator_slug}/{corpus_slug}/{document_slug}"
    if isinstance(version_number, int) and version_number > 0:
        path += "?" + urlencode({DOCUMENT_VERSION_QUERY_PARAM: version_number})
    return path
