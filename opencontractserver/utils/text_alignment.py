"""
Text alignment utility for grounding extracted values to source documents.

Inspired by LangExtract's WordAligner, this module finds extracted text
snippets within a document and returns character intervals. It uses a
three-tier matching strategy:

1. Exact substring match (str.find) — fastest, O(n)
2. Normalized match (collapse whitespace + lowercase) — handles LLM reformatting
3. Fuzzy match via difflib.SequenceMatcher — handles minor paraphrasing

The output is format-agnostic: downstream code converts character intervals
to TOKEN_LABEL (PDF) or SPAN_LABEL (text/DOCX) annotations.
"""

from __future__ import annotations

import dataclasses
import difflib
import logging
import re
import time
from enum import Enum

from opencontractserver.constants.extraction import (
    FUZZY_ANCHOR_MIN_NGRAM_WORDS,
    FUZZY_PER_QUERY_TIMEOUT_SECONDS,
    MAX_DOC_LENGTH_FOR_FUZZY,
    MAX_QUERY_LENGTH_FOR_FUZZY,
)

logger = logging.getLogger(__name__)


class MatchType(str, Enum):
    """How the query text was matched to the document."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    FUZZY = "fuzzy"


@dataclasses.dataclass(frozen=True, slots=True)
class AlignmentResult:
    """A single grounding hit mapping query text to a document position."""

    query_text: str
    """The text we searched for."""

    matched_text: str
    """The actual text slice from the document at [char_start:char_end]."""

    char_start: int
    """Inclusive start index in the document text."""

    char_end: int
    """Exclusive end index in the document text."""

    match_quality: float
    """Similarity ratio in [0.0, 1.0]. 1.0 for exact matches."""

    match_type: MatchType
    """Which tier produced this match."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Collapse whitespace and lowercase for normalized comparison."""
    return _WHITESPACE_RE.sub(" ", text.strip()).lower()


def _build_normalized_index(doc_text: str) -> tuple[str, list[int]]:
    """Build a normalized version of the document text with a position map.

    Returns:
        (normalized_text, char_map) where char_map[i] is the index in the
        original doc_text that corresponds to position i in normalized_text.
    """
    char_map: list[int] = []
    normalized_chars: list[str] = []
    in_whitespace = False

    for orig_idx, ch in enumerate(doc_text):
        if ch in (" ", "\t", "\n", "\r", "\f", "\v"):
            if not in_whitespace and normalized_chars:
                normalized_chars.append(" ")
                char_map.append(orig_idx)
                in_whitespace = True
        else:
            normalized_chars.append(ch.lower())
            char_map.append(orig_idx)
            in_whitespace = False

    return "".join(normalized_chars), char_map


_WORD_RE = re.compile(r"\w+")


def _has_anchor_ngram(
    query: str,
    doc_text: str,
    *,
    n: int = FUZZY_ANCHOR_MIN_NGRAM_WORDS,
    doc_lower: str | None = None,
) -> bool:
    """Cheap pre-filter: does ``query`` share any n consecutive words with
    ``doc_text`` as an exact substring?

    Most queries that ultimately fail fuzzy alignment also fail this anchor
    test (no n-gram of the query appears verbatim in the doc), so we can
    skip the expensive sliding-window scan. Trades a small amount of recall
    on pathological paraphrases for predictable grounding latency.

    ``n=0`` short-circuits to ``True`` (filter disabled).

    ``doc_lower`` lets the caller hoist the lowercase conversion out of a
    per-query loop — at ``MAX_DOC_LENGTH_FOR_FUZZY`` (200 KB) every call
    otherwise allocates a fresh 200 KB string.  When ``None`` (default),
    the function falls back to computing it locally so single-call sites
    don't have to plumb it through.
    """
    if n <= 0:
        return True
    words = _WORD_RE.findall(query.lower())
    if len(words) < n:
        # Query is shorter than the anchor window — fall back to allowing
        # fuzzy. With <n words the short-circuit above is a no-op anyway.
        return True
    # Case-insensitive substring match: paraphrases often shift case
    # (titles, sentence-initial caps) without breaking the underlying
    # anchor.
    if doc_lower is None:
        doc_lower = doc_text.lower()
    for i in range(len(words) - n + 1):
        ngram = " ".join(words[i : i + n])
        if ngram and ngram in doc_lower:
            return True
    return False


