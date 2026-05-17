"""
Tests for EmbeddingManager in opencontractserver/shared/Managers.py

Covers:
- store_embedding ValueError when no parent ID provided (line 398)
- store_embedding IntegrityError race condition handling (lines 432-442)
- Concurrent store_embedding race condition with ThreadPoolExecutor
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import Embedding
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH
from opencontractserver.users.models import User


class EmbeddingManagerStoreEmbeddingTest(TestCase):
    """Tests for EmbeddingManager.store_embedding method."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(
            username="embedding_manager_test_user",
            email="embedding_manager_test@test.com",
            password="testpassword",
        )

    def setUp(self):
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
        )
        with open(SAMPLE_PDF_FILE_TWO_PATH, "rb") as f:
            pdf_content = f.read()
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.user,
            pdf_file=SimpleUploadedFile(
                "test.pdf", pdf_content, content_type="application/pdf"
            ),
            backend_lock=False,
        )
        self.corpus.add_document(document=self.document, user=self.user)

    def tearDown(self):
        Embedding.objects.filter(embedder_path__startswith="test.").delete()
        self.document.delete()
        self.corpus.delete()

    def test_store_embedding_no_parent_id_raises_value_error(self):
        """
        Test that store_embedding raises ValueError when no parent ID is provided.

        Covers line 398 in Managers.py.
        """
        with self.assertRaises(ValueError) as context:
            Embedding.objects.store_embedding(
                creator=self.user,
                embedder_path="test.embedder",
                vector=[0.1] * 384,
                dimension=384,
                # No parent ID provided - should raise ValueError
            )

        self.assertIn(
            "Must provide exactly one of document_id, annotation_id, note_id, "
            "conversation_id, message_id, or relationship_id",
            str(context.exception),
        )

    def test_store_embedding_multiple_parent_ids_raises_value_error(self):
        """Two parent FKs is just as wrong as zero — both must be rejected."""
        with self.assertRaises(ValueError) as context:
            Embedding.objects.store_embedding(
                creator=self.user,
                embedder_path="test.embedder",
                vector=[0.1] * 384,
                dimension=384,
                document_id=self.document.id,
                annotation_id=12345,
            )
        self.assertIn(
            "Must provide exactly one of",
            str(context.exception),
        )

    def test_store_embedding_race_condition_integrity_error(self):
        """
        Test that store_embedding handles IntegrityError from race conditions.

        When a concurrent worker creates the same embedding between our check
        and create, we catch IntegrityError and update the existing record.

        Covers lines 432-442 in Managers.py.
        """
        embedder_path = "test.race_condition_embedder"
        vector_1 = [0.1] * 384
        vector_2 = [0.2] * 384

        # First, create an embedding normally
        embedding1 = Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector_1,
            dimension=384,
            document_id=self.document.id,
        )
        self.assertIsNotNone(embedding1)

        # Now simulate a race condition: patch filter().first() to return None
        # (simulating a check that misses the existing record) but then
        # create() will fail with IntegrityError because the record exists
        def mock_filter_then_fail(*args, **kwargs):
            """
            Return a mock queryset that returns None on first() to simulate
            the race condition where filter misses the existing record.
            """
            mock_qs = MagicMock()
            mock_qs.first.return_value = None
            return mock_qs

        with patch.object(
            Embedding.objects, "filter", side_effect=mock_filter_then_fail
        ):
            with patch.object(
                Embedding.objects,
                "create",
                side_effect=IntegrityError("duplicate key"),
            ):
                with patch.object(Embedding.objects, "get", return_value=embedding1):
                    # This should catch IntegrityError and update existing
                    result = Embedding.objects.store_embedding(
                        creator=self.user,
                        embedder_path=embedder_path,
                        vector=vector_2,
                        dimension=384,
                        document_id=self.document.id,
                    )

        # Should return the existing embedding (now updated)
        self.assertEqual(result.id, embedding1.id)
        # The vector should have been updated
        self.assertEqual(list(result.vector_384), vector_2)


