import unittest
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model

from opencontractserver.annotations.models import Annotation, Note
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.utils.embeddings import get_embedder

User = get_user_model()


class TestEmbedder(BaseEmbedder):
    """
    A test embedder for unit testing.
    """

    title = "Test Embedder"
    description = "A test embedder for unit testing."
    author = "Test Author"
    dependencies = []
    vector_size = 128
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT]

    def embed_text(self, text: str, **kwargs) -> list[float]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size


class TestEmbedder384(BaseEmbedder):
    """
    A test embedder with 384-dimensional vectors.
    """

    title = "Test Embedder 384"
    description = "A test embedder with 384-dimensional vectors."
    author = "Test Author"
    dependencies = []
    vector_size = 384
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT]

    def embed_text(self, text: str, **kwargs) -> list[float]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size


class TestEmbedder768(BaseEmbedder):
    """
    A test embedder with 768-dimensional vectors.
    """

    title = "Test Embedder 768"
    description = "A test embedder with 768-dimensional vectors."
    author = "Test Author"
    dependencies = []
    vector_size = 768
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT]

    def embed_text(self, text: str, **kwargs) -> list[float]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size


class TestEmbedder1536(BaseEmbedder):
    """
    A test embedder with 1536-dimensional vectors.
    """

    title = "Test Embedder 1536"
    description = "A test embedder with 1536-dimensional vectors."
    author = "Test Author"
    dependencies = []
    vector_size = 1536
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT]

    def embed_text(self, text: str, **kwargs) -> list[float]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size


class TestEmbedder3072(BaseEmbedder):
    """
    A test embedder with 3072-dimensional vectors.
    """

    title = "Test Embedder 3072"
    description = "A test embedder with 3072-dimensional vectors."
    author = "Test Author"
    dependencies = []
    vector_size = 3072
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT]

    def embed_text(self, text: str, **kwargs) -> list[float]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size


class TestEmbeddingsTask(unittest.TestCase):
    """
    Tests for the embeddings task functions.
    """

    @patch("opencontractserver.corpuses.models.Corpus")
    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    @patch("opencontractserver.pipeline.utils.find_embedder_for_filetype")
    @patch("opencontractserver.pipeline.utils.get_default_embedder")
    def test_get_embedder_for_corpus_with_preferred_embedder(
        self,
        mock_get_default,
        mock_find_embedder,
        mock_get_component,
        mock_corpus_model,
    ):
        """
        Test get_embedder when the corpus has a preferred embedder.
        """
        # Set up the mock corpus object with a preferred embedder
        mock_corpus = MagicMock()
        mock_corpus.preferred_embedder = "path.to.TestEmbedder"
        mock_corpus_model.objects.get.return_value = mock_corpus

        # Mock the component lookup to return our test embedder class
        mock_get_component.return_value = TestEmbedder

        # Call the function
        embedder_class, embedder_path = get_embedder(corpus_id=1)

        # Verify the corpus was looked up by ID
        mock_corpus_model.objects.get.assert_called_with(id=1)

        # Verify the embedder class was loaded by path
        mock_get_component.assert_called_with("path.to.TestEmbedder")

        # Verify the fallback methods were not called
        mock_find_embedder.assert_not_called()
        mock_get_default.assert_not_called()

        # Verify the correct results were returned
        self.assertEqual(embedder_class, TestEmbedder)
        self.assertEqual(embedder_path, "path.to.TestEmbedder")

    @patch("opencontractserver.corpuses.models.Corpus")
    @patch("opencontractserver.pipeline.utils.find_embedder_for_filetype")
    @patch("opencontractserver.pipeline.utils.get_default_embedder")
    def test_get_embedder_for_corpus_with_mimetype(
        self, mock_get_default, mock_find_embedder, mock_corpus
    ):
        """
        Test get_embedder_for_corpus when no preferred embedder but mimetype is provided.
        """
        # Set up mocks
        mock_corpus_obj = MagicMock()
        mock_corpus_obj.preferred_embedder = None
        mock_corpus.objects.get.return_value = mock_corpus_obj

        # Mock the embedder lookup
        mock_find_embedder.return_value = TestEmbedder

        # Call the function
        embedder_class, embedder_path = get_embedder(
            corpus_id=1, mimetype_or_enum="application/pdf"
        )

        # Verify the results
        self.assertEqual(embedder_class, TestEmbedder)
        self.assertEqual(
            embedder_path, f"{TestEmbedder.__module__}.{TestEmbedder.__name__}"
        )
        mock_corpus.objects.get.assert_called_with(id=1)
        mock_find_embedder.assert_called_with("application/pdf")
        mock_get_default.assert_not_called()

    @patch("opencontractserver.corpuses.models.Corpus")
    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    @patch("opencontractserver.pipeline.utils.find_embedder_for_filetype")
    @patch("opencontractserver.pipeline.utils.get_default_embedder")
    def test_get_embedder_for_corpus_with_error_loading_preferred(
        self, mock_get_default, mock_find_embedder, mock_get_component, mock_corpus
    ):
        """
        Test get_embedder_for_corpus when there's an error loading the preferred embedder.
        """
        # Set up mocks
        mock_corpus_obj = MagicMock()
        mock_corpus_obj.preferred_embedder = "path.to.NonExistentEmbedder"
        mock_corpus.objects.get.return_value = mock_corpus_obj

        # Mock the component lookup to raise an exception
        mock_get_component.side_effect = Exception("Component not found")

        # Mock the embedder lookup
        mock_find_embedder.return_value = TestEmbedder

        # Call the function
        embedder_class, embedder_path = get_embedder(
            corpus_id=1, mimetype_or_enum="application/pdf"
        )

        # Verify the results
        self.assertEqual(embedder_class, TestEmbedder)
        self.assertEqual(
            embedder_path, f"{TestEmbedder.__module__}.{TestEmbedder.__name__}"
        )
        mock_corpus.objects.get.assert_called_with(id=1)
        mock_get_component.assert_called_with("path.to.NonExistentEmbedder")
        mock_find_embedder.assert_called_with("application/pdf")
        mock_get_default.assert_not_called()

    @patch("opencontractserver.corpuses.models.Corpus")
    @patch("opencontractserver.pipeline.utils.find_embedder_for_filetype")
    @patch("opencontractserver.pipeline.utils.get_default_embedder")
    def test_get_embedder_for_corpus_with_corpus_not_found(
        self, mock_get_default, mock_find_embedder, mock_corpus
    ):
        """
        Test get_embedder_for_corpus when the corpus is not found.
        """
        # Set up mocks
        mock_corpus.objects.get.side_effect = Exception("Corpus not found")

        # Mock the embedder lookup
        mock_find_embedder.return_value = TestEmbedder

        # Call the function
        embedder_class, embedder_path = get_embedder(
            corpus_id=1, mimetype_or_enum="application/pdf"
        )

        # Verify the results
        self.assertEqual(embedder_class, TestEmbedder)
        self.assertEqual(
            embedder_path, f"{TestEmbedder.__module__}.{TestEmbedder.__name__}"
        )
        mock_corpus.objects.get.assert_called_with(id=1)
        mock_find_embedder.assert_called_with("application/pdf")
        mock_get_default.assert_not_called()

    @patch("opencontractserver.corpuses.models.Corpus")
    @patch("opencontractserver.pipeline.utils.find_embedder_for_filetype")
    @patch("opencontractserver.pipeline.utils.get_default_embedder")
    def test_get_embedder_for_corpus_fallback_to_default(
        self, mock_get_default, mock_find_embedder, mock_corpus
    ):
        """
        Test get_embedder_for_corpus fallback to default embedder.
        """
        # Set up mocks
        mock_corpus_obj = MagicMock()
        mock_corpus_obj.preferred_embedder = None
        mock_corpus.objects.get.return_value = mock_corpus_obj

        # Mock the embedder lookup to return None
        mock_find_embedder.return_value = None

        # Mock the default embedder
        mock_get_default.return_value = TestEmbedder

        # Call the function
        embedder_class, embedder_path = get_embedder(
            corpus_id=1, mimetype_or_enum="application/pdf"
        )

        # Verify the results
        self.assertEqual(embedder_class, TestEmbedder)
        self.assertEqual(
            embedder_path, f"{TestEmbedder.__module__}.{TestEmbedder.__name__}"
        )
        mock_corpus.objects.get.assert_called_with(id=1)
        mock_find_embedder.assert_called_with("application/pdf")
        mock_get_default.assert_called_once()


