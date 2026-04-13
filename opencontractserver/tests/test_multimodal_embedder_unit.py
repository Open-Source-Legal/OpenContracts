"""
Unit tests for CLIPMicroserviceEmbedder.

These tests use mocks to test all code paths without requiring the actual
multimodal embedder service to be running.

Note: These tests mock the Settings dataclass to test configuration behavior.
The actual Settings dataclass is populated from PipelineSettings DB at runtime.
"""

import base64
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase
from PIL import Image
from requests.exceptions import ConnectionError, Timeout

from opencontractserver.pipeline.base.exceptions import (
    EmbeddingClientError,
    EmbeddingServerError,
)
from opencontractserver.pipeline.embedders.multimodal_microservice import (
    CLIPMicroserviceEmbedder,
)
from opencontractserver.types.enums import ContentModality


def create_mock_clip_settings(
    clip_embedder_url: str = "http://vector-embedder:8000",
    clip_embedder_api_key: str = "",
    use_cloud_run_iam_auth: bool = False,
):
    """Create a mock Settings object for CLIPMicroserviceEmbedder."""
    mock_settings = MagicMock()
    mock_settings.clip_embedder_url = clip_embedder_url
    mock_settings.clip_embedder_api_key = clip_embedder_api_key
    mock_settings.use_cloud_run_iam_auth = use_cloud_run_iam_auth
    return mock_settings


def create_mock_qwen_settings(
    qwen_embedder_url: str = "http://qwen-embedder:8000",
    qwen_embedder_api_key: str = "",
    use_cloud_run_iam_auth: bool = False,
):
    """Create a mock Settings object for QwenMicroserviceEmbedder."""
    mock_settings = MagicMock()
    mock_settings.qwen_embedder_url = qwen_embedder_url
    mock_settings.qwen_embedder_api_key = qwen_embedder_api_key
    mock_settings.use_cloud_run_iam_auth = use_cloud_run_iam_auth
    return mock_settings


