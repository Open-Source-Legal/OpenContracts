import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.parsers.docling_parser_rest import DoclingParser
from opencontractserver.types.dicts import BoundingBoxPythonType

User = get_user_model()


class MockResponse:
    """Mock response object similar to requests.Response."""

    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self.json_data = json_data
        self.text = json.dumps(json_data)

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP Error: {self.status_code}")


class TestDoclingParser(TestCase):
    """Tests for the DoclingParser class."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(username="bob", password="12345678")

        # Create a sample Document object with a mock PDF file
        self.doc = Document.objects.create(
            title="Test Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )

        # Create a mock PDF file for the document
        pdf_content = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Count 1/Kids[3 0 R]>>\nendobj\n3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"  # noqa: E501
        self.doc.pdf_file.save("test.pdf", ContentFile(pdf_content))

        # Create an instance of DoclingParser
        self.parser = DoclingParser()
        self.parser.chunk_retry_limit = 0  # Disable per-chunk retries for unit tests

        # Sample response from the docling service
        self.sample_response = {
            "title": "Test Document",
            "content": "Sample document content",
            "description": "Test Description",
            "pawlsFileContent": [
                {
                    "page": {"width": 612, "height": 792, "index": 1},
                    "tokens": [
                        {
                            "x": 100,
                            "y": 100,
                            "width": 50,
                            "height": 20,
                            "text": "Sample",
                        }
                    ],
                }
            ],
            "pageCount": 1,
            "docLabels": [],
            "labelledText": [
                {
                    "id": "text-1",
                    "annotationLabel": "Paragraph",
                    "rawText": "Sample document content",
                    "page": 0,
                    "annotationJson": {
                        "0": {
                            "bounds": {
                                "left": 100,
                                "top": 100,
                                "right": 150,
                                "bottom": 120,
                            },
                            "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                            "rawText": "Sample document content",
                        }
                    },
                    "parent_id": None,
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                }
            ],
            "relationships": [],
        }

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_success(self, mock_open, mock_post, _mock_page_count):
        """Test successful document parsing."""
        # Mock the file reading
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock the HTTP response
        mock_post.return_value = MockResponse(200, self.sample_response)

        # Call the parse_document method
        result = self.parser.parse_document(user_id=1, doc_id=self.doc.id)

        # Check that the result is not None
        self.assertIsNotNone(result)
        assert result is not None

        # Check that the result contains expected keys
        self.assertEqual(result["title"], "Test Document")
        self.assertEqual(result["content"], "Sample document content")
        self.assertEqual(result["page_count"], 1)

        # Check that labelledText was normalized to labelled_text
        self.assertIn("labelled_text", result)
        self.assertEqual(len(result["labelled_text"]), 1)

        # Verify correct request was made
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["headers"]["Content-Type"], "application/json")

        # Verify payload has the correct structure
        payload = call_kwargs[
            "json"
        ]  # In requests.post, the json parameter is already a dict
        self.assertTrue(payload["filename"].endswith(".pdf"))
        self.assertIn("pdf_base64", payload)
        self.assertFalse(payload["force_ocr"])
        self.assertTrue(payload["roll_up_groups"])
        self.assertFalse(payload["llm_enhanced_hierarchy"])

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_service_error(self, mock_open, mock_post, _mock_page_count):
        """Test handling of service errors raises DocumentParsingError."""
        # Mock the file reading
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock an error response
        mock_post.return_value = MockResponse(500, {"detail": "Internal server error"})
        mock_post.return_value.raise_for_status = MagicMock(
            side_effect=Exception("500 Server Error")
        )

        # Call the parse_document method - should raise DocumentParsingError
        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=1, doc_id=self.doc.id)

        # Verify the error is marked as transient (server errors are transient)
        self.assertTrue(ctx.exception.is_transient)

    def test_custom_settings(self):
        """Test that custom settings are properly loaded from Settings dataclass."""
        from unittest.mock import MagicMock

        parser = DoclingParser()
        # Mock the Settings dataclass with a custom URL (simulating PipelineSettings DB)
        mock_settings = MagicMock()
        mock_settings.service_url = "http://custom-host:9000/parse/"
        mock_settings.request_timeout = 300
        mock_settings.use_cloud_run_iam_auth = False
        mock_settings.extract_images = True
        mock_settings.image_format = "jpeg"
        mock_settings.image_quality = 85
        mock_settings.image_dpi = 150
        mock_settings.min_image_width = 50
        mock_settings.min_image_height = 50
        parser._settings = mock_settings
        # Reinitialize from settings
        parser.service_url = parser._settings.service_url
        self.assertEqual(parser.service_url, "http://custom-host:9000/parse/")

    def test_normalize_response(self):
        """Test the response normalization function."""
        # Create a response with camelCase keys
        camel_case_response = {
            "title": "Test",
            "pawlsFileContent": [{"page": {"width": 100}}],
            "pageCount": 2,
            "docLabels": [],
            "labelledText": [{"id": "1"}],
        }

        # Normalize the response
        normalized = self.parser._normalize_response(camel_case_response)

        # Check that both camelCase and snake_case keys are present
        self.assertIn("pawlsFileContent", normalized)
        self.assertIn("pawls_file_content", normalized)
        self.assertIn("pageCount", normalized)
        self.assertIn("page_count", normalized)
        self.assertIn("docLabels", normalized)
        self.assertIn("doc_labels", normalized)
        self.assertIn("labelledText", normalized)
        self.assertIn("labelled_text", normalized)

        # Check values
        self.assertEqual(normalized["page_count"], 2)
        self.assertEqual(normalized["pawls_file_content"][0]["page"]["width"], 100)

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_timeout_error(self, mock_open, mock_post, _mock_page_count):
        """Parser raises DocumentParsingError when the Docling service call times out."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Simulate a timeout raised by requests.post
        mock_post.side_effect = Timeout()

        # Should raise DocumentParsingError with is_transient=True
        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=1, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("timed out", str(ctx.exception))
        mock_post.assert_called_once()  # Ensure we attempted a single request

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_connection_error(
        self, mock_open, mock_post, _mock_page_count
    ):
        """Parser raises DocumentParsingError when the Docling service is unreachable."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Simulate inability to connect to the service
        mock_post.side_effect = ConnectionError()

        # Should raise DocumentParsingError with is_transient=True
        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=1, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("Failed to connect", str(ctx.exception))
        mock_post.assert_called_once()

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_generic_request_exception(
        self, mock_open, mock_post, _mock_page_count
    ):
        """
        Parser raises DocumentParsingError when an unexpected RequestException is raised.
        Also verify that a response object attached to the exception is handled.
        """
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Create a mock response to attach to the exception
        mock_failed_response = MagicMock()
        mock_failed_response.text = "Upstream failure"
        mock_failed_response.status_code = None  # No status code for generic exception

        # Raise a generic RequestException that includes a response attribute
        mock_post.side_effect = RequestException(
            "Service blew up", response=mock_failed_response
        )

        # Should raise DocumentParsingError with is_transient=True (default for unknown errors)
        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=1, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)
        mock_post.assert_called_once()

    def test_maybe_add_cloud_run_auth_non_cloud_run_url(self):
        """Test that non-Cloud Run URLs return headers unchanged."""
        headers = {"Content-Type": "application/json"}
        result = DoclingParser._maybe_add_cloud_run_auth(
            "http://localhost:8000/parse", headers
        )
        # Should return original headers without Authorization
        self.assertEqual(result, headers)
        self.assertNotIn("Authorization", result)

    def test_maybe_add_cloud_run_auth_https_non_cloud_run(self):
        """Test that HTTPS URLs not ending in .run.app return headers unchanged."""
        headers = {"Content-Type": "application/json"}
        result = DoclingParser._maybe_add_cloud_run_auth(
            "https://example.com/parse", headers
        )
        # Should return original headers without Authorization
        self.assertEqual(result, headers)
        self.assertNotIn("Authorization", result)

    @patch("google.oauth2.id_token.fetch_id_token")
    @patch("google.auth.transport.requests.Request")
    def test_maybe_add_cloud_run_auth_success(
        self, mock_request_class, mock_fetch_id_token
    ):
        """Test successful Cloud Run auth token addition."""
        # Mock the google auth components
        mock_request_instance = MagicMock()
        mock_request_class.return_value = mock_request_instance
        mock_fetch_id_token.return_value = "fake_token_12345"

        headers = {"Content-Type": "application/json"}
        result = DoclingParser._maybe_add_cloud_run_auth(
            "https://my-service-abc123.run.app/parse", headers
        )

        # Should have Authorization header added
        self.assertIn("Authorization", result)
        self.assertEqual(result["Authorization"], "Bearer fake_token_12345")
        # Original headers should still be present
        self.assertEqual(result["Content-Type"], "application/json")
        # Verify the token was fetched with correct audience
        mock_fetch_id_token.assert_called_once_with(
            mock_request_instance, "https://my-service-abc123.run.app"
        )

    @patch("google.oauth2.id_token.fetch_id_token")
    @patch("google.auth.transport.requests.Request")
    def test_maybe_add_cloud_run_auth_token_is_none(
        self, mock_request_class, mock_fetch_id_token
    ):
        """Test handling when fetch_id_token returns None."""
        mock_request_instance = MagicMock()
        mock_request_class.return_value = mock_request_instance
        mock_fetch_id_token.return_value = None

        headers = {"Content-Type": "application/json"}
        result = DoclingParser._maybe_add_cloud_run_auth(
            "https://my-service-abc123.run.app/parse", headers
        )

        # Should return original headers without Authorization
        self.assertNotIn("Authorization", result)
        self.assertEqual(result["Content-Type"], "application/json")

    @patch("google.oauth2.id_token.fetch_id_token")
    @patch("google.auth.transport.requests.Request")
    def test_maybe_add_cloud_run_auth_import_error(
        self, mock_request_class, mock_fetch_id_token
    ):
        """Test handling when google auth libraries are not available."""
        # Simulate ImportError by making the import fail
        mock_request_class.side_effect = Exception("No module named 'google'")

        headers = {"Content-Type": "application/json"}
        result = DoclingParser._maybe_add_cloud_run_auth(
            "https://my-service-abc123.run.app/parse", headers
        )

        # Should return original headers without Authorization
        self.assertNotIn("Authorization", result)
        self.assertEqual(result["Content-Type"], "application/json")

    @patch("google.oauth2.id_token.fetch_id_token")
    @patch("google.auth.transport.requests.Request")
    def test_maybe_add_cloud_run_auth_force_flag(
        self, mock_request_class, mock_fetch_id_token
    ):
        """Test force flag adds auth even for non-Cloud Run URLs."""
        mock_request_instance = MagicMock()
        mock_request_class.return_value = mock_request_instance
        mock_fetch_id_token.return_value = "forced_token_999"

        headers = {"Content-Type": "application/json"}
        # Force auth on a non-Cloud Run URL
        result = DoclingParser._maybe_add_cloud_run_auth(
            "https://example.com/parse", headers, force=True
        )

        # Should have Authorization header added due to force flag
        self.assertIn("Authorization", result)
        self.assertEqual(result["Authorization"], "Bearer forced_token_999")
        # Verify the token was fetched with correct audience
        mock_fetch_id_token.assert_called_once_with(
            mock_request_instance, "https://example.com"
        )


class TestDoclingParserImageExtraction(TestCase):
    """Tests for image extraction features of DoclingParser."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="imgextract_user", password="testpass123"
            )

        self.doc = Document.objects.create(
            title="Image Test Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )

        pdf_content = (
            b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n%%EOF\n"
        )
        self.doc.pdf_file.save("test_img.pdf", ContentFile(pdf_content))

        self.parser = DoclingParser()
        self.parser.chunk_retry_limit = 0  # Disable per-chunk retries for unit tests

    def test_find_images_in_bounds_overlapping(self):
        """Test that _find_images_in_bounds finds overlapping image tokens."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 300,
            "bottom": 300,
        }

        # Image token that overlaps with bounds
        page_tokens = [
            {"x": 0, "y": 0, "width": 50, "height": 12, "text": "Text"},  # text
            {
                "x": 150,
                "y": 150,
                "width": 100,
                "height": 100,
                "text": "",
                "is_image": True,
            },  # image overlaps
            {
                "x": 500,
                "y": 500,
                "width": 50,
                "height": 50,
                "text": "",
                "is_image": True,
            },  # no overlap
        ]

        pawls_pages = [{"page": {"width": 612, "height": 792}, "tokens": page_tokens}]

        result = self.parser._find_images_in_bounds(
            bounds=bounds,
            page_idx=0,
            pawls_pages=pawls_pages,
            token_offset=1,  # Image tokens start at index 1
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pageIndex"], 0)
        self.assertEqual(result[0]["tokenIndex"], 1)

    def test_find_images_in_bounds_no_overlap(self):
        """Test that _find_images_in_bounds returns empty when no overlap."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 200,
            "bottom": 200,
        }

        page_tokens = [
            {"x": 0, "y": 0, "width": 50, "height": 12, "text": "Text"},
            {
                "x": 300,
                "y": 300,
                "width": 50,
                "height": 50,
                "text": "",
                "is_image": True,
            },
        ]
        pawls_pages = [{"page": {"width": 612, "height": 792}, "tokens": page_tokens}]

        result = self.parser._find_images_in_bounds(
            bounds=bounds,
            page_idx=0,
            pawls_pages=pawls_pages,
            token_offset=1,
        )

        self.assertEqual(len(result), 0)

    def test_find_images_in_bounds_empty_tokens(self):
        """Test that _find_images_in_bounds handles empty token list."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 200,
            "bottom": 200,
        }
        pawls_pages = [{"page": {"width": 612, "height": 792}, "tokens": []}]

        result = self.parser._find_images_in_bounds(
            bounds=bounds,
            page_idx=0,
            pawls_pages=pawls_pages,
            token_offset=0,
        )

        self.assertEqual(result, [])

    @patch(
        "opencontractserver.pipeline.parsers.docling_parser_rest.extract_images_from_pdf"
    )
    def test_add_images_to_result_with_images(self, mock_extract):
        """Test _add_images_to_result adds image tokens to PAWLs."""
        # Mock extract_images_from_pdf to return test images
        mock_extract.return_value = {
            0: [
                {
                    "x": 100,
                    "y": 250,
                    "width": 150,
                    "height": 100,
                    "text": "",
                    "is_image": True,
                    "format": "jpeg",
                    "original_width": 300,
                    "original_height": 200,
                    "content_hash": "abc123",
                    "image_type": "embedded",
                    "base64_data": "dGVzdA==",
                }
            ]
        }

        # Base result from docling service
        base_result = {
            "title": "Test",
            "content": "Test content",
            "pawls_file_content": [
                {
                    "page": {"width": 612, "height": 792, "index": 0},
                    "tokens": [
                        {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Text"}
                    ],
                }
            ],
            "labelled_text": [],
        }

        result = self.parser._add_images_to_result(
            result=base_result,
            pdf_bytes=b"fake pdf",
            storage_path="documents/1/images",
        )

        # Check image token was added
        self.assertEqual(len(result["pawls_file_content"][0]["tokens"]), 2)
        image_token = result["pawls_file_content"][0]["tokens"][1]
        self.assertTrue(image_token.get("is_image"))
        self.assertEqual(image_token["format"], "jpeg")

    @patch(
        "opencontractserver.pipeline.parsers.docling_parser_rest.extract_images_from_pdf"
    )
    def test_add_images_to_result_empty_images(self, mock_extract):
        """Test _add_images_to_result handles empty images gracefully."""
        # Mock extract_images_from_pdf to return empty dict
        mock_extract.return_value = {}

        base_result = {
            "title": "Test",
            "content": "Test content",
            "pawls_file_content": [
                {
                    "page": {"width": 612, "height": 792, "index": 0},
                    "tokens": [
                        {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Text"}
                    ],
                }
            ],
            "labelled_text": [],
        }

        result = self.parser._add_images_to_result(
            result=base_result,
            pdf_bytes=b"fake pdf",
            storage_path=None,
        )

        # Should be unchanged
        self.assertEqual(len(result["pawls_file_content"][0]["tokens"]), 1)

    @patch(
        "opencontractserver.pipeline.parsers.docling_parser_rest.crop_image_from_pdf"
    )
    def test_add_image_refs_to_annotation_with_crop(self, mock_crop):
        """Test _add_image_refs_to_annotation crops when no embedded image."""
        mock_crop.return_value = {
            "x": 100,
            "y": 200,
            "width": 200,
            "height": 150,
            "text": "",
            "is_image": True,
            "format": "jpeg",
            "original_width": 400,
            "original_height": 300,
            "content_hash": "cropped123",
            "image_type": "cropped",
            "base64_data": "Y3JvcHBlZA==",
        }

        annotation: dict = {
            "id": "figure-1",
            "annotationLabel": "Figure",
            "page": 0,
            "annotation_json": {
                "0": {
                    "bounds": {"left": 100, "top": 200, "right": 300, "bottom": 350},
                    "tokensJsons": [],
                }
            },
        }

        pawls_pages = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 50, "y": 50, "width": 100, "height": 20, "text": "Header"}
                ],
            }
        ]

        # No existing image tokens, so crop should be triggered
        image_token_offsets = {0: 1}  # Image tokens would start at index 1
        page_dims = {0: (612.0, 792.0)}

        self.parser._add_image_refs_to_annotation(
            annotation=annotation,
            pdf_bytes=b"fake pdf",
            image_token_offsets=image_token_offsets,
            page_dims=page_dims,
            pawls_pages=pawls_pages,
            storage_path="documents/1/images",
        )

        # crop_image_from_pdf should have been called
        mock_crop.assert_called_once()

        # Annotation should have image token reference
        token_refs = annotation["annotation_json"]["0"]["tokensJsons"]
        self.assertGreater(len(token_refs), 0)

    def test_add_image_refs_with_existing_image(self):
        """Test _add_image_refs_to_annotation uses existing overlapping image."""
        annotation: dict = {
            "id": "figure-1",
            "annotationLabel": "Figure",
            "page": 0,
            "annotation_json": {
                "0": {
                    "bounds": {"left": 100, "top": 200, "right": 300, "bottom": 350},
                    "tokensJsons": [],
                }
            },
        }

        # PAWLs with an existing image token that overlaps
        pawls_pages = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 50, "y": 50, "width": 100, "height": 20, "text": "Header"},
                    {
                        "x": 120,
                        "y": 220,
                        "width": 160,
                        "height": 100,
                        "text": "",
                        "is_image": True,
                        "format": "jpeg",
                    },
                ],
            }
        ]

        # Image token starts at index 1
        image_token_offsets = {0: 1}
        page_dims = {0: (612.0, 792.0)}

        self.parser._add_image_refs_to_annotation(
            annotation=annotation,
            pdf_bytes=b"fake pdf",
            image_token_offsets=image_token_offsets,
            page_dims=page_dims,
            pawls_pages=pawls_pages,
            storage_path=None,
        )

        # Annotation should have reference to existing image token
        token_refs = annotation["annotation_json"]["0"]["tokensJsons"]
        self.assertEqual(len(token_refs), 1)
        self.assertEqual(token_refs[0]["tokenIndex"], 1)

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch(
        "opencontractserver.pipeline.parsers.docling_parser_rest.extract_images_from_pdf"
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_with_extract_images(
        self, mock_open, mock_post, mock_extract_images, _mock_page_count
    ):
        """Test parse_document with extract_images=True."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Response with a Figure annotation
        response_with_figure = {
            "title": "Test Document",
            "content": "Content",
            "pawlsFileContent": [
                {
                    "page": {"width": 612, "height": 792, "index": 1},
                    "tokens": [
                        {"x": 100, "y": 100, "width": 50, "height": 20, "text": "Hi"}
                    ],
                }
            ],
            "pageCount": 1,
            "docLabels": [],
            "labelledText": [
                {
                    "id": "fig-1",
                    "annotationLabel": "Figure",
                    "rawText": "",
                    "page": 0,
                    "annotationJson": {
                        "0": {
                            "bounds": {
                                "left": 50,
                                "top": 200,
                                "right": 300,
                                "bottom": 400,
                            },
                            "tokensJsons": [],
                        }
                    },
                    "structural": True,
                }
            ],
            "relationships": [],
        }

        mock_post.return_value = MockResponse(200, response_with_figure)

        # Mock image extraction
        mock_extract_images.return_value = {
            0: [
                {
                    "x": 100,
                    "y": 250,
                    "width": 150,
                    "height": 100,
                    "text": "",
                    "is_image": True,
                    "format": "jpeg",
                    "content_hash": "abc123",
                    "image_type": "embedded",
                }
            ]
        }

        result = self.parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            extract_images=True,
        )

        self.assertIsNotNone(result)
        mock_extract_images.assert_called_once()

    def test_find_images_in_bounds_invalid_page_type(self):
        """Test _find_images_in_bounds handles non-dict page data."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 200,
            "bottom": 200,
        }
        # Page is not a dict
        pawls_pages: list = ["invalid page data"]

        result = self.parser._find_images_in_bounds(
            bounds=bounds,
            page_idx=0,
            pawls_pages=pawls_pages,
            token_offset=0,
        )

        self.assertEqual(result, [])

    def test_find_images_in_bounds_invalid_page_index(self):
        """Test _find_images_in_bounds handles out-of-range page index."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 200,
            "bottom": 200,
        }
        pawls_pages = [{"page": {"width": 612, "height": 792}, "tokens": []}]

        result = self.parser._find_images_in_bounds(
            bounds=bounds,
            page_idx=5,  # Out of range
            pawls_pages=pawls_pages,
            token_offset=0,
        )

        self.assertEqual(result, [])

    def test_find_images_in_bounds_token_offset_exceeds_length(self):
        """Test _find_images_in_bounds when token_offset exceeds token list."""
        bounds: BoundingBoxPythonType = {
            "left": 100,
            "top": 100,
            "right": 200,
            "bottom": 200,
        }
        page_tokens = [
            {"x": 0, "y": 0, "width": 50, "height": 12, "text": "Text"},
        ]
        pawls_pages = [{"page": {"width": 612, "height": 792}, "tokens": page_tokens}]

        result = self.parser._find_images_in_bounds(
            bounds=bounds,
            page_idx=0,
            pawls_pages=pawls_pages,
            token_offset=10,  # Exceeds token list length
        )

        self.assertEqual(result, [])

    def test_add_image_refs_to_annotation_empty_bounds(self):
        """Test _add_image_refs_to_annotation returns early when bounds is empty."""
        annotation: dict = {
            "id": "figure-1",
            "annotationLabel": "Figure",
            "page": 0,
            "annotation_json": {
                "0": {
                    "bounds": {},  # Empty bounds
                    "tokensJsons": [],
                }
            },
        }

        pawls_pages = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [],
            }
        ]

        # Should return early without modifying anything
        self.parser._add_image_refs_to_annotation(
            annotation=annotation,
            pdf_bytes=b"fake pdf",
            image_token_offsets={},
            page_dims={0: (612.0, 792.0)},
            pawls_pages=pawls_pages,
            storage_path=None,
        )

        # annotation_json should remain unchanged
        self.assertEqual(annotation["annotation_json"]["0"]["tokensJsons"], [])

    @patch(
        "opencontractserver.pipeline.parsers.docling_parser_rest.extract_images_from_pdf"
    )
    def test_add_images_to_result_exception_handling(self, mock_extract):
        """Test _add_images_to_result handles exceptions gracefully."""
        mock_extract.side_effect = Exception("Image extraction failed")

        base_result = {
            "title": "Test",
            "content": "Test content",
            "pawls_file_content": [
                {
                    "page": {"width": 612, "height": 792, "index": 0},
                    "tokens": [],
                }
            ],
            "labelled_text": [],
        }

        # Should not raise, just log warning and return result unchanged
        result = self.parser._add_images_to_result(
            result=base_result,
            pdf_bytes=b"fake pdf",
            storage_path=None,
        )

        self.assertEqual(result, base_result)

    @patch(
        "opencontractserver.pipeline.parsers.docling_parser_rest.extract_images_from_pdf"
    )
    def test_add_images_to_result_invalid_page_index(self, mock_extract):
        """Test _add_images_to_result handles invalid page index in images_by_page."""
        # Return images for a page that doesn't exist in pawls_pages
        mock_extract.return_value = {
            5: [  # Page index 5 doesn't exist
                {
                    "x": 100,
                    "y": 250,
                    "width": 150,
                    "height": 100,
                    "text": "",
                    "is_image": True,
                    "format": "jpeg",
                }
            ]
        }

        base_result = {
            "title": "Test",
            "pawls_file_content": [
                {
                    "page": {"width": 612, "height": 792, "index": 0},
                    "tokens": [],
                }
            ],
            "labelled_text": [],
        }

        # Should not raise, just skip invalid page
        result = self.parser._add_images_to_result(
            result=base_result,
            pdf_bytes=b"fake pdf",
            storage_path=None,
        )

        # Original result should be unchanged
        self.assertEqual(len(result["pawls_file_content"][0]["tokens"]), 0)


