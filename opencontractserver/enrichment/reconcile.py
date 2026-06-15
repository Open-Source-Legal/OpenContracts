"""Merge detection layers with precedence: registry > grammar > llm.

A higher-precedence candidate suppresses a lower or equal-precedence candidate
whose span overlaps it **and that shares its reference_type** — so a registry
SECTION mention can never silence a grammar LAW citation that happens to
overlap it (the dedup we want is registry-LAW over grammar-LAW for the *same*
citation, e.g. ``exchange-act:10(b)`` over ``usc-15:78j(b)``). Within a single
layer, the earlier span (by start offset) wins an overlap. The Tier-1
(registry) list is always preserved in full — callers pass it as ``primary``.
"""

from __future__ import annotations

from opencontractserver.enrichment.extractor import Candidate


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


def reconcile(primary: list[Candidate], secondary: list[Candidate]) -> list[Candidate]:
    """Keep all ``primary``; add ``secondary`` candidates that don't overlap a
    kept span **of the same reference_type**. ``secondary`` is processed in
    document order so the earliest span wins an intra-layer overlap."""
    kept: list[Candidate] = list(primary)
    # (start, end, reference_type) — suppression is scoped to matching types.
    occupied: list[tuple[int, int, str]] = [
        (c.start, c.end, c.reference_type) for c in primary
    ]
    for cand in sorted(secondary, key=lambda c: (c.start, c.end)):
        span = (cand.start, cand.end)
        if any(
            ref_type == cand.reference_type and _overlaps(span, (start, end))
            for start, end, ref_type in occupied
        ):
            continue
        kept.append(cand)
        occupied.append((cand.start, cand.end, cand.reference_type))
    return kept
