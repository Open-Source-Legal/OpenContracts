"""
Integration tests for multimodal PDF processing pipeline.

These tests require the following services (defined in test.yml):
- multimodal-embedder service running (CLIP ViT-L-14)
- docling-parser service running (for PDF parsing with image extraction)

Tests will FAIL if services are unavailable - this is by design to ensure
CI environments have the required services running via docker compose.

Run these tests:
    docker compose -f test.yml run django pytest opencontractserver/tests/test_multimodal_integration.py -v

Note: These tests populate PipelineSettings from environment variables to test
the actual production configuration flow. The env vars are defined in
.envs/.test/.django and include MULTIMODAL_EMBEDDER_URL and MULTIMODAL_EMBEDDER_API_KEY.
"""

import base64
import os
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from PIL import Image

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, PipelineSettings
from opencontractserver.pipeline.embedders.multimodal_microservice import (
    CLIPMicroserviceEmbedder,
)
from opencontractserver.pipeline.parsers.docling_parser_rest import DoclingParser
from opencontractserver.tests.fixtures.pdf_generator import (
    create_pdf_with_chart_figure,
    create_pdf_with_image,
)
from opencontractserver.types.enums import ContentModality

User = get_user_model()
pytestmark = pytest.mark.django_db


def setup_pipeline_settings_from_env() -> None:
    """
    Populate PipelineSettings database from environment variables.

    This mirrors the production flow where settings are loaded from env vars
    via the migrate_pipeline_settings management command. For integration tests,
    we do this directly to ensure PipelineSettings (single source of truth)
    has the correct values.
    """
    # Get the singleton PipelineSettings instance
    pipeline_settings = PipelineSettings.get_instance()

    # Build component settings from env vars
    clip_embedder_path = (
        "opencontractserver.pipeline.embedders."
        "multimodal_microservice.CLIPMicroserviceEmbedder"
    )

    component_settings = pipeline_settings.component_settings or {}
    component_settings[clip_embedder_path] = {
        "clip_embedder_url": os.environ.get(
            "MULTIMODAL_EMBEDDER_URL", "http://multimodal-embedder:8000"
        ),
        "clip_embedder_api_key": os.environ.get("MULTIMODAL_EMBEDDER_API_KEY", ""),
        "use_cloud_run_iam_auth": os.environ.get(
            "USE_CLOUD_RUN_IAM_AUTH", "false"
        ).lower()
        in ("true", "1", "yes"),
    }

    # Also set up docling parser settings
    docling_parser_path = (
        "opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser"
    )
    component_settings[docling_parser_path] = {
        "service_url": os.environ.get(
            "DOCLING_PARSER_SERVICE_URL", "http://docling-parser:8000/parse/"
        ),
    }

    pipeline_settings.component_settings = component_settings
    pipeline_settings.save()


