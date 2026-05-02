"""Retrieval probe used by the benchmark runner.

Extraction and retrieval are evaluated on separate axes: extraction uses the
structured-response agent path (which intentionally does not surface raw
citations), retrieval uses the core vector store that powers chat agents.
Keeping the two probes separate gives us clean, interpretable metrics and
lets each dimension fail independently.
"""

from __future__ import annotations

import dataclasses
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


# Module-level cache for ``StructuralAnnotationSet → Document`` resolution
# inside a benchmark process.  A full LegalBench-RAG run probes ~776
# queries × top_k=32 hits and reuses a small set of structural sets, so
# making the cache call-local would re-issue the same query hundreds of
# times.  Keying on ``(corpus_id, struct_set_id)`` keeps separate corpora
# isolated when the same struct_set appears in multiple corpora.
_STRUCT_SET_TO_DOC: dict[tuple[int, int], int | None] = {}


def _clear_struct_set_cache() -> None:
    """Test hook: drop cached struct-set→document resolutions.

    The cache is process-wide; tests that recreate corpora between
    cases need to clear it so a stale ``Document.id`` from a torn-down
    fixture isn't returned.
    """
    _STRUCT_SET_TO_DOC.clear()


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
    # Parallel list of document IDs — needed when ``corpus_wide=True`` so
    # the metric layer can filter intersection to the target document
    # (matching LegalBench-RAG's ``snippet.file_path == gt_snippet.file_path``
    # check in ``run_benchmark.py:29``).  In per-document mode every entry
    # equals the queried document_id, and scoring collapses to the
    # single-doc formulas unchanged.
    document_ids: list[int | None] = dataclasses.field(default_factory=list)


def probe_retrieval(
    *,
    corpus_id: int,
    document_id: int,
    query_text: str,
    top_k: int,
    user_id: int | None = None,
    corpus_wide: bool = False,
) -> RetrievalResult:
    """Retrieve the top-k annotations for ``query_text`` via the core vector store.

    By default, only annotations belonging to ``document_id`` inside
    ``corpus_id`` are considered — this matches OpenContracts' production
    extraction protocol (one agent run per target document).

    With ``corpus_wide=True`` the document filter is dropped and the probe
    searches the entire ``corpus_id``.  This matches LegalBench-RAG's
    baseline, which has no document filter and forces the retriever to
    find the right file plus the right span in a single shot.  Use this
    mode when you want numbers directly comparable to the paper.

    Args:
        corpus_id: The corpus the benchmark loader created.
        document_id: The document to search within (ignored when
            ``corpus_wide=True``; kept on the signature so callers don't
            need to branch on mode).
        query_text: The benchmark query.
        top_k: Number of top annotations to return.
        user_id: Optional user id to thread through for ACL filtering.
            When omitted, only public/structural annotations are visible.
        corpus_wide: If ``True``, do not filter by ``document_id``.

    Returns:
        A :class:`RetrievalResult` ready for the metrics module.
    """
    # ``check_corpus_deletion=False`` works around a bug in
    # ``CoreAnnotationVectorStore``: when ``document_id`` is None (the
    # corpus-wide case), the deletion-aware path adds a
    # ``document_id__in=<active_doc_ids>`` filter that silently drops every
    # structural annotation (paragraph chunks, sentence chunks, …) because
    # their ``document_id`` FK is NULL — they're attached via
    # ``StructuralAnnotationSet.structural_set_id`` instead. Bypass that
    # filter for the benchmark; the corpus is freshly created for each
    # run, so there are no stale-deleted documents to defend against.
    store = CoreAnnotationVectorStore(
        corpus_id=corpus_id,
        document_id=None if corpus_wide else document_id,
        user_id=user_id,
        check_corpus_deletion=not corpus_wide,
    )
    query = VectorSearchQuery(query_text=query_text, similarity_top_k=top_k)
    results: list[VectorSearchResult] = store.search(query)

    annotation_ids: list[int] = []
    spans: list[Span] = []
    scores: list[float] = []
    doc_ids: list[int | None] = []
    # Structural annotations have ``document_id=NULL`` because they hang
    # off ``StructuralAnnotationSet`` (shared across documents with the
    # same content hash). To produce a per-result document_id we resolve
    # ``structural_set_id`` → ``Document.id`` via the reverse FK on
    # Document.  The cache is module-level (keyed by corpus_id) so a
    # full benchmark run amortises the lookup across all probe calls
    # rather than re-querying once per-call.
    from opencontractserver.documents.models import Document

    def _resolve_doc_id(annotation: Annotation) -> int | None:
        if annotation.document_id is not None:
            return annotation.document_id
        struct_set_id = annotation.structural_set_id
        if struct_set_id is None:
            return None
        cache_key = (corpus_id, struct_set_id)
        if cache_key not in _STRUCT_SET_TO_DOC:
            # Resolve to the Document in the *target corpus* — across
            # benchmark runs the same content_hash can reappear, and
            # ``CoreAnnotationVectorStore``'s structural-annotation
            # filter doesn't restrict to corpus, so a naive
            # ``filter(structural_annotation_set_id=…).first()`` can
            # land on a Document from a previous run's corpus, making
            # doc_ids mismatch the gold's target_doc_id and zeroing
            # out char_recall_cross_doc. Constrain via DocumentPath.
            doc = (
                Document.objects.filter(
                    structural_annotation_set_id=struct_set_id,
                    path_records__corpus_id=corpus_id,
                )
                .distinct()
                .first()
            )
            _STRUCT_SET_TO_DOC[cache_key] = doc.id if doc else None
        return _STRUCT_SET_TO_DOC[cache_key]

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
        doc_ids.append(_resolve_doc_id(annotation))

    return RetrievalResult(
        annotation_ids=annotation_ids,
        spans=spans,
        similarity_scores=scores,
        document_ids=doc_ids,
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
