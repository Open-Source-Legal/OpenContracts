"""Unit tests for the shared parser-service HTTP helpers.

These helpers back every REST parser client that posts a whole PDF to a
microservice (Warp-Ingest, LiteParse): error classification, JSON decoding
and multipart filename sanitizing.
"""

from unittest.mock import MagicMock

from django.test import SimpleTestCase
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.utils.parser_service_http import (
    decode_parser_service_json,
    parser_service_request_error,
    safe_pdf_filename,
)


def _http_error(status_code: int, text: str = "body") -> RequestException:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    error = RequestException(f"HTTP {status_code}")
    error.response = response
    return error


def _classify(error: RequestException):
    return parser_service_request_error(
        error,
        service_name="Acme",
        service_url="http://x/parse",
        timeout=30,
        doc_id=5,
    )


class TestParserServiceRequestError(SimpleTestCase):
    def test_timeout_is_transient_and_mentions_timeout(self):
        err = _classify(Timeout())
        self.assertTrue(err.is_transient)
        self.assertIn(
            "Request to Acme parser service timed out after 30s for document 5",
            str(err),
        )

    def test_connection_error_is_transient(self):
        err = _classify(ConnectionError())
        self.assertTrue(err.is_transient)
        self.assertIn(
            "Failed to connect to Acme parser service at http://x/parse for document 5",
            str(err),
        )

    def test_4xx_permanent_408_429_transient_5xx_transient(self):
        self.assertFalse(_classify(_http_error(415)).is_transient)
        self.assertTrue(_classify(_http_error(408)).is_transient)
        self.assertTrue(_classify(_http_error(429)).is_transient)
        self.assertTrue(_classify(_http_error(503)).is_transient)

    def test_status_and_truncated_body_in_message(self):
        err = _classify(_http_error(415, "x" * 600))
        message = str(err)
        self.assertIn("(status=415)", message)
        self.assertIn("Response: " + "x" * 500, message)
        self.assertNotIn("x" * 501, message)

    def test_request_exception_without_response_is_transient(self):
        err = _classify(RequestException("boom"))
        self.assertTrue(err.is_transient)
        self.assertIn("Request to Acme parser service failed for document 5", str(err))


class TestDecodeParserServiceJson(SimpleTestCase):
    def test_decode_returns_payload(self):
        response = MagicMock()
        response.json.return_value = {"ok": True}
        self.assertEqual(
            decode_parser_service_json(response, service_name="Acme", doc_id=5),
            {"ok": True},
        )

    def test_decode_non_json_is_transient(self):
        response = MagicMock()
        response.json.side_effect = ValueError("Expecting value")
        with self.assertRaises(DocumentParsingError) as ctx:
            decode_parser_service_json(response, service_name="Acme", doc_id=5)
        self.assertTrue(ctx.exception.is_transient)
        self.assertIn(
            "Acme returned a malformed (non-JSON) response for document 5",
            str(ctx.exception),
        )


class TestSafePdfFilename(SimpleTestCase):
    def test_plain_title_gets_pdf_suffix(self):
        self.assertEqual(safe_pdf_filename("My Contract", 7), "My Contract.pdf")

    def test_existing_pdf_suffix_preserved(self):
        self.assertEqual(safe_pdf_filename("report.pdf", 7), "report.pdf")

    def test_control_chars_and_separators_stripped(self):
        out = safe_pdf_filename('a\r\nb/c\\d"e', 7)
        for bad in ("\r", "\n", "/", "\\", '"'):
            self.assertNotIn(bad, out)
        self.assertTrue(out.endswith(".pdf"))

    def test_empty_or_none_title_falls_back_to_doc_id(self):
        self.assertEqual(safe_pdf_filename(None, 42), "doc_42.pdf")
        self.assertEqual(safe_pdf_filename("   ", 42), "doc_42.pdf")
