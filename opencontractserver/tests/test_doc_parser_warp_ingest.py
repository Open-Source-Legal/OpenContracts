"""Unit tests for the Warp-Ingest REST parser.

Mirrors the DoclingParser REST tests: the HTTP call is mocked so the tests
exercise request construction, response extraction and error classification
without a running Warp-Ingest microservice. An end-to-end smoke test against
the real ``ghcr.io/open-source-legal/warp-ingest`` container lives in
``docs/test_scripts/warp_ingest_parser_smoke_test.md``.
"""

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.parsers.warp_ingest_parser import (
    WARP_INGEST_API_KEY_HEADER,
    WarpIngestParser,
)

User = get_user_model()

_POST_PATH = "opencontractserver.pipeline.parsers.warp_ingest_parser.requests.post"
_STORAGE_PATH = (
    "opencontractserver.pipeline.parsers.warp_ingest_parser.default_storage.open"
)
_STORAGE_SIZE_PATH = (
    "opencontractserver.pipeline.parsers.warp_ingest_parser.default_storage.size"
)


class MockResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self.json_data = json_data
        self.text = json.dumps(json_data)

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP Error: {self.status_code}")


def _sample_export():
    """A realistic OpenContractDocExport as returned under response['result']."""
    return {
        "title": "Test Document",
        "content": "Sample document content",
        "description": "Test Description",
        "pawls_file_content": [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 20, "text": "Sample"}
                ],
            }
        ],
        "page_count": 1,
        "doc_labels": [],
        "labelled_text": [
            {
                "id": "text-1",
                "annotationLabel": "Paragraph",
                "rawText": "Sample document content",
                "page": 0,
                "annotation_json": {
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
        "file_type": "application/pdf",
    }


def _sample_response():
    """The full Warp-Ingest envelope wrapping the export under 'result'."""
    return {"page_dim": [[612, 792]], "num_pages": 1, "result": _sample_export()}


class TestWarpIngestParser(TestCase):
    """Tests for the WarpIngestParser class."""

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(username="warp", password="12345678")

        self.doc = Document.objects.create(
            title="Test Document",
            description="Test Description",
            file_type="pdf",
            creator=self.user,
        )
        pdf_content = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog>>\nendobj\n%%EOF\n"
        self.doc.pdf_file.save("test.pdf", ContentFile(pdf_content))

        self.parser = WarpIngestParser()

    def _mock_storage(self, mock_open):
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock pdf content"
        mock_open.return_value.__enter__.return_value = mock_file

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_parse_document_success(self, mock_open, mock_post):
        """A successful parse returns the export from response['result']."""
        self._mock_storage(mock_open)
        mock_post.return_value = MockResponse(200, _sample_response())

        result = self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertIsNotNone(result)
        assert result is not None
        # The 'result' payload is unwrapped and returned verbatim.
        self.assertEqual(result["title"], "Test Document")
        self.assertEqual(result["content"], "Sample document content")
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(len(result["labelled_text"]), 1)
        self.assertEqual(result["labelled_text"][0]["annotationLabel"], "Paragraph")

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_request_is_built_correctly(self, mock_open, mock_post):
        """The multipart request carries the right params, file field and headers."""
        self._mock_storage(mock_open)
        mock_post.return_value = MockResponse(200, _sample_response())
        self.parser.api_key = "test-key"

        self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs

        # Query params: opencontracts render format + lowercase bool strings.
        params = kwargs["params"]
        self.assertEqual(params["render_format"], "opencontracts")
        self.assertEqual(params["apply_ocr"], "false")
        self.assertEqual(params["disable_ocr"], "false")
        self.assertEqual(params["semantic_units"], "false")
        self.assertEqual(params["include_images"], "false")

        # Multipart file field named "file" with an explicit PDF content type.
        files = kwargs["files"]
        self.assertIn("file", files)
        filename, _payload, content_type = files["file"]
        self.assertTrue(filename.lower().endswith(".pdf"))
        self.assertEqual(content_type, "application/pdf")

        # API key rides on X-API-Key (not Authorization), leaving Authorization
        # free for a Cloud Run IAM id_token.
        self.assertEqual(kwargs["headers"][WARP_INGEST_API_KEY_HEADER], "test-key")

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_no_api_key_header_when_unset(self, mock_open, mock_post):
        """No X-API-Key header is sent when the api_key setting is blank."""
        self._mock_storage(mock_open)
        mock_post.return_value = MockResponse(200, _sample_response())
        self.parser.api_key = ""

        self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        headers = mock_post.call_args.kwargs["headers"]
        self.assertNotIn(WARP_INGEST_API_KEY_HEADER, headers)

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_call_time_override_flags(self, mock_open, mock_post):
        """apply_ocr / semantic_units passed at call time override the settings."""
        self._mock_storage(mock_open)
        mock_post.return_value = MockResponse(200, _sample_response())

        self.parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            apply_ocr=True,
            semantic_units=True,
        )

        params = mock_post.call_args.kwargs["params"]
        self.assertEqual(params["apply_ocr"], "true")
        self.assertEqual(params["semantic_units"], "true")

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_mutually_exclusive_ocr_flags(self, mock_open, mock_post):
        """apply_ocr + disable_ocr both true fails fast without an HTTP call."""
        self._mock_storage(mock_open)

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(
                user_id=self.user.id,
                doc_id=self.doc.id,
                apply_ocr=True,
                disable_ocr=True,
            )

        self.assertFalse(ctx.exception.is_transient)
        mock_post.assert_not_called()

    def test_missing_pdf_file_raises_permanent(self):
        """A document with no stored file fails permanently (no retry)."""
        doc = Document.objects.create(
            title="No File", file_type="pdf", creator=self.user
        )
        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=doc.id)
        self.assertFalse(ctx.exception.is_transient)

    @patch(_POST_PATH)
    @patch(_STORAGE_SIZE_PATH)
    @patch(_STORAGE_PATH)
    def test_oversized_pdf_raises_permanent(self, mock_open, mock_size, mock_post):
        """A PDF over max_file_size_mb fails fast on the size metadata alone.

        The guard checks ``default_storage.size`` *before* reading the file, so
        an over-limit PDF is rejected without ever being opened/buffered.
        """
        mock_size.return_value = 2 * 1024 * 1024  # 2 MB (metadata only)
        self.parser.max_file_size_mb = 1  # cap below the 2 MB file

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertFalse(ctx.exception.is_transient)
        self.assertIn("MB", str(ctx.exception))
        mock_post.assert_not_called()
        mock_open.assert_not_called()  # never even read the file

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_malicious_title_sanitized_in_multipart_filename(
        self, mock_open, mock_post
    ):
        """CR/LF in document.title cannot leak into the multipart filename."""
        self._mock_storage(mock_open)
        mock_post.return_value = MockResponse(200, _sample_response())
        self.doc.title = "evil\r\nContent-Disposition: x"
        self.doc.save()

        self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        filename = mock_post.call_args.kwargs["files"]["file"][0]
        self.assertNotIn("\r", filename)
        self.assertNotIn("\n", filename)
        self.assertTrue(filename.lower().endswith(".pdf"))

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_timeout_is_transient(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.side_effect = Timeout()

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("timed out", str(ctx.exception))

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_connection_error_is_transient(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.side_effect = ConnectionError()

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("Failed to connect", str(ctx.exception))

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_4xx_is_not_transient(self, mock_open, mock_post):
        """4xx (e.g. 415 unsupported media type, 401 auth) is permanent."""
        self._mock_storage(mock_open)
        mock_response = MagicMock()
        mock_response.status_code = 415
        mock_response.text = "Unsupported Media Type"
        error = RequestException("Unsupported Media Type")
        error.response = mock_response
        mock_post.side_effect = error

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertFalse(ctx.exception.is_transient)

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_5xx_is_transient(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        error = RequestException("Service Unavailable")
        error.response = mock_response
        mock_post.side_effect = error

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_malformed_json_body_is_transient(self, mock_open, mock_post):
        """A 200 with a truncated/non-JSON body is a classified transient error."""
        self._mock_storage(mock_open)
        bad_response = MagicMock()
        bad_response.status_code = 200
        bad_response.raise_for_status = MagicMock()
        bad_response.json.side_effect = ValueError("Expecting value")
        mock_post.return_value = bad_response

        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("non-JSON", str(ctx.exception))


class TestWarpIngestExtractExport(TestCase):
    """Unit tests for the static response-extraction helper."""

    def test_reads_result_key(self):
        export = WarpIngestParser._extract_export(_sample_response(), doc_id=1)
        self.assertEqual(export["content"], "Sample document content")

    def test_falls_back_to_top_level_export(self):
        """If a future API returns the export unwrapped, it is still accepted."""
        export = WarpIngestParser._extract_export(_sample_export(), doc_id=1)
        self.assertEqual(export["content"], "Sample document content")

    def test_missing_payload_raises_permanent(self):
        with self.assertRaises(DocumentParsingError) as ctx:
            WarpIngestParser._extract_export({"page_dim": [], "num_pages": 0}, doc_id=1)
        self.assertFalse(ctx.exception.is_transient)

    def test_non_dict_response_raises_permanent(self):
        with self.assertRaises(DocumentParsingError) as ctx:
            WarpIngestParser._extract_export(["not", "a", "dict"], doc_id=1)
        self.assertFalse(ctx.exception.is_transient)


class TestWarpIngestSafeFilename(TestCase):
    """Unit tests for the multipart-filename sanitizer."""

    def test_plain_title_gets_pdf_suffix(self):
        self.assertEqual(
            WarpIngestParser._safe_pdf_filename("My Contract", 7), "My Contract.pdf"
        )

    def test_existing_pdf_suffix_preserved(self):
        self.assertEqual(
            WarpIngestParser._safe_pdf_filename("report.pdf", 7), "report.pdf"
        )

    def test_control_chars_and_separators_stripped(self):
        out = WarpIngestParser._safe_pdf_filename('a\r\nb/c\\d"e', 7)
        for bad in ("\r", "\n", "/", "\\", '"'):
            self.assertNotIn(bad, out)
        self.assertTrue(out.endswith(".pdf"))

    def test_empty_or_none_title_falls_back_to_doc_id(self):
        self.assertEqual(WarpIngestParser._safe_pdf_filename(None, 42), "doc_42.pdf")
        self.assertEqual(WarpIngestParser._safe_pdf_filename("   ", 42), "doc_42.pdf")


class TestWarpIngestParserSettings(TestCase):
    """The dataclass default timeout must agree with the shared constant."""

    def test_settings_request_timeout_matches_constant(self):
        from opencontractserver.constants.document_processing import (
            WARP_INGEST_PARSER_REQUEST_TIMEOUT_SECONDS,
        )

        self.assertEqual(
            WarpIngestParser.Settings().request_timeout,
            WARP_INGEST_PARSER_REQUEST_TIMEOUT_SECONDS,
        )

    def test_default_service_url_targets_parse_endpoint(self):
        self.assertTrue(WarpIngestParser.Settings().service_url.endswith("/api/parse"))

    def test_default_max_file_size_is_positive(self):
        self.assertGreater(WarpIngestParser.Settings().max_file_size_mb, 0)
