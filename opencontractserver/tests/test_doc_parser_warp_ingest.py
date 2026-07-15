"""Unit tests for the Warp-Ingest REST parser.

Mirrors the DoclingParser REST tests: the HTTP call is mocked so the tests
exercise request construction, response extraction and error classification
without a running Warp-Ingest microservice. An end-to-end smoke test against
the real ``ghcr.io/open-source-legal/warp-ingest`` container lives in
``docs/test_scripts/warp_ingest_parser_smoke_test.md``.
"""

import json
import threading
from typing import cast
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.parsers.warp_ingest_parser import (
    WARP_INGEST_API_KEY_HEADER,
    WarpIngestParser,
)
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.types.enums import LabelType

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

        # The configured request timeout is forwarded to requests.post.
        self.assertEqual(kwargs["timeout"], self.parser.request_timeout)

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
    def test_disable_ocr_and_include_images_overrides(self, mock_open, mock_post):
        """disable_ocr / include_images passed at call time reach the query params."""
        self._mock_storage(mock_open)
        mock_post.return_value = MockResponse(200, _sample_response())

        self.parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            disable_ocr=True,
            include_images=True,
        )

        params = mock_post.call_args.kwargs["params"]
        self.assertEqual(params["disable_ocr"], "true")
        self.assertEqual(params["include_images"], "true")

    @patch(
        "opencontractserver.pipeline.parsers.warp_ingest_parser.maybe_add_cloud_run_auth"
    )
    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_cloud_run_iam_auth_header_path(self, mock_open, mock_post, mock_auth):
        """use_cloud_run_iam_auth forwards force=True and its Authorization header."""
        self._mock_storage(mock_open)
        mock_post.return_value = MockResponse(200, _sample_response())
        self.parser.use_cloud_run_iam_auth = True
        self.parser.api_key = "k"
        mock_auth.side_effect = lambda url, headers, force: {
            **headers,
            "Authorization": "Bearer id-token",
        }

        self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        # maybe_add_cloud_run_auth called with the service URL and force flag.
        self.assertEqual(mock_auth.call_args.kwargs.get("force"), True)
        sent_headers = mock_post.call_args.kwargs["headers"]
        self.assertEqual(sent_headers["Authorization"], "Bearer id-token")
        # API key still rides on its own header alongside the IAM bearer.
        self.assertEqual(sent_headers[WARP_INGEST_API_KEY_HEADER], "k")

    @patch(_POST_PATH)
    @patch(_STORAGE_PATH)
    def test_secret_api_key_redacted_in_logs(self, mock_open, mock_post):
        """The api_key secret must not appear in the base parser's INFO log line."""
        self._mock_storage(mock_open)
        mock_post.return_value = MockResponse(200, _sample_response())

        # Simulate the DB returning the decrypted secret among component settings
        # (patch.object avoids a mypy method-assign error on the instance).
        with patch.object(
            self.parser,
            "get_component_settings",
            return_value={"api_key": "super-secret-key-xyz", "apply_ocr": False},
        ), self.assertLogs(
            "opencontractserver.pipeline.base.parser", level="INFO"
        ) as cm:
            self.parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)

        joined = "\n".join(cm.output)
        self.assertNotIn("super-secret-key-xyz", joined)
        self.assertIn("***", joined)

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


def _sample_export_with_relationships():
    """A Warp-Ingest-shaped export with 2 structural annotations + 1 relationship.

    Uses the real Warp-Ingest field shape (camelCase ``annotationLabel``/
    ``rawText``, page-keyed ``annotation_json`` with ``bounds``/``tokensJsons``,
    ``parent_id`` heading link, ``relationshipLabel`` + ``*_annotation_ids``) so
    the import path is exercised against the actual export contract.
    """
    return {
        "title": "Warp Doc",
        "content": "Title\nBody",
        "description": None,
        "pawls_file_content": [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 60, "height": 18, "text": "Title"},
                    {"x": 100, "y": 130, "width": 90, "height": 18, "text": "Body"},
                ],
            }
        ],
        "page_count": 1,
        "doc_labels": [],
        "labelled_text": [
            {
                "id": "a1",
                "annotationLabel": "Section Header",
                "rawText": "Title",
                "page": 0,
                "annotation_json": {
                    "0": {
                        "bounds": {
                            "left": 100,
                            "top": 100,
                            "right": 160,
                            "bottom": 118,
                        },
                        "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                        "rawText": "Title",
                    }
                },
                "parent_id": None,
                "annotation_type": "TOKEN_LABEL",
                "structural": True,
                "content_modalities": ["TEXT"],
            },
            {
                "id": "a2",
                "annotationLabel": "Paragraph",
                "rawText": "Body",
                "page": 0,
                "annotation_json": {
                    "0": {
                        "bounds": {
                            "left": 100,
                            "top": 130,
                            "right": 190,
                            "bottom": 148,
                        },
                        "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                        "rawText": "Body",
                    }
                },
                "parent_id": "a1",
                "annotation_type": "TOKEN_LABEL",
                "structural": True,
                "content_modalities": ["TEXT"],
            },
        ],
        "relationships": [
            {
                "id": "r1",
                "relationshipLabel": "warpRefersTo",
                "source_annotation_ids": ["a1"],
                "target_annotation_ids": ["a2"],
                "structural": True,
            }
        ],
    }


