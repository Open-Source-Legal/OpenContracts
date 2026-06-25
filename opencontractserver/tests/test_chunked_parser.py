"""
Tests for the BaseChunkedParser reassembly logic and chunk dispatching.
"""

import threading
import time
from typing import Optional, cast
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.chunk_reassembler import (
    offset_annotation as _offset_annotation,
)
from opencontractserver.pipeline.base.chunk_reassembler import (
    offset_relationship as _offset_relationship,
)
from opencontractserver.pipeline.base.chunked_parser import (
    BaseChunkedParser,
    _reassemble_chunk_results,
)
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.parsers.docling_parser_rest import DoclingParser
from opencontractserver.pipeline.parsers.oc_text_parser import TxtParser
from opencontractserver.pipeline.utils import get_all_parsers
from opencontractserver.tests.helpers import make_test_pdf
from opencontractserver.types.dicts import (
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
)
from opencontractserver.utils.pdf_splitting import get_pdf_page_count

User = get_user_model()


def _make_chunk_result(
    num_pages: int = 2,
    annotations: list | None = None,
    relationships: list | None = None,
    content: str = "chunk text",
) -> OpenContractDocExport:
    """Build a minimal chunk result with local 0-based page indices."""
    pawls: list = []
    for i in range(num_pages):
        pawls.append(
            {
                "page": {"width": 612, "height": 792, "index": i},
                "tokens": [
                    {"x": 10, "y": 10, "width": 50, "height": 12, "text": f"tok_{i}"}
                ],
            }
        )

    if annotations is None:
        annotations = [
            {
                "id": "ann-1",
                "annotationLabel": "Paragraph",
                "rawText": "sample",
                "page": 0,
                "annotation_json": {
                    "0": {
                        "bounds": {
                            "left": 10,
                            "top": 10,
                            "right": 60,
                            "bottom": 22,
                        },
                        "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                        "rawText": "sample",
                    }
                },
                "parent_id": None,
                "annotation_type": "TOKEN_LABEL",
                "structural": True,
            }
        ]

    return {
        "title": "Test Doc",
        "content": content,
        "description": "desc",
        "pawls_file_content": pawls,
        "page_count": num_pages,
        "doc_labels": ["Contract"],
        "labelled_text": annotations,
        "relationships": relationships or [],
    }


class _FakeChunkedParser(BaseChunkedParser):
    """Minimal concrete chunked parser for orchestration tests."""

    title = "Fake Chunked"
    description = "test"
    author = "test"
    supported_file_types = [FileTypeEnum.PDF]
    # Force chunking at a low threshold for tests.
    max_pages_per_chunk = 2
    min_pages_for_chunking = 2
    # This double returns a fixed-size fake result that does not model overlap
    # pages, so it exercises the offset/dispatch mechanics with overlap disabled
    # (overlap=2 would also be invalid against max_pages_per_chunk=2). Overlap
    # dedup/re-linking is covered by the overlap-aware doubles further below.
    chunk_overlap = 0

    def __init__(self, **kwargs):
        # Skip PipelineComponentBase settings loading during tests
        self._full_class_path = "test._FakeChunkedParser"
        self._settings = None

    def _parse_single_chunk_impl(
        self,
        user_id,
        doc_id,
        chunk_pdf_bytes,
        chunk_index,
        total_chunks,
        page_offset,
        **all_kwargs,
    ):
        n = get_pdf_page_count(chunk_pdf_bytes)
        return _make_chunk_result(num_pages=n, content=f"chunk{chunk_index}")


# ======================================================================
# Reassembly pure-function tests
# ======================================================================