class TestAnnotationSignals(unittest.TestCase):
    """
    Tests for the annotation signal handlers that process embeddings when annotations
    are created. With the corpus-isolated structural annotation architecture, each
    annotation belongs to exactly one corpus context, and embeddings are handled via
    the dual embedding strategy in the task.
    """

    @patch(
        "opencontractserver.annotations.signals.calculate_embedding_for_annotation_text"
    )
    def test_process_annot_on_create_structural(self, mock_calc_embedding):
        """
        Test that process_annot_on_create_atomic correctly processes structural annotations.
        Structural annotations in a structural_set don't have a corpus_id, so corpus_id=None.
        """
        from opencontractserver.annotations.signals import (
            process_annot_on_create_atomic,
        )

        # Create mock annotation that's structural (in a structural_set, no corpus)
        mock_annotation = MagicMock()
        mock_annotation.id = 1
        mock_annotation.corpus_id = None  # Structural annotations have no corpus
        mock_annotation.embedding = None
        mock_annotation.structural = True

        # Call the signal handler
        process_annot_on_create_atomic(
            sender=Annotation, instance=mock_annotation, created=True
        )

        # Verify embedding calculation was scheduled with corpus_id=None
        mock_calc_embedding.si.assert_called_with(annotation_id=1, corpus_id=None)
        mock_calc_embedding.si.return_value.apply_async.assert_called_once()

    @patch(
        "opencontractserver.annotations.signals.calculate_embedding_for_annotation_text"
    )
    def test_process_annot_on_create_non_structural(self, mock_calc_embedding):
        """
        Test that process_annot_on_create_atomic correctly handles non-structural annotations.
        Non-structural annotations have a corpus_id.
        """
        from opencontractserver.annotations.signals import (
            process_annot_on_create_atomic,
        )

        # Create mock annotation that's NOT structural (has corpus)
        mock_annotation = MagicMock()
        mock_annotation.id = 1
        mock_annotation.corpus_id = 100  # Regular annotation in a corpus
        mock_annotation.embedding = None
        mock_annotation.structural = False

        # Call the signal handler
        process_annot_on_create_atomic(
            sender=Annotation, instance=mock_annotation, created=True
        )

        # Verify embedding calculation was scheduled with the corpus_id
        mock_calc_embedding.si.assert_called_with(annotation_id=1, corpus_id=100)
        mock_calc_embedding.si.return_value.apply_async.assert_called_once()

    @patch(
        "opencontractserver.annotations.signals.calculate_embedding_for_annotation_text"
    )
    def test_process_annot_on_create_existing_embedding(self, mock_calc_embedding):
        """
        Test that process_annot_on_create_atomic skips annotations with existing embeddings.
        """
        from opencontractserver.annotations.signals import (
            process_annot_on_create_atomic,
        )

        # Create mock annotation with an existing embedding
        mock_annotation = MagicMock()
        mock_annotation.id = 1
        mock_annotation.corpus_id = 100
        mock_annotation.embedding = [0.1, 0.2, 0.3]  # Non-None embedding
        mock_annotation.structural = True

        # Call the signal handler
        process_annot_on_create_atomic(
            sender=Annotation, instance=mock_annotation, created=True
        )

        # Verify embedding calculation was NOT scheduled
        mock_calc_embedding.si.assert_not_called()

    @patch("opencontractserver.annotations.signals.calculate_embedding_for_note_text")
    def test_process_note_on_create(self, mock_calc_embedding):
        """
        Test that process_note_on_create_atomic correctly schedules note embedding tasks.
        """
        from opencontractserver.annotations.signals import process_note_on_create_atomic

        # Create mock note with a corpus
        mock_note = MagicMock()
        mock_note.id = 1
        mock_note.corpus_id = 100
        mock_note.corpus = MagicMock()
        mock_note.embedding = None

        # Call the signal handler
        process_note_on_create_atomic(sender=Note, instance=mock_note, created=True)

        # Verify embedding calculation was scheduled with corpus_id
        mock_calc_embedding.si.assert_called_with(note_id=1, corpus_id=100)
        mock_calc_embedding.si.return_value.apply_async.assert_called_once()

    @patch(
        "opencontractserver.annotations.signals.calculate_embedding_for_annotation_text"
    )
    def test_process_structural_annotation_for_corpuses(self, mock_calc_embedding):
        """
        Test that structural annotations without corpus_id still get embeddings.
        With corpus-isolated StructuralAnnotationSets, the embedding task handles
        the dual embedding strategy automatically.
        """
        from opencontractserver.annotations.signals import (
            process_annot_on_create_atomic,
        )

        # Structural annotation linked via structural_set (no direct corpus)
        mock_annotation = MagicMock()
        mock_annotation.id = 42
        mock_annotation.corpus_id = None
        mock_annotation.embedding = None

        process_annot_on_create_atomic(
            sender=Annotation, instance=mock_annotation, created=True
        )

        # Should schedule embedding with corpus_id=None
        mock_calc_embedding.si.assert_called_with(annotation_id=42, corpus_id=None)
        mock_calc_embedding.si.return_value.apply_async.assert_called_once()


