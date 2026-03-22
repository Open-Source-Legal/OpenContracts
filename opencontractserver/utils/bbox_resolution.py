"""
Bounding-box annotation resolution.

Converts bbox_annotations (PDF-point bounding boxes keyed by page) into
standard TOKEN_LABEL annotation dicts by matching against PAWLs tokens.
"""

from __future__ import annotations

import logging

from opencontractserver.types.dicts import (
    BboxAnnotationType,
    BoundingBoxPythonType,
    OpenContractsAnnotationPythonType,
    OpenContractsSinglePageAnnotationType,
    PawlsPagePythonType,
)

logger = logging.getLogger(__name__)


def _token_center(token: dict) -> tuple[float, float]:
    """Compute the center point of a PAWLs token."""
    return (
        token["x"] + token["width"] / 2,
        token["y"] + token["height"] / 2,
    )


def _point_in_rect(cx: float, cy: float, rect: BoundingBoxPythonType) -> bool:
    """Check if a point falls inside a bounding rectangle (inclusive boundaries)."""
    return rect["left"] <= cx <= rect["right"] and rect["top"] <= cy <= rect["bottom"]


def _token_bounding_box(token: dict) -> BoundingBoxPythonType:
    """Convert a PAWLs token to a BoundingBoxPythonType."""
    return {
        "top": token["y"],
        "bottom": token["y"] + token["height"],
        "left": token["x"],
        "right": token["x"] + token["width"],
    }


def _union_bounding_box(
    boxes: list[BoundingBoxPythonType],
) -> BoundingBoxPythonType:
    """Compute the union bounding box of a list of bounding boxes."""
    return {
        "top": min(b["top"] for b in boxes),
        "bottom": max(b["bottom"] for b in boxes),
        "left": min(b["left"] for b in boxes),
        "right": max(b["right"] for b in boxes),
    }


def resolve_bbox_annotations(
    pawls_pages: list[PawlsPagePythonType],
    bbox_annotations: list[BboxAnnotationType],
) -> list[OpenContractsAnnotationPythonType]:
    """
    Resolve bounding-box annotations to TOKEN_LABEL annotations.

    For each bbox annotation, matches PAWLs tokens whose center point falls
    inside any of the annotation's bounding rectangles. Produces standard
    TOKEN_LABEL annotation dicts ready for ``import_doc_annotations``.

    Both input bounding boxes and PAWLs tokens use PDF points (1/72 inch)
    with top-left origin -- no coordinate scaling is needed.

    Args:
        pawls_pages: PAWLs page data (list of page dicts with tokens).
        bbox_annotations: Bounding-box annotation entries to resolve.

    Returns:
        List of resolved ``OpenContractsAnnotationPythonType`` dicts with
        ``annotation_type = "TOKEN_LABEL"``.
    """
    pages_by_index: dict[int, dict] = {}
    for page_data in pawls_pages:
        pages_by_index[page_data["page"]["index"]] = page_data

    resolved: list[OpenContractsAnnotationPythonType] = []

    for bbox_ann in bbox_annotations:
        bounds = bbox_ann.get("bounds", {})
        if not bounds:
            logger.warning(
                "Skipping bbox annotation %s: empty bounds",
                bbox_ann.get("id", "<no id>"),
            )
            continue

        annotation_json: dict[str, OpenContractsSinglePageAnnotationType] = {}
        has_text_tokens = False
        has_image_tokens = False

        for page_str, rects in bounds.items():
            try:
                page_idx = int(page_str)
            except (ValueError, TypeError):
                logger.warning(
                    "Skipping invalid page key %r for bbox annotation %s",
                    page_str,
                    bbox_ann.get("id", "<no id>"),
                )
                continue
            page_data = pages_by_index.get(page_idx)
            if page_data is None:
                logger.warning(
                    "Skipping page %d for bbox annotation %s: "
                    "page index exceeds PAWLs page count (%d)",
                    page_idx,
                    bbox_ann.get("id", "<no id>"),
                    len(pawls_pages),
                )
                continue

            tokens = page_data["tokens"]
            matched_indices: list[int] = []

            for token_idx, token in enumerate(tokens):
                cx, cy = _token_center(token)
                if any(_point_in_rect(cx, cy, rect) for rect in rects):
                    matched_indices.append(token_idx)
                    if token.get("is_image"):
                        has_image_tokens = True
                    else:
                        has_text_tokens = True

            if not matched_indices:
                logger.warning(
                    "No tokens matched on page %d for bbox annotation %s",
                    page_idx,
                    bbox_ann.get("id", "<no id>"),
                )
                continue

            matched_tokens = [tokens[i] for i in matched_indices]
            token_boxes = [_token_bounding_box(t) for t in matched_tokens]

            page_annotation: OpenContractsSinglePageAnnotationType = {
                "bounds": _union_bounding_box(token_boxes),
                "tokensJsons": [
                    {"pageIndex": page_idx, "tokenIndex": i} for i in matched_indices
                ],
                "rawText": " ".join(t["text"] for t in matched_tokens if t.get("text")),
            }
            annotation_json[page_str] = page_annotation

        if not annotation_json:
            logger.warning(
                "Dropping bbox annotation %s: no tokens matched on any page",
                bbox_ann.get("id", "<no id>"),
            )
            continue

        # page field = minimum page number with matched tokens
        min_page = min(int(p) for p in annotation_json)

        # content_modalities
        modalities: list[str] = []
        if has_text_tokens:
            modalities.append("TEXT")
        if has_image_tokens:
            modalities.append("IMAGE")

        # Top-level rawText uses the caller's input (may be a cleaned/canonical
        # form).  Per-page rawText inside annotation_json uses token-derived text
        # for positional accuracy.  This mirrors how OC_SECTION annotations work.
        resolved_ann: OpenContractsAnnotationPythonType = {
            "id": bbox_ann.get("id"),
            "annotationLabel": bbox_ann["annotationLabel"],
            "rawText": bbox_ann["rawText"],
            "page": min_page,
            "annotation_json": annotation_json,
            "parent_id": bbox_ann.get("parent_id"),
            "annotation_type": "TOKEN_LABEL",
            "structural": bbox_ann.get("structural", False),
            "content_modalities": modalities,
        }
        if "long_description" in bbox_ann:
            resolved_ann["long_description"] = bbox_ann["long_description"]

        resolved.append(resolved_ann)

    return resolved


def merge_bbox_into_labelled_text(doc_data: dict) -> None:
    """
    Resolve ``bbox_annotations`` in *doc_data* and merge into ``labelled_text``.

    Modifies *doc_data* in place. No-op if ``bbox_annotations`` is absent or
    empty, or if ``pawls_file_content`` is not available.

    Args:
        doc_data: Document data dict (``OpenContractDocExport``-shaped or
            worker metadata). Must contain ``pawls_file_content`` for
            resolution to proceed.
    """
    bbox_annotations = doc_data.get("bbox_annotations")
    if not bbox_annotations:
        return

    pawls_pages = doc_data.get("pawls_file_content")
    if not pawls_pages:
        logger.warning(
            "bbox_annotations present but no pawls_file_content available -- "
            "skipping bbox resolution"
        )
        return

    resolved = resolve_bbox_annotations(pawls_pages, bbox_annotations)
    if resolved:
        labelled_text = doc_data.get("labelled_text")
        if labelled_text is None:
            doc_data["labelled_text"] = resolved
        else:
            labelled_text.extend(resolved)