class TestReassembleChunkResults(TestCase):
    """Tests for _reassemble_chunk_results."""

    def test_single_chunk_at_offset_zero(self):
        """A single chunk at offset 0 still gets prefixed IDs for consistency."""
        chunk = _make_chunk_result()
        result = _reassemble_chunk_results([chunk], [0])
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(len(result["pawls_file_content"]), 2)
        self.assertEqual(len(result["labelled_text"]), 1)
        # IDs are always prefixed, even for single-chunk results
        self.assertEqual(result["labelled_text"][0]["id"], "c0_ann-1")

    def test_two_chunks_page_count(self):
        c0 = _make_chunk_result(num_pages=3, content="first")
        c1 = _make_chunk_result(num_pages=2, content="second")
        result = _reassemble_chunk_results([c0, c1], [0, 3])
        self.assertEqual(result["page_count"], 5)
        self.assertEqual(len(result["pawls_file_content"]), 5)

    def test_pawls_page_index_offset(self):
        c0 = _make_chunk_result(num_pages=2)
        c1 = _make_chunk_result(num_pages=2)
        result = _reassemble_chunk_results([c0, c1], [0, 2])
        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 2, 3])

    def test_annotation_page_offset(self):
        c0 = _make_chunk_result(num_pages=3)
        c1 = _make_chunk_result(num_pages=3)
        result = _reassemble_chunk_results([c0, c1], [0, 3])
        pages = [a["page"] for a in result["labelled_text"]]
        self.assertEqual(pages, [0, 3])

    def test_annotation_id_prefixing(self):
        c0 = _make_chunk_result()
        c1 = _make_chunk_result()
        result = _reassemble_chunk_results([c0, c1], [0, 2])
        ids = [a["id"] for a in result["labelled_text"]]
        self.assertEqual(ids, ["c0_ann-1", "c1_ann-1"])

    def test_annotation_json_page_key_offset(self):
        c1 = _make_chunk_result(num_pages=2)
        result = _reassemble_chunk_results([c1], [5])
        ann = result["labelled_text"][0]
        self.assertIn("5", ann["annotation_json"])
        self.assertNotIn("0", ann["annotation_json"])

    def test_tokens_json_page_index_offset(self):
        c1 = _make_chunk_result(num_pages=2)
        result = _reassemble_chunk_results([c1], [10])
        ann = result["labelled_text"][0]
        page_data = cast(dict, ann["annotation_json"])["10"]
        self.assertEqual(page_data["tokensJsons"][0]["pageIndex"], 10)

    def test_content_concatenation(self):
        c0 = _make_chunk_result(content="hello")
        c1 = _make_chunk_result(content="world")
        result = _reassemble_chunk_results([c0, c1], [0, 2])
        self.assertEqual(result["content"], "hello\nworld")

    def test_doc_labels_deduplicated(self):
        c0 = _make_chunk_result()
        c1 = _make_chunk_result()
        # Both chunks have doc_labels=["Contract"]
        result = _reassemble_chunk_results([c0, c1], [0, 2])
        self.assertEqual(result["doc_labels"], ["Contract"])

    def test_relationship_id_prefixing(self):
        rels = [
            {
                "id": "rel-1",
                "relationshipLabel": "Contains",
                "source_annotation_ids": ["ann-1"],
                "target_annotation_ids": ["ann-2"],
                "structural": True,
            }
        ]
        c0 = _make_chunk_result(relationships=rels)
        result = _reassemble_chunk_results([c0], [5])
        rel = result["relationships"][0]
        self.assertEqual(rel["id"], "c0_rel-1")
        self.assertEqual(rel["source_annotation_ids"], ["c0_ann-1"])
        self.assertEqual(rel["target_annotation_ids"], ["c0_ann-2"])

    def test_parent_id_prefixing(self):
        annotations = [
            {
                "id": "parent-1",
                "annotationLabel": "Section",
                "rawText": "section",
                "page": 0,
                "annotation_json": {
                    "0": {"bounds": {}, "tokensJsons": [], "rawText": ""}
                },
                "parent_id": None,
                "annotation_type": "TOKEN_LABEL",
                "structural": True,
            },
            {
                "id": "child-1",
                "annotationLabel": "Paragraph",
                "rawText": "para",
                "page": 1,
                "annotation_json": {
                    "1": {"bounds": {}, "tokensJsons": [], "rawText": ""}
                },
                "parent_id": "parent-1",
                "annotation_type": "TOKEN_LABEL",
                "structural": True,
            },
        ]
        c0 = _make_chunk_result(annotations=annotations, num_pages=2)
        result = _reassemble_chunk_results([c0], [10])
        child = result["labelled_text"][1]
        self.assertEqual(child["parent_id"], "c0_parent-1")
        self.assertEqual(child["id"], "c0_child-1")

    def test_cross_chunk_parent_id_becomes_orphan(self):
        """Parent-child references across chunk boundaries become orphaned.

        When a child annotation in chunk 1 references a parent_id that
        exists in chunk 0, the prefixed IDs won't match because each
        chunk's IDs are prefixed independently (c0_ vs c1_).
        """
        # Chunk 0 has the parent
        parent_ann = {
            "id": "section-1",
            "annotationLabel": "Section",
            "rawText": "Section Header",
            "page": 0,
            "annotation_json": {"0": {"bounds": {}, "tokensJsons": [], "rawText": ""}},
            "parent_id": None,
            "annotation_type": "TOKEN_LABEL",
            "structural": True,
        }
        c0 = _make_chunk_result(annotations=[parent_ann], num_pages=2)

        # Chunk 1 has a child referencing chunk 0's parent
        child_ann = {
            "id": "para-1",
            "annotationLabel": "Paragraph",
            "rawText": "Paragraph text",
            "page": 0,
            "annotation_json": {"0": {"bounds": {}, "tokensJsons": [], "rawText": ""}},
            "parent_id": "section-1",  # References chunk 0's annotation
            "annotation_type": "TOKEN_LABEL",
            "structural": True,
        }
        c1 = _make_chunk_result(annotations=[child_ann], num_pages=2)

        result = _reassemble_chunk_results([c0, c1], [0, 2])

        parent = result["labelled_text"][0]
        child = result["labelled_text"][1]

        # Parent gets c0_ prefix
        self.assertEqual(parent["id"], "c0_section-1")
        # Child's parent_id gets c1_ prefix (its own chunk), NOT c0_
        # This is a known limitation: cross-chunk parent refs are orphaned
        self.assertEqual(child["parent_id"], "c1_section-1")

        # Verify the reference is indeed broken
        all_ids = {a["id"] for a in result["labelled_text"]}
        self.assertNotIn(child["parent_id"], all_ids)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            _reassemble_chunk_results([], [])


