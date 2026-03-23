"""
Unit tests for OpenAIEmbedder.

Tests the OpenAI embeddings integration using mocked API responses.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from opencontractserver.constants.embeddings import (
    DEFAULT_OPENAI_EMBEDDING_DIMENSIONS,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
)
from opencontractserver.pipeline.base.settings_schema import (
    get_required_settings,
    get_secret_settings,
    get_settings_schema,
)
from opencontractserver.pipeline.embedders.openai_embedder import OpenAIEmbedder
from opencontractserver.types.enums import ContentModality


class TestOpenAIEmbedderProperties(TestCase):
    """Tests for OpenAIEmbedder class properties and metadata."""

    def test_class_metadata(self):
        embedder = OpenAIEmbedder()
        self.assertEqual(embedder.title, "OpenAI Embedder")
        self.assertEqual(embedder.vector_size, DEFAULT_OPENAI_EMBEDDING_DIMENSIONS)
        self.assertIn("openai", embedder.dependencies)

    def test_text_only_modality(self):
        embedder = OpenAIEmbedder()
        self.assertFalse(embedder.is_multimodal)
        self.assertTrue(embedder.supports_text)
        self.assertFalse(embedder.supports_images)
        self.assertEqual(embedder.supported_modalities, {ContentModality.TEXT})

    def test_supported_file_types(self):
        embedder = OpenAIEmbedder()
        self.assertEqual(len(embedder.supported_file_types), 3)


class TestOpenAIEmbedderVectorSize(TestCase):
    """Tests for dynamic vector_size property."""

    def test_default_vector_size(self):
        embedder = OpenAIEmbedder()
        self.assertEqual(embedder.vector_size, DEFAULT_OPENAI_EMBEDDING_DIMENSIONS)

    def test_vector_size_reflects_large_model(self):
        embedder = OpenAIEmbedder()
        embedder._settings = OpenAIEmbedder.Settings(
            openai_embedding_model="text-embedding-3-large",
            openai_embedding_dimensions=3072,
        )
        self.assertEqual(embedder.vector_size, 3072)

    def test_vector_size_reflects_custom_dimensions(self):
        embedder = OpenAIEmbedder()
        embedder._settings = OpenAIEmbedder.Settings(
            openai_embedding_model="text-embedding-3-small",
            openai_embedding_dimensions=512,
        )
        self.assertEqual(embedder.vector_size, 512)

    def test_vector_size_ada_ignores_custom_dimensions(self):
        embedder = OpenAIEmbedder()
        embedder._settings = OpenAIEmbedder.Settings(
            openai_embedding_model="text-embedding-ada-002",
            openai_embedding_dimensions=768,
        )
        # ada-002 doesn't support custom dims, so vector_size comes from the model map
        self.assertEqual(embedder.vector_size, 1536)


class TestOpenAIEmbedderSettings(TestCase):
    """Tests for OpenAIEmbedder settings schema."""

    def test_settings_schema_has_required_fields(self):
        schema = get_settings_schema(OpenAIEmbedder)
        self.assertIn("openai_api_key", schema)
        self.assertIn("openai_embedding_model", schema)
        self.assertIn("openai_embedding_dimensions", schema)
        self.assertIn("openai_api_base_url", schema)

    def test_api_key_is_secret_and_required(self):
        secret_settings = get_secret_settings(OpenAIEmbedder)
        self.assertIn("openai_api_key", secret_settings)

        required_settings = get_required_settings(OpenAIEmbedder)
        self.assertIn("openai_api_key", required_settings)

    def test_default_model(self):
        settings = OpenAIEmbedder.Settings()
        self.assertEqual(
            settings.openai_embedding_model, DEFAULT_OPENAI_EMBEDDING_MODEL
        )

    def test_default_dimensions(self):
        settings = OpenAIEmbedder.Settings()
        self.assertEqual(
            settings.openai_embedding_dimensions, DEFAULT_OPENAI_EMBEDDING_DIMENSIONS
        )


class TestOpenAIEmbedderEmbedText(TestCase):
    """Tests for OpenAIEmbedder._embed_text_impl via embed_text."""

    def _make_mock_response(self, embedding):
        """Create a mock OpenAI embeddings response."""
        mock_data = MagicMock()
        mock_data.embedding = embedding
        mock_response = MagicMock()
        mock_response.data = [mock_data]
        return mock_response

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_success(self, mock_openai_cls):
        fake_embedding = [0.1] * DEFAULT_OPENAI_EMBEDDING_DIMENSIONS
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            fake_embedding
        )
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        result = embedder.embed_text("Hello world", openai_api_key="test-key")

        self.assertIsNotNone(result)
        self.assertEqual(len(result), DEFAULT_OPENAI_EMBEDDING_DIMENSIONS)
        self.assertEqual(result, fake_embedding)

        # Verify the client was called with the right model and dimensions
        call_kwargs = mock_client.embeddings.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], DEFAULT_OPENAI_EMBEDDING_MODEL)
        self.assertEqual(
            call_kwargs.kwargs["dimensions"], DEFAULT_OPENAI_EMBEDDING_DIMENSIONS
        )
        self.assertEqual(call_kwargs.kwargs["input"], "Hello world")

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_custom_model(self, mock_openai_cls):
        fake_embedding = [0.2] * 3072
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            fake_embedding
        )
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        result = embedder.embed_text(
            "Hello",
            openai_api_key="test-key",
            openai_embedding_model="text-embedding-3-large",
            openai_embedding_dimensions=3072,
        )

        self.assertIsNotNone(result)
        call_kwargs = mock_client.embeddings.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], "text-embedding-3-large")
        self.assertEqual(call_kwargs.kwargs["dimensions"], 3072)

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_ada_omits_dimensions(self, mock_openai_cls):
        """text-embedding-ada-002 does not support the dimensions parameter."""
        fake_embedding = [0.3] * 1536
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            fake_embedding
        )
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        embedder.embed_text(
            "Hello",
            openai_api_key="test-key",
            openai_embedding_model="text-embedding-ada-002",
        )

        call_kwargs = mock_client.embeddings.create.call_args
        self.assertNotIn("dimensions", call_kwargs.kwargs)

    def test_embed_text_empty_returns_none(self):
        embedder = OpenAIEmbedder()
        self.assertIsNone(embedder.embed_text(""))
        self.assertIsNone(embedder.embed_text("   "))

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_auth_error_returns_none(self, mock_openai_cls):
        import openai as openai_module

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = openai_module.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        result = embedder.embed_text("Hello", openai_api_key="bad-key")

        self.assertIsNone(result)

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_rate_limit_returns_none(self, mock_openai_cls):
        import openai as openai_module

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = openai_module.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        result = embedder.embed_text("Hello", openai_api_key="test-key")

        self.assertIsNone(result)

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_custom_base_url(self, mock_openai_cls):
        fake_embedding = [0.1] * DEFAULT_OPENAI_EMBEDDING_DIMENSIONS
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            fake_embedding
        )
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        embedder.embed_text(
            "Hello",
            openai_api_key="test-key",
            openai_api_base_url="https://custom.openai.azure.com",
        )

        mock_openai_cls.assert_called_with(
            api_key="test-key",
            base_url="https://custom.openai.azure.com",
        )

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_empty_base_url_passes_none(self, mock_openai_cls):
        fake_embedding = [0.1] * DEFAULT_OPENAI_EMBEDDING_DIMENSIONS
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            fake_embedding
        )
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        embedder.embed_text("Hello", openai_api_key="test-key")

        mock_openai_cls.assert_called_with(api_key="test-key", base_url=None)

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_bad_request_returns_none(self, mock_openai_cls):
        import openai as openai_module

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = openai_module.BadRequestError(
            message="Invalid input",
            response=MagicMock(status_code=400),
            body=None,
        )
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        result = embedder.embed_text("Hello", openai_api_key="test-key")

        self.assertIsNone(result)

    @patch("opencontractserver.pipeline.embedders.openai_embedder.openai.OpenAI")
    def test_embed_text_generic_exception_returns_none(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = RuntimeError("unexpected failure")
        mock_openai_cls.return_value = mock_client

        embedder = OpenAIEmbedder()
        result = embedder.embed_text("Hello", openai_api_key="test-key")

        self.assertIsNone(result)

    def test_embed_image_not_supported(self):
        embedder = OpenAIEmbedder()
        result = embedder.embed_image("base64data", "jpeg")
        self.assertIsNone(result)


class TestOpenAIEmbedderDiscovery(TestCase):
    """Tests that OpenAIEmbedder is properly discovered by the registry."""

    def test_embedder_discoverable(self):
        from opencontractserver.pipeline.registry import get_all_embedders_cached

        embedders = get_all_embedders_cached()
        names = [e.name for e in embedders]
        self.assertIn("OpenAIEmbedder", names)

    def test_embedder_definition_metadata(self):
        from opencontractserver.pipeline.registry import get_component_by_name_cached

        definition = get_component_by_name_cached("OpenAIEmbedder")
        self.assertIsNotNone(definition)
        self.assertEqual(definition.vector_size, DEFAULT_OPENAI_EMBEDDING_DIMENSIONS)
        self.assertFalse(definition.is_multimodal)
        self.assertTrue(definition.supports_text)
