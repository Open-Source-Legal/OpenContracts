"""
Tests for the LlamaParseParser class.

Tests cover:
- Successful document parsing with JSON/layout output
- Bounding box parsing and conversion
- Structural annotation creation with token-level data
- Error handling (missing API key, API errors, etc.)
- Configuration via Settings dataclass (from PipelineSettings DB)

Note: LlamaParse provides element-level bounding boxes, and the parser uses
pdfplumber to extract word-level tokens from the PDF. These tokens are then
mapped to annotations using spatial intersection (shapely STRtree).

Note: These tests mock the Settings dataclass since the actual Settings are
populated from PipelineSettings DB at runtime. Use `create_mock_llamaparse_settings()`
to create mock Settings for testing.
"""

import sys
from typing import cast
from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.parsers.llamaparse_parser import LlamaParseParser
from opencontractserver.types.dicts import BoundingBoxPythonType, TokenIdPythonType
from opencontractserver.utils.pdf_token_extraction import find_image_tokens_in_bounds

User = get_user_model()

# Create a mock llama_parse module for testing since it may not be installed
mock_llama_parse = MagicMock()
mock_llama_parse.LlamaParse = MagicMock()
sys.modules["llama_parse"] = mock_llama_parse


def create_mock_llamaparse_settings(
    api_key: str = "test-api-key-123",
    result_type: str = "json",
    extract_layout: bool = True,
    num_workers: int = 4,
    language: str = "en",
    verbose: bool = False,
    extract_images: bool = True,
    image_format: str = "jpeg",
    image_quality: int = 85,
    image_dpi: int = 150,
    min_image_width: int = 50,
    min_image_height: int = 50,
):
    """Create a mock Settings object for LlamaParseParser."""
    mock_settings = MagicMock()
    mock_settings.api_key = api_key
    mock_settings.result_type = result_type
    mock_settings.extract_layout = extract_layout
    mock_settings.num_workers = num_workers
    mock_settings.language = language
    mock_settings.verbose = verbose
    mock_settings.extract_images = extract_images
    mock_settings.image_format = image_format
    mock_settings.image_quality = image_quality
    mock_settings.image_dpi = image_dpi
    mock_settings.min_image_width = min_image_width
    mock_settings.min_image_height = min_image_height
    return mock_settings


def patch_parser_settings(parser, **settings_overrides):
    """Patch a LlamaParseParser instance with mock settings."""
    mock_settings = create_mock_llamaparse_settings(**settings_overrides)
    parser._settings = mock_settings
    # Update instance attributes from the mocked settings
    parser.api_key = mock_settings.api_key
    parser.result_type = mock_settings.result_type
    parser.extract_layout = mock_settings.extract_layout
    parser.num_workers = mock_settings.num_workers
    parser.language = mock_settings.language
    parser.verbose = mock_settings.verbose
    parser.extract_images = mock_settings.extract_images
    parser.image_format = mock_settings.image_format
    parser.image_quality = mock_settings.image_quality
    parser.image_dpi = mock_settings.image_dpi
    parser.min_image_width = mock_settings.min_image_width
    parser.min_image_height = mock_settings.min_image_height
    return parser


def create_mock_token_extraction_result(page_count=1, tokens_per_page=5):
    """
    Create mock token extraction result for testing.

    Returns a tuple matching the signature of extract_pawls_tokens_from_pdf:
    (pawls_pages, spatial_indices, tokens_by_page, token_indices_by_page,
     page_dims, content)
    """
    pawls_pages = []
    spatial_indices = {}
    tokens_by_page = {}
    token_indices_by_page = {}
    page_dims = {}

    for page_idx in range(page_count):
        # Create mock tokens for this page
        tokens = []
        for i in range(tokens_per_page):
            tokens.append(
                {
                    "x": 100 + (i * 60),
                    "y": 100,
                    "width": 50,
                    "height": 20,
                    "text": f"word{i}",
                }
            )

        pawls_pages.append(
            {
                "page": {"width": 612, "height": 792, "index": page_idx},
                "tokens": tokens,
            }
        )

        # Create mock spatial index (MagicMock since we don't need real STRtree)
        spatial_indices[page_idx] = MagicMock()
        tokens_by_page[page_idx] = tokens
        token_indices_by_page[page_idx] = np.array(
            list(range(len(tokens))), dtype=np.intp
        )
        page_dims[page_idx] = (612.0, 792.0)

    content = " ".join([f"word{i}" for i in range(tokens_per_page)])
    return (
        pawls_pages,
        spatial_indices,
        tokens_by_page,
        token_indices_by_page,
        page_dims,
        content,
    )


class MockLlamaDocument:
    """Mock LlamaIndex Document object."""

    def __init__(self, text: str):
        self.text = text


