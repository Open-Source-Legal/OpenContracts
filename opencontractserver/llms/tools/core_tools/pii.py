"""Agent tool: scan documents for PII via the privacy-filter microservice
and create labeled annotations for each detection.

PDFs receive token-level annotations through PlasmaPDF (TOKEN_LABEL).
Plain-text documents receive character-span annotations (SPAN_LABEL).
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any
from uuid import uuid4

from django.db import transaction

from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL, Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

from ._helpers import _db_sync_to_async
from ._privacy_filter_client import Detection, adetect_pii

logger = logging.getLogger(__name__)


# Mapping from privacy-filter entity_group → (label_text, color, icon).
# Labels are auto-created via Corpus.ensure_label_and_labelset on first use.
ENTITY_GROUP_LABELS: dict[str, tuple[str, str, str]] = {
    "private_email":  ("PII: Email",          "#1f77b4", "mail"),
    "phone_number":   ("PII: Phone",           "#ff7f0e", "phone"),
    "person_name":    ("PII: Person Name",     "#2ca02c", "user"),
    "address":        ("PII: Address",         "#d62728", "home"),
    "account_number": ("PII: Account Number",  "#9467bd", "credit card"),
    "url":            ("PII: URL",             "#8c564b", "linkify"),
    "date":           ("PII: Date",            "#e377c2", "calendar"),
    "secret":         ("PII: Secret",          "#7f7f7f", "key"),
}


def _load_doc_text_sync(
    document_id: int, corpus_id: int
) -> tuple[Any, Any, str, str, Any]:
    """Return (document, corpus, doc_text, file_type, pdf_layer).

    Validates document↔corpus linkage and supported file type. For PDFs,
    the PlasmaPDF translation layer is built here and returned so it can be
    forwarded directly into ``_persist_annotations_sync`` without a second
    PAWLs read.  For non-PDF documents ``pdf_layer`` is ``None``.
    """
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document id={document_id} does not exist") from exc

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus id={corpus_id} does not exist") from exc

    if not corpus.get_documents().filter(pk=document_id).exists():
        raise ValueError(
            f"Document id={document_id} is not linked to corpus id={corpus_id}."
        )

    file_type = (doc.file_type or "").lower()
    if not file_type:
        raise ValueError(f"Document id={document_id} has no file_type set.")

    if file_type in {"application/txt", "text/plain"}:
        if not doc.txt_extract_file:
            raise ValueError(
                f"Text document id={document_id} lacks txt_extract_file."
            )
        with doc.txt_extract_file.open("r") as f:
            doc_text = f.read()
        return doc, corpus, doc_text, file_type, None

    if file_type == "application/pdf":
        if not doc.pawls_parse_file:
            raise ValueError(
                f"PDF document id={document_id} lacks a PAWLS layer."
            )
        from plasmapdf.models.PdfDataLayer import build_translation_layer

        from opencontractserver.utils.compact_pawls import expand_pawls_pages

        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(_json.load(f))
        pdf_layer = build_translation_layer(pawls_tokens)
        return doc, corpus, pdf_layer.doc_text, file_type, pdf_layer

    raise ValueError(
        f"Unsupported file_type {doc.file_type} for document id={document_id}"
    )


def _persist_annotations_sync(
    *,
    doc: Any,
    corpus: Any,
    pdf_layer: Any,
    creator_id: int,
    corpus_action_id: int | None,
    file_type: str,
    detections: list[Detection],
    doc_text: str,
) -> list[int]:
    """Create one Annotation per detection. Returns the new annotation ids."""
    if file_type == "application/pdf":
        from plasmapdf.models.types import SpanAnnotation, TextSpan

        label_type_const = TOKEN_LABEL
    else:
        label_type_const = SPAN_LABEL

    label_cache: dict[str, Any] = {}

    def _label_for(group: str):
        if group in label_cache:
            return label_cache[group]
        mapping = ENTITY_GROUP_LABELS.get(group)
        if mapping is None:
            raise ValueError(f"Unknown entity_group from privacy-filter: {group!r}")
        label_text, color, icon = mapping
        label = corpus.ensure_label_and_labelset(
            label_text=label_text,
            creator_id=creator_id,
            label_type=label_type_const,
            color=color,
            icon=icon,
        )
        label_cache[group] = label
        return label

    new_ids: list[int] = []
    with transaction.atomic():
        for det in detections:
            start, end = det["start"], det["end"]
            if start < 0 or end > len(doc_text) or start >= end:
                logger.warning(
                    "scan_and_annotate_pii: skipping invalid detection "
                    "start=%s end=%s len=%s", start, end, len(doc_text),
                )
                continue
            group = det["entity_group"]
            if group not in ENTITY_GROUP_LABELS:
                logger.warning(
                    "scan_and_annotate_pii: unknown entity_group=%r from privacy-filter; skipping",
                    group,
                )
                continue
            label_obj = _label_for(group)
            if file_type == "application/pdf":
                span = TextSpan(
                    id=str(uuid4()), start=start, end=end, text=doc_text[start:end]
                )
                span_annotation = SpanAnnotation(
                    span=span, annotation_label=label_obj.text
                )
                oc_ann = pdf_layer.create_opencontract_annotation_from_span(
                    span_annotation
                )
                ann = Annotation(
                    raw_text=oc_ann["rawText"],
                    page=oc_ann.get("page", 1),
                    json=oc_ann["annotation_json"],
                    annotation_label=label_obj,
                    document=doc,
                    corpus=corpus,
                    creator_id=creator_id,
                    corpus_action_id=corpus_action_id,
                    annotation_type=TOKEN_LABEL,
                    structural=False,
                )
            else:
                ann = Annotation(
                    raw_text=doc_text[start:end],
                    page=1,
                    json={"start": start, "end": end},
                    annotation_label=label_obj,
                    document=doc,
                    corpus=corpus,
                    creator_id=creator_id,
                    corpus_action_id=corpus_action_id,
                    annotation_type=SPAN_LABEL,
                    structural=False,
                )
            ann.save()
            new_ids.append(ann.pk)
    return new_ids


async def ascan_and_annotate_pii(
    *,
    # context-injected by the tool framework
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
    # agent-controllable knobs
    min_score: float = 0.5,
    entity_groups: list[str] | None = None,
    dry_run: bool = False,
    start_char: int | None = None,
    end_char: int | None = None,
) -> dict:
    """Scan ``document_id`` for PII and create labeled annotations.

    Args:
        document_id: Document to scan (injected from context).
        corpus_id: Corpus that owns the document (injected from context).
        creator_id: User credited as annotation creator (injected from context).
        corpus_action_id: Optional triggering corpus action (injected from context).
        min_score: Drop detections with score < this value (default 0.5).
        entity_groups: Optional allowlist (e.g. ``["private_email"]``);
            ``None`` means accept all 8 categories.
        dry_run: If True, return detections without writing annotations.
        start_char, end_char: Optional character range scoping the scan.
            Offsets returned are always global (relative to full doc_text).

    Returns a dict with: document_id, scanned_chars, detection_count,
    by_entity_group, annotation_ids (empty when dry_run), detections (only
    populated when dry_run).
    """
    doc, corpus, doc_text, file_type, pdf_layer = await _db_sync_to_async(
        _load_doc_text_sync
    )(document_id, corpus_id)

    s = 0 if start_char is None else max(0, min(start_char, len(doc_text)))
    e = len(doc_text) if end_char is None else max(0, min(end_char, len(doc_text)))
    if s >= e:
        return {
            "document_id": document_id,
            "scanned_chars": 0,
            "detection_count": 0,
            "by_entity_group": {},
            "annotation_ids": [],
            "detections": [],
        }

    slice_text = doc_text[s:e]
    raw = await adetect_pii(slice_text)

    allowlist = set(entity_groups) if entity_groups else None
    detections: list[Detection] = []
    for det in raw:
        if det["score"] < float(min_score):
            continue
        if allowlist is not None and det["entity_group"] not in allowlist:
            continue
        g_start = det["start"] + s
        g_end = det["end"] + s
        detections.append(
            Detection(
                entity_group=det["entity_group"],
                score=det["score"],
                start=g_start,
                end=g_end,
                text=doc_text[g_start:g_end],
            )
        )

    by_group: dict[str, int] = {}
    for d in detections:
        by_group[d["entity_group"]] = by_group.get(d["entity_group"], 0) + 1

    if dry_run:
        return {
            "document_id": document_id,
            "scanned_chars": len(slice_text),
            "detection_count": len(detections),
            "by_entity_group": by_group,
            "annotation_ids": [],
            "detections": [dict(d) for d in detections],
        }

    new_ids = await _db_sync_to_async(_persist_annotations_sync)(
        doc=doc,
        corpus=corpus,
        pdf_layer=pdf_layer,
        creator_id=creator_id,
        corpus_action_id=corpus_action_id,
        file_type=file_type,
        detections=detections,
        doc_text=doc_text,
    )
    return {
        "document_id": document_id,
        "scanned_chars": len(slice_text),
        "detection_count": len(detections),
        "by_entity_group": by_group,
        "annotation_ids": new_ids,
        "detections": [],
    }