class TestEmbeddingTask(unittest.TestCase):
    """
    Tests for the embedding task functions that calculate embeddings for annotations.

    The embedding task uses the dual embedding strategy:
    - ALWAYS creates a DEFAULT_EMBEDDER embedding (for global search)
    - ADDITIONALLY creates corpus-specific embedding if corpus uses different embedder

    When an explicit embedder_path is provided, it bypasses the dual embedding strategy
    and uses only that embedder.
    """

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_calculate_embedding_for_annotation_text_with_explicit_embedder(
        self, mock_annotation_model, mock_get_component
    ):
        """
        Test that calculate_embedding_for_annotation_text uses an explicitly provided embedder_path.
        When explicit embedder_path is provided, it bypasses the dual embedding strategy.
        """
        from opencontractserver.tasks.embeddings_task import (
            calculate_embedding_for_annotation_text,
        )

        # Create mock annotation with a corpus_id
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.pk = 1
        mock_annot.raw_text = "This is test text"
        mock_annot.corpus_id = 123
        mock_annot.content_modalities = ["TEXT"]  # Text-only annotation
        mock_annotation_model.objects.select_related.return_value.get.return_value = (
            mock_annot
        )

        # Create mock embedder class and instance
        mock_embedder_instance = MagicMock()
        mock_embedder_instance.is_multimodal = False
        mock_embedder_instance.supports_images = False
        test_vector = [0.1, 0.2, 0.3]
        mock_embedder_instance.embed_text.return_value = test_vector

        mock_embedder_class = MagicMock(return_value=mock_embedder_instance)
        mock_get_component.return_value = mock_embedder_class

        # Define the explicit embedder path we'll provide
        explicit_embedder_path = "path.to.TestEmbedder"

        # Call the function with explicit embedder_path
        calculate_embedding_for_annotation_text(
            annotation_id=1, embedder_path=explicit_embedder_path
        )

        # Verify annotation was retrieved correctly (includes structural_set for multimodal)
        mock_annotation_model.objects.select_related.assert_called_with(
            "document", "structural_set"
        )
        mock_annotation_model.objects.select_related.return_value.get.assert_called_with(
            pk=1
        )

        # Verify get_component_by_name was called with explicit embedder path
        mock_get_component.assert_called_with(explicit_embedder_path)

        # Verify embed_text was called
        mock_embedder_instance.embed_text.assert_called_with("This is test text")

        # The key test: verify that the explicit embedder_path was used
        mock_annot.add_embedding.assert_called_with(explicit_embedder_path, test_vector)

    @patch("opencontractserver.tasks.embeddings_task.Corpus")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder_path")
    def test_calculate_embedding_for_annotation_text_fallback_to_annotation_corpus(
        self,
        mock_get_path,
        mock_annotation_model,
        mock_get_default,
        mock_get_component,
        mock_corpus_model,
    ):
        """
        Test that calculate_embedding_for_annotation_text creates both default and
        corpus-specific embeddings when the corpus has a different preferred embedder.
        """
        from opencontractserver.tasks.embeddings_task import (
            calculate_embedding_for_annotation_text,
        )

        # Set up settings mock
        mock_get_path.return_value = "default.embedder.path"

        # Create mock annotation with corpus reference
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.pk = 1
        mock_annot.raw_text = "This is test text"
        mock_annot.corpus_id = 123
        mock_annot.content_modalities = ["TEXT"]  # Text-only annotation
        mock_annotation_model.objects.select_related.return_value.get.return_value = (
            mock_annot
        )

        # Create mock default embedder
        mock_default_embedder_instance = MagicMock()
        mock_default_embedder_instance.is_multimodal = False
        mock_default_embedder_instance.supports_images = False
        default_vector = [0.1, 0.2, 0.3]
        mock_default_embedder_instance.embed_text.return_value = default_vector
        mock_default_embedder_class = MagicMock(
            return_value=mock_default_embedder_instance
        )
        mock_get_default.return_value = mock_default_embedder_class

        # Create mock corpus-specific embedder
        mock_corpus_embedder_instance = MagicMock()
        mock_corpus_embedder_instance.is_multimodal = False
        mock_corpus_embedder_instance.supports_images = False
        corpus_vector = [0.4, 0.5, 0.6]
        mock_corpus_embedder_instance.embed_text.return_value = corpus_vector
        mock_corpus_embedder_class = MagicMock(
            return_value=mock_corpus_embedder_instance
        )
        mock_get_component.return_value = mock_corpus_embedder_class

        # Create mock corpus with different preferred embedder
        mock_corpus = MagicMock()
        mock_corpus.id = 123
        mock_corpus.preferred_embedder = "corpus.embedder.path"
        mock_corpus_model.objects.get.return_value = mock_corpus

        # Call the function without embedder_path
        calculate_embedding_for_annotation_text(annotation_id=1)

        # Verify annotation was retrieved correctly
        mock_annotation_model.objects.select_related.return_value.get.assert_called_with(
            pk=1
        )

        # Verify default embedder was called
        mock_get_default.assert_called_once()
        mock_default_embedder_instance.embed_text.assert_called_with(
            "This is test text"
        )

        # Verify corpus was retrieved for dual embedding
        mock_corpus_model.objects.get.assert_called_with(id=123)

        # Verify corpus embedder was called for dual embedding
        mock_get_component.assert_called_with("corpus.embedder.path")
        mock_corpus_embedder_instance.embed_text.assert_called_with("This is test text")

        # Verify both embeddings were stored (default + corpus-specific)
        calls = mock_annot.add_embedding.call_args_list
        self.assertEqual(len(calls), 2)
        # First call: default embedder
        self.assertEqual(calls[0][0], ("default.embedder.path", default_vector))
        # Second call: corpus embedder
        self.assertEqual(calls[1][0], ("corpus.embedder.path", corpus_vector))

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder_path")
    def test_calculate_embedding_for_annotation_text_fallback_to_default(
        self, mock_get_path, mock_annotation_model, mock_get_default
    ):
        """
        Test that calculate_embedding_for_annotation_text creates only the default embedding
        when no corpus is associated (no dual embedding needed).
        """
        from opencontractserver.tasks.embeddings_task import (
            calculate_embedding_for_annotation_text,
        )

        # Set up settings mock
        mock_get_path.return_value = "default.embedder.path"

        # Create mock annotation with no corpus
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.pk = 1
        mock_annot.raw_text = "This is test text"
        mock_annot.corpus_id = None  # No corpus
        mock_annot.content_modalities = ["TEXT"]  # Text-only annotation
        mock_annotation_model.objects.select_related.return_value.get.return_value = (
            mock_annot
        )

        # Create mock embedder class and instance
        mock_embedder_instance = MagicMock()
        mock_embedder_instance.is_multimodal = False
        mock_embedder_instance.supports_images = False
        test_vector = [0.7, 0.8, 0.9]
        mock_embedder_instance.embed_text.return_value = test_vector

        mock_embedder_class = MagicMock(return_value=mock_embedder_instance)
        mock_get_default.return_value = mock_embedder_class

        # Call the function without embedder_path
        calculate_embedding_for_annotation_text(annotation_id=1)

        # Verify annotation was retrieved correctly
        mock_annotation_model.objects.select_related.return_value.get.assert_called_with(
            pk=1
        )

        # Verify only default embedder was called
        mock_get_default.assert_called_once()

        # Verify embedding was stored with the default path
        mock_annot.add_embedding.assert_called_once_with(
            "default.embedder.path", test_vector
        )