class TestOffsetAnnotation(TestCase):
    """Tests for the _offset_annotation helper."""

    def test_basic_offset(self):
        ann: dict = {
            "id": "a1",
            "page": 2,
            "parent_id": "a0",
            "annotation_json": {
                "2": {
                    "tokensJsons": [{"pageIndex": 2, "tokenIndex": 0}],
                    "bounds": {},
                    "rawText": "",
                }
            },
        }
        _offset_annotation(cast(OpenContractsAnnotationPythonType, ann), 10, "c0_")
        self.assertEqual(ann["id"], "c0_a1")
        self.assertEqual(ann["page"], 12)
        self.assertEqual(ann["parent_id"], "c0_a0")
        self.assertIn("12", ann["annotation_json"])
        self.assertNotIn("2", ann["annotation_json"])
        self.assertEqual(
            ann["annotation_json"]["12"]["tokensJsons"][0]["pageIndex"], 12
        )


class TestOffsetRelationship(TestCase):
    """Tests for the _offset_relationship helper."""

    def test_basic_offset(self):
        rel = {
            "id": "r1",
            "source_annotation_ids": ["a1", "a2"],
            "target_annotation_ids": ["a3"],
        }
        _offset_relationship(cast(OpenContractsRelationshipPythonType, rel), "c1_")
        self.assertEqual(rel["id"], "c1_r1")
        self.assertEqual(rel["source_annotation_ids"], ["c1_a1", "c1_a2"])
        self.assertEqual(rel["target_annotation_ids"], ["c1_a3"])


# ======================================================================
# BaseChunkedParser integration tests
# ======================================================================


class ConcreteChunkedParser(BaseChunkedParser):
    """Minimal concrete implementation for testing the base class."""

    title = "Test Chunked Parser"
    description = "Testing only"
    supported_file_types = [FileTypeEnum.PDF]
    # Returns a fixed-size fake result independent of the real (overlap-extended)
    # chunk page count, so it tests offset/dispatch mechanics with overlap off.
    # Realistic overlap dedup is covered by TestOverlapReassembly /
    # TestChunkedOverlapGoldenEquivalence below.
    chunk_overlap = 0

    def __init__(self, chunk_results=None, **kwargs):
        # Skip PipelineComponentBase settings loading during tests
        self._full_class_path = "test.ConcreteChunkedParser"
        self._settings = None
        self._chunk_results = chunk_results or {}

    def _parse_single_chunk_impl(
        self,
        user_id,
        doc_id,
        chunk_pdf_bytes,
        chunk_index,
        total_chunks,
        page_offset,
        **all_kwargs,
    ) -> Optional[OpenContractDocExport]:
        if chunk_index in self._chunk_results:
            return self._chunk_results[chunk_index]
        return _make_chunk_result(num_pages=2, content=f"chunk_{chunk_index}")


