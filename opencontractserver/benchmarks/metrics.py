"""Metric helpers for benchmark evaluation.

Two families of metrics are supported:

* **Answer metrics** operate on predicted-vs-gold text strings.  They mirror
  the standard SQuAD evaluation (normalization → tokenization → F1).
* **Retrieval metrics** operate on predicted-vs-gold character-span ranges
  (``[start, end)``).  They mirror the LegalBench-RAG evaluation.

All functions are pure and side-effect free; the evaluator composes them.
"""

from __future__ import annotations

import logging
import re
import string
from collections.abc import Iterable, Sequence

logger = logging.getLogger(__name__)

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
        # Empty gold is almost always a data-quality bug; treating
        # ``token_recall("", "")`` as 1.0 silently inflates aggregate
        # F1.  Mirror :func:`char_recall` and return 0.0 with a warning
        # so the operator sees the offending row.
        logger.warning(
            "token_recall called with empty gold; returning 0.0. "
            "This usually indicates a data-quality issue in the dataset."
        )
        return 0.0
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


def char_recall(
    predicted: Sequence[Span],
    gold: Sequence[Span],
) -> float:
    """Fraction of gold **characters** covered by predicted spans.

    Mirrors LegalBench-RAG's per-query recall
    (``legalbenchrag/run_benchmark.py`` lines 38-54) exactly::

        recall = chars(predicted ∩ gold) / chars(gold)

    Both sides are merged into non-overlapping intervals first so
    overlapping retrievals aren't double-counted.  Returns 0.0 when
    ``gold`` is empty — a recall question is undefined without gold,
    and 0.0 (rather than 1.0) avoids inflating aggregate numbers on
    adapter bugs that drop gold spans.
    """
    gold_merged = _merge_spans(gold)
    gold_len = _total_span_length(gold_merged)
    if gold_len == 0:
        return 0.0
    pred_merged = _merge_spans(predicted)
    return _intersection_length(pred_merged, gold_merged) / gold_len


def char_precision(
    predicted: Sequence[Span],
    gold: Sequence[Span],
) -> float:
    """Fraction of predicted **characters** that hit a gold span.

    Mirrors LegalBench-RAG's per-query precision
    (``legalbenchrag/run_benchmark.py`` lines 20-36)::

        precision = chars(predicted ∩ gold) / chars(predicted)

    Returns 0.0 when nothing was predicted — "precision of nothing"
    is undefined, and 0.0 keeps the metric honest when a probe silently
    returns an empty list.
    """
    pred_merged = _merge_spans(predicted)
    pred_len = _total_span_length(pred_merged)
    if pred_len == 0:
        return 0.0
    gold_merged = _merge_spans(gold)
    return _intersection_length(pred_merged, gold_merged) / pred_len


def char_precision_cross_doc(
    predicted_spans: Sequence[Span],
    predicted_doc_ids: Sequence[int | None],
    target_doc_id: int,
    gold: Sequence[Span],
) -> float:
    """LegalBench-RAG precision when retrieval may return spans from
    multiple documents.

    Mirrors ``legalbenchrag/run_benchmark.py`` lines 20-36 exactly: the
    precision DENOMINATOR is the total chars across every retrieved span
    (summed as-is, no merging — matching their loop), and the NUMERATOR
    counts only the chars that intersect a gold span *in the same
    document as the gold* (LB-RAG's ``file_path`` equality check).

    Spans from non-target documents contribute to the denominator
    (they're "retrieved noise") but not the numerator, which is the
    honest way to report the cost of retrieving the wrong document.
    """
    if len(predicted_spans) != len(predicted_doc_ids):
        raise ValueError("predicted_spans and predicted_doc_ids must be parallel")
    total_retrieved_len = sum(e - s for s, e in predicted_spans)
    if total_retrieved_len == 0:
        return 0.0
    same_doc_spans = [
        sp
        for sp, did in zip(predicted_spans, predicted_doc_ids)
        if did == target_doc_id
    ]
    gold_merged = _merge_spans(gold)
    pred_merged = _merge_spans(same_doc_spans)
    intersection = _intersection_length(pred_merged, gold_merged)
    return intersection / total_retrieved_len