class EmbeddingManagerConcurrentTest(TransactionTestCase):
    """
    Test concurrent access to EmbeddingManager.store_embedding.

    Uses TransactionTestCase because we need real database transactions
    for concurrent thread access to properly test race conditions.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create user in setUpClass to avoid recreation per test
        cls.user = User.objects.create_user(
            username="embedding_concurrent_test_user",
            email="embedding_concurrent_test@test.com",
            password="testpassword",
        )

    def setUp(self):
        self.corpus = Corpus.objects.create(
            title="Test Corpus Concurrent",
            creator=self.user,
        )
        with open(SAMPLE_PDF_FILE_TWO_PATH, "rb") as f:
            pdf_content = f.read()
        self.document = Document.objects.create(
            title="Test Document Concurrent",
            creator=self.user,
            pdf_file=SimpleUploadedFile(
                "test_concurrent.pdf", pdf_content, content_type="application/pdf"
            ),
            backend_lock=False,
        )
        self.corpus.add_document(document=self.document, user=self.user)

    def tearDown(self):
        Embedding.objects.filter(embedder_path__startswith="test.concurrent").delete()
        self.document.delete()
        self.corpus.delete()

    def test_concurrent_store_embedding_no_duplicates(self):
        """
        Test that concurrent store_embedding calls don't create duplicates.

        Multiple threads attempt to create the same embedding simultaneously.
        The unique constraint + IntegrityError handling should ensure only
        one embedding exists at the end.
        """
        embedder_path = "test.concurrent.embedder"
        num_workers = 5
        results = []
        errors = []
        barrier = threading.Barrier(num_workers)

        def worker(worker_id):
            """Each worker tries to store the same embedding."""
            try:
                # Close any inherited connections
                close_old_connections()

                # Wait for all workers to be ready (maximize collision chance)
                barrier.wait()

                # All workers try to store the same embedding
                vector = [0.1 * worker_id] * 384
                result = Embedding.objects.store_embedding(
                    creator=self.user,
                    embedder_path=embedder_path,
                    vector=vector,
                    dimension=384,
                    document_id=self.document.id,
                )
                return ("success", worker_id, result.id)
            except Exception as e:
                return ("error", worker_id, str(e))
            finally:
                close_old_connections()

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker, i) for i in range(num_workers)]
            for future in as_completed(futures):
                result = future.result()
                if result[0] == "success":
                    results.append(result)
                else:
                    errors.append(result)

        # All workers should succeed (no unhandled exceptions)
        self.assertEqual(
            len(errors),
            0,
            f"Some workers failed with errors: {errors}",
        )
        self.assertEqual(
            len(results),
            num_workers,
            f"Expected {num_workers} successful results, got {len(results)}",
        )

        # All workers should have returned the same embedding ID
        embedding_ids = {r[2] for r in results}
        self.assertEqual(
            len(embedding_ids),
            1,
            f"Expected all workers to return same embedding ID, got: {embedding_ids}",
        )

        # Verify only one embedding exists in the database
        embedding_count = Embedding.objects.filter(
            embedder_path=embedder_path,
            document_id=self.document.id,
        ).count()
        self.assertEqual(
            embedding_count,
            1,
            f"Expected exactly 1 embedding, found {embedding_count}",
        )


class EmbeddingManager2048DimensionTest(TestCase):
    """
    Tests for 2048-dimensional embedding support in EmbeddingManager.

    Covers the 2048 dimension branches added in commit f790fdb5:
    - Managers.py lines 363-364: _get_vector_field_name returning "vector_2048"
    - mixins.py lines 37-38: _dimension_to_field returning "embedding_set__vector_2048"
    - mixins.py lines 144-145: get_embedding looking up vector_2048
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(
            username="embedding_2048_test_user",
            email="embedding_2048_test@test.com",
            password="testpassword",
        )

    def setUp(self):
        self.corpus = Corpus.objects.create(
            title="Test Corpus 2048",
            creator=self.user,
        )
        with open(SAMPLE_PDF_FILE_TWO_PATH, "rb") as f:
            pdf_content = f.read()
        self.document = Document.objects.create(
            title="Test Document 2048",
            creator=self.user,
            pdf_file=SimpleUploadedFile(
                "test_2048.pdf", pdf_content, content_type="application/pdf"
            ),
            backend_lock=False,
        )
        self.corpus.add_document(document=self.document, user=self.user)

    def tearDown(self):
        Embedding.objects.filter(embedder_path__startswith="test.2048").delete()
        self.document.delete()
        self.corpus.delete()

    def test_store_embedding_2048_dimension(self):
        """
        Test that store_embedding correctly handles 2048-dimensional vectors.

        Covers Managers.py lines 363-364: _get_vector_field_name returning "vector_2048"
        """
        embedder_path = "test.2048.embedder"
        vector = [0.1] * 2048

        embedding = Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector,
            dimension=2048,
            document_id=self.document.id,
        )

        self.assertIsNotNone(embedding)
        self.assertIsNotNone(embedding.vector_2048)
        self.assertEqual(len(embedding.vector_2048), 2048)
        self.assertEqual(list(embedding.vector_2048), vector)

    def test_get_embedding_2048_dimension(self):
        """
        Test that get_embedding correctly retrieves 2048-dimensional vectors.

        Covers mixins.py lines 144-145: get_embedding looking up vector_2048
        """
        embedder_path = "test.2048.get_embedder"
        vector = [0.2] * 2048

        # Store the embedding first
        Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector,
            dimension=2048,
            document_id=self.document.id,
        )

        # Retrieve using get_embedding from HasEmbeddingMixin
        retrieved = self.document.get_embedding(embedder_path, dimension=2048)

        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved), 2048)
        # Convert to list for comparison (pgvector returns numpy array)
        self.assertEqual(list(retrieved), vector)

    def test_search_by_embedding_2048_dimension(self):
        """
        Test that search_by_embedding works with 2048-dimensional vectors.

        Covers mixins.py lines 37-38: _dimension_to_field returning
        "{EMBEDDING_RELATED_NAME}__vector_2048"
        """
        embedder_path = "test.2048.search_embedder"
        vector = [0.3] * 2048

        # Store the embedding
        Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector,
            dimension=2048,
            document_id=self.document.id,
        )

        # Search using 2048-dimensional query vector
        query_vector = [0.3] * 2048
        results = Document.objects.search_by_embedding(
            query_vector=query_vector,
            embedder_path=embedder_path,
            top_k=10,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, self.document.id)
        # Cosine similarity should be 1.0 for identical vectors (1 - distance)
        self.assertAlmostEqual(results[0].similarity_score, 1.0, places=5)