class TestLlamaParseParser(TestCase):
    """Tests for the LlamaParseParser class."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass123"
            )

        # Create a sample Document object with a mock PDF file
        self.doc = Document.objects.create(
            title="Test LlamaParse Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )

        # Create a minimal valid PDF for testing
        pdf_content = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Count 1/Kids[3 0 R]>>\nendobj\n3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"  # noqa: E501
        self.doc.pdf_file.save("test_llama.pdf", ContentFile(pdf_content))

        # Sample JSON response from LlamaParse with layout data
        # Note: LlamaParse uses 'bBox' (camelCase) with 'w'/'h' keys
        self.sample_json_response = [
            {
                "pages": [
                    {
                        "text": "This is the first page of the document.",
                        "width": 612,
                        "height": 792,
                        "items": [
                            {
                                "type": "title",
                                "text": "Document Title",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 39.6,
                                    "w": 489.6,
                                    "h": 39.6,
                                },
                            },
                            {
                                "type": "paragraph",
                                "text": "This is a paragraph with some content.",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 118.8,
                                    "w": 489.6,
                                    "h": 79.2,
                                },
                            },
                            {
                                "type": "table",
                                "text": "Column A | Column B\nValue 1 | Value 2",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 237.6,
                                    "w": 489.6,
                                    "h": 158.4,
                                },
                            },
                        ],
                        "layout": [
                            {
                                "label": "title",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 39.6,
                                    "w": 489.6,
                                    "h": 39.6,
                                },
                                "confidence": 0.95,
                                "isLikelyNoise": False,
                            },
                        ],
                    },
                    {
                        "text": "This is the second page.",
                        "width": 612,
                        "height": 792,
                        "items": [
                            {
                                "type": "text",
                                "text": "More content on page 2.",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 79.2,
                                    "w": 489.6,
                                    "h": 79.2,
                                },
                            },
                        ],
                    },
                ]
            }
        ]

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_success_with_layout(
        self, mock_open, mock_llama_parse_class, mock_extract_tokens, mock_find_tokens
    ):
        """Test successful document parsing with layout extraction and token mapping."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock the LlamaParse instance
        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = self.sample_json_response
        mock_llama_parse_class.return_value = mock_parser

        # Mock token extraction
        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=2, tokens_per_page=5
        )

        # Mock find_tokens_in_bbox to return some token references
        mock_find_tokens.return_value = [
            {"pageIndex": 0, "tokenIndex": 0},
            {"pageIndex": 0, "tokenIndex": 1},
        ]

        # Create parser with mocked settings and parse document
        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # Verify result structure
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Test LlamaParse Document")
        self.assertEqual(result["page_count"], 2)

        # Verify PAWLS content was generated with tokens
        self.assertIn("pawls_file_content", result)
        self.assertEqual(len(result["pawls_file_content"]), 2)

        # Verify first page structure - now has tokens from mock
        first_page = result["pawls_file_content"][0]
        self.assertEqual(first_page["page"]["index"], 0)
        self.assertEqual(first_page["page"]["width"], 612)
        self.assertEqual(first_page["page"]["height"], 792)
        # Tokens should now be populated from the mock
        self.assertEqual(len(first_page["tokens"]), 5)

        # Verify annotations were created
        self.assertIn("labelled_text", result)
        self.assertGreater(len(result["labelled_text"]), 0)

        # Verify annotation structure
        first_annotation = result["labelled_text"][0]
        self.assertEqual(first_annotation["annotationLabel"], "Title")
        self.assertEqual(first_annotation["structural"], True)
        self.assertEqual(first_annotation["annotation_type"], "TOKEN_LABEL")
        self.assertIn("annotation_json", first_annotation)

        # Verify annotation has token references (from mock)
        page_anno = first_annotation["annotation_json"]["0"]
        self.assertEqual(len(page_anno["tokensJsons"]), 2)
        self.assertEqual(page_anno["tokensJsons"][0], {"pageIndex": 0, "tokenIndex": 0})

    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_markdown_mode(self, mock_open, mock_llama_parse_class):
        """Test document parsing with markdown output (no layout)."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock the LlamaParse instance for markdown mode
        mock_parser = MagicMock()
        mock_parser.load_data.return_value = [
            MockLlamaDocument("# Title\n\nThis is the document content."),
            MockLlamaDocument("## Section 2\n\nMore content here."),
        ]
        mock_llama_parse_class.return_value = mock_parser

        # Create parser with mocked settings and parse document with markdown mode
        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            result_type="markdown",
            extract_layout=False,
        )

        # Verify result structure
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Test LlamaParse Document")
        self.assertIn("# Title", result["content"])
        self.assertEqual(result["page_count"], 2)

        # Verify no PAWLS content (markdown mode)
        self.assertEqual(result["pawls_file_content"], [])

        # Verify no annotations (markdown mode without layout)
        self.assertEqual(result["labelled_text"], [])

    def test_parse_document_no_api_key(self):
        """Test that parsing fails gracefully without API key."""
        # Create parser with mocked Settings (simulating PipelineSettings DB)
        # that has empty API key
        parser = patch_parser_settings(LlamaParseParser(), api_key="")

        result = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertIsNone(result)

    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_api_error(self, mock_open, mock_llama_parse_class):
        """Test handling of API errors."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock the LlamaParse instance to raise an error
        mock_parser = MagicMock()
        mock_parser.get_json_result.side_effect = Exception("API rate limit exceeded")
        mock_llama_parse_class.return_value = mock_parser

        # Create parser with mocked settings and attempt to parse
        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # Should return None on error
        self.assertIsNone(result)

    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_empty_result(self, mock_open, mock_llama_parse_class):
        """Test handling of empty results from API."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock empty response
        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = []
        mock_llama_parse_class.return_value = mock_parser

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertIsNone(result)

    def test_parse_document_nonexistent(self):
        """Test parsing a document that doesn't exist."""
        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(user_id=self.user.id, doc_id=999999)

        self.assertIsNone(result)

    def test_parse_document_no_pdf_file(self):
        """Test parsing a document without a PDF file."""
        # Create a document without a PDF file
        doc_without_pdf = Document.objects.create(
            title="No PDF Document",
            description="Test",
            file_type="pdf",
            creator=self.user,
        )

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(user_id=self.user.id, doc_id=doc_without_pdf.id)

        self.assertIsNone(result)


