"""Framework-agnostic PAWLs token-matching helpers.

Shared by the PDF outline enricher and the post-ingest annotation remap.
PAWLs coordinates use a top-left origin; each token is
``{"x","y","width","height","text"}`` and ``top`` is the minimum ``y``.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from opencontractserver.constants.annotations import (
    PDF_OUTLINE_FIRST_WORD_PREFILTER_RATIO,
)
from opencontractserver.types.dicts import (
    BoundingBoxPythonType,
    PawlsPagePythonType,
    PawlsTokenPythonType,
)


def page_text_tokens(page: PawlsPagePythonType) -> tuple[list[str], list[int]]:
    """Return ``(token_texts, original_indices)`` for a page's non-image,
    non-empty text tokens (image/blank tokens skipped)."""
    token_texts: list[str] = []
    original_indices: list[int] = []
    for idx, tok in enumerate(page.get("tokens", []) or []):
        if tok.get("is_image"):
            continue
        text = (tok.get("text") or "").strip()
        if not text:
            continue
        token_texts.append(text)
        original_indices.append(idx)
    return token_texts, original_indices


def match_title_to_tokens(
    title: str, token_texts: list[str], fuzzy_threshold: float
) -> tuple[int, int] | None:
    """Locate ``title`` among a page's text tokens (whitespace-collapsed,
    case-insensitive). Returns inclusive ``(start, end)`` into ``token_texts``
    or ``None``."""
    title_norm = " ".join(title.casefold().split())
    if not title_norm:
        return None
    first_word = title_norm.split()[0]
    max_len = int(len(title_norm) * 1.5) + 8

    cf = [t.casefold() for t in token_texts]
    n = len(cf)
    best_ratio = 0.0
    best_span: tuple[int, int] | None = None

    for j in range(n):
        if (
            SequenceMatcher(None, cf[j], first_word).ratio()
            < PDF_OUTLINE_FIRST_WORD_PREFILTER_RATIO
        ):
            continue
        candidate = cf[j]
        k = j
        while k < n:
            if k > j:
                candidate = candidate + " " + cf[k]
            if len(candidate) > max_len:
                break
            if candidate == title_norm:
                return (j, k)
            matcher = SequenceMatcher(None, candidate, title_norm)
            if matcher.quick_ratio() >= max(best_ratio, fuzzy_threshold):
                ratio = matcher.ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_span = (j, k)
            k += 1

    if best_span is not None and best_ratio >= fuzzy_threshold:
        return best_span
    return None


def union_bounds(
    tokens: list[PawlsTokenPythonType], indices: list[int]
) -> BoundingBoxPythonType:
    """Union bounding box (top/bottom/left/right) of ``tokens`` at ``indices``."""
    lefts, tops, rights, bottoms = [], [], [], []
    for idx in indices:
        tok = tokens[idx]
        x, y = float(tok["x"]), float(tok["y"])
        w, h = float(tok["width"]), float(tok["height"])
        lefts.append(x)
        tops.append(y)
        rights.append(x + w)
        bottoms.append(y + h)
    return {
        "left": min(lefts),
        "top": min(tops),
        "right": max(rights),
        "bottom": max(bottoms),
    }


def _token_box(tok: PawlsTokenPythonType) -> tuple[float, float, float, float]:
    x, y = float(tok["x"]), float(tok["y"])
    w, h = float(tok["width"]), float(tok["height"])
    return (x, y, x + w, y + h)


def _intersection_area(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def select_tokens_in_region(
    page: PawlsPagePythonType,
    region: BoundingBoxPythonType,
    *,
    overlap_threshold: float,
) -> list[int]:
    """Original indices of the page's text tokens whose intersection with
    ``region`` covers >= ``overlap_threshold`` of the token's own area,
    in page-token order."""
    rbox = (region["left"], region["top"], region["right"], region["bottom"])
    selected: list[int] = []
    for idx, tok in enumerate(page.get("tokens", []) or []):
        if tok.get("is_image"):
            continue
        if not (tok.get("text") or "").strip():
            continue
        tbox = _token_box(tok)
        tarea = (tbox[2] - tbox[0]) * (tbox[3] - tbox[1])
        if tarea <= 0:
            continue
        if _intersection_area(tbox, rbox) / tarea >= overlap_threshold:
            selected.append(idx)
    return selected