class TestWarpIngestSaveParsedDataIntegration(TestCase):
    """Lock the "no key normalization" design claim in CI.

    A Warp-Ingest-shaped export flows through ``save_parsed_data`` →
    ``import_annotations`` / ``import_relationships`` and creates the expected DB
    rows without any key remapping — so an upstream schema drift (or a change to
    the OpenContracts importer) that breaks this compatibility is caught here
    rather than only by the manual smoke test
    (``docs/test_scripts/warp_ingest_parser_smoke_test.md``).
    """

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="warp_save", password="pw12345678"
            )
        self.doc = Document.objects.create(
            title="Warp Save Doc", file_type="pdf", creator=self.user
        )
        self.doc.pdf_file.save("s.pdf", ContentFile(b"%PDF-1.7\n%%EOF\n"))

    def test_warp_export_imports_without_normalization(self):
        WarpIngestParser().save_parsed_data(
            user_id=self.user.id,
            doc_id=self.doc.id,
            open_contracts_data=cast(
                OpenContractDocExport, _sample_export_with_relationships()
            ),
        )

        # Both structural annotations imported verbatim (camelCase keys, no remap).
        self.assertEqual(Annotation.objects.count(), 2)
        parent = Annotation.objects.get(raw_text="Title")
        child = Annotation.objects.get(raw_text="Body")
        self.assertTrue(child.structural)
        # parent_id heading link survives the import.
        self.assertEqual(child.parent, parent)
        # The relationship imported (subtree-group materialization may add more,
        # so assert our specific labelled relationship exists rather than a count).
        self.assertTrue(
            Relationship.objects.filter(
                relationship_label__text="warpRefersTo"
            ).exists()
        )

    def test_warp_export_reuses_labels_in_target_corpus(self):
        """Corpus ingestion must not create one structural label per document."""
        corpus = Corpus.objects.create(title="Warp Corpus", creator=self.user)
        second_doc = Document.objects.create(
            title="Second Warp Save Doc", file_type="pdf", creator=self.user
        )
        second_doc.pdf_file.save("second.pdf", ContentFile(b"%PDF-1.7\n%%EOF\n"))

        parser = WarpIngestParser()
        export = cast(OpenContractDocExport, _sample_export_with_relationships())
        for document in (self.doc, second_doc):
            parser.save_parsed_data(
                user_id=self.user.id,
                doc_id=document.id,
                open_contracts_data=export,
                corpus_id=corpus.id,
            )

        corpus.refresh_from_db()
        assert corpus.label_set is not None
        labels = corpus.label_set.annotation_labels.filter(
            text__in=["Section Header", "Paragraph", "warpRefersTo"]
        )
        text_label_type = settings.ANNOTATION_LABELS.get(
            self.doc.file_type, "SPAN_LABEL"
        )
        self.assertEqual(labels.count(), 3)
        self.assertEqual(
            labels.filter(text="Section Header", label_type=text_label_type).count(), 1
        )
        self.assertEqual(
            labels.filter(text="Paragraph", label_type=text_label_type).count(), 1
        )
        self.assertEqual(
            labels.filter(text="warpRefersTo", label_type=RELATIONSHIP_LABEL).count(),
            1,
        )


class CorpusParserLabelConcurrencyTests(TransactionTestCase):
    """The corpus/label-set locks must converge concurrent parser workers."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="parser_label_race", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="Parser Label Race Corpus", creator=self.user
        )

    def test_concurrent_creation_reuses_one_label_and_label_set(self) -> None:
        barrier = threading.Barrier(2)
        errors: list[Exception] = []
        label_ids: list[int] = []

        def create_label() -> None:
            close_old_connections()
            try:
                corpus = Corpus.objects.get(pk=self.corpus.pk)
                barrier.wait(timeout=10)
                label = corpus.ensure_labels_and_labelset(
                    label_data={
                        "Parser Race Label": {
                            "label_type": TOKEN_LABEL,
                            "color": "grey",
                            "description": "Parser Structural Label",
                            "icon": "expand",
                            "read_only": True,
                        }
                    },
                    creator_id=self.user.id,
                )["Parser Race Label"]
                label_ids.append(label.id)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)
            finally:
                close_old_connections()

        workers = [threading.Thread(target=create_label) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=20)

        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertFalse(errors, errors)
        self.assertEqual(len(label_ids), 2)
        self.assertEqual(len(set(label_ids)), 1)
        self.assertEqual(
            AnnotationLabel.objects.filter(
                text="Parser Race Label", label_type=TOKEN_LABEL
            ).count(),
            1,
        )
        self.corpus.refresh_from_db()
        assert self.corpus.label_set is not None
        self.assertEqual(
            self.corpus.label_set.annotation_labels.filter(
                text="Parser Race Label", label_type=TOKEN_LABEL
            ).count(),
            1,
        )

    def test_single_label_helper_accepts_label_type_enum(self) -> None:
        label = self.corpus.ensure_label_and_labelset(
            label_text="Parser Relationship",
            creator_id=self.user.id,
            label_type=LabelType.RELATIONSHIP_LABEL,
        )

        self.assertEqual(label.label_type, RELATIONSHIP_LABEL)
