"""Anchor producer 'dumb-anchor' annotations onto pipeline output.

PDF annotations carry a ``page`` + ``bbox``; text annotations carry ``start``/
``end`` hints. Both carry ``rawText`` (the source of truth). This module turns
them into full ``OpenContractsAnnotationPythonType`` dicts ready for
``import_annotations``; annotations that cannot be confidently anchored are
dropped and recorded in the returned report. Pure: no DB, no IO.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import cast

from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL
from opencontractserver.constants.annotations import (
    ANNOTATION_ANCHOR_GEOMETRY_OVERLAP_THRESHOLD,
    ANNOTATION_ANCHOR_TEXT_CONFIRM_RATIO,
    ANNOTATION_REPORT_RAWTEXT_HEAD,
    ANNOTATION_REPORT_RAWTEXT_TAIL,
    PDF_OUTLINE_FUZZY_MATCH_THRESHOLD,
)
from opencontractserver.types.dicts import (
    BoundingBoxPythonType,
    PawlsPagePythonType,
)
from opencontractserver.utils.pdf_token_matching import (
    match_title_to_tokens,
    page_text_tokens,
    select_tokens_in_region,
    union_bounds,
)
from opencontractserver.utils.text import truncate_middle


def report_rawtext_preview(raw: str | None) -> str:
    """Head+tail preview of an annotation's rawText for a remap report entry."""
    return truncate_middle(
        raw, ANNOTATION_REPORT_RAWTEXT_HEAD, ANNOTATION_REPORT_RAWTEXT_TAIL
    )


def _norm(s: str) -> str:
    return " ".join((s or "").casefold().split())


def _anchor_pdf_page(
    page_idx: object, bbox: object, raw: str, pawls: list[dict]
) -> list[int] | None:
    """Resolve token indices for a single ``(page, bbox, rawText)`` anchor.

    Tries geometry (bbox overlap, text-confirmed) first, then a fuzzy rawText
    match against the page's tokens. Returns ``None`` when neither yields a
    confident match.
    """
    if not isinstance(page_idx, int) or not (0 <= page_idx < len(pawls)):
        return None
    page = pawls[page_idx]
    tokens = page.get("tokens", []) or []
    indices: list[int] | None = None

    if isinstance(bbox, dict):
        cand = select_tokens_in_region(
            cast(PawlsPagePythonType, page),
            cast(BoundingBoxPythonType, bbox),
            overlap_threshold=ANNOTATION_ANCHOR_GEOMETRY_OVERLAP_THRESHOLD,
        )
        if cand:
            joined = " ".join((tokens[i].get("text") or "") for i in cand)
            if SequenceMatcher(None, _norm(joined), _norm(raw)).ratio() >= (
                ANNOTATION_ANCHOR_TEXT_CONFIRM_RATIO
            ):
                indices = cand

    if indices is None:
        texts, original = page_text_tokens(cast(PawlsPagePythonType, page))
        span = match_title_to_tokens(raw, texts, PDF_OUTLINE_FUZZY_MATCH_THRESHOLD)
        if span is not None:
            indices = original[span[0] : span[1] + 1]

    return indices or None


def _anchor_pdf(ann: dict, pawls: list[dict]) -> dict | None:
    """Anchor a (possibly multi-page) PDF annotation onto ``pawls``.

    Reads an ``anchors`` list (``[{"page", "bbox", "rawText"}, ...]``) when
    present — produced by the legacy adapter for multi-page annotations — and
    otherwise falls back to a single top-level ``page`` + ``bbox`` (the dumb-
    anchor sidecar shape, so existing single-page sidecars are byte-identical).
    Each page is resolved independently; a page that cannot be confidently
    anchored is omitted. Returns ``None`` only when no page anchors at all.
    """
    raw = ann.get("rawText", "") or ""
    anchors = ann.get("anchors")
    if not anchors:
        anchors = [{"page": ann.get("page"), "bbox": ann.get("bbox"), "rawText": raw}]

    annotation_json: dict[str, dict] = {}
    first_page: int | None = None
    for anc in anchors:
        page_idx = anc.get("page")
        anc_raw = anc.get("rawText") or raw
        indices = _anchor_pdf_page(page_idx, anc.get("bbox"), anc_raw, pawls)
        if not indices:
            continue
        tokens = pawls[page_idx].get("tokens", []) or []
        annotation_json[str(page_idx)] = {
            "bounds": union_bounds(tokens, indices),
            "tokensJsons": [{"pageIndex": page_idx, "tokenIndex": i} for i in indices],
            "rawText": anc_raw,
        }
        if first_page is None:
            first_page = page_idx

    if not annotation_json:
        return None

    return {
        "id": ann.get("id"),
        "annotationLabel": ann["label"],
        "annotation_type": TOKEN_LABEL,
        "structural": False,
        "parent_id": ann.get("parent_id"),
        "rawText": raw,
        "long_description": ann.get("long_description"),
        "page": first_page,
        "annotation_json": annotation_json,
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
        # PAWLs pages are 0-indexed. A text/SPAN annotation has no meaningful
        # page (its locator is the char span below), so anchor it to page 0
        # rather than the misleading 1.
        "page": 0,
        "annotation_json": {"start": chosen, "end": end, "text": content[chosen:end]},
    }


