"""Resolve extracted reference candidates to concrete targets in a corpus.

The resolver is fed the corpus's documents (already permission-scoped by the
caller via ``CorpusDocumentService``) so it performs no Tier-0 permission
fusions itself. It maps:

* law citations            -> EXTERNAL (no internal target; canonical stub only)
* document/exhibit refs    -> a target Document (by exhibit number in its title)
* identifier citations     -> a target Document (by identifier-shaped title,
                              e.g. CBP ruling numbers; extension-stripped)
* internal section refs    -> an OC_SECTION annotation, or a heading-text offset
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import Candidate

# Exhibit number as it appears in EDGAR document titles, e.g.
# "Cerebras Systems Inc. S-1 (2024-09-30) - Exhibit 10.12(A): EX-10.12(A)".
_TITLE_EXHIBIT_RE = re.compile(r"Exhibit\s+(?P<num>\d+\.\d+[A-Za-z()]*)", re.IGNORECASE)


@dataclass
class Resolution:
    """A candidate paired with its resolved target (if any)."""

    candidate: Candidate
    source_document_id: int
    resolution_status: str
    target_document_id: int | None = None
    target_annotation_id: int | None = None
    target_offset: int | None = None
    canonical_key: str | None = None
    confidence: float = 1.0
    normalized_data: dict = field(default_factory=dict)

    @property
    def reference_type(self) -> str:
        return self.candidate.reference_type


@dataclass
class SectionAnno:
    """Minimal view of an OC_SECTION annotation for matching."""

    id: int
    raw_text: str


class ReferenceResolver:
    """Resolve candidates against a fixed set of corpus documents."""

    def __init__(self, documents) -> None:
        # Build {exhibit_number -> document_id} from document titles.
        self._exhibit_index: dict[str, int] = {}
        # {canonical identifier -> document_id} for identifier-shaped titles
        # (CBP CROSS-style "title IS the ruling number" corpora). Titles are
        # canonicalized via document_identifier_from_title — extension-stripped
        # and uppercased — because the citation grammar only ever extracts the
        # bare identifier while ingested titles often keep their materialized
        # filename extension ("A83482.doc"); indexing the raw title would make
        # every citation into such documents silently unresolvable.
        self._identifier_index: dict[str, int] = {}
        # Reverse view — {document_id -> its own canonical identifier} — used
        # by the self-mention drop. Kept separate from _identifier_index
        # (which setdefaults first-writer-wins) so a corpus holding duplicate
        # identifier titles (the same ruling re-ingested as .doc and .pdf)
        # still drops EVERY duplicate's self-identifying header mention, not
        # just the one that happened to claim the index slot.
        self._doc_identifiers: dict[int, str] = {}
        for doc in documents:
            for m in _TITLE_EXHIBIT_RE.finditer(doc.title or ""):
                self._exhibit_index.setdefault(m.group("num").lower(), doc.id)
            ident = C.document_identifier_from_title(doc.title)
            if C.DOC_IDENTIFIER_RE.fullmatch(ident):
                self._identifier_index.setdefault(ident, doc.id)
                self._doc_identifiers[doc.id] = ident

    # -- per-type ---------------------------------------------------------- #

    def resolve_law(self, cand: Candidate) -> Resolution:
        return Resolution(
            candidate=cand,
            source_document_id=0,  # filled by caller via _stamp_source
            resolution_status=C.STATUS_EXTERNAL,
            canonical_key=cand.canonical_key,
            normalized_data=dict(cand.normalized_data),
        )

    def resolve_document(
        self, cand: Candidate, source_doc_id: int
    ) -> Resolution | None:
        ident = cand.normalized_data.get(C.KEY_DOCUMENT_IDENTIFIER)
        if ident is not None:
            return self._resolve_document_identifier(cand, source_doc_id, ident)
        num = (cand.normalized_data.get("exhibit_number") or "").lower()
        target = self._exhibit_index.get(num)
        if target is not None and target != source_doc_id:
            status = C.STATUS_RESOLVED
        else:
            target = None
            status = C.STATUS_UNRESOLVED
        return Resolution(
            candidate=cand,
            source_document_id=source_doc_id,
            resolution_status=status,
            target_document_id=target,
            canonical_key=cand.canonical_key,
            normalized_data=dict(cand.normalized_data),
        )

    def _resolve_document_identifier(
        self, cand: Candidate, source_doc_id: int, ident: str
    ) -> Resolution | None:
        """Title-identifier citation (e.g. a CBP ruling number) -> sibling doc.

        Returns ``None`` for a SELF-mention — CROSS-style documents state
        their own identifier in headers/footers, so persisting those spans
        would put a systematic self-reference row on every document. The
        check is against the SOURCE document's own title identifier (not
        "target == source"), so a duplicate-titled sibling (the same ruling
        ingested twice) can never turn one copy's header into a resolved
        citation pointing at the other copy. The drop is deliberately
        DOCUMENT-WIDE, not header-scoped: there is no positional signal
        separating a header restatement from a body self-cite, and a
        self-citation resolves to a self-loop edge the reference graph has
        no use for — dropping every own-identifier span trades that (rare,
        informationless) edge for never persisting header/footer noise.
        Citations to identifiers absent from the corpus persist UNRESOLVED
        (the mention is real; the writer's forward-only heal upgrades the row
        when the sibling is ingested later and enrichment re-applies).
        """
        if self._doc_identifiers.get(source_doc_id) == ident:
            return None
        target = self._identifier_index.get(ident)
        return Resolution(
            candidate=cand,
            source_document_id=source_doc_id,
            resolution_status=(
                C.STATUS_RESOLVED if target is not None else C.STATUS_UNRESOLVED
            ),
            target_document_id=target,
            canonical_key=cand.canonical_key,
            normalized_data=dict(cand.normalized_data),
        )

    def resolve_section(
        self,
        cand: Candidate,
        source_doc_id: int,
        doc_text: str,
        sections: list[SectionAnno] | None = None,
    ) -> Resolution:
        heading = (cand.normalized_data.get("heading") or "").strip()
        res = Resolution(
            candidate=cand,
            source_document_id=source_doc_id,
            resolution_status=C.STATUS_UNRESOLVED,
            normalized_data=dict(cand.normalized_data),
        )
        # 1. Prefer an OC_SECTION annotation whose text matches the heading.
        for sec in sections or []:
            if (sec.raw_text or "").strip().lower() == heading.lower():
                res.target_annotation_id = sec.id
                res.resolution_status = C.STATUS_RESOLVED
                return res
        # 2. Fallback: locate the heading text within the document.
        if heading:
            idx = doc_text.lower().find(heading.lower(), cand.end)
            if idx == -1:
                # Backward reference (e.g. "as defined in 'Heading' above"):
                # match the nearest *preceding* occurrence, not the first in
                # the document — a duplicate heading in an earlier exhibit
                # would otherwise mis-resolve to an unrelated section.
                idx = doc_text.lower().rfind(heading.lower(), 0, cand.start)
            if idx != -1:
                res.target_offset = idx
                res.resolution_status = C.STATUS_RESOLVED
                res.confidence = 0.6  # heading-text match, not a real section anno
        return res

    # -- dispatcher -------------------------------------------------------- #

    def resolve(
        self,
        cand: Candidate,
        source_doc_id: int,
        doc_text: str,
        sections: list[SectionAnno] | None = None,
    ) -> Resolution | None:
        """Resolve one candidate; ``None`` means "do not persist this span"
        (today: a document's self-identifying header mention — see
        :meth:`_resolve_document_identifier`)."""
        if cand.reference_type == C.REF_LAW:
            res = self.resolve_law(cand)
            res.source_document_id = source_doc_id
            return res
        if cand.reference_type == C.REF_DOCUMENT:
            return self.resolve_document(cand, source_doc_id)
        if cand.reference_type == C.REF_SECTION:
            return self.resolve_section(cand, source_doc_id, doc_text, sections)
        if cand.reference_type == C.REF_DEFINED_TERM:
            # A definition site is self-contained: the mention IS the canonical
            # target for ``term:<slug>``. Usage->definition linking is a future
            # increment (volume/precision control needed for terms like "Company").
            return Resolution(
                candidate=cand,
                source_document_id=source_doc_id,
                resolution_status=C.STATUS_RESOLVED,
                canonical_key=cand.canonical_key,
                normalized_data=dict(cand.normalized_data),
            )
        # Any future types: carry through unresolved.
        return Resolution(
            candidate=cand,
            source_document_id=source_doc_id,
            resolution_status=C.STATUS_UNRESOLVED,
            canonical_key=cand.canonical_key,
            normalized_data=dict(cand.normalized_data),
        )
