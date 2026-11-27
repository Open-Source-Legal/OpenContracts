"""Tests for the LiteParse (OCRia-nano) REST parser client.

The HTTP call is mocked with a real response recorded from the
``compose/liteparse`` service (``fixtures/liteparse/needs_ocr.json``), so these
tests exercise request construction, error classification and the full
parse → ``save_parsed_data`` path without a running service. The live
end-to-end check is ``docs/test_scripts/liteparse_parser_smoke_test.md``.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.annotations.models import Annotation
from opencontractserver.constants.document_processing import (
    LITEPARSE_API_KEY_HEADER,
)
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.parsers.liteparse_parser import LiteParseParser
from opencontractserver.pipeline.registry import get_registry

User = get_user_model()

_MODULE = "opencontractserver.pipeline.parsers.liteparse_parser"
_POST_PATH = f"{_MODULE}.requests.post"
_STORAGE_PATH = f"{_MODULE}.default_storage.open"
_STORAGE_SIZE_PATH = f"{_MODULE}.default_storage.size"

_FIXTURE = Path(__file__).parent / "fixtures" / "liteparse" / "needs_ocr.json"


def _fixture_payload() -> dict:
    with open(_FIXTURE) as f:
        return json.load(f)


def _ok_response(payload=None):
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = payload if payload is not None else _fixture_payload()
    return response


def _http_error(status_code: int) -> RequestException:
    response = MagicMock()
    response.status_code = status_code
    response.text = f"HTTP {status_code}"
    error = RequestException(f"HTTP {status_code}")
    error.response = response
    return error


class TestLiteParseParser(TestCase):
    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(username="lp", password="12345678")
        self.doc = Document.objects.create(
            title="Scanned Form", file_type="pdf", creator=self.user
        )
        self.doc.pdf_file.save("scan.pdf", ContentFile(b"%PDF-1.7\n%%EOF\n"))
        self.parser = LiteParseParser()

    def _mock_storage(self, mock_open):
        mock_file = MagicMock()
        mock_file.read.return_value = b"%PDF-1.7 mock"
        mock_open.return_value.__enter__.return_value = mock_file

    def _parse(self):
        return self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_parse_document_success_uses_fixture(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.return_value = _ok_response()
        self.parser.api_key = "k"

        result = self._parse()

        assert result is not None
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(len(result["pawls_file_content"]), 1)
        self.assertTrue(result["labelled_text"])
        self.assertEqual(result["title"], "Scanned Form")

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://liteparse:8000/parse")
        self.assertEqual(kwargs["headers"][LITEPARSE_API_KEY_HEADER], "k")
        filename, body, content_type = kwargs["files"]["file"]
        self.assertEqual(filename, "Scanned Form.pdf")
        self.assertEqual(body, b"%PDF-1.7 mock")
        self.assertEqual(content_type, "application/pdf")
        self.assertEqual(kwargs["timeout"], self.parser.request_timeout)

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_no_api_key_header_when_unset(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.return_value = _ok_response()
        self.parser.api_key = ""

        self._parse()

        self.assertNotIn(
            LITEPARSE_API_KEY_HEADER, mock_post.call_args.kwargs["headers"]
        )

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_timeout_transient(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.side_effect = Timeout()
        with self.assertRaises(DocumentParsingError) as ctx:
            self._parse()
        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("LiteParse parser service timed out", str(ctx.exception))

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_connection_error_transient(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.side_effect = ConnectionError()
        with self.assertRaises(DocumentParsingError) as ctx:
            self._parse()
        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("Failed to connect to LiteParse", str(ctx.exception))

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_415_permanent(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.side_effect = _http_error(415)
        with self.assertRaises(DocumentParsingError) as ctx:
            self._parse()
        self.assertFalse(ctx.exception.is_transient)

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_503_transient(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.side_effect = _http_error(503)
        with self.assertRaises(DocumentParsingError) as ctx:
            self._parse()
        self.assertTrue(ctx.exception.is_transient)

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_malformed_json_transient(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        response = _ok_response()
        response.json.side_effect = ValueError("Expecting value")
        mock_post.return_value = response
        with self.assertRaises(DocumentParsingError) as ctx:
            self._parse()
        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("non-JSON", str(ctx.exception))

    @patch(_POST_PATH)
    @patch(_STORAGE_SIZE_PATH)
    @patch(_STORAGE_PATH)
    def test_oversize_file_permanent(self, mock_open, mock_size, mock_post):
        mock_size.return_value = 300 * 1024 * 1024
        with self.assertRaises(DocumentParsingError) as ctx:
            self._parse()
        self.assertFalse(ctx.exception.is_transient)
        self.assertIn("MB", str(ctx.exception))
        mock_post.assert_not_called()
        mock_open.assert_not_called()

    def test_missing_file_permanent(self):
        doc = Document.objects.create(
            title="No File", file_type="pdf", creator=self.user
        )
        with self.assertRaises(DocumentParsingError) as ctx:
            self.parser.parse_document(user_id=self.user.id, doc_id=doc.id)
        self.assertFalse(ctx.exception.is_transient)

    @patch(_POST_PATH)
    def test_parse_pdf_bytes_needs_no_document(self, mock_post):
        mock_post.return_value = _ok_response()
        result = self.parser.parse_pdf_bytes(b"%PDF-1.7 x", title="", doc_id=0)
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(mock_post.call_args.kwargs["files"]["file"][0], "doc_0.pdf")

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_save_parsed_data_persists_hierarchy(self, mock_open, mock_post):
        self._mock_storage(mock_open)
        mock_post.return_value = _ok_response()

        export = self._parse()
        assert export is not None
        self.parser.save_parsed_data(
            user_id=self.user.id, doc_id=self.doc.id, open_contracts_data=export
        )

        self.assertEqual(Annotation.objects.count(), len(export["labelled_text"]))
        child = Annotation.objects.get(raw_text="Ondernemings- en vestigingsgegevens")
        self.assertTrue(child.structural)
        self.assertIsNotNone(child.parent)
        self.assertEqual(child.parent.raw_text, "KVK 14 Wijziging")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.page_count, 1)
        self.assertTrue(self.doc.pawls_parse_file.name)

    def test_registry_discovers_parser(self):
        matches = [
            d
            for d in get_registry().parsers
            if d.class_name.endswith("liteparse_parser.LiteParseParser")
        ]
        self.assertEqual(len(matches), 1)
        self.assertIn("pdf", matches[0].supported_file_types)
