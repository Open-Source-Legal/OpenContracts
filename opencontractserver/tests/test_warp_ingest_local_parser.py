"""Tests for :class:`WarpIngestLocalParser`.

Warp-Ingest is an optional dependency, so the core tests inject a fake
``warp_ingest.ingestor.pdf_ingestor`` module (the parser imports it lazily) and
assert the glue: PDF bytes in → ``OpenContractDocExport`` out, title/description
fallback, and the error semantics. A final test runs the REAL parser against a
fixture PDF when the package happens to be installed (e.g. a desktop build) and
self-skips otherwise.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.parsers.warp_ingest_local_parser import (
    WarpIngestLocalParser,
)

User = get_user_model()

# Minimal valid-ish PDF bytes (never actually parsed — parse_to_opencontracts is
# mocked in the core tests).
_PDF_BYTES = (
    b"%PDF-1.7\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n"
    b"2 0 obj\n<</Type/Pages/Count 1/Kids[3 0 R]>>\nendobj\n"
    b"3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>"
    b"\nendobj\ntrailer\n<</Size 4/Root 1 0 R>>\n%%EOF\n"
)


def _sample_export() -> dict:
    """An ``OpenContractDocExport`` shaped like real Warp-Ingest output."""
    return {
        "title": "",
        "content": "Section One\nA paragraph.",
        "description": "",
        "page_count": 1,
        "doc_labels": [],
        "labelled_text": [
            {
                "id": "0",
                "annotationLabel": "Section Header",
                "rawText": "Section One",
                "page": 0,
                "annotation_json": {"0": {"bounds": {}, "tokensJsons": []}},
                "parent_id": None,
                "annotation_type": "TOKEN_LABEL",
                "structural": True,
                "content_modalities": ["TEXT"],
            }
        ],
        "relationships": [
            {
                "id": "rel-1",
                "relationshipLabel": "OC_PARENT_CHILD",
                "source_annotation_ids": ["0"],
                "target_annotation_ids": ["1"],
                "structural": True,
            }
        ],
        "pawls_file_content": [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [{"x": 1, "y": 1, "width": 10, "height": 12, "text": "Hi"}],
            }
        ],
    }


class _FakeWarpIngest:
    """Context manager injecting a fake ``warp_ingest.ingestor.pdf_ingestor``."""

    def __init__(self, parse_return=None, parse_side_effect=None):
        self.mock = MagicMock()
        if parse_side_effect is not None:
            self.mock.parse_to_opencontracts.side_effect = parse_side_effect
        else:
            self.mock.parse_to_opencontracts.return_value = (
                parse_return if parse_return is not None else _sample_export()
            )
        self._saved = {}

    def __enter__(self):
        pkg = types.ModuleType("warp_ingest")
        ingestor_pkg = types.ModuleType("warp_ingest.ingestor")
        setattr(ingestor_pkg, "pdf_ingestor", self.mock)
        setattr(pkg, "ingestor", ingestor_pkg)
        for name, mod in (
            ("warp_ingest", pkg),
            ("warp_ingest.ingestor", ingestor_pkg),
            ("warp_ingest.ingestor.pdf_ingestor", self.mock),
        ):
            self._saved[name] = sys.modules.get(name)
            sys.modules[name] = mod
        return self.mock

    def __exit__(self, *exc):
        for name, prev in self._saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev


class WarpIngestLocalParserTests(TestCase):
    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(username="warp", password="12345678")
        self.doc = Document.objects.create(
            title="Fallback Title",
            description="Fallback Desc",
            file_type="pdf",
            creator=self.user,
        )
        self.doc.pdf_file.save("test.pdf", ContentFile(_PDF_BYTES))
        self.parser = WarpIngestLocalParser()

    def test_parses_pdf_to_export(self):
        with _FakeWarpIngest() as mock:
            result = self.parser._parse_document_impl(self.user.id, self.doc.id)
        assert result is not None
        self.assertEqual(len(result["labelled_text"]), 1)
        self.assertEqual(len(result["relationships"]), 1)
        self.assertEqual(
            result["relationships"][0]["relationshipLabel"], "OC_PARENT_CHILD"
        )
        self.assertEqual(result["pawls_file_content"][0]["tokens"][0]["text"], "Hi")
        # parse_to_opencontracts is called with a temp path + parse options.
        args, _ = mock.parse_to_opencontracts.call_args
        self.assertTrue(str(args[0]).endswith(".pdf"))
        self.assertIn("apply_ocr", args[1])

    def test_title_and_description_fallback(self):
        with _FakeWarpIngest():
            result = self.parser._parse_document_impl(self.user.id, self.doc.id)
        # Warp returned empty title/description → fall back to the document's.
        assert result is not None
        self.assertEqual(result["title"], "Fallback Title")
        self.assertEqual(result["description"], "Fallback Desc")

    def test_missing_pdf_returns_none(self):
        doc = Document.objects.create(
            title="No File", file_type="pdf", creator=self.user
        )
        with _FakeWarpIngest():
            self.assertIsNone(self.parser._parse_document_impl(self.user.id, doc.id))

    def test_parse_failure_raises_permanent_error(self):
        with _FakeWarpIngest(parse_side_effect=ValueError("bad pdf")):
            with self.assertRaises(DocumentParsingError) as ctx:
                self.parser._parse_document_impl(self.user.id, self.doc.id)
        self.assertFalse(ctx.exception.is_transient)

    def test_network_failure_is_transient(self):
        # e.g. a first-run OCR model download over a flaky network — retryable.
        with _FakeWarpIngest(parse_side_effect=ConnectionError("net down")):
            with self.assertRaises(DocumentParsingError) as ctx:
                self.parser._parse_document_impl(self.user.id, self.doc.id)
        self.assertTrue(ctx.exception.is_transient)

    def test_requests_style_network_error_is_transient(self):
        # requests/httpx network errors do NOT subclass builtin ConnectionError;
        # they must still be classified transient (matched by MRO class name).
        class ConnectTimeout(Exception):  # httpx-style name, not a builtin subclass
            pass

        with _FakeWarpIngest(parse_side_effect=ConnectTimeout("slow")):
            with self.assertRaises(DocumentParsingError) as ctx:
                self.parser._parse_document_impl(self.user.id, self.doc.id)
        self.assertTrue(ctx.exception.is_transient)

    def test_missing_dependency_raises_permanent_error(self):
        # sys.modules[name]=None makes ``import warp_ingest`` raise ImportError.
        saved = sys.modules.get("warp_ingest")
        sys.modules["warp_ingest"] = None  # type: ignore[assignment]
        try:
            with self.assertRaises(DocumentParsingError) as ctx:
                self.parser._parse_document_impl(self.user.id, self.doc.id)
        finally:
            if saved is None:
                sys.modules.pop("warp_ingest", None)
            else:
                sys.modules["warp_ingest"] = saved
        self.assertFalse(ctx.exception.is_transient)

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("warp_ingest") is not None,
        "warp-ingest not installed",
    )
    def test_real_parse_smoke(self):
        """Real end-to-end parse when Warp-Ingest is actually installed."""
        import os

        # Warp-Ingest needs the nltk corpora at parse time; on a dev machine
        # they arrive via the desktop first-run bootstrap, so skip (not fail)
        # when they haven't been downloaded here.
        try:
            import nltk

            nltk.data.find("corpora/stopwords")
            nltk.data.find("tokenizers/punkt")
            nltk.data.find("tokenizers/punkt_tab")
        except LookupError:
            self.skipTest("nltk corpora not downloaded")

        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "files", "doc_1_pdf_file.pdf"
        )
        if not os.path.exists(fixture):
            self.skipTest("fixture PDF missing")
        with open(fixture, "rb") as fh:
            self.doc.pdf_file.save("real.pdf", ContentFile(fh.read()))
        result = self.parser._parse_document_impl(self.user.id, self.doc.id)
        assert result is not None
        self.assertGreater(len(result["labelled_text"]), 0)
        self.assertGreater(len(result["pawls_file_content"]), 0)