class TestLlamaParseParserBboxConversion(TestCase):
    """Tests for bounding box conversion methods.

    Note: LlamaParse only provides element-level bounding boxes, not token-level data.
    The _create_pawls_tokens_from_bbox method returns empty tokens list and just the bounds.
    """

    def setUp(self):
        """Set up test environment."""
        self.parser = LlamaParseParser()

    def test_bbox_fractional_xy_format(self):
        """Test conversion of fractional x,y,width,height bbox format."""
        bbox = {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}
        tokens, bounds = self.parser._create_pawls_tokens_from_bbox(
            text="test word",
            bbox=bbox,
            page_width=612,
            page_height=792,
            start_token_idx=0,
        )

        # Check bounds are converted to absolute coordinates
        self.assertAlmostEqual(bounds["left"], 61.2, places=1)
        self.assertAlmostEqual(bounds["top"], 158.4, places=1)
        self.assertAlmostEqual(bounds["right"], 244.8, places=1)
        self.assertAlmostEqual(bounds["bottom"], 237.6, places=1)

        # Tokens list is empty - we don't generate fake tokens
        self.assertEqual(len(tokens), 0)

    def test_bbox_llamaparse_format(self):
        """Test conversion of LlamaParse's actual format: bBox with x/y/w/h."""
        # This is the actual format LlamaParse uses (absolute coordinates)
        bbox = {"x": 72.1, "y": 35.4, "w": 467.35, "h": 151}
        tokens, bounds = self.parser._create_pawls_tokens_from_bbox(
            text="LlamaParse format test",
            bbox=bbox,
            page_width=612,
            page_height=792,
            start_token_idx=0,
        )

        # Should be treated as absolute coordinates since values > 1
        self.assertAlmostEqual(bounds["left"], 72.1, places=1)
        self.assertAlmostEqual(bounds["top"], 35.4, places=1)
        self.assertAlmostEqual(bounds["right"], 539.45, places=1)  # x + w
        self.assertAlmostEqual(bounds["bottom"], 186.4, places=1)  # y + h

        # No tokens
        self.assertEqual(len(tokens), 0)

    def test_bbox_fractional_ltrb_format(self):
        """Test conversion of fractional left,top,right,bottom bbox format."""
        bbox = {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.3}
        tokens, bounds = self.parser._create_pawls_tokens_from_bbox(
            text="hello world",
            bbox=bbox,
            page_width=612,
            page_height=792,
            start_token_idx=0,
        )

        self.assertAlmostEqual(bounds["left"], 61.2, places=1)
        self.assertAlmostEqual(bounds["top"], 158.4, places=1)
        self.assertAlmostEqual(bounds["right"], 550.8, places=1)
        self.assertAlmostEqual(bounds["bottom"], 237.6, places=1)

        # No tokens
        self.assertEqual(len(tokens), 0)

    def test_bbox_array_format(self):
        """Test conversion of array bbox format [x1, y1, x2, y2]."""
        bbox = [0.1, 0.2, 0.9, 0.3]
        tokens, bounds = self.parser._create_pawls_tokens_from_bbox(
            text="array format test",
            # array format: the parser also accepts list bbox at runtime
            bbox=bbox,  # type: ignore[arg-type]
            page_width=612,
            page_height=792,
            start_token_idx=0,
        )

        self.assertAlmostEqual(bounds["left"], 61.2, places=1)
        self.assertAlmostEqual(bounds["top"], 158.4, places=1)
        self.assertAlmostEqual(bounds["right"], 550.8, places=1)
        self.assertAlmostEqual(bounds["bottom"], 237.6, places=1)

        # No tokens
        self.assertEqual(len(tokens), 0)

    def test_bbox_absolute_coordinates(self):
        """Test handling of absolute coordinate bbox (values > 1)."""
        bbox = {"x": 100, "y": 200, "width": 300, "height": 50}
        tokens, bounds = self.parser._create_pawls_tokens_from_bbox(
            text="absolute coords",
            bbox=bbox,
            page_width=612,
            page_height=792,
            start_token_idx=0,
        )

        # When values > 1, they're treated as absolute
        self.assertEqual(bounds["left"], 100)
        self.assertEqual(bounds["top"], 200)
        self.assertEqual(bounds["right"], 400)  # x + width
        self.assertEqual(bounds["bottom"], 250)  # y + height

        # No tokens
        self.assertEqual(len(tokens), 0)

    def test_bbox_empty(self):
        """Test handling of empty/missing bbox."""
        tokens, bounds = self.parser._create_pawls_tokens_from_bbox(
            text="no bbox",
            bbox={},
            page_width=612,
            page_height=792,
            start_token_idx=0,
        )

        # Should use default margins
        self.assertEqual(bounds["left"], 72)
        self.assertEqual(bounds["top"], 72)

        # No tokens
        self.assertEqual(len(tokens), 0)

    def test_bbox_x1_y1_x2_y2_format(self):
        """Test conversion of x1/y1/x2/y2 corner coordinate format."""
        bbox = {"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.3}
        tokens, bounds = self.parser._create_pawls_tokens_from_bbox(
            text="corner format test",
            bbox=bbox,
            page_width=612,
            page_height=792,
            start_token_idx=0,
        )

        self.assertAlmostEqual(bounds["left"], 61.2, places=1)
        self.assertAlmostEqual(bounds["top"], 158.4, places=1)
        self.assertAlmostEqual(bounds["right"], 550.8, places=1)
        self.assertAlmostEqual(bounds["bottom"], 237.6, places=1)

        # No tokens
        self.assertEqual(len(tokens), 0)

    def test_bbox_sanity_checks(self):
        """Test that sanity checks are applied to bounding boxes."""
        # Test bounds are clamped to page
        bbox = {"x": -10, "y": -10, "w": 1000, "h": 1000}
        tokens, bounds = self.parser._create_pawls_tokens_from_bbox(
            text="out of bounds",
            bbox=bbox,
            page_width=612,
            page_height=792,
            start_token_idx=0,
        )

        # Should be clamped to page bounds
        self.assertGreaterEqual(bounds["left"], 0)
        self.assertGreaterEqual(bounds["top"], 0)
        self.assertLessEqual(bounds["right"], 612)
        self.assertLessEqual(bounds["bottom"], 792)


class TestLlamaParseParserAnnotations(TestCase):
    """Tests for annotation creation methods.

    Annotations can now include tokensJsons when token extraction succeeds.
    """

    def setUp(self):
        """Set up test environment."""
        self.parser = LlamaParseParser()

    def test_create_annotation_structure_without_tokens(self):
        """Test annotation creation has correct structure without token refs."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 300,
            "bottom": 150,
        }

        annotation = self.parser._create_annotation(
            annotation_id="anno-1",
            label="Title",
            raw_text="Sample Title",
            page_idx=0,
            bounds=bounds,
        )

        # Check required fields
        self.assertEqual(annotation["id"], "anno-1")
        self.assertEqual(annotation["annotationLabel"], "Title")
        self.assertEqual(annotation["rawText"], "Sample Title")
        self.assertEqual(annotation["page"], 0)
        self.assertEqual(annotation["structural"], True)
        self.assertEqual(annotation["annotation_type"], "TOKEN_LABEL")
        self.assertIsNone(annotation["parent_id"])

        # Check annotation_json structure
        self.assertIn("0", annotation["annotation_json"])
        page_anno = cast(dict, annotation["annotation_json"])["0"]
        self.assertEqual(page_anno["bounds"], bounds)
        self.assertEqual(page_anno["rawText"], "Sample Title")
        # tokensJsons is empty when no token_refs provided
        self.assertEqual(len(page_anno["tokensJsons"]), 0)

    def test_create_annotation_structure_with_tokens(self):
        """Test annotation creation with token references."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 300,
            "bottom": 150,
        }
        token_refs: list[TokenIdPythonType] = [
            {"pageIndex": 0, "tokenIndex": 0},
            {"pageIndex": 0, "tokenIndex": 1},
            {"pageIndex": 0, "tokenIndex": 2},
        ]

        annotation = self.parser._create_annotation(
            annotation_id="anno-2",
            label="Paragraph",
            raw_text="Sample paragraph text",
            page_idx=0,
            bounds=bounds,
            token_refs=token_refs,
        )

        # Check annotation_json structure includes tokens
        page_anno = cast(dict, annotation["annotation_json"])["0"]
        self.assertEqual(len(page_anno["tokensJsons"]), 3)
        self.assertEqual(page_anno["tokensJsons"][0], {"pageIndex": 0, "tokenIndex": 0})
        self.assertEqual(page_anno["tokensJsons"][2], {"pageIndex": 0, "tokenIndex": 2})

    def test_element_type_mapping(self):
        """Test that element types are properly mapped to labels."""
        type_mappings = {
            "title": "Title",
            "paragraph": "Paragraph",
            "table": "Table",
            "figure": "Figure",
            "list": "List",
            "heading": "Heading",
            "unknown_type": "Text Block",  # Default
        }

        for element_type, expected_label in type_mappings.items():
            label = LlamaParseParser.ELEMENT_TYPE_MAPPING.get(
                element_type, "Text Block"
            )
            self.assertEqual(
                label,
                expected_label,
                f"Element type '{element_type}' should map to '{expected_label}'",
            )


