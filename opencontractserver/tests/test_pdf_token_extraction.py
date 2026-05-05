"""
Tests for the PDF token extraction utility module.

Tests cover:
- Token extraction from PDFs using pdfplumber
- Spatial intersection queries using shapely STRtree
- Edge cases (empty PDFs, invalid coordinates)
- has_extractable_text detection

Uses mock-based testing to avoid needing real PDF fixtures.
"""

from unittest.mock import MagicMock, patch

import numpy as np
from django.test import TestCase
from shapely.geometry import box
from shapely.strtree import STRtree

from opencontractserver.utils.pdf_token_extraction import (
    crop_image_from_pdf,
    extract_images_from_pdf,
    extract_pawls_tokens_from_pdf,
    find_tokens_in_bbox,
    get_image_as_base64,
    get_image_data_url,
    has_extractable_text,
)


class TestHasExtractableText(TestCase):
    """Tests for the has_extractable_text function."""

    @patch("pdfplumber.open")
    def test_has_extractable_text_returns_true_for_text_pdf(self, mock_pdfplumber_open):
        """Test that has_extractable_text returns True for PDFs with text."""
        # Mock pdfplumber to return a PDF with text
        mock_page = MagicMock()
        mock_page.extract_text.return_value = (
            "This is sample text content that is long enough."
        )

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        result = has_extractable_text(b"fake pdf bytes")

        self.assertTrue(result)

    @patch("pdfplumber.open")
    def test_has_extractable_text_returns_false_for_scanned_pdf(
        self, mock_pdfplumber_open
    ):
        """Test that has_extractable_text returns False for scanned PDFs."""
        # Mock pdfplumber to return a PDF with no text
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page, mock_page, mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        result = has_extractable_text(b"fake scanned pdf bytes")

        self.assertFalse(result)

    @patch("pdfplumber.open")
    def test_has_extractable_text_returns_false_for_empty_pdf(
        self, mock_pdfplumber_open
    ):
        """Test that has_extractable_text returns False for PDFs with no pages."""
        mock_pdf = MagicMock()
        mock_pdf.pages = []
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        result = has_extractable_text(b"empty pdf")

        self.assertFalse(result)

    @patch("pdfplumber.open")
    def test_has_extractable_text_min_chars_threshold(self, mock_pdfplumber_open):
        """Test that min_chars threshold works correctly."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "short"  # Less than 10 chars

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        # Default min_chars=10, "short" is only 5 chars
        result = has_extractable_text(b"pdf", min_chars=10)
        self.assertFalse(result)

        # With lower threshold, should pass
        mock_page.extract_text.return_value = "short"
        result = has_extractable_text(b"pdf", min_chars=3)
        self.assertTrue(result)


class TestExtractPawlsTokensFromPdf(TestCase):
    """Tests for the extract_pawls_tokens_from_pdf function."""

    @patch("pdfplumber.open")
    def test_extract_tokens_returns_correct_format(self, mock_pdfplumber_open):
        """Test that token extraction returns correct PAWLS format."""
        # Mock pdfplumber page with words
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.extract_words.return_value = [
            {"x0": 100, "top": 100, "x1": 150, "bottom": 120, "text": "Hello"},
            {"x0": 160, "top": 100, "x1": 210, "bottom": 120, "text": "World"},
        ]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        (
            pawls_pages,
            spatial_indices,
            tokens_by_page,
            token_indices_by_page,
            page_dims,
            content,
        ) = extract_pawls_tokens_from_pdf(b"fake pdf bytes")

        # Check PAWLS pages structure
        self.assertEqual(len(pawls_pages), 1)
        self.assertEqual(pawls_pages[0]["page"]["width"], 612)
        self.assertEqual(pawls_pages[0]["page"]["height"], 792)
        self.assertEqual(pawls_pages[0]["page"]["index"], 0)

        # Check tokens
        tokens = pawls_pages[0]["tokens"]
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0]["text"], "Hello")
        self.assertEqual(tokens[0]["x"], 100)
        self.assertEqual(tokens[0]["y"], 100)
        self.assertEqual(tokens[0]["width"], 50)  # 150 - 100
        self.assertEqual(tokens[0]["height"], 20)  # 120 - 100

        # Check spatial index was created
        self.assertIn(0, spatial_indices)
        self.assertIsInstance(spatial_indices[0], STRtree)

        # Check tokens_by_page
        self.assertIn(0, tokens_by_page)
        self.assertEqual(len(tokens_by_page[0]), 2)

        # Check token_indices_by_page
        self.assertIn(0, token_indices_by_page)
        self.assertEqual(len(token_indices_by_page[0]), 2)

        # Check page dimensions
        self.assertEqual(page_dims[0], (612.0, 792.0))

        # Check content
        self.assertIn("Hello", content)
        self.assertIn("World", content)

    @patch("pdfplumber.open")
    def test_extract_tokens_multiple_pages(self, mock_pdfplumber_open):
        """Test token extraction from multiple pages."""
        mock_page1 = MagicMock()
        mock_page1.width = 612
        mock_page1.height = 792
        mock_page1.extract_words.return_value = [
            {"x0": 100, "top": 100, "x1": 150, "bottom": 120, "text": "Page1"},
        ]

        mock_page2 = MagicMock()
        mock_page2.width = 612
        mock_page2.height = 792
        mock_page2.extract_words.return_value = [
            {"x0": 100, "top": 100, "x1": 150, "bottom": 120, "text": "Page2"},
        ]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page1, mock_page2]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        pawls_pages, spatial_indices, tokens_by_page, _, _, content = (
            extract_pawls_tokens_from_pdf(b"multi-page pdf")
        )

        self.assertEqual(len(pawls_pages), 2)
        self.assertEqual(pawls_pages[0]["page"]["index"], 0)
        self.assertEqual(pawls_pages[1]["page"]["index"], 1)
        self.assertIn(0, spatial_indices)
        self.assertIn(1, spatial_indices)

    @patch("pdfplumber.open")
    def test_extract_tokens_empty_page(self, mock_pdfplumber_open):
        """Test handling of pages with no words."""
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.extract_words.return_value = []

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        pawls_pages, spatial_indices, tokens_by_page, token_indices_by_page, _, _ = (
            extract_pawls_tokens_from_pdf(b"empty page pdf")
        )

        self.assertEqual(len(pawls_pages), 1)
        self.assertEqual(len(pawls_pages[0]["tokens"]), 0)
        # No spatial index for empty page
        self.assertNotIn(0, spatial_indices)
        self.assertEqual(len(tokens_by_page[0]), 0)

    @patch("pdfplumber.open")
    def test_extract_tokens_with_page_dimensions_override(self, mock_pdfplumber_open):
        """Test that page_dimensions parameter scales coordinates."""
        mock_page = MagicMock()
        mock_page.width = 612  # Native width
        mock_page.height = 792  # Native height
        mock_page.extract_words.return_value = [
            {"x0": 100, "top": 100, "x1": 200, "bottom": 120, "text": "Test"},
        ]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        # Override with double the dimensions
        page_dimensions = {0: (1224.0, 1584.0)}  # 2x the native dimensions

        pawls_pages, _, _, _, page_dims, _ = extract_pawls_tokens_from_pdf(
            b"pdf", page_dimensions=page_dimensions
        )

        # Coordinates should be scaled
        token = pawls_pages[0]["tokens"][0]
        self.assertEqual(token["x"], 200)  # 100 * 2
        self.assertEqual(token["y"], 200)  # 100 * 2
        self.assertEqual(token["width"], 200)  # 100 * 2
        self.assertEqual(token["height"], 40)  # 20 * 2

        # Page dimensions should match override
        self.assertEqual(page_dims[0], (1224.0, 1584.0))

    @patch("pdfplumber.open")
    def test_extract_tokens_skips_invalid_tokens(self, mock_pdfplumber_open):
        """Test that tokens with zero width/height or empty text are skipped."""
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.extract_words.return_value = [
            {
                "x0": 100,
                "top": 100,
                "x1": 100,
                "bottom": 120,
                "text": "ZeroWidth",
            },  # Skip
            {
                "x0": 100,
                "top": 100,
                "x1": 150,
                "bottom": 100,
                "text": "ZeroHeight",
            },  # Skip
            {
                "x0": 100,
                "top": 100,
                "x1": 150,
                "bottom": 120,
                "text": "   ",
            },  # Skip whitespace
            {"x0": 200, "top": 100, "x1": 250, "bottom": 120, "text": "Valid"},  # Keep
        ]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        pawls_pages, _, _, _, _, _ = extract_pawls_tokens_from_pdf(b"pdf")

        # Only the valid token should be included
        self.assertEqual(len(pawls_pages[0]["tokens"]), 1)
        self.assertEqual(pawls_pages[0]["tokens"][0]["text"], "Valid")


class TestFindTokensInBbox(TestCase):
    """Tests for the find_tokens_in_bbox function."""

    def setUp(self):
        """Create a test spatial index with some tokens."""
        # Create tokens at known positions
        self.tokens = [
            {"x": 100, "y": 100, "width": 50, "height": 20, "text": "Token0"},
            {"x": 160, "y": 100, "width": 50, "height": 20, "text": "Token1"},
            {"x": 220, "y": 100, "width": 50, "height": 20, "text": "Token2"},
            {"x": 100, "y": 200, "width": 50, "height": 20, "text": "Token3"},
        ]

        # Create geometries for spatial index
        geometries = []
        for token in self.tokens:
            geom = box(
                token["x"],
                token["y"],
                token["x"] + token["width"],
                token["y"] + token["height"],
            )
            geometries.append(geom)

        self.spatial_index = STRtree(geometries)
        self.token_indices = np.array([0, 1, 2, 3], dtype=np.intp)

    def test_find_tokens_in_bbox_returns_intersecting_tokens(self):
        """Test that find_tokens_in_bbox returns tokens that intersect the bbox."""
        # Bbox that should intersect Token0 and Token1
        bbox = {"left": 80, "top": 90, "right": 200, "bottom": 130}

        token_refs = find_tokens_in_bbox(
            bbox=bbox,
            page_idx=0,
            spatial_index=self.spatial_index,
            token_indices=self.token_indices,
            tokens=self.tokens,
        )

        # Should find Token0 and Token1
        self.assertEqual(len(token_refs), 2)
        self.assertIn({"pageIndex": 0, "tokenIndex": 0}, token_refs)
        self.assertIn({"pageIndex": 0, "tokenIndex": 1}, token_refs)

    def test_find_tokens_in_bbox_returns_empty_for_no_intersection(self):
        """Test that find_tokens_in_bbox returns empty list when no intersection."""
        # Bbox that doesn't intersect any tokens
        bbox = {"left": 500, "top": 500, "right": 600, "bottom": 600}

        token_refs = find_tokens_in_bbox(
            bbox=bbox,
            page_idx=0,
            spatial_index=self.spatial_index,
            token_indices=self.token_indices,
            tokens=self.tokens,
        )

        self.assertEqual(len(token_refs), 0)

    def test_find_tokens_in_bbox_handles_no_spatial_index(self):
        """Test that find_tokens_in_bbox returns empty list when no spatial index."""
        bbox = {"left": 100, "top": 100, "right": 200, "bottom": 200}

        token_refs = find_tokens_in_bbox(
            bbox=bbox,
            page_idx=0,
            spatial_index=None,
            token_indices=None,
            tokens=None,
        )

        self.assertEqual(len(token_refs), 0)

    def test_find_tokens_in_bbox_handles_empty_token_indices(self):
        """Test that find_tokens_in_bbox returns empty list for empty indices."""
        bbox = {"left": 100, "top": 100, "right": 200, "bottom": 200}

        token_refs = find_tokens_in_bbox(
            bbox=bbox,
            page_idx=0,
            spatial_index=self.spatial_index,
            token_indices=np.array([], dtype=np.intp),
            tokens=[],
        )

        self.assertEqual(len(token_refs), 0)

    def test_find_tokens_in_bbox_handles_swapped_coordinates(self):
        """Test that find_tokens_in_bbox handles left > right or top > bottom."""
        # Swapped coordinates (right < left, bottom < top)
        bbox = {"left": 200, "top": 130, "right": 80, "bottom": 90}

        token_refs = find_tokens_in_bbox(
            bbox=bbox,
            page_idx=0,
            spatial_index=self.spatial_index,
            token_indices=self.token_indices,
            tokens=self.tokens,
        )

        # Should still find Token0 and Token1 after coordinates are swapped
        self.assertEqual(len(token_refs), 2)

    def test_find_tokens_in_bbox_returns_sorted_indices(self):
        """Test that token refs are sorted by token index."""
        # Bbox that should intersect all tokens
        bbox = {"left": 0, "top": 0, "right": 500, "bottom": 500}

        token_refs = find_tokens_in_bbox(
            bbox=bbox,
            page_idx=0,
            spatial_index=self.spatial_index,
            token_indices=self.token_indices,
            tokens=self.tokens,
        )

        # Should be sorted by token index
        indices = [ref["tokenIndex"] for ref in token_refs]
        self.assertEqual(indices, sorted(indices))

    def test_find_tokens_in_bbox_uses_correct_page_index(self):
        """Test that returned token refs use the provided page index."""
        bbox = {"left": 80, "top": 90, "right": 200, "bottom": 130}

        token_refs = find_tokens_in_bbox(
            bbox=bbox,
            page_idx=5,  # Use a different page index
            spatial_index=self.spatial_index,
            token_indices=self.token_indices,
            tokens=self.tokens,
        )

        # All refs should have pageIndex=5
        for ref in token_refs:
            self.assertEqual(ref["pageIndex"], 5)


class TestExtractImagesFromPdf(TestCase):
    """Tests for the extract_images_from_pdf function."""

    @patch("pdfplumber.open")
    def test_extract_images_returns_dict_by_page(self, mock_pdfplumber_open):
        """Test that extract_images_from_pdf returns dict mapping page to images."""
        # Mock pdfplumber page with images
        mock_image_info = {
            "x0": 100,
            "top": 100,
            "x1": 300,
            "bottom": 300,
        }

        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = [mock_image_info]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        # Mock PIL Image returned from rendering+cropping
        mock_pil_image = MagicMock()
        mock_pil_image.mode = "RGB"
        mock_pil_image.width = 200
        mock_pil_image.height = 200
        mock_pil_image.save = lambda buf, format, quality=85: buf.write(b"fake")

        # After issue #1498, extract_images_from_pdf renders the page once via
        # _render_pdf_page and crops via _crop_region_from_rendered_page.
        with patch(
            "opencontractserver.utils.pdf_token_extraction._render_pdf_page"
        ) as mock_render, patch(
            "opencontractserver.utils.pdf_token_extraction"
            "._crop_region_from_rendered_page"
        ) as mock_crop:
            mock_render.return_value = mock_pil_image
            mock_crop.return_value = mock_pil_image

            images_by_page = extract_images_from_pdf(b"fake pdf bytes")

            # Should return dict
            self.assertIsInstance(images_by_page, dict)

    @patch("pdfplumber.open")
    def test_extract_images_returns_empty_for_no_images(self, mock_pdfplumber_open):
        """Test that extract_images_from_pdf returns empty dict for PDFs without images."""
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = []

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        images_by_page = extract_images_from_pdf(b"pdf without images")

        self.assertEqual(len(images_by_page.get(0, [])), 0)

    @patch("pdfplumber.open")
    def test_extract_images_skips_small_images(self, mock_pdfplumber_open):
        """Test that small images below minimum size are skipped."""
        # Image that is too small (40x40, below 50x50 default)
        mock_image_info = {
            "x0": 100,
            "top": 100,
            "x1": 140,  # width = 40
            "bottom": 140,  # height = 40
        }

        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = [mock_image_info]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        images_by_page = extract_images_from_pdf(b"pdf", min_width=50, min_height=50)

        # Small image should be skipped
        self.assertEqual(len(images_by_page.get(0, [])), 0)


class TestCropImageFromPdf(TestCase):
    """Tests for the crop_image_from_pdf function."""

    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_crop_image_returns_image_token(self, mock_crop_region):
        """Test that crop_image_from_pdf returns a valid image token."""
        # Mock the cropped PIL image
        mock_pil_image = MagicMock()
        mock_pil_image.mode = "RGB"
        mock_pil_image.width = 150
        mock_pil_image.height = 100

        # Mock save to write some bytes
        def mock_save(buf, format, quality=85):
            buf.write(b"fake image bytes")

        mock_pil_image.save = mock_save
        mock_crop_region.return_value = mock_pil_image

        bbox = {"left": 100, "top": 100, "right": 250, "bottom": 200}

        image_token = crop_image_from_pdf(
            b"fake pdf", 0, bbox, 612, 792, image_format="jpeg"
        )

        # Should return a valid image token
        self.assertIsNotNone(image_token)
        self.assertEqual(image_token["x"], 100)
        self.assertEqual(image_token["y"], 100)
        self.assertEqual(image_token["width"], 150)
        self.assertEqual(image_token["height"], 100)
        self.assertEqual(image_token["format"], "jpeg")
        self.assertIn("base64_data", image_token)
        self.assertIn("content_hash", image_token)

    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_crop_image_returns_none_on_failure(self, mock_crop_region):
        """Test that crop_image_from_pdf returns None when cropping fails."""
        mock_crop_region.return_value = None

        bbox = {"left": 100, "top": 100, "right": 250, "bottom": 200}

        image_token = crop_image_from_pdf(b"fake pdf", 0, bbox, 612, 792)

        self.assertIsNone(image_token)

    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_crop_image_handles_swapped_coordinates(self, mock_crop_region):
        """Test that crop_image_from_pdf handles swapped left/right or top/bottom."""
        mock_pil_image = MagicMock()
        mock_pil_image.mode = "RGB"
        mock_pil_image.width = 150
        mock_pil_image.height = 100
        mock_pil_image.save = lambda buf, format, quality=85: buf.write(b"fake")
        mock_crop_region.return_value = mock_pil_image

        # Swapped coordinates
        bbox = {"left": 250, "top": 200, "right": 100, "bottom": 100}

        image_token = crop_image_from_pdf(b"fake pdf", 0, bbox, 612, 792)

        # Should still work with corrected coordinates
        self.assertIsNotNone(image_token)
        self.assertEqual(image_token["x"], 100)  # Swapped back
        self.assertEqual(image_token["y"], 100)

    @patch("opencontractserver.utils.pdf_token_extraction._save_image_to_storage")
    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_crop_image_saves_to_storage(self, mock_crop_region, mock_save):
        """Test that crop_image_from_pdf saves to storage when storage_path is provided."""
        mock_pil_image = MagicMock()
        mock_pil_image.mode = "RGB"
        mock_pil_image.width = 150
        mock_pil_image.height = 100
        mock_pil_image.save = lambda buf, format, quality=85: buf.write(b"fake")
        mock_crop_region.return_value = mock_pil_image
        mock_save.return_value = "documents/123/images/page_0_img_0.jpg"

        bbox = {"left": 100, "top": 100, "right": 250, "bottom": 200}

        image_token = crop_image_from_pdf(
            b"fake pdf",
            0,
            bbox,
            612,
            792,
            storage_path="documents/123/images",
            img_idx=0,
        )

        # Should call storage saver
        mock_save.assert_called_once()
        # Should have image_path instead of base64_data
        self.assertEqual(
            image_token["image_path"], "documents/123/images/page_0_img_0.jpg"
        )
        self.assertNotIn("base64_data", image_token)

    @patch("opencontractserver.utils.pdf_token_extraction._save_image_to_storage")
    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_crop_image_falls_back_to_base64_on_storage_failure(
        self, mock_crop_region, mock_save
    ):
        """Test that crop_image_from_pdf falls back to base64 when storage save fails."""
        mock_pil_image = MagicMock()
        mock_pil_image.mode = "RGB"
        mock_pil_image.width = 150
        mock_pil_image.height = 100
        mock_pil_image.save = lambda buf, format, quality=85: buf.write(b"fake")
        mock_crop_region.return_value = mock_pil_image
        mock_save.return_value = None  # Simulate storage failure

        bbox = {"left": 100, "top": 100, "right": 250, "bottom": 200}

        image_token = crop_image_from_pdf(
            b"fake pdf",
            0,
            bbox,
            612,
            792,
            storage_path="documents/123/images",
            img_idx=0,
        )

        # Should fall back to base64_data
        self.assertIn("base64_data", image_token)
        self.assertNotIn("image_path", image_token)


class TestImageHelperFunctions(TestCase):
    """Tests for image helper functions."""

    def test_get_image_as_base64_returns_base64_data(self):
        """Test that get_image_as_base64 returns the base64_data field."""
        image_token = {
            "x": 100,
            "y": 100,
            "width": 50,
            "height": 50,
            "base64_data": "SGVsbG8gV29ybGQ=",
            "format": "jpeg",
        }

        result = get_image_as_base64(image_token)

        self.assertEqual(result, "SGVsbG8gV29ybGQ=")

    @patch("opencontractserver.utils.pdf_token_extraction._load_image_from_storage")
    def test_get_image_as_base64_loads_from_storage(self, mock_load):
        """Test that get_image_as_base64 loads from storage when image_path is present."""
        # Mock storage to return image bytes
        mock_load.return_value = b"Hello World"

        image_token = {
            "x": 100,
            "y": 100,
            "width": 50,
            "height": 50,
            "image_path": "documents/123/images/page_0_img_0.jpg",
            "format": "jpeg",
        }

        result = get_image_as_base64(image_token)

        # Should call storage loader
        mock_load.assert_called_once_with("documents/123/images/page_0_img_0.jpg")
        # Should return base64 encoded bytes
        self.assertEqual(result, "SGVsbG8gV29ybGQ=")

    @patch("opencontractserver.utils.pdf_token_extraction._load_image_from_storage")
    def test_get_image_as_base64_returns_none_when_storage_fails(self, mock_load):
        """Test that get_image_as_base64 returns None when storage load fails."""
        mock_load.return_value = None

        image_token = {
            "x": 100,
            "y": 100,
            "width": 50,
            "height": 50,
            "image_path": "documents/123/images/missing.jpg",
            "format": "jpeg",
        }

        result = get_image_as_base64(image_token)

        self.assertIsNone(result)

    def test_get_image_as_base64_prefers_inline_base64(self):
        """Test that base64_data is preferred over image_path when both exist."""
        image_token = {
            "x": 100,
            "y": 100,
            "width": 50,
            "height": 50,
            "base64_data": "aW5saW5lZGF0YQ==",  # "inlinedata" in base64
            "image_path": "documents/123/images/page_0_img_0.jpg",
            "format": "jpeg",
        }

        result = get_image_as_base64(image_token)

        # Should return inline data, not load from storage
        self.assertEqual(result, "aW5saW5lZGF0YQ==")

    def test_get_image_as_base64_returns_none_for_missing_data(self):
        """Test that get_image_as_base64 returns None when no image data."""
        image_token = {
            "x": 100,
            "y": 100,
            "width": 50,
            "height": 50,
            "format": "jpeg",
        }

        result = get_image_as_base64(image_token)

        self.assertIsNone(result)

    def test_get_image_data_url_returns_correct_format(self):
        """Test that get_image_data_url returns properly formatted data URL."""
        image_token = {
            "x": 100,
            "y": 100,
            "width": 50,
            "height": 50,
            "base64_data": "SGVsbG8gV29ybGQ=",
            "format": "jpeg",
        }

        result = get_image_data_url(image_token)

        self.assertEqual(result, "data:image/jpeg;base64,SGVsbG8gV29ybGQ=")

    def test_get_image_data_url_handles_png_format(self):
        """Test that get_image_data_url uses correct MIME type for PNG."""
        image_token = {
            "x": 100,
            "y": 100,
            "width": 50,
            "height": 50,
            "base64_data": "iVBORw0KGgo=",
            "format": "png",
        }

        result = get_image_data_url(image_token)

        self.assertTrue(result.startswith("data:image/png;base64,"))

    def test_get_image_data_url_returns_none_for_missing_data(self):
        """Test that get_image_data_url returns None when no image data."""
        image_token = {
            "x": 100,
            "y": 100,
            "width": 50,
            "height": 50,
            "format": "jpeg",
        }

        result = get_image_data_url(image_token)

        self.assertIsNone(result)


class TestExtractImagesMemoryBound(TestCase):
    """
    Regression tests for issue #1498 — bound peak memory in PDF image
    extraction so it does NOT scale linearly with page count.

    The fix has three observable contracts that these tests pin down:

      1. A page with N embedded images is rasterised at most ONCE per call.
      2. Per-image PIL Image and BytesIO buffers are explicitly closed.
      3. pdfplumber's per-page parse cache is flushed and gc.collect() is
         invoked between pages.

    Without (1), peak RSS scales with images-per-page; without (2), peak
    RSS scales with pages-per-document; without (3), pdfplumber's lazy
    caches accumulate across the iteration.
    """

    def _make_mock_image_info(self, x0=100, top=100, x1=300, bottom=300):
        """Build a pdfplumber-style image info dict (no decodable stream)."""
        return {"x0": x0, "top": top, "x1": x1, "bottom": bottom}

    def _make_mock_pil_image(self, width=200, height=200):
        """
        Build a PIL-Image-shaped mock that can be saved, cropped, and closed.

        Sets ``.size`` (used by ``_crop_region_from_rendered_page``) and
        wires ``.crop`` to return a sibling mock so the production code's
        crop path returns a usable image-like object.
        """
        mock = MagicMock()
        mock.mode = "RGB"
        mock.width = width
        mock.height = height
        mock.size = (width, height)

        def _save(buf, format, quality=85):
            buf.write(b"fake encoded bytes")

        mock.save = _save

        # ``crop`` on a real PIL image returns a new image. Producing a
        # distinct mock per call lets tests assert per-crop close().
        def _crop(_box):
            child = MagicMock()
            child.mode = "RGB"
            child.width = width
            child.height = height
            child.size = (width, height)
            child.save = _save
            return child

        mock.crop = MagicMock(side_effect=_crop)
        return mock

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_page_rendered_only_once_per_page_with_multiple_images(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        A page with 5 images that all need cropping should rasterise the
        page exactly once — not five times. Pre-fix this was 5x the work
        and 5x the page-render RSS spike.
        """
        # 5 image infos on a single page, none with a decodable stream
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = [self._make_mock_image_info() for _ in range(5)]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        # Render returns a fresh mock each call so we can count distinctly.
        mock_render.side_effect = lambda *_a, **_kw: self._make_mock_pil_image()

        extract_images_from_pdf(b"fake pdf bytes")

        # The page must be rendered at most once even with 5 images.
        self.assertEqual(
            mock_render.call_count,
            1,
            "Expected page rendering to be cached across images on the "
            "same page; got "
            f"{mock_render.call_count} renders for 5 images on 1 page.",
        )

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_render_count_equals_pages_not_images(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        Across 10 pages with 3 images each, _render_pdf_page must be called
        at most 10 times — not 30. This is the headline memory fix.
        """
        pages = []
        for _ in range(10):
            p = MagicMock()
            p.width = 612
            p.height = 792
            p.images = [self._make_mock_image_info() for _ in range(3)]
            pages.append(p)

        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        mock_render.side_effect = lambda *_a, **_kw: self._make_mock_pil_image()

        extract_images_from_pdf(b"fake pdf bytes")

        # One render per page with images, regardless of images-per-page.
        self.assertEqual(
            mock_render.call_count,
            10,
            "Expected exactly one page render per page (10 pages * 1 render);"
            f" got {mock_render.call_count}.",
        )

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_rendered_page_is_closed_after_each_page(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        The rasterised page buffer is the largest single allocation in the
        extraction loop. It must be ``close()``-d before moving to the next
        page so peak RSS is bounded by one rendered page, not N.
        """
        # 3 pages, each with one image needing crop
        pages = []
        for _ in range(3):
            p = MagicMock()
            p.width = 612
            p.height = 792
            p.images = [self._make_mock_image_info()]
            pages.append(p)

        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        rendered_pages = [self._make_mock_pil_image() for _ in range(3)]
        mock_render.side_effect = rendered_pages

        extract_images_from_pdf(b"fake pdf bytes")

        # Every rendered page must have had close() called.
        for idx, rp in enumerate(rendered_pages):
            self.assertTrue(
                rp.close.called,
                f"Rendered page {idx} was not closed; rendered-page buffers "
                "would accumulate as RSS across pages.",
            )

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_pdfplumber_page_cache_flushed_between_pages(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        pdfplumber lazily caches per-page parse state when ``page.images`` is
        accessed. Without ``page.flush_cache()``, that state lives until the
        outer ``with`` block exits — i.e. RSS grows monotonically with page
        count even after we extract their images.
        """
        pages = []
        for _ in range(4):
            p = MagicMock()
            p.width = 612
            p.height = 792
            p.images = []  # No images, but cache must still flush
            pages.append(p)

        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        extract_images_from_pdf(b"fake pdf bytes")

        for idx, p in enumerate(pages):
            self.assertTrue(
                p.flush_cache.called,
                f"page.flush_cache() not called for page {idx}; pdfplumber "
                "per-page caches would accumulate across the iteration.",
            )

    @patch("opencontractserver.utils.pdf_token_extraction.gc.collect")
    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_gc_collect_runs_between_pages(
        self, mock_pdfplumber_open, mock_render, mock_gc
    ):
        """
        Even with explicit ``close()`` calls, Poppler subprocess buffers and
        PIL pixel buffers can sit in the heap until CPython's threshold-based
        GC runs. Forcing collection between pages reclaims that memory
        immediately and keeps peak RSS bounded.
        """
        pages = []
        for _ in range(5):
            p = MagicMock()
            p.width = 612
            p.height = 792
            p.images = []
            pages.append(p)

        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        extract_images_from_pdf(b"fake pdf bytes")

        # With the default IMAGE_EXTRACTION_GC_INTERVAL_PAGES=1, gc.collect
        # should run once per page.
        self.assertGreaterEqual(
            mock_gc.call_count,
            5,
            "gc.collect() not invoked at the configured page interval; peak "
            "RSS may grow with page count under default CPython GC thresholds.",
        )

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_per_image_buffers_closed_eagerly(self, mock_pdfplumber_open, mock_render):
        """
        Per-image PIL Image objects must be closed in the inner loop, not
        left to refcount-rebind on the next iteration. Without this, the
        decoded image bytes for image N stay live until image N+1 is fully
        decoded, doubling per-image peak RSS.
        """
        # One page with two images
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = [self._make_mock_image_info() for _ in range(2)]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        # Each crop returns a distinct mock so we can verify both are closed
        cropped_images = [self._make_mock_pil_image() for _ in range(2)]
        rendered = self._make_mock_pil_image()
        rendered.crop = MagicMock(side_effect=cropped_images)
        mock_render.return_value = rendered

        extract_images_from_pdf(b"fake pdf bytes")

        for idx, ci in enumerate(cropped_images):
            self.assertTrue(
                ci.close.called,
                f"Per-image PIL buffer {idx} was not closed eagerly; "
                "decoded image bytes would briefly double in RSS.",
            )

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_extract_handles_synthetic_large_document(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        Smoke-test scaling: a synthetic 100-page document with 1 image per
        page must produce 100 image tokens AND must not invoke the page
        rasteriser more than 100 times. This is the regression guard for
        the 127-page OOM in the issue report.
        """
        num_pages = 100
        pages = []
        for _ in range(num_pages):
            p = MagicMock()
            p.width = 612
            p.height = 792
            p.images = [self._make_mock_image_info()]
            pages.append(p)

        mock_pdf = MagicMock()
        mock_pdf.pages = pages
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        mock_render.side_effect = lambda *_a, **_kw: self._make_mock_pil_image()

        result = extract_images_from_pdf(b"fake pdf bytes")

        # We get an image token per page
        total_images = sum(len(v) for v in result.values())
        self.assertEqual(
            total_images,
            num_pages,
            f"Expected {num_pages} image tokens, got {total_images}.",
        )
        # And we rendered each page at most once
        self.assertLessEqual(
            mock_render.call_count,
            num_pages,
            "Page render count exceeded page count; per-image rasterisation "
            "regressed.",
        )

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_rgba_image_original_closed_before_rebind(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        When a cropped image is in RGBA mode and JPEG output is requested,
        the production code calls pil_image.convert("RGB"), then closes the
        original before rebinding pil_image to the converted copy.

        Without the fix, the original reference is dropped without close(),
        leaking the pre-conversion pixel buffer until the next GC cycle.
        This test pins that the ORIGINAL image mock receives close() before
        the finally block closes the converted copy.
        """
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = [self._make_mock_image_info()]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        # Original cropped image in RGBA mode
        original_image = MagicMock()
        original_image.mode = "RGBA"
        original_image.width = 200
        original_image.height = 200
        original_image.size = (200, 200)

        # The converted RGB image returned by .convert("RGB")
        converted_image = MagicMock()
        converted_image.mode = "RGB"
        converted_image.width = 200
        converted_image.height = 200
        converted_image.size = (200, 200)

        def _save(buf, format, quality=85):
            buf.write(b"fake jpeg bytes")

        converted_image.save = _save
        original_image.convert = MagicMock(return_value=converted_image)

        rendered_page = self._make_mock_pil_image()
        rendered_page.crop = MagicMock(return_value=original_image)
        mock_render.return_value = rendered_page

        extract_images_from_pdf(b"fake pdf bytes", image_format="jpeg")

        # convert("RGB") must have been called on the original
        original_image.convert.assert_called_once_with("RGB")
        # The ORIGINAL must be closed (not just the converted copy in finally)
        original_image.close.assert_called()
        # The converted image is closed by the finally block
        converted_image.close.assert_called()

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_la_mode_image_original_closed_before_rebind(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        Same contract as the RGBA test but for LA (greyscale + alpha) mode,
        which is the other common transparency variant that requires conversion
        before JPEG encoding.
        """
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = [self._make_mock_image_info()]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        original_image = MagicMock()
        original_image.mode = "LA"
        original_image.width = 100
        original_image.height = 100
        original_image.size = (100, 100)

        converted_image = MagicMock()
        converted_image.mode = "RGB"
        converted_image.width = 100
        converted_image.height = 100
        converted_image.size = (100, 100)
        converted_image.save = lambda buf, format, quality=85: buf.write(b"la jpeg")
        original_image.convert = MagicMock(return_value=converted_image)

        rendered_page = self._make_mock_pil_image()
        rendered_page.crop = MagicMock(return_value=original_image)
        mock_render.return_value = rendered_page

        extract_images_from_pdf(b"fake pdf bytes", image_format="jpeg")

        original_image.convert.assert_called_once_with("RGB")
        original_image.close.assert_called()
        converted_image.close.assert_called()

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_p_mode_image_original_closed_before_rebind(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        Same contract for palette (P) mode images, which cannot be JPEG-encoded
        directly and must first be converted to RGB.
        """
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = [self._make_mock_image_info()]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        original_image = MagicMock()
        original_image.mode = "P"
        original_image.width = 150
        original_image.height = 150
        original_image.size = (150, 150)

        converted_image = MagicMock()
        converted_image.mode = "RGB"
        converted_image.width = 150
        converted_image.height = 150
        converted_image.size = (150, 150)
        converted_image.save = lambda buf, format, quality=85: buf.write(b"p jpeg")
        original_image.convert = MagicMock(return_value=converted_image)

        rendered_page = self._make_mock_pil_image()
        rendered_page.crop = MagicMock(return_value=original_image)
        mock_render.return_value = rendered_page

        extract_images_from_pdf(b"fake pdf bytes", image_format="jpeg")

        original_image.convert.assert_called_once_with("RGB")
        original_image.close.assert_called()
        converted_image.close.assert_called()

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_rgb_image_skips_conversion_no_spurious_close(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        A native RGB image must NOT have convert() called on it; the
        conversion guard is mode-conditional.  This test also verifies
        the image is still closed (by the finally block) even when
        no conversion is needed.
        """
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        mock_page.images = [self._make_mock_image_info()]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        rgb_image = MagicMock()
        rgb_image.mode = "RGB"
        rgb_image.width = 200
        rgb_image.height = 200
        rgb_image.size = (200, 200)
        rgb_image.save = lambda buf, format, quality=85: buf.write(b"rgb jpeg")

        rendered_page = self._make_mock_pil_image()
        rendered_page.crop = MagicMock(return_value=rgb_image)
        mock_render.return_value = rendered_page

        extract_images_from_pdf(b"fake pdf bytes", image_format="jpeg")

        # No conversion for RGB
        rgb_image.convert.assert_not_called()
        # But the image must still be closed in the finally block
        rgb_image.close.assert_called()

    @patch("opencontractserver.utils.pdf_token_extraction._render_pdf_page")
    @patch("pdfplumber.open")
    def test_size_limit_stops_extraction_and_sets_flag(
        self, mock_pdfplumber_open, mock_render
    ):
        """
        When the running total of image bytes exceeds MAX_TOTAL_IMAGES_SIZE_BYTES,
        the extraction loop must stop adding images for that page without crashing.

        We patch MAX_TOTAL_IMAGES_SIZE_BYTES to a very small value so the
        test does not need to write gigabytes of data.
        """
        mock_page = MagicMock()
        mock_page.width = 612
        mock_page.height = 792
        # Three images; the limit should be triggered before the last one
        mock_page.images = [self._make_mock_image_info() for _ in range(3)]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        # Each image writes 100 bytes; we set the total limit to 150 so the
        # first image fits but the second triggers the cap.
        small_payload = b"X" * 100

        def _make_small_image():
            img = MagicMock()
            img.mode = "RGB"
            img.width = 200
            img.height = 200
            img.size = (200, 200)
            img.save = lambda buf, format, quality=85: buf.write(small_payload)
            return img

        rendered_page = self._make_mock_pil_image()
        rendered_page.crop = MagicMock(side_effect=lambda _: _make_small_image())
        mock_render.return_value = rendered_page

        patch_target = (
            "opencontractserver.utils.pdf_token_extraction.MAX_TOTAL_IMAGES_SIZE_BYTES"
        )
        with patch(patch_target, 150):
            result = extract_images_from_pdf(b"fake pdf bytes")

        # Only 1 image fits under the 150-byte cap; the second triggers
        # hit_size_limit which breaks the loop.
        total = sum(len(v) for v in result.values())
        self.assertEqual(
            total,
            1,
            "Expected exactly 1 image before the size limit fires; " f"got {total}",
        )


class TestCloseQuietly(TestCase):
    """Tests for the _close_quietly helper."""

    def test_close_quietly_calls_close(self):
        """Test that _close_quietly calls close() on objects that have it."""
        from opencontractserver.utils.pdf_token_extraction import _close_quietly

        mock_obj = MagicMock()
        _close_quietly(mock_obj)
        mock_obj.close.assert_called_once()

    def test_close_quietly_handles_none(self):
        """Test that _close_quietly silently handles None."""
        from opencontractserver.utils.pdf_token_extraction import _close_quietly

        # Should not raise
        _close_quietly(None)

    def test_close_quietly_handles_object_without_close(self):
        """Test that _close_quietly handles objects without a close() method."""
        from opencontractserver.utils.pdf_token_extraction import _close_quietly

        # Should not raise
        _close_quietly("not closeable")
        _close_quietly(42)

    def test_close_quietly_swallows_close_exceptions(self):
        """Test that _close_quietly swallows exceptions raised by close()."""
        from opencontractserver.utils.pdf_token_extraction import _close_quietly

        mock_obj = MagicMock()
        mock_obj.close.side_effect = RuntimeError("close failed")

        # Should not raise
        _close_quietly(mock_obj)
        mock_obj.close.assert_called_once()


class TestCropImageFromPdfModeConversion(TestCase):
    """
    Tests for the mode-conversion fix in crop_image_from_pdf.

    The fix ensures that when a cropped PIL image in RGBA/LA/P mode is
    converted to RGB for JPEG encoding, the ORIGINAL image is closed
    before the reference is rebound to the converted copy.
    """

    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_rgba_image_original_closed_in_crop_function(self, mock_crop_region):
        """
        crop_image_from_pdf must close the original RGBA image before
        rebinding to the converted RGB image.
        """
        original_image = MagicMock()
        original_image.mode = "RGBA"
        original_image.width = 150
        original_image.height = 100
        original_image.size = (150, 100)

        converted_image = MagicMock()
        converted_image.mode = "RGB"
        converted_image.width = 150
        converted_image.height = 100
        converted_image.size = (150, 100)
        converted_image.save = lambda buf, format, quality=85: buf.write(b"rgba jpeg")
        original_image.convert = MagicMock(return_value=converted_image)
        mock_crop_region.return_value = original_image

        bbox = {"left": 100, "top": 100, "right": 250, "bottom": 200}
        result = crop_image_from_pdf(
            b"fake pdf", 0, bbox, 612, 792, image_format="jpeg"
        )

        # The function must have converted the original
        original_image.convert.assert_called_once_with("RGB")
        # And the original must be closed explicitly
        original_image.close.assert_called()
        # The result is still a valid image token
        self.assertIsNotNone(result)

    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_la_image_original_closed_in_crop_function(self, mock_crop_region):
        """Same contract for LA-mode images in crop_image_from_pdf."""
        original_image = MagicMock()
        original_image.mode = "LA"
        original_image.width = 100
        original_image.height = 80
        original_image.size = (100, 80)

        converted_image = MagicMock()
        converted_image.mode = "RGB"
        converted_image.width = 100
        converted_image.height = 80
        converted_image.size = (100, 80)
        converted_image.save = lambda buf, format, quality=85: buf.write(b"la jpeg")
        original_image.convert = MagicMock(return_value=converted_image)
        mock_crop_region.return_value = original_image

        bbox = {"left": 50, "top": 50, "right": 150, "bottom": 130}
        result = crop_image_from_pdf(
            b"fake pdf", 0, bbox, 612, 792, image_format="jpeg"
        )

        original_image.convert.assert_called_once_with("RGB")
        original_image.close.assert_called()
        self.assertIsNotNone(result)

    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_p_mode_image_original_closed_in_crop_function(self, mock_crop_region):
        """Same contract for P (palette) mode images in crop_image_from_pdf."""
        original_image = MagicMock()
        original_image.mode = "P"
        original_image.width = 120
        original_image.height = 90
        original_image.size = (120, 90)

        converted_image = MagicMock()
        converted_image.mode = "RGB"
        converted_image.width = 120
        converted_image.height = 90
        converted_image.size = (120, 90)
        converted_image.save = lambda buf, format, quality=85: buf.write(b"p jpeg")
        original_image.convert = MagicMock(return_value=converted_image)
        mock_crop_region.return_value = original_image

        bbox = {"left": 60, "top": 60, "right": 180, "bottom": 150}
        result = crop_image_from_pdf(
            b"fake pdf", 0, bbox, 612, 792, image_format="jpeg"
        )

        original_image.convert.assert_called_once_with("RGB")
        original_image.close.assert_called()
        self.assertIsNotNone(result)

    @patch("opencontractserver.utils.pdf_token_extraction._crop_pdf_region")
    def test_pil_image_closed_after_getvalue_in_crop_function(self, mock_crop_region):
        """
        crop_image_from_pdf must close the PIL image and BytesIO buffer
        after reading the bytes, not leak them until the exception handler.
        This test verifies the explicit close path added by the fix.
        """
        mock_pil = MagicMock()
        mock_pil.mode = "RGB"
        mock_pil.width = 100
        mock_pil.height = 80
        mock_pil.size = (100, 80)
        mock_pil.save = lambda buf, format, quality=85: buf.write(b"rgb jpeg bytes")
        mock_crop_region.return_value = mock_pil

        bbox = {"left": 50, "top": 50, "right": 150, "bottom": 130}
        result = crop_image_from_pdf(
            b"fake pdf", 0, bbox, 612, 792, image_format="jpeg"
        )

        # The PIL image should be closed before the function returns
        mock_pil.close.assert_called()
        self.assertIsNotNone(result)
