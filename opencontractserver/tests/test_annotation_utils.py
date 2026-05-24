"""
Tests for opencontractserver/annotations/utils.py.

Tests the content modality detection functions used for multimodal annotations.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.annotations.utils import (
    compute_content_modalities,
    update_annotation_modalities,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import ContentModality
from opencontractserver.users.models import User

pytestmark = pytest.mark.django_db


class TestComputeContentModalities(TestCase):
    """Tests for compute_content_modalities function."""

    def test_empty_tokens_returns_text_default(self):
        """Empty token list should return TEXT as default."""
        result = compute_content_modalities([])
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_no_document_or_pawls_data_returns_text(self):
        """No document or pawls_data provided should return TEXT default."""
        tokens = [{"pageIndex": 0, "tokenIndex": 0}]
        result = compute_content_modalities(tokens)
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_text_only_tokens_returns_text(self):
        """Tokens referencing text should return TEXT modality."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                    {"x": 200, "y": 100, "width": 50, "height": 12, "text": "World"},
                ],
            }
        ]
        tokens = [
            {"pageIndex": 0, "tokenIndex": 0},
            {"pageIndex": 0, "tokenIndex": 1},
        ]

        result = compute_content_modalities(tokens, pawls_data=pawls_data)
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_image_only_tokens_returns_image(self):
        """Tokens referencing only images should return IMAGE modality."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {
                        "x": 100,
                        "y": 100,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                    },
                ],
            }
        ]
        tokens = [{"pageIndex": 0, "tokenIndex": 0}]

        result = compute_content_modalities(tokens, pawls_data=pawls_data)
        self.assertEqual(result, [ContentModality.IMAGE.value])

    def test_mixed_tokens_returns_text_and_image(self):
        """Tokens with both text and images should return both modalities."""
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
                    },
                ],
            }
        ]
        tokens = [
            {"pageIndex": 0, "tokenIndex": 0},
            {"pageIndex": 0, "tokenIndex": 1},
        ]

        result = compute_content_modalities(tokens, pawls_data=pawls_data)
        self.assertIn(ContentModality.TEXT.value, result)
        self.assertIn(ContentModality.IMAGE.value, result)

    def test_invalid_token_refs_skipped(self):
        """Non-dict token references should be skipped."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                ],
            }
        ]
        # Mix of valid and invalid token refs
        tokens = [
            "invalid_string",
            None,
            123,
            {"pageIndex": 0, "tokenIndex": 0},
        ]

        # Deliberately pass mixed/invalid items to exercise defensive skipping.
        result = compute_content_modalities(tokens, pawls_data=pawls_data)  # type: ignore[arg-type]
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_missing_page_or_token_index_skipped(self):
        """Token refs missing pageIndex or tokenIndex should be skipped."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                ],
            }
        ]
        tokens = [
            {"pageIndex": 0},  # Missing tokenIndex
            {"tokenIndex": 0},  # Missing pageIndex
            {},  # Missing both
            {"pageIndex": 0, "tokenIndex": 0},  # Valid
        ]

        result = compute_content_modalities(tokens, pawls_data=pawls_data)
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_out_of_bounds_page_index_skipped(self):
        """Page index beyond pawls_data length should be skipped."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                ],
            }
        ]
        tokens = [
            {"pageIndex": 5, "tokenIndex": 0},  # Page doesn't exist
            {"pageIndex": -1, "tokenIndex": 0},  # Negative index
        ]

        # With no valid tokens, should default to TEXT
        result = compute_content_modalities(tokens, pawls_data=pawls_data)
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_out_of_bounds_token_index_skipped(self):
        """Token index beyond page tokens length should be skipped."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                ],
            }
        ]
        tokens = [
            {"pageIndex": 0, "tokenIndex": 10},  # Token doesn't exist
            {"pageIndex": 0, "tokenIndex": -1},  # Negative index
        ]

        result = compute_content_modalities(tokens, pawls_data=pawls_data)
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_non_dict_page_skipped(self):
        """Non-dict pages in pawls_data should be skipped."""
        pawls_data = [
            "not_a_dict",
            None,
            {
                "page": {"width": 612, "height": 792, "index": 2},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                ],
            },
        ]
        tokens = [
            {"pageIndex": 0, "tokenIndex": 0},  # Points to non-dict
            {"pageIndex": 1, "tokenIndex": 0},  # Points to None
            {"pageIndex": 2, "tokenIndex": 0},  # Valid
        ]

        # Deliberately pass a non-dict / None page to exercise defensive skipping.
        result = compute_content_modalities(tokens, pawls_data=pawls_data)  # type: ignore[arg-type]
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_non_dict_token_skipped(self):
        """Non-dict tokens in page should be skipped."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    "not_a_dict",
                    None,
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Valid"},
                ],
            }
        ]
        tokens = [
            {"pageIndex": 0, "tokenIndex": 0},  # Points to string
            {"pageIndex": 0, "tokenIndex": 1},  # Points to None
            {"pageIndex": 0, "tokenIndex": 2},  # Valid
        ]

        result = compute_content_modalities(tokens, pawls_data=pawls_data)
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_early_exit_when_both_modalities_found(self):
        """Should exit early when both text and image are found."""
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
                    },
                    # More tokens that won't be processed due to early exit
                    {"x": 100, "y": 300, "width": 50, "height": 12, "text": "Extra"},
                ],
            }
        ]
        tokens = [
            {"pageIndex": 0, "tokenIndex": 0},  # Text
            {"pageIndex": 0, "tokenIndex": 1},  # Image - should trigger early exit
            {"pageIndex": 0, "tokenIndex": 2},  # Won't be processed
        ]

        result = compute_content_modalities(tokens, pawls_data=pawls_data)
        self.assertIn(ContentModality.TEXT.value, result)
        self.assertIn(ContentModality.IMAGE.value, result)


