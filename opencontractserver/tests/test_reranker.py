"""Unit tests for the post-retrieval reranker framework.

Covers:
    - :class:`BaseReranker` contract (sorting, validation, empty input).
    - :class:`NoopReranker` identity behaviour.
    - :class:`MicroserviceReranker` HTTP plumbing (mocked requests).
    - :class:`CohereReranker` HTTP plumbing (mocked requests).
    - ``safe_rerank`` / ``safe_arerank`` failure handling.
    - Pipeline utility helpers that resolve the default reranker.
    - Integration with :class:`CoreAnnotationVectorStore`.
"""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import Annotation
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchResult,
)
from opencontractserver.pipeline.base.reranker import (
    BaseReranker,
    RerankerUnavailableError,
    RerankResult,
    safe_arerank,
    safe_rerank,
    strict_arerank,
    strict_rerank,
)
from opencontractserver.pipeline.rerankers.cohere_reranker import CohereReranker
from opencontractserver.pipeline.rerankers.microservice_reranker import (
    MicroserviceReranker,
)
from opencontractserver.pipeline.rerankers.noop_reranker import NoopReranker

# --------------------------------------------------------------------------- #
# Base class tests
# --------------------------------------------------------------------------- #


class _ReversingReranker(BaseReranker):
    """Reverses the candidate order (last → first)."""

    title = "Reversing Reranker"
    description = "Test reranker that reverses the candidate order."

    def _rerank_impl(
        self, query: str, passages: list[str], **all_kwargs
    ) -> list[RerankResult]:
        n = len(passages)
        return [RerankResult(index=i, score=float(i)) for i in range(n)]


class _KeywordReranker(BaseReranker):
    """Scores passages by a single-keyword hit count."""

    title = "Keyword Reranker"
    description = "Scores passages by keyword-hit count."

    def _rerank_impl(
        self, query: str, passages: list[str], **all_kwargs
    ) -> list[RerankResult]:
        return [
            RerankResult(index=i, score=float(p.lower().count(query.lower())))
            for i, p in enumerate(passages)
        ]


class _ExplodingReranker(BaseReranker):
    title = "Exploding Reranker"
    description = "Always raises to exercise safe_rerank fallback."

    def _rerank_impl(
        self, query: str, passages: list[str], **all_kwargs
    ) -> list[RerankResult]:
        raise RuntimeError("boom")


class BaseRerankerContractTest(TestCase):
    def test_empty_passages_returns_empty(self) -> None:
        reranker = _KeywordReranker()
        self.assertEqual(reranker.rerank("anything", []), [])

    def test_empty_query_returns_identity_order(self) -> None:
        reranker = _KeywordReranker()
        passages = ["alpha", "beta", "gamma"]
        results = reranker.rerank("", passages)
        self.assertEqual([r.index for r in results], [0, 1, 2])

    def test_keyword_reranker_orders_by_hit_count(self) -> None:
        reranker = _KeywordReranker()
        passages = ["no match here", "cat cat dog", "one cat", "zero"]
        results = reranker.rerank("cat", passages)
        # Scores: [0, 2, 1, 0] → expect indices [1, 2, 0, 3]
        self.assertEqual([r.index for r in results], [1, 2, 0, 3])
        self.assertEqual([r.score for r in results], [2.0, 1.0, 0.0, 0.0])

    def test_top_k_truncates(self) -> None:
        reranker = _ReversingReranker()
        passages = [f"p{i}" for i in range(5)]
        results = reranker.rerank("q", passages, top_k=2)
        self.assertEqual(len(results), 2)
        # Reversed order: highest score = index 4, then 3
        self.assertEqual([r.index for r in results], [4, 3])

    def test_out_of_range_indices_are_dropped(self) -> None:
        class BadReranker(BaseReranker):
            title = "Bad"
            description = "Returns bogus indices."

            def _rerank_impl(self, query, passages, **_):
                return [
                    RerankResult(index=-1, score=9.0),
                    RerankResult(index=99, score=8.0),
                    RerankResult(index=0, score=1.0),
                ]

        results = BadReranker().rerank("q", ["only"])
        self.assertEqual([r.index for r in results], [0])

    def test_max_candidates_is_enforced(self) -> None:
        class SmallCapReranker(_ReversingReranker):
            max_candidates = 3

        passages = [f"p{i}" for i in range(10)]
        results = SmallCapReranker().rerank("q", passages)
        # Only the first 3 candidates are scored; the rest are dropped.
        self.assertEqual(len(results), 3)
        self.assertTrue(all(0 <= r.index < 3 for r in results))

    def test_arerank_default_wraps_sync(self) -> None:
        reranker = _KeywordReranker()
        passages = ["x cat y", "nothing", "cat cat"]
        results = asyncio.run(reranker.arerank("cat", passages))
        self.assertEqual([r.index for r in results], [2, 0, 1])