class TestLlamaParseParserConfiguration(TestCase):
    """Tests for parser configuration."""

    def test_default_configuration(self):
        """Test default configuration values from mocked Settings dataclass."""
        # Create parser with explicit mock Settings (simulating PipelineSettings DB)
        # This tests that the parser correctly reads from Settings dataclass
        parser = patch_parser_settings(
            LlamaParseParser(),
            api_key="test-key",
            result_type="json",
            extract_layout=True,
            num_workers=4,
            language="en",
            verbose=False,
        )

        self.assertEqual(parser.result_type, "json")
        self.assertEqual(parser.extract_layout, True)
        self.assertEqual(parser.num_workers, 4)
        self.assertEqual(parser.language, "en")
        self.assertEqual(parser.verbose, False)

    def test_custom_configuration(self):
        """Test custom configuration via Settings dataclass (PipelineSettings DB)."""
        # Create parser with custom mocked settings (simulating PipelineSettings DB)
        parser = patch_parser_settings(
            LlamaParseParser(),
            api_key="custom-key",
            result_type="markdown",
            extract_layout=False,
            num_workers=8,
            language="de",
            verbose=True,
        )

        self.assertEqual(parser.result_type, "markdown")
        self.assertEqual(parser.extract_layout, False)
        self.assertEqual(parser.num_workers, 8)
        self.assertEqual(parser.language, "de")
        self.assertEqual(parser.verbose, True)

    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_kwargs_override_settings(self, mock_open, mock_llama_parse_class):
        """Test that kwargs override Settings dataclass values."""
        with transaction.atomic():
            user = User.objects.create_user(
                username="configtestuser", password="pass123"
            )

        doc = Document.objects.create(
            title="Config Test Doc",
            file_type="pdf",
            creator=user,
        )
        doc.pdf_file.save("config_test.pdf", ContentFile(b"%PDF-1.4 test"))

        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = [{"pages": []}]
        mock_llama_parse_class.return_value = mock_parser

        # Create parser with default settings
        parser = patch_parser_settings(LlamaParseParser())
        # Parse with kwarg overrides
        parser.parse_document(
            user_id=user.id,
            doc_id=doc.id,
            language="fr",
            num_workers=16,
        )

        # Verify LlamaParse was called with overridden values
        mock_llama_parse_class.assert_called_once()
        call_kwargs = mock_llama_parse_class.call_args.kwargs
        self.assertEqual(call_kwargs["language"], "fr")
        self.assertEqual(call_kwargs["num_workers"], 16)


