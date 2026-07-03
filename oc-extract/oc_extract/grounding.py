"""Ground extracted values back to source-document spans.

Port of the alignment core of
``opencontractserver/utils/extraction_grounding.py``: after the LLM returns a
typed value, every groundable string in it is aligned to the document text
(exact → case-insensitive → whitespace-normalized → bounded fuzzy) so each
answer carries verifiable character-offset citations.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from .constants import (
    FUZZY_THRESHOLD,
    MAX_DOC_LENGTH_FOR_FUZZY,
    MAX_GROUNDABLE_STRINGS,
    MAX_QUERY_LENGTH_FOR_FUZZY,
    MIN_GROUNDABLE_LENGTH,
)


@dataclass
class GroundedSpan:
    start: int
    end: int
    text: str
    method: str  # "exact" | "case_insensitive" | "normalized" | "fuzzy"
    score: float


def collect_groundable_strings(value: Any) -> list[str]:
    """Walk an extraction result and collect strings worth grounding."""
    found: list[str] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if len(found) >= MAX_GROUNDABLE_STRINGS:
            return
        if isinstance(node, str):
            stripped = node.strip()
            if len(stripped) >= MIN_GROUNDABLE_LENGTH and stripped not in seen:
                seen.add(stripped)
                found.append(stripped)
        elif isinstance(node, dict):
            for child in node.values():
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(value)
    return found


def _normalized_pattern(query: str) -> re.Pattern | None:
    """Whitespace-tolerant regex for *query* (words joined by ``\\s+``)."""
    words = query.split()
    if not words:
        return None
    return re.compile(
        r"\s+".join(re.escape(word) for word in words), re.IGNORECASE | re.DOTALL
    )


def _fuzzy_align(doc_text: str, query: str) -> GroundedSpan | None:
    """Bounded fuzzy alignment via difflib matching blocks.

    The longest common block anchors the candidate location; nearby blocks
    (within one query-length of the anchor) contribute to the match ratio so
    a single differing word mid-phrase doesn't sink the alignment.
    """
    if (
        len(doc_text) > MAX_DOC_LENGTH_FOR_FUZZY
        or len(query) > MAX_QUERY_LENGTH_FOR_FUZZY
    ):
        return None
    # autojunk must be OFF: on long documents it silently junks frequent
    # characters and destroys the block matching (the size caps above are
    # the cost guard instead).
    matcher = difflib.SequenceMatcher(
        None, query.casefold(), doc_text.casefold(), autojunk=False
    )
    blocks = [b for b in matcher.get_matching_blocks() if b.size > 0]
    if not blocks:
        return None
    anchor = max(blocks, key=lambda b: b.size)
    window = len(query)
    local = [b for b in blocks if abs(b.b - anchor.b) <= 2 * window]
    matched = sum(b.size for b in local)
    ratio = matched / len(query)
    if ratio < FUZZY_THRESHOLD:
        return None
    start = min(b.b for b in local)
    end = max(b.b + b.size for b in local)
    return GroundedSpan(
        start=start,
        end=end,
        text=doc_text[start:end],
        method="fuzzy",
        score=round(min(ratio, 1.0), 3),
    )


def align_string(
    doc_text: str, query: str, *, enable_fuzzy: bool = True
) -> GroundedSpan | None:
    """Locate *query* in *doc_text*, trying cheap strategies first."""
    idx = doc_text.find(query)
    if idx != -1:
        return GroundedSpan(idx, idx + len(query), query, "exact", 1.0)

    idx = doc_text.casefold().find(query.casefold())
    if idx != -1:
        span_text = doc_text[idx : idx + len(query)]
        return GroundedSpan(idx, idx + len(query), span_text, "case_insensitive", 1.0)

    pattern = _normalized_pattern(query)
    if pattern is not None:
        match = pattern.search(doc_text)
        if match:
            return GroundedSpan(
                match.start(), match.end(), match.group(0), "normalized", 1.0
            )

    if enable_fuzzy:
        return _fuzzy_align(doc_text, query)
    return None


def ground_value(
    doc_text: str, value: Any, *, enable_fuzzy: bool = True
) -> list[GroundedSpan]:
    """Ground every groundable string in *value* against *doc_text*."""
    spans: list[GroundedSpan] = []
    covered: set[tuple[int, int]] = set()
    for candidate in collect_groundable_strings(value):
        span = align_string(doc_text, candidate, enable_fuzzy=enable_fuzzy)
        if span and (span.start, span.end) not in covered:
            covered.add((span.start, span.end))
            spans.append(span)
    return spans
