"""
Compact PAWLS & annotation JSON format converters.

This module provides bidirectional conversion between the legacy verbose
format and the new compact format for both PAWLS token data and annotation
JSON.

## Compact PAWLS Format

Legacy per-token (~85 bytes):
    {"x": 523.5, "y": 179.30, "width": 18.0, "height": 12.0, "text": "Code"}

Compact per-token (~35 bytes):
    [523.5, 179.3, 18.0, 12.0, "Code"]

Legacy page:
    {"page": {"width": 612.0, "height": 792.0, "index": 0},
     "tokens": [{...}, ...]}

Compact page:
    {"p": [612.0, 792.0, 0],
     "t": [[x, y, w, h, "text"], ...],
     "im": {"5": {"p": "path", "f": "jpeg", ...}}}   # optional

Image metadata is stored separately in ``"im"`` keyed by token index,
keeping the ``"t"`` array uniform.

## Compact Annotation JSON

Legacy:
    {"0": {"bounds": {"top": 10, "bottom": 20, "left": 5, "right": 50},
           "tokensJsons": [{"pageIndex": 0, "tokenIndex": 3}],
           "rawText": "hello"}}

Compact:
    {"0": {"b": [5, 10, 50, 20], "t": [3], "r": "hello"}}

Bounds array order: [left, top, right, bottom].
Token references are bare indices (pageIndex is always the dict key).

All floats are rounded to 2 decimal places (sub-pixel precision at 72 DPI).
"""

from __future__ import annotations

import math
from typing import Any, Union

from opencontractserver.types.dicts import (
    BoundingBoxPythonType,
    OpenContractsSinglePageAnnotationType,
    PawlsPageBoundaryPythonType,
    PawlsPagePythonType,
    PawlsTokenPythonType,
    TokenIdPythonType,
)

# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

# Positional indices within a compact token array [x, y, w, h, text]
_TX = 0
_TY = 1
_TW = 2
_TH = 3
_TT = 4

# Positional indices within a compact bounds array [left, top, right, bottom]
_BL = 0
_BT = 1
_BR = 2
_BB = 3

# Positional indices within a compact page array [width, height, index]
_PW = 0
_PH = 1
_PI = 2

# Image metadata compact keys
_IM_KEYS = {
    "image_path": "p",
    "format": "f",
    "content_hash": "h",
    "original_width": "ow",
    "original_height": "oh",
    "image_type": "it",
    "base64_data": "d",
}
_IM_KEYS_REVERSE = {v: k for k, v in _IM_KEYS.items()}


# ═══════════════════════════════════════════════════════════════
# Precision helper
# ═══════════════════════════════════════════════════════════════


def _r2(v: float | int) -> float | int:
    """Round a coordinate to 2 decimal places, returning int when exact."""
    rounded = round(v, 2)
    int_val = int(rounded)
    if rounded == int_val:
        return int_val
    return rounded


# ═══════════════════════════════════════════════════════════════
# Format detection
# ═══════════════════════════════════════════════════════════════


def is_compact_pawls(pages: list[Any]) -> bool:
    """Return True if *pages* uses the compact PAWLS format.

    Detection: compact pages have a ``"p"`` key (array) instead of ``"page"``
    (object).
    """
    if not pages:
        return False
    first = pages[0]
    if isinstance(first, dict):
        return "p" in first and "page" not in first
    return False


def is_compact_annotation_json(
    json_data: dict[str | int, Any],
) -> bool:
    """Return True if *json_data* uses the compact annotation JSON format.

    Detection: compact format uses ``"b"`` key instead of ``"bounds"``.
    """
    if not json_data:
        return False
    # Check the first page entry
    for page_data in json_data.values():
        if isinstance(page_data, dict):
            return "b" in page_data and "bounds" not in page_data
    return False


# ═══════════════════════════════════════════════════════════════
# PAWLS conversion: legacy ↔ compact
# ═══════════════════════════════════════════════════════════════


def compact_token(token: PawlsTokenPythonType) -> list[Any]:
    """Convert a single legacy token dict to a compact 5-element array."""
    return [
        _r2(token["x"]),
        _r2(token["y"]),
        _r2(token["width"]),
        _r2(token["height"]),
        token["text"],
    ]


def expand_token(arr: list[Any]) -> PawlsTokenPythonType:
    """Convert a compact 5-element array back to a legacy token dict."""
    return PawlsTokenPythonType(
        x=float(arr[_TX]),
        y=float(arr[_TY]),
        width=float(arr[_TW]),
        height=float(arr[_TH]),
        text=str(arr[_TT]),
    )


