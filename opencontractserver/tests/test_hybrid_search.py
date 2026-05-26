"""
Integration tests for hybrid search, search_by_embedding refactor,
and the search_vector GIN trigger.

These tests verify:
1. hybrid_search() and async_hybrid_search() combine vector + full-text search
   via Reciprocal Rank Fusion.
2. search_by_embedding() uses PostgreSQL ORDER BY + LIMIT without DISTINCT ON.
3. The search_vector trigger auto-populates tsvector on INSERT and UPDATE.
4. Sequential scan fallback for high-dimensional vectors (dims > 1536).
"""

from typing import Optional
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
    VectorSearchResult,
)
from opencontractserver.pipeline.utils import get_default_embedder_path

User = get_user_model()


def constant_vector(dimension: int = 384, value: float = 0.5) -> list[float]:
    """Generate a constant vector of the given dimension."""
    return [value] * dimension


def directional_vector(dimension: int = 384, active_dims: int = 384) -> list[float]:
    """Generate a vector with 1.0 in the first *active_dims* positions, 0.0 elsewhere.

    Two directional vectors with different ``active_dims`` values will produce
    meaningfully different cosine distances from a query vector, unlike
    constant vectors where all-0.1 and all-0.2 have identical direction.
    """
    return [1.0] * active_dims + [0.0] * (dimension - active_dims)


class TestHybridSearch(TestCase):
    """End-to-end tests for hybrid_search() and async_hybrid_search().

    These tests verify that both sync and async paths:
    - Combine vector and full-text results via RRF fusion
    - Fall back to vector-only when no query text is provided
    - Fall back to text-only when embedding generation fails
    - Return empty results when both arms produce nothing
    """

    @classmethod
    def setUpTestData(cls) -> None:
        with transaction.atomic():
            cls.user = User.objects.create_user(
                username="hybrid_user",
                password="testpass",
                email="hybrid@example.com",
            )
            cls.corpus = Corpus.objects.create(
                title="Hybrid Search Corpus",
                creator=cls.user,
                is_public=True,
            )
            cls.doc = Document.objects.create(
                title="Hybrid Doc",
                creator=cls.user,
                is_public=True,
            )
            DocumentPath.objects.create(
                document=cls.doc,
                corpus=cls.corpus,
                path="/hybrid.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
                creator=cls.user,
            )
            cls.label = AnnotationLabel.objects.create(
                text="Contract Clause",
                creator=cls.user,
            )

            # Create annotations with distinct text to differentiate FTS hits.
            cls.anno_alpha = Annotation.objects.create(
                document=cls.doc,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="The indemnification clause provides broad protection.",
                annotation_label=cls.label,
                is_public=True,
            )
            cls.anno_beta = Annotation.objects.create(
                document=cls.doc,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="Termination provisions allow early exit from contract.",
                annotation_label=cls.label,
                is_public=True,
            )
            cls.anno_gamma = Annotation.objects.create(
                document=cls.doc,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="Force majeure events excuse performance obligations.",
                annotation_label=cls.label,
                is_public=True,
            )

        # Attach embeddings so vector arm can find them.
        dim = 384
        embedder_path = get_default_embedder_path()
        cls.anno_alpha.add_embedding(embedder_path, constant_vector(dim, 0.1))
        cls.anno_beta.add_embedding(embedder_path, constant_vector(dim, 0.2))
        cls.anno_gamma.add_embedding(embedder_path, constant_vector(dim, 0.3))

    def _make_store(self) -> CoreAnnotationVectorStore:
        return CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
        )

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".generate_embeddings_from_text"
    )
    def test_hybrid_search_fuses_vector_and_text(self, mock_embed):
        """hybrid_search with text query should invoke both arms and fuse."""
        mock_embed.return_value = (
            get_default_embedder_path(),
            constant_vector(384, 0.15),
        )
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="indemnification clause",
            similarity_top_k=10,
        )
        results = store.hybrid_search(query)
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0, "Should return at least one result")
        for r in results:
            self.assertIsInstance(r, VectorSearchResult)
            self.assertIsInstance(r.similarity_score, float)

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".generate_embeddings_from_text"
    )
    def test_hybrid_search_vector_only_fallback(self, mock_embed):
        """When no query_text is given, hybrid_search should still work (vector only)."""
        mock_embed.return_value = (
            get_default_embedder_path(),
            constant_vector(384, 0.15),
        )
        store = self._make_store()
        query = VectorSearchQuery(
            query_embedding=constant_vector(384, 0.15),
            query_text=None,
            similarity_top_k=10,
        )
        results = store.hybrid_search(query)
        self.assertTrue(len(results) > 0, "Vector-only fallback should return results")

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".generate_embeddings_from_text"
    )
    def test_hybrid_search_text_only_fallback(self, mock_embed):
        """When embedding generation fails, fall back to text-only."""
        mock_embed.return_value = (None, None)
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="indemnification",
            similarity_top_k=10,
        )
        results = store.hybrid_search(query)
        # Text-only arm should still find annotations via search_vector
        self.assertIsInstance(results, list)

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".agenerate_embeddings_from_text"
    )
    def test_async_hybrid_search_fuses_results(self, mock_aembed):
        """async_hybrid_search with text should invoke both arms and fuse."""
        mock_aembed.return_value = (
            get_default_embedder_path(),
            constant_vector(384, 0.15),
        )
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="termination provisions",
            similarity_top_k=10,
        )
        results = async_to_sync(store.async_hybrid_search)(query)
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0, "Async hybrid should return results")

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".agenerate_embeddings_from_text"
    )
    def test_async_search_delegates_to_hybrid_for_text(self, mock_aembed):
        """async_search with query_text should delegate to async_hybrid_search."""
        mock_aembed.return_value = (
            get_default_embedder_path(),
            constant_vector(384, 0.15),
        )
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="force majeure",
            similarity_top_k=10,
        )
        results = async_to_sync(store.async_search)(query)
        self.assertIsInstance(results, list)
        self.assertTrue(
            len(results) > 0,
            "async_search with text should use hybrid path",
        )

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".agenerate_embeddings_from_text"
    )
    def test_async_search_skips_hybrid_for_embedding_only(self, mock_aembed):
        """async_search with embedding-only (no text) should bypass hybrid."""
        store = self._make_store()
        query = VectorSearchQuery(
            query_embedding=constant_vector(384, 0.15),
            query_text=None,
            similarity_top_k=10,
        )
        results = async_to_sync(store.async_search)(query)
        self.assertIsInstance(results, list)
        # Should NOT have called the async embedding generator
        mock_aembed.assert_not_called()


