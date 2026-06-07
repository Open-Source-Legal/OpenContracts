"""Tests for the MarkdownParser (no-op parser for .md / .caml files)."""

from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.parsers.oc_markdown_parser import MarkdownParser
from opencontractserver.users.models import User


class TestMarkdownParser(TestCase):
    user: User
    parser: MarkdownParser

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(
            username="md_parser_test_user", password="testpass"
        )
        cls.parser = MarkdownParser()

    def _make_document(self, txt_content: str = "# Hello\nWorld") -> Document:
        doc = Document.objects.create(
            title="test.md",
            description="A test markdown document",
            creator=self.user,
        )
        doc.txt_extract_file.save("test.txt", ContentFile(txt_content.encode("utf-8")))
        doc.save()
        return doc

    def test_parse_returns_expected_dict(self):
        """Successful parse returns title, content, and empty annotation lists."""
        doc = self._make_document("# My Article\nSome body text.")
        result = self.parser._parse_document_impl(self.user.id, doc.id)

        assert result is not None
        self.assertEqual(result["title"], "test.md")
        self.assertEqual(result["content"], "# My Article\nSome body text.")
        self.assertEqual(result["description"], "A test markdown document")
        self.assertEqual(result["pawls_file_content"], [])
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["doc_labels"], [])
        self.assertEqual(result["labelled_text"], [])

    def test_parse_no_txt_file_returns_none(self):
        """Returns None when document has no txt_extract_file."""
        doc = Document.objects.create(
            title="empty.md",
            description="",
            creator=self.user,
        )
        result = self.parser._parse_document_impl(self.user.id, doc.id)
        self.assertIsNone(result)

    def test_parse_handles_bytes_from_storage(self):
        """Storage backends may return bytes; parser should decode them."""
        doc = self._make_document("Unicode content: \u00e9\u00e0\u00fc")

        # The parser now reads through ``read_field_file_text``, which calls
        # ``txt_extract_file.open("r")``; cloud backends return bytes there.
        # Patch ``open`` on the FieldFile *class* (``type(...)``): patching the
        # instance fails because ``FieldFile.open`` is resolved on the class,
        # not the instance ``__dict__``.
        raw_bytes = "Unicode content: \u00e9\u00e0\u00fc".encode()
        with patch.object(type(doc.txt_extract_file), "open") as mock_open:
            mock_open.return_value.__enter__ = lambda s: BytesIO(raw_bytes)
            mock_open.return_value.__exit__ = lambda s, *a: None
            result = self.parser._parse_document_impl(self.user.id, doc.id)

        assert result is not None
        self.assertEqual(result["content"], "Unicode content: \u00e9\u00e0\u00fc")

    def test_parse_handles_string_from_storage(self):
        """Storage backends may return str directly; parser should handle both."""
        doc = self._make_document("Plain string content")

        with patch.object(type(doc.txt_extract_file), "open") as mock_open:
            mock_open.return_value.__enter__ = lambda s: StringIO(
                "Plain string content"
            )
            mock_open.return_value.__exit__ = lambda s, *a: None
            result = self.parser._parse_document_impl(self.user.id, doc.id)

        assert result is not None
        self.assertEqual(result["content"], "Plain string content")

    def test_parse_empty_description_defaults_to_empty_string(self):
        """When document.description is None, result uses empty string."""
        doc = Document.objects.create(
            title="no-desc.md",
            creator=self.user,
        )
        doc.txt_extract_file.save("no-desc.txt", ContentFile(b"content"))
        doc.save()
        # description may be None or "" depending on model field
        doc.description = None
        doc.save()

        result = self.parser._parse_document_impl(self.user.id, doc.id)
        assert result is not None
        self.assertEqual(result["description"], "")
