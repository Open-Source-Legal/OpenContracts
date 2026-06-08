"""Tests for the incremental ChunkReassembler."""

from django.test import TestCase

from opencontractserver.pipeline.base.chunk_reassembler import ChunkReassembler
from opencontractserver.tests.test_chunked_parser import _make_chunk_result


class TestChunkReassembler(TestCase):
    def test_incremental_matches_contiguous_indices(self):
        r = ChunkReassembler()
        r.add_chunk(_make_chunk_result(num_pages=2), page_offset=0, chunk_index=0)
        r.add_chunk(_make_chunk_result(num_pages=2), page_offset=2, chunk_index=1)
        r.add_chunk(_make_chunk_result(num_pages=2), page_offset=4, chunk_index=2)
        result = r.finalize()
        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 2, 3, 4, 5])
        self.assertEqual(result["page_count"], 6)

    def test_ids_prefixed_per_chunk_index(self):
        r = ChunkReassembler()
        r.add_chunk(_make_chunk_result(), page_offset=0, chunk_index=0)
        r.add_chunk(_make_chunk_result(), page_offset=2, chunk_index=1)
        ids = [a["id"] for a in r.finalize()["labelled_text"]]
        self.assertEqual(ids, ["c0_ann-1", "c1_ann-1"])

    def test_finalize_on_empty_raises(self):
        with self.assertRaises(ValueError):
            ChunkReassembler().finalize()
