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
from unittest.mock import patch

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
