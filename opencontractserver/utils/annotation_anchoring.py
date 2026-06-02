"""Anchor producer 'dumb-anchor' annotations onto pipeline output.

PDF annotations carry a ``page`` + ``bbox``; text annotations carry ``start``/
``end`` hints. Both carry ``rawText`` (the source of truth). This module turns
them into full ``OpenContractsAnnotationPythonType`` dicts ready for
``import_annotations``; annotations that cannot be confidently anchored are
dropped and recorded in the returned report. Pure: no DB, no IO.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL
from opencontractserver.constants.annotations import (
    ANNOTATION_ANCHOR_GEOMETRY_OVERLAP_THRESHOLD,
    ANNOTATION_ANCHOR_TEXT_CONFIRM_RATIO,
    PDF_OUTLINE_FUZZY_MATCH_THRESHOLD,
)
from opencontractserver.utils.pdf_token_matching import (
    match_title_to_tokens,
    page_text_tokens,
    select_tokens_in_region,
    union_bounds,
)


def _norm(s: str) -> str:
    return " ".join((s or "").casefold().split())


def _anchor_pdf(ann: dict, pawls: list[dict]) -> dict | None:
    page_idx = ann.get("page")
    if not isinstance(page_idx, int) or not (0 <= page_idx < len(pawls)):
        return None
    page = pawls[page_idx]
    tokens = page.get("tokens", []) or []
    raw = ann.get("rawText", "")
    indices: list[int] | None = None

    bbox = ann.get("bbox")
    if isinstance(bbox, dict):
        cand = select_tokens_in_region(
            page, bbox, overlap_threshold=ANNOTATION_ANCHOR_GEOMETRY_OVERLAP_THRESHOLD
        )
        if cand:
            joined = " ".join((tokens[i].get("text") or "") for i in cand)
            if SequenceMatcher(None, _norm(joined), _norm(raw)).ratio() >= (
                ANNOTATION_ANCHOR_TEXT_CONFIRM_RATIO
            ):
                indices = cand

    if indices is None:
        texts, original = page_text_tokens(page)
        span = match_title_to_tokens(raw, texts, PDF_OUTLINE_FUZZY_MATCH_THRESHOLD)
        if span is not None:
            indices = original[span[0]: span[1] + 1]

    if not indices:
        return None

    return {
        "id": ann.get("id"),
        "annotationLabel": ann["label"],
        "annotation_type": TOKEN_LABEL,
        "structural": False,
        "parent_id": ann.get("parent_id"),
        "rawText": raw,
        "long_description": ann.get("long_description"),
        "page": page_idx,
        "annotation_json": {
            str(page_idx): {
                "bounds": union_bounds(tokens, indices),
                "tokensJsons": [
                    {"pageIndex": page_idx, "tokenIndex": i} for i in indices
                ],
                "rawText": raw,
            }
        },
    }


def _anchor_text(ann: dict, content: str) -> dict | None:
    raw = ann.get("rawText") or ""
    if not raw or not content:
        return None
    hint = ann.get("start")
    occurrences = []
    start = content.find(raw)
    while start != -1:
        occurrences.append(start)
        start = content.find(raw, start + 1)
    if not occurrences:
        return None
    if isinstance(hint, int):
        chosen = min(occurrences, key=lambda s: abs(s - hint))
    else:
        chosen = occurrences[0]
    end = chosen + len(raw)
    return {
        "id": ann.get("id"),
        "annotationLabel": ann["label"],
        "annotation_type": SPAN_LABEL,
        "structural": False,
        "parent_id": ann.get("parent_id"),
        "rawText": raw,
        "long_description": ann.get("long_description"),
        "page": 1,
        "annotation_json": {"start": chosen, "end": end, "text": content[chosen:end]},
    }


def anchor_annotations(
    annotations: list[dict],
    *,
    is_pdf: bool,
    pawls: list[dict],
    content: str,
) -> tuple[list[dict], list[dict]]:
    """Return ``(anchored_dicts, report)``. ``report`` has one entry per input
    annotation: ``{"id", "rawText", "dropped": bool, "reason": str}``."""
    out: list[dict] = []
    report: list[dict] = []
    for ann in annotations:
        try:
            built = _anchor_pdf(ann, pawls) if is_pdf else _anchor_text(ann, content)
        except Exception as exc:  # never abort the batch for one annotation
            built = None
            reason = f"error: {exc}"
        else:
            reason = "" if built else "no confident anchor"
        if built:
            out.append(built)
            report.append({"id": ann.get("id"), "rawText": ann.get("rawText", "")[:80],
                           "dropped": False, "reason": ""})
        else:
            report.append({"id": ann.get("id"), "rawText": ann.get("rawText", "")[:80],
                           "dropped": True, "reason": reason})
    return out, report