def char_recall_cross_doc(
    predicted_spans: Sequence[Span],
    predicted_doc_ids: Sequence[int | None],
    target_doc_id: int,
    gold: Sequence[Span],
) -> float:
    """LegalBench-RAG recall when retrieval may return spans from
    multiple documents.

    Only retrieved spans from ``target_doc_id`` contribute to the
    intersection; denominator is total gold chars.  Equivalent to
    :func:`char_recall` applied to the subset of retrieved spans whose
    document matches the gold's target document.
    """
    if len(predicted_spans) != len(predicted_doc_ids):
        raise ValueError("predicted_spans and predicted_doc_ids must be parallel")
    same_doc_spans = [
        sp
        for sp, did in zip(predicted_spans, predicted_doc_ids)
        if did == target_doc_id
    ]
    return char_recall(same_doc_spans, gold)


# --------------------------------------------------------------------------- #
# Paper-faithful (UPSTREAM-EXACT) variants
# --------------------------------------------------------------------------- #
#
# These mirror ``legalbenchrag/run_benchmark.py`` (commit master, lines
# 16-53) byte-for-byte: per-pair overlap accumulation, NO merging of
# predicted spans, file_path equality enforced via the parallel
# document-id list. The merged variants above (``char_recall`` /
# ``char_precision``) are mathematically more sensible (no
# double-counting when retrieved spans overlap each other) but they
# diverge from upstream whenever such overlap exists. The
# ``_paper`` variants exist so headline numbers can be quoted against
# the paper without an "almost-the-same-formula" caveat. Equivalence
# against a vendored copy of upstream is enforced in
# ``test_benchmarks.TestUpstreamEquivalence``.


def char_recall_paper(
    predicted_spans: Sequence[Span],
    predicted_doc_ids: Sequence[int | None],
    target_doc_id: int,
    gold: Sequence[Span],
) -> float:
    """Recall computed exactly as upstream ``QAResult.recall`` does.

    Outer loop over gold, inner over retrieved; per-pair overlap is
    accumulated into the numerator; denominator is the sum of gold
    span lengths. Predicted spans are NOT merged, so when two
    retrieved spans both cover the same gold region the overlap is
    summed twice. file_path equality is enforced via
    ``predicted_doc_ids`` (only retrieved spans whose document id
    matches ``target_doc_id`` contribute).
    """
    if len(predicted_spans) != len(predicted_doc_ids):
        raise ValueError("predicted_spans and predicted_doc_ids must be parallel")
    total_relevant_len = 0
    relevant_retrieved_len = 0
    for g_start, g_end in gold:
        total_relevant_len += g_end - g_start
        for (p_start, p_end), p_doc in zip(predicted_spans, predicted_doc_ids):
            if p_doc != target_doc_id:
                continue
            common_min = max(p_start, g_start)
            common_max = min(p_end, g_end)
            if common_max > common_min:
                relevant_retrieved_len += common_max - common_min
    if total_relevant_len == 0:
        return 0.0
    return relevant_retrieved_len / total_relevant_len


def char_precision_paper(
    predicted_spans: Sequence[Span],
    predicted_doc_ids: Sequence[int | None],
    target_doc_id: int,
    gold: Sequence[Span],
) -> float:
    """Precision computed exactly as upstream ``QAResult.precision`` does.

    Outer loop over retrieved, inner over gold; per-pair overlap is
    accumulated into the numerator; denominator is the sum of EVERY
    retrieved span's length (including spans from non-target
    documents — they are noise and properly count against precision).
    Only spans whose document id matches ``target_doc_id`` can
    contribute to the numerator (file_path equality).
    """
    if len(predicted_spans) != len(predicted_doc_ids):
        raise ValueError("predicted_spans and predicted_doc_ids must be parallel")
    total_retrieved_len = 0
    relevant_retrieved_len = 0
    for (p_start, p_end), p_doc in zip(predicted_spans, predicted_doc_ids):
        total_retrieved_len += p_end - p_start
        if p_doc != target_doc_id:
            continue
        for g_start, g_end in gold:
            common_min = max(p_start, g_start)
            common_max = min(p_end, g_end)
            if common_max > common_min:
                relevant_retrieved_len += common_max - common_min
    if total_retrieved_len == 0:
        return 0.0
    return relevant_retrieved_len / total_retrieved_len


def char_f1(
    predicted: Sequence[Span],
    gold: Sequence[Span],
) -> float:
    """Harmonic mean of :func:`char_recall` and :func:`char_precision`.

    LegalBench-RAG reports recall and precision separately rather than
    F1; we compute F1 anyway because it's the single-number summary
    most readers expect.  Returns 0.0 when either side is zero.
    """
    r = char_recall(predicted, gold)
    p = char_precision(predicted, gold)
    if r + p == 0.0:
        return 0.0
    return 2 * r * p / (r + p)


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
