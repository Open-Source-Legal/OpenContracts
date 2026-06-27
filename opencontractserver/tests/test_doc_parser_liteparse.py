"""
Tests for the LiteParseParser class.

Tests cover:
- Successful PDF parsing into structural annotations with word-level tokens
- Font-size-based feature labels (Title / Section Header / Text Block)
- Derived parent-child hierarchy (parent_id) from the heading stack
- Image extraction into the unified token array + Image annotations
- Error handling (no PDF, missing document, liteparse not installed, empty result)
- Configuration via the Settings dataclass and call-time kwarg overrides

LiteParse exposes line-level spatial text items (text + x/y/width/height in PDF
points, plus font metadata). The parser maps those bboxes to word-level tokens
extracted with pdfplumber, so these tests mock both ``liteparse.LiteParse`` and
the pdfplumber-backed extraction utilities.
"""

import sys
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.parsers.liteparse_parser import (
    LABEL_SECTION_HEADER,
    LABEL_TEXT_BLOCK,
    LABEL_TITLE,
    LiteParseParser,
)
from opencontractserver.types.dicts import BoundingBoxPythonType

User = get_user_model()

# liteparse is an optional native dependency that may not be installed in the
# test environment. Inject a stand-in module so ``from liteparse import
# LiteParse`` resolves; individual tests patch ``liteparse.LiteParse``.
_mock_liteparse = MagicMock()
_mock_liteparse.LiteParse = MagicMock()
sys.modules.setdefault("liteparse", _mock_liteparse)


# ---------------------------------------------------------------------------
# Fake LiteParse result helpers (mimic the real dataclasses' attributes)
# ---------------------------------------------------------------------------
def make_item(
    text: str, x: float, y: float, w: float, h: float, font_size: Optional[float] = None
):
    """Build a stand-in for liteparse.TextItem."""
    return SimpleNamespace(
        text=text,
        x=x,
        y=y,
        width=w,
        height=h,
        font_name=None,
        font_size=font_size,
        confidence=None,
    )


def make_page(page_num: int, width: float, height: float, text: str, items: list):
    """Build a stand-in for liteparse.ParsedPage."""
    return SimpleNamespace(
        page_num=page_num,
        width=width,
        height=height,
        text=text,
        text_items=items,
    )


def make_result(pages: list, text: str):
    """Build a stand-in for liteparse.ParseResult."""
    return SimpleNamespace(pages=pages, text=text)


def create_mock_token_extraction_result(page_count=1, tokens_per_page=5):
    """Mock the 6-tuple returned by extract_pawls_tokens_from_pdf."""
    pawls_pages = []
    spatial_indices = {}
    tokens_by_page = {}
    token_indices_by_page = {}
    page_dims = {}

    for page_idx in range(page_count):
        tokens = [
            {
                "x": 100 + (i * 60),
                "y": 100,
                "width": 50,
                "height": 20,
                "text": f"word{i}",
            }
            for i in range(tokens_per_page)
        ]
        pawls_pages.append(
            {
                "page": {"width": 612, "height": 792, "index": page_idx},
                "tokens": tokens,
            }
        )
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


def create_mock_liteparse_settings(**overrides):
    """Create a mock Settings object for LiteParseParser."""
    defaults = dict(
        output_format="markdown",
        ocr_enabled=False,
        ocr_language="eng",
        ocr_server_url="",
        dpi=150,
        num_workers=4,
        target_pages="",
        max_pages=0,
        password="",
        image_mode="off",
        detect_headings=True,
        heading_size_ratio=1.2,
        extract_images=True,
        image_format="jpeg",
        image_quality=85,
        min_image_width=50,
        min_image_height=50,
    )
    defaults.update(overrides)
    mock_settings = MagicMock()
    for key, value in defaults.items():
        setattr(mock_settings, key, value)
    return mock_settings


def patch_parser_settings(parser, **overrides):
    """Patch a LiteParseParser instance with mock settings."""
    mock_settings = create_mock_liteparse_settings(**overrides)
    parser._settings = mock_settings
    for key in (
        "output_format",
        "ocr_enabled",
        "ocr_language",
        "ocr_server_url",
        "dpi",
        "num_workers",
        "target_pages",
        "max_pages",
        "password",
        "image_mode",
        "detect_headings",
        "heading_size_ratio",
        "extract_images",
        "image_format",
        "image_quality",
        "min_image_width",
        "min_image_height",
    ):
        setattr(parser, key, getattr(mock_settings, key))
    return parser