# --------------------------------------------------------------------------- #
# Safe wrapper tests
# --------------------------------------------------------------------------- #


class SafeRerankTest(TestCase):
    def test_safe_rerank_none_on_missing_reranker(self) -> None:
        self.assertIsNone(safe_rerank(None, "q", ["a"]))

    def test_safe_rerank_none_on_empty_passages(self) -> None:
        self.assertIsNone(safe_rerank(_KeywordReranker(), "q", []))

    def test_safe_rerank_swallows_exceptions(self) -> None:
        self.assertIsNone(safe_rerank(_ExplodingReranker(), "q", ["a", "b"]))

    def test_safe_arerank_swallows_exceptions(self) -> None:
        result = asyncio.run(safe_arerank(_ExplodingReranker(), "q", ["a", "b"]))
        self.assertIsNone(result)


class StrictRerankTest(TestCase):
    def test_strict_rerank_raises_when_reranker_is_none(self) -> None:
        with self.assertRaises(RerankerUnavailableError):
            strict_rerank(None, "q", ["a", "b"])

    def test_strict_rerank_raises_on_backend_exception(self) -> None:
        with self.assertRaises(RerankerUnavailableError):
            strict_rerank(_ExplodingReranker(), "q", ["a", "b"])

    def test_strict_rerank_empty_passages_returns_empty(self) -> None:
        self.assertEqual(strict_rerank(_KeywordReranker(), "q", []), [])

    def test_strict_arerank_raises_on_backend_exception(self) -> None:
        with self.assertRaises(RerankerUnavailableError):
            asyncio.run(strict_arerank(_ExplodingReranker(), "q", ["a", "b"]))


# --------------------------------------------------------------------------- #
# Built-in backends
# --------------------------------------------------------------------------- #


class NoopRerankerTest(TestCase):
    def test_identity_ordering(self) -> None:
        passages = ["a", "b", "c"]
        results = NoopReranker().rerank("query", passages)
        self.assertEqual([r.index for r in results], [0, 1, 2])


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class MicroserviceRerankerTest(TestCase):
    def _reranker(self) -> MicroserviceReranker:
        reranker = MicroserviceReranker()
        # Override settings without touching the database.
        reranker._settings = MicroserviceReranker.Settings(
            reranker_microservice_url="http://reranker.test",
            reranker_api_key="sekret",
        )
        return reranker

    def test_successful_rerank_parses_response(self) -> None:
        reranker = self._reranker()
        fake_response = _FakeResponse(
            status_code=200,
            payload={
                "results": [
                    {"index": 2, "score": 9.0},
                    {"index": 0, "score": 4.0},
                    {"index": 1, "score": 2.0},
                ]
            },
        )
        with patch("requests.post", return_value=fake_response) as mock_post:
            results = reranker.rerank(
                "query",
                ["p0", "p1", "p2"],
                top_k=2,
            )
        self.assertEqual([r.index for r in results], [2, 0])
        # Sanity-check the request shape.
        call = mock_post.call_args
        self.assertEqual(call.args[0], "http://reranker.test/rerank")
        self.assertEqual(call.kwargs["json"]["query"], "query")
        self.assertEqual(call.kwargs["json"]["passages"], ["p0", "p1", "p2"])
        self.assertEqual(call.kwargs["headers"]["X-API-Key"], "sekret")

    def test_missing_url_falls_through_to_identity(self) -> None:
        reranker = MicroserviceReranker()
        reranker._settings = MicroserviceReranker.Settings(reranker_microservice_url="")
        results = reranker.rerank("query", ["p0", "p1"])
        self.assertEqual([r.index for r in results], [0, 1])

    def test_request_exception_falls_back_to_identity(self) -> None:
        reranker = self._reranker()
        with patch(
            "requests.post",
            side_effect=requests.exceptions.ConnectionError("network down"),
        ):
            results = reranker.rerank("query", ["p0", "p1"])
        self.assertEqual([r.index for r in results], [0, 1])

    def test_non_200_status_falls_back_to_identity(self) -> None:
        reranker = self._reranker()
        with patch("requests.post", return_value=_FakeResponse(status_code=500)):
            results = reranker.rerank("query", ["p0", "p1"])
        self.assertEqual([r.index for r in results], [0, 1])

    def test_malformed_body_falls_back_to_identity(self) -> None:
        reranker = self._reranker()
        with patch(
            "requests.post",
            return_value=_FakeResponse(status_code=200, payload={"nope": 1}),
        ):
            results = reranker.rerank("query", ["p0", "p1"])
        self.assertEqual([r.index for r in results], [0, 1])


