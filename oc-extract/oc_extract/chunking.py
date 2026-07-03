"""Paragraph-aware chunking with exact char offsets.

Chunks play the role OpenContracts' structural annotations play in the
production retrieval index: addressable spans that the search tool returns
and that citations point back to.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from .constants import CHUNK_MAX_CHARS

_PARAGRAPH_RE = re.compile(r"\n\s*\n")


@dataclass
class Chunk:
    """An addressable span of the document text."""

    id: int
    start: int
    end: int
    text: str
    page: int | None = None


def page_for_offset(page_offsets: list[int] | None, offset: int) -> int | None:
    """1-based page number containing *offset*, if page offsets are known."""
    if not page_offsets:
        return None
    return bisect.bisect_right(page_offsets, offset)


def chunk_text(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
    page_offsets: list[int] | None = None,
) -> list[Chunk]:
    """Split *text* into chunks of at most *max_chars*, on paragraph
    boundaries where possible, preserving exact source offsets."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _PARAGRAPH_RE.finditer(text):
        if match.start() > cursor:
            spans.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text)))

    # Merge small paragraphs into windows; hard-split oversized ones.
    merged: list[tuple[int, int]] = []
    win_start: int | None = None
    win_end = 0
    for start, end in spans:
        if end - start > max_chars:
            if win_start is not None:
                merged.append((win_start, win_end))
                win_start = None
            pos = start
            while pos < end:
                merged.append((pos, min(pos + max_chars, end)))
                pos += max_chars
            continue
        if win_start is None:
            win_start, win_end = start, end
        elif end - win_start <= max_chars:
            win_end = end
        else:
            merged.append((win_start, win_end))
            win_start, win_end = start, end
    if win_start is not None:
        merged.append((win_start, win_end))

    return [
        Chunk(
            id=i,
            start=start,
            end=end,
            text=text[start:end],
            page=page_for_offset(page_offsets, start),
        )
        for i, (start, end) in enumerate(merged)
        if text[start:end].strip()
    ]