class TestMultimodalEmbeddingTask(unittest.TestCase):
    """Tests for multimodal embedding paths in embedding tasks."""

    @patch(
        "opencontractserver.utils.multimodal_embeddings.generate_multimodal_embedding"
    )
    def test_annotation_with_images_uses_multimodal_embedding(
        self, mock_multimodal_embed
    ):
        """Test that annotations with IMAGE modality use multimodal embedding."""
        from opencontractserver.tasks.embeddings_task import (
            _create_embedding_for_annotation,
        )

        # Create mock annotation with IMAGE modality
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.raw_text = "Figure 1 caption"
        mock_annot.content_modalities = ["TEXT", "IMAGE"]

        # Create mock multimodal embedder
        mock_embedder = MagicMock()
        mock_embedder.is_multimodal = True
        mock_embedder.supports_images = True

        test_vector = [0.5] * 768
        mock_multimodal_embed.return_value = test_vector

        result = _create_embedding_for_annotation(
            mock_annot, mock_embedder, "multimodal.embedder.path"
        )

        # Should have called multimodal embedding
        mock_multimodal_embed.assert_called_once_with(mock_annot, mock_embedder)

        # Should have stored embedding
        mock_annot.add_embedding.assert_called_once_with(
            "multimodal.embedder.path", test_vector
        )

        self.assertTrue(result)

    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_annotation_with_images_non_multimodal_embedder_falls_back_to_text(
        self, mock_annotation_model
    ):
        """Test that text-only embedder falls back to text even for IMAGE annotations."""
        from opencontractserver.tasks.embeddings_task import (
            _create_embedding_for_annotation,
        )

        # Create mock annotation with IMAGE modality
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.raw_text = "Figure 1 caption"
        mock_annot.content_modalities = ["TEXT", "IMAGE"]

        # Create mock text-only embedder
        mock_embedder = MagicMock()
        mock_embedder.is_multimodal = False
        mock_embedder.supports_images = False

        test_vector = [0.1] * 768
        mock_embedder.embed_text.return_value = test_vector

        result = _create_embedding_for_annotation(
            mock_annot, mock_embedder, "text.only.embedder"
        )

        # Should have called text embedding (fallback)
        mock_embedder.embed_text.assert_called_once_with("Figure 1 caption")

        # Should have stored embedding
        mock_annot.add_embedding.assert_called_once_with(
            "text.only.embedder", test_vector
        )

        self.assertTrue(result)

    @patch(
        "opencontractserver.utils.multimodal_embeddings.generate_multimodal_embedding"
    )
    def test_annotation_multimodal_returns_none_fails(self, mock_multimodal_embed):
        """Test that multimodal embedding returning None causes failure."""
        from opencontractserver.tasks.embeddings_task import (
            _create_embedding_for_annotation,
        )

        # Create mock annotation with IMAGE modality
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.raw_text = "Figure caption"
        mock_annot.content_modalities = ["TEXT", "IMAGE"]

        # Create mock multimodal embedder
        mock_embedder = MagicMock()
        mock_embedder.is_multimodal = True
        mock_embedder.supports_images = True

        # Make multimodal embedding return None (not an exception)
        mock_multimodal_embed.return_value = None

        result = _create_embedding_for_annotation(
            mock_annot, mock_embedder, "multimodal.embedder.path"
        )

        # Should have called multimodal embedding
        mock_multimodal_embed.assert_called_once_with(mock_annot, mock_embedder)

        # Should NOT have stored embedding (vector was None)
        mock_annot.add_embedding.assert_not_called()

        # Should return False
        self.assertFalse(result)

    @patch(
        "opencontractserver.utils.multimodal_embeddings.generate_multimodal_embedding"
    )
    def test_annotation_multimodal_add_embedding_fails(self, mock_multimodal_embed):
        """Test that add_embedding returning None causes failure."""
        from opencontractserver.tasks.embeddings_task import (
            _create_embedding_for_annotation,
        )

        # Create mock annotation with IMAGE modality
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.raw_text = "Figure caption"
        mock_annot.content_modalities = ["TEXT", "IMAGE"]
        mock_annot.add_embedding.return_value = None  # Simulate storage failure

        # Create mock multimodal embedder
        mock_embedder = MagicMock()
        mock_embedder.is_multimodal = True
        mock_embedder.supports_images = True

        test_vector = [0.5] * 768
        mock_multimodal_embed.return_value = test_vector

        result = _create_embedding_for_annotation(
            mock_annot, mock_embedder, "multimodal.embedder.path"
        )

        # Should have called multimodal embedding
        mock_multimodal_embed.assert_called_once_with(mock_annot, mock_embedder)

        # Should have tried to store embedding
        mock_annot.add_embedding.assert_called_once_with(
            "multimodal.embedder.path", test_vector
        )

        # Should return False because add_embedding returned None
        self.assertFalse(result)

    @patch(
        "opencontractserver.utils.multimodal_embeddings.generate_multimodal_embedding"
    )
    def test_annotation_multimodal_failure_falls_back_to_text(
        self, mock_multimodal_embed
    ):
        """Test graceful degradation: multimodal failure falls back to text."""
        from opencontractserver.tasks.embeddings_task import (
            _create_embedding_for_annotation,
        )

        # Create mock annotation with IMAGE modality
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.raw_text = "Figure with error"
        mock_annot.content_modalities = ["TEXT", "IMAGE"]

        # Create mock multimodal embedder
        mock_embedder = MagicMock()
        mock_embedder.is_multimodal = True
        mock_embedder.supports_images = True

        test_vector = [0.2] * 768
        mock_embedder.embed_text.return_value = test_vector

        # Make multimodal embedding fail
        mock_multimodal_embed.side_effect = Exception("Multimodal failed")

        result = _create_embedding_for_annotation(
            mock_annot, mock_embedder, "multimodal.embedder.path"
        )

        # Should have fallen back to text embedding
        mock_embedder.embed_text.assert_called_once_with("Figure with error")

        # Should have stored embedding
        mock_annot.add_embedding.assert_called_once_with(
            "multimodal.embedder.path", test_vector
        )

        self.assertTrue(result)

    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_annotation_text_only_modality_uses_text_embedding(
        self, mock_annotation_model
    ):
        """Test that text-only annotations use text embedding even with multimodal embedder."""
        from opencontractserver.tasks.embeddings_task import (
            _create_embedding_for_annotation,
        )

        # Create mock annotation with TEXT only modality
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.raw_text = "Just plain text"
        mock_annot.content_modalities = ["TEXT"]

        # Create mock multimodal embedder
        mock_embedder = MagicMock()
        mock_embedder.is_multimodal = True
        mock_embedder.supports_images = True

        test_vector = [0.3] * 768
        mock_embedder.embed_text.return_value = test_vector

        result = _create_embedding_for_annotation(
            mock_annot, mock_embedder, "multimodal.embedder.path"
        )

        # Should have called text embedding (no images to embed)
        mock_embedder.embed_text.assert_called_once_with("Just plain text")

        self.assertTrue(result)

    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_annotation_no_modalities_defaults_to_text(self, mock_annotation_model):
        """Test that annotations with no content_modalities default to TEXT."""
        from opencontractserver.tasks.embeddings_task import (
            _create_embedding_for_annotation,
        )

        # Create mock annotation with no modalities
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.raw_text = "No modalities set"
        mock_annot.content_modalities = None

        mock_embedder = MagicMock()
        mock_embedder.is_multimodal = True
        mock_embedder.supports_images = True

        test_vector = [0.4] * 768
        mock_embedder.embed_text.return_value = test_vector

        result = _create_embedding_for_annotation(
            mock_annot, mock_embedder, "multimodal.embedder.path"
        )

        # Should default to text embedding
        mock_embedder.embed_text.assert_called_once_with("No modalities set")

        self.assertTrue(result)

    def test_create_text_embedding_empty_text(self):
        """Test that empty text returns False and doesn't embed."""
        from opencontractserver.tasks.embeddings_task import _create_text_embedding

        mock_obj = MagicMock()
        mock_embedder = MagicMock()

        result = _create_text_embedding(
            mock_obj, mock_embedder, "embedder.path", "", "test", 1
        )

        self.assertFalse(result)
        mock_embedder.embed_text.assert_not_called()
        mock_obj.add_embedding.assert_not_called()

    def test_create_text_embedding_embed_returns_none(self):
        """Test that embedding failure returns False."""
        from opencontractserver.tasks.embeddings_task import _create_text_embedding

        mock_obj = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = None

        result = _create_text_embedding(
            mock_obj, mock_embedder, "embedder.path", "test text", "test", 1
        )

        self.assertFalse(result)
        mock_obj.add_embedding.assert_not_called()


