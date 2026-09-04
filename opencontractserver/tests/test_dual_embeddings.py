"""
Tests for the dual embedding strategy.

The dual embedding strategy ensures:
1. Every annotation ALWAYS gets a default embedder embedding (for global search)
2. If corpus has a different preferred_embedder, annotation ALSO gets corpus-specific embedding
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.utils import get_default_embedder_path
from opencontractserver.tasks.embeddings_task import (
    _apply_dual_embedding_strategy,
    _create_text_embedding,
    calculate_embedding_for_annotation_text,
)
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.users.models import User


class MockEmbedder:
    """Mock embedder for testing."""

    vector_size = 768
    is_multimodal = False
    supports_images = False

    def embed_text(self, text: str, **kwargs) -> list[float]:
        """Return a mock embedding vector."""
        return [0.1] * 768


class MockCorpusEmbedder:
    """Mock corpus-specific embedder for testing."""

    vector_size = 768
    is_multimodal = False
    supports_images = False

    def embed_text(self, text: str, **kwargs) -> list[float]:
        """Return a different mock embedding vector."""
        return [0.2] * 768


class TestDualEmbeddingHelpers(TestCase):
    """Test helper functions for dual embedding strategy."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    def test_apply_dual_embedding_no_corpus(self, mock_get_component, mock_get_default):
        """Test dual embedding with no corpus - should only create default embedding."""
        mock_get_default.return_value = MockEmbedder

        # Create a mock object with HasEmbeddingMixin
        mock_obj = MagicMock()
        mock_obj.add_embedding = MagicMock(return_value=MagicMock())

        # Create a simple embed function that tracks calls
        embed_calls = []

        def track_embed_func(obj, embedder, embedder_path):
            embed_calls.append(embedder_path)
            obj.add_embedding(embedder_path, embedder.embed_text("test"))
            return True

        _apply_dual_embedding_strategy(
            obj=mock_obj,
            text="test text",
            corpus_id=None,
            obj_type="test",
            obj_id=1,
            embed_func=track_embed_func,
        )

        # Should only call default embedder
        self.assertEqual(len(embed_calls), 1)
        self.assertEqual(embed_calls[0], get_default_embedder_path())

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    def test_apply_dual_embedding_corpus_same_embedder(
        self, mock_get_component, mock_get_default
    ):
        """Test dual embedding when corpus uses same embedder as default."""
        mock_get_default.return_value = MockEmbedder

        # Create corpus with default embedder
        corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            preferred_embedder=get_default_embedder_path(),  # Same as default
        )

        mock_obj = MagicMock()
        mock_obj.add_embedding = MagicMock(return_value=MagicMock())

        embed_calls = []

        def track_embed_func(obj, embedder, embedder_path):
            embed_calls.append(embedder_path)
            obj.add_embedding(embedder_path, embedder.embed_text("test"))
            return True

        _apply_dual_embedding_strategy(
            obj=mock_obj,
            text="test text",
            corpus_id=corpus.id,
            obj_type="test",
            obj_id=1,
            embed_func=track_embed_func,
        )

        # Should only call default embedder (corpus uses same)
        self.assertEqual(len(embed_calls), 1)
        self.assertEqual(embed_calls[0], get_default_embedder_path())

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    def test_apply_dual_embedding_corpus_different_embedder(
        self, mock_get_component, mock_get_default
    ):
        """Test dual embedding when corpus uses different embedder."""
        mock_get_default.return_value = MockEmbedder
        mock_get_component.return_value = MockCorpusEmbedder

        custom_embedder_path = "custom.embedder.path"

        # Create corpus with custom embedder
        corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            preferred_embedder=custom_embedder_path,
        )

        mock_obj = MagicMock()
        mock_obj.add_embedding = MagicMock(return_value=MagicMock())

        embed_calls = []

        def track_embed_func(obj, embedder, embedder_path):
            embed_calls.append(embedder_path)
            obj.add_embedding(embedder_path, embedder.embed_text("test"))
            return True

        _apply_dual_embedding_strategy(
            obj=mock_obj,
            text="test text",
            corpus_id=corpus.id,
            obj_type="test",
            obj_id=1,
            embed_func=track_embed_func,
        )

        # Should call both default and corpus embedder
        self.assertEqual(len(embed_calls), 2)
        self.assertIn(get_default_embedder_path(), embed_calls)
        self.assertIn(custom_embedder_path, embed_calls)

    def test_apply_dual_embedding_empty_text(self):
        """Test dual embedding with empty text - should skip embedding."""
        mock_obj = MagicMock()
        mock_obj.add_embedding = MagicMock(return_value=MagicMock())

        embed_calls = []

        def track_embed_func(obj, embedder, embedder_path):
            embed_calls.append(embedder_path)
            return True

        _apply_dual_embedding_strategy(
            obj=mock_obj,
            text="",  # Empty text
            corpus_id=None,
            obj_type="test",
            obj_id=1,
            embed_func=track_embed_func,
        )

        # Should not call any embedder
        self.assertEqual(len(embed_calls), 0)
        mock_obj.add_embedding.assert_not_called()