class TestLlamaParseParserLayoutOnlyProcessing(TestCase):
    """Tests for layout-only processing (when items are empty but layout exists)."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="layouttestuser", password="testpass123"
            )

        self.doc = Document.objects.create(
            title="Layout Test Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )

        pdf_content = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Count 1/Kids[3 0 R]>>\nendobj\n3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"  # noqa: E501
        self.doc.pdf_file.save("test_layout.pdf", ContentFile(pdf_content))

        # JSON response with layout elements but no items
        # Uses actual LlamaParse format with bBox and w/h
        self.layout_only_response = [
            {
                "pages": [
                    {
                        "text": "Layout only page content.",
                        "width": 612,
                        "height": 792,
                        "items": [],  # Empty items list
                        "layout": [
                            {
                                "label": "title",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 39.6,
                                    "w": 489.6,
                                    "h": 39.6,
                                },
                                "text": "Document Title from Layout",
                            },
                            {
                                "label": "paragraph",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 158.4,
                                    "w": 489.6,
                                    "h": 79.2,
                                },
                                "text": "Paragraph content from layout element.",
                            },
                            {
                                "label": "figure",
                                "bBox": {
                                    "x": 122.4,
                                    "y": 316.8,
                                    "w": 367.2,
                                    "h": 237.6,
                                },
                                "text": "",  # Empty text for figure - should use [figure]
                            },
                            {
                                "label": "text",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 594.0,
                                    "w": 489.6,
                                    "h": 39.6,
                                },
                                "text": "",  # Empty text for non-figure - should be skipped
                            },
                        ],
                    }
                ]
            }
        ]

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_layout_only_processing(
        self, mock_open, mock_llama_parse_class, mock_extract_tokens, mock_find_tokens
    ):
        """Test document parsing when items are empty but layout exists.

        This tests the layout-only processing path in _convert_json_to_opencontracts.
        """
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = self.layout_only_response
        mock_llama_parse_class.return_value = mock_parser

        # Mock token extraction
        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=5
        )
        mock_find_tokens.return_value = [{"pageIndex": 0, "tokenIndex": 0}]

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # Verify result structure
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Layout Test Document")
        self.assertEqual(result["page_count"], 1)

        # Verify PAWLS content structure (now has tokens from extraction)
        self.assertIn("pawls_file_content", result)
        self.assertEqual(len(result["pawls_file_content"]), 1)
        first_page = result["pawls_file_content"][0]
        # Tokens should now be populated from the mock
        self.assertEqual(len(first_page["tokens"]), 5)

        # Verify annotations were created from layout elements
        self.assertIn("labelled_text", result)
        # Should have 3 annotations: title, paragraph, and figure
        # The empty text "text" type should be skipped
        self.assertEqual(len(result["labelled_text"]), 3)

        # Check the annotation labels
        labels = [anno["annotationLabel"] for anno in result["labelled_text"]]
        self.assertIn("Title", labels)
        self.assertIn("Paragraph", labels)
        self.assertIn("Figure", labels)

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_layout_figure_without_text(
        self, mock_open, mock_llama_parse_class, mock_extract_tokens, mock_find_tokens
    ):
        """Test that figures/images with empty text are processed correctly.

        Figures and images should use [element_type] as placeholder text.
        """
        layout_with_images = [
            {
                "pages": [
                    {
                        "text": "Page with figures",
                        "width": 612,
                        "height": 792,
                        "items": [],
                        "layout": [
                            {
                                "label": "image",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 79.2,
                                    "w": 489.6,
                                    "h": 316.8,
                                },
                                "text": "",  # Empty text - should use [image]
                            },
                            {
                                "label": "figure",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 475.2,
                                    "w": 489.6,
                                    "h": 237.6,
                                },
                                "text": "",  # Empty text - should use [figure]
                            },
                        ],
                    }
                ]
            }
        ]

        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = layout_with_images
        mock_llama_parse_class.return_value = mock_parser

        # Mock token extraction
        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=5
        )
        mock_find_tokens.return_value = []

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # Both figure and image should be processed
        self.assertIsNotNone(result)
        self.assertEqual(len(result["labelled_text"]), 2)

        # Check that placeholder text was used
        for anno in result["labelled_text"]:
            self.assertIn(anno["rawText"], ["[image]", "[figure]"])

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_layout_skips_empty_text_non_figures(
        self, mock_open, mock_llama_parse_class, mock_extract_tokens, mock_find_tokens
    ):
        """Test that non-figure elements with empty text are skipped."""
        layout_with_empty_text = [
            {
                "pages": [
                    {
                        "text": "Page content",
                        "width": 612,
                        "height": 792,
                        "items": [],
                        "layout": [
                            {
                                "label": "title",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 79.2,
                                    "w": 489.6,
                                    "h": 39.6,
                                },
                                "text": "Valid Title",  # Has text - should be included
                            },
                            {
                                "label": "paragraph",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 158.4,
                                    "w": 489.6,
                                    "h": 79.2,
                                },
                                "text": "",  # Empty text - should be skipped
                            },
                            {
                                "label": "heading",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 316.8,
                                    "w": 489.6,
                                    "h": 39.6,
                                },
                                "text": "",  # Empty text - should be skipped
                            },
                            {
                                "label": "section_header",
                                "bBox": {
                                    "x": 61.2,
                                    "y": 396.0,
                                    "w": 489.6,
                                    "h": 39.6,
                                },
                                "text": "Valid Section Header",  # Has text - should be included
                            },
                        ],
                    }
                ]
            }
        ]

        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = layout_with_empty_text
        mock_llama_parse_class.return_value = mock_parser

        # Mock token extraction
        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=5
        )
        mock_find_tokens.return_value = []

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # Only 2 annotations should be created (title and section_header)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["labelled_text"]), 2)

        labels = [anno["annotationLabel"] for anno in result["labelled_text"]]
        self.assertIn("Title", labels)
        self.assertIn("Section Header", labels)
        self.assertNotIn("Paragraph", labels)
        self.assertNotIn("Heading", labels)


class TestLlamaParseParserImageExtraction(TestCase):
    """Tests for image extraction and multimodal annotation features."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="imagetestuser", password="testpass123"
            )

        self.doc = Document.objects.create(
            title="Image Test Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )

        pdf_content = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Count 1/Kids[3 0 R]>>\nendobj\n3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"  # noqa: E501
        self.doc.pdf_file.save("test_image.pdf", ContentFile(pdf_content))

        self.parser = LlamaParseParser()

    def test_find_images_in_bounds_overlapping(self):
        """Test that find_image_tokens_in_bounds finds overlapping images."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 300,
            "bottom": 300,
        }

        # Image that overlaps with the bounds
        page_images: list = [
            {"x": 150, "y": 150, "width": 100, "height": 100},  # Overlaps
            {"x": 400, "y": 400, "width": 50, "height": 50},  # No overlap
        ]

        result = find_image_tokens_in_bounds(
            bounds=bounds,
            page_idx=0,
            image_tokens=page_images,
            token_offset=10,  # Images start at token index 10
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pageIndex"], 0)
        self.assertEqual(result[0]["tokenIndex"], 10)  # First image at offset 10

    def test_find_images_in_bounds_no_overlap(self):
        """Test that find_image_tokens_in_bounds returns empty when no overlap."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 200,
            "bottom": 200,
        }

        page_images: list = [
            {"x": 300, "y": 300, "width": 50, "height": 50},  # No overlap
            {"x": 400, "y": 400, "width": 50, "height": 50},  # No overlap
        ]

        result = find_image_tokens_in_bounds(
            bounds=bounds,
            page_idx=0,
            image_tokens=page_images,
            token_offset=5,
        )

        self.assertEqual(len(result), 0)

    def test_find_images_in_bounds_empty_images(self):
        """Test that find_image_tokens_in_bounds handles empty image list."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 200,
            "bottom": 200,
        }

        result = find_image_tokens_in_bounds(
            bounds=bounds,
            page_idx=0,
            image_tokens=[],
            token_offset=0,
        )

        self.assertEqual(result, [])

    def test_find_images_in_bounds_multiple_overlaps(self):
        """Test that find_image_tokens_in_bounds finds all overlapping images."""
        bounds: BoundingBoxPythonType = {
            "left": 50,
            "top": 50,
            "right": 400,
            "bottom": 400,
        }

        page_images: list = [
            {"x": 100, "y": 100, "width": 100, "height": 100},  # Overlaps
            {"x": 250, "y": 250, "width": 100, "height": 100},  # Overlaps
            {"x": 500, "y": 500, "width": 50, "height": 50},  # No overlap
        ]

        result = find_image_tokens_in_bounds(
            bounds=bounds,
            page_idx=1,
            image_tokens=page_images,
            token_offset=20,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["pageIndex"], 1)
        self.assertEqual(result[0]["tokenIndex"], 20)
        self.assertEqual(result[1]["tokenIndex"], 21)

    def test_create_annotation_with_image_tokens(self):
        """Test annotation creation with image token references."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 300,
            "bottom": 300,
        }
        token_refs: list[TokenIdPythonType] = [
            {"pageIndex": 0, "tokenIndex": 5},  # Image token
        ]

        annotation = self.parser._create_annotation(
            annotation_id="figure-1",
            label="Figure",
            raw_text="[figure]",
            page_idx=0,
            bounds=bounds,
            token_refs=token_refs,
            has_text_tokens=False,
            has_image_tokens=True,
        )

        # Should have IMAGE in content_modalities
        self.assertIn("content_modalities", annotation)
        self.assertIn("IMAGE", annotation["content_modalities"])
        self.assertNotIn("TEXT", annotation["content_modalities"])

    def test_create_annotation_with_text_and_image_tokens(self):
        """Test annotation creation with both text and image tokens."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 300,
            "bottom": 300,
        }
        token_refs: list[TokenIdPythonType] = [
            {"pageIndex": 0, "tokenIndex": 0},  # Text token
            {"pageIndex": 0, "tokenIndex": 1},  # Text token
            {"pageIndex": 0, "tokenIndex": 10},  # Image token
        ]

        annotation = self.parser._create_annotation(
            annotation_id="mixed-1",
            label="Figure",
            raw_text="Figure with caption",
            page_idx=0,
            bounds=bounds,
            token_refs=token_refs,
            has_text_tokens=True,
            has_image_tokens=True,
        )

        # Should have both TEXT and IMAGE in content_modalities
        self.assertIn("content_modalities", annotation)
        self.assertIn("TEXT", annotation["content_modalities"])
        self.assertIn("IMAGE", annotation["content_modalities"])

    def test_create_annotation_without_modalities(self):
        """Test annotation creation without modalities flag."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 300,
            "bottom": 150,
        }

        annotation = self.parser._create_annotation(
            annotation_id="text-1",
            label="Paragraph",
            raw_text="Just text",
            page_idx=0,
            bounds=bounds,
            token_refs=[],
            has_text_tokens=False,
            has_image_tokens=False,
        )

        # Should not have content_modalities when neither flag is set
        self.assertNotIn("content_modalities", annotation)

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.crop_image_from_pdf")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_with_image_extraction(
        self,
        mock_open,
        mock_llama_parse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
        mock_crop_image,
    ):
        """Test document parsing with image extraction enabled."""
        # Mock file reading
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # JSON response with a figure element
        json_response = [
            {
                "pages": [
                    {
                        "text": "Page with figure",
                        "width": 612,
                        "height": 792,
                        "items": [
                            {
                                "type": "figure",
                                "text": "Figure 1: Test Chart",
                                "bBox": {"x": 100, "y": 200, "w": 400, "h": 300},
                            },
                        ],
                    }
                ]
            }
        ]

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = json_response
        mock_llama_parse_class.return_value = mock_parser

        # Mock token extraction
        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=3
        )
        mock_find_tokens.return_value = []

        # Mock image extraction - return an image on page 0
        mock_extract_images.return_value = {
            0: [
                {
                    "x": 120,
                    "y": 220,
                    "width": 360,
                    "height": 260,
                    "format": "jpeg",
                    "image_path": "documents/1/images/page_0_img_0.jpg",
                    "content_hash": "abc123",
                }
            ]
        }

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            extract_images=True,
        )

        # Verify result
        self.assertIsNotNone(result)

        # Verify image extraction was called
        mock_extract_images.assert_called_once()

        # Verify the figure annotation was created
        self.assertGreater(len(result["labelled_text"]), 0)
        figure_anno = next(
            (a for a in result["labelled_text"] if a["annotationLabel"] == "Figure"),
            None,
        )
        self.assertIsNotNone(figure_anno)

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.crop_image_from_pdf")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_crops_figure_when_no_embedded_image(
        self,
        mock_open,
        mock_llama_parse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
        mock_crop_image,
    ):
        """Test that figures without embedded images trigger cropping."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        json_response = [
            {
                "pages": [
                    {
                        "text": "Page with figure",
                        "width": 612,
                        "height": 792,
                        "items": [
                            {
                                "type": "figure",
                                "text": "",  # Empty text for figure
                                "bBox": {"x": 100, "y": 200, "w": 400, "h": 300},
                            },
                        ],
                    }
                ]
            }
        ]

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = json_response
        mock_llama_parse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=3
        )
        mock_find_tokens.return_value = []

        # No embedded images found
        mock_extract_images.return_value = {}

        # Mock crop_image_from_pdf to return a cropped image
        mock_crop_image.return_value = {
            "x": 100,
            "y": 200,
            "width": 400,
            "height": 300,
            "text": "",
            "is_image": True,
            "format": "jpeg",
            "image_path": "documents/1/images/page_0_img_0.jpg",
            "content_hash": "cropped123",
            "original_width": 800,
            "original_height": 600,
            "image_type": "cropped",
        }

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            extract_images=True,
        )

        # Verify crop_image_from_pdf was called
        mock_crop_image.assert_called()

        # Verify result has the figure annotation with image modality
        self.assertIsNotNone(result)
        figure_annos = [
            a for a in result["labelled_text"] if a["annotationLabel"] == "Figure"
        ]
        self.assertEqual(len(figure_annos), 1)

        # The annotation should have IMAGE modality
        self.assertIn("content_modalities", figure_annos[0])
        self.assertIn("IMAGE", figure_annos[0]["content_modalities"])

    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_image_extraction_failure_graceful(
        self,
        mock_open,
        mock_llama_parse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
    ):
        """Test that image extraction failures are handled gracefully."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        json_response = [
            {
                "pages": [
                    {
                        "text": "Page content",
                        "width": 612,
                        "height": 792,
                        "items": [
                            {
                                "type": "paragraph",
                                "text": "Some text",
                                "bBox": {"x": 100, "y": 100, "w": 400, "h": 50},
                            },
                        ],
                    }
                ]
            }
        ]

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = json_response
        mock_llama_parse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=3
        )
        mock_find_tokens.return_value = []

        # Image extraction raises an exception
        mock_extract_images.side_effect = Exception("Image extraction failed")

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            extract_images=True,
        )

        # Should still succeed, just without images
        self.assertIsNotNone(result)
        self.assertEqual(len(result["labelled_text"]), 1)