_MINIMAL_PDF = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Count 1/Kids[3 0 R]>>\nendobj\n3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"  # noqa: E501


class TestLiteParseParser(TestCase):
    """End-to-end parse tests (with extraction utilities mocked)."""

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="liteparse_user", password="testpass123"
            )
        self.doc = Document.objects.create(
            title="Test LiteParse Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )
        self.doc.pdf_file.save("test_lite.pdf", ContentFile(_MINIMAL_PDF))

    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("liteparse.LiteParse")
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.default_storage.open")
    def test_parse_success_with_tokens(
        self,
        mock_open,
        mock_liteparse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
    ):
        """A page of items becomes structural annotations with token refs."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        result = make_result(
            pages=[
                make_page(
                    1,
                    612,
                    792,
                    "Document Title\nBody one.\nBody two.",
                    [
                        make_item("Document Title", 72, 40, 400, 28, font_size=20),
                        make_item("Body one.", 72, 120, 300, 14, font_size=11),
                        make_item("Body two.", 72, 150, 300, 14, font_size=11),
                    ],
                )
            ],
            text="# Document Title\n\nBody one.\nBody two.",
        )
        mock_parser = MagicMock()
        mock_parser.parse.return_value = result
        mock_liteparse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=5
        )
        mock_find_tokens.return_value = [
            {"pageIndex": 0, "tokenIndex": 0},
            {"pageIndex": 0, "tokenIndex": 1},
        ]
        mock_extract_images.return_value = {}

        parser = patch_parser_settings(LiteParseParser())
        out = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertIsNotNone(out)
        self.assertEqual(out["title"], "Test LiteParse Document")
        self.assertEqual(out["page_count"], 1)
        self.assertEqual(len(out["pawls_file_content"]), 1)
        # Word tokens come from pdfplumber extraction.
        self.assertEqual(len(out["pawls_file_content"][0]["tokens"]), 5)

        # Three text annotations.
        self.assertEqual(len(out["labelled_text"]), 3)
        first = out["labelled_text"][0]
        self.assertEqual(first["annotationLabel"], LABEL_TITLE)
        self.assertEqual(first["structural"], True)
        self.assertEqual(first["annotation_type"], "TOKEN_LABEL")
        page_anno = first["annotation_json"]["0"]
        self.assertEqual(len(page_anno["tokensJsons"]), 2)

        # Bounds preserved as absolute coordinates (no fractional conversion).
        self.assertAlmostEqual(page_anno["bounds"]["left"], 72.0, places=1)
        self.assertAlmostEqual(page_anno["bounds"]["right"], 472.0, places=1)

    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("liteparse.LiteParse")
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.default_storage.open")
    def test_heading_detection_and_hierarchy(
        self,
        mock_open,
        mock_liteparse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
    ):
        """Font sizes drive labels and a parent-child hierarchy."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        result = make_result(
            pages=[
                make_page(
                    1,
                    612,
                    792,
                    "doc",
                    [
                        make_item("Big Title", 72, 40, 400, 30, font_size=24),
                        make_item("Section A", 72, 100, 300, 20, font_size=16),
                        make_item("body a1", 72, 130, 300, 14, font_size=11),
                        make_item("Section B", 72, 200, 300, 20, font_size=16),
                        make_item("body b1", 72, 230, 300, 14, font_size=11),
                    ],
                )
            ],
            text="doc",
        )
        mock_parser = MagicMock()
        mock_parser.parse.return_value = result
        mock_liteparse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(
            page_count=1, tokens_per_page=3
        )
        mock_find_tokens.return_value = []
        mock_extract_images.return_value = {}

        parser = patch_parser_settings(LiteParseParser())
        out = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        annos = out["labelled_text"]
        self.assertEqual(len(annos), 5)

        labels = [a["annotationLabel"] for a in annos]
        self.assertEqual(
            labels,
            [
                LABEL_TITLE,
                LABEL_SECTION_HEADER,
                LABEL_TEXT_BLOCK,
                LABEL_SECTION_HEADER,
                LABEL_TEXT_BLOCK,
            ],
        )

        by_id = {a["id"]: a for a in annos}
        # Title is a root.
        self.assertIsNone(by_id["0"]["parent_id"])
        # Section A and Section B nest under the Title.
        self.assertEqual(by_id["1"]["parent_id"], "0")
        self.assertEqual(by_id["3"]["parent_id"], "0")
        # Body text nests under its nearest preceding section header.
        self.assertEqual(by_id["2"]["parent_id"], "1")
        self.assertEqual(by_id["4"]["parent_id"], "3")

    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("liteparse.LiteParse")
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.default_storage.open")
    def test_heading_detection_disabled(
        self,
        mock_open,
        mock_liteparse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
    ):
        """With detection off, every line is a flat Text Block with no parent."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        result = make_result(
            pages=[
                make_page(
                    1,
                    612,
                    792,
                    "doc",
                    [
                        make_item("Big Title", 72, 40, 400, 30, font_size=24),
                        make_item("body", 72, 130, 300, 14, font_size=11),
                    ],
                )
            ],
            text="doc",
        )
        mock_parser = MagicMock()
        mock_parser.parse.return_value = result
        mock_liteparse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(1, 3)
        mock_find_tokens.return_value = []
        mock_extract_images.return_value = {}

        parser = patch_parser_settings(LiteParseParser(), detect_headings=False)
        out = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        annos = out["labelled_text"]
        self.assertEqual(len(annos), 2)
        for a in annos:
            self.assertEqual(a["annotationLabel"], LABEL_TEXT_BLOCK)
            self.assertIsNone(a["parent_id"])

    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("liteparse.LiteParse")
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.default_storage.open")
    def test_detect_headings_disabled_via_call_kwarg(
        self,
        mock_open,
        mock_liteparse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
    ):
        """A detect_headings=False call-time kwarg overrides the instance setting.

        Regression guard: the instance is configured with detect_headings=True,
        but the per-call kwarg must win and produce flat Text Blocks.
        """
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        result = make_result(
            pages=[
                make_page(
                    1,
                    612,
                    792,
                    "doc",
                    [
                        make_item("Big Title", 72, 40, 400, 30, font_size=24),
                        make_item("body", 72, 130, 300, 14, font_size=11),
                    ],
                )
            ],
            text="doc",
        )
        mock_parser = MagicMock()
        mock_parser.parse.return_value = result
        mock_liteparse_class.return_value = mock_parser

        mock_extract_tokens.return_value = create_mock_token_extraction_result(1, 3)
        mock_find_tokens.return_value = []
        mock_extract_images.return_value = {}

        # Instance setting leaves detection ON; the call kwarg turns it OFF.
        parser = patch_parser_settings(LiteParseParser(), detect_headings=True)
        out = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            detect_headings=False,
        )

        annos = out["labelled_text"]
        self.assertEqual(len(annos), 2)
        for a in annos:
            self.assertEqual(a["annotationLabel"], LABEL_TEXT_BLOCK)
            self.assertIsNone(a["parent_id"])

    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("liteparse.LiteParse")
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.default_storage.open")
    def test_image_extraction_creates_image_annotations(
        self,
        mock_open,
        mock_liteparse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
    ):
        """Embedded images become unified tokens + Image annotations."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        result = make_result(
            pages=[
                make_page(
                    1,
                    612,
                    792,
                    "page",
                    [make_item("caption", 72, 500, 200, 14, font_size=11)],
                )
            ],
            text="page",
        )
        mock_parser = MagicMock()
        mock_parser.parse.return_value = result
        mock_liteparse_class.return_value = mock_parser

        # pdfplumber word tokens (5) -> image token will be appended at index 5.
        mock_extract_tokens.return_value = create_mock_token_extraction_result(1, 5)
        mock_find_tokens.return_value = []
        mock_extract_images.return_value = {
            0: [
                {
                    "x": 100,
                    "y": 200,
                    "width": 300,
                    "height": 250,
                    "text": "",
                    "is_image": True,
                    "format": "jpeg",
                    "image_path": "documents/1/images/page_0_img_0.jpg",
                    "content_hash": "abc123",
                }
            ]
        }

        parser = patch_parser_settings(LiteParseParser())
        out = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # Image token appended to the unified tokens array.
        tokens = out["pawls_file_content"][0]["tokens"]
        self.assertEqual(len(tokens), 6)
        self.assertTrue(tokens[5].get("is_image"))

        # One text annotation + one Image annotation.
        image_annos = [
            a for a in out["labelled_text"] if a["annotationLabel"] == "Image"
        ]
        self.assertEqual(len(image_annos), 1)
        img = image_annos[0]
        self.assertIn("IMAGE", img.get("content_modalities", []))
        ref = img["annotation_json"]["0"]["tokensJsons"][0]
        self.assertEqual(ref, {"pageIndex": 0, "tokenIndex": 5})

    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.find_tokens_in_bbox")
    @patch(
        "opencontractserver.pipeline.parsers.liteparse_parser.extract_pawls_tokens_from_pdf"
    )
    @patch("liteparse.LiteParse")
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.default_storage.open")
    def test_kwargs_override_settings(
        self,
        mock_open,
        mock_liteparse_class,
        mock_extract_tokens,
        mock_find_tokens,
        mock_extract_images,
    ):
        """Call-time kwargs flow into the LiteParse constructor."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_parser = MagicMock()
        mock_parser.parse.return_value = make_result(
            pages=[make_page(1, 612, 792, "x", [])], text="x"
        )
        mock_liteparse_class.return_value = mock_parser
        mock_extract_tokens.return_value = create_mock_token_extraction_result(1, 0)
        mock_find_tokens.return_value = []
        mock_extract_images.return_value = {}

        parser = patch_parser_settings(LiteParseParser())
        parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            output_format="text",
            ocr_enabled=True,
        )

        mock_liteparse_class.assert_called_once()
        call_kwargs = mock_liteparse_class.call_args.kwargs
        self.assertEqual(call_kwargs["output_format"], "text")
        self.assertEqual(call_kwargs["ocr_enabled"], True)
        # parse() received the raw PDF bytes (no temp file).
        mock_parser.parse.assert_called_once_with(b"mock pdf content")

    @patch("liteparse.LiteParse")
    @patch("opencontractserver.pipeline.parsers.liteparse_parser.default_storage.open")
    def test_parse_empty_result(self, mock_open, mock_liteparse_class):
        """A result with no pages yields None."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_parser = MagicMock()
        mock_parser.parse.return_value = make_result(pages=[], text="")
        mock_liteparse_class.return_value = mock_parser

        parser = patch_parser_settings(LiteParseParser())
        self.assertIsNone(
            parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)
        )

    def test_parse_nonexistent_document(self):
        parser = patch_parser_settings(LiteParseParser())
        self.assertIsNone(parser.parse_document(user_id=self.user.id, doc_id=999999))

    def test_parse_no_pdf_file(self):
        doc = Document.objects.create(
            title="No PDF", description="", file_type="pdf", creator=self.user
        )
        parser = patch_parser_settings(LiteParseParser())
        self.assertIsNone(parser.parse_document(user_id=self.user.id, doc_id=doc.id))

    @patch("opencontractserver.pipeline.parsers.liteparse_parser.default_storage.open")
    def test_import_error_returns_none(self, mock_open):
        """A missing liteparse install degrades to None, not a crash."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        original = sys.modules.get("liteparse")
        # Force `from liteparse import LiteParse` to raise ImportError.
        sys.modules["liteparse"] = None  # type: ignore[assignment]
        try:
            parser = patch_parser_settings(LiteParseParser())
            self.assertIsNone(
                parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)
            )
        finally:
            if original is not None:
                sys.modules["liteparse"] = original
            else:
                sys.modules.pop("liteparse", None)


class TestLiteParseHeuristics(TestCase):
    """Unit tests for the font-size / bbox helpers (no DB or parse needed)."""

    def setUp(self):
        self.parser = patch_parser_settings(LiteParseParser())

    def test_classify_heading_sizes_tie_breaks_to_smaller_body(self):
        """When body and a heading size tie on frequency, body is the smaller."""
        pages = [
            make_page(
                1,
                612,
                792,
                "x",
                [
                    make_item("a", 0, 0, 1, 1, font_size=16),
                    make_item("b", 0, 0, 1, 1, font_size=16),
                    make_item("c", 0, 0, 1, 1, font_size=11),
                    make_item("d", 0, 0, 1, 1, font_size=11),
                    make_item("e", 0, 0, 1, 1, font_size=24),
                ],
            )
        ]
        heading_sizes, body_size = self.parser._classify_heading_sizes(pages)
        self.assertEqual(body_size, 11.0)
        # 16 and 24 both exceed 11 * 1.2 = 13.2; sorted descending.
        self.assertEqual(heading_sizes, [24.0, 16.0])

    def test_classify_heading_sizes_no_fonts_returns_empty(self):
        pages = [
            make_page(1, 612, 792, "x", [make_item("a", 0, 0, 1, 1, font_size=None)])
        ]
        heading_sizes, body_size = self.parser._classify_heading_sizes(pages)
        self.assertEqual(heading_sizes, [])
        self.assertIsNone(body_size)

    def test_classify_item_levels(self):
        heading_sizes = [24.0, 16.0]
        level, label = self.parser._classify_item(
            make_item("t", 0, 0, 1, 1, font_size=24), heading_sizes
        )
        self.assertEqual((level, label), (0, LABEL_TITLE))

        level, label = self.parser._classify_item(
            make_item("s", 0, 0, 1, 1, font_size=16), heading_sizes
        )
        self.assertEqual((level, label), (1, LABEL_SECTION_HEADER))

        level, label = self.parser._classify_item(
            make_item("b", 0, 0, 1, 1, font_size=11), heading_sizes
        )
        self.assertEqual((level, label), (None, LABEL_TEXT_BLOCK))

    def test_bounds_from_item_clamps_to_page(self):
        bounds = LiteParseParser._bounds_from_item(
            make_item("x", -10, -5, 1000, 2000), 612, 792
        )
        self.assertGreaterEqual(bounds["left"], 0)
        self.assertGreaterEqual(bounds["top"], 0)
        self.assertLessEqual(bounds["right"], 612)
        self.assertLessEqual(bounds["bottom"], 792)

    def test_bounds_from_item_absolute_coordinates(self):
        bounds = LiteParseParser._bounds_from_item(
            make_item("x", 72, 100, 200, 14), 612, 792
        )
        self.assertEqual(bounds["left"], 72)
        self.assertEqual(bounds["top"], 100)
        self.assertEqual(bounds["right"], 272)
        self.assertEqual(bounds["bottom"], 114)

    def test_bounds_from_item_at_page_edge_stays_nondegenerate(self):
        """An item pinned to the page edge still yields a >=1pt box."""
        # Zero-size item whose origin is exactly the bottom-right corner.
        bounds = LiteParseParser._bounds_from_item(
            make_item("x", 612, 792, 0, 0), 612, 792
        )
        self.assertGreaterEqual(bounds["right"] - bounds["left"], 1)
        self.assertGreaterEqual(bounds["bottom"] - bounds["top"], 1)
        # Expansion happens inward, staying within the page.
        self.assertLessEqual(bounds["right"], 612)
        self.assertLessEqual(bounds["bottom"], 792)
        self.assertGreaterEqual(bounds["left"], 0)
        self.assertGreaterEqual(bounds["top"], 0)

    def test_create_annotation_with_parent(self):
        bounds: BoundingBoxPythonType = {
            "left": 10,
            "top": 10,
            "right": 50,
            "bottom": 30,
        }
        annotation = self.parser._create_annotation(
            annotation_id="5",
            label=LABEL_TEXT_BLOCK,
            raw_text="hello",
            page_idx=0,
            bounds=bounds,
            token_refs=[{"pageIndex": 0, "tokenIndex": 0}],
            has_text_tokens=True,
            parent_id="2",
        )
        self.assertEqual(annotation["parent_id"], "2")
        self.assertEqual(annotation["structural"], True)
        self.assertIn("TEXT", annotation["content_modalities"])
        self.assertEqual(
            annotation["annotation_json"]["0"]["tokensJsons"],
            [{"pageIndex": 0, "tokenIndex": 0}],
        )


class TestLiteParseConfiguration(TestCase):
    """Configuration is read from the Settings dataclass."""

    def test_default_configuration(self):
        parser = patch_parser_settings(LiteParseParser())
        self.assertEqual(parser.output_format, "markdown")
        self.assertTrue(parser.detect_headings)
        self.assertEqual(parser.heading_size_ratio, 1.2)
        self.assertTrue(parser.extract_images)

    def test_custom_configuration(self):
        parser = patch_parser_settings(
            LiteParseParser(),
            output_format="json",
            detect_headings=False,
            heading_size_ratio=1.5,
            ocr_enabled=True,
        )
        self.assertEqual(parser.output_format, "json")
        self.assertFalse(parser.detect_headings)
        self.assertEqual(parser.heading_size_ratio, 1.5)
        self.assertTrue(parser.ocr_enabled)

    def test_registered_in_pipeline_registry(self):
        """The parser auto-registers and is PDF-capable."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        names = {p.name for p in registry.parsers}
        self.assertIn("LiteParseParser", names)
        pdf_parsers = {p.name for p in registry.get_parsers_for_filetype("pdf")}
        self.assertIn("LiteParseParser", pdf_parsers)
