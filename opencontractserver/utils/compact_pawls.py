"""
Compact PAWLs v2 format.

Provides encode/decode between the verbose v1 PAWLs format and the compact v2
format, plus a **format-agnostic accessor layer** so consumers never need to
know which format they are reading.

The v2 format reduces storage by:

1. Array-based tokens: ``[x, y, w, h, "text"]`` instead of
   ``{"x": …, "y": …, "width": …, "height": …, "text": …}`` — ~60% saving
   per text token.
2. Shortened page dimension keys: ``w``, ``h`` instead of ``width``, ``height``.
3. Implicit page index: position in the array *is* the page index.
4. Coordinate precision normalization: round floats to 1 decimal place.
5. Separated image metadata: image tokens carry a 6th element (dict) with
   compact keys, keeping the common text-only path lean.

Format spec::

    v1 (legacy):
    [
      {
        "page": {"width": 612.0, "height": 792.0, "index": 0},
        "tokens": [
          {"x": 72.0, "y": 720.0, "width": 41.0, "height": 12.0, "text": "Hello"},
          ...
        ]
      },
      ...
    ]

    v2 (compact):
    {
      "v": 2,
      "p": [
        {
          "w": 612.0,
          "h": 792.0,
          "t": [
            [72.0, 720.0, 41.0, 12.0, "Hello"],
            [0.0, 100.0, 200.0, 300.0, "", {"p": "img.jpg", "f": "jpeg", ...}],
            ...
          ]
        },
        ...
      ]
    }

**Accessor layer** (preferred for all new code)::

    from opencontractserver.utils.compact_pawls import (
        expand_pawls_pages,
        is_compact_pawls_format,
    )

    # Always returns v1 list[PawlsPagePythonType] regardless of input format
    pages = expand_pawls_pages(raw_json)
"""

from __future__ import annotations

import logging
from typing import Any

from opencontractserver.constants.pawls import (
    COMPACT_PAWLS_COORDINATE_PRECISION as PRECISION,
)
from opencontractserver.constants.pawls import (
    COMPACT_PAWLS_MAX_TOKENS_PER_PAGE as MAX_TOKENS_PER_PAGE,
)
from opencontractserver.constants.pawls import (
    COMPACT_PAWLS_VERSION,
)

logger = logging.getLogger(__name__)

# ── Image metadata key mapping (v1 full key → v2 short key) ──

_IMAGE_KEY_MAP: dict[str, str] = {
    "image_path": "p",
    "base64_data": "b64",
    "format": "f",
    "content_hash": "ch",
    "original_width": "ow",
    "original_height": "oh",
    "image_type": "it",
}

_IMAGE_KEY_REVERSE: dict[str, str] = {v: k for k, v in _IMAGE_KEY_MAP.items()}


# ── Format detection ─────────────────────────────────────────────


def is_compact_pawls_format(data: Any) -> bool:
    """Return ``True`` if *data* uses the v2 compact PAWLs layout."""
    return (
        isinstance(data, dict)
        and data.get("v") == COMPACT_PAWLS_VERSION
        and isinstance(data.get("p"), list)
    )


# ── Compact (v1 → v2) ───────────────────────────────────────────


def _round(value: float) -> float:
    """Round a coordinate float to the configured precision."""
    return round(value, PRECISION)


def _compact_token(token: dict[str, Any]) -> list:
    """Convert a single v1 token dict to a compact array.

    Text token: ``[x, y, w, h, "text"]``
    Image token: ``[x, y, w, h, "", {compact_image_meta}]``
    """
    arr: list = [
        _round(float(token.get("x", 0))),
        _round(float(token.get("y", 0))),
        _round(float(token.get("width", 0))),
        _round(float(token.get("height", 0))),
        token.get("text", ""),
    ]

    if token.get("is_image"):
        img_meta: dict[str, Any] = {}
        for v1_key, v2_key in _IMAGE_KEY_MAP.items():
            if v1_key in token and token[v1_key] is not None:
                img_meta[v2_key] = token[v1_key]
        if img_meta:
            arr.append(img_meta)

    return arr