def legacy_annotation_to_dumb_anchor(ann: dict, *, is_pdf: bool) -> dict | None:
    """Convert a legacy export annotation into the dumb-anchor *input* shape.

    Legacy annotations carry baked ``annotation_json`` (PDF: a ``{page:
    {bounds, tokensJsons, rawText}}`` map; span: ``{start, end, text}``). We
    DISCARD the ``tokensJsons`` and keep only geometry + text so
    ``anchor_annotations`` re-derives indices against whatever PAWLs the
    document actually has — robust to a different/updated parser.

    Returns ``None`` (caller records a drop — never silent) for:
      * ``structural=True`` annotations (regenerated by the parser, never
        re-anchored),
      * compact-v2 / unrecognised ``annotation_json`` shapes lacking the
        ``bounds`` (PDF) or ``start`` (span) we need.
    """
    if ann.get("structural"):
        return None
    aj = ann.get("annotation_json")
    if not isinstance(aj, dict):
        return None

    raw = ann.get("rawText") or ""
    base = {
        "id": ann.get("id"),
        "label": ann.get("annotationLabel") or ann.get("label"),
        "rawText": raw,
        "parent_id": ann.get("parent_id"),
        "long_description": ann.get("long_description"),
    }

    if is_pdf:
        anchors: list[dict] = []
        for page_key, single in aj.items():
            # Skip the span keys / compact shapes that have no per-page bounds.
            if not isinstance(single, dict) or "bounds" not in single:
                continue
            try:
                page_idx = int(page_key)
            except (TypeError, ValueError):
                continue
            anchors.append(
                {
                    "page": page_idx,
                    "bbox": single.get("bounds"),
                    "rawText": single.get("rawText") or raw,
                }
            )
        if not anchors:
            return None
        base["anchors"] = anchors
        return base

    # Text / span annotation: re-find by rawText, hinted by the export start.
    start = aj.get("start")
    if not isinstance(start, int):
        return None
    base["rawText"] = aj.get("text") or raw
    base["start"] = start
    return base


def anchor_annotations(
    annotations: list[dict],
    *,
    is_pdf: bool,
    pawls: list[dict],
    content: str,
) -> tuple[list[dict], list[dict]]:
    """Return ``(anchored_dicts, report)``. ``report`` has one entry per input
    annotation: ``{"id", "rawText", "dropped": bool, "reason": str}``.

    Accepts both the dumb-anchor input shape (top-level ``page``/``bbox`` or
    ``start``) and the legacy export shape (a baked ``annotation_json``). Legacy
    entries are normalised via ``legacy_annotation_to_dumb_anchor`` first, so the
    deferred pipeline (bulk-ZIP / scraper / sidecar imports) accepts old-format
    annotations transparently.
    """
    out: list[dict] = []
    report: list[dict] = []
    for ann in annotations:
        # Normalise legacy export annotations (baked annotation_json) into the
        # dumb-anchor input shape, dropping their token indices.
        if isinstance(ann, dict) and "annotation_json" in ann:
            converted = legacy_annotation_to_dumb_anchor(ann, is_pdf=is_pdf)
            if converted is None:
                # ``legacy_annotation_to_dumb_anchor`` returns None for two
                # distinct cases; report them separately so an operator reading
                # a partial-remap report can tell an intentional structural
                # skip from a genuinely unconvertible annotation.
                reason = (
                    "structural annotation — regenerated by parser"
                    if ann.get("structural")
                    else "unsupported legacy annotation format"
                )
                report.append(
                    {
                        "id": ann.get("id"),
                        "rawText": report_rawtext_preview(ann.get("rawText")),
                        "dropped": True,
                        "reason": reason,
                    }
                )
                continue
            ann = converted
        try:
            built = _anchor_pdf(ann, pawls) if is_pdf else _anchor_text(ann, content)
        except Exception as exc:  # never abort the batch for one annotation
            built = None
            reason = f"error: {exc}"
        else:
            reason = "" if built else "no confident anchor"
        if built:
            out.append(built)
            report.append(
                {
                    "id": ann.get("id"),
                    "rawText": report_rawtext_preview(ann.get("rawText")),
                    "dropped": False,
                    "reason": "",
                }
            )
        else:
            report.append(
                {
                    "id": ann.get("id"),
                    "rawText": report_rawtext_preview(ann.get("rawText")),
                    "dropped": True,
                    "reason": reason,
                }
            )
    return out, report
