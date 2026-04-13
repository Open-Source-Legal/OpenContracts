"""
Auto-grounding pipeline for extraction results.

After an LLM extracts data into a Datacell, this module finds the extracted
text values in the source document and creates Annotation objects linked as
sources.  It bridges the text_alignment utility with PlasmaPDF (for PDFs) or
span-based annotations (for text/DOCX).

The grounding is best-effort: if alignment fails for a value, it is silently
skipped — the extraction result is never lost.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from asgiref.sync import sync_to_async

from opencontractserver.constants.extraction import (
    DATACELL_DATA_KEY,
    MAX_GROUNDABLE_STRINGS,
    MIN_GROUNDABLE_LENGTH,
)
from opencontractserver.utils.text_alignment import (
    AlignmentResult,
    align_text_to_document,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: Extract groundable strings from datacell.data
# ---------------------------------------------------------------------------


def extract_groundable_strings(data: Any) -> list[str]:
    """Recursively extract string values worth grounding from extraction results.

    Walks the extraction result (which may be a primitive, dict, or list)
    and collects string values that are likely to appear verbatim in the
    source document.

    Filters out:
    - Strings shorter than ``MIN_GROUNDABLE_LENGTH``
    - Pure numeric strings
    - Boolean-like strings ("true", "false", "yes", "no")

    Returns at most ``MAX_GROUNDABLE_STRINGS`` unique strings, preserving
    insertion order.
    """
    seen: set[str] = set()
    results: list[str] = []

    def _walk(obj: Any) -> None:
        if len(results) >= MAX_GROUNDABLE_STRINGS:
            return

        if isinstance(obj, str):
            stripped = obj.strip()
            if (
                len(stripped) >= MIN_GROUNDABLE_LENGTH
                and stripped not in seen
                and not _is_non_groundable(stripped)
            ):
                seen.add(stripped)
                results.append(stripped)

        elif isinstance(obj, dict):
            for value in obj.values():
                _walk(value)
                if len(results) >= MAX_GROUNDABLE_STRINGS:
                    return

        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)
                if len(results) >= MAX_GROUNDABLE_STRINGS:
                    return

    _walk(data)
    return results


def _is_non_groundable(s: str) -> bool:
    """Return True for strings unlikely to appear verbatim in a document."""
    lower = s.lower()

    # Boolean-like
    if lower in ("true", "false", "yes", "no", "none", "null", "n/a"):
        return True

    # Pure numeric (int or float)
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        pass

    return False


# ---------------------------------------------------------------------------
# Step 2: Load document text (format-aware)
# ---------------------------------------------------------------------------


@sync_to_async
def _load_document_text_and_layer(document):
    """Load document text and optional PlasmaPDF translation layer.

    Returns:
        (doc_text, pdf_layer_or_none, annotation_type_const)
    """
    from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL
    from opencontractserver.constants.document_processing import TEXT_MIMETYPES
    from opencontractserver.utils.compact_pawls import expand_pawls_pages

    file_type = (document.file_type or "").lower()
    docx_mime = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    if file_type == "application/pdf":
        if not document.pawls_parse_file:
            raise ValueError(
                f"PDF document id={document.id} lacks a PAWLS layer; "
                "cannot ground extractions."
            )
        from plasmapdf.models.PdfDataLayer import build_translation_layer

        with document.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        return pdf_layer.doc_text, pdf_layer, TOKEN_LABEL

    elif file_type in TEXT_MIMETYPES or file_type == docx_mime:
        if not document.txt_extract_file:
            raise ValueError(
                f"Document id={document.id} (type={file_type}) lacks "
                "txt_extract_file; cannot ground extractions."
            )
        with document.txt_extract_file.open("r") as f:
            doc_text = f.read()

        return doc_text, None, SPAN_LABEL

    else:
        raise ValueError(
            f"Unsupported file_type {file_type!r} for grounding on "
            f"document id={document.id}"
        )


# ---------------------------------------------------------------------------
# Step 3: Create annotations from alignment results
# ---------------------------------------------------------------------------


@sync_to_async
def _create_grounding_annotations(
    alignment_results: list[AlignmentResult],
    document,
    corpus,
    creator_id: int,
    pdf_layer,
    annotation_type: str,
) -> list:
    """Create Annotation objects for each alignment result.

    For PDFs, uses PlasmaPDF to generate token-level annotations with
    bounding boxes.  For text/DOCX, creates span annotations with
    character offsets.

    Returns list of saved Annotation instances.
    """
    from django.db import transaction

    from opencontractserver.annotations.models import (
        SPAN_LABEL,
        TOKEN_LABEL,
    )
    from opencontractserver.constants.annotations import OC_EXTRACT_SOURCE_LABEL

    if not alignment_results:
        return []

    # Get or create the extraction source label
    label_obj = corpus.ensure_label_and_labelset(
        label_text=OC_EXTRACT_SOURCE_LABEL,
        creator_id=creator_id,
        label_type=annotation_type,
    )

    annotations = []

    for result in alignment_results:
        try:
            with transaction.atomic():
                if annotation_type == TOKEN_LABEL and pdf_layer is not None:
                    annot = _create_pdf_annotation(
                        result, document, corpus, creator_id, pdf_layer, label_obj
                    )
                elif annotation_type == SPAN_LABEL:
                    annot = _create_span_annotation(
                        result, document, corpus, creator_id, label_obj
                    )
                else:
                    continue

                annot.save()
                annotations.append(annot)

        except Exception:
            logger.warning(
                "Failed to create grounding annotation for %r "
                "at [%d:%d] in document %d",
                result.query_text[:50],
                result.char_start,
                result.char_end,
                document.id,
                exc_info=True,
            )

    return annotations


def _create_pdf_annotation(result, document, corpus, creator_id, pdf_layer, label_obj):
    """Create a TOKEN_LABEL annotation for a PDF document via PlasmaPDF."""
    from plasmapdf.models.types import SpanAnnotation, TextSpan

    from opencontractserver.annotations.models import TOKEN_LABEL, Annotation

    span = TextSpan(
        id=str(uuid4()),
        start=result.char_start,
        end=result.char_end,
        text=result.matched_text,
    )
    span_annotation = SpanAnnotation(span=span, annotation_label=label_obj.text)
    oc_ann = pdf_layer.create_opencontract_annotation_from_span(span_annotation)

    page = oc_ann.get("page")
    if page is None:
        logger.warning(
            "PlasmaPDF annotation missing 'page' key for span [%d:%d] "
            "in document %d; defaulting to page 1",
            result.char_start,
            result.char_end,
            document.id,
        )
        page = 1

    return Annotation(
        raw_text=oc_ann["rawText"],
        page=page,
        json=oc_ann["annotation_json"],
        annotation_label=label_obj,
        document=document,
        corpus=corpus,
        creator_id=creator_id,
        annotation_type=TOKEN_LABEL,
        structural=False,
    )


def _create_span_annotation(result, document, corpus, creator_id, label_obj):
    """Create a SPAN_LABEL annotation for a text/DOCX document."""
    from opencontractserver.annotations.models import SPAN_LABEL, Annotation

    return Annotation(
        raw_text=result.matched_text,
        page=1,
        json={"start": result.char_start, "end": result.char_end},
        annotation_label=label_obj,
        document=document,
        corpus=corpus,
        creator_id=creator_id,
        annotation_type=SPAN_LABEL,
        structural=False,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@sync_to_async
def _resolve_corpus(corpus_id: int):
    """Resolve a corpus ID to a Corpus instance."""
    from opencontractserver.corpuses.models import Corpus

    try:
        return Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist:
        logger.warning("Corpus id=%d not found for auto-grounding", corpus_id)
        return None


async def ground_extraction_to_annotations(
    datacell,
    document,
    corpus,
    user_id: int,
    *,
    fuzzy_threshold: float = 0.75,
    enable_fuzzy: bool = True,
) -> list:
    """Auto-ground a completed Datacell's extracted data to source annotations.

    This is the main entry point.  Call it after ``datacell.data`` has been
    populated with extraction results.

    Steps:
        1. Extract groundable text strings from ``datacell.data``
        2. Load document text (format-aware: PDF/text/DOCX)
        3. Align each string to the document text
        4. Create Annotation objects (TOKEN_LABEL or SPAN_LABEL)
        5. Link annotations to ``datacell.sources`` M2M

    Args:
        datacell: A Datacell with populated ``data`` field.
        document: The source Document.
        corpus: The Corpus instance or corpus ID (int). May be None.
        user_id: Creator ID for the annotations.
        fuzzy_threshold: Minimum similarity for fuzzy matches.
        enable_fuzzy: Whether to attempt fuzzy matching.

    Returns:
        List of created Annotation instances (may be empty).
    """
    if not datacell.data:
        return []

    if corpus is None:
        logger.info(
            "Skipping auto-grounding for datacell %d: no corpus context",
            datacell.id,
        )
        return []

    # Resolve corpus ID to Corpus instance if needed
    if isinstance(corpus, int):
        corpus = await _resolve_corpus(corpus)
        if corpus is None:
            return []

    # 1. Extract groundable strings
    if isinstance(datacell.data, dict):
        raw_data = datacell.data.get(DATACELL_DATA_KEY)
        if raw_data is None and datacell.data:
            logger.debug(
                "Datacell %d data dict has no %r key; available keys: %s",
                datacell.id,
                DATACELL_DATA_KEY,
                list(datacell.data.keys()),
            )
    else:
        raw_data = datacell.data
    groundable = extract_groundable_strings(raw_data)

    if not groundable:
        logger.debug("No groundable strings found in datacell %d", datacell.id)
        return []

    logger.info(
        "Auto-grounding datacell %d: %d groundable strings from extraction",
        datacell.id,
        len(groundable),
    )

    # 2. Load document text + optional PDF layer
    doc_text, pdf_layer, annotation_type = await _load_document_text_and_layer(document)

    # 3. Align strings to document
    alignments = align_text_to_document(
        groundable,
        doc_text,
        fuzzy_threshold=fuzzy_threshold,
        enable_fuzzy=enable_fuzzy,
    )

    if not alignments:
        logger.info(
            "No alignment hits for datacell %d (%d queries tried)",
            datacell.id,
            len(groundable),
        )
        return []

    logger.info(
        "Aligned %d/%d strings for datacell %d",
        len(alignments),
        len(groundable),
        datacell.id,
    )

    # 4. Create annotations
    annotations = await _create_grounding_annotations(
        alignment_results=alignments,
        document=document,
        corpus=corpus,
        creator_id=user_id,
        pdf_layer=pdf_layer,
        annotation_type=annotation_type,
    )

    # 5. Link to datacell
    if annotations:
        await _link_sources(datacell, annotations)
        logger.info(
            "Linked %d source annotations to datacell %d",
            len(annotations),
            datacell.id,
        )

    return annotations


@sync_to_async
def _link_sources(datacell, annotations):
    """Add annotation objects to datacell.sources M2M."""
    datacell.sources.add(*annotations)
