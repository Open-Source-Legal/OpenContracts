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


def normalize_answer(text: str) -> str:
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
    case, where it returns 1.0 — matching the SQuAD convention).
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

    Both sides are flattened into sets of character indices; returns
    ``|pred ∩ gold| / |pred ∪ gold|``.  Returns 0.0 when the union is empty
    (i.e. there is literally nothing to compare).  This metric is more
    forgiving than strict span matching because it rewards partial hits.
    """
    pred_chars = _union_of_spans(predicted)
    gold_chars = _union_of_spans(gold)
    if not pred_chars and not gold_chars:
        return 0.0
    intersection = pred_chars & gold_chars
    union = pred_chars | gold_chars
    if not union:
        return 0.0
    return len(intersection) / len(union)


def _union_of_spans(spans: Iterable[Span]) -> set[int]:
    """Return the set of character offsets covered by ``spans``."""
    covered: set[int] = set()
    for start, end in spans:
        if end > start:
            covered.update(range(start, end))
    return covered


# --------------------------------------------------------------------------- #
# Aggregates
# --------------------------------------------------------------------------- #


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
