"""Tests for the concurrent document file-URL pre-warm middleware.

The middleware pre-signs a Document connection page's *requested* file URLs in
a thread pool and warms ``info.context._file_url_cache`` so the per-node
``optimized_file_resolvers`` return from cache instead of signing serially.
See ``config/graphql/file_url_prewarm.py``.
"""

from __future__ import annotations

import threading
from typing import Any

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from graphql import OperationDefinitionNode, parse

from config.graphql.file_url_prewarm import (
    FileUrlPrewarmMiddleware,
    _requested_document_file_fields,
)
from config.graphql.optimized_file_resolvers import _FILE_URL_CACHE_PREFIX


class _CountingFieldFile:
    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self._url = url
        self.url_calls = 0
        self._lock = threading.Lock()

    def __bool__(self) -> bool:
        return bool(self.name)

    @property
    def url(self) -> str:
        with self._lock:
            self.url_calls += 1
        return self._url


class _Doc:
    def __init__(self, doc_id: int, **files) -> None:
        self.id = doc_id
        for field, value in files.items():
            setattr(self, field, value)


class _Edge:
    def __init__(self, node) -> None:
        self.node = node


class _Connection:
    def __init__(self, nodes) -> None:
        self.edges = [_Edge(n) for n in nodes]


class _Ctx:
    def build_absolute_uri(self, url: str) -> str:
        return f"http://testserver{url}" if url.startswith("/") else url


class _Info:
    def __init__(self, field_nodes) -> None:
        self.field_nodes = field_nodes
        self.fragments: dict = {}
        self.context = _Ctx()


def _info_for(query: str) -> _Info:
    """Build an _Info whose field_nodes is the top-level ``documents`` field."""
    document = parse(query)
    operation = document.definitions[0]
    assert isinstance(operation, OperationDefinitionNode)
    documents_field = operation.selection_set.selections[0]
    return _Info([documents_field])


_QUERY = """
query {
  documents {
    edges { node { id pdfFile icon } }
  }
}
"""


class RequestedFileFieldsTests(SimpleTestCase):
    def test_maps_camelcase_to_model_fields(self) -> None:
        info = _info_for(_QUERY)
        self.assertEqual(_requested_document_file_fields(info), {"pdf_file", "icon"})

    def test_ignores_unselected_file_fields(self) -> None:
        info = _info_for("query { documents { edges { node { id title } } } }")
        self.assertEqual(_requested_document_file_fields(info), set())


@override_settings(FILE_URL_SHARED_CACHE_TTL=600)
class PrewarmTests(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()

    def _docs(self):
        return [
            _Doc(
                1,
                pdf_file=_CountingFieldFile("media/1.pdf", "https://s/1.pdf"),
                icon=_CountingFieldFile("media/1.png", "https://s/1.png"),
            ),
            _Doc(
                2,
                pdf_file=_CountingFieldFile("media/2.pdf", "https://s/2.pdf"),
                icon=_CountingFieldFile("media/2.png", "https://s/2.png"),
            ),
        ]

    def test_prewarm_populates_request_cache(self) -> None:
        docs = self._docs()
        info = _info_for(_QUERY)

        FileUrlPrewarmMiddleware._prewarm(_Connection(docs), info)

        memo: dict[str, Any] = getattr(info.context, "_file_url_cache")
        self.assertEqual(memo["1:pdf_file"], "https://s/1.pdf")
        self.assertEqual(memo["1:icon"], "https://s/1.png")
        self.assertEqual(memo["2:pdf_file"], "https://s/2.pdf")
        self.assertEqual(memo["2:icon"], "https://s/2.png")
        # Each blob signed exactly once.
        for doc in docs:
            self.assertEqual(doc.pdf_file.url_calls, 1)
            self.assertEqual(doc.icon.url_calls, 1)

    def test_prewarm_writes_through_to_shared_cache(self) -> None:
        docs = self._docs()
        FileUrlPrewarmMiddleware._prewarm(_Connection(docs), _info_for(_QUERY))
        self.assertEqual(
            cache.get(f"{_FILE_URL_CACHE_PREFIX}media/1.pdf"), "https://s/1.pdf"
        )

    def test_prewarm_uses_shared_cache_hit(self) -> None:
        # Seed the shared cache for doc 1's pdf; it must not be re-signed.
        cache.set(f"{_FILE_URL_CACHE_PREFIX}media/1.pdf", "https://cached/1.pdf", 600)
        docs = self._docs()
        info = _info_for(_QUERY)

        FileUrlPrewarmMiddleware._prewarm(_Connection(docs), info)

        # Served from the shared cache: not re-signed, but still memoized.
        self.assertEqual(docs[0].pdf_file.url_calls, 0)
        memo: dict[str, Any] = getattr(info.context, "_file_url_cache")
        self.assertEqual(memo["1:pdf_file"], "https://cached/1.pdf")
        # Doc 1's icon (not seeded) IS signed.
        self.assertEqual(docs[0].icon.url_calls, 1)

    def test_noop_when_ttl_zero(self) -> None:
        docs = self._docs()
        info = _info_for(_QUERY)
        with override_settings(FILE_URL_SHARED_CACHE_TTL=0):
            FileUrlPrewarmMiddleware._prewarm(_Connection(docs), info)
        self.assertFalse(hasattr(info.context, "_file_url_cache"))
        for doc in docs:
            self.assertEqual(doc.pdf_file.url_calls, 0)