class CohereRerankerTest(TestCase):
    def _reranker(self) -> CohereReranker:
        reranker = CohereReranker()
        reranker._settings = CohereReranker.Settings(cohere_api_key="test-key")
        return reranker

    def test_successful_rerank_parses_cohere_response(self) -> None:
        reranker = self._reranker()
        fake_response = _FakeResponse(
            status_code=200,
            payload={
                "results": [
                    {"index": 1, "relevance_score": 0.92},
                    {"index": 0, "relevance_score": 0.61},
                ]
            },
        )
        with patch("requests.post", return_value=fake_response) as mock_post:
            results = reranker.rerank("query", ["p0", "p1"], top_k=1)
        self.assertEqual([r.index for r in results], [1])
        call = mock_post.call_args
        self.assertIn("Authorization", call.kwargs["headers"])
        self.assertTrue(call.kwargs["headers"]["Authorization"].startswith("Bearer "))
        self.assertEqual(call.kwargs["json"]["top_n"], 1)

    def test_missing_api_key_returns_identity(self) -> None:
        reranker = CohereReranker()
        reranker._settings = CohereReranker.Settings(cohere_api_key="")
        results = reranker.rerank("query", ["a", "b"])
        self.assertEqual([r.index for r in results], [0, 1])


# --------------------------------------------------------------------------- #
# Pipeline utility tests
# --------------------------------------------------------------------------- #


class PipelineUtilityTest(TransactionTestCase):
    """Covers the ``get_default_reranker_*`` helpers and the instance cache."""

    def setUp(self) -> None:
        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.utils import invalidate_reranker_cache

        self.PipelineSettings = PipelineSettings
        invalidate_reranker_cache()

    def tearDown(self) -> None:
        from opencontractserver.pipeline.utils import invalidate_reranker_cache

        invalidate_reranker_cache()

    def test_default_empty_returns_none(self) -> None:
        from opencontractserver.pipeline.utils import (
            get_default_reranker_instance,
            get_default_reranker_path,
        )

        instance = self.PipelineSettings.get_instance()
        instance.default_reranker = ""
        instance.save()

        self.assertEqual(get_default_reranker_path(), "")
        self.assertIsNone(get_default_reranker_instance())

    def test_configured_reranker_is_instantiated_and_cached(self) -> None:
        from opencontractserver.pipeline.utils import (
            get_default_reranker_instance,
        )

        instance = self.PipelineSettings.get_instance()
        instance.default_reranker = (
            "opencontractserver.pipeline.rerankers.noop_reranker.NoopReranker"
        )
        instance.save()

        first = get_default_reranker_instance()
        self.assertIsInstance(first, NoopReranker)
        second = get_default_reranker_instance()
        self.assertIs(first, second, "Instance should be process-cached.")

    def test_invalid_class_path_returns_none(self) -> None:
        from opencontractserver.pipeline.utils import (
            get_default_reranker_instance,
        )

        instance = self.PipelineSettings.get_instance()
        instance.default_reranker = "nonexistent.module.Reranker"
        instance.save()
        self.assertIsNone(get_default_reranker_instance())


# --------------------------------------------------------------------------- #
# Vector store integration
# --------------------------------------------------------------------------- #


class _FakeAnnotation:
    """Lightweight stand-in for the Annotation model used by vector store tests."""

    def __init__(self, ann_id: int, raw_text: str, similarity_score: float = 1.0):
        self.id = ann_id
        self.raw_text = raw_text
        self.similarity_score = similarity_score


