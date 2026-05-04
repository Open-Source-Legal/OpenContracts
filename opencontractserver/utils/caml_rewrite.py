"""
CAML (corpus markdown / README) reference rewriting for bulk imports.

Bulk-import zips can include a corpus README that references documents and
annotations bundled in the same zip.  Authors of the zip do not know the
final OpenContracts primary keys or slugs, so they reference resources by
identifiers that are stable inside the zip:

    [label](oc-import://document/<path-as-it-appears-in-the-zip>)
    [label](oc-import://annotation/<id-as-it-appears-in-data.json>)

After import, those placeholder URLs are rewritten to live, slug-based URLs
that the existing mention parser (``utils/mention_parser.py``) understands:

    [label](/d/<user-slug>/<corpus-slug>/<doc-slug>)
    [label](/d/<user-slug>/<corpus-slug>/<doc-slug>?ann=<new-pk>)

Unresolved references (e.g., a filename not present in the zip, an annotation
old-id with no entry in the import map) are left as-is and a warning is
logged.  We deliberately do not strip them so authors can fix the source and
re-import.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from opencontractserver.annotations.models import Annotation

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)

OC_IMPORT_SCHEME = "oc-import"
_DOCUMENT_PREFIX = f"{OC_IMPORT_SCHEME}://document/"
_ANNOTATION_PREFIX = f"{OC_IMPORT_SCHEME}://annotation/"

# Markdown link pattern: [text](url) — captures text and url separately.
# Matches the pattern used by utils/mention_parser.py for consistency.
_LINK_PATTERN = re.compile(r"(\[[^\]]+\])\(([^)]+)\)")


def _doc_url(user_slug: str, corpus_slug: str, doc_slug: str) -> str:
    return f"/d/{user_slug}/{corpus_slug}/{doc_slug}"


def rewrite_oc_import_links(
    content: str,
    corpus: Corpus,
    doc_filename_to_doc: dict[str, Document],
    annot_old_id_to_new_pk: dict[str | int, int],
) -> tuple[str, dict[str, int]]:
    """
    Rewrite ``oc-import://`` placeholder URLs in markdown to live URLs.

    Args:
        content: The raw markdown content of the README.
        corpus: The newly-created Corpus (used for its slug + creator slug).
        doc_filename_to_doc: Mapping of zip filename (the keys of
            ``data.json["annotated_docs"]``) to the corpus-isolated Document
            instance created during import.
        annot_old_id_to_new_pk: Mapping of old annotation id (as it appears
            in the export's ``"id"`` field — string or int) to the newly
            created Annotation primary key.  This is the same map the
            importer aggregates as ``all_annot_id_maps``.

    Returns:
        Tuple of ``(rewritten_content, stats)`` where ``stats`` reports counts
        of resolved / unresolved references for logging and tests::

            {
                "documents_resolved": int,
                "documents_unresolved": int,
                "annotations_resolved": int,
                "annotations_unresolved": int,
            }

    The function never raises on a bad reference; it leaves it intact and
    increments the corresponding ``unresolved`` counter.
    """
    if not content:
        return content, {
            "documents_resolved": 0,
            "documents_unresolved": 0,
            "annotations_resolved": 0,
            "annotations_unresolved": 0,
        }

    user_slug = getattr(getattr(corpus, "creator", None), "slug", None) or ""
    corpus_slug = corpus.slug or ""

    if not user_slug or not corpus_slug:
        logger.warning(
            "CAML rewrite: missing user_slug or corpus_slug "
            "(user_slug=%r, corpus_slug=%r); rewritten URLs will be malformed.",
            user_slug,
            corpus_slug,
        )

    # Normalize annotation map to string keys — the export always emits
    # ``"id": f"{annot.id}"`` as a string, but we accept int too.
    annot_str_map: dict[str, int] = {
        str(k): int(v) for k, v in annot_old_id_to_new_pk.items()
    }

    # Pre-fetch every annotation that any reference might resolve to so we
    # don't issue one query per regex match inside ``_replace``.  Only
    # ``document.slug`` is read off the joined row, so a single ``document``
    # join is sufficient.
    referenced_pks = set(annot_str_map.values())
    annot_pk_to_obj: dict[int, Annotation] = (
        {
            a.pk: a
            for a in Annotation.objects.select_related("document").filter(
                pk__in=referenced_pks
            )
        }
        if referenced_pks
        else {}
    )

    # Build a quick filename lookup that tolerates leading "./" — authors
    # may write either of:
    #   oc-import://document/documents/foo.pdf
    #   oc-import://document/./documents/foo.pdf
    normalized_doc_map: dict[str, Document] = {}
    for fname, doc in doc_filename_to_doc.items():
        normalized_doc_map[fname] = doc
        if fname.startswith("./"):
            normalized_doc_map[fname[2:]] = doc

    stats = {
        "documents_resolved": 0,
        "documents_unresolved": 0,
        "annotations_resolved": 0,
        "annotations_unresolved": 0,
    }

    def _normalize_ref(ref: str) -> str:
        """Strip a single leading ``./`` so lookups are consistent.

        Nested forms like ``././foo.pdf`` are not collapsed — bulk-import
        zips have flat document paths and chained relative segments are not
        a real-world concern.
        """
        if ref.startswith("./"):
            ref = ref[2:]
        return ref

    def _replace(match: re.Match[str]) -> str:
        label = match.group(1)
        url = match.group(2)

        if url.startswith(_DOCUMENT_PREFIX):
            ref = _normalize_ref(url[len(_DOCUMENT_PREFIX) :])
            doc = normalized_doc_map.get(ref)
            if doc is None:
                stats["documents_unresolved"] += 1
                logger.warning(
                    "CAML rewrite: document reference '%s' did not match any "
                    "imported document filename; leaving link unchanged.",
                    ref,
                )
                return match.group(0)
            stats["documents_resolved"] += 1
            return f"{label}({_doc_url(user_slug, corpus_slug, doc.slug or '')})"

        if url.startswith(_ANNOTATION_PREFIX):
            old_id = url[len(_ANNOTATION_PREFIX) :].strip()
            new_pk = annot_str_map.get(old_id)
            if new_pk is None:
                stats["annotations_unresolved"] += 1
                logger.warning(
                    "CAML rewrite: annotation reference '%s' has no entry in "
                    "the import id map; leaving link unchanged.",
                    old_id,
                )
                return match.group(0)
            annot = annot_pk_to_obj.get(new_pk)
            if annot is None:
                stats["annotations_unresolved"] += 1
                logger.warning(
                    "CAML rewrite: annotation pk %s vanished between import "
                    "and rewrite; leaving link unchanged.",
                    new_pk,
                )
                return match.group(0)
            doc = annot.document
            doc_slug = (doc.slug or "") if doc is not None else ""
            if not doc_slug:
                logger.warning(
                    "CAML rewrite: annotation pk %s has no document slug "
                    "(document=%r); rewritten URL will be malformed.",
                    new_pk,
                    getattr(doc, "pk", None),
                )
            stats["annotations_resolved"] += 1
            return (
                f"{label}({_doc_url(user_slug, corpus_slug, doc_slug)}"
                f"?ann={new_pk})"
            )

        return match.group(0)

    rewritten = _LINK_PATTERN.sub(_replace, content)

    logger.info(
        "CAML rewrite: %d document refs resolved (%d unresolved), "
        "%d annotation refs resolved (%d unresolved).",
        stats["documents_resolved"],
        stats["documents_unresolved"],
        stats["annotations_resolved"],
        stats["annotations_unresolved"],
    )
    return rewritten, stats