class HasEmbeddingMixinDimensionTest(TestCase):
    """
    Tests for HasEmbeddingMixin.get_embedding across all supported dimensions.

    Covers the dimension branches in mixins.py get_embedding method:
    - Line 139: vector_768
    - Line 141: vector_1024
    - Line 143: vector_1536
    - Line 146: vector_3072
    - Line 148-149: vector_4096
    - Line 151: unsupported dimension ValueError
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(
            username="mixin_dimension_test_user",
            email="mixin_dimension_test@test.com",
            password="testpassword",
        )

    def setUp(self):
        self.corpus = Corpus.objects.create(
            title="Test Corpus Mixin",
            creator=self.user,
        )
        with open(SAMPLE_PDF_FILE_TWO_PATH, "rb") as f:
            pdf_content = f.read()
        self.document = Document.objects.create(
            title="Test Document Mixin",
            creator=self.user,
            pdf_file=SimpleUploadedFile(
                "test_mixin.pdf", pdf_content, content_type="application/pdf"
            ),
            backend_lock=False,
        )
        self.corpus.add_document(document=self.document, user=self.user)

    def tearDown(self):
        Embedding.objects.filter(embedder_path__startswith="test.mixin").delete()
        self.document.delete()
        self.corpus.delete()

    def test_get_embedding_768_dimension(self):
        """
        Test get_embedding correctly retrieves 768-dimensional vectors.

        Covers mixins.py line 139: vector_field = "vector_768"
        """
        embedder_path = "test.mixin.768"
        vector = [0.1] * 768

        Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector,
            dimension=768,
            document_id=self.document.id,
        )

        retrieved = self.document.get_embedding(embedder_path, dimension=768)
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved), 768)
        self.assertEqual(list(retrieved), vector)

    def test_get_embedding_1024_dimension(self):
        """
        Test get_embedding correctly retrieves 1024-dimensional vectors.

        Covers mixins.py line 141: vector_field = "vector_1024"
        """
        embedder_path = "test.mixin.1024"
        vector = [0.2] * 1024

        Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector,
            dimension=1024,
            document_id=self.document.id,
        )

        retrieved = self.document.get_embedding(embedder_path, dimension=1024)
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved), 1024)
        self.assertEqual(list(retrieved), vector)

    def test_get_embedding_1536_dimension(self):
        """
        Test get_embedding correctly retrieves 1536-dimensional vectors.

        Covers mixins.py line 143: vector_field = "vector_1536"
        """
        embedder_path = "test.mixin.1536"
        vector = [0.3] * 1536

        Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector,
            dimension=1536,
            document_id=self.document.id,
        )

        retrieved = self.document.get_embedding(embedder_path, dimension=1536)
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved), 1536)
        self.assertEqual(list(retrieved), vector)

    def test_get_embedding_3072_dimension(self):
        """
        Test get_embedding correctly retrieves 3072-dimensional vectors.

        Covers mixins.py line 146: vector_field = "vector_3072"
        """
        embedder_path = "test.mixin.3072"
        vector = [0.4] * 3072

        Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector,
            dimension=3072,
            document_id=self.document.id,
        )

        retrieved = self.document.get_embedding(embedder_path, dimension=3072)
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved), 3072)
        self.assertEqual(list(retrieved), vector)

    def test_get_embedding_4096_dimension(self):
        """
        Test get_embedding correctly retrieves 4096-dimensional vectors.

        Covers mixins.py lines 148-149: vector_field = "vector_4096"
        """
        embedder_path = "test.mixin.4096"
        vector = [0.5] * 4096

        Embedding.objects.store_embedding(
            creator=self.user,
            embedder_path=embedder_path,
            vector=vector,
            dimension=4096,
            document_id=self.document.id,
        )

        retrieved = self.document.get_embedding(embedder_path, dimension=4096)
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved), 4096)
        self.assertEqual(list(retrieved), vector)

    def test_get_embedding_unsupported_dimension_raises_error(self):
        """
        Test get_embedding raises ValueError for unsupported dimensions.

        Covers mixins.py line 151: raise ValueError
        """
        with self.assertRaises(ValueError) as context:
            self.document.get_embedding("test.mixin.unsupported", dimension=512)

        self.assertIn("Unsupported embedding dimension: 512", str(context.exception))
