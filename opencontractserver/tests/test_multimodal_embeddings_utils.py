"""
Tests for opencontractserver/utils/multimodal_embeddings.py.

Tests the utility functions for multimodal embedding generation.
"""

import base64
import json
import math
from io import BytesIO
from typing import Optional
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.types.enums import ContentModality
from opencontractserver.utils.multimodal_embeddings import (
    embed_images_average,
    generate_multimodal_embedding,
    get_annotation_image_tokens,
    get_multimodal_weights,
    normalize_vector,
    weighted_average_embeddings,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


class MockEmbedder(BaseEmbedder):
    """Mock embedder for testing."""

    title = "Mock Embedder"
    description = "Mock embedder for testing"
    vector_size = 768
    supported_modalities = {ContentModality.TEXT, ContentModality.IMAGE}

    def __init__(self, text_embedding=None, image_embedding=None, **kwargs):
        super().__init__(**kwargs)
        self._text_embedding = text_embedding or [0.1] * 768
        self._image_embedding = image_embedding or [0.2] * 768

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        return self._text_embedding

    def _embed_image_impl(
        self, image_base64: str, image_format: str = "jpeg", **all_kwargs
    ) -> Optional[list[float]]:
        return self._image_embedding


class MockTextOnlyEmbedder(BaseEmbedder):
    """Mock text-only embedder for testing."""

    title = "Mock Text-Only Embedder"
    description = "Mock text-only embedder for testing"
    vector_size = 768
    supported_modalities = {ContentModality.TEXT}

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        return [0.1] * 768


class TestGetMultimodalWeights(TestCase):
    """Tests for get_multimodal_weights function."""

    def test_default_weights(self):
        """Should return default weights when not configured."""
        text_weight, image_weight = get_multimodal_weights()
        self.assertEqual(text_weight, 0.3)
        self.assertEqual(image_weight, 0.7)

    @override_settings(
        MULTIMODAL_EMBEDDING_WEIGHTS={"text_weight": 0.5, "image_weight": 0.5}
    )
    def test_weights_from_settings(self):
        """Should return weights from settings."""
        text_weight, image_weight = get_multimodal_weights()
        self.assertEqual(text_weight, 0.5)
        self.assertEqual(image_weight, 0.5)

    @override_settings(MULTIMODAL_EMBEDDING_WEIGHTS={"text_weight": 0.8})
    def test_partial_settings(self):
        """Should use defaults for missing weights."""
        text_weight, image_weight = get_multimodal_weights()
        self.assertEqual(text_weight, 0.8)
        self.assertEqual(image_weight, 0.7)  # Default

    @override_settings(MULTIMODAL_EMBEDDING_WEIGHTS={})
    def test_empty_settings(self):
        """Should return defaults for empty settings."""
        text_weight, image_weight = get_multimodal_weights()
        self.assertEqual(text_weight, 0.3)
        self.assertEqual(image_weight, 0.7)


class TestNormalizeVector(TestCase):
    """Tests for normalize_vector function."""

    def test_normalizes_to_unit_length(self):
        """Normalized vector should have unit length."""
        vector = [3.0, 4.0]  # 3-4-5 triangle
        result = normalize_vector(vector)

        # Check unit length (within floating point tolerance)
        length = math.sqrt(sum(x * x for x in result))
        self.assertAlmostEqual(length, 1.0, places=10)

    def test_preserves_direction(self):
        """Normalized vector should preserve direction (proportions)."""
        vector = [3.0, 4.0]
        result = normalize_vector(vector)

        # 3:4 ratio should be preserved
        ratio = result[0] / result[1]
        self.assertAlmostEqual(ratio, 0.75, places=10)

    def test_zero_vector_returns_zero(self):
        """Zero vector should remain zero (norm is 0)."""
        vector = [0.0, 0.0, 0.0]
        result = normalize_vector(vector)
        self.assertEqual(result, [0.0, 0.0, 0.0])

    def test_already_unit_vector(self):
        """Already unit vector should stay unit."""
        vector = [1.0, 0.0, 0.0]
        result = normalize_vector(vector)
        self.assertAlmostEqual(result[0], 1.0)
        self.assertAlmostEqual(result[1], 0.0)
        self.assertAlmostEqual(result[2], 0.0)

    def test_high_dimensional_vector(self):
        """Should work with high-dimensional vectors."""
        vector = [1.0] * 768
        result = normalize_vector(vector)

        length = math.sqrt(sum(x * x for x in result))
        self.assertAlmostEqual(length, 1.0, places=10)


class TestWeightedAverageEmbeddings(TestCase):
    """Tests for weighted_average_embeddings function."""

    def test_empty_list_returns_empty(self):
        """Empty vectors list should return empty."""
        result = weighted_average_embeddings([], [])
        self.assertEqual(result, [])

    def test_single_vector(self):
        """Single vector should be returned normalized."""
        vector = [[3.0, 4.0]]
        weights = [1.0]
        result = weighted_average_embeddings(vector, weights)

        # Should be normalized
        length = math.sqrt(sum(x * x for x in result))
        self.assertAlmostEqual(length, 1.0, places=10)

    def test_equal_weights(self):
        """Equal weights should give simple average."""
        vectors = [[1.0, 0.0], [0.0, 1.0]]
        weights = [1.0, 1.0]
        result = weighted_average_embeddings(vectors, weights)

        # Average of [1,0] and [0,1] is [0.5, 0.5], normalized
        expected_length = math.sqrt(0.5 * 0.5 + 0.5 * 0.5)
        self.assertAlmostEqual(result[0], 0.5 / expected_length, places=10)
        self.assertAlmostEqual(result[1], 0.5 / expected_length, places=10)

    def test_unequal_weights(self):
        """Unequal weights should bias toward heavier weight."""
        vectors = [[1.0, 0.0], [0.0, 1.0]]
        weights = [3.0, 1.0]  # 75% weight on first vector
        result = weighted_average_embeddings(vectors, weights)

        # Result should be closer to first vector
        self.assertGreater(result[0], result[1])

    def test_weights_normalized(self):
        """Weights should be normalized to sum to 1."""
        vectors = [[1.0, 0.0], [0.0, 1.0]]
        weights = [10.0, 10.0]  # Sum to 20, not 1
        result = weighted_average_embeddings(vectors, weights)

        # Should still give same result as [0.5, 0.5]
        length = math.sqrt(sum(x * x for x in result))
        self.assertAlmostEqual(length, 1.0, places=10)

    def test_different_dimensions_raises_error(self):
        """Vectors with different dimensions should raise ValueError."""
        vectors = [[1.0, 0.0], [0.0, 1.0, 0.0]]  # 2D and 3D
        weights = [0.5, 0.5]

        with self.assertRaises(ValueError) as context:
            weighted_average_embeddings(vectors, weights)

        self.assertIn("different dimensions", str(context.exception))


class TestGetAnnotationImageTokens(TestCase):
    """Tests for get_annotation_image_tokens function."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="test_multimodal_user", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=cls.user,
        )
        cls.label = AnnotationLabel.objects.create(
            text="Test Label",
            creator=cls.user,
        )

    def _create_sample_image_base64(self, width=100, height=100):
        """Create sample base64 image."""
        from PIL import Image

        img = Image.new("RGB", (width, height), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _create_document_with_pawls(self, pawls_data):
        """Helper to create a document with PAWLs data."""
        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
            pawls_parse_file=ContentFile(
                json.dumps(pawls_data).encode(), name="test.pawls"
            ),
        )
        self.corpus.add_document(document=document, user=self.user)
        return document

    def test_no_document_returns_empty(self):
        """Annotation with no document should return empty list."""
        annotation = MagicMock()
        annotation.document = None
        annotation.pk = 1

        result = get_annotation_image_tokens(annotation)
        self.assertEqual(result, [])

    def test_no_pawls_data_returns_empty(self):
        """Document without PAWLs data should return empty list."""
        document = Document.objects.create(
            title="Test Doc No Pawls",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
        )
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json={"0": {"tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}]}},
        )

        result = get_annotation_image_tokens(annotation)
        self.assertEqual(result, [])

    def test_no_images_in_tokens(self):
        """Tokens without images should return empty list."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                ],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json={"0": {"tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}]}},
        )

        result = get_annotation_image_tokens(annotation)
        self.assertEqual(result, [])

    def test_finds_image_tokens(self):
        """Should find image tokens in annotation."""
        base64_data = self._create_sample_image_base64()
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "base64_data": base64_data,
                    },
                ],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json={
                "0": {
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 0},
                        {"pageIndex": 0, "tokenIndex": 1},
                    ]
                }
            },
        )

        result = get_annotation_image_tokens(annotation)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].get("is_image"))

    def test_uses_provided_pawls_data(self):
        """Should use provided pawls_data instead of loading from document."""
        base64_data = self._create_sample_image_base64()
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "base64_data": base64_data,
                    },
                ],
            }
        ]
        document = Document.objects.create(
            title="Test Doc No Pawls",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
        )
        self.corpus.add_document(document=document, user=self.user)
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json={"0": {"tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}]}},
        )

        # Pass pawls_data directly
        result = get_annotation_image_tokens(annotation, pawls_data=pawls_data)
        self.assertEqual(len(result), 1)

    def test_handles_invalid_token_refs(self):
        """Should skip invalid token references (out-of-bounds token index)."""
        base64_data = self._create_sample_image_base64()
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "base64_data": base64_data,
                    },
                ],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json={
                "0": {
                    "bounds": {"top": 200, "left": 100, "right": 300, "bottom": 350},
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 99},  # Out of bounds token
                        {"pageIndex": 0, "tokenIndex": 0},  # Valid image token
                    ],
                    "rawText": "",
                }
            },
        )

        result = get_annotation_image_tokens(annotation, pawls_data=pawls_data)
        self.assertEqual(len(result), 1)

    def test_v2_compact_format_finds_image_tokens(self):
        """get_annotation_image_tokens works with v2 compact annotation JSON."""
        base64_data = self._create_sample_image_base64()
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 10, "y": 10, "width": 50, "height": 12, "text": "Hi"},
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "base64_data": base64_data,
                    },
                ],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)
        # Use v2 compact format: page 0, tokens 0 and 1
        v2_json = {"v": 2, "p": {"0": {"b": [10, 10, 300, 350], "t": "0-1"}}}
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json=v2_json,
        )

        result = get_annotation_image_tokens(annotation, pawls_data=pawls_data)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].get("is_image"))

    def test_out_of_bounds_page_index_skipped(self):
        """Annotation referencing pages beyond PAWLs data is safely skipped."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [{"x": 10, "y": 10, "width": 50, "height": 12, "text": "Hi"}],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)
        # Annotation references page 5, but PAWLs only has page 0
        v2_json = {"v": 2, "p": {"5": {"b": [0, 0, 0, 0], "t": "0"}}}
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json=v2_json,
        )

        result = get_annotation_image_tokens(annotation, pawls_data=pawls_data)
        self.assertEqual(result, [])

    def test_non_dict_pawls_page_skipped(self):
        """Non-dict entries in PAWLs data are safely skipped."""
        pawls_data = ["not_a_dict"]
        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
        )
        self.corpus.add_document(document=document, user=self.user)
        v2_json = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": "0"}}}
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json=v2_json,
        )

        result = get_annotation_image_tokens(annotation, pawls_data=pawls_data)
        self.assertEqual(result, [])


class TestEmbedImagesAverage(TestCase):
    """Tests for embed_images_average function."""

    def _create_sample_image_base64(self, width=100, height=100):
        """Create sample base64 image."""
        from PIL import Image

        img = Image.new("RGB", (width, height), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def test_empty_list_returns_none(self):
        """Empty image tokens should return None."""
        embedder = MockEmbedder()
        result = embed_images_average(embedder, [])
        self.assertIsNone(result)

    def test_single_image(self):
        """Single image should return its embedding normalized."""
        embedder = MockEmbedder(image_embedding=[3.0, 4.0] + [0.0] * 766)
        image_tokens = [
            {"is_image": True, "base64_data": self._create_sample_image_base64()}
        ]

        result = embed_images_average(embedder, image_tokens)

        self.assertIsNotNone(result)
        length = math.sqrt(sum(x * x for x in result))
        self.assertAlmostEqual(length, 1.0, places=10)

    def test_multiple_images_averaged(self):
        """Multiple images should be averaged."""
        embedder = MockEmbedder(image_embedding=[1.0, 0.0] + [0.0] * 766)
        image_tokens = [
            {"is_image": True, "base64_data": self._create_sample_image_base64()},
            {"is_image": True, "base64_data": self._create_sample_image_base64()},
        ]

        result = embed_images_average(embedder, image_tokens)
        self.assertIsNotNone(result)

    def test_skips_tokens_without_base64_data(self):
        """Should skip tokens without base64_data."""
        embedder = MockEmbedder()
        image_tokens = [
            {"is_image": True},  # No base64_data
            {"is_image": True, "base64_data": self._create_sample_image_base64()},
        ]

        result = embed_images_average(embedder, image_tokens)
        self.assertIsNotNone(result)

    def test_handles_embedding_failure(self):
        """Should handle embedding failures gracefully."""
        embedder = MagicMock()
        embedder.embed_image.side_effect = Exception("Embedding failed")

        image_tokens = [
            {"is_image": True, "base64_data": self._create_sample_image_base64()}
        ]

        result = embed_images_average(embedder, image_tokens)
        self.assertIsNone(result)


class TestGenerateMultimodalEmbedding(TestCase):
    """Tests for generate_multimodal_embedding function."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="test_generate_mm_user", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=cls.user,
        )
        cls.label = AnnotationLabel.objects.create(
            text="Test Label",
            creator=cls.user,
        )

    def _create_sample_image_base64(self, width=100, height=100):
        """Create sample base64 image."""
        from PIL import Image

        img = Image.new("RGB", (width, height), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _create_document_with_pawls(self, pawls_data):
        """Helper to create a document with PAWLs data."""
        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
            pawls_parse_file=ContentFile(
                json.dumps(pawls_data).encode(), name="test.pawls"
            ),
        )
        self.corpus.add_document(document=document, user=self.user)
        return document

    def test_text_only_modality_uses_text_embedding(self):
        """TEXT only modality should return text embedding."""
        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
        )
        self.corpus.add_document(document=document, user=self.user)

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Hello world",
            content_modalities=["TEXT"],
        )

        embedder = MockEmbedder(text_embedding=[1.0, 0.0] + [0.0] * 766)
        result = generate_multimodal_embedding(annotation, embedder)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 1.0)

    def test_image_only_modality_uses_image_embedding(self):
        """IMAGE only modality should return image embedding."""
        base64_data = self._create_sample_image_base64()
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "base64_data": base64_data,
                    },
                ],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            content_modalities=["IMAGE"],
            json={"0": {"tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}]}},
        )

        embedder = MockEmbedder(image_embedding=[0.0, 1.0] + [0.0] * 766)
        result = generate_multimodal_embedding(annotation, embedder)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[1], 1.0)

    def test_mixed_modality_returns_weighted_average(self):
        """TEXT+IMAGE modality should return weighted average."""
        base64_data = self._create_sample_image_base64()
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "base64_data": base64_data,
                    },
                ],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Hello world",
            content_modalities=["TEXT", "IMAGE"],
            json={
                "0": {
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 0},
                        {"pageIndex": 0, "tokenIndex": 1},
                    ]
                }
            },
        )

        # Text: [1,0], Image: [0,1] with weights 0.3/0.7
        embedder = MockEmbedder(
            text_embedding=[1.0, 0.0] + [0.0] * 766,
            image_embedding=[0.0, 1.0] + [0.0] * 766,
        )
        result = generate_multimodal_embedding(annotation, embedder)

        self.assertIsNotNone(result)
        # Result should be between text and image, biased toward image
        self.assertGreater(result[1], result[0])

    def test_no_content_returns_none(self):
        """Annotation with no embeddable content should return None."""
        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
        )
        self.corpus.add_document(document=document, user=self.user)

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="",  # Empty text
            content_modalities=["TEXT"],
        )

        embedder = MockEmbedder()
        result = generate_multimodal_embedding(annotation, embedder)

        self.assertIsNone(result)

    def test_text_only_embedder_ignores_images(self):
        """Text-only embedder should not try to embed images."""
        base64_data = self._create_sample_image_base64()
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "base64_data": base64_data,
                    },
                ],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Hello world",
            content_modalities=["TEXT", "IMAGE"],
            json={"0": {"tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}]}},
        )

        embedder = MockTextOnlyEmbedder()
        result = generate_multimodal_embedding(annotation, embedder)

        # Should still return text embedding even though has IMAGE modality
        self.assertIsNotNone(result)

    def test_custom_weights(self):
        """Custom weights should be used."""
        base64_data = self._create_sample_image_base64()
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "base64_data": base64_data,
                    },
                ],
            }
        ]
        document = self._create_document_with_pawls(pawls_data)

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Hello world",
            content_modalities=["TEXT", "IMAGE"],
            json={
                "0": {
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 0},
                        {"pageIndex": 0, "tokenIndex": 1},
                    ]
                }
            },
        )

        embedder = MockEmbedder(
            text_embedding=[1.0, 0.0] + [0.0] * 766,
            image_embedding=[0.0, 1.0] + [0.0] * 766,
        )

        # Heavy text weight should bias toward text
        result = generate_multimodal_embedding(
            annotation, embedder, text_weight=0.9, image_weight=0.1
        )

        self.assertIsNotNone(result)
        self.assertGreater(result[0], result[1])  # More text influence

    def test_default_modalities_when_empty(self):
        """Empty content_modalities should default to TEXT."""
        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
        )
        self.corpus.add_document(document=document, user=self.user)

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Hello world",
            content_modalities=[],  # Empty list
        )

        embedder = MockEmbedder(text_embedding=[1.0, 0.0] + [0.0] * 766)
        result = generate_multimodal_embedding(annotation, embedder)

        self.assertIsNotNone(result)