class TestCreateTextEmbedding(TestCase):
    """Test the _create_text_embedding helper function."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_create_text_embedding_empty_text(self):
        """Test that empty text returns False."""
        mock_obj = MagicMock()
        mock_embedder = MockEmbedder()

        result = _create_text_embedding(
            obj=mock_obj,
            embedder=mock_embedder,
            embedder_path="test.embedder",
            text="",
            obj_type="test",
            obj_id=1,
        )

        self.assertFalse(result)
        mock_obj.add_embedding.assert_not_called()

    def test_create_text_embedding_whitespace_text(self):
        """Test that whitespace-only text returns False."""
        mock_obj = MagicMock()
        mock_embedder = MockEmbedder()

        result = _create_text_embedding(
            obj=mock_obj,
            embedder=mock_embedder,
            embedder_path="test.embedder",
            text="   \n\t  ",
            obj_type="test",
            obj_id=1,
        )

        self.assertFalse(result)
        mock_obj.add_embedding.assert_not_called()

    def test_create_text_embedding_success(self):
        """Test successful text embedding creation."""
        mock_obj = MagicMock()
        mock_obj.add_embedding = MagicMock(return_value=MagicMock())
        mock_embedder = MockEmbedder()

        result = _create_text_embedding(
            obj=mock_obj,
            embedder=mock_embedder,
            embedder_path="test.embedder",
            text="This is test text",
            obj_type="test",
            obj_id=1,
        )

        self.assertTrue(result)
        mock_obj.add_embedding.assert_called_once()
        call_args = mock_obj.add_embedding.call_args
        self.assertEqual(call_args[0][0], "test.embedder")
        self.assertEqual(len(call_args[0][1]), 768)  # Vector dimension


class TestAnnotationEmbeddingTask(TestCase):
    """Test the calculate_embedding_for_annotation_text task."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

        # Create a document
        with open(SAMPLE_PDF_FILE_ONE_PATH, "rb") as f:
            from django.core.files.base import ContentFile

            self.document = Document.objects.create(
                title="Test Document",
                creator=self.user,
                pdf_file=ContentFile(f.read(), name="test.pdf"),
            )

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    def test_annotation_embedding_no_corpus(self, mock_get_component, mock_get_default):
        """Test annotation embedding without corpus."""
        mock_get_default.return_value = MockEmbedder

        # Create annotation
        annotation = Annotation.objects.create(
            document=self.document,
            creator=self.user,
            raw_text="Test annotation text",
            page=1,
        )

        # Run embedding task
        calculate_embedding_for_annotation_text(annotation.id)

        # Check that default embedding was created
        self.assertTrue(
            annotation.embedding_set.filter(
                embedder_path=get_default_embedder_path()
            ).exists()
        )

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    def test_annotation_embedding_with_corpus_different_embedder(
        self, mock_get_component, mock_get_default
    ):
        """Test annotation embedding with corpus using different embedder."""
        mock_get_default.return_value = MockEmbedder
        mock_get_component.return_value = MockCorpusEmbedder

        custom_embedder_path = "custom.embedder.path"

        # Create corpus with custom embedder
        corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            preferred_embedder=custom_embedder_path,
        )

        # Create annotation with corpus
        annotation = Annotation.objects.create(
            document=self.document,
            corpus=corpus,
            creator=self.user,
            raw_text="Test annotation text",
            page=1,
        )

        # Run embedding task with corpus_id
        calculate_embedding_for_annotation_text(annotation.id, corpus_id=corpus.id)

        # Check that both embeddings were created
        embeddings = annotation.embedding_set.all()
        embedder_paths = {e.embedder_path for e in embeddings}

        self.assertIn(get_default_embedder_path(), embedder_paths)
        self.assertIn(custom_embedder_path, embedder_paths)
        self.assertEqual(len(embedder_paths), 2)

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    def test_annotation_embedding_with_explicit_path(
        self, mock_get_component, mock_get_default
    ):
        """Test annotation embedding with explicit embedder_path bypasses dual strategy."""
        mock_get_component.return_value = MockCorpusEmbedder

        explicit_path = "explicit.embedder.path"

        # Create annotation with dummy embedding to prevent signal from firing
        annotation = Annotation.objects.create(
            document=self.document,
            creator=self.user,
            raw_text="Test annotation text",
            page=1,
            embedding=[0.1] * 384,  # Dummy embedding to skip signal handler
        )

        # Clear the dummy embedding so the task will actually run
        annotation.embedding = None
        annotation.save(update_fields=["embedding"])
        annotation.embedding_set.all().delete()

        # Run embedding task with explicit embedder_path
        calculate_embedding_for_annotation_text(
            annotation.id, embedder_path=explicit_path
        )

        # Check that only explicit embedder was used
        embeddings = annotation.embedding_set.all()
        self.assertEqual(embeddings.count(), 1)
        self.assertEqual(embeddings[0].embedder_path, explicit_path)

        # Default embedder should NOT have been called
        mock_get_default.assert_not_called()

    def test_annotation_embedding_no_text(self):
        """Test annotation embedding with no text - should not create embeddings."""
        # Create annotation with no text
        annotation = Annotation.objects.create(
            document=self.document,
            creator=self.user,
            raw_text="",  # Empty text
            page=1,
        )

        # Run embedding task
        calculate_embedding_for_annotation_text(annotation.id)

        # No embeddings should be created
        self.assertEqual(annotation.embedding_set.count(), 0)


class TestIdempotentEmbedding(TestCase):
    """Test that embedding creation is idempotent."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

        with open(SAMPLE_PDF_FILE_ONE_PATH, "rb") as f:
            from django.core.files.base import ContentFile

            self.document = Document.objects.create(
                title="Test Document",
                creator=self.user,
                pdf_file=ContentFile(f.read(), name="test.pdf"),
            )

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    def test_running_task_twice_no_duplicate(self, mock_get_default):
        """Running embedding task twice should not create duplicate embeddings."""
        mock_get_default.return_value = MockEmbedder

        # Create annotation
        annotation = Annotation.objects.create(
            document=self.document,
            creator=self.user,
            raw_text="Test annotation text",
            page=1,
        )

        # Run embedding task twice
        calculate_embedding_for_annotation_text(annotation.id)
        calculate_embedding_for_annotation_text(annotation.id)

        # Should still only have one embedding per embedder_path
        default_embeddings = annotation.embedding_set.filter(
            embedder_path=get_default_embedder_path()
        )
        self.assertEqual(default_embeddings.count(), 1)
