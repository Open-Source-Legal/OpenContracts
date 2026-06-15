"""Merge detection layers with precedence: registry > grammar > llm.

A higher-precedence candidate suppresses any lower or equal-precedence
candidate whose span overlaps it. Within a single layer, the earlier span (by
start offset) wins an overlap. The Tier-1 (registry) list is always preserved
in full — callers pass it as ``primary``.
"""

from __future__ import annotations

from opencontractserver.enrichment.extractor import Candidate


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


def reconcile(
    primary: list[Candidate], secondary: list[Candidate]
) -> list[Candidate]:
    """Keep all ``primary``; add ``secondary`` candidates that don't overlap a
    kept span. ``secondary`` is processed in document order so the earliest
    span wins an intra-layer overlap."""
    kept: list[Candidate] = list(primary)
    occupied: list[tuple[int, int]] = [(c.start, c.end) for c in primary]
    for cand in sorted(secondary, key=lambda c: (c.start, c.end)):
        span = (cand.start, cand.end)
        if any(_overlaps(span, used) for used in occupied):
            continue
        kept.append(cand)
        occupied.append(span)
    return kept
