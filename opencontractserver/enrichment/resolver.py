"""Resolve extracted reference candidates to concrete targets in a corpus.

The resolver is fed the corpus's documents (already permission-scoped by the
caller via ``CorpusDocumentService``) so it performs no Tier-0 permission
fusions itself. It maps:

* law citations            -> EXTERNAL (no internal target; canonical stub only)
* document/exhibit refs    -> a target Document (by exhibit number in its title)
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
        for doc in documents:
            for m in _TITLE_EXHIBIT_RE.finditer(doc.title or ""):
                self._exhibit_index.setdefault(m.group("num").lower(), doc.id)

    # -- per-type ---------------------------------------------------------- #

    def resolve_law(self, cand: Candidate) -> Resolution:
        return Resolution(
            candidate=cand,
            source_document_id=0,  # filled by caller via _stamp_source
            resolution_status=C.STATUS_EXTERNAL,
            canonical_key=cand.canonical_key,
            normalized_data=dict(cand.normalized_data),
        )

    def resolve_document(self, cand: Candidate, source_doc_id: int) -> Resolution:
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
    ) -> Resolution:
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