def _fuzzy_find(
    query: str,
    doc_text: str,
    threshold: float,
) -> AlignmentResult | None:
    """Slide a window over doc_text and find the best fuzzy match.

    Uses difflib.SequenceMatcher with a window slightly wider than the
    query to allow for insertions/deletions.
    """
    query_len = len(query)
    if query_len == 0 or len(doc_text) == 0:
        return None

    # Window sizes: from 80% to 120% of query length
    min_window = max(1, int(query_len * 0.8))
    max_window = min(len(doc_text), int(query_len * 1.2))

    best_ratio = 0.0
    best_start = -1
    best_end = -1

    # Step size: skip by 1/4 of query length for speed, min 1
    step = max(1, query_len // 4)

    # Wallclock budget so a single pathological query can't pin the
    # grounder. The window-iteration math is bounded in theory, but
    # ``SequenceMatcher.ratio`` with ``autojunk=False`` on highly repetitive
    # legal text occasionally degenerates badly enough to be effectively
    # unbounded in practice.
    deadline = time.monotonic() + FUZZY_PER_QUERY_TIMEOUT_SECONDS
    timed_out = False

    for window_size in range(
        min_window, max_window + 1, max(1, (max_window - min_window) // 3)
    ):
        if time.monotonic() >= deadline:
            timed_out = True
            break
        for start in range(0, len(doc_text) - window_size + 1, step):
            if time.monotonic() >= deadline:
                timed_out = True
                break
            end = start + window_size
            candidate = doc_text[start:end]
            ratio = difflib.SequenceMatcher(
                None, query, candidate, autojunk=False
            ).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                best_start = start
                best_end = end
        if timed_out:
            break

    if timed_out:
        logger.warning(
            "Fuzzy search timed out after %.1fs for query (%d chars); "
            "best ratio so far=%.2f, threshold=%.2f",
            FUZZY_PER_QUERY_TIMEOUT_SECONDS,
            query_len,
            best_ratio,
            threshold,
        )

    if best_ratio < threshold or best_start < 0:
        return None

    # Refine: search char-by-char around best position. Honour the same
    # deadline so the refinement pass can't push us over budget either.
    refine_start = max(0, best_start - step)
    refine_end_limit = min(len(doc_text), best_end + step)

    for window_size in (
        best_end - best_start - 1,
        best_end - best_start,
        best_end - best_start + 1,
    ):
        if time.monotonic() >= deadline:
            break
        if window_size < 1:
            continue
        for start in range(
            refine_start,
            min(refine_end_limit - window_size + 1, refine_start + 2 * step),
        ):
            if time.monotonic() >= deadline:
                break
            end = start + window_size
            candidate = doc_text[start:end]
            ratio = difflib.SequenceMatcher(
                None, query, candidate, autojunk=False
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = start
                best_end = end

    if best_ratio < threshold:
        return None

    return AlignmentResult(
        query_text=query,
        matched_text=doc_text[best_start:best_end],
        char_start=best_start,
        char_end=best_end,
        match_quality=best_ratio,
        match_type=MatchType.FUZZY,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def align_text_to_document(
    query_texts: list[str],
    document_text: str,
    *,
    fuzzy_threshold: float = 0.75,
    enable_fuzzy: bool = True,
    min_query_length: int = 4,
) -> list[AlignmentResult]:
    """Find each query text's best location in the document.

    Tries three strategies in order of preference:
    1. **Exact** — ``str.find()``
    2. **Normalized** — collapse whitespace + lowercase, then find
    3. **Fuzzy** — sliding-window ``difflib.SequenceMatcher``

    Args:
        query_texts: Strings to locate in the document.
        document_text: Full document text to search within.
        fuzzy_threshold: Minimum similarity ratio for fuzzy matches.
        enable_fuzzy: Whether to attempt fuzzy matching (slower).
        min_query_length: Skip queries shorter than this.

    Returns:
        List of :class:`AlignmentResult` for queries that matched.
        Queries with no match are silently omitted.
    """
    if not document_text:
        return []

    results: list[AlignmentResult] = []

    # Pre-build normalized index for tier 2 (amortized across queries)
    norm_doc, char_map = _build_normalized_index(document_text)
    # Hoist the lowercase conversion used by ``_has_anchor_ngram`` out of
    # the per-query loop — at the fuzzy cap (200 KB) the per-call
    # allocation cost dominated the anchor check itself.
    doc_lower_cached: str | None = None

    for query in query_texts:
        if not query or len(query) < min_query_length:
            continue

        # --- Tier 1: Exact match ---
        pos = document_text.find(query)
        if pos != -1:
            results.append(
                AlignmentResult(
                    query_text=query,
                    matched_text=document_text[pos : pos + len(query)],
                    char_start=pos,
                    char_end=pos + len(query),
                    match_quality=1.0,
                    match_type=MatchType.EXACT,
                )
            )
            continue

        # --- Tier 2: Normalized match ---
        norm_query = _normalize(query)
        norm_pos = norm_doc.find(norm_query)
        if norm_pos != -1:
            # Map back to original character positions
            orig_start = char_map[norm_pos]
            norm_end = norm_pos + len(norm_query)
            # Use the *next* char_map entry as the exclusive end to avoid
            # an off-by-one when the match ends on collapsed whitespace.
            if norm_end < len(char_map):
                orig_end = char_map[norm_end]
            else:
                orig_end = len(document_text)
            matched = document_text[orig_start:orig_end]

            results.append(
                AlignmentResult(
                    query_text=query,
                    matched_text=matched,
                    char_start=orig_start,
                    char_end=orig_end,
                    match_quality=difflib.SequenceMatcher(
                        None, query, matched, autojunk=False
                    ).ratio(),
                    match_type=MatchType.NORMALIZED,
                )
            )
            continue

        # --- Tier 3: Fuzzy match ---
        if enable_fuzzy and len(query) >= min_query_length:
            if len(document_text) > MAX_DOC_LENGTH_FOR_FUZZY:
                logger.debug(
                    "Skipping fuzzy match for query %r: document length "
                    "%d exceeds MAX_DOC_LENGTH_FOR_FUZZY (%d)",
                    query[:50],
                    len(document_text),
                    MAX_DOC_LENGTH_FOR_FUZZY,
                )
                continue
            if len(query) > MAX_QUERY_LENGTH_FOR_FUZZY:
                logger.debug(
                    "Skipping fuzzy match: query length %d exceeds "
                    "MAX_QUERY_LENGTH_FOR_FUZZY (%d). Multi-paragraph "
                    "answers rarely produce useful alignments and would "
                    "blow up the sliding-window cost.",
                    len(query),
                    MAX_QUERY_LENGTH_FOR_FUZZY,
                )
                continue
            if doc_lower_cached is None:
                doc_lower_cached = document_text.lower()
            if not _has_anchor_ngram(query, document_text, doc_lower=doc_lower_cached):
                logger.debug(
                    "Skipping fuzzy match: query %r has no exact %d-gram "
                    "anchor in document. Most queries that fail this test "
                    "also fail the sliding-window scan, so skip both.",
                    query[:50],
                    FUZZY_ANCHOR_MIN_NGRAM_WORDS,
                )
                continue
            fuzzy_result = _fuzzy_find(query, document_text, fuzzy_threshold)
            if fuzzy_result is not None:
                results.append(fuzzy_result)

    return results