class TestBaseChunkedParserIntegration(TestCase):
    """Integration tests for BaseChunkedParser._parse_document_impl."""

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="chunktest", password="12345678"
            )

        # Create a multi-page PDF
        pdf_bytes = make_test_pdf(100)
        self.doc = Document.objects.create(
            title="Large Test Doc",
            description="100-page document",
            file_type="application/pdf",
            creator=self.user,
        )
        self.doc.pdf_file.save("large_test.pdf", ContentFile(pdf_bytes))

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_small_doc_no_chunking(self, mock_open):
        """Documents below threshold should NOT be chunked but still get prefixed IDs."""
        small_pdf = make_test_pdf(10)
        mock_file = MagicMock()
        mock_file.read.return_value = small_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        parser = ConcreteChunkedParser()
        parser.min_pages_for_chunking = 75

        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["page_count"], 2)  # From default _make_chunk_result
        # Even single-chunk documents now get consistent c0_ prefixed IDs
        self.assertEqual(result["labelled_text"][0]["id"], "c0_ann-1")

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_large_doc_is_chunked(self, mock_open):
        """Documents above threshold should be chunked and reassembled."""
        large_pdf = make_test_pdf(100)
        mock_file = MagicMock()
        mock_file.read.return_value = large_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        parser = ConcreteChunkedParser()
        parser.max_pages_per_chunk = 50
        parser.min_pages_for_chunking = 75
        parser.max_concurrent_chunks = 1  # Sequential for determinism

        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIsNotNone(result)
        assert result is not None
        # 2 chunks x 2 pages each from _make_chunk_result default
        self.assertEqual(result["page_count"], 4)
        # PAWLs pages should have correct indices
        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 50, 51])

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_concurrent_dispatch(self, mock_open):
        """Concurrent dispatch should produce same results as sequential."""
        large_pdf = make_test_pdf(100)
        mock_file = MagicMock()
        mock_file.read.return_value = large_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        parser = ConcreteChunkedParser()
        parser.max_pages_per_chunk = 50
        parser.min_pages_for_chunking = 75
        parser.max_concurrent_chunks = 3

        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["page_count"], 4)
        # Verify PAWLs pages are in correct global order (not completion order)
        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 50, 51])

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_chunk_failure_raises(self, mock_open):
        """If a chunk fails, DocumentParsingError should propagate."""
        large_pdf = make_test_pdf(100)
        mock_file = MagicMock()
        mock_file.read.return_value = large_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        class FailingParser(ConcreteChunkedParser):
            def _parse_single_chunk_impl(self, *args, **kwargs):
                raise DocumentParsingError("boom", is_transient=False)

        parser = FailingParser()
        parser.max_pages_per_chunk = 50
        parser.min_pages_for_chunking = 75
        parser.chunk_retry_limit = 0

        with self.assertRaises(DocumentParsingError):
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_post_reassemble_hook_called(self, mock_open):
        """The post-reassemble hook should be called after chunked parsing."""
        large_pdf = make_test_pdf(100)
        mock_file = MagicMock()
        mock_file.read.return_value = large_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        hook_called = {"value": False}

        class HookParser(ConcreteChunkedParser):
            def _post_reassemble_hook(
                self, user_id, doc_id, reassembled, pdf_bytes, **kw
            ):
                hook_called["value"] = True
                reassembled["title"] = "HOOKED"
                return reassembled

        parser = HookParser()
        parser.max_pages_per_chunk = 50
        parser.min_pages_for_chunking = 75

        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertTrue(hook_called["value"])
        assert result is not None
        self.assertEqual(result["title"], "HOOKED")

    def test_parse_pdf_bytes_no_database_single_chunk(self):
        """parse_pdf_bytes produces a full export from raw bytes with NO Document
        row and NO storage access — the headless entry point the remote-ingest
        worker relies on."""
        parser = ConcreteChunkedParser()
        parser.min_pages_for_chunking = 75

        # No Document, no doc_id, no default_storage mock — pure bytes in.
        result = parser.parse_pdf_bytes(make_test_pdf(10))

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["page_count"], 2)  # from _make_chunk_result default
        # Single-chunk docs still get consistent c0_-prefixed IDs.
        self.assertEqual(result["labelled_text"][0]["id"], "c0_ann-1")

    def test_parse_pdf_bytes_no_database_chunked(self):
        """parse_pdf_bytes chunks + reassembles large PDFs without a Document."""
        parser = ConcreteChunkedParser()
        parser.max_pages_per_chunk = 50
        parser.min_pages_for_chunking = 75
        parser.max_concurrent_chunks = 1  # sequential for determinism

        result = parser.parse_pdf_bytes(make_test_pdf(100))

        assert result is not None
        self.assertEqual(result["page_count"], 4)
        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 50, 51])

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_parse_document_impl_delegates_to_parse_pdf_bytes(self, mock_open):
        """_parse_document_impl reads the Document's bytes then delegates to the
        DB-free parse_pdf_bytes — proving the two paths share one implementation."""
        small_pdf = make_test_pdf(10)
        mock_file = MagicMock()
        mock_file.read.return_value = small_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        parser = ConcreteChunkedParser()
        parser.min_pages_for_chunking = 75

        with patch.object(
            parser, "parse_pdf_bytes", wraps=parser.parse_pdf_bytes
        ) as spy:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)

        spy.assert_called_once()
        # The PDF bytes read from storage are passed positionally.
        self.assertEqual(spy.call_args.args[0], small_pdf)

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    @patch("opencontractserver.pipeline.base.chunked_parser.time.sleep")
    def test_chunk_retry_on_transient_error(self, mock_sleep, mock_open):
        """Transient chunk errors should be retried up to chunk_retry_limit."""
        small_pdf = make_test_pdf(10)
        mock_file = MagicMock()
        mock_file.read.return_value = small_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        call_count = {"value": 0}

        class RetryParser(ConcreteChunkedParser):
            def _parse_single_chunk_impl(self, *args, **kwargs):
                call_count["value"] += 1
                if call_count["value"] == 1:
                    raise DocumentParsingError("transient", is_transient=True)
                return _make_chunk_result()

        parser = RetryParser()
        parser.chunk_retry_limit = 1

        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIsNotNone(result)
        self.assertEqual(call_count["value"], 2)
        mock_sleep.assert_called_once()

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    @patch("opencontractserver.pipeline.base.chunked_parser.time.sleep")
    def test_retry_backoff_capped_at_max(self, mock_sleep, mock_open):
        """Backoff should be capped at MAX_CHUNK_RETRY_BACKOFF_SECONDS for high retry counts."""
        small_pdf = make_test_pdf(10)
        mock_file = MagicMock()
        mock_file.read.return_value = small_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        call_count = {"value": 0}

        class PersistentRetryParser(ConcreteChunkedParser):
            def _parse_single_chunk_impl(self, *args, **kwargs):
                call_count["value"] += 1
                # Fail on attempts 1-4, succeed on attempt 5
                if call_count["value"] < 5:
                    raise DocumentParsingError("transient", is_transient=True)
                return _make_chunk_result()

        parser = PersistentRetryParser()
        parser.chunk_retry_limit = 4  # 1 initial + 4 retries = 5 attempts

        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIsNotNone(result)
        self.assertEqual(call_count["value"], 5)

        # Verify backoff values: 5*2^0=5, 5*2^1=10, 5*2^2=20, 5*2^3=40->capped to 30
        self.assertEqual(mock_sleep.call_count, 4)
        backoff_values = [call.args[0] for call in mock_sleep.call_args_list]
        self.assertEqual(backoff_values, [5, 10, 20, 30])

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_invalid_max_pages_per_chunk_raises_document_parsing_error(self, mock_open):
        """max_pages_per_chunk=0 should raise DocumentParsingError, not bare ValueError."""
        small_pdf = make_test_pdf(10)
        mock_file = MagicMock()
        mock_file.read.return_value = small_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        parser = ConcreteChunkedParser()
        parser.max_pages_per_chunk = 0

        with self.assertRaises(DocumentParsingError) as ctx:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIn("max_pages_per_chunk must be > 0", str(ctx.exception))
        self.assertFalse(ctx.exception.is_transient)

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_invalid_min_pages_for_chunking_raises_document_parsing_error(
        self, mock_open
    ):
        """min_pages_for_chunking=0 should raise DocumentParsingError, not bare ValueError."""
        small_pdf = make_test_pdf(10)
        mock_file = MagicMock()
        mock_file.read.return_value = small_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        parser = ConcreteChunkedParser()
        parser.min_pages_for_chunking = 0

        with self.assertRaises(DocumentParsingError) as ctx:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIn("min_pages_for_chunking must be > 0", str(ctx.exception))
        self.assertFalse(ctx.exception.is_transient)

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_zero_max_concurrent_chunks_raises_for_small_doc(self, mock_open):
        """max_concurrent_chunks=0 should raise even for small (non-chunked) docs."""
        small_pdf = make_test_pdf(10)
        mock_file = MagicMock()
        mock_file.read.return_value = small_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        parser = ConcreteChunkedParser()
        parser.max_concurrent_chunks = 0

        with self.assertRaises(DocumentParsingError) as ctx:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIn("max_concurrent_chunks must be > 0", str(ctx.exception))

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_zero_max_concurrent_chunks_raises_for_large_doc(self, mock_open):
        """max_concurrent_chunks=0 should raise for large (chunked) docs."""
        large_pdf = make_test_pdf(100)
        mock_file = MagicMock()
        mock_file.read.return_value = large_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        parser = ConcreteChunkedParser()
        parser.max_pages_per_chunk = 50
        parser.min_pages_for_chunking = 75
        parser.max_concurrent_chunks = 0

        with self.assertRaises(DocumentParsingError) as ctx:
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIn("max_concurrent_chunks must be > 0", str(ctx.exception))

    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage.open")
    def test_concurrent_failure_cancels_remaining(self, mock_open):
        """When one chunk fails concurrently, remaining futures should be cancelled."""
        large_pdf = make_test_pdf(200)
        mock_file = MagicMock()
        mock_file.read.return_value = large_pdf
        mock_open.return_value.__enter__.return_value = mock_file

        slow_chunks_started = threading.Event()

        class SlowFailParser(ConcreteChunkedParser):
            def _parse_single_chunk_impl(self, *args, **kwargs):
                chunk_index = kwargs.get("chunk_index")
                if chunk_index is None:
                    # Positional: user_id, doc_id, chunk_pdf_bytes, chunk_index, ...
                    chunk_index = args[3] if len(args) > 3 else 0
                if chunk_index == 0:
                    raise DocumentParsingError("chunk 0 boom", is_transient=False)
                slow_chunks_started.set()
                # Sleep briefly; the error from chunk 0 should unblock the caller
                # before this completes on a healthy system.
                time.sleep(0.5)
                return _make_chunk_result()

        parser = SlowFailParser()
        parser.max_pages_per_chunk = 50
        parser.min_pages_for_chunking = 75
        parser.max_concurrent_chunks = 4
        parser.chunk_retry_limit = 0

        with self.assertRaises(DocumentParsingError):
            parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)

        # Wait briefly for slow chunks to signal (eliminates theoretical race on
        # heavily loaded CI machines where the event might not be set yet).
        slow_chunks_started.wait(timeout=2)
        # Confirm at least one slow chunk was dispatched before the error propagated
        self.assertTrue(slow_chunks_started.is_set())


