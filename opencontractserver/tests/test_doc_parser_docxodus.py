import io
import json
import zipfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from requests.exceptions import ConnectionError, Timeout

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.parsers.docxodus_parser import DocxodusServiceParser

User = get_user_model()


def make_minimal_docx() -> bytes:
    """Create a minimal valid DOCX file (ZIP with required XML entries)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '  # noqa: E501
            'Target="word/document.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            "<w:p><w:r><w:t>Hello World</w:t></w:r></w:p>"
            "</w:body>"
            "</w:document>",
        )
    return buf.getvalue()


class MockResponse:
    """Mock HTTP response for docxodus microservice."""

    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self.json_data = json_data
        self.text = json.dumps(json_data)

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests.exceptions import HTTPError

            resp = type(
                "Response",
                (),
                {"status_code": self.status_code, "text": self.text},
            )()
            raise HTTPError(response=resp)


class TestDocxodusServiceParser(TestCase):
    """Tests for the DocxodusServiceParser class."""

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="docxodus_tester", password="12345678"
            )

        self.doc = Document.objects.create(
            title="Test DOCX",
            description="Test Description",
            file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            creator=self.user,
        )

        docx_content = make_minimal_docx()
        self.doc.pdf_file.save("test.docx", ContentFile(docx_content))

        self.sample_response = {
            "title": "Test DOCX",
            "content": "Hello World",
            "pageCount": 1,
            "pawlsFileContent": [],
            "docLabels": [],
            "labelledText": [
                {
                    "id": "ann-1",
                    "annotationLabel": "PARAGRAPH",
                    "rawText": "Hello World",
                    "page": 0,
                    "annotationJson": {"start": 0, "end": 11},
                    "structural": True,
                    "annotationType": "text",
                    "parentId": None,
                }
            ],
            "relationships": [],
        }

    @patch("opencontractserver.pipeline.parsers.docxodus_parser.requests.post")
    def test_parse_document_success(self, mock_post):
        """Test successful DOCX parsing via the microservice."""
        mock_post.return_value = MockResponse(200, self.sample_response)

        parser = DocxodusServiceParser()
        parser.service_url = "http://docxodus-parser:8080/parse"
        parser.request_timeout = 30

        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["content"], "Hello World")
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(len(result["labelled_text"]), 1)

        ann = result["labelled_text"][0]
        self.assertEqual(ann["annotationLabel"], "PARAGRAPH")
        self.assertEqual(ann["rawText"], "Hello World")

        # Verify request was made with base64-encoded DOCX
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = (
            call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        )
        self.assertIn("docx_base64", payload)
        self.assertIn("filename", payload)

    @patch("opencontractserver.pipeline.parsers.docxodus_parser.requests.post")
    def test_parse_document_timeout(self, mock_post):
        """Test that timeout raises transient DocumentParsingError."""
        mock_post.side_effect = Timeout("Connection timed out")

        parser = DocxodusServiceParser()
        parser.service_url = "http://docxodus-parser:8080/parse"
        parser.request_timeout = 5

        with self.assertRaises(DocumentParsingError) as ctx:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)

    @patch("opencontractserver.pipeline.parsers.docxodus_parser.requests.post")
    def test_parse_document_connection_error(self, mock_post):
        """Test that connection error raises transient DocumentParsingError."""
        mock_post.side_effect = ConnectionError("Connection refused")

        parser = DocxodusServiceParser()
        parser.service_url = "http://docxodus-parser:8080/parse"

        with self.assertRaises(DocumentParsingError) as ctx:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)

    def test_normalize_response_camel_to_snake(self):
        """Test camelCase to snake_case field normalization."""
        response = {
            "title": "Test",
            "content": "Hello",
            "pageCount": 3,
            "pawlsFileContent": [],
            "docLabels": ["CONTRACT"],
            "labelledText": [
                {
                    "annotationLabel": "HEADING",
                    "rawText": "Title",
                    "annotationJson": {"start": 0, "end": 5},
                    "parentId": "parent-1",
                    "annotationType": "text",
                    "contentModalities": ["text"],
                }
            ],
            "relationships": [
                {
                    "relationshipLabel": "CONTAINS",
                    "sourceAnnotationIds": ["a1"],
                    "targetAnnotationIds": ["a2"],
                }
            ],
            "structuralSetHash": "abc123",
            "fileType": "docx",
        }

        normalized = DocxodusServiceParser._normalize_response(response)

        # Top-level field normalization
        self.assertEqual(normalized["page_count"], 3)
        self.assertEqual(normalized["pawls_file_content"], [])
        self.assertEqual(normalized["doc_labels"], ["CONTRACT"])
        self.assertEqual(normalized["structural_set_hash"], "abc123")
        self.assertEqual(normalized["file_type"], "docx")

        # Annotation field normalization
        # annotationLabel and rawText stay camelCase (OpenContractDocExport format)
        ann = normalized["labelled_text"][0]
        self.assertEqual(ann["annotationLabel"], "HEADING")
        self.assertEqual(ann["rawText"], "Title")
        self.assertEqual(ann["annotation_json"], {"start": 0, "end": 5})
        self.assertEqual(ann["parent_id"], "parent-1")
        # "text" is not a valid LABEL_TYPES value, so annotation_type is dropped
        self.assertNotIn("annotation_type", ann)
        self.assertEqual(ann["content_modalities"], ["text"])

        # Relationship field normalization
        rel = normalized["relationships"][0]
        self.assertEqual(rel["source_annotation_ids"], ["a1"])
        self.assertEqual(rel["target_annotation_ids"], ["a2"])

    @patch("opencontractserver.pipeline.parsers.docxodus_parser.requests.post")
    def test_parse_document_http_4xx_error(self, mock_post):
        """Test that a 4xx HTTP error raises a non-transient DocumentParsingError."""
        mock_post.return_value = MockResponse(400, {"error": "Bad request"})

        parser = DocxodusServiceParser()
        parser.service_url = "http://docxodus-parser:8080/parse"

        with self.assertRaises(DocumentParsingError) as ctx:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)

        self.assertFalse(ctx.exception.is_transient)

    @patch("opencontractserver.pipeline.parsers.docxodus_parser.requests.post")
    def test_parse_document_http_5xx_error(self, mock_post):
        """Test that a 5xx HTTP error raises a transient DocumentParsingError."""
        mock_post.return_value = MockResponse(502, {"error": "Bad Gateway"})

        parser = DocxodusServiceParser()
        parser.service_url = "http://docxodus-parser:8080/parse"

        with self.assertRaises(DocumentParsingError) as ctx:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)

    def test_no_file_returns_none(self):
        """Test that a document with no file returns None."""
        doc_no_file = Document.objects.create(
            title="Empty Doc",
            description="No file",
            file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            creator=self.user,
        )

        parser = DocxodusServiceParser()
        parser.service_url = "http://docxodus-parser:8080/parse"

        result = parser._parse_document_impl(
            user_id=self.user.id, doc_id=doc_no_file.id
        )

        self.assertIsNone(result)


class TestDocxThumbnailGenerator(TestCase):
    """Tests for the DocxThumbnailGenerator class."""

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="thumb_tester", password="12345678"
            )

    def test_extract_text_preview(self):
        """Test extraction of text from DOCX XML for thumbnail."""
        from opencontractserver.pipeline.thumbnailers.docx_thumbnailer import (
            DocxThumbnailGenerator,
        )

        docx_bytes = make_minimal_docx()
        preview = DocxThumbnailGenerator._extract_text_preview(docx_bytes)

        self.assertIsNotNone(preview)
        assert preview is not None
        self.assertIn("Hello", preview)
        self.assertIn("World", preview)

    def test_extract_embedded_thumbnail_no_thumbnail(self):
        """Test that DOCX without embedded thumbnail returns None."""
        from opencontractserver.pipeline.thumbnailers.docx_thumbnailer import (
            DocxThumbnailGenerator,
        )

        docx_bytes = make_minimal_docx()
        result = DocxThumbnailGenerator._extract_embedded_thumbnail(docx_bytes)
        self.assertIsNone(result)

    def test_extract_embedded_thumbnail_with_jpeg(self):
        """Test extraction of embedded JPEG thumbnail from DOCX."""
        from opencontractserver.pipeline.thumbnailers.docx_thumbnailer import (
            DocxThumbnailGenerator,
        )

        # Create a DOCX with an embedded thumbnail
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            zf.writestr("word/document.xml", "<w:document/>")
            # Add a fake JPEG thumbnail
            fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
            zf.writestr("docProps/thumbnail.jpeg", fake_jpeg)

        result = DocxThumbnailGenerator._extract_embedded_thumbnail(buf.getvalue())

        self.assertIsNotNone(result)
        assert result is not None
        thumb_bytes, ext = result
        self.assertEqual(ext, "jpeg")
        self.assertTrue(thumb_bytes.startswith(b"\xff\xd8"))

    def test_text_thumbnail_generation(self):
        """Test text-based thumbnail generation for DOCX."""
        from opencontractserver.pipeline.thumbnailers.docx_thumbnailer import (
            DocxThumbnailGenerator,
        )

        generator = DocxThumbnailGenerator()
        docx_bytes = make_minimal_docx()

        result = generator._generate_thumbnail_impl(
            txt_content=None,
            pdf_bytes=docx_bytes,
            height=300,
            width=300,
        )

        self.assertIsNotNone(result)
        assert result is not None
        thumb_bytes, ext = result
        self.assertEqual(ext, "png")
        self.assertGreater(len(thumb_bytes), 0)

    def test_invalid_docx_returns_none(self):
        """Test that invalid DOCX bytes don't crash the thumbnail generator."""
        from opencontractserver.pipeline.thumbnailers.docx_thumbnailer import (
            DocxThumbnailGenerator,
        )

        result = DocxThumbnailGenerator._extract_embedded_thumbnail(b"not a valid docx")
        self.assertIsNone(result)

        preview = DocxThumbnailGenerator._extract_text_preview(b"not a valid docx")
        self.assertIsNone(preview)