def compact_pawls_pages(
    pages: list[dict[str, Any]] | Any | None,
) -> dict[str, Any] | Any | None:
    """Convert v1 PAWLs pages to v2 compact format.

    Already-compact data is returned unchanged.  ``None`` is returned as-is.

    Args:
        pages: A v1-format list of ``PawlsPagePythonType`` dicts, or
            already-compact v2 data.

    Returns:
        V2 compact PAWLs dict, or ``None`` if input was ``None``.
        Falls back to returning the original v1 data if any page exceeds
        ``MAX_TOKENS_PER_PAGE``.
    """
    if pages is None:
        return None

    # Already compact — pass through
    if is_compact_pawls_format(pages):
        return pages

    if not isinstance(pages, list):
        return pages

    compact_pages: list[dict[str, Any]] = []
    for page_data in pages:
        if not isinstance(page_data, dict):
            continue

        page_info = page_data.get("page", {})
        # Tolerate older fixtures that store ``page`` as a scalar
        # instead of a dict.  We can't recover the width/height in
        # that case, but a zero-sized stub is better than a crash —
        # the export carries the same payload either way and the
        # PDF-burn step is independently fault-tolerant.
        if not isinstance(page_info, dict):
            page_info = {}
        tokens = page_data.get("tokens", [])

        if len(tokens) > MAX_TOKENS_PER_PAGE:
            logger.warning(
                "Page has %d tokens (limit %d) — storing v1 format instead",
                len(tokens),
                MAX_TOKENS_PER_PAGE,
            )
            return pages

        compact_page: dict[str, Any] = {
            "w": _round(float(page_info.get("width", 0))),
            "h": _round(float(page_info.get("height", 0))),
            "t": [_compact_token(tok) for tok in tokens if isinstance(tok, dict)],
        }
        compact_pages.append(compact_page)

    return {"v": COMPACT_PAWLS_VERSION, "p": compact_pages}


# ── Expand (v2 → v1) ────────────────────────────────────────────


def _expand_token(arr: list) -> dict[str, Any] | None:
    """Convert a compact token array back to a v1 token dict.

    Returns ``None`` if the array is malformed.
    """
    if not isinstance(arr, (list, tuple)) or len(arr) < 5:
        return None

    token: dict[str, Any] = {
        "x": float(arr[0]),
        "y": float(arr[1]),
        "width": float(arr[2]),
        "height": float(arr[3]),
        "text": str(arr[4]),
    }

    # 6th element = image metadata
    if len(arr) >= 6 and isinstance(arr[5], dict):
        token["is_image"] = True
        for v2_key, value in arr[5].items():
            v1_key = _IMAGE_KEY_REVERSE.get(v2_key)
            if v1_key:
                token[v1_key] = value

    return token


def expand_pawls_pages(
    data: Any,
) -> list[dict[str, Any]]:
    """Normalize PAWLs data to canonical v1 format (list of page dicts).

    Accepts both v1 and v2 formats.  If already v1, returns as-is.

    Args:
        data: Raw PAWLs JSON — either a v1 list or a v2 compact dict.

    Returns:
        List of ``PawlsPagePythonType`` dicts in v1 format.
        Returns an empty list for ``None`` or unrecognized input.
    """
    if data is None:
        return []

    # Already v1 — pass through
    if isinstance(data, list):
        return data

    if not is_compact_pawls_format(data):
        # Unrecognized format
        if isinstance(data, dict):
            logger.warning(
                "Unrecognized PAWLs format (dict but not v2): %s", type(data)
            )
        return []

    compact_pages = data.get("p", [])
    if not isinstance(compact_pages, list):
        return []

    v1_pages: list[dict[str, Any]] = []
    for page_index, compact_page in enumerate(compact_pages):
        if not isinstance(compact_page, dict):
            continue

        page_info: dict[str, Any] = {
            "width": float(compact_page.get("w", 0)),
            "height": float(compact_page.get("h", 0)),
            "index": page_index,
        }

        compact_tokens = compact_page.get("t", [])
        tokens: list[dict[str, Any]] = []
        for tok_arr in compact_tokens:
            tok = _expand_token(tok_arr)
            if tok is not None:
                tokens.append(tok)

        v1_pages.append({"page": page_info, "tokens": tokens})

    return v1_pages
