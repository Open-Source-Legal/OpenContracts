"""Retrieval probe used by the benchmark runner.

Extraction and retrieval are evaluated on separate axes: extraction uses the
structured-response agent path (which intentionally does not surface raw
citations), retrieval uses the core vector store that powers chat agents.
Keeping the two probes separate gives us clean, interpretable metrics and
lets each dimension fail independently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from opencontractserver.annotations.models import Annotation
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
    VectorSearchResult,
)

logger = logging.getLogger(__name__)


Span = tuple[int, int]


@dataclass
class RetrievalResult:
    """Retrieval probe output for a single (query, document) pair.

    Attributes:
        annotation_ids: Primary keys of the annotations returned by the
            vector store, in rank order.
        spans: Parallel list of character spans (pulled from each
            annotation's ``json`` payload, which ``TxtParser`` populates
            with ``{"start": int, "end": int}`` for text documents).
        similarity_scores: Raw similarity scores in rank order.
    """

    annotation_ids: list[int]
    spans: list[Span]
    similarity_scores: list[float]


def probe_retrieval(
    *,
    corpus_id: int,
    document_id: int,
    query_text: str,
    top_k: int,
    user_id: int | None = None,
) -> RetrievalResult:
    """Retrieve the top-k annotations for ``query_text`` via the core vector store.

    Only annotations belonging to ``document_id`` inside ``corpus_id`` are
    considered.  The filter is intentionally narrow so benchmark retrieval
    numbers are per-document, matching LegalBench-RAG's convention of
    scoring each query against a specific corpus file.

    Args:
        corpus_id: The corpus the benchmark loader created.
        document_id: The document to search within.
        query_text: The benchmark query.
        top_k: Number of top annotations to return.
        user_id: Optional user id to thread through for ACL filtering.
            When omitted, only public/structural annotations are visible.

    Returns:
        A :class:`RetrievalResult` ready for the metrics module.
    """
    store = CoreAnnotationVectorStore(
        corpus_id=corpus_id,
        document_id=document_id,
        user_id=user_id,
    )
    query = VectorSearchQuery(query_text=query_text, similarity_top_k=top_k)
    results: list[VectorSearchResult] = store.search(query)

    annotation_ids: list[int] = []
    spans: list[Span] = []
    scores: list[float] = []

    for hit in results:
        annotation: Annotation = hit.annotation
        span = _annotation_char_span(annotation)
        if span is None:
            # Non-text or malformed payload — skip but keep going.
            logger.debug(
                "Skipping annotation %s (no text span available)", annotation.id
            )
            continue
        annotation_ids.append(annotation.id)
        spans.append(span)
        scores.append(float(hit.similarity_score))

    return RetrievalResult(
        annotation_ids=annotation_ids,
        spans=spans,
        similarity_scores=scores,
    )


def _annotation_char_span(annotation: Annotation) -> Span | None:
    """Pull a ``(start, end)`` char span from an annotation's JSON payload.

    Benchmark documents are always text/plain, so their annotations store
    ``{"start": int, "end": int}`` via ``TxtParser``.  Non-text annotations
    (multipage PDFs, PAWLs, etc.) are skipped — they're meaningless for
    LegalBench-RAG character-offset metrics.
    """
    payload: Any = annotation.json
    if not isinstance(payload, dict):
        return None
    start = payload.get("start")
    end = payload.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    if end < start:
        return None
    return start, end
