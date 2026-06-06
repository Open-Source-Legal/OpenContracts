"""Tests for the optimized document file-URL resolvers.

These resolvers exist because signing an S3/GCS media URL is expensive — on GCS
with IAM signBlob it's a network round trip per ``FieldFile.url``. A
document-list edge selecting ``pdfFile``/``txtExtractFile``/``pawlsParseFile``/
``icon`` would otherwise sign N×4 URLs per request. The per-request memo alone
does NOT help a list query (each (document, field) is unique), so a
cross-request shared cache keyed by blob name signs each blob at most once per
TTL window. See ``config/graphql/optimized_file_resolvers.py``.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from config.graphql.optimized_file_resolvers import create_file_resolver


class _CountingFieldFile:
    """Stand-in for a Django ``FieldFile`` that counts ``.url`` accesses (each
    access models one expensive signing round trip)."""

    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self._url = url
        self.url_calls = 0

    def __bool__(self) -> bool:
        return bool(self.name)

    @property
    def url(self) -> str:
        self.url_calls += 1
        return self._url


class _Doc:
    def __init__(self, doc_id: int, field_name: str, file_obj) -> None:
        self.id = doc_id
        setattr(self, field_name, file_obj)


class _Ctx:
    def build_absolute_uri(self, url: str) -> str:
        if url.startswith("/"):
            return f"http://testserver{url}"
        return url


class _Info:
    """Fresh context per instance == a distinct request."""

    def __init__(self) -> None:
        self.context = _Ctx()


class OptimizedFileResolverTests(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()
        self.resolver = create_file_resolver("pdf_file")

    def test_empty_field_returns_empty_string(self) -> None:
        doc = _Doc(1, "pdf_file", _CountingFieldFile("", ""))
        self.assertEqual(self.resolver(doc, _Info()), "")

    def test_per_request_memo_signs_once(self) -> None:
        """Same (document, field) resolved twice in one request signs once."""
        f = _CountingFieldFile("media/a.pdf", "https://signed/a")
        doc = _Doc(1, "pdf_file", f)
        info = _Info()

        self.assertEqual(self.resolver(doc, info), "https://signed/a")
        self.assertEqual(self.resolver(doc, info), "https://signed/a")
        self.assertEqual(f.url_calls, 1)

    @override_settings(FILE_URL_SHARED_CACHE_TTL=600)
    def test_shared_cache_signs_blob_once_across_requests(self) -> None:
        """A blob is signed once even across separate requests / documents."""
        f1 = _CountingFieldFile("media/shared.pdf", "https://signed/shared")
        f2 = _CountingFieldFile("media/shared.pdf", "https://signed/shared")

        url1 = self.resolver(_Doc(1, "pdf_file", f1), _Info())
        # Second request, different document object, SAME blob name.
        url2 = self.resolver(_Doc(2, "pdf_file", f2), _Info())

        self.assertEqual(url1, "https://signed/shared")
        self.assertEqual(url2, "https://signed/shared")
        self.assertEqual(f1.url_calls, 1)
        self.assertEqual(f2.url_calls, 0)  # served from the shared cache

    @override_settings(FILE_URL_SHARED_CACHE_TTL=0)
    def test_shared_cache_disabled_signs_each_request(self) -> None:
        """TTL=0 (LOCAL storage) keeps the old per-request-only behavior."""
        f1 = _CountingFieldFile("media/x.pdf", "https://signed/x")
        f2 = _CountingFieldFile("media/x.pdf", "https://signed/x")

        self.resolver(_Doc(1, "pdf_file", f1), _Info())
        self.resolver(_Doc(2, "pdf_file", f2), _Info())

        self.assertEqual(f1.url_calls, 1)
        self.assertEqual(f2.url_calls, 1)  # no shared cache -> signed again

    @override_settings(FILE_URL_SHARED_CACHE_TTL=600)
    def test_relative_url_made_absolute_after_cache(self) -> None:
        """A cached RAW (relative) URL is still host-qualified per request."""
        f1 = _CountingFieldFile("media/rel.pdf", "/media/rel.pdf")
        f2 = _CountingFieldFile("media/rel.pdf", "/media/rel.pdf")

        url1 = self.resolver(_Doc(1, "pdf_file", f1), _Info())
        url2 = self.resolver(_Doc(2, "pdf_file", f2), _Info())

        self.assertEqual(url1, "http://testserver/media/rel.pdf")
        self.assertEqual(url2, "http://testserver/media/rel.pdf")
        self.assertEqual(f2.url_calls, 0)
