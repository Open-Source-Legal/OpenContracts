"""Tests for chunk-artifact storage helpers."""

from django.core.files.storage import default_storage
from django.test import TestCase

from opencontractserver.pipeline.chunk_artifacts import (
    chunk_input_key,
    chunk_output_key,
    cleanup_chunk_artifacts,
    read_chunk_pdf,
    read_chunk_result,
    write_chunk_pdf,
    write_chunk_result,
)


class TestChunkArtifacts(TestCase):
    def test_key_namespacing_is_per_doc_and_index(self):
        self.assertEqual(chunk_input_key(7, 2), "chunk_scratch/doc_7/in_2.pdf")
        self.assertEqual(chunk_output_key(7, 2), "chunk_scratch/doc_7/out_2.json")

    def test_pdf_round_trip(self):
        key = write_chunk_pdf(7, 0, b"%PDF-1.4 fake")
        self.assertEqual(key, chunk_input_key(7, 0))
        self.assertEqual(read_chunk_pdf(key), b"%PDF-1.4 fake")

    def test_result_round_trip(self):
        payload = {"title": "t", "page_count": 3, "pawls_file_content": []}
        key = write_chunk_result(7, 1, payload)
        self.assertEqual(key, chunk_output_key(7, 1))
        self.assertEqual(read_chunk_result(key), payload)

    def test_cleanup_removes_all_doc_artifacts(self):
        write_chunk_pdf(9, 0, b"a")
        write_chunk_pdf(9, 1, b"b")
        write_chunk_result(9, 0, {"x": 1})
        cleanup_chunk_artifacts(9)
        self.assertFalse(default_storage.exists(chunk_input_key(9, 0)))
        self.assertFalse(default_storage.exists(chunk_input_key(9, 1)))
        self.assertFalse(default_storage.exists(chunk_output_key(9, 0)))

    def test_cleanup_is_idempotent(self):
        cleanup_chunk_artifacts(123456)