# ======================================================================
# Reassembly determinism / golden equivalence tests
# ======================================================================


class TestReassemblyGoldenEquivalence(TestCase):
    """Reassembled multi-chunk output matches a single logical document."""

    def test_global_page_indices_are_contiguous(self):
        # Three chunks of 2 pages each -> a 6-page document, indices 0..5.
        # Global page offsets are supplied to _reassemble_chunk_results below;
        # _make_chunk_result always emits local 0-based pages.
        chunk_a = _make_chunk_result(num_pages=2)
        chunk_b = _make_chunk_result(num_pages=2)
        chunk_c = _make_chunk_result(num_pages=2)

        result = _reassemble_chunk_results(
            [chunk_a, chunk_b, chunk_c], page_offsets=[0, 2, 4]
        )

        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 2, 3, 4, 5])
        self.assertEqual(result["page_count"], 6)

    def test_all_annotations_preserved_with_unique_ids(self):
        chunk_a = _make_chunk_result(num_pages=2)
        chunk_b = _make_chunk_result(num_pages=2)

        result = _reassemble_chunk_results([chunk_a, chunk_b], page_offsets=[0, 2])

        anns = result["labelled_text"]
        # Each synthetic chunk contributes one annotation; both survive.
        self.assertEqual(len(anns), 2)
        # IDs are made unique across chunks via the c{idx}_ prefix.
        ids = [a["id"] for a in anns]
        self.assertEqual(len(set(ids)), len(ids))
        # Second chunk's annotation page is offset into global space.
        self.assertEqual(anns[1]["page"], 2)

    def test_single_chunk_reassembly_is_stable(self):
        # A below-threshold document routes through reassembly as one chunk;
        # global indices must equal local indices.
        chunk = _make_chunk_result(num_pages=3)
        result = _reassemble_chunk_results([chunk], page_offsets=[0])
        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 2])
        self.assertEqual(result["page_count"], 3)