def _compact_image_meta(token: PawlsTokenPythonType) -> dict[str, Any]:
    """Extract image metadata from a legacy token into compact form."""
    meta: dict[str, Any] = {}
    for long_key, short_key in _IM_KEYS.items():
        if long_key in token:
            meta[short_key] = token[long_key]  # type: ignore[literal-required]
    return meta


def _expand_image_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Expand compact image metadata back to legacy keys."""
    result: dict[str, Any] = {"is_image": True}
    for short_key, long_key in _IM_KEYS_REVERSE.items():
        if short_key in meta:
            result[long_key] = meta[short_key]
    return result


def compact_page(page: PawlsPagePythonType) -> dict[str, Any]:
    """Convert a single legacy page object to compact format."""
    boundary = page["page"]
    compact: dict[str, Any] = {
        "p": [_r2(boundary["width"]), _r2(boundary["height"]), boundary["index"]],
        "t": [],
    }

    image_meta: dict[str, Any] = {}

    for idx, token in enumerate(page["tokens"]):
        compact["t"].append(compact_token(token))
        if token.get("is_image"):
            meta = _compact_image_meta(token)
            if meta:
                image_meta[str(idx)] = meta

    if image_meta:
        compact["im"] = image_meta

    return compact


def expand_page(compact_pg: dict[str, Any]) -> PawlsPagePythonType:
    """Convert a compact page back to legacy format."""
    p = compact_pg["p"]
    boundary = PawlsPageBoundaryPythonType(
        width=float(p[_PW]),
        height=float(p[_PH]),
        index=int(p[_PI]),
    )

    image_meta: dict[str, Any] = compact_pg.get("im", {})
    tokens: list[PawlsTokenPythonType] = []

    for idx, arr in enumerate(compact_pg["t"]):
        token = expand_token(arr)
        idx_str = str(idx)
        if idx_str in image_meta:
            expanded_meta = _expand_image_meta(image_meta[idx_str])
            token.update(expanded_meta)  # type: ignore[typeddict-item]
        tokens.append(token)

    return PawlsPagePythonType(page=boundary, tokens=tokens)


def compact_pawls(pages: list[PawlsPagePythonType]) -> list[dict[str, Any]]:
    """Convert a full legacy PAWLS document to compact format."""
    return [compact_page(p) for p in pages]


def expand_pawls(compact_pages: list[dict[str, Any]]) -> list[PawlsPagePythonType]:
    """Convert a full compact PAWLS document back to legacy format."""
    return [expand_page(p) for p in compact_pages]


def normalize_pawls(
    pages: list[Any],
) -> list[PawlsPagePythonType]:
    """Accept either format and always return legacy (expanded) format.

    This is the primary entry point for code that reads PAWLS data and needs
    the standard in-memory representation regardless of storage format.
    """
    if not pages:
        return []
    if is_compact_pawls(pages):
        return expand_pawls(pages)
    return pages


def to_compact_pawls(pages: list[Any]) -> list[dict[str, Any]]:
    """Accept either format and always return compact format.

    This is the primary entry point for code that writes PAWLS data and
    wants the smallest possible serialization.
    """
    if not pages:
        return []
    if is_compact_pawls(pages):
        return pages
    return compact_pawls(pages)


# ═══════════════════════════════════════════════════════════════
# Annotation JSON conversion: legacy ↔ compact
# ═══════════════════════════════════════════════════════════════

# Type alias for the multipage annotation dict
MultipageAnnotationDict = dict[
    Union[int, str], OpenContractsSinglePageAnnotationType
]


def compact_single_page_annotation(
    page_index: int | str,
    annotation: OpenContractsSinglePageAnnotationType,
) -> dict[str, Any]:
    """Convert a single-page legacy annotation to compact format."""
    bounds = annotation["bounds"]
    tokens = annotation["tokensJsons"]

    return {
        "b": [
            _r2(bounds["left"]),
            _r2(bounds["top"]),
            _r2(bounds["right"]),
            _r2(bounds["bottom"]),
        ],
        "t": [t["tokenIndex"] for t in tokens],
        "r": annotation["rawText"],
    }


def expand_single_page_annotation(
    page_index: int | str,
    compact_ann: dict[str, Any],
) -> OpenContractsSinglePageAnnotationType:
    """Convert a compact single-page annotation back to legacy format."""
    b = compact_ann["b"]
    page_idx = int(page_index)

    return OpenContractsSinglePageAnnotationType(
        bounds=BoundingBoxPythonType(
            left=b[_BL],
            top=b[_BT],
            right=b[_BR],
            bottom=b[_BB],
        ),
        tokensJsons=[
            TokenIdPythonType(pageIndex=page_idx, tokenIndex=idx)
            for idx in compact_ann["t"]
        ],
        rawText=compact_ann["r"],
    )


def compact_annotation_json(
    json_data: dict[str | int, Any],
) -> dict[str, Any]:
    """Convert a full multipage annotation JSON to compact format."""
    if not json_data:
        return {}
    result: dict[str, Any] = {}
    for page_key, page_data in json_data.items():
        result[str(page_key)] = compact_single_page_annotation(
            page_key, page_data
        )
    return result


def expand_annotation_json(
    compact_data: dict[str | int, Any],
) -> dict[str, OpenContractsSinglePageAnnotationType]:
    """Convert a compact multipage annotation JSON back to legacy format."""
    if not compact_data:
        return {}
    result: dict[str, OpenContractsSinglePageAnnotationType] = {}
    for page_key, page_data in compact_data.items():
        result[str(page_key)] = expand_single_page_annotation(
            page_key, page_data
        )
    return result


def normalize_annotation_json(
    json_data: dict[str | int, Any] | None,
) -> dict[str, OpenContractsSinglePageAnnotationType] | None:
    """Accept either format and return legacy (expanded) format.

    Returns None if input is None. Returns empty dict if input is empty.
    This is the primary entry point for code that reads annotation JSON.
    """
    if json_data is None:
        return None
    if not json_data:
        return {}
    if is_compact_annotation_json(json_data):
        return expand_annotation_json(json_data)
    # Already legacy format - normalize keys to str
    result: dict[str, OpenContractsSinglePageAnnotationType] = {}
    for k, v in json_data.items():
        result[str(k)] = v
    return result


def to_compact_annotation_json(
    json_data: dict[str | int, Any] | None,
) -> dict[str, Any] | None:
    """Accept either format and return compact format.

    Returns None if input is None. This is the primary entry point for code
    that writes annotation JSON.
    """
    if json_data is None:
        return None
    if not json_data:
        return {}
    if is_compact_annotation_json(json_data):
        return dict(json_data)
    return compact_annotation_json(json_data)


# ═══════════════════════════════════════════════════════════════
# Utility: compact bounding box helpers
# ═══════════════════════════════════════════════════════════════


def compact_bounding_box(bbox: BoundingBoxPythonType) -> list[float | int]:
    """Convert a legacy bounding box dict to compact [left, top, right, bottom]."""
    return [
        _r2(bbox["left"]),
        _r2(bbox["top"]),
        _r2(bbox["right"]),
        _r2(bbox["bottom"]),
    ]


def expand_bounding_box(arr: list[float | int]) -> BoundingBoxPythonType:
    """Convert a compact bounding box array back to legacy dict."""
    return BoundingBoxPythonType(
        left=arr[_BL],
        top=arr[_BT],
        right=arr[_BR],
        bottom=arr[_BB],
    )


def is_compact_bounding_box(bbox: Any) -> bool:
    """Return True if *bbox* is a compact bounding box (list/tuple of 4 numbers)."""
    return isinstance(bbox, (list, tuple)) and len(bbox) == 4


def normalize_bounding_box(
    bbox: Any,
) -> BoundingBoxPythonType:
    """Accept either format and return legacy bounding box dict."""
    if is_compact_bounding_box(bbox):
        return expand_bounding_box(bbox)
    return bbox


# ═══════════════════════════════════════════════════════════════
# Utility: compact tokens_jsons (standalone TokenId lists)
# ═══════════════════════════════════════════════════════════════


def compact_tokens_jsons(
    tokens: list[TokenIdPythonType],
) -> list[list[int]]:
    """Convert a list of legacy TokenId dicts to compact [pageIndex, tokenIndex] arrays."""
    return [[t["pageIndex"], t["tokenIndex"]] for t in tokens]


def expand_tokens_jsons(
    compact_tokens: list[list[int]],
) -> list[TokenIdPythonType]:
    """Convert compact [pageIndex, tokenIndex] arrays back to legacy TokenId dicts."""
    return [
        TokenIdPythonType(pageIndex=t[0], tokenIndex=t[1])
        for t in compact_tokens
    ]


def is_compact_tokens_jsons(tokens: list[Any]) -> bool:
    """Return True if *tokens* uses compact format (list of 2-element arrays)."""
    if not tokens:
        return False
    first = tokens[0]
    return isinstance(first, (list, tuple))


def normalize_tokens_jsons(
    tokens: list[Any],
) -> list[TokenIdPythonType]:
    """Accept either format and return legacy TokenId dicts."""
    if not tokens:
        return []
    if is_compact_tokens_jsons(tokens):
        return expand_tokens_jsons(tokens)
    return tokens


def to_compact_tokens_jsons(
    tokens: list[Any],
) -> list[list[int]]:
    """Accept either format and return compact [pageIndex, tokenIndex] arrays."""
    if not tokens:
        return []
    if is_compact_tokens_jsons(tokens):
        return tokens
    return compact_tokens_jsons(tokens)