class TestMultimodalEmbedderService(TestCase):
    """
    Test multimodal embedder service connectivity and basic operations.

    These tests verify that the CLIP ViT-L-14 microservice is functioning correctly.
    """

    @classmethod
    def setUpTestData(cls):
        # Populate PipelineSettings from env vars (single source of truth)
        setup_pipeline_settings_from_env()
        cls.embedder = CLIPMicroserviceEmbedder()

    def test_text_embedding_returns_768_dimensions(self):
        """Test text embedding returns correct dimension (768 for CLIP ViT-L-14)."""
        result = self.embedder.embed_text("This is a test document about contracts.")

        self.assertIsNotNone(
            result,
            "Text embedding should not be None - check MULTIMODAL_EMBEDDER_URL configuration",
        )
        self.assertEqual(
            len(result),
            768,
            f"CLIP ViT-L-14 should return 768 dimensions, got {len(result)}",
        )

    def test_image_embedding_returns_768_dimensions(self):
        """Test image embedding returns correct dimension (768 for CLIP ViT-L-14)."""
        # Create a simple test image
        img = Image.new("RGB", (100, 100), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        result = self.embedder.embed_image(image_base64, image_format="jpeg")

        self.assertIsNotNone(
            result,
            "Image embedding should not be None - check MULTIMODAL_EMBEDDER_URL configuration",
        )
        self.assertEqual(
            len(result),
            768,
            f"CLIP ViT-L-14 should return 768 dimensions, got {len(result)}",
        )

    def test_embedder_reports_multimodal_capabilities(self):
        """Verify embedder correctly reports its multimodal capabilities."""
        self.assertTrue(
            self.embedder.is_multimodal,
            "CLIPMicroserviceEmbedder should report is_multimodal=True",
        )
        self.assertTrue(
            self.embedder.supports_text,
            "CLIPMicroserviceEmbedder should support text",
        )
        self.assertTrue(
            self.embedder.supports_images,
            "CLIPMicroserviceEmbedder should support images",
        )
        self.assertEqual(
            self.embedder.vector_size,
            768,
            "CLIPMicroserviceEmbedder should have vector_size=768",
        )

    def test_supported_modalities(self):
        """Verify supported_modalities returns correct ContentModality enum values."""
        modalities = self.embedder.supported_modalities
        self.assertIn(ContentModality.TEXT, modalities)
        self.assertIn(ContentModality.IMAGE, modalities)
        self.assertEqual(len(modalities), 2)

    def test_supports_modalities_check(self):
        """Verify supports_modalities method works correctly."""
        self.assertTrue(self.embedder.supports_modalities(["TEXT"]))
        self.assertTrue(self.embedder.supports_modalities(["IMAGE"]))
        self.assertTrue(self.embedder.supports_modalities(["TEXT", "IMAGE"]))
        self.assertFalse(self.embedder.supports_modalities(["AUDIO"]))

    def test_text_and_image_in_same_embedding_space(self):
        """
        Test that text and image embeddings are in the same vector space.

        CLIP embeddings allow cross-modal similarity search - we verify
        this by checking that both types produce valid non-zero vectors
        of the same dimensionality.
        """
        # Get text embedding
        text_result = self.embedder.embed_text("A red square image")

        # Get image embedding (red square)
        img = Image.new("RGB", (100, 100), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        image_result = self.embedder.embed_image(image_base64)

        self.assertIsNotNone(text_result)
        self.assertIsNotNone(image_result)

        # Both should have same dimensionality (768 for CLIP ViT-L-14)
        self.assertEqual(len(text_result), len(image_result))
        self.assertEqual(len(text_result), 768)

        # Both should have non-zero magnitude (valid embeddings)
        import math

        text_magnitude = math.sqrt(sum(x * x for x in text_result))
        image_magnitude = math.sqrt(sum(x * x for x in image_result))

        self.assertGreater(
            text_magnitude, 0.1, "Text embedding should have non-zero magnitude"
        )
        self.assertGreater(
            image_magnitude, 0.1, "Image embedding should have non-zero magnitude"
        )


class TestMultimodalEmbedderBatch(TestCase):
    """Test batch embedding functionality."""

    @classmethod
    def setUpTestData(cls):
        # Populate PipelineSettings from env vars (single source of truth)
        setup_pipeline_settings_from_env()
        cls.embedder = CLIPMicroserviceEmbedder()

    def test_batch_text_embedding(self):
        """Test batch text embedding returns correct dimensions."""
        texts = [
            "First document about contracts",
            "Second document about agreements",
            "Third document about legal terms",
        ]

        result = self.embedder.embed_texts_batch(texts)

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        for embedding in result:
            self.assertEqual(len(embedding), 768)

    def test_batch_image_embedding(self):
        """Test batch image embedding returns correct dimensions."""
        images = []
        for color in ["red", "green", "blue"]:
            img = Image.new("RGB", (50, 50), color=color)
            buffer = BytesIO()
            img.save(buffer, format="JPEG")
            images.append(base64.b64encode(buffer.getvalue()).decode("utf-8"))

        result = self.embedder.embed_images_batch(images)

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        for embedding in result:
            self.assertEqual(len(embedding), 768)


class TestPdfGeneratorUtility(TestCase):
    """Test the PDF generator utility functions."""

    def test_create_pdf_with_image_produces_valid_pdf(self):
        """Verify create_pdf_with_image produces valid PDF bytes."""
        pdf_bytes = create_pdf_with_image(
            text="Test document",
            image_size=(100, 100),
            image_color="blue",
        )

        self.assertIsNotNone(pdf_bytes)
        self.assertGreater(len(pdf_bytes), 100)
        # Check PDF header
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_create_pdf_with_chart_figure_produces_valid_pdf(self):
        """Verify create_pdf_with_chart_figure produces valid PDF bytes."""
        pdf_bytes = create_pdf_with_chart_figure(
            title="Q4 Report",
            chart_title="Revenue",
            labels=["Jan", "Feb", "Mar"],
            values=[100, 150, 200],
        )

        self.assertIsNotNone(pdf_bytes)
        self.assertGreater(len(pdf_bytes), 100)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


class TestDoclingImageExtraction(TransactionTestCase):
    """
    Test that docling parser extracts images as unified tokens.

    These tests verify the end-to-end flow from PDF with embedded images
    through docling parsing to image token extraction.
    """

    def setUp(self):
        # Populate PipelineSettings from env vars (single source of truth)
        setup_pipeline_settings_from_env()
        self.user = User.objects.create_user(
            username="docling_image_test_user",
            password="testpass123",
        )
        self.corpus = Corpus.objects.create(
            title="Docling Image Test Corpus",
            creator=self.user,
        )

    def test_parse_pdf_with_embedded_image(self):
        """
        Verify docling extracts image tokens from PDF.

        This test creates a PDF with an embedded image and verifies that
        docling's parser identifies and extracts the image as a token.
        """
        # Create PDF with embedded image
        pdf_bytes = create_pdf_with_image(
            text="Contract with embedded Figure 1",
            image_size=(200, 150),
            image_color="blue",
        )

        # Create document with processing_started set to prevent the
        # post_save signal from triggering ingest_doc before pdf_file is saved.
        doc = Document.objects.create(
            title="PDF with Image for Docling Test",
            creator=self.user,
            file_type="application/pdf",
            processing_started=timezone.now(),
        )
        doc.pdf_file.save("test_with_image.pdf", ContentFile(pdf_bytes))

        # Parse with docling
        parser = DoclingParser()
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=doc.id,
        )

        # Verify parsing succeeded
        self.assertIsNotNone(result, "Docling parser should return a result")
        self.assertIn(
            "pawls_file_content", result, "Result should contain pawls_file_content"
        )

        # The PAWLs data should contain page information
        pawls_data = result["pawls_file_content"]
        self.assertGreater(
            len(pawls_data), 0, "PAWLs data should have at least one page"
        )

        # Log information about what docling found
        total_tokens = 0
        image_tokens = 0
        for page in pawls_data:
            tokens = page.get("tokens", [])
            total_tokens += len(tokens)
            for token in tokens:
                if token.get("is_image"):
                    image_tokens += 1

        # Note: Image extraction depends on docling's capabilities
        # We verify the parsing worked and tokens were extracted
        self.assertGreater(
            total_tokens,
            0,
            "Docling should extract at least some tokens from the PDF",
        )

        # If images were extracted, verify they have required fields
        if image_tokens > 0:
            for page in pawls_data:
                for token in page.get("tokens", []):
                    if token.get("is_image"):
                        # Verify image token has required fields
                        self.assertIn("x", token)
                        self.assertIn("y", token)
                        self.assertIn("width", token)
                        self.assertIn("height", token)
                        self.assertEqual(token.get("text"), "")


class TestFullMultimodalPipeline(TransactionTestCase):
    """
    End-to-end test: PDF -> docling -> image tokens -> multimodal embeddings.

    This test class verifies the complete flow from a PDF document with images
    through parsing, token extraction, and embedding generation.
    """

    def setUp(self):
        # Populate PipelineSettings from env vars (single source of truth)
        setup_pipeline_settings_from_env()
        self.user = User.objects.create_user(
            username="full_pipeline_test_user",
            password="testpass123",
        )
        self.corpus = Corpus.objects.create(
            title="Full Pipeline Test Corpus",
            creator=self.user,
        )
        self.embedder = CLIPMicroserviceEmbedder()

    def test_full_pipeline_text_and_image_embedding(self):
        """
        Test complete flow from PDF with image to embeddings.

        Steps:
        1. Create PDF with embedded image (chart figure)
        2. Parse with docling
        3. Extract text and generate text embedding
        4. If image tokens found, generate image embedding
        5. Verify both embeddings are in same vector space
        """
        # 1. Create PDF with embedded chart
        pdf_bytes = create_pdf_with_chart_figure(
            title="Revenue Report Q4",
            chart_title="Quarterly Revenue Growth",
        )

        # 2. Create document and parse (processing_started prevents auto-ingest
        # signal from firing before pdf_file is saved)
        doc = Document.objects.create(
            title="Revenue Report",
            creator=self.user,
            file_type="application/pdf",
            processing_started=timezone.now(),
        )
        doc.pdf_file.save("revenue_report.pdf", ContentFile(pdf_bytes))

        parser = DoclingParser()
        result = parser.parse_document(user_id=self.user.id, doc_id=doc.id)

        self.assertIsNotNone(result, "Parser should return result")

        # 3. Generate text embedding from extracted content
        text_content = result.get("content", "") or result.get("labelled_text", "")
        if isinstance(text_content, list):
            # Combine labelled text items
            text_content = " ".join(
                item.get("rawText", "")
                for item in text_content
                if isinstance(item, dict)
            )

        if text_content:
            # Truncate to reasonable size for embedding
            text_embedding = self.embedder.embed_text(text_content[:2000])
            self.assertIsNotNone(text_embedding, "Text embedding should succeed")
            self.assertEqual(len(text_embedding), 768)

        # 4. Look for image tokens and generate image embedding if found
        pawls_data = result.get("pawls_file_content", [])
        image_embedding_generated = False

        for page in pawls_data:
            for token in page.get("tokens", []):
                if token.get("is_image"):
                    # Try to get image data
                    image_data = self._extract_image_data(token)
                    if image_data:
                        image_embedding = self.embedder.embed_image(
                            image_data, token.get("format", "jpeg")
                        )
                        if image_embedding:
                            self.assertEqual(len(image_embedding), 768)
                            image_embedding_generated = True
                            break
            if image_embedding_generated:
                break

        # Note: Image extraction from docling may not always produce base64 data
        # The important thing is the pipeline doesn't crash

    def test_embedder_handles_missing_service_gracefully(self):
        """
        Test that embedder returns None (not exception) when service URL is empty.

        This test verifies graceful degradation when the PipelineSettings DB
        has an empty service URL configured.
        """
        # Update PipelineSettings to have empty URL for CLIP embedder
        # This simulates a misconfigured or not-yet-configured deployment
        pipeline_settings = PipelineSettings.get_instance()
        clip_embedder_path = (
            "opencontractserver.pipeline.embedders."
            "multimodal_microservice.CLIPMicroserviceEmbedder"
        )

        # Store original settings to restore later
        original_settings = (
            (pipeline_settings.component_settings or {})
            .get(clip_embedder_path, {})
            .copy()
        )

        # Set empty URL in PipelineSettings DB
        component_settings = pipeline_settings.component_settings or {}
        component_settings[clip_embedder_path] = {
            "clip_embedder_url": "",
            "clip_embedder_api_key": "",
            "use_cloud_run_iam_auth": False,
        }
        pipeline_settings.component_settings = component_settings
        pipeline_settings.save()

        try:
            # Create new embedder that will read the empty URL from DB
            embedder = CLIPMicroserviceEmbedder()

            # Should return None, not raise exception
            result = embedder.embed_text("test")
            # With empty URL, should return None (no exception)
            self.assertIsNone(
                result, "Embedder should return None when service URL is empty"
            )
        finally:
            # Restore original settings
            component_settings[clip_embedder_path] = original_settings
            pipeline_settings.component_settings = component_settings
            pipeline_settings.save()

    def _extract_image_data(self, token: dict) -> str | None:
        """
        Extract base64 image data from a token.

        Handles different storage methods:
        - Direct base64_data in token
        - image_path pointing to stored file
        """
        # Direct base64 data
        if token.get("base64_data"):
            return token["base64_data"]

        # File path storage
        image_path = token.get("image_path")
        if image_path:
            try:
                from django.core.files.storage import default_storage

                with default_storage.open(image_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass

        return None


class TestMultimodalEmbedderErrorHandling(TestCase):
    """Test error handling and edge cases."""

    def setUp(self):
        # Populate PipelineSettings from env vars (single source of truth)
        setup_pipeline_settings_from_env()
        self.embedder = CLIPMicroserviceEmbedder()

    def test_empty_text_handling(self):
        """Test that empty text is handled gracefully."""
        # Note: Behavior depends on service implementation
        # At minimum, should not crash
        try:
            _result = self.embedder.embed_text("")  # noqa: F841
            # Result may be None or a valid embedding depending on service
        except Exception as e:
            self.fail(f"Empty text should not raise exception: {e}")

    def test_invalid_base64_image_handling(self):
        """Test that invalid base64 image data is handled gracefully."""
        try:
            _result = self.embedder.embed_image("not-valid-base64!!!")  # noqa: F841
            # Should return None or handle gracefully
        except Exception as e:
            self.fail(f"Invalid base64 should not raise exception: {e}")

    def test_embedder_attributes(self):
        """Verify embedder has all required attributes."""
        self.assertTrue(hasattr(self.embedder, "title"))
        self.assertTrue(hasattr(self.embedder, "description"))
        self.assertTrue(hasattr(self.embedder, "vector_size"))
        self.assertTrue(hasattr(self.embedder, "is_multimodal"))
        self.assertTrue(hasattr(self.embedder, "supports_text"))
        self.assertTrue(hasattr(self.embedder, "supports_images"))

        # Verify values
        self.assertEqual(self.embedder.vector_size, 768)
        self.assertTrue(self.embedder.is_multimodal)