class TestLlamaParseParserPageLevelImages(TestCase):
    """Tests for LlamaParse page-level image processing (page['images'] array)."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="pagelevelimguser", password="testpass123"
            )

        self.doc = Document.objects.create(
            title="Page Level Image Test Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )

        pdf_content = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Count 1/Kids[3 0 R]>>\nendobj\n3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"  # noqa: E501
        self.doc.pdf_file.save("test_page_images.pdf", ContentFile(pdf_content))

        self.parser = patch_parser_settings(LlamaParseParser())

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.crop_image_from_pdf")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_with_page_level_images(
        self,
        mock_open,
        mock_llama_parse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
        mock_crop_image,
    ):
        """Test that page-level images from LlamaParse are processed correctly.

        LlamaParse provides images in page["images"] array, separate from items.
        This tests that these images are detected and annotations created.
        """
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # JSON response with page-level images (actual LlamaParse format)
        json_response = [
            {
                "pages": [
                    {
                        "text": "Page with header image",
                        "width": 612,
                        "height": 792,
                        "items": [
                            {
                                "type": "heading",
                                "text": "Document Title",
                                "bBox": {"x": 100, "y": 100, "w": 400, "h": 30},
                            },
                        ],
                        # LlamaParse page-level images array
                        "images": [
                            {
                                "name": "img_p0_1.jpg",
                                "x": 40.3,
                                "y": 27.2,
                                "width": 282.4,
                                "height": 72,
                                "original_width": 863,
                                "original_height": 220,
                                "rotation": 0,
                                "ocr": [
                                    {"text": "STATE OF NEW YORK", "x": 150, "y": 41},
                                    {
                                        "text": "Division of Corporations",
                                        "x": 359,
                                        "y": 35,
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        ]

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = json_response
        mock_llama_parse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=3
        )
        mock_find_tokens.return_value = []

        # No embedded images found
        mock_extract_images.return_value = {}

        # Mock crop to return image data
        mock_crop_image.return_value = {
            "x": 40.3,
            "y": 27.2,
            "width": 282.4,
            "height": 72,
            "format": "jpeg",
            "image_path": "documents/1/images/page_0_img_0.jpg",
            "content_hash": "abc123",
            "original_width": 282,
            "original_height": 72,
            "image_type": "cropped",
        }

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            extract_images=True,
        )

        self.assertIsNotNone(result)

        # Should have annotation for the LlamaParse-detected image
        image_annos = [
            a for a in result["labelled_text"] if a["annotationLabel"] == "Image"
        ]
        self.assertEqual(len(image_annos), 1)

        # Image annotation should have IMAGE modality
        self.assertIn("content_modalities", image_annos[0])
        self.assertIn("IMAGE", image_annos[0]["content_modalities"])

        # Should contain OCR text from LlamaParse
        self.assertIn("STATE OF NEW YORK", image_annos[0]["rawText"])
        self.assertIn("Division of Corporations", image_annos[0]["rawText"])

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.crop_image_from_pdf")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_page_level_images_uses_existing_embedded(
        self,
        mock_open,
        mock_llama_parse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
        mock_crop_image,
    ):
        """Test that page-level images reuse existing embedded images when available."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        json_response = [
            {
                "pages": [
                    {
                        "text": "Page with image",
                        "width": 612,
                        "height": 792,
                        "items": [],
                        "images": [
                            {
                                "name": "img_p0_1.jpg",
                                "x": 100,
                                "y": 100,
                                "width": 200,
                                "height": 150,
                                "ocr": [],
                            }
                        ],
                    }
                ]
            }
        ]

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = json_response
        mock_llama_parse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=3
        )
        mock_find_tokens.return_value = []

        # Embedded image found at same location
        mock_extract_images.return_value = {
            0: [
                {
                    "x": 110,
                    "y": 110,
                    "width": 180,
                    "height": 130,
                    "format": "jpeg",
                    "image_path": "documents/1/images/embedded_0.jpg",
                }
            ]
        }

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            extract_images=True,
        )

        self.assertIsNotNone(result)

        # crop_image should NOT be called since embedded image was found
        mock_crop_image.assert_not_called()

        # Should still have the image annotation
        image_annos = [
            a for a in result["labelled_text"] if a["annotationLabel"] == "Image"
        ]
        self.assertEqual(len(image_annos), 1)

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.crop_image_from_pdf")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_page_level_images_skips_small(
        self,
        mock_open,
        mock_llama_parse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
        mock_crop_image,
    ):
        """Test that small page-level images are skipped."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        json_response = [
            {
                "pages": [
                    {
                        "text": "Page with tiny image",
                        "width": 612,
                        "height": 792,
                        "items": [],
                        "images": [
                            {
                                "name": "tiny_img.jpg",
                                "x": 100,
                                "y": 100,
                                "width": 20,  # Too small (< min_image_width of 50)
                                "height": 20,  # Too small (< min_image_height of 50)
                                "ocr": [],
                            }
                        ],
                    }
                ]
            }
        ]

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = json_response
        mock_llama_parse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=3
        )
        mock_find_tokens.return_value = []
        mock_extract_images.return_value = {}

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            extract_images=True,
        )

        self.assertIsNotNone(result)

        # No image annotations should be created (image too small)
        image_annos = [
            a for a in result["labelled_text"] if a["annotationLabel"] == "Image"
        ]
        self.assertEqual(len(image_annos), 0)

        # crop_image should not be called for small images
        mock_crop_image.assert_not_called()

    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.crop_image_from_pdf")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.llamaparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("llama_parse.LlamaParse")
    @patch("opencontractserver.pipeline.parsers.llamaparse_parser.default_storage.open")
    def test_parse_document_page_level_images_fallback_text(
        self,
        mock_open,
        mock_llama_parse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
        mock_crop_image,
    ):
        """Test that images without OCR text use [Image] fallback."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        json_response = [
            {
                "pages": [
                    {
                        "text": "Page with image",
                        "width": 612,
                        "height": 792,
                        "items": [],
                        "images": [
                            {
                                "name": "img_no_ocr.jpg",
                                "x": 100,
                                "y": 100,
                                "width": 200,
                                "height": 150,
                                # No ocr key - should use fallback
                            }
                        ],
                    }
                ]
            }
        ]

        mock_parser = MagicMock()
        mock_parser.get_json_result.return_value = json_response
        mock_llama_parse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=3
        )
        mock_find_tokens.return_value = []
        mock_extract_images.return_value = {}

        mock_crop_image.return_value = {
            "x": 100,
            "y": 100,
            "width": 200,
            "height": 150,
            "format": "jpeg",
            "image_path": "documents/1/images/page_0_img_0.jpg",
        }

        parser = patch_parser_settings(LlamaParseParser())
        result = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            extract_images=True,
        )

        self.assertIsNotNone(result)

        image_annos = [
            a for a in result["labelled_text"] if a["annotationLabel"] == "Image"
        ]
        self.assertEqual(len(image_annos), 1)

        # Should use [Image] fallback text
        self.assertEqual(image_annos[0]["rawText"], "[Image]")