class CoreVectorStoreRerankerIntegrationTest(TestCase):
    """Verify the vector store oversamples and re-orders through a reranker."""

    def _fake_results(self) -> list[VectorSearchResult]:
        passages = [
            "irrelevant filler passage about weather",
            "contract termination notice and penalties",
            "footer page 1 of 10",
            "assignment clause and notice period",
            "unrelated definitions section",
            "governing law and venue",
        ]
        return [
            VectorSearchResult(
                annotation=cast(
                    Annotation,
                    _FakeAnnotation(i, text, similarity_score=1.0 - i * 0.1),
                ),
                similarity_score=1.0 - i * 0.1,
            )
            for i, text in enumerate(passages)
        ]

    def test_apply_rerank_moves_relevant_passages_to_top(self) -> None:
        store = CoreAnnotationVectorStore(
            corpus_id=1, embedder_path="fake", reranker=_KeywordReranker()
        )
        # Bypass corpus existence check by stubbing _get_reranker.
        store._reranker_override = _KeywordReranker()

        reranked = store._apply_rerank(
            self._fake_results(),
            query_text="termination",
            top_k=3,
            reranker=store._reranker_override,
        )

        self.assertEqual(len(reranked), 3)
        # The only passage containing 'termination' is index 1.
        self.assertEqual(reranked[0].annotation.id, 1)
        # The reranked similarity_score is now the keyword-hit count.
        self.assertEqual(reranked[0].similarity_score, 1.0)

    def test_apply_rerank_without_query_text_just_truncates(self) -> None:
        store = CoreAnnotationVectorStore(
            corpus_id=1, embedder_path="fake", reranker=_KeywordReranker()
        )
        truncated = store._apply_rerank(
            self._fake_results(),
            query_text=None,
            top_k=2,
            reranker=_KeywordReranker(),
        )
        self.assertEqual(len(truncated), 2)
        self.assertEqual([r.annotation.id for r in truncated], [0, 1])

    def test_apply_rerank_without_reranker_just_truncates(self) -> None:
        store = CoreAnnotationVectorStore(corpus_id=1, embedder_path="fake")
        truncated = store._apply_rerank(
            self._fake_results(),
            query_text="termination",
            top_k=2,
            reranker=None,
        )
        self.assertEqual([r.annotation.id for r in truncated], [0, 1])

    def test_first_stage_top_k_oversamples_when_reranker_active(self) -> None:
        store = CoreAnnotationVectorStore(
            corpus_id=1,
            embedder_path="fake",
            reranker=_KeywordReranker(),
            rerank_oversample_factor=4,
        )
        # With an active reranker, first-stage fetch should oversample.
        self.assertEqual(
            store._effective_first_stage_top_k(5, store._get_reranker()), 20
        )
        # Without a reranker, no oversampling.
        self.assertEqual(store._effective_first_stage_top_k(5, None), 5)

    def test_first_stage_top_k_capped_by_max_candidates(self) -> None:
        store = CoreAnnotationVectorStore(
            corpus_id=1,
            embedder_path="fake",
            reranker=_KeywordReranker(),
            rerank_oversample_factor=1000,
        )
        # Oversample (1000 * 50 = 50,000) must be capped by RERANK_MAX_CANDIDATES.
        from opencontractserver.constants.search import RERANK_MAX_CANDIDATES

        self.assertEqual(
            store._effective_first_stage_top_k(50, store._get_reranker()),
            RERANK_MAX_CANDIDATES,
        )

    def test_reranker_failure_falls_back_to_first_stage_order(self) -> None:
        store = CoreAnnotationVectorStore(
            corpus_id=1, embedder_path="fake", reranker=_ExplodingReranker()
        )
        results = store._apply_rerank(
            self._fake_results(),
            query_text="termination",
            top_k=3,
            reranker=_ExplodingReranker(),
        )
        # safe_rerank caught the exception → original order + top_k truncation.
        self.assertEqual([r.annotation.id for r in results], [0, 1, 2])


# --------------------------------------------------------------------------- #
# Registry integration
# --------------------------------------------------------------------------- #


class RerankerRegistryTest(TestCase):
    """Confirm that shipped rerankers are auto-discovered by the registry."""

    def test_builtin_rerankers_discovered(self) -> None:
        from opencontractserver.pipeline.registry import (
            get_all_rerankers_cached,
            reset_registry,
        )

        reset_registry()
        rerankers = get_all_rerankers_cached()
        names = {r.name for r in rerankers}
        self.assertIn("NoopReranker", names)
        self.assertIn("MicroserviceReranker", names)
        self.assertIn("CohereReranker", names)

    def test_reranker_lookup_by_class_path(self) -> None:
        from opencontractserver.pipeline.registry import (
            get_registry,
            reset_registry,
        )

        reset_registry()
        registry = get_registry()
        defn = registry.get_by_class_name(
            "opencontractserver.pipeline.rerankers.noop_reranker.NoopReranker"
        )
        assert defn is not None
        self.assertEqual(defn.name, "NoopReranker")


# Quiet unused-symbol lint warnings for test helpers.
_ = MagicMock
