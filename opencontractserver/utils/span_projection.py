"""Char-span → PAWLs-token projection, shared across annotation producers.

PDF documents are token-indexed (PAWLs bounding boxes); char-offset spans are
indexed against the PAWLs-derived document text — the parser saves
``txt_extract_file`` from ``build_translation_layer(...).doc_text``
(``opencontractserver/pipeline/base/parser.py``), so offsets into that text
project onto token bounding boxes losslessly via PlasmaPDF.

This module is the single home for that projection. Consumers:

* datacell auto-grounding (``opencontractserver/utils/extraction_grounding.py``)
* the reference-enrichment writer (``opencontractserver/enrichment/writer.py``)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from opencontractserver.utils.files import read_field_file_text


def load_document_text_and_layer(document: Any) -> tuple[str, Any, str]:
    """Load document text and the optional PlasmaPDF translation layer.

    Returns ``(doc_text, pdf_layer_or_none, annotation_type_const)`` —
    ``TOKEN_LABEL`` with a layer for PDFs, ``SPAN_LABEL`` with ``None`` for
    text/DOCX. Raises ``ValueError`` for unsupported types or missing files;
    callers that prefer a span fallback over failure catch it.
    """
    from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL
    from opencontractserver.constants.document_processing import (
        DOCX_MIME_TYPE,
        TEXT_MIMETYPES,
    )
    from opencontractserver.utils.compact_pawls import expand_pawls_pages

    file_type = (document.file_type or "").lower()

    if file_type == "application/pdf":
        if not document.pawls_parse_file:
            raise ValueError(
                f"PDF document id={document.id} lacks a PAWLS layer; "
                "cannot project spans onto tokens."
            )
        from plasmapdf.models.PdfDataLayer import build_translation_layer

        with document.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        return pdf_layer.doc_text, pdf_layer, TOKEN_LABEL

    elif file_type in TEXT_MIMETYPES or file_type == DOCX_MIME_TYPE:
        if not document.txt_extract_file:
            raise ValueError(
                f"Document id={document.id} (type={file_type}) lacks "
                "txt_extract_file; cannot anchor spans."
            )
        doc_text = read_field_file_text(document.txt_extract_file)

        return doc_text, None, SPAN_LABEL

    else:
        raise ValueError(
            f"Unsupported file_type {file_type!r} for span anchoring on "
            f"document id={document.id}"
        )


def span_annotation_payload(start: int, end: int, text: str) -> tuple[dict, int]:
    """Canonical ``(annotation_json, page)`` for a ``SPAN_LABEL`` annotation.

    The json shape (``{start, end, text}``) and the no-page sentinel are the
    contract the TXT renderer and the import anchorer
    (``annotation_anchoring._anchor_text``) share — build span payloads here
    so the shape cannot drift between producers.
    """
    from opencontractserver.constants.annotations import SPAN_NO_PAGE

    return {"start": start, "end": end, "text": text}, SPAN_NO_PAGE


def project_span_to_token_annotation(
    pdf_layer: Any,
    *,
    start: int,
    end: int,
    text: str,
    label_text: str,
) -> tuple[dict, int, str]:
    """Project a char-offset span onto PAWLs token bounding boxes.

    Returns ``(annotation_json, page, raw_text)`` ready for a ``TOKEN_LABEL``
    ``Annotation`` — ``raw_text`` is PlasmaPDF's token-joined rendering of the
    span (the canonical raw text for token annotations). Raises ``ValueError``
    when PlasmaPDF cannot determine the page — skipping (or falling back to a
    span) is preferred over saving with a wrong page, which produces a
    structurally incorrect annotation that confuses users clicking through to
    the source.
    """
    from plasmapdf.models.types import SpanAnnotation, TextSpan

    span = TextSpan(id=str(uuid4()), start=start, end=end, text=text)
    oc_ann = pdf_layer.create_opencontract_annotation_from_span(
        SpanAnnotation(span=span, annotation_label=label_text)
    )
    page = oc_ann.get("page")
    if page is None:
        raise ValueError(
            f"PlasmaPDF could not determine page for span [{start}:{end}]."
        )
    return oc_ann["annotation_json"], page, oc_ann["rawText"]