class TestLlamaParseParserTextConversion(TestCase):
    """Tests for text/markdown conversion path."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="texttestuser", password="testpass123"
            )

        self.doc = Document.objects.create(
            title="Text Test Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )

        pdf_content = (
            b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n%%EOF\n"
        )
        self.doc.pdf_file.save("test_text.pdf", ContentFile(pdf_content))

    def test_convert_text_to_opencontracts(self):
        """Test _convert_text_to_opencontracts method."""
        parser = LlamaParseParser()

        # Create mock LlamaIndex documents
        mock_docs = [
            MockLlamaDocument("First page content"),
            MockLlamaDocument("Second page content"),
        ]

        result = parser._convert_text_to_opencontracts(self.doc, mock_docs)

        self.assertEqual(result["title"], "Text Test Document")
        self.assertEqual(result["content"], "First page content\n\nSecond page content")
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["pawls_file_content"], [])
        self.assertEqual(result["labelled_text"], [])
        self.assertEqual(result["relationships"], [])

    def test_convert_text_to_opencontracts_empty_docs(self):
        """Test _convert_text_to_opencontracts with empty documents."""
        parser = LlamaParseParser()

        # Create mock LlamaIndex documents with empty text
        mock_docs = [
            MockLlamaDocument(""),
            MockLlamaDocument("Only second page has content"),
        ]

        result = parser._convert_text_to_opencontracts(self.doc, mock_docs)

        # Empty pages are filtered out, so only non-empty page content is included
        self.assertEqual(result["content"], "Only second page has content")
        self.assertEqual(result["page_count"], 2)
