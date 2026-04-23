"""Base class for post-retrieval rerankers.

Rerankers take a query + a set of candidate passages and return a re-ordered
set of ``(index, score)`` pairs. They are intended to run *after* vector
similarity or hybrid search as a second pass that uses a more expensive but
more accurate scoring function (typically a cross-encoder).

Design goals:
- Pluggable via the standard ``PipelineComponentBase`` mechanism so settings
  are loaded from ``PipelineSettings`` just like parsers and embedders.
- Framework-agnostic: rerankers accept plain ``str`` passages so they can be
  reused for annotation search, conversation search, or any future retrieval
  pipeline.
- Fault-tolerant: reranker failures must never break retrieval. Callers that
  surface exceptions at a tight path (e.g. agent tools) should wrap rerank
  calls with :func:`safe_rerank`.
- Sync + async: the abstract method is sync (so CPU-bound cross-encoders and
  blocking HTTP calls stay simple) but a default async wrapper uses
  ``sync_to_async`` so callers on the async retrieval path don't need to care.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from asgiref.sync import sync_to_async

from opencontractserver.constants.search import RERANK_MAX_CANDIDATES

from .base_component import PipelineComponentBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RerankResult:
    """A single reranker output.

    Attributes:
        index: Position of the passage in the *original* ``passages`` list
            passed to :meth:`BaseReranker.rerank`. Callers use this to rebuild
            the reranked candidate list without having to ship payloads
            through the reranker.
        score: Relevance score assigned by the reranker. Score ranges are
            model-specific (e.g. cross-encoder logits, Cohere relevance
            probabilities). Higher = more relevant.
    """

    index: int
    score: float


class BaseReranker(PipelineComponentBase, ABC):
    """Abstract base class for rerankers.

    Concrete implementations override :meth:`_rerank_impl`. The public
    :meth:`rerank` method handles settings injection (via
    ``get_component_settings()``) and input validation.

    ``arerank()`` provides an async entry point. The default implementation
    wraps the sync impl via ``sync_to_async`` — subclasses that can issue
    native async I/O (e.g. ``httpx.AsyncClient``) should override
    ``_arerank_impl``.
    """

    title: str = ""
    description: str = ""
    author: str = ""
    dependencies: list[str] = []
    input_schema: Mapping = {}

    # Hard upper bound on candidates per call. Cross-encoders quadratic in
    # this number (per-pair scoring), so keep it reasonable. Shares a single
    # source of truth with the retrieval-side cap
    # (:data:`RERANK_MAX_CANDIDATES`) so oversampling and reranker-side
    # truncation stay aligned. Callers can raise this on an instance if
    # they know what they're doing.
    max_candidates: int = RERANK_MAX_CANDIDATES

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def _effective_settings(self):
        """Return ``self.settings`` or a fresh default-configured Settings().

        Shared by all concrete backends so fallback behaviour stays consistent
        if :attr:`PipelineComponentBase.settings` semantics ever change.
        Concrete reranker subclasses always declare a ``Settings`` dataclass,
        so the fallback path is always callable at runtime.
        """
        if self.settings is not None:
            return self.settings
        settings_cls = self.Settings
        assert (
            settings_cls is not None
        ), f"{type(self).__name__} must declare a Settings dataclass"
        return settings_cls()

    def _prepare_call(
        self,
        query: str,
        passages: list[str],
        top_k: int | None,
        direct_kwargs: dict,
    ) -> tuple[list[str], dict, list[RerankResult] | None]:
        """Apply shared input validation for sync + async entry points.

        Returns ``(passages, merged_kwargs, short_circuit)`` where
        ``short_circuit`` is a non-None result list when the caller should
        skip the concrete impl (empty passages or empty query).
        """
        if not passages:
            return passages, {}, []

        if not query or not query.strip():
            logger.debug("Reranker received empty query; returning identity ordering.")
            return (
                passages,
                {},
                [RerankResult(index=i, score=1.0) for i in range(len(passages))],
            )

        if len(passages) > self.max_candidates:
            logger.warning(
                "Reranker '%s' received %d candidates (max=%d); "
                "truncating to the first %d.",
                self.__class__.__name__,
                len(passages),
                self.max_candidates,
                self.max_candidates,
            )
            passages = passages[: self.max_candidates]

        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}
        if top_k is not None:
            merged_kwargs.setdefault("top_k", top_k)
        return passages, merged_kwargs, None

    def rerank(
        self,
        query: str,
        passages: list[str],
        top_k: int | None = None,
        **direct_kwargs,
    ) -> list[RerankResult]:
        """Re-order passages by relevance to the query.

        Args:
            query: User query / natural-language question.
            passages: Candidate passage texts. Empty or whitespace-only
                passages keep their original index but receive a score of
                ``-inf`` so they sort to the bottom.
            top_k: Optional cap on number of results to return. ``None`` =
                return all re-scored passages sorted by score descending.
            **direct_kwargs: Runtime overrides merged with component
                settings before being forwarded to the concrete impl.
                ``top_k`` is forwarded as a hint so backends that can
                short-circuit (HTTP services, hosted APIs) have access to
                it; the base class still performs the authoritative trim.

        Returns:
            A list of :class:`RerankResult`, sorted by ``score`` descending.
            When ``top_k`` is provided, the list length is
            ``min(top_k, len(passages))``.
        """
        passages, merged_kwargs, short_circuit = self._prepare_call(
            query, passages, top_k, direct_kwargs
        )
        if short_circuit is not None:
            return short_circuit
        results = self._rerank_impl(query, passages, **merged_kwargs)
        return self._finalize_results(results, len(passages), top_k)

    async def arerank(
        self,
        query: str,
        passages: list[str],
        top_k: int | None = None,
        **direct_kwargs,
    ) -> list[RerankResult]:
        """Async variant of :meth:`rerank`.

        Default implementation wraps :meth:`rerank` via ``sync_to_async``.
        Subclasses that make async HTTP calls should override
        :meth:`_arerank_impl` instead of overriding this method — the
        validation/finalization steps in :meth:`rerank` are not trivial.
        """
        passages, merged_kwargs, short_circuit = self._prepare_call(
            query, passages, top_k, direct_kwargs
        )
        if short_circuit is not None:
            return short_circuit
        results = await self._arerank_impl(query, passages, **merged_kwargs)
        return self._finalize_results(results, len(passages), top_k)

    # ------------------------------------------------------------------ #
    # Hooks for subclasses
    # ------------------------------------------------------------------ #

    @abstractmethod
    def _rerank_impl(
        self,
        query: str,
        passages: list[str],
        **all_kwargs,
    ) -> list[RerankResult]:
        """Concrete reranker implementation.

        Must return one :class:`RerankResult` per input passage — the public
        ``rerank`` method handles sorting and ``top_k`` trimming.
        Implementations MUST return indices in the range
        ``[0, len(passages))``.
        """

    async def _arerank_impl(
        self,
        query: str,
        passages: list[str],
        **all_kwargs,
    ) -> list[RerankResult]:
        """Async hook for subclasses that can do native async I/O.

        Default implementation wraps the sync ``_rerank_impl`` via
        ``sync_to_async`` so every backend has a working async path without
        having to duplicate logic.
        """
        return await sync_to_async(self._rerank_impl, thread_sensitive=False)(
            query, passages, **all_kwargs
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _finalize_results(
        results: list[RerankResult],
        n_candidates: int,
        top_k: int | None,
    ) -> list[RerankResult]:
        """Validate indices, sort by score, and trim to ``top_k``."""
        # Defensive: drop any invalid indices rather than raising, to keep
        # a misbehaving backend from breaking retrieval.
        clean: list[RerankResult] = []
        seen: set[int] = set()
        for r in results:
            if not (0 <= r.index < n_candidates):
                logger.warning(
                    "Reranker produced out-of-range index %d (n=%d); skipping.",
                    r.index,
                    n_candidates,
                )
                continue
            if r.index in seen:
                # Shouldn't happen in practice, but guard against duplicates.
                continue
            seen.add(r.index)
            clean.append(r)

        # Sort descending by score, stable on original index for ties.
        clean.sort(key=lambda r: (-r.score, r.index))

        if top_k is not None and top_k >= 0:
            clean = clean[:top_k]
        return clean


def safe_rerank(
    reranker: BaseReranker | None,
    query: str,
    passages: list[str],
    top_k: int | None = None,
    **direct_kwargs,
) -> list[RerankResult] | None:
    """Run :meth:`BaseReranker.rerank` without propagating failures.

    Returns ``None`` if the reranker is ``None``, the inputs are unusable,
    or the backend raises. Callers should treat ``None`` as "fall back to
    the pre-rerank ordering".
    """
    if reranker is None or not passages:
        return None
    try:
        return reranker.rerank(query, passages, top_k=top_k, **direct_kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Reranker '%s' failed; falling back to pre-rerank ordering: %s",
            reranker.__class__.__name__,
            exc,
        )
        return None


async def safe_arerank(
    reranker: BaseReranker | None,
    query: str,
    passages: list[str],
    top_k: int | None = None,
    **direct_kwargs,
) -> list[RerankResult] | None:
    """Async counterpart of :func:`safe_rerank`."""
    if reranker is None or not passages:
        return None
    try:
        return await reranker.arerank(query, passages, top_k=top_k, **direct_kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Reranker '%s' failed (async); falling back to pre-rerank ordering: %s",
            reranker.__class__.__name__,
            exc,
        )
        return None
