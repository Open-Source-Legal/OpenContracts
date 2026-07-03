"""Dependency-free lexical retrieval (BM25) over document chunks.

This is the lightweight stand-in for OpenContracts' hybrid
pgvector + Postgres-FTS retrieval: the agent's ``search_document`` tool ranks
chunks with BM25 so no embedding model or vector database is required.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .chunking import Chunk
from .constants import BM25_B, BM25_K1, SEARCH_TOP_K

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """A tiny in-memory BM25 index over a document's chunks."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._tfs: list[Counter] = [Counter(tokenize(c.text)) for c in chunks]
        self._doc_lens = [sum(tf.values()) for tf in self._tfs]
        self._avg_len = (
            sum(self._doc_lens) / len(self._doc_lens) if self._doc_lens else 0.0
        )
        df: Counter = Counter()
        for tf in self._tfs:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {
            term: math.log(1 + (n - count + 0.5) / (count + 0.5))
            for term, count in df.items()
        }

    def search(
        self,
        query: str,
        k: int = SEARCH_TOP_K,
        must_contain: str | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Top-*k* chunks for *query*, optionally hard-filtered to chunks
        containing *must_contain* (case-insensitive substring)."""
        terms = tokenize(query)
        needle = must_contain.casefold() if must_contain else None
        scored: list[tuple[Chunk, float]] = []
        for chunk, tf, doc_len in zip(self.chunks, self._tfs, self._doc_lens):
            if needle is not None and needle not in chunk.text.casefold():
                continue
            score = 0.0
            for term in terms:
                freq = tf.get(term)
                if not freq:
                    continue
                idf = self._idf.get(term, 0.0)
                denom = freq + BM25_K1 * (
                    1 - BM25_B + BM25_B * doc_len / (self._avg_len or 1.0)
                )
                score += idf * freq * (BM25_K1 + 1) / denom
            if score > 0.0:
                scored.append((chunk, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]