# ======================================================================
# supports_chunking capability flag tests
# ======================================================================


class TestSupportsChunkingFlag(TestCase):
    """The supports_chunking capability flag is set correctly per parser."""

    def test_base_parser_defaults_to_false(self):
        self.assertFalse(BaseParser.supports_chunking)

    def test_chunked_base_is_true(self):
        self.assertTrue(BaseChunkedParser.supports_chunking)

    def test_docling_parser_supports_chunking(self):
        self.assertTrue(DoclingParser.supports_chunking)

    def test_non_paginated_parser_does_not_support_chunking(self):
        # TxtParser extends BaseParser directly and must not opt in.
        self.assertFalse(TxtParser.supports_chunking)

    def test_all_registered_parsers_flag_matches_chunked_lineage(self):
        # Registry-driven: prove the orchestrator's introspection is correct for
        # *every* registered parser (current and future), not just the two
        # enumerated above. The flag must be True iff the parser is a
        # BaseChunkedParser subclass.
        parsers = get_all_parsers()
        self.assertTrue(parsers, "no parsers discovered by get_all_parsers()")
        for parser_cls in parsers:
            expected = issubclass(parser_cls, BaseChunkedParser)
            self.assertEqual(
                parser_cls.supports_chunking,
                expected,
                msg=(
                    f"{parser_cls.__name__}.supports_chunking="
                    f"{parser_cls.supports_chunking} but chunked-lineage="
                    f"{expected}"
                ),
            )


# ======================================================================
# prepare_chunk_inputs / reassemble_and_finalize orchestration tests
# ======================================================================


class TestPrepareChunkInputs(TestCase):
    def _make_doc(self, pages: int) -> Document:
        user = User.objects.create_user(username="cp", password="x")
        doc = Document(creator=user, title="t")
        doc.save()
        doc.pdf_file.save(f"doc_{doc.id}.pdf", ContentFile(make_test_pdf(pages)))
        return doc

    def test_below_threshold_returns_empty(self):
        doc = self._make_doc(1)  # threshold is 2
        parser = _FakeChunkedParser()
        self.assertEqual(parser.prepare_chunk_inputs(doc.id), [])

    def test_large_doc_writes_chunk_pdfs_and_returns_descriptors(self):
        from opencontractserver.pipeline.chunk_artifacts import (
            chunk_input_key,
            read_chunk_pdf,
        )

        doc = self._make_doc(5)  # max 2/chunk -> chunks (0,2)(2,4)(4,5)
        parser = _FakeChunkedParser()
        descriptors = parser.prepare_chunk_inputs(doc.id)
        self.assertEqual(len(descriptors), 3)
        self.assertEqual(descriptors[0]["chunk_index"], 0)
        self.assertEqual(descriptors[0]["page_offset"], 0)
        self.assertEqual(descriptors[0]["total_chunks"], 3)
        self.assertEqual(descriptors[0]["input_key"], chunk_input_key(doc.id, 0))
        self.assertEqual(
            get_pdf_page_count(read_chunk_pdf(descriptors[0]["input_key"])), 2
        )
        self.assertEqual(
            get_pdf_page_count(read_chunk_pdf(descriptors[2]["input_key"])), 1
        )