class TestSearchModeDispatch(TestCase):
    """Tests for the ``mode`` knob on :class:`VectorSearchQuery`.

    Verifies the new ``search()`` / ``async_search()`` dispatch and the
    standalone ``"vector"`` / ``"fts"`` paths. Existing hybrid tests above
    cover the ``"hybrid"`` default.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        with transaction.atomic():
            cls.user = User.objects.create_user(
                username="mode_user",
                password="testpass",
                email="mode@example.com",
            )
            cls.corpus = Corpus.objects.create(
                title="Mode Dispatch Corpus",
                creator=cls.user,
                is_public=True,
            )
            cls.doc = Document.objects.create(
                title="Mode Doc",
                creator=cls.user,
                is_public=True,
            )
            DocumentPath.objects.create(
                document=cls.doc,
                corpus=cls.corpus,
                path="/mode.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
                creator=cls.user,
            )
            cls.label = AnnotationLabel.objects.create(text="Clause", creator=cls.user)
            cls.anno_alpha = Annotation.objects.create(
                document=cls.doc,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="Indemnification clauses limit liability exposure.",
                annotation_label=cls.label,
                is_public=True,
            )
            cls.anno_beta = Annotation.objects.create(
                document=cls.doc,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="Royalty payments accrue quarterly under the agreement.",
                annotation_label=cls.label,
                is_public=True,
            )

        dim = 384
        embedder_path = get_default_embedder_path()
        cls.anno_alpha.add_embedding(embedder_path, constant_vector(dim, 0.1))
        cls.anno_beta.add_embedding(embedder_path, constant_vector(dim, 0.2))

    def _make_store(self) -> CoreAnnotationVectorStore:
        return CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
        )

    def test_query_defaults_to_hybrid_mode(self) -> None:
        """VectorSearchQuery defaults mode to 'hybrid'."""
        q = VectorSearchQuery(query_text="anything")
        self.assertEqual(q.mode, "hybrid")

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".agenerate_embeddings_from_text"
    )
    def test_async_search_mode_vector_skips_fts(self, mock_aembed):
        """mode='vector' should NOT call the FTS arm even with query_text."""
        mock_aembed.return_value = (
            get_default_embedder_path(),
            constant_vector(384, 0.15),
        )
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="indemnification",
            similarity_top_k=5,
            mode="vector",
        )
        with patch.object(CoreAnnotationVectorStore, "_run_fts_query") as mock_fts:
            results = async_to_sync(store.async_search)(query)
        mock_fts.assert_not_called()
        self.assertIsInstance(results, list)

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".agenerate_embeddings_from_text"
    )
    def test_async_search_mode_fts_skips_vector(self, mock_aembed):
        """mode='fts' should NOT generate an embedding."""
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="indemnification",
            similarity_top_k=5,
            mode="fts",
        )
        results = async_to_sync(store.async_search)(query)
        self.assertIsInstance(results, list)
        # FTS-only path should never ask for an embedding
        mock_aembed.assert_not_called()

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".agenerate_embeddings_from_text"
    )
    def test_async_search_mode_fts_without_text_degrades_to_vector(
        self, mock_aembed
    ) -> None:
        """mode='fts' with no text degrades to vector; embedding gen is skipped."""
        store = self._make_store()
        query = VectorSearchQuery(
            query_text=None,
            similarity_top_k=5,
            mode="fts",
        )
        # _resolve_mode is the canonical degradation contract; pin it directly.
        self.assertEqual(CoreAnnotationVectorStore._resolve_mode(query), "vector")

        # Then verify dispatch follows: async_search should route through the
        # vector-only arm (no FTS embedding generation, no FTS arm call).
        with patch.object(
            CoreAnnotationVectorStore,
            "_async_vector_only",
            new=AsyncMock(return_value=[]),
        ) as mock_vector_only, patch.object(
            CoreAnnotationVectorStore, "_run_fts_query"
        ) as mock_fts:
            results = async_to_sync(store.async_search)(query)
        mock_vector_only.assert_awaited_once()
        mock_fts.assert_not_called()
        mock_aembed.assert_not_called()
        self.assertIsInstance(results, list)

    def test_async_search_mode_hybrid_dispatches_to_hybrid(self) -> None:
        """mode='hybrid' explicitly routes async_search through async_hybrid_search."""
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="indemnification",
            similarity_top_k=5,
            mode="hybrid",
        )
        with patch.object(
            CoreAnnotationVectorStore,
            "async_hybrid_search",
            new=AsyncMock(return_value=[]),
        ) as mock_hybrid:
            async_to_sync(store.async_search)(query)
        mock_hybrid.assert_awaited_once()

    def test_sync_search_mode_hybrid_dispatches_to_hybrid(self) -> None:
        """mode='hybrid' explicitly routes sync search through hybrid_search."""
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="indemnification",
            similarity_top_k=5,
            mode="hybrid",
        )
        with patch.object(
            CoreAnnotationVectorStore, "hybrid_search", return_value=[]
        ) as mock_hybrid:
            store.search(query)
        mock_hybrid.assert_called_once()

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".generate_embeddings_from_text"
    )
    def test_sync_search_mode_fts(self, mock_embed):
        """Sync search() dispatches to FTS-only when mode='fts'."""
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="royalty",
            similarity_top_k=5,
            mode="fts",
        )
        results = store.search(query)
        self.assertIsInstance(results, list)
        # FTS-only should not generate embeddings
        mock_embed.assert_not_called()

    @patch(
        "opencontractserver.llms.vector_stores.base_vector_store"
        ".generate_embeddings_from_text"
    )
    def test_sync_search_mode_vector(self, mock_embed):
        """Sync search() dispatches to vector-only when mode='vector'."""
        mock_embed.return_value = (
            get_default_embedder_path(),
            constant_vector(384, 0.15),
        )
        store = self._make_store()
        query = VectorSearchQuery(
            query_text="royalty",
            similarity_top_k=5,
            mode="vector",
        )
        with patch.object(CoreAnnotationVectorStore, "_run_fts_query") as mock_fts:
            results = store.search(query)
        # Vector-only must not invoke the FTS arm
        mock_fts.assert_not_called()
        self.assertIsInstance(results, list)

    def test_resolve_mode_degrades_fts_without_text(self) -> None:
        """``_resolve_mode`` downgrades fts/hybrid to vector when text is missing."""
        empty = VectorSearchQuery(query_text="   ", mode="fts")
        self.assertEqual(CoreAnnotationVectorStore._resolve_mode(empty), "vector")
        none_q = VectorSearchQuery(query_text=None, mode="hybrid")
        self.assertEqual(CoreAnnotationVectorStore._resolve_mode(none_q), "vector")
        ok = VectorSearchQuery(query_text="something", mode="hybrid")
        self.assertEqual(CoreAnnotationVectorStore._resolve_mode(ok), "hybrid")

    # --------------------------------------------------------------------
    # global_search() mode dispatch — the classmethod path has its own
    # embedding + queryset assembly (it doesn't delegate to ``search`` /
    # ``async_search``), so it needs its own coverage.
    # --------------------------------------------------------------------

    def test_global_search_mode_vector_skips_fts(self) -> None:
        """global_search(mode='vector') must not invoke the FTS arm."""
        with patch.object(CoreAnnotationVectorStore, "_run_fts_query") as mock_fts:
            results = CoreAnnotationVectorStore.global_search(
                user_id=self.user.id,
                query_text="indemnification",
                top_k=5,
                mode="vector",
            )
        mock_fts.assert_not_called()
        self.assertIsInstance(results, list)

    def test_global_search_mode_fts_skips_embedder(self) -> None:
        """global_search(mode='fts') must not call the embedder factory."""
        with patch(
            "opencontractserver.pipeline.utils.get_default_embedder"
        ) as mock_get_embedder, patch.object(
            CoreAnnotationVectorStore, "_run_fts_query", return_value=[]
        ) as mock_fts:
            results = CoreAnnotationVectorStore.global_search(
                user_id=self.user.id,
                query_text="indemnification",
                top_k=5,
                mode="fts",
            )
        mock_get_embedder.assert_not_called()
        mock_fts.assert_called_once()
        self.assertIsInstance(results, list)

    def test_global_search_mode_fts_without_text_degrades_to_vector(self) -> None:
        """global_search(mode='fts') with empty text degrades to vector mode.

        After degradation the FTS arm must not run.
        """
        with patch.object(CoreAnnotationVectorStore, "_run_fts_query") as mock_fts:
            results = CoreAnnotationVectorStore.global_search(
                user_id=self.user.id,
                query_text="   ",
                top_k=5,
                mode="fts",
            )
        mock_fts.assert_not_called()
        self.assertIsInstance(results, list)

    def test_global_search_mode_hybrid_dispatches_both_arms(self) -> None:
        """global_search(mode='hybrid') invokes the FTS arm (vector arm covered separately).

        ``test_global_search_mode_vector_skips_fts`` pins the inverse, so a
        successful FTS arm call here is sufficient to prove the dispatch.
        """
        with patch.object(
            CoreAnnotationVectorStore, "_run_fts_query", return_value=[]
        ) as mock_fts:
            results = CoreAnnotationVectorStore.global_search(
                user_id=self.user.id,
                query_text="indemnification",
                top_k=5,
                mode="hybrid",
            )
        mock_fts.assert_called_once()
        self.assertIsInstance(results, list)

    def test_global_search_mode_hybrid_embedder_failure_degrades_to_fts(self) -> None:
        """When the embedder is unavailable, hybrid must degrade to fts (not abort)."""
        with patch(
            "opencontractserver.pipeline.utils.get_default_embedder", return_value=None
        ), patch.object(
            CoreAnnotationVectorStore, "_run_fts_query", return_value=[]
        ) as mock_fts:
            results = CoreAnnotationVectorStore.global_search(
                user_id=self.user.id,
                query_text="indemnification",
                top_k=5,
                mode="hybrid",
            )
        # Vector arm couldn't run, but FTS arm still must (this is the whole
        # point of the degradation contract).
        mock_fts.assert_called_once()
        self.assertIsInstance(results, list)

    def test_global_search_mode_vector_embedder_failure_returns_empty(self) -> None:
        """Vector-only with no embedder has nothing to fall back to — empty list."""
        with patch(
            "opencontractserver.pipeline.utils.get_default_embedder", return_value=None
        ), patch.object(CoreAnnotationVectorStore, "_run_fts_query") as mock_fts:
            results = CoreAnnotationVectorStore.global_search(
                user_id=self.user.id,
                query_text="indemnification",
                top_k=5,
                mode="vector",
            )
        self.assertEqual(results, [])
        # FTS arm must not be silently triggered when caller asked for vector.
        mock_fts.assert_not_called()

    # --------------------------------------------------------------------
    # _generate_global_query_vector helper — unit-level coverage of the
    # mode + vector resolution rule extracted from global_search.
    # --------------------------------------------------------------------

    def test_generate_global_query_vector_no_embedder_class_degrades_hybrid(
        self,
    ) -> None:
        """Hybrid with no embedder class → mode collapses to fts, vector is None."""
        with patch(
            "opencontractserver.pipeline.utils.get_default_embedder", return_value=None
        ):
            mode, vector = CoreAnnotationVectorStore._generate_global_query_vector(
                "hybrid", "any text", get_default_embedder_path()
            )
        self.assertEqual(mode, "fts")
        self.assertIsNone(vector)

    def test_generate_global_query_vector_no_embedder_class_preserves_vector(
        self,
    ) -> None:
        """Vector with no embedder class → mode stays vector (caller aborts on None)."""
        with patch(
            "opencontractserver.pipeline.utils.get_default_embedder", return_value=None
        ):
            mode, vector = CoreAnnotationVectorStore._generate_global_query_vector(
                "vector", "any text", get_default_embedder_path()
            )
        self.assertEqual(mode, "vector")
        self.assertIsNone(vector)

    def test_generate_global_query_vector_embed_returns_none_degrades_hybrid(
        self,
    ) -> None:
        """Hybrid where embed_text returns None → degrade to fts."""

        class _FailingEmbedder:
            def embed_text(self, _text: str) -> Optional[list[float]]:
                return None

        with patch(
            "opencontractserver.pipeline.utils.get_default_embedder",
            return_value=_FailingEmbedder,
        ):
            mode, vector = CoreAnnotationVectorStore._generate_global_query_vector(
                "hybrid", "any text", get_default_embedder_path()
            )
        self.assertEqual(mode, "fts")
        self.assertIsNone(vector)

    def test_generate_global_query_vector_success(self) -> None:
        """Successful embedding preserves the input mode and returns the vector."""

        class _OkEmbedder:
            def embed_text(self, _text: str) -> list[float]:
                return constant_vector(384, 0.5)

        with patch(
            "opencontractserver.pipeline.utils.get_default_embedder",
            return_value=_OkEmbedder,
        ):
            mode, vector = CoreAnnotationVectorStore._generate_global_query_vector(
                "hybrid", "any text", get_default_embedder_path()
            )
        self.assertEqual(mode, "hybrid")
        self.assertEqual(len(vector), 384)


class TestSearchByEmbeddingRefactor(TestCase):
    """Tests that search_by_embedding uses ORDER BY + LIMIT and returns a list.

    The refactored search_by_embedding:
    - Delegates sorting and limiting to PostgreSQL (ORDER BY + LIMIT)
    - Does not use DISTINCT ON (unique constraint from migration 0059 prevents dupes)
    - Returns a list (not a QuerySet)
    - Annotates each result with similarity_score
    """

    @classmethod
    def setUpTestData(cls) -> None:
        with transaction.atomic():
            cls.user = User.objects.create_user(
                username="embed_user",
                password="testpass",
                email="embed@example.com",
            )
            cls.doc = Document.objects.create(
                title="Embed Search Doc",
                creator=cls.user,
                is_public=True,
            )
            # Create annotations with embeddings whose *direction* differs
            # from the query vector by varying amounts, producing distinct
            # cosine distances that PostgreSQL can stably sort.
            cls.annotations = []
            for i in range(5):
                ann = Annotation.objects.create(
                    document=cls.doc,
                    creator=cls.user,
                    raw_text=f"Annotation {i} for embedding search test",
                    is_public=True,
                )
                cls.annotations.append(ann)

        embedder_path = get_default_embedder_path()
        # Use directional vectors so each annotation has a genuinely different
        # cosine distance from the query vector (which will be a full 1.0 vector).
        # active_dims: 384, 300, 200, 100, 50 -> increasingly different from query.
        active_dims_list = [384, 300, 200, 100, 50]
        for i, ann in enumerate(cls.annotations):
            ann.add_embedding(
                embedder_path,
                directional_vector(384, active_dims_list[i]),
            )

    def test_search_by_embedding_returns_list(self):
        """search_by_embedding should return a list, not a QuerySet."""
        query_vec = directional_vector(384, 384)
        results = Annotation.objects.search_by_embedding(
            query_vector=query_vec,
            embedder_path=get_default_embedder_path(),
            top_k=10,
        )
        self.assertIsInstance(results, list)

    def test_search_by_embedding_respects_top_k(self):
        """Returned list should have at most top_k elements."""
        query_vec = directional_vector(384, 384)
        top_k = 3
        results = Annotation.objects.search_by_embedding(
            query_vector=query_vec,
            embedder_path=get_default_embedder_path(),
            top_k=top_k,
        )
        self.assertLessEqual(len(results), top_k)

    def test_search_by_embedding_has_similarity_scores(self):
        """Each result should have a similarity_score between 0 and 1."""
        query_vec = directional_vector(384, 384)
        results = Annotation.objects.search_by_embedding(
            query_vector=query_vec,
            embedder_path=get_default_embedder_path(),
            top_k=10,
        )
        for ann in results:
            self.assertTrue(
                hasattr(ann, "similarity_score"),
                "Missing similarity_score attribute",
            )
            self.assertGreaterEqual(ann.similarity_score, 0.0)
            self.assertLessEqual(ann.similarity_score, 1.0)

    def test_search_by_embedding_ordered_by_similarity(self):
        """Results should be ordered by descending similarity (ascending distance).

        Uses directional vectors with varying numbers of active dimensions to
        produce clearly distinct cosine distances, ensuring PostgreSQL can
        stably sort the results.
        """
        query_vec = directional_vector(384, 384)
        results = Annotation.objects.search_by_embedding(
            query_vector=query_vec,
            embedder_path=get_default_embedder_path(),
            top_k=10,
        )
        scores = [ann.similarity_score for ann in results]
        self.assertEqual(
            scores,
            sorted(scores, reverse=True),
            "Results should be sorted by descending similarity",
        )

    def test_search_by_embedding_filters_by_embedder(self):
        """Only annotations with the specified embedder should appear."""
        query_vec = directional_vector(384, 384)
        results = Annotation.objects.search_by_embedding(
            query_vector=query_vec,
            embedder_path="nonexistent-embedder-path",
            top_k=10,
        )
        self.assertEqual(len(results), 0, "No embeddings for this path")


class TestSequentialScanFallback(TestCase):
    """Test graceful degradation for embedding dimensions above the HNSW limit.

    Vectors with dimension > 1536 cannot use HNSW indexes (pgvector hard limit
    of 2000 dims, and we only index up to 1536). These queries fall back to
    sequential scan and should still return correct results while logging a
    warning message.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        with transaction.atomic():
            cls.user = User.objects.create_user(
                username="seqscan_user",
                password="testpass",
                email="seqscan@example.com",
            )
            cls.doc = Document.objects.create(
                title="Sequential Scan Doc",
                creator=cls.user,
                is_public=True,
            )
            cls.annotation = Annotation.objects.create(
                document=cls.doc,
                creator=cls.user,
                raw_text="High-dimensional embedding test annotation",
                is_public=True,
            )

        # Store a 2048-dim embedding (above HNSW limit of 1536)
        embedder_path = get_default_embedder_path()
        cls.annotation.add_embedding(embedder_path, constant_vector(2048, 0.5))

    def test_high_dim_search_returns_results(self):
        """Queries with dim > 1536 should still return results via sequential scan."""
        query_vec = constant_vector(2048, 0.5)
        results = Annotation.objects.search_by_embedding(
            query_vector=query_vec,
            embedder_path=get_default_embedder_path(),
            top_k=10,
        )
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0, "Sequential scan should still find results")
        # The single stored vector is identical to the query, so similarity ~ 1.0
        self.assertAlmostEqual(results[0].similarity_score, 1.0, places=3)

    def test_high_dim_search_logs_warning(self):
        """Queries with dim > 1536 should log a warning about sequential scan."""
        query_vec = constant_vector(2048, 0.5)
        with self.assertLogs("opencontractserver.shared.mixins", level="WARNING") as cm:
            Annotation.objects.search_by_embedding(
                query_vector=query_vec,
                embedder_path=get_default_embedder_path(),
                top_k=10,
            )
        self.assertTrue(
            any("sequential scan" in msg for msg in cm.output),
            "Expected log message about sequential scan fallback",
        )


