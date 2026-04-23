"""Metric helpers for benchmark evaluation.

Two families of metrics are supported:

* **Answer metrics** operate on predicted-vs-gold text strings.  They mirror
  the standard SQuAD evaluation (normalization → tokenization → F1).
* **Retrieval metrics** operate on predicted-vs-gold character-span ranges
  (``[start, end)``).  They mirror the LegalBench-RAG evaluation.

All functions are pure and side-effect free; the evaluator composes them.
"""

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Sequence

Span = tuple[int, int]

# --------------------------------------------------------------------------- #
# Answer metrics (SQuAD-style)
# --------------------------------------------------------------------------- #

_ARTICLE_RE = re.compile(r"\b(a|an|the)\b", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_answer(text: str | None) -> str:
    """Lower-case, strip punctuation/articles, and collapse whitespace.

    This is the canonical SQuAD answer normalizer (Rajpurkar 2016).  Using
    the same recipe makes token F1 / exact match numbers directly
    comparable with the wider RAG literature.
    """
    if text is None:
        return ""
    text = text.lower()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = _ARTICLE_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def exact_match(prediction: str, gold: str) -> float:
    """Return 1.0 iff ``prediction`` and ``gold`` match after normalization."""
    return float(normalize_answer(prediction) == normalize_answer(gold))


def token_f1(prediction: str, gold: str) -> float:
    """SQuAD-style token F1 between ``prediction`` and ``gold``.

    Returns 0.0 when either side is empty (except in the symmetric empty
    case, where it returns 1.0 -- matching the SQuAD convention).

    Note: This differs from :func:`char_iou`, which returns 0.0 when both
    sides are empty.  The asymmetry follows each metric's upstream
    convention (SQuAD for token F1, LegalBench-RAG for span IoU) and is
    intentional.
    """
    pred_tokens = normalize_answer(prediction).split()
    gold_tokens = normalize_answer(gold).split()

    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0

    pred_counts: dict[str, int] = {}
    for tok in pred_tokens:
        pred_counts[tok] = pred_counts.get(tok, 0) + 1

    common = 0
    for tok in gold_tokens:
        if pred_counts.get(tok, 0) > 0:
            common += 1
            pred_counts[tok] -= 1

    if common == 0:
        return 0.0
    precision = common / len(pred_tokens)
    recall = common / len(gold_tokens)
    return (2 * precision * recall) / (precision + recall)


def token_recall(prediction: str, gold: str) -> float:
    """Fraction of gold tokens that appear in the prediction (unique-token set).

    Use this alongside :func:`token_f1` when gold answers are verbatim slices
    from source documents and the LLM tends to wrap its answer with preambles
    or additional explanation.  SQuAD F1 penalises that extra prose heavily
    through its precision term; set-based token recall measures "did the
    model surface the gold content" without caring about extra surrounding
    text.  Defined as ``|unique_gold_tokens ∩ pred_tokens| / |unique_gold_tokens|``
    after normalisation.
    """
    pred_tokens = set(normalize_answer(prediction).split())
    gold_tokens = list(normalize_answer(gold).split())
    if not gold_tokens:
        return 0.0 if pred_tokens else 1.0
    unique_gold = set(gold_tokens)
    if not pred_tokens:
        return 0.0
    return sum(1 for t in unique_gold if t in pred_tokens) / len(unique_gold)


def contains_verbatim_span(
    prediction: str, gold: str, *, min_consecutive_tokens: int = 12
) -> float:
    """1.0 if ``prediction`` contains a verbatim run of ``min_consecutive_tokens``
    gold tokens (after normalisation), else 0.0.

    This is a coarse but pragmatic signal for "did the model quote the
    correct passage" that is robust to preamble / summary wrapping.  The
    default window of 12 tokens is long enough that random overlap is
    negligible for contract/policy text.  Returns 0.0 when the gold answer
    is shorter than ``min_consecutive_tokens`` tokens.
    """
    pred = normalize_answer(prediction)
    gold_tokens = normalize_answer(gold).split()
    if len(gold_tokens) < min_consecutive_tokens or not pred:
        return 0.0
    for start in range(len(gold_tokens) - min_consecutive_tokens + 1):
        window = " ".join(gold_tokens[start : start + min_consecutive_tokens])
        if window in pred:
            return 1.0
    return 0.0


# --------------------------------------------------------------------------- #
# Retrieval metrics (span-overlap)
# --------------------------------------------------------------------------- #


def _overlap_length(a: Span, b: Span) -> int:
    """Length of the intersection of two half-open character spans."""
    start = max(a[0], b[0])
    end = min(a[1], b[1])
    return max(0, end - start)


def _span_length(span: Span) -> int:
    return max(0, span[1] - span[0])


def _overlaps(a: Span, b: Span) -> bool:
    return _overlap_length(a, b) > 0


def overlaps_any(predicted: Iterable[Span], gold: Iterable[Span]) -> bool:
    """Return ``True`` iff any predicted span overlaps any gold span.

    Public helper so callers outside this module (e.g. the runner's
    citation-vs-gold comparison) can share a single definition of "a span
    hit" and stay in sync with the recall / precision / IoU metrics.
    """
    gold_list = list(gold)
    return any(_overlaps(p, g) for p in predicted for g in gold_list)


def gold_spans_covered(
    predicted: Sequence[Span],
    gold: Sequence[Span],
) -> int:
    """Count gold spans that are touched by at least one predicted span."""
    covered = 0
    for g in gold:
        if any(_overlaps(p, g) for p in predicted):
            covered += 1
    return covered


def predicted_spans_matching(
    predicted: Sequence[Span],
    gold: Sequence[Span],
) -> int:
    """Count predicted spans that touch at least one gold span."""
    matched = 0
    for p in predicted:
        if any(_overlaps(p, g) for g in gold):
            matched += 1
    return matched


def recall_at_k(
    predicted: Sequence[Span],
    gold: Sequence[Span],
    k: int,
) -> float:
    """Fraction of gold spans covered by at least one of the top-k predictions.

    ``predicted`` must already be ranked (best first); the function only
    looks at the first ``k`` entries.  Returns 0.0 when ``gold`` is empty —
    a recall question is undefined without gold.
    """
    if not gold:
        return 0.0
    top_k = list(predicted)[: max(0, k)]
    return gold_spans_covered(top_k, gold) / len(gold)


def precision_at_k(
    predicted: Sequence[Span],
    gold: Sequence[Span],
    k: int,
) -> float:
    """Fraction of the top-k predicted spans that touch a gold span.

    Returns 0.0 when k is 0 or predicted has no entries.
    """
    top_k = list(predicted)[: max(0, k)]
    if not top_k:
        return 0.0
    return predicted_spans_matching(top_k, gold) / len(top_k)


def char_iou(
    predicted: Sequence[Span],
    gold: Sequence[Span],
) -> float:
    """Character-level IoU between unioned predicted and gold spans.

    Both sides are merged into non-overlapping intervals, then intersection
    and union lengths are computed in O(n log n) time without materializing
    individual character indices.  Returns 0.0 when the union is empty
    (i.e. there is literally nothing to compare).  This metric is more
    forgiving than strict span matching because it rewards partial hits.

    Note: Unlike :func:`token_f1`, the empty-vs-empty case returns 0.0
    (not 1.0) because IoU is undefined when the union is empty.  See
    :func:`token_f1` for more on this intentional asymmetry.
    """
    pred_merged = _merge_spans(predicted)
    gold_merged = _merge_spans(gold)
    pred_len = _total_span_length(pred_merged)
    gold_len = _total_span_length(gold_merged)
    if pred_len == 0 and gold_len == 0:
        return 0.0
    intersection_len = _intersection_length(pred_merged, gold_merged)
    union_len = pred_len + gold_len - intersection_len
    if union_len == 0:
        return 0.0
    return intersection_len / union_len


def _merge_spans(spans: Iterable[Span]) -> list[Span]:
    """Merge overlapping/adjacent half-open spans into sorted, disjoint intervals."""
    valid = sorted((s, e) for s, e in spans if e > s)
    if not valid:
        return []
    merged: list[Span] = [valid[0]]
    for start, end in valid[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _total_span_length(merged: Sequence[Span]) -> int:
    """Sum of lengths of non-overlapping merged spans."""
    return sum(e - s for s, e in merged)


def _intersection_length(a: Sequence[Span], b: Sequence[Span]) -> int:
    """Total length of the intersection of two sorted, merged span lists."""
    total = 0
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        if start < end:
            total += end - start
        # Advance whichever interval ends first.
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


# --------------------------------------------------------------------------- #
# Aggregates
# --------------------------------------------------------------------------- #


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
