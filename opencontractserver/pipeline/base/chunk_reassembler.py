"""Incremental reassembly of per-chunk OpenContractDocExport results.

Accepts one chunk result at a time (``add_chunk``) so the chunked-parse Celery
callback can stream results from storage without holding them all in memory,
then produces a single merged document (``finalize``). The list-based
``_reassemble_chunk_results`` in ``chunked_parser`` delegates here.
"""

import logging
from typing import Any, Optional

from opencontractserver.annotations.compact_json import (
    is_span_format,
    iter_page_annotations,
    offset_annotation_json,
)
from opencontractserver.types.dicts import (
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
    PawlsPagePythonType,
)

logger = logging.getLogger(__name__)

# Decimal places used when folding annotation bounding boxes into a dedup
# signature. The same physical page parsed in two overlapping chunks yields
# bit-identical bounds, so this only guards against trivial float noise.
_BOUNDS_SIGNATURE_PRECISION = 2


def _annotation_signature(annotation: OpenContractsAnnotationPythonType) -> tuple:
    """Build a content signature identifying an annotation independent of chunk.

    Two copies of the same structure parsed in different (overlapping) chunks
    share a signature once their page indices have been offset into global
    space, which is what lets reassembly dedupe them and re-link references.

    The signature is derived from the annotation's label plus its global page
    geometry (page index, bounding box, token indices) — NOT its chunk-prefixed
    ``id`` — so it is stable across the ``c{idx}_`` prefixing applied per chunk.
    """
    label = annotation.get("annotationLabel")
    raw_text = annotation.get("rawText", "") or ""
    annotation_json: Any = annotation.get("annotation_json")

    # Span annotations (text documents) key on their character offsets.
    if is_span_format(annotation_json):
        return (
            "span",
            label,
            annotation_json.get("start"),
            annotation_json.get("end"),
            raw_text,
        )

    pages: list[tuple] = []
    for page in iter_page_annotations(annotation_json, raw_text=raw_text):
        b = page.bounds
        bounds_sig = (
            round(float(b.get("top", 0)), _BOUNDS_SIGNATURE_PRECISION),
            round(float(b.get("left", 0)), _BOUNDS_SIGNATURE_PRECISION),
            round(float(b.get("right", 0)), _BOUNDS_SIGNATURE_PRECISION),
            round(float(b.get("bottom", 0)), _BOUNDS_SIGNATURE_PRECISION),
        )
        pages.append((page.page_index, bounds_sig, tuple(sorted(page.token_indices))))
    pages.sort()
    return ("multipage", label, tuple(pages), raw_text)


def _relationship_signature(
    relationship: OpenContractsRelationshipPythonType,
) -> tuple:
    """Content signature for a relationship after its endpoint IDs are remapped.

    Keyed on the label plus the (order-independent) sets of source/target
    annotation IDs, so a relationship duplicated across an overlap zone collapses
    to one once both copies point at the same deduped global annotation IDs.
    """
    return (
        relationship.get("relationshipLabel"),
        frozenset(relationship.get("source_annotation_ids", [])),
        frozenset(relationship.get("target_annotation_ids", [])),
    )


def offset_annotation(
    annotation: OpenContractsAnnotationPythonType,
    page_offset: int,
    id_prefix: str,
) -> None:
    """Mutate *annotation* in place: offset pages and prefix IDs."""
    # Offset the primary page field
    annotation["page"] = annotation.get("page", 0) + page_offset

    # Prefix the annotation ID
    old_id = annotation.get("id")
    if old_id is not None:
        annotation["id"] = f"{id_prefix}{old_id}"

    # Prefix parent_id
    parent_id = annotation.get("parent_id")
    if parent_id is not None:
        annotation["parent_id"] = f"{id_prefix}{parent_id}"

    # Offset annotation_json page keys and token references
    annotation_json = annotation.get("annotation_json")
    if isinstance(annotation_json, dict):
        annotation["annotation_json"] = offset_annotation_json(
            annotation_json, page_offset
        )