class TestEmbeddingGenerationError(unittest.TestCase):
    """
    Tests for EmbeddingGenerationError behavior introduced in PR #828.

    The error handling ensures:
    - Default embedding failures raise EmbeddingGenerationError (triggers Celery retry)
    - Explicit embedder path failures raise EmbeddingGenerationError
    - Corpus-specific embedding failures are logged but don't fail the task
    """

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder_path")
    def test_embedding_generation_error_raised_when_default_embedder_returns_none(
        self, mock_get_path, mock_get_default
    ):
        """
        Test that EmbeddingGenerationError is raised when the default embedder
        returns None (embedding generation failed).
        """
        from opencontractserver.tasks.embeddings_task import (
            EmbeddingGenerationError,
            _apply_dual_embedding_strategy,
        )

        mock_get_path.return_value = "default.embedder.path"

        # Create mock embedder that returns None (failure)
        mock_embedder_instance = MagicMock()
        mock_embedder_class = MagicMock(return_value=mock_embedder_instance)
        mock_get_default.return_value = mock_embedder_class

        # Create mock object
        mock_obj = MagicMock()

        # Create embed function that returns False (embedding failed)
        def failing_embed_func(obj, embedder, embedder_path):
            return False

        # Should raise EmbeddingGenerationError
        with self.assertRaises(EmbeddingGenerationError) as context:
            _apply_dual_embedding_strategy(
                obj=mock_obj,
                text="test text",
                corpus_id=None,
                obj_type="document",
                obj_id=1,
                embed_func=failing_embed_func,
            )

        self.assertIn("Default embedding failed", str(context.exception))
        self.assertIn(
            "Embedder returned None or failed to store", str(context.exception)
        )

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder_path")
    def test_embedding_generation_error_raised_when_default_embedder_class_none(
        self, mock_get_path, mock_get_default
    ):
        """
        Test that EmbeddingGenerationError is raised when get_default_embedder
        returns None (no embedder configured).
        """
        from opencontractserver.tasks.embeddings_task import (
            EmbeddingGenerationError,
            _apply_dual_embedding_strategy,
        )

        mock_get_path.return_value = "default.embedder.path"
        mock_get_default.return_value = None  # No default embedder

        mock_obj = MagicMock()

        def embed_func(obj, embedder, embedder_path):
            return True

        with self.assertRaises(EmbeddingGenerationError) as context:
            _apply_dual_embedding_strategy(
                obj=mock_obj,
                text="test text",
                corpus_id=None,
                obj_type="document",
                obj_id=1,
                embed_func=embed_func,
            )

        self.assertIn("Could not get default embedder class", str(context.exception))

    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder_path")
    def test_embedding_generation_error_raised_when_default_embedder_throws(
        self, mock_get_path, mock_get_default
    ):
        """
        Test that EmbeddingGenerationError is raised when the default embedder
        throws an exception during embedding generation.
        """
        from opencontractserver.tasks.embeddings_task import (
            EmbeddingGenerationError,
            _apply_dual_embedding_strategy,
        )

        mock_get_path.return_value = "default.embedder.path"

        # Make get_default_embedder raise an exception
        mock_get_default.side_effect = Exception("Connection refused")

        mock_obj = MagicMock()

        def embed_func(obj, embedder, embedder_path):
            return True

        with self.assertRaises(EmbeddingGenerationError) as context:
            _apply_dual_embedding_strategy(
                obj=mock_obj,
                text="test text",
                corpus_id=None,
                obj_type="document",
                obj_id=1,
                embed_func=embed_func,
            )

        self.assertIn("Connection refused", str(context.exception))

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_explicit_embedder_path_raises_embedding_generation_error_on_failure(
        self, mock_annotation_model, mock_get_component
    ):
        """
        Test that calculate_embedding_for_annotation_text raises EmbeddingGenerationError
        when an explicit embedder_path is provided and embedding fails.
        """
        from opencontractserver.tasks.embeddings_task import (
            EmbeddingGenerationError,
            calculate_embedding_for_annotation_text,
        )

        # Create mock annotation
        mock_annot = MagicMock()
        mock_annot.id = 1
        mock_annot.pk = 1
        mock_annot.raw_text = "Test text"
        mock_annot.corpus_id = None
        mock_annot.content_modalities = ["TEXT"]
        mock_annotation_model.objects.select_related.return_value.get.return_value = (
            mock_annot
        )

        # Create mock embedder that returns None (failure)
        mock_embedder_instance = MagicMock()
        mock_embedder_instance.is_multimodal = False
        mock_embedder_instance.supports_images = False
        mock_embedder_instance.embed_text.return_value = None  # Embedding failed
        mock_embedder_class = MagicMock(return_value=mock_embedder_instance)
        mock_get_component.return_value = mock_embedder_class

        # Should raise EmbeddingGenerationError
        with self.assertRaises(EmbeddingGenerationError) as context:
            calculate_embedding_for_annotation_text(
                annotation_id=1, embedder_path="explicit.embedder.path"
            )

        self.assertIn("Embedding failed for annotation 1", str(context.exception))
        self.assertIn("explicit.embedder.path", str(context.exception))

    @patch("opencontractserver.tasks.embeddings_task.Corpus")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder_path")
    def test_corpus_embedding_failure_does_not_raise_error(
        self, mock_get_path, mock_get_default, mock_get_component, mock_corpus_model
    ):
        """
        Test that corpus-specific embedding failures are logged but don't fail the task.
        Only the default embedding failure should raise EmbeddingGenerationError.
        """
        from opencontractserver.tasks.embeddings_task import (
            _apply_dual_embedding_strategy,
        )

        mock_get_path.return_value = "default.embedder.path"

        # Create successful default embedder
        mock_default_embedder = MagicMock()
        mock_default_embedder_class = MagicMock(return_value=mock_default_embedder)
        mock_get_default.return_value = mock_default_embedder_class

        # Create failing corpus embedder
        mock_corpus_embedder = MagicMock()
        mock_corpus_embedder_class = MagicMock(return_value=mock_corpus_embedder)
        mock_get_component.return_value = mock_corpus_embedder_class

        # Set up corpus with different preferred embedder
        mock_corpus = MagicMock()
        mock_corpus.id = 123
        mock_corpus.preferred_embedder = "corpus.embedder.path"
        mock_corpus_model.objects.get.return_value = mock_corpus

        mock_obj = MagicMock()

        call_count = [0]

        def embed_func(obj, embedder, embedder_path):
            call_count[0] += 1
            if embedder_path == "default.embedder.path":
                return True  # Default succeeds
            else:
                return False  # Corpus-specific fails

        # Should NOT raise - corpus failure is non-fatal
        _apply_dual_embedding_strategy(
            obj=mock_obj,
            text="test text",
            corpus_id=123,
            obj_type="document",
            obj_id=1,
            embed_func=embed_func,
        )

        # Both embedders should have been called
        self.assertEqual(call_count[0], 2)

    @patch("opencontractserver.tasks.embeddings_task.Corpus")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder")
    @patch("opencontractserver.tasks.embeddings_task.get_default_embedder_path")
    def test_corpus_embedding_exception_does_not_raise_error(
        self, mock_get_path, mock_get_default, mock_get_component, mock_corpus_model
    ):
        """
        Test that corpus-specific embedding exceptions are caught and logged,
        but don't fail the task.
        """
        from opencontractserver.tasks.embeddings_task import (
            _apply_dual_embedding_strategy,
        )

        mock_get_path.return_value = "default.embedder.path"

        # Create successful default embedder
        mock_default_embedder = MagicMock()
        mock_default_embedder_class = MagicMock(return_value=mock_default_embedder)
        mock_get_default.return_value = mock_default_embedder_class

        # Make corpus embedder loading throw an exception
        mock_get_component.side_effect = Exception("Corpus embedder not found")

        # Set up corpus with different preferred embedder
        mock_corpus = MagicMock()
        mock_corpus.id = 123
        mock_corpus.preferred_embedder = "corpus.embedder.path"
        mock_corpus_model.objects.get.return_value = mock_corpus

        mock_obj = MagicMock()

        def embed_func(obj, embedder, embedder_path):
            return True

        # Should NOT raise - corpus loading failure is non-fatal
        _apply_dual_embedding_strategy(
            obj=mock_obj,
            text="test text",
            corpus_id=123,
            obj_type="document",
            obj_id=1,
            embed_func=embed_func,
        )

        # Default embedder should still have been used
        mock_get_default.assert_called_once()

    def test_embedding_generation_error_is_exception_subclass(self):
        """Test that EmbeddingGenerationError is a proper Exception subclass."""
        from opencontractserver.tasks.embeddings_task import EmbeddingGenerationError

        self.assertTrue(issubclass(EmbeddingGenerationError, Exception))

        error = EmbeddingGenerationError("Test error message")
        self.assertEqual(str(error), "Test error message")