class MockResponse:
    """Mock response object for requests."""

    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def create_test_image_base64(width: int = 100, height: int = 100) -> str:
    """Create a sample base64-encoded image for testing."""
    img = Image.new("RGB", (width, height), color="red")
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class TestCLIPMicroserviceEmbedderUnit(TestCase):
    """Unit tests for CLIPMicroserviceEmbedder with mocked HTTP calls."""

    def setUp(self):
        self.embedder = CLIPMicroserviceEmbedder()

    # =========================================================================
    # Text Embedding Tests
    # =========================================================================

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_text_success(self, mock_post):
        """Test successful text embedding."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768]})

        result = self.embedder.embed_text(
            "Test text", multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 768)
        mock_post.assert_called_once()

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_text_no_service_url(self, mock_post):
        """Test text embedding returns None when no service URL configured."""
        # Mock the Settings dataclass to have empty URL
        self.embedder._settings = create_mock_clip_settings(clip_embedder_url="")
        result = self.embedder.embed_text("Test text")

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_text_bad_status_code(self, mock_post):
        """Test text embedding handles bad status codes."""
        mock_post.return_value = MockResponse(500, {"error": "Server error"})

        result = self.embedder.embed_text(
            "Test text", multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_text_timeout(self, mock_post):
        """Test text embedding handles timeout gracefully."""
        mock_post.side_effect = Timeout()

        result = self.embedder.embed_text(
            "Test text", multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_text_connection_error(self, mock_post):
        """Test text embedding handles connection error gracefully."""
        mock_post.side_effect = ConnectionError()

        result = self.embedder.embed_text(
            "Test text", multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_text_generic_exception(self, mock_post):
        """Test text embedding handles generic exceptions gracefully."""
        mock_post.side_effect = Exception("Unexpected error")

        result = self.embedder.embed_text(
            "Test text", multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_text_nan_values(self, mock_post):
        """Test text embedding returns None when embeddings contain NaN."""
        embeddings_with_nan = [[0.1] * 767 + [float("nan")]]
        mock_post.return_value = MockResponse(200, {"embeddings": embeddings_with_nan})

        result = self.embedder.embed_text(
            "Test text", multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    # =========================================================================
    # Image Embedding Tests
    # =========================================================================

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_success(self, mock_post):
        """Test successful image embedding."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.2] * 768]})

        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(
            image_base64, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 768)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_no_service_url(self, mock_post):
        """Test image embedding returns None when no service URL configured."""
        # Mock the Settings dataclass to have empty URL
        self.embedder._settings = create_mock_clip_settings(clip_embedder_url="")
        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(image_base64)

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_invalid_base64(self, mock_post):
        """Test image embedding handles invalid base64 gracefully."""
        result = self.embedder.embed_image(
            "not-valid-base64!!!", multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_bad_status_code(self, mock_post):
        """Test image embedding handles bad status codes."""
        mock_post.return_value = MockResponse(500, {"error": "Server error"})

        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(
            image_base64, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_timeout(self, mock_post):
        """Test image embedding handles timeout gracefully."""
        mock_post.side_effect = Timeout()

        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(
            image_base64, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_connection_error(self, mock_post):
        """Test image embedding handles connection error gracefully."""
        mock_post.side_effect = ConnectionError()

        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(
            image_base64, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_generic_exception(self, mock_post):
        """Test image embedding handles generic exceptions gracefully."""
        mock_post.side_effect = Exception("Unexpected error")

        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(
            image_base64, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_nan_values(self, mock_post):
        """Test image embedding returns None when embeddings contain NaN."""
        embeddings_with_nan = [[0.2] * 767 + [float("nan")]]
        mock_post.return_value = MockResponse(200, {"embeddings": embeddings_with_nan})

        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(
            image_base64, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    # =========================================================================
    # Batch Text Embedding Tests
    # =========================================================================

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_success(self, mock_post):
        """Test successful batch text embedding."""
        mock_post.return_value = MockResponse(
            200, {"embeddings": [[0.1] * 768, [0.2] * 768, [0.3] * 768]}
        )

        texts = ["Text 1", "Text 2", "Text 3"]
        result = self.embedder.embed_texts_batch(
            texts, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        for embedding in result:
            self.assertEqual(len(embedding), 768)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_truncates_over_100(self, mock_post):
        """Test batch text embedding truncates to max 100 items."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768] * 100})

        texts = [f"Text {i}" for i in range(150)]
        self.embedder.embed_texts_batch(
            texts, multimodal_embedder_url="http://test:8000"
        )

        # Verify only 100 texts were sent
        call_args = mock_post.call_args
        sent_texts = call_args.kwargs["json"]["texts"]
        self.assertEqual(len(sent_texts), 100)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_no_service_url(self, mock_post):
        """Test batch text embedding returns None when no service URL."""
        # Mock the Settings dataclass to have empty URL
        self.embedder._settings = create_mock_clip_settings(clip_embedder_url="")
        result = self.embedder.embed_texts_batch(["Text 1"])

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_bad_status_code(self, mock_post):
        """Test batch text embedding raises EmbeddingServerError on 5xx.

        Unlike single-text embed_text() which returns None on all errors,
        batch methods intentionally raise EmbeddingServerError on 5xx so
        that Celery task-level retry can fire. See _embed_text_impl() vs
        embed_texts_batch() for the asymmetry rationale.
        """
        mock_post.return_value = MockResponse(500, {"error": "Server error"})

        with self.assertRaises(EmbeddingServerError):
            self.embedder.embed_texts_batch(
                ["Text 1"], multimodal_embedder_url="http://test:8000"
            )

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_nan_values(self, mock_post):
        """Test batch text embedding returns None when embeddings contain NaN."""
        embeddings_with_nan = [[0.1] * 768, [0.2] * 767 + [float("nan")]]
        mock_post.return_value = MockResponse(200, {"embeddings": embeddings_with_nan})

        result = self.embedder.embed_texts_batch(
            ["Text 1", "Text 2"], multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_3d_array_squeeze(self, mock_post):
        """Test batch text embedding handles 3D array response by squeezing."""
        # Service returns 3D array (each embedding wrapped)
        embeddings_3d = [[[0.1] * 768], [[0.2] * 768]]
        mock_post.return_value = MockResponse(200, {"embeddings": embeddings_3d})

        result = self.embedder.embed_texts_batch(
            ["Text 1", "Text 2"], multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        for embedding in result:
            self.assertEqual(len(embedding), 768)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_3d_array_bad_shape(self, mock_post):
        """Test batch text embedding returns None for 3D array with shape[1] != 1."""
        # Each embedding wrapped in a list of 2 elements (unsqueezable)
        embeddings_3d_bad = [[[0.1] * 768, [0.2] * 768], [[0.3] * 768, [0.4] * 768]]
        mock_post.return_value = MockResponse(200, {"embeddings": embeddings_3d_bad})

        result = self.embedder.embed_texts_batch(
            ["Text 1", "Text 2"], multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_exception(self, mock_post):
        """Test batch text embedding handles exceptions gracefully."""
        mock_post.side_effect = Exception("Network error")

        result = self.embedder.embed_texts_batch(
            ["Text 1"], multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    # =========================================================================
    # Batch Image Embedding Tests
    # =========================================================================

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_success(self, mock_post):
        """Test successful batch image embedding."""
        mock_post.return_value = MockResponse(
            200, {"embeddings": [[0.1] * 768, [0.2] * 768, [0.3] * 768]}
        )

        images = [create_test_image_base64() for _ in range(3)]
        result = self.embedder.embed_images_batch(
            images, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        for embedding in result:
            self.assertEqual(len(embedding), 768)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_truncates_over_20(self, mock_post):
        """Test batch image embedding truncates to max 20 items."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768] * 20})

        images = [create_test_image_base64() for _ in range(30)]
        self.embedder.embed_images_batch(
            images, multimodal_embedder_url="http://test:8000"
        )

        # Verify only 20 images were sent
        call_args = mock_post.call_args
        sent_images = call_args.kwargs["json"]["images"]
        self.assertEqual(len(sent_images), 20)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_no_service_url(self, mock_post):
        """Test batch image embedding returns None when no service URL."""
        # Mock the Settings dataclass to have empty URL
        self.embedder._settings = create_mock_clip_settings(clip_embedder_url="")
        result = self.embedder.embed_images_batch([create_test_image_base64()])

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_bad_status_code(self, mock_post):
        """Test batch image embedding raises EmbeddingServerError on 5xx.

        Unlike single-image embed_image() which returns None on all errors,
        batch methods intentionally raise EmbeddingServerError on 5xx so
        that Celery task-level retry can fire.
        """
        mock_post.return_value = MockResponse(500, {"error": "Server error"})

        with self.assertRaises(EmbeddingServerError):
            self.embedder.embed_images_batch(
                [create_test_image_base64()], multimodal_embedder_url="http://test:8000"
            )

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_nan_values(self, mock_post):
        """Test batch image embedding returns None when embeddings contain NaN."""
        embeddings_with_nan = [[0.1] * 768, [0.2] * 767 + [float("nan")]]
        mock_post.return_value = MockResponse(200, {"embeddings": embeddings_with_nan})

        result = self.embedder.embed_images_batch(
            [create_test_image_base64(), create_test_image_base64()],
            multimodal_embedder_url="http://test:8000",
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_3d_array_squeeze(self, mock_post):
        """Test batch image embedding handles 3D array response by squeezing."""
        # Service returns 3D array (each embedding wrapped)
        embeddings_3d = [[[0.1] * 768], [[0.2] * 768]]
        mock_post.return_value = MockResponse(200, {"embeddings": embeddings_3d})

        result = self.embedder.embed_images_batch(
            [create_test_image_base64(), create_test_image_base64()],
            multimodal_embedder_url="http://test:8000",
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        for embedding in result:
            self.assertEqual(len(embedding), 768)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_3d_array_bad_shape(self, mock_post):
        """Test batch image embedding returns None for 3D array with shape[1] != 1."""
        # Each embedding wrapped in a list of 2 elements (unsqueezable)
        embeddings_3d_bad = [[[0.1] * 768, [0.2] * 768], [[0.3] * 768, [0.4] * 768]]
        mock_post.return_value = MockResponse(200, {"embeddings": embeddings_3d_bad})

        result = self.embedder.embed_images_batch(
            [create_test_image_base64(), create_test_image_base64()],
            multimodal_embedder_url="http://test:8000",
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_exception(self, mock_post):
        """Test batch image embedding handles exceptions gracefully."""
        mock_post.side_effect = Exception("Network error")

        result = self.embedder.embed_images_batch(
            [create_test_image_base64()], multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    # =========================================================================
    # Service Config Tests
    # =========================================================================

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_service_config_from_settings(self, mock_post):
        """Test that service config is loaded from Settings dataclass (PipelineSettings DB)."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768]})

        # Mock the Settings dataclass with specific values (simulating PipelineSettings DB)
        embedder = CLIPMicroserviceEmbedder()
        embedder._settings = create_mock_clip_settings(
            clip_embedder_url="http://settings-url:8000",
            clip_embedder_api_key="settings-api-key",
        )
        embedder.embed_text("Test")

        call_args = mock_post.call_args
        # Check URL used
        self.assertTrue(call_args.args[0].startswith("http://settings-url:8000"))
        # Check API key header
        self.assertEqual(call_args.kwargs["headers"]["X-API-Key"], "settings-api-key")

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_service_config_direct_kwargs_override(self, mock_post):
        """Test that direct kwargs override Settings dataclass values."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768]})

        # Set default settings that should be overridden
        self.embedder._settings = create_mock_clip_settings(
            clip_embedder_url="http://default-url:8000",
            clip_embedder_api_key="default-api-key",
        )

        # Pass kwargs that should override the Settings
        self.embedder.embed_text(
            "Test",
            clip_embedder_url="http://direct-url:9000",
            clip_embedder_api_key="direct-api-key",
        )

        call_args = mock_post.call_args
        # Check URL used - kwargs should override Settings
        self.assertTrue(call_args.args[0].startswith("http://direct-url:9000"))
        # Check API key header
        self.assertEqual(call_args.kwargs["headers"]["X-API-Key"], "direct-api-key")

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.maybe_add_cloud_run_auth"
    )
    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_cloud_run_iam_auth_enabled(self, mock_post, mock_cloud_auth):
        """Test Cloud Run IAM auth is applied when enabled."""
        mock_cloud_auth.return_value = {
            "Content-Type": "application/json",
            "Authorization": "Bearer cloud-token",
        }
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768]})

        self.embedder.embed_text(
            "Test",
            multimodal_embedder_url="http://test:8000",
            use_cloud_run_iam_auth=True,
        )

        mock_cloud_auth.assert_called_once()
        # Verify the force flag was passed
        call_args = mock_cloud_auth.call_args
        self.assertTrue(call_args.kwargs.get("force") or call_args.args[2])

    # =========================================================================
    # Embedder Attributes Tests
    # =========================================================================

    def test_embedder_attributes(self):
        """Test embedder has correct attributes."""
        self.assertEqual(self.embedder.vector_size, 768)
        self.assertTrue(self.embedder.is_multimodal)
        self.assertTrue(self.embedder.supports_text)
        self.assertTrue(self.embedder.supports_images)
        self.assertIn(ContentModality.TEXT, self.embedder.supported_modalities)
        self.assertIn(ContentModality.IMAGE, self.embedder.supported_modalities)

    def test_get_supported_modalities_as_strings(self):
        """Test get_supported_modalities_as_strings returns correct values."""
        modalities = self.embedder.get_supported_modalities_as_strings()
        self.assertIn("TEXT", modalities)
        self.assertIn("IMAGE", modalities)

    # =========================================================================
    # 4xx Client Error Tests
    # =========================================================================

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_image_client_error_4xx(self, mock_post):
        """Test image embedding handles 4xx client errors (non-retriable)."""
        mock_post.return_value = MockResponse(400, {"error": "Bad request"})

        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(
            image_base64, multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_text_client_error_4xx(self, mock_post):
        """Test text embedding handles 4xx client errors (non-retriable)."""
        mock_post.return_value = MockResponse(422, {"error": "Validation error"})

        result = self.embedder.embed_text(
            "Test text", multimodal_embedder_url="http://test:8000"
        )

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_texts_batch_client_error_4xx(self, mock_post):
        """Test batch text embedding raises EmbeddingClientError on 4xx.

        Batch methods raise EmbeddingClientError on 4xx so callers can
        distinguish a client-side failure from a parsing error (which
        still returns None). The batch task helper swallows it and
        records permanent failures without triggering Celery retry.
        """
        mock_post.return_value = MockResponse(413, {"error": "Payload too large"})

        with self.assertRaises(EmbeddingClientError):
            self.embedder.embed_texts_batch(
                ["Text 1", "Text 2"], multimodal_embedder_url="http://test:8000"
            )

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_embed_images_batch_client_error_4xx(self, mock_post):
        """Test batch image embedding raises EmbeddingClientError on 4xx.

        Same asymmetry rationale as ``test_embed_texts_batch_client_error_4xx``.
        """
        mock_post.return_value = MockResponse(400, {"error": "Bad request"})

        with self.assertRaises(EmbeddingClientError):
            self.embedder.embed_images_batch(
                [create_test_image_base64()], multimodal_embedder_url="http://test:8000"
            )

    # =========================================================================
    # New-Style Service Config Tests (clip_embedder_url, clip_embedder_api_key)
    # =========================================================================

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_service_config_new_style_kwargs(self, mock_post):
        """Test that new-style kwargs (clip_embedder_url) work correctly."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768]})

        self.embedder.embed_text(
            "Test",
            clip_embedder_url="http://new-style-url:9000",
            clip_embedder_api_key="new-style-api-key",
        )

        call_args = mock_post.call_args
        # Check URL used
        self.assertTrue(call_args.args[0].startswith("http://new-style-url:9000"))
        # Check API key header
        self.assertEqual(call_args.kwargs["headers"]["X-API-Key"], "new-style-api-key")

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_service_config_new_style_settings(self, mock_post):
        """Test that Settings dataclass values are used correctly."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768]})

        # Mock the Settings dataclass (simulating values from PipelineSettings DB)
        embedder = CLIPMicroserviceEmbedder()
        embedder._settings = create_mock_clip_settings(
            clip_embedder_url="http://new-settings-url:8000",
            clip_embedder_api_key="new-settings-api-key",
        )
        embedder.embed_text("Test")

        call_args = mock_post.call_args
        # Check URL used
        self.assertTrue(call_args.args[0].startswith("http://new-settings-url:8000"))
        # Check API key header
        self.assertEqual(
            call_args.kwargs["headers"]["X-API-Key"], "new-settings-api-key"
        )

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_service_config_new_style_kwargs_override_legacy(self, mock_post):
        """Test new-style kwargs take precedence over legacy kwargs."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 768]})

        self.embedder.embed_text(
            "Test",
            # Legacy kwargs
            multimodal_embedder_url="http://legacy-url:8000",
            multimodal_embedder_api_key="legacy-api-key",
            # New-style kwargs should take precedence
            clip_embedder_url="http://new-style-url:9000",
            clip_embedder_api_key="new-style-api-key",
        )

        call_args = mock_post.call_args
        # New-style should win
        self.assertTrue(call_args.args[0].startswith("http://new-style-url:9000"))
        self.assertEqual(call_args.kwargs["headers"]["X-API-Key"], "new-style-api-key")


class TestQwenMicroserviceEmbedderUnit(TestCase):
    """Unit tests for QwenMicroserviceEmbedder with mocked HTTP calls."""

    def setUp(self):
        from opencontractserver.pipeline.embedders.multimodal_microservice import (
            QwenMicroserviceEmbedder,
        )

        self.embedder = QwenMicroserviceEmbedder()

    def test_qwen_embedder_attributes(self):
        """Test Qwen embedder has correct attributes."""
        self.assertEqual(self.embedder.vector_size, 1024)
        self.assertEqual(self.embedder.title, "Qwen Microservice Embedder")

    def test_qwen_default_url(self):
        """Test Qwen embedder has correct default URL."""
        self.assertEqual(self.embedder._default_url, "http://qwen-embedder:8000")

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_qwen_embed_text_success(self, mock_post):
        """Test successful text embedding with Qwen embedder."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 1024]})

        result = self.embedder.embed_text(
            "Test text", qwen_embedder_url="http://test:8000"
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1024)
        mock_post.assert_called_once()

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_qwen_embed_image_success(self, mock_post):
        """Test successful image embedding with Qwen embedder."""
        mock_post.return_value = MockResponse(200, {"embeddings": [[0.2] * 1024]})

        image_base64 = create_test_image_base64()
        result = self.embedder.embed_image(
            image_base64, qwen_embedder_url="http://test:8000"
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1024)

    @patch(
        "opencontractserver.pipeline.embedders.multimodal_microservice.requests.post"
    )
    def test_qwen_service_config_from_settings(self, mock_post):
        """
        Test Qwen embedder loads config from Settings dataclass (PipelineSettings DB).
        """
        from opencontractserver.pipeline.embedders.multimodal_microservice import (
            QwenMicroserviceEmbedder,
        )

        mock_post.return_value = MockResponse(200, {"embeddings": [[0.1] * 1024]})

        # Create instance and mock its Settings
        embedder = QwenMicroserviceEmbedder()
        embedder._settings = create_mock_qwen_settings(
            qwen_embedder_url="http://qwen-settings-url:8000",
            qwen_embedder_api_key="qwen-settings-api-key",
        )
        embedder.embed_text("Test")

        call_args = mock_post.call_args
        # Check URL used - should use the Settings value
        self.assertTrue(call_args.args[0].startswith("http://qwen-settings-url:8000"))
        # Check API key header
        self.assertEqual(
            call_args.kwargs["headers"]["X-API-Key"], "qwen-settings-api-key"
        )