class TestSearchVectorTrigger(TestCase):
    """Tests for the database trigger that auto-populates search_vector.

    The trigger (migration 0063) fires BEFORE INSERT and UPDATE OF raw_text
    on annotations_annotation, populating search_vector with
    to_tsvector('english', COALESCE(raw_text, '')).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create_user(
            username="trigger_user",
            password="testpass",
            email="trigger@example.com",
        )
        cls.doc = Document.objects.create(
            title="Trigger Test Doc",
            creator=cls.user,
            is_public=True,
        )

    def _get_search_vector_raw(self, annotation_id: int) -> Optional[str]:
        """Fetch the raw search_vector text for an annotation directly from DB."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT search_vector::text FROM annotations_annotation WHERE id = %s",
                [annotation_id],
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def test_trigger_populates_on_insert(self):
        """INSERT should auto-populate search_vector via the trigger."""
        ann = Annotation.objects.create(
            document=self.doc,
            creator=self.user,
            raw_text="Contractual obligations for indemnification coverage",
            is_public=True,
        )
        sv = self._get_search_vector_raw(ann.id)
        self.assertIsNotNone(sv, "search_vector should be populated on INSERT")
        # Verify stemmed terms are present (English tsvector stems words)
        self.assertIn("contract", sv, "Expected stemmed 'contractual' -> 'contract'")
        self.assertIn("oblig", sv, "Expected stemmed 'obligations' -> 'oblig'")
        self.assertIn(
            "indemnif", sv, "Expected stemmed 'indemnification' -> 'indemnif'"
        )

    def test_trigger_updates_on_raw_text_change(self):
        """UPDATE of raw_text should refresh search_vector via the trigger."""
        ann = Annotation.objects.create(
            document=self.doc,
            creator=self.user,
            raw_text="Initial placeholder text",
            is_public=True,
        )
        sv_initial = self._get_search_vector_raw(ann.id)
        # English stemmer reduces "placeholder" -> "placehold"
        self.assertIn("placehold", sv_initial)

        # Update raw_text via QuerySet.update to ensure the DB trigger fires
        # without any Django model-layer interference.
        Annotation.objects.filter(pk=ann.pk).update(
            raw_text="Revised termination clause with penalty provisions"
        )

        sv_updated = self._get_search_vector_raw(ann.id)
        self.assertNotEqual(sv_initial, sv_updated, "search_vector should change")
        self.assertIn("termin", sv_updated, "Expected stemmed 'termination'")
        self.assertIn("penalti", sv_updated, "Expected stemmed 'penalty' -> 'penalti'")

    def test_trigger_handles_null_raw_text(self):
        """INSERT with NULL raw_text should produce a valid (empty) tsvector."""
        ann = Annotation.objects.create(
            document=self.doc,
            creator=self.user,
            raw_text=None,
            is_public=True,
        )
        sv = self._get_search_vector_raw(ann.id)
        # COALESCE(NULL, '') -> '' -> empty tsvector
        self.assertIsNotNone(
            sv, "search_vector should not be NULL even with NULL raw_text"
        )

    def test_trigger_handles_empty_raw_text(self):
        """INSERT with empty raw_text should produce a valid (empty) tsvector."""
        ann = Annotation.objects.create(
            document=self.doc,
            creator=self.user,
            raw_text="",
            is_public=True,
        )
        sv = self._get_search_vector_raw(ann.id)
        self.assertIsNotNone(sv, "search_vector should exist for empty raw_text")
        # Empty raw_text produces an empty tsvector (no lexemes)
        sv_stripped = sv.strip() if sv else ""
        self.assertEqual(sv_stripped, "", "Empty raw_text should yield empty tsvector")