class TestBytesDecoding(unittest.TestCase):
    """
    Tests for bytes-to-string decoding in embedding tasks.

    Some storage backends (e.g., django-storages with certain S3 configurations)
    may return bytes even when files are opened in text mode ("r").
    """

    @patch("opencontractserver.tasks.embeddings_task._apply_dual_embedding_strategy")
    @patch("opencontractserver.tasks.embeddings_task.Document")
    def test_bytes_content_decoded_to_string(
        self, mock_document_model, mock_apply_strategy
    ):
        """
        Test that bytes content from txt_extract_file is properly decoded to UTF-8.
        """
        from opencontractserver.tasks.embeddings_task import (
            calculate_embedding_for_doc_text,
        )

        # Create mock document with a txt_extract_file that returns bytes
        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.txt_extract_file.name = "test.txt"

        # Simulate storage backend returning bytes even in "r" mode
        mock_file = MagicMock()
        mock_file.read.return_value = b"Test content in bytes"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_doc.txt_extract_file.open.return_value = mock_file

        mock_document_model.objects.get.return_value = mock_doc

        # Call the function
        calculate_embedding_for_doc_text(doc_id=1, corpus_id=None)

        # Verify _apply_dual_embedding_strategy was called with decoded string
        mock_apply_strategy.assert_called_once()
        call_kwargs = mock_apply_strategy.call_args[1]
        self.assertEqual(call_kwargs["text"], "Test content in bytes")
        self.assertIsInstance(call_kwargs["text"], str)

    @patch("opencontractserver.tasks.embeddings_task._apply_dual_embedding_strategy")
    @patch("opencontractserver.tasks.embeddings_task.Document")
    def test_string_content_passed_through(
        self, mock_document_model, mock_apply_strategy
    ):
        """
        Test that string content from txt_extract_file is passed through unchanged.
        """
        from opencontractserver.tasks.embeddings_task import (
            calculate_embedding_for_doc_text,
        )

        # Create mock document with a txt_extract_file that returns string
        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.txt_extract_file.name = "test.txt"

        # Normal behavior: file returns string
        mock_file = MagicMock()
        mock_file.read.return_value = "Test content as string"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_doc.txt_extract_file.open.return_value = mock_file

        mock_document_model.objects.get.return_value = mock_doc

        # Call the function
        calculate_embedding_for_doc_text(doc_id=1, corpus_id=None)

        # Verify _apply_dual_embedding_strategy was called with the string
        mock_apply_strategy.assert_called_once()
        call_kwargs = mock_apply_strategy.call_args[1]
        self.assertEqual(call_kwargs["text"], "Test content as string")


