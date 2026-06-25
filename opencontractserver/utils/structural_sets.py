"""
Shared helper for materialising a document's structural annotations into a
:class:`~opencontractserver.annotations.models.StructuralAnnotationSet`.

The parser pipeline (``BaseParser.save_parsed_data``) and the worker-upload
ingestion path (``opencontractserver.worker_uploads.tasks``) both need to take
the structural annotations a parser produced (``structural=True``, still bound
to ``document``) and migrate them into a shared ``StructuralAnnotationSet`` so
they are stored once, embedded with corpus-specific embedders, and resolved
through the same structural-set join the rest of the platform relies on (see
``AnnotationService.get_document_annotations``). Keeping the logic in one place
guarantees the two ingestion paths produce an identical end-state — a document
ingested locally by the parser and the same document ingested remotely and
pushed through worker-upload are byte-for-byte equivalent in their structural
layer.
"""

from __future__ import annotations

import logging
from typing import Any

from opencontractserver.annotations.models import (
    Annotation,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


def create_structural_annotation_set(
    document: Document,
    user: Any,
    *,
    parser_name: str,
    parser_version: str = "1.0",
) -> StructuralAnnotationSet | None:
    """
    Create a :class:`StructuralAnnotationSet` for *document* and migrate its
    structural annotations and relationships into it.

    The migration enforces the model's XOR constraint (an annotation/relationship
    belongs to *either* a ``document`` *or* a ``structural_set``, never both) by
    nulling ``document`` as each row is re-homed onto the set, then links the
    document to the set.

    Idempotent: a document that already has a structural set, or that has no
    structural annotations, is a no-op (returns the existing set or ``None``).
    ``get_or_create`` on the content hash tolerates retry scenarios where the
    set was created but the document link was not saved.

    Args:
        document: The ``Document`` whose structural annotations should migrate.
        user: The user to credit as the set's creator.
        parser_name: Name of the parser that produced the structural layer
            (stored on the set for provenance / dedup bookkeeping).
        parser_version: Version string for the parser.

    Returns:
        The (created or reused) ``StructuralAnnotationSet``, or ``None`` if the
        document had no structural annotations to migrate.
    """
    # Already linked — nothing to do.
    if document.structural_annotation_set:
        logger.info(
            f"Document {document.pk} already has StructuralAnnotationSet "
            f"{document.structural_annotation_set.pk}"
        )
        return document.structural_annotation_set

    structural_annotations = Annotation.objects.filter(
        document=document, structural=True, structural_set__isnull=True
    )

    if not structural_annotations.exists():
        logger.info(f"Document {document.pk} has no structural annotations to migrate")
        return None

    # Stable content hash so re-ingesting the same source PDF reuses the set.
    content_hash = document.pdf_file_hash or f"doc_{document.pk}"

    struct_set, created = StructuralAnnotationSet.objects.get_or_create(
        content_hash=content_hash,
        defaults={
            "creator": user,
            "parser_name": parser_name,
            "parser_version": parser_version,
            "page_count": document.page_count,
            "pawls_parse_file": document.pawls_parse_file,
            "txt_extract_file": document.txt_extract_file,
        },
    )

    if created:
        logger.info(
            f"Created StructuralAnnotationSet {struct_set.pk} for document {document.pk}"
        )
    else:
        logger.info(
            f"Reusing existing StructuralAnnotationSet {struct_set.pk} "
            f"for document {document.pk} (retry/dedup scenario)"
        )

    structural_annotation_ids = set(structural_annotations.values_list("id", flat=True))

    for annot in structural_annotations:
        annot.structural_set = struct_set
        annot.document = None  # XOR constraint: either document or structural_set
        annot.save()

    # Migrate structural relationships whose endpoints are both structural
    # annotations that we just migrated.
    structural_relationships = Relationship.objects.filter(
        document=document, structural=True, structural_set__isnull=True
    ).filter(
        source_annotations__id__in=structural_annotation_ids,
        target_annotations__id__in=structural_annotation_ids,
    )

    for rel in structural_relationships:
        rel.structural_set = struct_set
        rel.document = None  # XOR constraint
        rel.save()

    document.structural_annotation_set = struct_set
    document.save()

    logger.info(
        f"Migrated {structural_annotations.count()} annotations and "
        f"{structural_relationships.count()} relationships to "
        f"StructuralAnnotationSet {struct_set.pk}"
    )
    return struct_set
