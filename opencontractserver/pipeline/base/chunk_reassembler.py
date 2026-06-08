"""Incremental reassembly of per-chunk OpenContractDocExport results.

Accepts one chunk result at a time (``add_chunk``) so the chunked-parse Celery
callback can stream results from storage without holding them all in memory,
then produces a single merged document (``finalize``). The list-based
``_reassemble_chunk_results`` in ``chunked_parser`` delegates here.
"""

import logging
from typing import Optional

from opencontractserver.annotations.compact_json import offset_annotation_json
from opencontractserver.types.dicts import (
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
    PawlsPagePythonType,
)

logger = logging.getLogger(__name__)


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

        result: OpenContractDocExport = {
            "title": self._first.get("title", ""),
            "content": "\n".join(self._content_parts),
            "description": self._first.get("description"),
            "pawls_file_content": self._pawls,
            "page_count": self._total_pages,
            "doc_labels": self._doc_labels,
            "labelled_text": self._annotations,
            "relationships": self._relationships,
        }

        # Detect and warn about orphaned cross-chunk parent references
        all_annotation_ids = {a["id"] for a in self._annotations if a.get("id")}
        orphaned_count = 0
        for ann in self._annotations:
            pid = ann.get("parent_id")
            if pid is not None and pid not in all_annotation_ids:
                orphaned_count += 1

        if orphaned_count > 0:
            logger.debug(
                f"Reassembly produced {orphaned_count} orphaned parent_id "
                f"reference(s). Cross-chunk parent-child relationships cannot "
                f"be preserved when chunks are parsed independently."
            )

        return result