class TestArrayFormatHandling(unittest.TestCase):
    """
    Tests for 1D vs 2D array format handling in embedders.

    Different embedding services may return embeddings in different formats:
    - 1D: [0.1, 0.2, 0.3, ...] - single embedding directly
    - 2D: [[0.1, 0.2, 0.3, ...]] - batch format with single item
    """

    def test_microservice_embedder_handles_1d_array(self):
        """Test that MicroserviceEmbedder correctly handles 1D array responses."""
        from opencontractserver.pipeline.embedders.sent_transformer_microservice import (
            MicroserviceEmbedder,
        )

        embedder = MicroserviceEmbedder()

        # Simulate 1D response: [0.1, 0.2, 0.3]
        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embeddings": [0.1, 0.2, 0.3]}
            mock_post.return_value = mock_response

            result = embedder.embed_text("test")

            self.assertEqual(result, [0.1, 0.2, 0.3])
            self.assertIsInstance(result, list)

    def test_microservice_embedder_handles_2d_array(self):
        """Test that MicroserviceEmbedder correctly handles 2D array responses."""
        from opencontractserver.pipeline.embedders.sent_transformer_microservice import (
            MicroserviceEmbedder,
        )

        embedder = MicroserviceEmbedder()

        # Simulate 2D response: [[0.1, 0.2, 0.3]]
        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
            mock_post.return_value = mock_response

            result = embedder.embed_text("test")

            self.assertEqual(result, [0.1, 0.2, 0.3])
            self.assertIsInstance(result, list)

    def test_multimodal_embedder_handles_1d_array(self):
        """Test that CLIPMicroserviceEmbedder correctly handles 1D array responses."""
        from opencontractserver.pipeline.embedders.multimodal_microservice import (
            CLIPMicroserviceEmbedder,
        )

        embedder = CLIPMicroserviceEmbedder()

        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embeddings": [0.4, 0.5, 0.6]}
            mock_post.return_value = mock_response

            with patch.object(
                embedder, "_get_service_config", return_value=("http://test", "", {})
            ):
                result = embedder.embed_text("test")

            self.assertEqual(result, [0.4, 0.5, 0.6])

    def test_multimodal_embedder_handles_2d_array(self):
        """Test that CLIPMicroserviceEmbedder correctly handles 2D array responses."""
        from opencontractserver.pipeline.embedders.multimodal_microservice import (
            CLIPMicroserviceEmbedder,
        )

        embedder = CLIPMicroserviceEmbedder()

        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embeddings": [[0.4, 0.5, 0.6]]}
            mock_post.return_value = mock_response

            with patch.object(
                embedder, "_get_service_config", return_value=("http://test", "", {})
            ):
                result = embedder.embed_text("test")

            self.assertEqual(result, [0.4, 0.5, 0.6])

    def test_microservice_embedder_settings_none_fallback(self):
        """MicroserviceEmbedder falls back to Settings() when self.settings is None."""
        from opencontractserver.pipeline.embedders.sent_transformer_microservice import (
            MicroserviceEmbedder,
        )

        embedder = MicroserviceEmbedder()
        # Force settings to None to exercise the fallback path
        embedder._settings = None

        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"embeddings": [0.1, 0.2, 0.3]}
            mock_post.return_value = mock_response

            result = embedder.embed_text("test")

            self.assertEqual(result, [0.1, 0.2, 0.3])

    def test_clip_embedder_settings_none_fallback(self):
        """CLIPMicroserviceEmbedder._get_service_config falls back to Settings()."""
        from opencontractserver.pipeline.embedders.multimodal_microservice import (
            CLIPMicroserviceEmbedder,
        )

        embedder = CLIPMicroserviceEmbedder()
        embedder._settings = None

        url, api_key, headers = embedder._get_service_config({})
        # Should use defaults from Settings dataclass
        self.assertEqual(url, "http://multimodal-embedder:8000")
        self.assertEqual(api_key, "")

    def test_qwen_embedder_settings_none_fallback(self):
        """QwenMicroserviceEmbedder._get_service_config falls back to Settings()."""
        from opencontractserver.pipeline.embedders.multimodal_microservice import (
            QwenMicroserviceEmbedder,
        )

        embedder = QwenMicroserviceEmbedder()
        embedder._settings = None

        url, api_key, headers = embedder._get_service_config({})
        # Should use defaults from Settings dataclass
        self.assertEqual(url, "http://qwen-embedder:8000")
        self.assertEqual(api_key, "")


if __name__ == "__main__":
    unittest.main()