class TestReassembleAndFinalize(TestCase):
    def test_streams_results_and_returns_combined(self):
        from opencontractserver.pipeline.chunk_artifacts import write_chunk_result

        user = User.objects.create_user(username="rf", password="x")
        doc = Document(creator=user, title="t")
        doc.save()
        out0 = write_chunk_result(doc.id, 0, _make_chunk_result(num_pages=2))
        out1 = write_chunk_result(doc.id, 1, _make_chunk_result(num_pages=2))
        parser = _FakeChunkedParser()
        combined = parser.reassemble_and_finalize(
            out_keys=[out0, out1],
            page_offsets=[0, 2],
            doc_id=doc.id,
            user_id=user.id,
            corpus_id=None,
            save=False,
        )
        indices = [p["page"]["index"] for p in combined["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 2, 3])

    def test_cleans_up_scratch_artifacts_even_when_save_raises(self):
        """A storage/ORM failure in save_parsed_data must not orphan the chunk
        scratch artifacts — cleanup runs in a finally block (review bug 2)."""
        from unittest.mock import patch

        from django.core.files.storage import default_storage

        from opencontractserver.pipeline.chunk_artifacts import write_chunk_result

        user = User.objects.create_user(username="rf_save_fail", password="x")
        doc = Document(creator=user, title="t")
        doc.save()
        out0 = write_chunk_result(doc.id, 0, _make_chunk_result(num_pages=2))
        out1 = write_chunk_result(doc.id, 1, _make_chunk_result(num_pages=2))
        self.assertTrue(default_storage.exists(out0))
        self.assertTrue(default_storage.exists(out1))

        parser = _FakeChunkedParser()
        with patch.object(parser, "save_parsed_data", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                parser.reassemble_and_finalize(
                    out_keys=[out0, out1],
                    page_offsets=[0, 2],
                    doc_id=doc.id,
                    user_id=user.id,
                    corpus_id=None,
                    save=True,
                )

        # Despite the save failure, no scratch artifacts are left behind.
        self.assertFalse(default_storage.exists(out0))
        self.assertFalse(default_storage.exists(out1))


# ======================================================================
# Overlap wiring + golden equivalence (issue #1961)
# ======================================================================


class _OverlapGoldenParser(BaseChunkedParser):
    """Deterministic parser whose per-chunk output depends only on GLOBAL page.

    Each parsed page ``g`` (= ``page_offset + local_index``) always yields the
    same token, annotation (``p{g}``, with a linear ``parent_id`` chain to
    ``p{g-1}``) and forward relationship (``rel{g}``: ``p{g}`` -> ``p{g+1}``).
    Because the output is a pure function of the global page, a chunked +
    overlap parse must reduce — after dedup and cross-boundary re-linking — to
    exactly the same logical document as a single-shot parse, modulo the
    ``c{idx}_`` ID prefixing. That is the Phase 3 correctness gate.
    """

    title = "Overlap Golden"
    description = "deterministic"
    author = "test"
    supported_file_types = [FileTypeEnum.PDF]

    def __init__(self, **kwargs):
        self._full_class_path = "test._OverlapGoldenParser"
        self._settings = None

    def _parse_single_chunk_impl(
        self,
        user_id,
        doc_id,
        chunk_pdf_bytes,
        chunk_index,
        total_chunks,
        page_offset,
        **all_kwargs,
    ) -> Optional[OpenContractDocExport]:
        n = get_pdf_page_count(chunk_pdf_bytes)
        pawls: list = []
        annotations: list = []
        relationships: list = []
        for i in range(n):
            g = page_offset + i
            pawls.append(
                {
                    "page": {"width": 612, "height": 792, "index": i},
                    "tokens": [
                        {"x": 1, "y": 1, "width": 5, "height": 5, "text": f"w{g}"}
                    ],
                }
            )
            annotations.append(
                {
                    "id": f"p{g}",
                    "annotationLabel": "Para",
                    "rawText": f"t{g}",
                    "page": i,
                    "annotation_json": {
                        str(i): {
                            "bounds": {
                                "top": g,
                                "left": 0,
                                "right": 10,
                                "bottom": g + 1,
                            },
                            "tokensJsons": [{"pageIndex": i, "tokenIndex": 0}],
                            "rawText": f"t{g}",
                        }
                    },
                    "parent_id": (f"p{g - 1}" if g > 0 else None),
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                }
            )
            # Forward edge, emitted only when both endpoints are in this chunk's
            # parse range. Cross-boundary edges therefore appear in both adjacent
            # chunks and must collapse after re-linking.
            if i + 1 < n:
                relationships.append(
                    {
                        "id": f"rel{g}",
                        "relationshipLabel": "next",
                        "source_annotation_ids": [f"p{g}"],
                        "target_annotation_ids": [f"p{g + 1}"],
                        "structural": True,
                    }
                )
        return {
            "title": "Golden Doc",
            "content": " ".join(f"w{page_offset + i}" for i in range(n)),
            "description": "d",
            "pawls_file_content": pawls,
            "page_count": n,
            "doc_labels": ["Contract"],
            "labelled_text": annotations,
            "relationships": relationships,
        }


class TestOverlapWiring(TestCase):
    """The parse range fed to each chunk is overlap-extended, and page_offset
    is the parse ``start`` (so reassembly can dedupe by global index)."""

    def _make_doc(self, pages: int) -> Document:
        user = User.objects.create_user(username="ow", password="x")
        doc = Document(creator=user, title="t")
        doc.save()
        doc.pdf_file.save(f"doc_{doc.id}.pdf", ContentFile(make_test_pdf(pages)))
        return doc

    def test_prepare_chunk_inputs_uses_overlap_extended_ranges(self):
        from opencontractserver.pipeline.chunk_artifacts import read_chunk_pdf

        doc = self._make_doc(10)
        parser = _OverlapGoldenParser()
        parser.max_pages_per_chunk = 4
        parser.min_pages_for_chunking = 4
        parser.chunk_overlap = 2

        descriptors = parser.prepare_chunk_inputs(doc.id)
        # cores tile (0,4)(4,8)(8,10) -> parse ranges (0,6)(2,10)(6,10).
        self.assertEqual([d["page_offset"] for d in descriptors], [0, 2, 6])
        self.assertEqual([d["total_chunks"] for d in descriptors], [3, 3, 3])
        page_counts = [
            get_pdf_page_count(read_chunk_pdf(d["input_key"])) for d in descriptors
        ]
        self.assertEqual(page_counts, [6, 8, 4])

    def test_chunk_overlap_defaults_to_constant(self):
        from opencontractserver.constants import DEFAULT_CHUNK_OVERLAP

        self.assertEqual(BaseChunkedParser.chunk_overlap, DEFAULT_CHUNK_OVERLAP)


def _annotation_signatures_by_id(result: OpenContractDocExport) -> dict:
    """Map each surviving annotation ID to its chunk-independent signature."""
    from opencontractserver.pipeline.base.chunk_reassembler import (
        _annotation_signature,
    )

    return {a["id"]: _annotation_signature(a) for a in result["labelled_text"]}


class TestChunkedOverlapGoldenEquivalence(TestCase):
    """Service-level golden gate: chunked-with-overlap == single-shot."""

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(username="golden", password="x")
        self.pages = 10
        self.doc = Document.objects.create(
            title="Golden", file_type="application/pdf", creator=self.user
        )
        self.doc.pdf_file.save("golden.pdf", ContentFile(make_test_pdf(self.pages)))

    def _single_shot(self) -> OpenContractDocExport:
        parser = _OverlapGoldenParser()
        parser.min_pages_for_chunking = self.pages + 1  # never chunk
        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        assert result is not None
        return result

    def _chunked_with_overlap(self) -> OpenContractDocExport:
        parser = _OverlapGoldenParser()
        parser.max_pages_per_chunk = 4
        parser.min_pages_for_chunking = 4
        parser.chunk_overlap = 2
        parser.max_concurrent_chunks = 1  # deterministic ordering
        result = parser._parse_document_impl(user_id=self.user.id, doc_id=self.doc.id)
        assert result is not None
        return result

    def test_pawls_pages_identical(self):
        single = self._single_shot()
        chunked = self._chunked_with_overlap()
        for result in (single, chunked):
            indices = [p["page"]["index"] for p in result["pawls_file_content"]]
            self.assertEqual(indices, list(range(self.pages)))
            texts = [p["tokens"][0]["text"] for p in result["pawls_file_content"]]
            self.assertEqual(texts, [f"w{i}" for i in range(self.pages)])
        self.assertEqual(single["page_count"], chunked["page_count"])

    def test_annotation_set_identical_modulo_ids(self):
        single = self._single_shot()
        chunked = self._chunked_with_overlap()
        single_sigs = sorted(_annotation_signatures_by_id(single).values())
        chunked_sigs = sorted(_annotation_signatures_by_id(chunked).values())
        # One annotation per page, no duplicates, identical logical set.
        self.assertEqual(len(chunked_sigs), self.pages)
        self.assertEqual(single_sigs, chunked_sigs)

    def test_relationships_identical_modulo_ids(self):
        single = self._single_shot()
        chunked = self._chunked_with_overlap()

        def rel_sigs(result):
            id_to_sig = _annotation_signatures_by_id(result)
            sigs = []
            for rel in result["relationships"]:
                src = frozenset(id_to_sig[s] for s in rel["source_annotation_ids"])
                tgt = frozenset(id_to_sig[t] for t in rel["target_annotation_ids"])
                sigs.append((rel["relationshipLabel"], src, tgt))
            return sorted(sigs)

        single_rels = rel_sigs(single)
        chunked_rels = rel_sigs(chunked)
        # One forward edge per adjacent page pair, deduped across boundaries.
        self.assertEqual(len(chunked_rels), self.pages - 1)
        self.assertEqual(single_rels, chunked_rels)

    def test_parent_chain_relinked_with_no_orphans(self):
        chunked = self._chunked_with_overlap()
        id_to_sig = _annotation_signatures_by_id(chunked)
        parented = 0
        for ann in chunked["labelled_text"]:
            pid = ann.get("parent_id")
            if pid is None:
                continue
            parented += 1
            # Every parent reference resolves to a surviving annotation: the
            # cross-boundary chain was re-linked, not orphaned.
            self.assertIn(pid, id_to_sig)
        # p1..p9 each have a parent -> 9 resolved references across 3 chunks.
        self.assertEqual(parented, self.pages - 1)
