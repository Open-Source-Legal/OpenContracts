"""
Canonical v2 PAWLs load / convert plumbing.

This module is the **single import boundary** through which raw PAWLs data
enters OpenContracts at runtime.

v1 PAWLs is accepted ONLY here at the load boundary. All downstream consumers
MUST work on the v2 dict shape (or via :class:`PageView` / :class:`TokenView`
read-views). v1 shape appearing in active runtime code paths is a bug.

Two responsibilities:

1. **Format normalization** — :func:`to_canonical_v2` accepts either v1 (list)
   or v2 (dict with ``"v": 2``) PAWLs JSON and returns a v2 dict. Idempotent.
2. **I/O** — :func:`load_canonical_v2` reads from a Django ``FieldFile``,
   open file-like, ``str``/``Path``, or already-decoded JSON, and runs the
   result through :func:`to_canonical_v2`.

Read views (:class:`TokenView`, :class:`PageView`, :func:`iter_pages`) provide
zero-copy attribute access over the positional v2 token rows so consumers
never need to remember the ``[x, y, w, h, text, image_meta?]`` index layout.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Iterator
from typing import Any

from opencontractserver.constants.pawls import COMPACT_PAWLS_VERSION
from opencontractserver.utils.compact_pawls import (
    _IMAGE_KEY_REVERSE,
    compact_pawls_pages,
)
from opencontractserver.utils.compact_pawls import (
    expand_pawls_pages as _expand_pawls_pages,
)
from opencontractserver.utils.compact_pawls import (
    is_compact_pawls_format,
)

logger = logging.getLogger(__name__)


# ── Format normalization ─────────────────────────────────────────


def to_canonical_v2(raw: Any) -> dict[str, Any]:
    """Normalize raw PAWLs JSON to canonical v2 dict shape.

    Accepts:
      * v1 PAWLs (a ``list`` of page dicts) — converted via
        :func:`compact_pawls_pages`.
      * v2 PAWLs (a ``dict`` with ``"v": 2`` and ``"p": [...]``) — returned
        as-is after a shallow shape validation.

    Idempotent: ``to_canonical_v2(to_canonical_v2(x)) == to_canonical_v2(x)``.

    Args:
        raw: Raw PAWLs payload — either a v1 list or a v2 dict.

    Returns:
        A v2 PAWLs dict (``CompactPawlsV2Type``).

    Raises:
        ValueError: If *raw* is not a recognizable PAWLs payload, or if a
            v2-shaped dict fails structural validation.
    """
    if raw is None:
        raise ValueError("Unrecognized PAWLS format: got None")

    # v2 path — validate shape and return as-is.
    if isinstance(raw, dict):
        if not is_compact_pawls_format(raw):
            raise ValueError(
                "Unrecognized PAWLS format: dict but not v2 (missing 'v'==2 "
                f"or 'p': list); keys={list(raw.keys())[:8]}"
            )
        pages = raw.get("p")
        if not isinstance(pages, list):
            raise ValueError("Malformed v2 PAWLS: 'p' must be a list")
        for i, page in enumerate(pages):
            if not isinstance(page, dict):
                raise ValueError(f"Malformed v2 PAWLS: page index {i} is not a dict")
            if "t" in page and not isinstance(page["t"], list):
                raise ValueError(f"Malformed v2 PAWLS: page {i}'s 't' must be a list")
        return raw

    # v1 path — convert through the existing encoder.
    if isinstance(raw, list):
        # `compact_pawls_pages` may fall back to v1 if a page exceeds
        # MAX_TOKENS_PER_PAGE. In that case it returns the list unchanged,
        # which is NOT canonical v2. Flag explicitly so callers don't get a
        # silent v1 leak past this boundary.
        result = compact_pawls_pages(raw)
        if not is_compact_pawls_format(result):
            raise ValueError(
                "Unable to compact v1 PAWLS to v2 (likely exceeds "
                "MAX_TOKENS_PER_PAGE); refusing to leak v1 past load boundary"
            )
        assert isinstance(result, dict)
        return result

    raise ValueError(
        f"Unrecognized PAWLS format: expected list (v1) or dict (v2), "
        f"got {type(raw).__name__}"
    )


# ── I/O entry point ──────────────────────────────────────────────


def _read_text_from_source(source: Any) -> str:
    """Read JSON text from a variety of source flavors.

    Supports:
      * Django ``FieldFile`` (or anything with ``.open()`` + ``.read()``)
      * Plain open file-like (with ``.read()``)
      * ``str`` / ``os.PathLike`` filesystem path
    """
    # Filesystem path (str or PathLike, but NOT a JSON-string).
    # We treat str inputs as paths only if they look like a real filesystem
    # path; raw JSON strings should be json.loads'd by the caller. Since the
    # public API does not document accepting raw JSON strings, str is treated
    # purely as a path here.
    if isinstance(source, (str, os.PathLike)):
        with open(source, encoding="utf-8") as fh:
            return fh.read()

    # Django FieldFile-style objects: prefer .open() to ensure correct mode,
    # but fall back to a direct .read() if .open() is unavailable.
    opener = getattr(source, "open", None)
    if callable(opener):
        # Django FieldFile.open() returns the file (and is idempotent enough
        # for our purposes). Use a try/finally to close when we own opening.
        was_closed = getattr(source, "closed", True)
        if was_closed:
            opener("rb")
        try:
            data = source.read()
        finally:
            if was_closed:
                close = getattr(source, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:  # pragma: no cover - defensive
                        logger.debug("Failed to close PAWLs source", exc_info=True)
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return data

    read = getattr(source, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return data

    raise TypeError(
        f"Unsupported PAWLs source: {type(source).__name__}; expected "
        "FieldFile, file-like, str/Path, or pre-decoded JSON"
    )


def load_canonical_v2(
    file_or_path: str | os.PathLike[str] | Any,
) -> dict[str, Any]:
    """Load PAWLs JSON from any supported source and return canonical v2.

    Accepts:
      * Django ``FieldFile`` (e.g. ``document.pawls_parse_file``)
      * Open file-like (``BytesIO``, ``StringIO``, file handle)
      * ``str`` / ``Path`` filesystem path
      * Pre-decoded JSON (``list`` or ``dict``) — passed straight through
        :func:`to_canonical_v2`

    Args:
        file_or_path: Source of PAWLs data.

    Returns:
        Canonical v2 PAWLs dict.

    Raises:
        ValueError: If the loaded payload is not a recognizable PAWLs format.
        TypeError: If *file_or_path* isn't a supported source type.
    """
    # Pre-decoded JSON shortcut — list or dict goes straight through.
    if isinstance(file_or_path, (list, dict)):
        return to_canonical_v2(file_or_path)

    text = _read_text_from_source(file_or_path)
    if not text:
        raise ValueError("Empty PAWLs payload")
    decoded = json.loads(text)
    return to_canonical_v2(decoded)


# ── Read-views (zero-copy attribute access over v2 rows) ─────────


class TokenView:
    """Lightweight read-view over a v2 token row.

    A v2 token is a ``list`` with the positional contract::

        [x, y, width, height, text, image_meta?]

    where ``image_meta`` (a ``dict`` with v2 short keys) is present iff the
    token represents an image. This view exposes named properties without
    copying any data — the underlying list is referenced directly.
    """

    __slots__ = ("_row",)

    def __init__(self, row: list) -> None:
        self._row = row

    @property
    def x(self) -> float:
        return float(self._row[0])

    @property
    def y(self) -> float:
        return float(self._row[1])

    @property
    def width(self) -> float:
        return float(self._row[2])

    @property
    def height(self) -> float:
        return float(self._row[3])

    @property
    def text(self) -> str:
        return str(self._row[4])

    @property
    def is_image(self) -> bool:
        """``True`` iff a 6th-element image-metadata dict is present."""
        return len(self._row) >= 6 and isinstance(self._row[5], dict)

    @property
    def image_meta(self) -> dict[str, Any] | None:
        """Image metadata in v2 short-key form, or ``None`` for text tokens.

        Returns the dict by reference (no copy). Keys are the v2 short keys
        (``p``, ``b64``, ``f``, ``ch``, ``ow``, ``oh``, ``it``).
        """
        if self.is_image:
            return self._row[5]
        return None

    @property
    def image_meta_v1(self) -> dict[str, Any] | None:
        """Image metadata translated back to v1 long keys, or ``None``.

        Convenience for downstream code that still expects v1-style keys
        (``image_path``, ``content_hash``, …). Returns a fresh dict.
        """
        meta = self.image_meta
        if meta is None:
            return None
        return {_IMAGE_KEY_REVERSE.get(k, k): v for k, v in meta.items()}

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        kind = "image" if self.is_image else "text"
        return (
            f"TokenView({kind} x={self.x} y={self.y} "
            f"w={self.width} h={self.height} text={self.text!r})"
        )


class PageView:
    """Lightweight read-view over a v2 page dict.

    Wraps ``{"w": float, "h": float, "t": list[token_row]}`` with named
    accessors and a ``tokens`` iterator yielding :class:`TokenView` instances.
    """

    __slots__ = ("_page", "_index")

    def __init__(self, page: dict[str, Any], index: int) -> None:
        self._page = page
        self._index = index

    @property
    def index(self) -> int:
        """0-based page index (position in ``pawls['p']``)."""
        return self._index

    @property
    def width(self) -> float:
        return float(self._page.get("w", 0))

    @property
    def height(self) -> float:
        return float(self._page.get("h", 0))

    @property
    def tokens(self) -> Iterator[TokenView]:
        """Iterate :class:`TokenView` instances in token-array order."""
        for row in self._page.get("t", []):
            if isinstance(row, list):
                yield TokenView(row)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"PageView(index={self._index} w={self.width} h={self.height} "
            f"n_tokens={len(self._page.get('t', []))})"
        )


def iter_pages(canonical_v2: dict[str, Any]) -> Iterable[PageView]:
    """Yield :class:`PageView` for each page in a canonical v2 dict.

    Args:
        canonical_v2: A v2 dict (must have ``"v": COMPACT_PAWLS_VERSION``
            and a list under ``"p"``). Use :func:`to_canonical_v2` to
            normalize first if you don't already have v2 in hand.

    Yields:
        :class:`PageView` instances in page-index order.

    Raises:
        ValueError: If *canonical_v2* isn't a valid v2 dict.
    """
    if not is_compact_pawls_format(canonical_v2):
        raise ValueError(
            "iter_pages requires canonical v2 PAWLs; got "
            f"{type(canonical_v2).__name__}"
        )
    if canonical_v2.get("v") != COMPACT_PAWLS_VERSION:
        raise ValueError(
            f"Unsupported PAWLs version: {canonical_v2.get('v')!r} "
            f"(expected {COMPACT_PAWLS_VERSION})"
        )
    for i, page in enumerate(canonical_v2.get("p", [])):
        if isinstance(page, dict):
            yield PageView(page, i)


# ── Boundary-only v2 → v1 adaptor ────────────────────────────────


def to_v1_pages(canonical_v2: Any) -> list[dict[str, Any]]:
    """Convert canonical v2 PAWLs back to the v1 page list shape.

    **Reserved for external/legacy boundaries.** The two allowed uses are:

    1. Hand-off to ``plasmapdf.build_translation_layer``, which still
       consumes v1 ``PawlsPagePythonType`` lists.
    2. Building v1 wire-format export payloads
       (``OpenContractDocExport.pawls_file_content``,
       ``StructuralAnnotationSetExport.pawls_file_content``).

    Active runtime code MUST NOT use this function — operate on the
    canonical v2 dict (or :class:`PageView` / :class:`TokenView` views)
    instead. v1 in-memory shape is a bug everywhere outside these two
    documented boundaries.

    Accepts pre-decoded v2 dicts. If you have raw input that may be v1
    or v2, run it through :func:`to_canonical_v2` first.

    Args:
        canonical_v2: A canonical v2 PAWLs dict (or already a v1 list,
            which is returned as-is for caller convenience).

    Returns:
        v1 ``list[PawlsPagePythonType]`` shape.
    """
    return _expand_pawls_pages(canonical_v2)


__all__ = [
    "PageView",
    "TokenView",
    "iter_pages",
    "load_canonical_v2",
    "to_canonical_v2",
    "to_v1_pages",
]
