import random
from typing import Optional
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
    VectorSearchResult,
)

User = get_user_model()


def random_vector(dimension: int = 384, seed: Optional[int] = None) -> list[float]:
    """
    Generates a random vector of the specified dimension.
    Optionally accepts a seed to ensure reproducibility.
    """
    rng = random.Random(seed)
    return [rng.random() for _ in range(dimension)]


def constant_vector(dimension: int = 384, value: float = 0.5) -> list[float]:
    """
    Generates a constant vector of a given dimension (default 384).
    Useful to simulate a dummy query vector of the correct dimension.
    """
    return [value] * dimension


class TestCoreAnnotationVectorStore(TestCase):
    """
    A test suite for the CoreAnnotationVectorStore class,
    particularly focusing on the new generate_embeddings_from_text,
    search_by_embedding patterns, and ensuring that we handle:
      - user ID filtering
      - corpus ID filtering
      - document ID filtering
      - partial text matching
      - annotation label metadata filters
      - direct query embedding usage
      - generated query embedding usage (via query_text)
    """

    @classmethod
    def setUpTestData(cls) -> None:
        """
        Create a user, a corpus, documents, and annotations with embeddings
        to support the tests. We'll use our updated code that adds embeddings
        for these objects, thus ensuring we can retrieve them by vector queries.
        """

        with transaction.atomic():
            cls.user = User.objects.create_user(
                username="testuser",
                password="testpass",
                email="testuser@example.com",
            )

            cls.corpus = Corpus.objects.create(
                title="Test Corpus for DAVA",
                creator=cls.user,
                is_public=True,
            )

            cls.doc1 = Document.objects.create(
                title="Document One",
                corpus=cls.corpus,
                creator=cls.user,
                is_public=True,
            )

            cls.doc2 = Document.objects.create(
                title="Document Two",
                corpus=cls.corpus,
                creator=cls.user,
                is_public=True,
            )

            # Create DocumentPath records to link documents to corpus
            DocumentPath.objects.create(
                document=cls.doc1,
                corpus=cls.corpus,
                path="/document_one.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
                creator=cls.user,
            )
            DocumentPath.objects.create(
                document=cls.doc2,
                corpus=cls.corpus,
                path="/document_two.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
                creator=cls.user,
            )

            # Labels
            cls.label_important = AnnotationLabel.objects.create(
                text="Important Label",
                creator=cls.user,
            )
            cls.label_minor = AnnotationLabel.objects.create(
                text="Minor Label",
                creator=cls.user,
            )

            # Annotations
            cls.anno1 = Annotation.objects.create(
                document=cls.doc1,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="This is the first annotation text for doc1",
                annotation_label=cls.label_important,
                is_public=True,
            )
            cls.anno2 = Annotation.objects.create(
                document=cls.doc1,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="Another annotation text, minor label, on doc1",
                annotation_label=cls.label_minor,
                is_public=True,
            )
            cls.anno3 = Annotation.objects.create(
                document=cls.doc2,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="Annotation text for doc2, important label",
                annotation_label=cls.label_important,
                is_public=True,
            )
            cls.anno4 = Annotation.objects.create(
                document=cls.doc2,
                corpus=cls.corpus,
                creator=cls.user,
                raw_text="Just some random text in doc2 with no label set",
                annotation_label=None,
                is_public=True,
            )

        # Add embeddings (384 dimension) to anno1, anno2, anno3; skip anno4 to confirm no-embed.
        dim = 384
        cls.anno1.add_embedding(
            "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
            constant_vector(dim, 0.1),
        )
        cls.anno2.add_embedding(
            "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
            constant_vector(dim, 0.2),
        )
        cls.anno3.add_embedding(
            "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
            constant_vector(dim, 0.3),
        )
        # no embedding for anno4

    def setUp(self) -> None:
        """
        Instantiate a CoreAnnotationVectorStore each test with default filters.
        """
        self.vector_store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            document_id=None,
            must_have_text=None,
        )

    def run_search_query(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        """
        Helper to call the .search method.
        """
        return self.vector_store.search(query)

    def test_search_with_no_vector(self) -> None:
        """
        If we do a search without specifying either query_embedding or query_text,
        just retrieve all matching annotations for the corpus (and user) with no doc_id.
        """
        query = VectorSearchQuery(
            query_embedding=None, query_text=None, similarity_top_k=10
        )
        results = self.run_search_query(query)
        self.assertEqual(
            len(results),
            4,
            "Should return all four annotations (no embedding filter).",
        )

    def test_search_with_document_filter(self) -> None:
        """
        Verifies specifying document_id in the vector store's init filters
        yields only that doc's annotations.
        """
        store_doc1 = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            document_id=self.doc1.id,
        )
        query = VectorSearchQuery(
            query_embedding=None, query_text=None, similarity_top_k=10
        )
        results = store_doc1.search(query)
        self.assertEqual(
            len(results), 2, "Should have exactly 2 annotations from doc1."
        )
        texts = [result.annotation.raw_text for result in results]
        self.assertTrue(any("first annotation text" in t for t in texts))
        self.assertTrue(any("Another annotation" in t for t in texts))

    def test_search_with_text_filter(self) -> None:
        """
        Using must_have_text substring search in the store's init.
        """
        store_text_filter = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            must_have_text="Another",
        )
        query = VectorSearchQuery(
            query_embedding=None, query_text=None, similarity_top_k=10
        )
        results = store_text_filter.search(query)
        self.assertEqual(len(results), 1, "Only anno2 matches the substring 'Another'.")
        self.assertIn(
            "Another annotation text, minor label, on doc1",
            results[0].annotation.raw_text,
        )

    @override_settings(
        DEFAULT_EMBEDDER="opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder"  # noqa: E501
    )
    def test_search_by_vector_similarity_explicit_embedding(self) -> None:
        """
        Provide an explicit query embedding. Expect to see only annotations with embeddings
        (anno1, 2, 3) in ascending distance order, limited by top_k.
        """
        query_vec = constant_vector(384, value=0.25)
        query = VectorSearchQuery(query_embedding=query_vec, similarity_top_k=3)
        results = self.run_search_query(query)

        # Because the dimension is 384, we only expect anno1,2,3 to appear. Anno4 has no embedding.
        returned_ids = {result.annotation.id for result in results}
        self.assertNotIn(
            self.anno4.id,
            returned_ids,
            "anno4 has no embedding, shouldn't appear.",
        )
        self.assertIn(self.anno1.id, returned_ids)
        self.assertIn(self.anno2.id, returned_ids)
        self.assertIn(self.anno3.id, returned_ids)

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_search_by_vector_similarity_generated_from_query_text(
        self, mock_gen_embeds
    ):
        """
        Provide query_text instead of explicit embedding. The vector store should
        call generate_embeddings_from_text internally.
        """
        # Mock the embedding generation to return a known vector
        expected_vector = constant_vector(384, value=0.15)
        mock_gen_embeds.return_value = (
            "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
            expected_vector,
        )

        query = VectorSearchQuery(
            query_embedding=None, query_text="test query", similarity_top_k=3
        )
        results = self.run_search_query(query)

        # Verify the embedding generation was called
        mock_gen_embeds.assert_called_once_with(
            "test query",
            embedder_path=self.vector_store.embedder_path,
        )

        # Should return annotations with embeddings
        returned_ids = {result.annotation.id for result in results}
        self.assertNotIn(self.anno4.id, returned_ids, "anno4 has no embedding")

    def test_search_with_label_metadata_filter(self) -> None:
        """
        Ensures we can filter by annotation_label text via the VectorSearchQuery filters.
        """
        filters = {"annotation_label": "Important Label"}
        query = VectorSearchQuery(
            query_embedding=None, query_text=None, filters=filters, similarity_top_k=10
        )

        results = self.run_search_query(query)
        returned_texts = [result.annotation.raw_text for result in results]

        # anno1, anno3 both have "Important Label"
        self.assertEqual(
            len(returned_texts),
            2,
            "We expect exactly 2 annotations with label=Important Label.",
        )
        self.assertTrue(any("first annotation text" in txt for txt in returned_texts))
        self.assertTrue(any("doc2, important label" in txt for txt in returned_texts))

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_search_query_text_fallback_when_no_embedding(self, mock_gen_embeds):
        """
        If a user calls a search with query_text but the dimension is unsupported or generate_embeddings
        fails (None, None), we should just return results with no vector-based ordering.
        """
        # Return (None, None) from generate_embeddings_from_text so the vector store
        # can't do a similarity search and must fallback.
        mock_gen_embeds.return_value = (None, None)

        query = VectorSearchQuery(
            query_embedding=None, query_text="some text", similarity_top_k=3
        )
        results = self.run_search_query(query)
        self.assertEqual(
            len(results),
            3,
            "Should return top 3 annotations with fallback filtering.",
        )

    def test_batch_add_embeddings_and_corpus_exclusion(self) -> None:
        """
        1) Demonstrates adding embeddings in batch via add_embeddings().
        2) Ensures that annotations belonging to a different corpus
           are excluded from searches restricted to self.corpus.
        """
        # Create a separate corpus for testing exclusion
        other_corpus = Corpus.objects.create(
            title="Unrelated Corpus",
            creator=self.user,
            is_public=True,
        )

        # Create a new annotation in cls.corpus
        new_annotation_in_corpus = Annotation.objects.create(
            document=self.doc1,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Batch-embedded annotation in the existing test corpus",
            annotation_label=self.label_important,
            is_public=True,
        )

        # Create an annotation in the other_corpus
        annotation_other_corpus = Annotation.objects.create(
            document=self.doc1,
            corpus=other_corpus,
            creator=self.user,
            raw_text="Annotation in a different corpus",
            annotation_label=self.label_important,
            is_public=True,
        )

        # Add multiple embeddings in a single batch for each annotation
        vectors_for_batch = [
            constant_vector(384, 0.45),
            constant_vector(384, 0.55),
        ]
        new_annotation_in_corpus.add_embeddings(
            "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
            vectors_for_batch,
        )
        annotation_other_corpus.add_embeddings(
            "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
            vectors_for_batch,
        )

        # Instantiate a vector store restricted to self.corpus
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            document_id=None,
            must_have_text=None,
        )

        # Submit a vector-based query
        query_vec = constant_vector(384, value=0.50)
        query = VectorSearchQuery(query_embedding=query_vec, similarity_top_k=10)
        results = store.search(query)

        returned_ids = {result.annotation.id for result in results}

        # Annotation in self.corpus should appear
        self.assertIn(
            new_annotation_in_corpus.id,
            returned_ids,
            "Expected in-corpus annotation to be retrieved.",
        )

        # Annotation in other_corpus should not appear
        self.assertNotIn(
            annotation_other_corpus.id,
            returned_ids,
            "Annotation from a different corpus must be excluded.",
        )

    def test_similarity_scores_in_results(self) -> None:
        """
        Test that similarity scores are properly included in search results.
        """
        query_vec = constant_vector(384, value=0.25)
        query = VectorSearchQuery(query_embedding=query_vec, similarity_top_k=3)
        results = self.run_search_query(query)

        # Check that all results have similarity scores
        for result in results:
            self.assertIsInstance(result.similarity_score, float)
            self.assertTrue(0.0 <= result.similarity_score <= 1.0)

    def test_empty_corpus_search(self) -> None:
        """
        Test searching in a corpus with no annotations.
        """
        empty_corpus = Corpus.objects.create(
            title="Empty Corpus",
            creator=self.user,
            is_public=True,
        )

        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=empty_corpus.id,
        )

        query = VectorSearchQuery(query_text="any text", similarity_top_k=10)
        results = store.search(query)

        self.assertEqual(len(results), 0, "Empty corpus should return no results")

    def test_user_filtering(self) -> None:
        """
        Test that user filtering works correctly.
        """
        # Create another user and annotation
        other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="otherpass123"
        )

        other_annotation = Annotation.objects.create(
            document=self.doc1,
            corpus=self.corpus,
            creator=other_user,
            raw_text="Annotation by other user",
            is_public=True,
        )

        # Search with user filter
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
        )

        query = VectorSearchQuery(similarity_top_k=10)
        results = store.search(query)

        returned_ids = {result.annotation.id for result in results}
        self.assertNotIn(
            other_annotation.id,
            returned_ids,
            "Other user's annotation should be filtered out",
        )