def offset_relationship(
    relationship: OpenContractsRelationshipPythonType,
    id_prefix: str,
) -> None:
    """Mutate *relationship* in place: prefix all IDs."""
    old_id = relationship.get("id")
    if old_id is not None:
        relationship["id"] = f"{id_prefix}{old_id}"

    relationship["source_annotation_ids"] = [
        f"{id_prefix}{sid}" for sid in relationship.get("source_annotation_ids", [])
    ]
    relationship["target_annotation_ids"] = [
        f"{id_prefix}{tid}" for tid in relationship.get("target_annotation_ids", [])
    ]


class ChunkReassembler:
    """Stateful accumulator that merges per-chunk results one at a time."""

    def __init__(self) -> None:
        self._first: Optional[OpenContractDocExport] = None
        self._pawls: list[PawlsPagePythonType] = []
        self._annotations: list[OpenContractsAnnotationPythonType] = []
        self._relationships: list[OpenContractsRelationshipPythonType] = []
        self._content_parts: list[str] = []
        self._doc_labels: list[str] = []
        self._seen_doc_labels: set[str] = set()
        self._total_pages = 0

    def add_chunk(
        self,
        chunk: OpenContractDocExport,
        page_offset: int,
        chunk_index: int,
    ) -> None:
        if self._first is None:
            self._first = chunk
        prefix = f"c{chunk_index}_"

        # -- PAWLs pages --
        for page_data in chunk.get("pawls_file_content", []):
            page_info = page_data.get("page", {})
            page_info["index"] = page_info.get("index", 0) + page_offset
            self._pawls.append(page_data)

        # -- Text content --
        content = chunk.get("content", "")
        if content:
            self._content_parts.append(content)

        # -- Page count --
        self._total_pages += chunk.get("page_count", 0)

        # -- Document labels (deduplicated) --
        for label in chunk.get("doc_labels", []):
            if label not in self._seen_doc_labels:
                self._seen_doc_labels.add(label)
                self._doc_labels.append(label)

        # -- Annotations --
        for annotation in chunk.get("labelled_text", []):
            offset_annotation(annotation, page_offset, prefix)
            self._annotations.append(annotation)

        # -- Relationships --
        for relationship in chunk.get("relationships", []):
            offset_relationship(relationship, prefix)
            self._relationships.append(relationship)

    def finalize(self) -> OpenContractDocExport:
        if self._first is None:
            raise ValueError("Cannot finalize an empty ChunkReassembler")

        pawls = self._dedupe_pages()
        annotations, id_remap = self._dedupe_annotations()
        relationships = self._relink_and_dedupe_relationships(id_remap)

        # page_count is the number of unique global pages, not the sum of the
        # chunks' page counts (overlap makes the latter over-count). Fall back to
        # the summed count only if no PAWLs pages were emitted at all.
        page_count = len(pawls) if pawls else self._total_pages

        result: OpenContractDocExport = {
            "title": self._first.get("title", ""),
            "content": "\n".join(self._content_parts),
            "description": self._first.get("description"),
            "pawls_file_content": pawls,
            "page_count": page_count,
            "doc_labels": self._doc_labels,
            "labelled_text": annotations,
            "relationships": relationships,
        }

        self._report_residual_orphans(annotations, relationships)
        return result

    # ------------------------------------------------------------------
    # finalize() helpers — dedupe overlap + re-link cross-boundary refs
    # ------------------------------------------------------------------

    def _dedupe_pages(self) -> list[PawlsPagePythonType]:
        """Drop duplicate overlap pages (keep first per global index), ordered."""
        seen: set[int] = set()
        deduped: list[PawlsPagePythonType] = []
        for page_data in self._pawls:
            idx = page_data.get("page", {}).get("index", 0)
            if idx in seen:
                continue
            seen.add(idx)
            deduped.append(page_data)
        deduped.sort(key=lambda p: p.get("page", {}).get("index", 0))
        return deduped

    def _dedupe_annotations(
        self,
    ) -> tuple[list[OpenContractsAnnotationPythonType], dict[Any, Any]]:
        """Collapse annotations duplicated across an overlap zone.

        Returns the surviving annotations (first copy per signature wins, so the
        owning/earlier chunk's copy is canonical) and an ``id_remap`` mapping each
        dropped duplicate's global ID to the surviving canonical ID — used to
        re-link relationships and ``parent_id`` references that pointed at a
        dropped copy.
        """
        canonical_by_sig: dict[tuple, Any] = {}
        id_remap: dict[Any, Any] = {}
        deduped: list[OpenContractsAnnotationPythonType] = []

        for ann in self._annotations:
            sig = _annotation_signature(ann)
            ann_id = ann.get("id")
            if sig in canonical_by_sig:
                canonical_id = canonical_by_sig[sig]
                if ann_id is not None and canonical_id is not None:
                    id_remap[ann_id] = canonical_id
                continue
            canonical_by_sig[sig] = ann_id
            deduped.append(ann)

        # Re-anchor surviving parent_id references onto the canonical IDs.
        for ann in deduped:
            pid = ann.get("parent_id")
            if pid is not None and pid in id_remap:
                ann["parent_id"] = id_remap[pid]

        return deduped, id_remap

    def _relink_and_dedupe_relationships(
        self, id_remap: dict[Any, Any]
    ) -> list[OpenContractsRelationshipPythonType]:
        """Rewrite endpoint IDs through ``id_remap`` then drop duplicates.

        Re-linking lets a relationship authored in one chunk reference annotations
        whose canonical copy lives in another chunk; once both copies of a
        boundary-spanning relationship point at the same global IDs they dedupe to
        a single edge.
        """
        seen: set[tuple] = set()
        deduped: list[OpenContractsRelationshipPythonType] = []
        for rel in self._relationships:
            rel["source_annotation_ids"] = [
                id_remap.get(sid, sid) for sid in rel.get("source_annotation_ids", [])
            ]
            rel["target_annotation_ids"] = [
                id_remap.get(tid, tid) for tid in rel.get("target_annotation_ids", [])
            ]
            sig = _relationship_signature(rel)
            if sig in seen:
                continue
            seen.add(sig)
            deduped.append(rel)
        return deduped

    def _report_residual_orphans(
        self,
        annotations: list[OpenContractsAnnotationPythonType],
        relationships: list[OpenContractsRelationshipPythonType],
    ) -> None:
        """Log + meter references that survived dedup but resolve to nothing.

        With sufficient overlap every boundary-spanning reference is re-linked, so
        a non-zero count means a structure spanned *more* pages than ``overlap``.
        This is surfaced for observability but is never fatal.
        """
        all_ids = {a["id"] for a in annotations if a.get("id")}
        orphan_parents = sum(
            1
            for a in annotations
            if a.get("parent_id") is not None and a.get("parent_id") not in all_ids
        )
        orphan_rel_refs = 0
        for rel in relationships:
            for ref in (
                *rel.get("source_annotation_ids", []),
                *rel.get("target_annotation_ids", []),
            ):
                if ref not in all_ids:
                    orphan_rel_refs += 1

        total = orphan_parents + orphan_rel_refs
        if total:
            logger.warning(
                "Chunk reassembly left %d residual cross-boundary orphan "
                "reference(s) (%d parent_id, %d relationship endpoint) after "
                "overlap dedup + re-linking — a structure likely spans more "
                "pages than the configured chunk overlap.",
                total,
                orphan_parents,
                orphan_rel_refs,
                extra={
                    "metric": "chunk_reassembly_orphan_refs",
                    "orphan_parent_refs": orphan_parents,
                    "orphan_relationship_refs": orphan_rel_refs,
                },
            )
