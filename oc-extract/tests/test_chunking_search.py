from __future__ import annotations

from oc_extract.chunking import chunk_text, page_for_offset
from oc_extract.search import BM25Index

from .conftest import SAMPLE_CONTRACT


def test_chunk_offsets_reconstruct_text():
    chunks = chunk_text(SAMPLE_CONTRACT, max_chars=200)
    assert chunks
    for chunk in chunks:
        assert SAMPLE_CONTRACT[chunk.start : chunk.end] == chunk.text


def test_oversized_paragraph_hard_split():
    text = "x" * 5000
    chunks = chunk_text(text, max_chars=1000)
    assert len(chunks) == 5
    assert all(len(c.text) <= 1000 for c in chunks)


def test_page_assignment():
    offsets = [0, 100, 250]
    assert page_for_offset(offsets, 0) == 1
    assert page_for_offset(offsets, 99) == 1
    assert page_for_offset(offsets, 100) == 2
    assert page_for_offset(offsets, 400) == 3
    assert page_for_offset(None, 5) is None


def test_bm25_finds_relevant_chunk():
    chunks = chunk_text(SAMPLE_CONTRACT, max_chars=200)
    index = BM25Index(chunks)
    hits = index.search("monthly fee payment invoice", k=3)
    assert hits
    assert "12,500" in hits[0][0].text


def test_bm25_must_contain_filter():
    chunks = chunk_text(SAMPLE_CONTRACT, max_chars=200)
    index = BM25Index(chunks)
    hits = index.search("agreement", k=10, must_contain="governing law")
    assert hits
    assert all(
        "governed" in c.text.lower() or "governing" in c.text.lower() for c, _ in hits
    )


def test_bm25_no_match_returns_empty():
    chunks = chunk_text(SAMPLE_CONTRACT, max_chars=200)
    index = BM25Index(chunks)
    assert index.search("zebra quantum blockchain", k=3) == []