class TestDoclingParser4xxErrors(TestCase):
    """Tests for 4xx HTTP error handling (non-transient errors)."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="error4xx_user", password="testpass123"
            )

        self.doc = Document.objects.create(
            title="4xx Error Test Document",
            file_type="pdf",
            creator=self.user,
        )

        pdf_content = (
            b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n%%EOF\n"
        )
        self.doc.pdf_file.save("test_4xx.pdf", ContentFile(pdf_content))

        self.parser = DoclingParser()
        self.parser.chunk_retry_limit = 0  # Disable per-chunk retries for unit tests

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_400_error_not_transient(
        self, mock_open, mock_post, _mock_page_count
    ):
        """Test that 400 Bad Request is treated as non-transient error."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        # Create a RequestException with a 400 response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request: Invalid PDF format"

        error = RequestException("Bad Request")
        error.response = mock_response
        mock_post.side_effect = error

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # 4xx errors should NOT be transient
        self.assertFalse(ctx.exception.is_transient)

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_403_error_not_transient(
        self, mock_open, mock_post, _mock_page_count
    ):
        """Test that 403 Forbidden is treated as non-transient error."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden: Access denied"

        error = RequestException("Forbidden")
        error.response = mock_response
        mock_post.side_effect = error

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertFalse(ctx.exception.is_transient)

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_503_error_is_transient(
        self, mock_open, mock_post, _mock_page_count
    ):
        """Test that 503 Service Unavailable is treated as transient error."""
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"

        error = RequestException("Service Unavailable")
        error.response = mock_response
        mock_post.side_effect = error

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # 5xx errors should be transient
        self.assertTrue(ctx.exception.is_transient)