class TestComputeContentModalitiesWithDocument(TestCase):
    """Tests for compute_content_modalities with Document loading."""

    user: User
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="test_annotation_utils_user", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=cls.user,
        )

    def test_pawls_data_loading_from_document(self):
        """Should load PAWLs data from document's pawls_parse_file."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                ],
            }
        ]

        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
            pawls_parse_file=ContentFile(
                json.dumps(pawls_data).encode(), name="test.pawls"
            ),
        )
        self.corpus.add_document(document=document, user=self.user)

        tokens = [{"pageIndex": 0, "tokenIndex": 0}]
        result = compute_content_modalities(tokens, document=document)

        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_document_without_pawls_file_returns_text(self):
        """Document without pawls_parse_file should return TEXT default."""
        document = Document.objects.create(
            title="Test Doc No Pawls",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
        )

        tokens = [{"pageIndex": 0, "tokenIndex": 0}]
        result = compute_content_modalities(tokens, document=document)

        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_pawls_data_loading_error_returns_text(self):
        """Error loading PAWLs data should return TEXT default."""
        # Create a mock document with a pawls_parse_file that raises an error
        mock_document = MagicMock()
        mock_file = MagicMock()
        mock_file.read.side_effect = IOError("Failed to read")
        mock_document.pawls_parse_file = mock_file

        # The hasattr check will be True for the mock
        with patch.object(mock_file, "read", side_effect=IOError("Read error")):
            tokens = [{"pageIndex": 0, "tokenIndex": 0}]
            result = compute_content_modalities(tokens, document=mock_document)

        self.assertEqual(result, [ContentModality.TEXT.value])


class TestUpdateAnnotationModalities(TestCase):
    """Tests for update_annotation_modalities function."""

    user: User
    corpus: Corpus
    label: AnnotationLabel

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="test_update_modalities_user", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=cls.user,
        )
        cls.label = AnnotationLabel.objects.create(
            text="Test Label",
            creator=cls.user,
        )

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

    def test_updates_annotation_modalities_field(self):
        """Should update annotation's content_modalities field."""
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
            json={
                "0": {
                    "bounds": {"left": 100, "top": 100, "right": 150, "bottom": 112},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                }
            },
        )

        result = update_annotation_modalities(annotation, pawls_data=pawls_data)

        annotation.refresh_from_db()
        self.assertEqual(result, [ContentModality.TEXT.value])
        self.assertEqual(annotation.content_modalities, [ContentModality.TEXT.value])

    def test_uses_annotation_document_if_not_provided(self):
        """Should use annotation.document if document not provided."""
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
            json={
                "0": {
                    "bounds": {"left": 100, "top": 100, "right": 150, "bottom": 112},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                }
            },
        )

        # Don't pass document - should use annotation.document
        result = update_annotation_modalities(annotation)

        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_save_false_does_not_save(self):
        """With save=False, should not save the annotation."""
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
            json={
                "0": {
                    "bounds": {"left": 100, "top": 100, "right": 150, "bottom": 112},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                }
            },
            content_modalities=[],  # Start empty
        )

        update_annotation_modalities(annotation, pawls_data=pawls_data, save=False)

        # The annotation object is updated in memory
        self.assertEqual(annotation.content_modalities, [ContentModality.TEXT.value])

        # But the database is not updated
        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, [])

    def test_extracts_tokens_from_annotation_json(self):
        """Should extract token refs from all pages in annotation json."""
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Page1"},
                ],
            },
            {
                "page": {"width": 612, "height": 792, "index": 1},
                "tokens": [
                    {
                        "x": 100,
                        "y": 100,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                    },
                ],
            },
        ]
        document = self._create_document_with_pawls(pawls_data)

        # Annotation spanning multiple pages with text and image
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json={
                "0": {
                    "bounds": {"left": 100, "top": 100, "right": 150, "bottom": 112},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                },
                "1": {
                    "bounds": {"left": 100, "top": 100, "right": 300, "bottom": 250},
                    "tokensJsons": [{"pageIndex": 1, "tokenIndex": 0}],
                },
            },
        )

        result = update_annotation_modalities(annotation, pawls_data=pawls_data)

        self.assertIn(ContentModality.TEXT.value, result)
        self.assertIn(ContentModality.IMAGE.value, result)

    def test_handles_empty_json(self):
        """Should handle annotation with empty json."""
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
            json={},  # Empty json (no pages)
        )

        result = update_annotation_modalities(annotation, pawls_data=pawls_data)

        # Empty tokens should default to TEXT
        self.assertEqual(result, [ContentModality.TEXT.value])

    def test_handles_non_dict_page_data(self):
        """Should skip non-dict page data in annotation json."""
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
            json={
                "0": "not_a_dict",  # Invalid page data
                "1": None,  # None page data
                "2": {
                    "bounds": {"left": 100, "top": 100, "right": 150, "bottom": 112},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                },
            },
        )

        result = update_annotation_modalities(annotation, pawls_data=pawls_data)

        self.assertEqual(result, [ContentModality.TEXT.value])
