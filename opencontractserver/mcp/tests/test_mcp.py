"""Tests for MCP server functionality."""

import asyncio
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase, override_settings

from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class _MCPAsyncRunMixin:
    """Shared helper for running an async coroutine inside a sync test method.

    Uses ``asyncio.run()`` so each invocation creates and tears down a
    fully isolated event loop without ever calling
    ``asyncio.set_event_loop()`` on the calling thread. The earlier
    ``new_event_loop`` → ``run_until_complete`` → ``set_event_loop(None)``
    dance worked sequentially but mutated thread-global event-loop state,
    which would race if pytest-xdist ever scheduled two async test
    methods on the same OS thread. ``asyncio.run`` (Python 3.11+) is the
    standard, race-free pattern for "run one coroutine and clean up
    after yourself".
    """

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    @staticmethod
    def _close_async_db_connections() -> None:
        """Close DB connections held by the ``sync_to_async`` thread-pool worker.

        ``call_tool_handler`` dispatches sync ORM work via
        ``asgiref.sync.sync_to_async`` which runs the handler on a shared
        thread-pool worker. ``django.db.connections`` is thread-local, so
        the main thread's ``connections.close_all()`` does NOT touch the
        worker's connection. If postgres ever terminates that worker's
        backend mid-query (transient OOM / timeout / network blip), the
        worker keeps the broken ``DatabaseWrapper`` instance and
        ``ensure_connection()`` won't reopen it — every subsequent test in
        the same class fails with ``InterfaceError: connection already
        closed``. Closing the worker's connection in tearDown scopes the
        blast radius to the originally-failing test.
        """
        from asgiref.sync import sync_to_async
        from django import db

        try:
            asyncio.run(sync_to_async(db.connections.close_all)())
        except Exception as exc:
            # If the worker thread itself is gone or the event loop refuses
            # to spin up cleanly, fall through — the main-thread close
            # below is still useful and we don't want tearDown to mask a
            # test failure. Log at DEBUG so transient infra issues stay
            # visible instead of silently disappearing.
            import logging

            logging.getLogger(__name__).debug("tearDown async DB close failed: %s", exc)


class URIParserTest(TestCase):
    """Tests for MCP URI parsing."""

    def test_parse_corpus_uri(self):
        """Test parsing corpus URIs."""
        from opencontractserver.mcp.server import URIParser

        # Valid URI
        result = URIParser.parse_corpus("corpus://my-corpus")
        self.assertEqual(result, "my-corpus")

        # More complex slugs
        result = URIParser.parse_corpus("corpus://Legal-Contracts-2024")
        self.assertEqual(result, "Legal-Contracts-2024")

        # Invalid URIs
        self.assertIsNone(URIParser.parse_corpus("corpus://"))
        self.assertIsNone(URIParser.parse_corpus("document://my-corpus"))
        self.assertIsNone(URIParser.parse_corpus("corpus://my corpus"))  # space invalid
        self.assertIsNone(
            URIParser.parse_corpus("corpus://my_corpus")
        )  # underscore invalid

    def test_parse_document_uri(self):
        """Test parsing document URIs."""
        from opencontractserver.mcp.server import URIParser

        result = URIParser.parse_document("document://my-corpus/my-doc")
        self.assertEqual(result, ("my-corpus", "my-doc"))

        result = URIParser.parse_document("document://corp-1/doc-2024")
        self.assertEqual(result, ("corp-1", "doc-2024"))

        self.assertIsNone(URIParser.parse_document("document://my-corpus"))
        self.assertIsNone(URIParser.parse_document("document://"))

    def test_parse_annotation_uri(self):
        """Test parsing annotation URIs."""
        from opencontractserver.mcp.server import URIParser

        result = URIParser.parse_annotation("annotation://corp/doc/123")
        self.assertEqual(result, ("corp", "doc", 123))

        result = URIParser.parse_annotation("annotation://my-corpus/my-doc/999")
        self.assertEqual(result, ("my-corpus", "my-doc", 999))

        self.assertIsNone(URIParser.parse_annotation("annotation://corp/doc"))
        self.assertIsNone(URIParser.parse_annotation("annotation://corp/doc/abc"))

    def test_parse_thread_uri(self):
        """Test parsing thread URIs."""
        from opencontractserver.mcp.server import URIParser

        result = URIParser.parse_thread("thread://my-corpus/threads/456")
        self.assertEqual(result, ("my-corpus", 456))

        result = URIParser.parse_thread("thread://legal-2024/threads/1")
        self.assertEqual(result, ("legal-2024", 1))

        self.assertIsNone(URIParser.parse_thread("thread://my-corpus/456"))
        self.assertIsNone(URIParser.parse_thread("thread://my-corpus/threads/"))


class MCPPermissionsTest(TestCase):
    """Tests for MCP permission validation."""

    def test_validate_slug(self):
        """Test slug validation."""
        from opencontractserver.mcp.permissions import validate_slug

        # Valid slugs
        self.assertTrue(validate_slug("my-corpus"))
        self.assertTrue(validate_slug("MyCorpus123"))
        self.assertTrue(validate_slug("test-doc-2024"))
        self.assertTrue(validate_slug("ABC"))
        self.assertTrue(validate_slug("123"))

        # Invalid slugs
        self.assertFalse(validate_slug("my corpus"))  # space
        self.assertFalse(validate_slug("my_corpus"))  # underscore
        self.assertFalse(validate_slug(""))
        self.assertFalse(validate_slug("my@corpus"))  # special char

    def test_sanitize_and_validate_slugs(self):
        """Test slug sanitization and validation."""
        from opencontractserver.mcp.permissions import sanitize_and_validate_slugs

        # Valid slugs pass through
        result = sanitize_and_validate_slugs("my-corpus", "my-doc")
        self.assertEqual(result, ("my-corpus", "my-doc"))

        # None document slug is allowed
        result = sanitize_and_validate_slugs("my-corpus", None)
        self.assertEqual(result, ("my-corpus", None))

        # Invalid corpus slug raises
        with self.assertRaises(ValueError):
            sanitize_and_validate_slugs("my corpus")

        # Invalid document slug raises
        with self.assertRaises(ValueError):
            sanitize_and_validate_slugs("my-corpus", "my_doc")

    def test_get_anonymous_user(self):
        """Test anonymous user helper."""
        from opencontractserver.mcp.permissions import get_anonymous_user

        user = get_anonymous_user()
        self.assertIsInstance(user, AnonymousUser)
        self.assertFalse(user.is_authenticated)


class MCPResourcesTest(TestCase):
    """Tests for MCP resource handlers."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.owner = User.objects.create_user(
            username="testowner", email="owner@test.com", password="testpass123"
        )

        # Create public corpus
        cls.public_corpus = Corpus.objects.create(
            title="Public Test Corpus",
            description="A public test corpus",
            creator=cls.owner,
            is_public=True,
        )

        # Create private corpus
        cls.private_corpus = Corpus.objects.create(
            title="Private Test Corpus",
            description="A private test corpus",
            creator=cls.owner,
            is_public=False,
        )

    def test_get_public_corpus_resource(self):
        """Anonymous users can access public corpus resources."""
        from opencontractserver.mcp.resources import get_corpus_resource

        result = get_corpus_resource(self.public_corpus.slug)
        data = json.loads(result)

        self.assertEqual(data["slug"], self.public_corpus.slug)
        self.assertEqual(data["title"], "Public Test Corpus")
        self.assertEqual(data["description"], "A public test corpus")

    def test_get_private_corpus_resource_denied(self):
        """Anonymous users cannot access private corpus resources."""
        from opencontractserver.mcp.resources import get_corpus_resource

        with self.assertRaises(Corpus.DoesNotExist):
            get_corpus_resource(self.private_corpus.slug)


class MCPToolsTest(TestCase):
    """Tests for MCP tool handlers."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.owner = User.objects.create_user(
            username="toolsowner", email="tools@test.com", password="testpass123"
        )

        # Create public corpuses
        cls.corpus1 = Corpus.objects.create(
            title="Corpus One",
            description="First corpus",
            creator=cls.owner,
            is_public=True,
        )
        cls.corpus2 = Corpus.objects.create(
            title="Corpus Two",
            description="Second corpus",
            creator=cls.owner,
            is_public=True,
        )

        # Create private corpus (should not appear)
        cls.private = Corpus.objects.create(
            title="Private Corpus", creator=cls.owner, is_public=False
        )

    def test_list_public_corpuses(self):
        """Test listing public corpuses."""
        from opencontractserver.mcp.tools import list_public_corpuses

        result = list_public_corpuses()

        self.assertIn("total_count", result)
        self.assertIn("corpuses", result)

        # Should only include public corpuses
        slugs = [c["slug"] for c in result["corpuses"]]
        self.assertIn(self.corpus1.slug, slugs)
        self.assertIn(self.corpus2.slug, slugs)
        self.assertNotIn(self.private.slug, slugs)

    def test_list_public_corpuses_with_search(self):
        """Test searching corpuses."""
        from opencontractserver.mcp.tools import list_public_corpuses

        result = list_public_corpuses(search="One")

        slugs = [c["slug"] for c in result["corpuses"]]
        self.assertIn(self.corpus1.slug, slugs)
        self.assertNotIn(self.corpus2.slug, slugs)

    def test_list_public_corpuses_pagination(self):
        """Test pagination."""
        from opencontractserver.mcp.tools import list_public_corpuses

        result = list_public_corpuses(limit=1, offset=0)
        self.assertEqual(len(result["corpuses"]), 1)

        result2 = list_public_corpuses(limit=1, offset=1)
        self.assertEqual(len(result2["corpuses"]), 1)

        # Different results
        self.assertNotEqual(
            result["corpuses"][0]["slug"], result2["corpuses"][0]["slug"]
        )

    def test_list_public_corpuses_max_limit(self):
        """Test that limit is capped at 100."""
        from opencontractserver.mcp.tools import list_public_corpuses

        # Even with a huge limit, should be capped
        result = list_public_corpuses(limit=1000)
        # The function caps at 100, but we only have 2 public corpuses
        self.assertLessEqual(len(result["corpuses"]), 100)


class MCPFormattersTest(TestCase):
    """Tests for MCP response formatters."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="formatowner", email="format@test.com", password="testpass123"
        )

        cls.corpus = Corpus.objects.create(
            title="Format Test Corpus",
            description="Testing formatters",
            creator=cls.owner,
            is_public=True,
        )

    def test_format_corpus_summary(self):
        """Test corpus summary formatting."""
        from opencontractserver.mcp.formatters import format_corpus_summary

        result = format_corpus_summary(self.corpus)

        self.assertEqual(result["slug"], self.corpus.slug)
        self.assertEqual(result["title"], "Format Test Corpus")
        self.assertEqual(result["description"], "Testing formatters")
        self.assertIn("created", result)
        self.assertIn("document_count", result)


class MCPConfigTest(TestCase):
    """Tests for MCP configuration."""

    def test_get_mcp_setting_with_default(self):
        """Test getting settings with defaults."""
        from opencontractserver.mcp.config import get_mcp_setting

        # Non-existent key returns default
        result = get_mcp_setting("nonexistent_key", "default_value")
        self.assertEqual(result, "default_value")

    def test_validate_slug(self):
        """Test slug validation in config."""
        from opencontractserver.mcp.config import validate_slug

        self.assertTrue(validate_slug("valid-slug"))
        self.assertTrue(validate_slug("Valid123"))
        self.assertFalse(validate_slug("invalid_slug"))
        self.assertFalse(validate_slug("invalid slug"))


class MCPRateLimiterTest(TestCase):
    """Tests for MCP rate limiting via the shared engine."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    @override_settings(RATELIMIT_DISABLE=False)
    def test_rate_limiter_allows_requests(self):
        """Test that the shared engine allows requests under the MCP global limit."""
        import asyncio

        from config.ratelimit.decorators import check_mcp_rate_limit

        scope = {"headers": [], "client": ("10.0.0.1", 8080)}

        # First request should be allowed
        is_limited, _, _ = asyncio.run(check_mcp_rate_limit(scope))
        self.assertFalse(is_limited)

    @override_settings(RATELIMIT_DISABLE=False)
    def test_rate_limiter_blocks_excess_requests(self):
        """Test that the shared engine blocks requests over the MCP global limit."""
        import asyncio
        from unittest.mock import patch

        from config.ratelimit.decorators import check_mcp_rate_limit
        from config.ratelimit.rates import RateLimits

        scope = {"headers": [], "client": ("10.0.0.2", 8080)}
        test_limit = 3

        async def _exhaust_and_check():
            # Exhaust the limit
            for _ in range(test_limit):
                await check_mcp_rate_limit(scope)
            # Next should be blocked
            return await check_mcp_rate_limit(scope)

        with patch("config.ratelimit.engine.time") as mock_time:
            mock_time.time.return_value = 1000000.0
            original_rate = RateLimits.MCP_GLOBAL
            RateLimits.MCP_GLOBAL = f"{test_limit}/m"
            try:
                is_limited, _, _ = asyncio.run(_exhaust_and_check())
                self.assertTrue(is_limited)
            finally:
                RateLimits.MCP_GLOBAL = original_rate

    @override_settings(RATELIMIT_DISABLE=False)
    def test_rate_limiter_separate_clients(self):
        """Test that different IPs have independent rate limit buckets."""
        import asyncio
        from unittest.mock import patch

        from config.ratelimit.decorators import check_mcp_rate_limit
        from config.ratelimit.rates import RateLimits

        scope_a = {"headers": [], "client": ("10.0.0.3", 8080)}
        scope_b = {"headers": [], "client": ("10.0.0.4", 8080)}
        test_limit = 3

        async def _exhaust_a_and_check_both():
            # Exhaust client-a
            for _ in range(test_limit):
                await check_mcp_rate_limit(scope_a)
            is_limited_a, _, _ = await check_mcp_rate_limit(scope_a)
            # client-b should still be fine
            is_limited_b, _, _ = await check_mcp_rate_limit(scope_b)
            return is_limited_a, is_limited_b

        with patch("config.ratelimit.engine.time") as mock_time:
            mock_time.time.return_value = 1000000.0
            original_rate = RateLimits.MCP_GLOBAL
            RateLimits.MCP_GLOBAL = f"{test_limit}/m"
            try:
                is_limited_a, is_limited_b = asyncio.run(_exhaust_a_and_check_both())
                self.assertTrue(is_limited_a)
                self.assertFalse(is_limited_b)
            finally:
                RateLimits.MCP_GLOBAL = original_rate


class MCPToolsDocumentsTest(TestCase):
    """Tests for MCP document-related tools."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with documents."""
        from django.core.files.base import ContentFile

        from opencontractserver.annotations.models import AnnotationLabel
        from opencontractserver.documents.models import Document, DocumentPath

        cls.owner = User.objects.create_user(
            username="doctoolsowner", email="doctools@test.com", password="testpass123"
        )

        # Create public corpus
        cls.corpus = Corpus.objects.create(
            title="Document Test Corpus",
            description="Test corpus with documents",
            creator=cls.owner,
            is_public=True,
        )

        # Create a private corpus (for testing access denial)
        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=cls.owner,
            is_public=False,
        )

        # Create documents
        cls.doc1 = Document.objects.create(
            title="Test Document One",
            description="First test document",
            creator=cls.owner,
            is_public=True,
            page_count=5,
        )
        # Add text file to doc1
        cls.doc1.txt_extract_file.save(
            "test_doc1.txt", ContentFile(b"This is the test document text content.")
        )

        cls.doc2 = Document.objects.create(
            title="Test Document Two",
            description="Second test document",
            creator=cls.owner,
            is_public=True,
            page_count=10,
        )

        # Create document without text file
        cls.doc_no_text = Document.objects.create(
            title="Document Without Text",
            description="No extracted text",
            creator=cls.owner,
            is_public=True,
        )

        # Create DocumentPaths to link documents to corpus
        DocumentPath.objects.create(
            document=cls.doc1,
            corpus=cls.corpus,
            path="/doc1.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )
        DocumentPath.objects.create(
            document=cls.doc2,
            corpus=cls.corpus,
            path="/doc2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )
        DocumentPath.objects.create(
            document=cls.doc_no_text,
            corpus=cls.corpus,
            path="/doc_no_text.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )

        # Create an annotation label
        cls.label = AnnotationLabel.objects.create(
            text="Test Label",
            color="#FF0000",
            label_type="TOKEN_LABEL",
            creator=cls.owner,
            is_public=True,
        )

    def test_list_documents(self):
        """Test listing documents in a corpus."""
        from opencontractserver.mcp.tools import list_documents

        result = list_documents(self.corpus.slug)

        self.assertIn("total_count", result)
        self.assertIn("documents", result)
        self.assertEqual(result["total_count"], 3)
        self.assertEqual(len(result["documents"]), 3)

        # Check document structure
        slugs = [d["slug"] for d in result["documents"]]
        self.assertIn(self.doc1.slug, slugs)
        self.assertIn(self.doc2.slug, slugs)

    def test_list_documents_with_search(self):
        """Test searching documents."""
        from opencontractserver.mcp.tools import list_documents

        result = list_documents(self.corpus.slug, search="One")

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["documents"][0]["slug"], self.doc1.slug)

    def test_list_documents_pagination(self):
        """Test document pagination."""
        from opencontractserver.mcp.tools import list_documents

        result1 = list_documents(self.corpus.slug, limit=1, offset=0)
        result2 = list_documents(self.corpus.slug, limit=1, offset=1)

        self.assertEqual(len(result1["documents"]), 1)
        self.assertEqual(len(result2["documents"]), 1)
        self.assertNotEqual(
            result1["documents"][0]["slug"], result2["documents"][0]["slug"]
        )

    def test_list_documents_max_limit(self):
        """Test that limit is capped at 100."""
        from opencontractserver.mcp.tools import list_documents

        # Should not raise even with huge limit
        result = list_documents(self.corpus.slug, limit=1000)
        self.assertLessEqual(len(result["documents"]), 100)

    def test_list_documents_private_corpus_denied(self):
        """Test that private corpus documents are not accessible."""
        from opencontractserver.mcp.tools import list_documents

        with self.assertRaises(Corpus.DoesNotExist):
            list_documents(self.private_corpus.slug)

    def test_get_document_text(self):
        """Test retrieving document text."""
        from opencontractserver.mcp.tools import get_document_text

        result = get_document_text(self.corpus.slug, self.doc1.slug)

        self.assertEqual(result["document_slug"], self.doc1.slug)
        self.assertEqual(result["page_count"], 5)
        # Note: File storage in tests may not persist, so we just verify the structure
        self.assertIn("text", result)

    def test_get_document_text_no_file(self):
        """Test retrieving document text when no text file exists."""
        from opencontractserver.mcp.tools import get_document_text

        result = get_document_text(self.corpus.slug, self.doc_no_text.slug)

        self.assertEqual(result["document_slug"], self.doc_no_text.slug)
        self.assertEqual(result["text"], "")

    def test_get_document_text_nonexistent(self):
        """Test accessing nonexistent document."""
        from opencontractserver.documents.models import Document
        from opencontractserver.mcp.tools import get_document_text

        with self.assertRaises(Document.DoesNotExist):
            get_document_text(self.corpus.slug, "nonexistent-doc")


class MCPToolsAnnotationsTest(TestCase):
    """Tests for MCP annotation-related tools."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with annotations."""
        from opencontractserver.annotations.models import Annotation, AnnotationLabel
        from opencontractserver.documents.models import Document, DocumentPath

        cls.owner = User.objects.create_user(
            username="anntoolsowner",
            email="anntools@test.com",
            password="testpass123",
        )

        cls.corpus = Corpus.objects.create(
            title="Annotation Test Corpus",
            creator=cls.owner,
            is_public=True,
        )

        cls.document = Document.objects.create(
            title="Annotated Document",
            creator=cls.owner,
            is_public=True,
            page_count=3,
        )

        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/annotated.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )

        cls.label1 = AnnotationLabel.objects.create(
            text="Header",
            color="#0000FF",
            label_type="TOKEN_LABEL",
            creator=cls.owner,
            is_public=True,
        )

        cls.label2 = AnnotationLabel.objects.create(
            text="Paragraph",
            color="#00FF00",
            label_type="TOKEN_LABEL",
            creator=cls.owner,
            is_public=True,
        )

        # Create annotations
        cls.ann1 = Annotation.objects.create(
            page=1,
            raw_text="This is a header",
            annotation_label=cls.label1,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.owner,
            is_public=True,
        )

        cls.ann2 = Annotation.objects.create(
            page=1,
            raw_text="This is a paragraph",
            annotation_label=cls.label2,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.owner,
            is_public=True,
        )

        cls.ann3 = Annotation.objects.create(
            page=2,
            raw_text="Page 2 content",
            annotation_label=cls.label1,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.owner,
            is_public=True,
        )

    def test_list_annotations(self):
        """Test listing annotations on a document."""
        from opencontractserver.mcp.tools import list_annotations

        result = list_annotations(self.corpus.slug, self.document.slug)

        self.assertIn("total_count", result)
        self.assertIn("annotations", result)
        self.assertEqual(result["total_count"], 3)

    def test_list_annotations_filter_by_page(self):
        """Test filtering annotations by page."""
        from opencontractserver.mcp.tools import list_annotations

        result = list_annotations(self.corpus.slug, self.document.slug, page=1)

        self.assertEqual(result["total_count"], 2)
        for ann in result["annotations"]:
            self.assertEqual(ann["page"], 1)

    def test_list_annotations_filter_by_label(self):
        """Test filtering annotations by label text."""
        from opencontractserver.mcp.tools import list_annotations

        result = list_annotations(
            self.corpus.slug, self.document.slug, label_text="Header"
        )

        self.assertEqual(result["total_count"], 2)
        for ann in result["annotations"]:
            self.assertEqual(ann["annotation_label"]["text"], "Header")

    def test_list_annotations_pagination(self):
        """Test annotation pagination."""
        from opencontractserver.mcp.tools import list_annotations

        result1 = list_annotations(self.corpus.slug, self.document.slug, limit=1)
        result2 = list_annotations(
            self.corpus.slug, self.document.slug, limit=1, offset=1
        )

        self.assertEqual(len(result1["annotations"]), 1)
        self.assertEqual(len(result2["annotations"]), 1)
        self.assertNotEqual(
            result1["annotations"][0]["id"], result2["annotations"][0]["id"]
        )


class MCPToolsSearchTest(TestCase):
    """Tests for MCP search functionality."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for search."""
        from opencontractserver.documents.models import Document, DocumentPath

        cls.owner = User.objects.create_user(
            username="searchowner", email="search@test.com", password="testpass123"
        )

        cls.corpus = Corpus.objects.create(
            title="Search Test Corpus",
            creator=cls.owner,
            is_public=True,
        )

        cls.doc1 = Document.objects.create(
            title="Contract Agreement",
            description="Legal binding agreement",
            creator=cls.owner,
            is_public=True,
        )

        cls.doc2 = Document.objects.create(
            title="Terms of Service",
            description="Website terms",
            creator=cls.owner,
            is_public=True,
        )

        DocumentPath.objects.create(
            document=cls.doc1,
            corpus=cls.corpus,
            path="/contract.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )
        DocumentPath.objects.create(
            document=cls.doc2,
            corpus=cls.corpus,
            path="/terms.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )

    def test_search_corpus_text_fallback(self):
        """Test search falls back to text search without embeddings."""
        from unittest.mock import patch

        from opencontractserver.mcp.tools import search_corpus

        # Mock embed_text to raise RuntimeError, forcing text search fallback
        # (RuntimeError is explicitly caught by search_corpus to trigger fallback)
        with patch.object(
            self.corpus.__class__,
            "embed_text",
            side_effect=RuntimeError("No embeddings"),
        ):
            result = search_corpus(self.corpus.slug, "Contract")

        self.assertIn("query", result)
        self.assertIn("results", result)
        self.assertEqual(result["query"], "Contract")

        # Should find the document with "Contract" in title
        self.assertTrue(len(result["results"]) >= 1)
        self.assertEqual(result["results"][0]["title"], "Contract Agreement")

    def test_search_corpus_limit(self):
        """Test search respects limit."""
        from opencontractserver.mcp.tools import search_corpus

        result = search_corpus(self.corpus.slug, "test", limit=1)

        self.assertLessEqual(len(result["results"]), 1)

    def test_text_search_fallback_directly(self):
        """Test the text search fallback function directly."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.mcp.tools import _text_search_fallback

        anonymous = AnonymousUser()
        result = _text_search_fallback(self.corpus, "Contract", 10, anonymous)

        self.assertIn("query", result)
        self.assertEqual(result["query"], "Contract")
        self.assertTrue(len(result["results"]) >= 1)


class MCPToolsThreadsTest(TestCase):
    """Tests for MCP thread-related tools."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with threads."""
        from opencontractserver.conversations.models import (
            ChatMessage,
            Conversation,
            ConversationTypeChoices,
            MessageTypeChoices,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        cls.owner = User.objects.create_user(
            username="threadowner", email="thread@test.com", password="testpass123"
        )

        cls.corpus = Corpus.objects.create(
            title="Thread Test Corpus",
            creator=cls.owner,
            is_public=True,
        )

        cls.document = Document.objects.create(
            title="Thread Document",
            creator=cls.owner,
            is_public=True,
        )

        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/thread_doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )

        # Create threads
        cls.thread1 = Conversation.objects.create(
            title="Discussion Thread One",
            description="First discussion",
            creator=cls.owner,
            is_public=True,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=cls.corpus,
            is_pinned=True,
        )

        cls.thread2 = Conversation.objects.create(
            title="Discussion Thread Two",
            description="Second discussion",
            creator=cls.owner,
            is_public=True,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=cls.corpus,
            chat_with_document=cls.document,
        )

        # Add messages to thread1
        cls.msg1 = ChatMessage.objects.create(
            conversation=cls.thread1,
            content="Hello everyone!",
            msg_type=MessageTypeChoices.HUMAN,
            creator=cls.owner,
            is_public=True,
        )

        cls.msg2 = ChatMessage.objects.create(
            conversation=cls.thread1,
            content="Welcome to the discussion",
            msg_type=MessageTypeChoices.HUMAN,
            creator=cls.owner,
            is_public=True,
        )

        # Add a reply to msg1
        cls.reply1 = ChatMessage.objects.create(
            conversation=cls.thread1,
            content="Thanks for the welcome!",
            msg_type=MessageTypeChoices.HUMAN,
            parent_message=cls.msg1,
            creator=cls.owner,
            is_public=True,
        )

    def test_list_threads(self):
        """Test listing threads in a corpus."""
        from opencontractserver.mcp.tools import list_threads

        result = list_threads(self.corpus.slug)

        self.assertIn("total_count", result)
        self.assertIn("threads", result)
        self.assertEqual(result["total_count"], 2)

        # Pinned thread should be first
        self.assertEqual(result["threads"][0]["id"], str(self.thread1.id))
        self.assertTrue(result["threads"][0]["is_pinned"])

    def test_list_threads_filter_by_document(self):
        """Test filtering threads by document."""
        from opencontractserver.mcp.tools import list_threads

        result = list_threads(self.corpus.slug, document_slug=self.document.slug)

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["threads"][0]["id"], str(self.thread2.id))

    def test_list_threads_pagination(self):
        """Test thread pagination."""
        from opencontractserver.mcp.tools import list_threads

        result = list_threads(self.corpus.slug, limit=1)
        self.assertEqual(len(result["threads"]), 1)

    def test_get_thread_messages_hierarchical(self):
        """Test getting thread messages with hierarchy."""
        from opencontractserver.mcp.tools import get_thread_messages

        result = get_thread_messages(self.corpus.slug, self.thread1.id)

        self.assertEqual(result["thread_id"], str(self.thread1.id))
        self.assertEqual(result["title"], "Discussion Thread One")
        self.assertIn("messages", result)

        # Should have 2 root messages
        root_messages = result["messages"]
        self.assertEqual(len(root_messages), 2)

        # First message should have a reply
        msg1_data = next(m for m in root_messages if m["content"] == "Hello everyone!")
        self.assertEqual(len(msg1_data["replies"]), 1)
        self.assertEqual(msg1_data["replies"][0]["content"], "Thanks for the welcome!")

    def test_get_thread_messages_flattened(self):
        """Test getting thread messages flattened."""
        from opencontractserver.mcp.tools import get_thread_messages

        result = get_thread_messages(self.corpus.slug, self.thread1.id, flatten=True)

        self.assertEqual(result["thread_id"], str(self.thread1.id))
        # All 3 messages should be in a flat list
        self.assertEqual(len(result["messages"]), 3)

    def test_get_thread_messages_nonexistent(self):
        """Test getting messages from nonexistent thread."""
        from django.core.exceptions import ObjectDoesNotExist

        from opencontractserver.mcp.tools import get_thread_messages

        with self.assertRaises(ObjectDoesNotExist):
            get_thread_messages(self.corpus.slug, 99999)


class MCPResourcesDocumentTest(TestCase):
    """Tests for MCP document resources."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        from django.core.files.base import ContentFile

        from opencontractserver.documents.models import Document, DocumentPath

        cls.owner = User.objects.create_user(
            username="docresowner", email="docres@test.com", password="testpass123"
        )

        cls.corpus = Corpus.objects.create(
            title="Document Resource Corpus",
            creator=cls.owner,
            is_public=True,
        )

        cls.document = Document.objects.create(
            title="Resource Document",
            description="Document for resource testing",
            creator=cls.owner,
            is_public=True,
            page_count=10,
            file_type="application/pdf",
        )
        cls.document.txt_extract_file.save(
            "resource_doc.txt", ContentFile(b"Full text content for resource test")
        )

        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/resource_doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )

    def test_get_document_resource(self):
        """Test getting document resource."""
        from opencontractserver.mcp.resources import get_document_resource

        result = get_document_resource(self.corpus.slug, self.document.slug)
        data = json.loads(result)

        self.assertEqual(data["slug"], self.document.slug)
        self.assertEqual(data["title"], "Resource Document")
        self.assertEqual(data["description"], "Document for resource testing")
        self.assertEqual(data["page_count"], 10)
        self.assertEqual(data["file_type"], "application/pdf")
        # Note: File storage in tests may not persist, so we just verify the structure
        self.assertIn("full_text", data)
        self.assertIn("text_preview", data)

    def test_get_document_resource_nonexistent(self):
        """Test accessing nonexistent document."""
        from opencontractserver.documents.models import Document
        from opencontractserver.mcp.resources import get_document_resource

        with self.assertRaises(Document.DoesNotExist):
            get_document_resource(self.corpus.slug, "nonexistent-doc")


class MCPResourcesAnnotationTest(TestCase):
    """Tests for MCP annotation resources."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        from opencontractserver.annotations.models import Annotation, AnnotationLabel
        from opencontractserver.documents.models import Document, DocumentPath

        cls.owner = User.objects.create_user(
            username="annresowner", email="annres@test.com", password="testpass123"
        )

        cls.corpus = Corpus.objects.create(
            title="Annotation Resource Corpus",
            creator=cls.owner,
            is_public=True,
        )

        cls.document = Document.objects.create(
            title="Annotation Resource Doc",
            creator=cls.owner,
            is_public=True,
        )

        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/ann_resource.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )

        cls.label = AnnotationLabel.objects.create(
            text="Resource Label",
            color="#AABBCC",
            label_type="TOKEN_LABEL",
            creator=cls.owner,
            is_public=True,
        )

        cls.annotation = Annotation.objects.create(
            page=3,
            raw_text="Annotation text for resource",
            annotation_label=cls.label,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.owner,
            is_public=True,
        )

    def test_get_annotation_resource(self):
        """Test getting annotation resource."""
        from opencontractserver.mcp.resources import get_annotation_resource

        result = get_annotation_resource(
            self.corpus.slug, self.document.slug, self.annotation.id
        )
        data = json.loads(result)

        self.assertEqual(data["id"], str(self.annotation.id))
        self.assertEqual(data["page"], 3)
        self.assertEqual(data["raw_text"], "Annotation text for resource")
        self.assertEqual(data["annotation_label"]["text"], "Resource Label")
        self.assertEqual(data["annotation_label"]["color"], "#AABBCC")
        self.assertIn("json", data)
        self.assertIsNotNone(data["json"])


class MCPResourcesThreadTest(TestCase):
    """Tests for MCP thread resources."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        from opencontractserver.conversations.models import (
            ChatMessage,
            Conversation,
            ConversationTypeChoices,
            MessageTypeChoices,
        )

        cls.owner = User.objects.create_user(
            username="threadresowner",
            email="threadres@test.com",
            password="testpass123",
        )

        cls.corpus = Corpus.objects.create(
            title="Thread Resource Corpus",
            creator=cls.owner,
            is_public=True,
        )

        cls.thread = Conversation.objects.create(
            title="Resource Thread",
            description="Thread for resource testing",
            creator=cls.owner,
            is_public=True,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=cls.corpus,
            is_locked=True,
            is_pinned=True,
        )

        cls.message = ChatMessage.objects.create(
            conversation=cls.thread,
            content="Resource thread message",
            msg_type=MessageTypeChoices.HUMAN,
            creator=cls.owner,
            is_public=True,
        )

    def test_get_thread_resource(self):
        """Test getting thread resource."""
        from opencontractserver.mcp.resources import get_thread_resource

        result = get_thread_resource(self.corpus.slug, self.thread.id)
        data = json.loads(result)

        self.assertEqual(data["id"], str(self.thread.id))
        self.assertEqual(data["title"], "Resource Thread")
        self.assertEqual(data["description"], "Thread for resource testing")
        self.assertTrue(data["is_locked"])
        self.assertTrue(data["is_pinned"])
        self.assertIn("messages", data)
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["content"], "Resource thread message")

    def test_get_thread_resource_nonexistent(self):
        """Test accessing nonexistent thread."""
        from opencontractserver.conversations.models import Conversation
        from opencontractserver.mcp.resources import get_thread_resource

        with self.assertRaises(Conversation.DoesNotExist):
            get_thread_resource(self.corpus.slug, 99999)


class MCPResourcesCorpusWithLabelSetTest(TestCase):
    """Tests for corpus resources with label sets."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with label set."""
        from opencontractserver.annotations.models import AnnotationLabel, LabelSet

        cls.owner = User.objects.create_user(
            username="labelsetowner",
            email="labelset@test.com",
            password="testpass123",
        )

        cls.label_set = LabelSet.objects.create(
            title="Test Label Set",
            creator=cls.owner,
            is_public=True,
        )

        cls.label1 = AnnotationLabel.objects.create(
            text="Label A",
            color="#111111",
            label_type="TOKEN_LABEL",
            creator=cls.owner,
            is_public=True,
        )

        cls.label2 = AnnotationLabel.objects.create(
            text="Label B",
            color="#222222",
            label_type="SPAN_LABEL",
            creator=cls.owner,
            is_public=True,
        )

        cls.label_set.annotation_labels.add(cls.label1, cls.label2)

        cls.corpus = Corpus.objects.create(
            title="Corpus With Labels",
            description="Has a label set",
            creator=cls.owner,
            is_public=True,
            label_set=cls.label_set,
        )

    def test_get_corpus_resource_with_label_set(self):
        """Test corpus resource includes label set data."""
        from opencontractserver.mcp.resources import get_corpus_resource

        result = get_corpus_resource(self.corpus.slug)
        data = json.loads(result)

        self.assertEqual(data["title"], "Corpus With Labels")
        self.assertIsNotNone(data["label_set"])
        self.assertEqual(data["label_set"]["title"], "Test Label Set")
        self.assertEqual(len(data["label_set"]["labels"]), 2)

        label_texts = [label["text"] for label in data["label_set"]["labels"]]
        self.assertIn("Label A", label_texts)
        self.assertIn("Label B", label_texts)


class MCPFormattersExtendedTest(TestCase):
    """Extended tests for MCP formatters."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        from opencontractserver.annotations.models import Annotation, AnnotationLabel
        from opencontractserver.conversations.models import (
            ChatMessage,
            Conversation,
            ConversationTypeChoices,
            MessageTypeChoices,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        cls.owner = User.objects.create_user(
            username="formatextowner",
            email="formatext@test.com",
            password="testpass123",
        )

        cls.corpus = Corpus.objects.create(
            title="Formatter Test Corpus",
            creator=cls.owner,
            is_public=True,
        )

        cls.document = Document.objects.create(
            title="Formatter Test Doc",
            description="Document for formatter tests",
            creator=cls.owner,
            is_public=True,
            page_count=15,
            file_type="application/pdf",
        )

        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/formatter.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )

        cls.label = AnnotationLabel.objects.create(
            text="Formatter Label",
            color="#DDEEFF",
            label_type="TOKEN_LABEL",
            creator=cls.owner,
            is_public=True,
        )

        cls.annotation = Annotation.objects.create(
            page=5,
            raw_text="Formatter annotation text",
            annotation_label=cls.label,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.owner,
            is_public=True,
            structural=True,
        )

        cls.annotation_no_label = Annotation.objects.create(
            page=6,
            raw_text="No label annotation",
            annotation_label=None,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.owner,
            is_public=True,
        )

        cls.thread = Conversation.objects.create(
            title="Formatter Thread",
            description="Thread for formatter tests",
            creator=cls.owner,
            is_public=True,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=cls.corpus,
            is_locked=False,
            is_pinned=False,
        )

        cls.message = ChatMessage.objects.create(
            conversation=cls.thread,
            content="Formatter message content",
            msg_type=MessageTypeChoices.HUMAN,
            creator=cls.owner,
            is_public=True,
            upvote_count=5,
            downvote_count=2,
        )

        cls.reply = ChatMessage.objects.create(
            conversation=cls.thread,
            content="Reply to formatter message",
            msg_type=MessageTypeChoices.HUMAN,
            parent_message=cls.message,
            creator=cls.owner,
            is_public=True,
        )

    def test_format_document_summary(self):
        """Test document summary formatting."""
        from opencontractserver.mcp.formatters import format_document_summary

        result = format_document_summary(self.document)

        self.assertEqual(result["slug"], self.document.slug)
        self.assertEqual(result["title"], "Formatter Test Doc")
        self.assertEqual(result["description"], "Document for formatter tests")
        self.assertEqual(result["page_count"], 15)
        self.assertEqual(result["file_type"], "application/pdf")
        self.assertIn("created", result)

    def test_format_annotation(self):
        """Test annotation formatting."""
        from opencontractserver.mcp.formatters import format_annotation

        result = format_annotation(self.annotation)

        self.assertEqual(result["id"], str(self.annotation.id))
        self.assertEqual(result["page"], 5)
        self.assertEqual(result["raw_text"], "Formatter annotation text")
        self.assertTrue(result["structural"])
        self.assertEqual(result["annotation_label"]["text"], "Formatter Label")
        self.assertEqual(result["annotation_label"]["color"], "#DDEEFF")

    def test_format_annotation_without_label(self):
        """Test annotation formatting without label."""
        from opencontractserver.mcp.formatters import format_annotation

        result = format_annotation(self.annotation_no_label)

        self.assertEqual(result["id"], str(self.annotation_no_label.id))
        self.assertIsNone(result["annotation_label"])

    def test_format_thread_summary(self):
        """Test thread summary formatting."""
        from opencontractserver.mcp.formatters import format_thread_summary

        result = format_thread_summary(self.thread)

        self.assertEqual(result["id"], str(self.thread.id))
        self.assertEqual(result["title"], "Formatter Thread")
        self.assertEqual(result["description"], "Thread for formatter tests")
        self.assertFalse(result["is_pinned"])
        self.assertFalse(result["is_locked"])
        self.assertIn("created_at", result)
        self.assertIn("last_activity", result)

    def test_format_message(self):
        """Test message formatting."""
        from opencontractserver.mcp.formatters import format_message

        result = format_message(self.message)

        self.assertEqual(result["id"], str(self.message.id))
        self.assertEqual(result["content"], "Formatter message content")
        self.assertEqual(result["msg_type"], "HUMAN")
        self.assertEqual(result["upvote_count"], 5)
        self.assertEqual(result["downvote_count"], 2)
        self.assertIn("created_at", result)

    def test_format_message_with_replies(self):
        """Test message formatting with replies."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.mcp.formatters import format_message_with_replies

        anonymous = AnonymousUser()
        result = format_message_with_replies(self.message, anonymous)

        self.assertEqual(result["id"], str(self.message.id))
        self.assertEqual(result["content"], "Formatter message content")
        self.assertIn("replies", result)
        self.assertEqual(len(result["replies"]), 1)
        self.assertEqual(result["replies"][0]["content"], "Reply to formatter message")

    def test_format_message_with_replies_max_depth(self):
        """Test message formatting respects max depth."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.mcp.formatters import format_message_with_replies

        anonymous = AnonymousUser()

        # Test with max_depth=0 should not include any replies
        result = format_message_with_replies(
            self.message, anonymous, max_depth=0, current_depth=0
        )

        self.assertEqual(result["replies"], [])
        # Should have indication if more replies exist
        self.assertIn("has_more_replies", result)


class MCPServerAsyncTest(TestCase):
    """Tests for MCP server async handlers."""

    def test_create_mcp_server(self):
        """Test MCP server creation."""
        from opencontractserver.mcp.server import create_mcp_server

        server = create_mcp_server()
        self.assertIsNotNone(server)
        self.assertEqual(server.name, "opencontracts")

    def test_get_session_manager(self):
        """Test session manager creation."""
        from opencontractserver.mcp.server import get_session_manager

        manager = get_session_manager()
        self.assertIsNotNone(manager)

        # Getting it again should return the same instance
        manager2 = get_session_manager()
        self.assertIs(manager, manager2)

    def test_create_mcp_asgi_app(self):
        """Test ASGI app creation."""
        from opencontractserver.mcp.server import create_mcp_asgi_app

        app = create_mcp_asgi_app()
        self.assertIsNotNone(app)
        self.assertTrue(callable(app))


class MCPServerComponentsTest(TestCase):
    """Tests for MCP server components."""

    def test_mcp_lifespan_manager(self):
        """Test MCPLifespanManager initialization."""
        from opencontractserver.mcp.server import MCPLifespanManager

        manager = MCPLifespanManager()
        self.assertFalse(manager._started)
        self.assertIsNone(manager._run_context)

    def test_uri_parser_patterns(self):
        """Test URIParser pattern constants."""
        from opencontractserver.mcp.server import URIParser

        # Check patterns are compiled
        self.assertIsNotNone(URIParser.PATTERNS["corpus"])
        self.assertIsNotNone(URIParser.PATTERNS["document"])
        self.assertIsNotNone(URIParser.PATTERNS["annotation"])
        self.assertIsNotNone(URIParser.PATTERNS["thread"])

    def test_mcp_server_has_name(self):
        """Test MCP server has correct name."""
        from opencontractserver.mcp.server import mcp_server

        self.assertEqual(mcp_server.name, "opencontracts")

    def test_mcp_asgi_app_exists(self):
        """Test ASGI app is created."""
        from opencontractserver.mcp.server import mcp_asgi_app

        self.assertIsNotNone(mcp_asgi_app)
        self.assertTrue(callable(mcp_asgi_app))


class MCPSSETransportTest(TestCase):
    """Tests for SSE transport support (deprecated, for backward compatibility)."""

    def test_sse_transport_exists(self):
        """Test SSE transport is created."""
        from opencontractserver.mcp.server import sse_transport

        self.assertIsNotNone(sse_transport)

    def test_sse_starlette_app_exists(self):
        """Test SSE Starlette app is created with correct routes."""
        from starlette.applications import Starlette

        from opencontractserver.mcp.server import sse_starlette_app

        self.assertIsNotNone(sse_starlette_app)
        self.assertIsInstance(sse_starlette_app, Starlette)

        # Verify routes are configured
        routes = sse_starlette_app.routes
        self.assertTrue(len(routes) >= 2)

        # Check route paths
        route_paths = [getattr(r, "path", None) for r in routes]
        self.assertIn("/sse", route_paths)

    def test_handle_sse_connection_exists(self):
        """Test handle_sse_connection function exists and is callable."""
        from opencontractserver.mcp.server import handle_sse_connection

        self.assertTrue(callable(handle_sse_connection))

    def test_handle_sse_connection_function(self):
        """Test handle_sse_connection with mocked SSE transport."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from opencontractserver.mcp.server import handle_sse_connection

        async def run_test():
            # Create a mock request object
            mock_request = MagicMock()
            mock_request.scope = {"type": "http", "path": "/sse"}
            mock_request.receive = AsyncMock(return_value={"type": "http.disconnect"})
            mock_request._send = AsyncMock()

            # Create mock streams
            mock_read_stream = AsyncMock()
            mock_write_stream = AsyncMock()

            # Create mock async context manager
            mock_connect = MagicMock()
            mock_connect.__aenter__ = AsyncMock(
                return_value=(mock_read_stream, mock_write_stream)
            )
            mock_connect.__aexit__ = AsyncMock(return_value=None)

            # Mock the mcp_server.run method
            mock_mcp_run = AsyncMock()

            with patch(
                "opencontractserver.mcp.server.sse_transport.connect_sse",
                return_value=mock_connect,
            ), patch(
                "opencontractserver.mcp.server.mcp_server.run", mock_mcp_run
            ), patch(
                "opencontractserver.mcp.server.mcp_server.create_initialization_options",
                return_value={},
            ):
                result = await handle_sse_connection(mock_request)

            # Verify the response is returned
            from starlette.responses import Response

            self.assertIsInstance(result, Response)

            # Verify mcp_server.run was called with the streams
            mock_mcp_run.assert_called_once()
            call_args = mock_mcp_run.call_args
            self.assertEqual(call_args[0][0], mock_read_stream)
            self.assertEqual(call_args[0][1], mock_write_stream)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


class MCPHttpRouterTest(TestCase):
    """Tests for the HTTP router that dispatches to MCP vs Django."""

    def test_http_router_routes_sse_to_mcp(self):
        """Test HTTP router routes /sse to MCP app."""
        import asyncio

        from config.asgi import create_http_router

        mcp_called = []
        django_called = []

        async def mock_mcp_app(scope, receive, send):
            mcp_called.append(scope["path"])

        async def mock_django_app(scope, receive, send):
            django_called.append(scope["path"])

        router = create_http_router(mock_django_app, mock_mcp_app)

        async def run_test():
            async def mock_receive():
                return {"type": "http.disconnect"}

            async def mock_send(message):
                pass

            # Test /sse routes to MCP
            await router({"type": "http", "path": "/sse"}, mock_receive, mock_send)
            # Test /sse/* routes to MCP
            await router(
                {"type": "http", "path": "/sse/messages/"}, mock_receive, mock_send
            )
            # Test other paths route to Django
            await router({"type": "http", "path": "/api/test"}, mock_receive, mock_send)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

        self.assertIn("/sse", mcp_called)
        self.assertIn("/sse/messages/", mcp_called)
        self.assertIn("/api/test", django_called)

    def test_http_router_routes_mcp_to_mcp(self):
        """Test HTTP router routes /mcp to MCP app."""
        import asyncio

        from config.asgi import create_http_router

        mcp_called = []

        async def mock_mcp_app(scope, receive, send):
            mcp_called.append(scope["path"])

        async def mock_django_app(scope, receive, send):
            pass

        router = create_http_router(mock_django_app, mock_mcp_app)

        async def run_test():
            async def mock_receive():
                return {"type": "http.disconnect"}

            async def mock_send(message):
                pass

            await router({"type": "http", "path": "/mcp"}, mock_receive, mock_send)
            await router({"type": "http", "path": "/mcp/"}, mock_receive, mock_send)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

        self.assertIn("/mcp", mcp_called)
        self.assertIn("/mcp/", mcp_called)


class MCPASGIRoutingTest(TestCase):
    """Tests for MCP ASGI app routing."""

    def test_asgi_app_routes_sse_paths(self):
        """Test ASGI app handles SSE paths correctly."""
        import asyncio

        from opencontractserver.mcp.server import create_mcp_asgi_app

        app = create_mcp_asgi_app()

        # Test that /sse path is recognized by the app
        # We create a mock scope and verify the app doesn't crash

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.disconnect"}

            async def mock_send(message):
                received_messages.append(message)

            scope = {
                "type": "http",
                "path": "/sse",
                "method": "GET",
                "query_string": b"",
                "headers": [],
            }

            try:
                await asyncio.wait_for(app(scope, mock_receive, mock_send), timeout=0.5)
            except (asyncio.TimeoutError, Exception):
                # SSE connection will timeout or error without proper setup
                # but we're just testing that the routing works
                pass

            return received_messages

        # Run the async test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
            # The app should attempt to respond (might fail due to missing SSE setup)
            # but it proves the routing works
        finally:
            loop.close()

    def test_asgi_app_routes_sse_messages_path(self):
        """Test ASGI app handles /sse/messages/ paths."""
        import asyncio

        from opencontractserver.mcp.server import create_mcp_asgi_app

        app = create_mcp_asgi_app()

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.disconnect"}

            async def mock_send(message):
                received_messages.append(message)

            scope = {
                "type": "http",
                "path": "/sse/messages/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
            }

            try:
                await asyncio.wait_for(app(scope, mock_receive, mock_send), timeout=0.5)
            except (asyncio.TimeoutError, Exception):
                pass

            return received_messages

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_asgi_app_ignores_non_http(self):
        """Test ASGI app ignores non-HTTP scopes."""
        import asyncio

        from opencontractserver.mcp.server import create_mcp_asgi_app

        app = create_mcp_asgi_app()

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "lifespan.shutdown"}

            async def mock_send(message):
                received_messages.append(message)

            # Non-HTTP scope (like websocket)
            scope = {
                "type": "websocket",
                "path": "/sse",
            }

            await app(scope, mock_receive, mock_send)
            return received_messages

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            # Should return immediately without sending anything
            self.assertEqual(len(result), 0)
        finally:
            loop.close()

    def test_asgi_app_returns_404_for_unknown_path(self):
        """Test ASGI app returns 404 with endpoint info for unknown paths."""
        import asyncio

        from opencontractserver.mcp.server import create_mcp_asgi_app

        app = create_mcp_asgi_app()

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.disconnect"}

            async def mock_send(message):
                received_messages.append(message)

            # Request unknown path
            scope = {
                "type": "http",
                "path": "/unknown/path",
                "method": "GET",
                "query_string": b"",
                "headers": [],
            }

            await app(scope, mock_receive, mock_send)
            return received_messages

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            # Should get a 404 response
            self.assertTrue(len(result) >= 2)
            # First message should be response start with 404
            self.assertEqual(result[0]["type"], "http.response.start")
            self.assertEqual(result[0]["status"], 404)
            # Second message should be the body with endpoint info
            self.assertEqual(result[1]["type"], "http.response.body")
            body = json.loads(result[1]["body"])
            self.assertEqual(body["error"], "Not found")
            self.assertIn("endpoints", body)
            self.assertIn("streamable_http", body["endpoints"])
            self.assertIn("sse", body["endpoints"])
        finally:
            loop.close()

    def test_asgi_app_mcp_path_error_handling(self):
        """Test ASGI app handles errors on /mcp path."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received_messages.append(message)

            scope = {
                "type": "http",
                "path": "/mcp",
                "method": "POST",
                "query_string": b"",
                "headers": [[b"content-type", b"application/json"]],
            }

            # Mock both lifespan_manager and session manager
            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock()

            mock_manager = AsyncMock()
            mock_manager.handle_request.side_effect = Exception("Test error")

            with patch(
                "opencontractserver.mcp.server.lifespan_manager", mock_lifespan
            ), patch(
                "opencontractserver.mcp.server.get_session_manager",
                return_value=mock_manager,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            return received_messages

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            # Should get a 500 error response
            self.assertTrue(len(result) >= 2)
            self.assertEqual(result[0]["type"], "http.response.start")
            self.assertEqual(result[0]["status"], 500)
            self.assertEqual(result[1]["type"], "http.response.body")
            body = json.loads(result[1]["body"])
            self.assertIn("error", body)
            self.assertEqual(body["error"], "Test error")
        finally:
            loop.close()

    def test_asgi_app_sse_path_error_handling(self):
        """Test ASGI app handles errors on /sse path."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.disconnect"}

            async def mock_send(message):
                received_messages.append(message)

            scope = {
                "type": "http",
                "path": "/sse",
                "method": "GET",
                "query_string": b"",
                "headers": [],
            }

            # Mock the sse_starlette_app to raise an exception
            async def mock_sse_app(scope, receive, send):
                raise Exception("SSE test error")

            with patch("opencontractserver.mcp.server.sse_starlette_app", mock_sse_app):
                # Need to recreate the app to pick up the mock
                new_app = create_mcp_asgi_app()
                await new_app(scope, mock_receive, mock_send)

            return received_messages

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            # Should get a 500 error response
            self.assertTrue(len(result) >= 2)
            self.assertEqual(result[0]["type"], "http.response.start")
            self.assertEqual(result[0]["status"], 500)
            self.assertEqual(result[1]["type"], "http.response.body")
            body = json.loads(result[1]["body"])
            self.assertIn("error", body)
            self.assertEqual(body["error"], "SSE test error")
        finally:
            loop.close()


class MCPTelemetryTest(TestCase):
    """Tests for MCP telemetry functionality."""

    def setUp(self):
        """Reset telemetry context before each test."""
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

    def tearDown(self):
        """Clean up telemetry context after each test."""
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

    def test_hash_ip(self):
        """Test IP hashing for privacy."""
        from opencontractserver.mcp.telemetry import _hash_ip

        # Same IP should produce same hash
        hash1 = _hash_ip("192.168.1.1")
        hash2 = _hash_ip("192.168.1.1")
        self.assertEqual(hash1, hash2)

        # Different IPs should produce different hashes
        hash3 = _hash_ip("192.168.1.2")
        self.assertNotEqual(hash1, hash3)

        # Hash should be 16 characters
        self.assertEqual(len(hash1), 16)

    def test_set_and_get_request_context(self):
        """Test setting and getting request context."""
        from opencontractserver.mcp.telemetry import (
            _get_request_context,
            set_request_context,
        )

        set_request_context(client_ip="10.0.0.1", transport="streamable_http")

        context = _get_request_context()
        self.assertEqual(context["transport"], "streamable_http")
        # Only hashed IP is stored for privacy-preserving unique user counting
        # Raw IP is never stored (GDPR compliance)
        self.assertNotIn("client_ip", context)
        self.assertIsNotNone(context["client_ip_hash"])
        self.assertNotEqual(context["client_ip_hash"], "10.0.0.1")
        self.assertEqual(len(context["client_ip_hash"]), 16)

    def test_set_request_context_no_ip(self):
        """Test setting request context without IP (stdio transport)."""
        from opencontractserver.mcp.telemetry import (
            _get_request_context,
            set_request_context,
        )

        set_request_context(client_ip=None, transport="stdio")

        context = _get_request_context()
        self.assertEqual(context["transport"], "stdio")
        # Raw IP is never stored (GDPR compliance)
        self.assertNotIn("client_ip", context)
        self.assertIsNone(context["client_ip_hash"])

    def test_clear_request_context(self):
        """Test clearing request context."""
        from opencontractserver.mcp.telemetry import (
            _get_request_context,
            clear_request_context,
            set_request_context,
        )

        set_request_context(client_ip="10.0.0.1", transport="sse")
        clear_request_context()

        context = _get_request_context()
        self.assertEqual(context, {})

    def test_get_client_ip_from_scope_direct(self):
        """Test extracting client IP from direct connection."""
        from opencontractserver.mcp.telemetry import get_claimed_client_ip_from_scope

        scope = {
            "client": ("192.168.1.100", 54321),
            "headers": [],
        }

        ip = get_claimed_client_ip_from_scope(scope)
        self.assertEqual(ip, "192.168.1.100")

    def test_get_client_ip_from_scope_x_forwarded_for(self):
        """Test extracting client IP from X-Forwarded-For header."""
        from opencontractserver.mcp.telemetry import get_claimed_client_ip_from_scope

        scope = {
            "client": ("127.0.0.1", 80),  # Proxy address
            "headers": [
                (b"x-forwarded-for", b"203.0.113.195, 70.41.3.18, 150.172.238.178"),
            ],
        }

        ip = get_claimed_client_ip_from_scope(scope)
        # Telemetry uses leftmost (original client claim) for privacy-
        # preserving analytics deduplication, unlike rate limiting which
        # uses rightmost for anti-spoofing.
        self.assertEqual(ip, "203.0.113.195")

    def test_get_client_ip_from_scope_x_real_ip(self):
        """Test extracting client IP from X-Real-IP header."""
        from opencontractserver.mcp.telemetry import get_claimed_client_ip_from_scope

        scope = {
            "client": ("127.0.0.1", 80),
            "headers": [
                (b"x-real-ip", b"203.0.113.50"),
            ],
        }

        ip = get_claimed_client_ip_from_scope(scope)
        self.assertEqual(ip, "203.0.113.50")

    def test_get_client_ip_from_scope_no_client(self):
        """Test extracting client IP when no client info available."""
        from opencontractserver.mcp.telemetry import get_claimed_client_ip_from_scope

        scope = {
            "headers": [],
        }

        ip = get_claimed_client_ip_from_scope(scope)
        self.assertIsNone(ip)

    def test_record_mcp_tool_call_success(self):
        """Test recording successful MCP tool call."""
        from unittest.mock import patch

        from opencontractserver.mcp.telemetry import (
            record_mcp_tool_call,
            set_request_context,
        )

        set_request_context(client_ip="10.0.0.1", transport="streamable_http")

        with patch(
            "opencontractserver.mcp.telemetry.record_event"
        ) as mock_record_event:
            mock_record_event.return_value = True

            result = record_mcp_tool_call("list_documents", success=True)

            self.assertTrue(result)
            mock_record_event.assert_called_once()

            # Check event type and properties
            call_args = mock_record_event.call_args
            self.assertEqual(call_args[0][0], "mcp_tool_call")

            properties = call_args[0][1]
            self.assertEqual(properties["tool_name"], "list_documents")
            self.assertTrue(properties["success"])
            self.assertEqual(properties["transport"], "streamable_http")
            self.assertIn("client_ip_hash", properties)
            # Raw IP is never sent to PostHog (GDPR compliance)
            self.assertNotIn("$ip", properties)
            self.assertNotIn("error_type", properties)

    def test_record_mcp_tool_call_failure(self):
        """Test recording failed MCP tool call."""
        from unittest.mock import patch

        from opencontractserver.mcp.telemetry import (
            record_mcp_tool_call,
            set_request_context,
        )

        set_request_context(client_ip="10.0.0.2", transport="sse")

        with patch(
            "opencontractserver.mcp.telemetry.record_event"
        ) as mock_record_event:
            mock_record_event.return_value = True

            result = record_mcp_tool_call(
                "search_corpus", success=False, error_type="ValueError"
            )

            self.assertTrue(result)
            mock_record_event.assert_called_once()

            properties = mock_record_event.call_args[0][1]
            self.assertEqual(properties["tool_name"], "search_corpus")
            self.assertFalse(properties["success"])
            self.assertEqual(properties["error_type"], "ValueError")

    def test_record_mcp_tool_call_no_context(self):
        """Test recording tool call without request context."""
        from unittest.mock import patch

        from opencontractserver.mcp.telemetry import record_mcp_tool_call

        with patch(
            "opencontractserver.mcp.telemetry.record_event"
        ) as mock_record_event:
            mock_record_event.return_value = True

            result = record_mcp_tool_call("list_public_corpuses", success=True)

            self.assertTrue(result)
            properties = mock_record_event.call_args[0][1]
            self.assertEqual(properties["transport"], "unknown")
            self.assertNotIn("client_ip_hash", properties)
            self.assertNotIn("$ip", properties)  # No IP for geolocation either

    def test_record_mcp_resource_read_success(self):
        """Test recording successful MCP resource read."""
        from unittest.mock import patch

        from opencontractserver.mcp.telemetry import (
            record_mcp_resource_read,
            set_request_context,
        )

        set_request_context(client_ip="172.16.0.1", transport="streamable_http")

        with patch(
            "opencontractserver.mcp.telemetry.record_event"
        ) as mock_record_event:
            mock_record_event.return_value = True

            result = record_mcp_resource_read("document", success=True)

            self.assertTrue(result)
            mock_record_event.assert_called_once()

            call_args = mock_record_event.call_args
            self.assertEqual(call_args[0][0], "mcp_resource_read")

            properties = call_args[0][1]
            self.assertEqual(properties["resource_type"], "document")
            self.assertTrue(properties["success"])
            self.assertEqual(properties["transport"], "streamable_http")
            self.assertIn("client_ip_hash", properties)
            # Raw IP is never sent to PostHog (GDPR compliance)
            self.assertNotIn("$ip", properties)

    def test_record_mcp_resource_read_failure(self):
        """Test recording failed MCP resource read."""
        from unittest.mock import patch

        from opencontractserver.mcp.telemetry import (
            record_mcp_resource_read,
            set_request_context,
        )

        set_request_context(client_ip="10.0.0.3", transport="sse")

        with patch(
            "opencontractserver.mcp.telemetry.record_event"
        ) as mock_record_event:
            mock_record_event.return_value = True

            result = record_mcp_resource_read(
                "corpus", success=False, error_type="DoesNotExist"
            )

            self.assertTrue(result)
            properties = mock_record_event.call_args[0][1]
            self.assertEqual(properties["resource_type"], "corpus")
            self.assertFalse(properties["success"])
            self.assertEqual(properties["error_type"], "DoesNotExist")

    def test_record_mcp_request(self):
        """Test recording MCP request."""
        from unittest.mock import patch

        from opencontractserver.mcp.telemetry import (
            record_mcp_request,
            set_request_context,
        )

        set_request_context(client_ip="10.0.0.4", transport="streamable_http")

        with patch(
            "opencontractserver.mcp.telemetry.record_event"
        ) as mock_record_event:
            mock_record_event.return_value = True

            result = record_mcp_request("/mcp", method="POST", success=True)

            self.assertTrue(result)
            mock_record_event.assert_called_once()

            call_args = mock_record_event.call_args
            self.assertEqual(call_args[0][0], "mcp_request")

            properties = call_args[0][1]
            self.assertEqual(properties["endpoint"], "/mcp")
            self.assertEqual(properties["method"], "POST")
            self.assertTrue(properties["success"])
            self.assertEqual(properties["transport"], "streamable_http")
            self.assertIn("client_ip_hash", properties)
            # Raw IP is never sent to PostHog (GDPR compliance)
            self.assertNotIn("$ip", properties)


class MCPTelemetryIntegrationTest(TestCase):
    """Integration tests for MCP telemetry in server handlers."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.owner = User.objects.create_user(
            username="telemetryowner",
            email="telemetry@test.com",
            password="testpass123",
        )

        cls.corpus = Corpus.objects.create(
            title="Telemetry Test Corpus",
            description="Test corpus for telemetry",
            creator=cls.owner,
            is_public=True,
        )

    def setUp(self):
        """Reset telemetry context before each test."""
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

    def tearDown(self):
        """Clean up telemetry context after each test."""
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

    def test_asgi_app_sets_context_for_mcp_path(self):
        """Test ASGI app sets telemetry context for /mcp path."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            captured_context = None

            # Mock the session manager to capture context during request
            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock()

            mock_manager = AsyncMock()

            async def capture_context_handler(scope, receive, send):
                nonlocal captured_context
                # Import here to get the context set during the request
                from opencontractserver.mcp.telemetry import _get_request_context

                captured_context = _get_request_context()
                # Send a minimal response
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                    }
                )

            mock_manager.handle_request = capture_context_handler

            scope = {
                "type": "http",
                "path": "/mcp",
                "method": "POST",
                "client": ("192.168.1.50", 12345),
                "headers": [],
            }

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                pass

            with patch(
                "opencontractserver.mcp.server.lifespan_manager", mock_lifespan
            ), patch(
                "opencontractserver.mcp.server.get_session_manager",
                return_value=mock_manager,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            return captured_context

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            context = loop.run_until_complete(run_test())
            self.assertIsNotNone(context)
            self.assertEqual(context["transport"], "streamable_http")
            self.assertIsNotNone(context["client_ip_hash"])
        finally:
            loop.close()

    def test_call_tool_records_telemetry(self):
        """Test that call_tool records telemetry events."""
        import asyncio
        from unittest.mock import MagicMock, patch

        from opencontractserver.mcp.server import TOOL_HANDLERS, call_tool_handler
        from opencontractserver.mcp.telemetry import set_request_context

        async def run_test():
            set_request_context(client_ip="10.0.0.5", transport="streamable_http")

            # Mock the tool handler to avoid database operations during parallel tests
            # This prevents OperationalError from connection termination under load
            mock_tool_result = {"total_count": 0, "corpuses": []}
            mock_handler = MagicMock(return_value=mock_tool_result)

            # Patch TOOL_HANDLERS dict directly since it holds function references
            original_handler = TOOL_HANDLERS["list_public_corpuses"]
            TOOL_HANDLERS["list_public_corpuses"] = mock_handler

            try:
                with patch(
                    "opencontractserver.mcp.server.arecord_mcp_tool_call"
                ) as mock_record:
                    mock_record.return_value = True

                    # Call list_public_corpuses tool using module-level handler
                    result = await call_tool_handler("list_public_corpuses", {})

                    # Verify telemetry was recorded
                    mock_record.assert_called_once_with(
                        "list_public_corpuses",
                        success=True,
                        corpus_slug=None,
                        document_slug=None,
                    )

                    # Verify the mock handler was actually called
                    mock_handler.assert_called_once()

                    return result
            finally:
                # Restore the original handler
                TOOL_HANDLERS["list_public_corpuses"] = original_handler

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertIsNotNone(result)
        finally:
            loop.close()

    def test_call_tool_records_failure_telemetry(self):
        """Test that call_tool records failure telemetry."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import call_tool_handler
        from opencontractserver.mcp.telemetry import set_request_context

        async def run_test():
            set_request_context(client_ip="10.0.0.6", transport="sse")

            with patch(
                "opencontractserver.mcp.server.arecord_mcp_tool_call"
            ) as mock_record:
                mock_record.return_value = True

                # Call with unknown tool using module-level handler
                try:
                    await call_tool_handler("unknown_tool", {})
                except ValueError:
                    pass

                # Verify failure telemetry was recorded
                mock_record.assert_called_once_with(
                    "unknown_tool",
                    success=False,
                    error_type="UnknownTool",
                    corpus_slug=None,
                    document_slug=None,
                )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_read_resource_records_telemetry(self):
        """Test that read_resource records telemetry events."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import read_resource_handler
        from opencontractserver.mcp.telemetry import set_request_context

        async def run_test():
            set_request_context(client_ip="10.0.0.7", transport="streamable_http")

            with patch(
                "opencontractserver.mcp.server.arecord_mcp_resource_read"
            ) as mock_record, patch(
                "opencontractserver.mcp.server.get_corpus_resource"
            ) as mock_get_corpus:
                mock_record.return_value = True
                mock_get_corpus.return_value = '{"title": "Test Corpus"}'

                # Read corpus resource using module-level handler
                uri = "corpus://test-corpus-slug"
                result = await read_resource_handler(uri)

                # Verify telemetry was recorded
                mock_record.assert_called_once_with(
                    "corpus", success=True, corpus_slug="test-corpus-slug"
                )

                return result

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertIsNotNone(result)
        finally:
            loop.close()

    def test_read_resource_records_failure_telemetry(self):
        """Test that read_resource records failure telemetry."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import read_resource_handler
        from opencontractserver.mcp.telemetry import set_request_context

        async def run_test():
            set_request_context(client_ip="10.0.0.8", transport="sse")

            with patch(
                "opencontractserver.mcp.server.arecord_mcp_resource_read"
            ) as mock_record:
                mock_record.return_value = True

                # Try to read invalid URI using module-level handler
                try:
                    await read_resource_handler("invalid://uri")
                except ValueError:
                    pass

                # Verify failure telemetry was recorded
                mock_record.assert_called_once_with(
                    "unknown",
                    success=False,
                    error_type="ValueError",
                    corpus_slug=None,
                    document_slug=None,
                )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_read_resource_document_uri(self):
        """Test that read_resource handles document URIs."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import read_resource_handler
        from opencontractserver.mcp.telemetry import set_request_context

        async def run_test():
            set_request_context(client_ip="10.0.0.9", transport="streamable_http")

            with patch(
                "opencontractserver.mcp.server.arecord_mcp_resource_read"
            ) as mock_record, patch(
                "opencontractserver.mcp.server.get_document_resource"
            ) as mock_get_doc:
                mock_record.return_value = True
                mock_get_doc.return_value = '{"title": "Test Document"}'

                # Read document resource
                uri = "document://test-corpus/test-document"
                result = await read_resource_handler(uri)

                # Verify telemetry was recorded with document type
                mock_record.assert_called_once_with(
                    "document",
                    success=True,
                    corpus_slug="test-corpus",
                    document_slug="test-document",
                )
                mock_get_doc.assert_called_once_with(
                    "test-corpus", "test-document", user=None
                )

                return result

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertIsNotNone(result)
        finally:
            loop.close()

    def test_read_resource_annotation_uri(self):
        """Test that read_resource handles annotation URIs."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import read_resource_handler
        from opencontractserver.mcp.telemetry import set_request_context

        async def run_test():
            set_request_context(client_ip="10.0.0.10", transport="streamable_http")

            with patch(
                "opencontractserver.mcp.server.arecord_mcp_resource_read"
            ) as mock_record, patch(
                "opencontractserver.mcp.server.get_annotation_resource"
            ) as mock_get_ann:
                mock_record.return_value = True
                mock_get_ann.return_value = '{"id": 123, "text": "Test Annotation"}'

                # Read annotation resource
                uri = "annotation://test-corpus/test-document/123"
                result = await read_resource_handler(uri)

                # Verify telemetry was recorded with annotation type
                mock_record.assert_called_once_with(
                    "annotation",
                    success=True,
                    corpus_slug="test-corpus",
                    document_slug="test-document",
                )
                mock_get_ann.assert_called_once_with(
                    "test-corpus", "test-document", 123, user=None
                )

                return result

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertIsNotNone(result)
        finally:
            loop.close()

    def test_read_resource_thread_uri(self):
        """Test that read_resource handles thread URIs."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import read_resource_handler
        from opencontractserver.mcp.telemetry import set_request_context

        async def run_test():
            set_request_context(client_ip="10.0.0.11", transport="streamable_http")

            with patch(
                "opencontractserver.mcp.server.arecord_mcp_resource_read"
            ) as mock_record, patch(
                "opencontractserver.mcp.server.get_thread_resource"
            ) as mock_get_thread:
                mock_record.return_value = True
                mock_get_thread.return_value = '{"id": 456, "title": "Test Thread"}'

                # Read thread resource
                uri = "thread://test-corpus/threads/456"
                result = await read_resource_handler(uri)

                # Verify telemetry was recorded with thread type
                mock_record.assert_called_once_with(
                    "thread", success=True, corpus_slug="test-corpus"
                )
                mock_get_thread.assert_called_once_with("test-corpus", 456, user=None)

                return result

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertIsNotNone(result)
        finally:
            loop.close()


# =============================================================================
# CORPUS-SCOPED MCP TESTS
# =============================================================================


class MCPScopedToolsTest(TestCase):
    """Tests for corpus-scoped MCP tool functionality."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with documents."""
        from django.core.files.base import ContentFile

        from opencontractserver.documents.models import Document, DocumentPath

        cls.owner = User.objects.create_user(
            username="scopedtoolsowner",
            email="scopedtools@test.com",
            password="testpass123",
        )

        # Create public corpus
        cls.corpus = Corpus.objects.create(
            title="Scoped Test Corpus",
            description="Test corpus for scoped tools",
            creator=cls.owner,
            is_public=True,
            allow_comments=True,
        )

        # Create private corpus (should not be accessible)
        cls.private_corpus = Corpus.objects.create(
            title="Private Scoped Corpus",
            creator=cls.owner,
            is_public=False,
        )

        # Create documents
        cls.doc1 = Document.objects.create(
            title="Scoped Document One",
            description="First scoped document",
            creator=cls.owner,
            is_public=True,
            page_count=5,
        )
        cls.doc1.txt_extract_file.save(
            "scoped_doc1.txt", ContentFile(b"Scoped document text content.")
        )

        cls.doc2 = Document.objects.create(
            title="Scoped Document Two",
            description="Second scoped document",
            creator=cls.owner,
            is_public=True,
            page_count=10,
        )

        # Link documents to corpus via DocumentPath
        DocumentPath.objects.create(
            document=cls.doc1,
            corpus=cls.corpus,
            path="/scoped_doc1.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )
        DocumentPath.objects.create(
            document=cls.doc2,
            corpus=cls.corpus,
            path="/scoped_doc2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.owner,
        )

    def test_get_corpus_info(self):
        """Test get_corpus_info tool returns detailed corpus information."""
        from opencontractserver.mcp.tools import get_corpus_info

        result = get_corpus_info(self.corpus.slug)

        self.assertEqual(result["slug"], self.corpus.slug)
        self.assertEqual(result["title"], "Scoped Test Corpus")
        self.assertEqual(result["description"], "Test corpus for scoped tools")
        self.assertEqual(result["document_count"], 2)
        self.assertTrue(result["allow_comments"])
        self.assertIn("created", result)
        self.assertIn("modified", result)

    def test_get_corpus_info_private_denied(self):
        """Test get_corpus_info denies access to private corpus."""
        from opencontractserver.mcp.tools import get_corpus_info

        with self.assertRaises(Corpus.DoesNotExist):
            get_corpus_info(self.private_corpus.slug)

    def test_create_scoped_tool_wrapper(self):
        """Test scoped tool wrapper auto-injects corpus_slug."""
        from opencontractserver.mcp.tools import (
            create_scoped_tool_wrapper,
            list_documents,
        )

        # Create a wrapper that auto-injects corpus_slug
        wrapped = create_scoped_tool_wrapper(list_documents, self.corpus.slug)

        # Call without corpus_slug - should work because it's auto-injected
        result = wrapped(limit=10)

        self.assertIn("total_count", result)
        self.assertEqual(result["total_count"], 2)

    def test_create_scoped_tool_wrapper_overrides_provided_slug(self):
        """Test scoped wrapper overrides any provided corpus_slug."""
        from opencontractserver.mcp.tools import (
            create_scoped_tool_wrapper,
            list_documents,
        )

        wrapped = create_scoped_tool_wrapper(list_documents, self.corpus.slug)

        # Try to provide a different corpus_slug - should be ignored
        result = wrapped(corpus_slug="some-other-corpus", limit=10)

        # Should still return results from the scoped corpus
        self.assertEqual(result["total_count"], 2)

    def test_get_scoped_tool_handlers(self):
        """Test get_scoped_tool_handlers returns all expected tools."""
        from opencontractserver.mcp.tools import get_scoped_tool_handlers

        handlers = get_scoped_tool_handlers(self.corpus.slug)

        # Should have all scoped tools
        expected_tools = [
            "get_corpus_info",
            "list_documents",
            "get_document_text",
            "list_annotations",
            "search_corpus",
            "list_threads",
            "get_thread_messages",
        ]

        for tool in expected_tools:
            self.assertIn(tool, handlers)
            self.assertTrue(callable(handlers[tool]))

    def test_scoped_list_documents(self):
        """Test scoped list_documents works without explicit corpus_slug."""
        from opencontractserver.mcp.tools import get_scoped_tool_handlers

        handlers = get_scoped_tool_handlers(self.corpus.slug)

        # Call list_documents without corpus_slug
        result = handlers["list_documents"](limit=50)

        self.assertIn("documents", result)
        self.assertEqual(result["total_count"], 2)

    def test_scoped_get_document_text(self):
        """Test scoped get_document_text works without explicit corpus_slug."""
        from opencontractserver.mcp.tools import get_scoped_tool_handlers

        handlers = get_scoped_tool_handlers(self.corpus.slug)

        # Call get_document_text with only document_slug
        result = handlers["get_document_text"](document_slug=self.doc1.slug)

        self.assertEqual(result["document_slug"], self.doc1.slug)
        self.assertEqual(result["page_count"], 5)


@pytest.mark.serial
@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})
class MCPScopedServerTest(TransactionTestCase):
    """Tests for corpus-scoped MCP server functionality.

    Uses TransactionTestCase because async tests with sync_to_async
    need data committed to be visible across database connections.

    Marked as serial because these tests use sync_to_async with Django ORM
    in manually created event loops, which can cause database connection
    corruption when run in parallel with pytest-xdist.

    CONN_MAX_AGE=0 prevents connection pooling issues with asyncio.run().
    """

    def setUp(self):
        """Create test data for each test."""
        self.owner = User.objects.create_user(
            username="scopedserverowner",
            email="scopedserver@test.com",
            password="testpass123",
        )

        self.corpus = Corpus.objects.create(
            title="Scoped Server Test Corpus",
            description="Test corpus for scoped server",
            creator=self.owner,
            is_public=True,
        )

    def tearDown(self):
        """Close all database connections to prevent stale connections.

        Tests in this class use sync_to_async which runs database queries in a
        thread pool. When the event loop is closed, those threads may have stale
        connections that can corrupt subsequent tests. Explicitly closing all
        connections after each test prevents this issue.
        """
        from django import db

        db.connections.close_all()

    def test_create_scoped_mcp_server(self):
        """Test creating a scoped MCP server."""
        from opencontractserver.mcp.server import create_scoped_mcp_server

        server = create_scoped_mcp_server(self.corpus.slug)

        self.assertIsNotNone(server)
        self.assertEqual(server.name, f"opencontracts-corpus-{self.corpus.slug}")

    def test_get_scoped_tool_definitions(self):
        """Test scoped tool definitions don't require corpus_slug."""
        from opencontractserver.mcp.server import get_scoped_tool_definitions

        tools = get_scoped_tool_definitions(self.corpus.slug)

        # Should have the expected tools
        tool_names = [t.name for t in tools]
        self.assertIn("get_corpus_info", tool_names)
        self.assertIn("list_documents", tool_names)
        self.assertIn("search_corpus", tool_names)
        # ``create_thread_message`` is dispatched by the scoped endpoint
        # (see ``get_scoped_tool_handlers``) so it must also be discoverable
        # via ``tools/list`` — otherwise authenticated clients have to know
        # the tool name out-of-band.
        self.assertIn("create_thread_message", tool_names)

        # list_documents should not require corpus_slug
        list_docs_tool = next(t for t in tools if t.name == "list_documents")
        required = list_docs_tool.inputSchema.get("required", [])
        self.assertNotIn("corpus_slug", required)

        # search_corpus should only require query
        search_tool = next(t for t in tools if t.name == "search_corpus")
        self.assertEqual(search_tool.inputSchema.get("required", []), ["query"])

        # The scoped create_thread_message variant must drop ``corpus_slug``
        # from required (auto-injected from the URL) and expose the content
        # length bounds in its JSON Schema for client-side validation.
        create_tool = next(t for t in tools if t.name == "create_thread_message")
        create_required = create_tool.inputSchema.get("required", [])
        self.assertNotIn("corpus_slug", create_required)
        self.assertIn("thread_id", create_required)
        self.assertIn("content", create_required)
        content_schema = create_tool.inputSchema["properties"]["content"]
        self.assertEqual(content_schema.get("minLength"), 1)
        self.assertGreater(content_schema.get("maxLength", 0), 0)

    def test_get_scoped_resource_definitions(self):
        """Test scoped resource definitions include corpus slug."""
        from opencontractserver.mcp.server import get_scoped_resource_definitions

        resources = get_scoped_resource_definitions(self.corpus.slug)

        # Should have at least the corpus resource (documents/threads dynamically added)
        self.assertTrue(len(resources) >= 1)

        # Corpus resource should have the scoped slug
        corpus_resource = next(r for r in resources if r.name == "Corpus")
        # Compare as strings since Resource.uri is an AnyUrl type
        self.assertEqual(str(corpus_resource.uri), f"corpus://{self.corpus.slug}")

    def test_get_scoped_resource_template_definitions(self):
        """Test scoped resource template definitions."""
        from opencontractserver.mcp.server import (
            get_scoped_resource_template_definitions,
        )

        templates = get_scoped_resource_template_definitions(self.corpus.slug)

        # Should have document, annotation, and thread templates
        self.assertEqual(len(templates), 3)

        template_names = [t.name for t in templates]
        self.assertIn("Document", template_names)
        self.assertIn("Annotation", template_names)
        self.assertIn("Discussion Thread", template_names)

    def test_get_scoped_session_manager(self):
        """Test getting/creating scoped session manager."""
        import asyncio

        from django import db

        from opencontractserver.mcp.server import get_scoped_session_manager

        async def run_test():
            manager = await get_scoped_session_manager(self.corpus.slug)
            self.assertIsNotNone(manager)

            # Getting it again should return the same instance (cached)
            manager2 = await get_scoped_session_manager(self.corpus.slug)
            self.assertIs(manager, manager2)

        # Close any stale connections before creating event loop
        db.connections.close_all()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()
            # Close connections after async execution to prevent corruption
            db.connections.close_all()

    def test_get_scoped_lifespan_manager(self):
        """Test getting/creating scoped lifespan manager."""
        import asyncio

        from django import db

        from opencontractserver.mcp.server import get_scoped_lifespan_manager

        async def run_test():
            manager = await get_scoped_lifespan_manager(self.corpus.slug)
            self.assertIsNotNone(manager)
            self.assertEqual(manager.corpus_slug, self.corpus.slug)

            # Getting it again should return the same instance (cached)
            manager2 = await get_scoped_lifespan_manager(self.corpus.slug)
            self.assertIs(manager, manager2)

        # Close any stale connections before creating event loop
        db.connections.close_all()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()
            # Close connections after async execution to prevent corruption
            db.connections.close_all()

    def test_validate_corpus_slug_valid(self):
        """Test validate_corpus_slug returns True for valid public corpus.

        Mocks the Corpus queryset to avoid async database connection issues
        in parallel test environments. The function's logic (checking if a
        corpus is visible to anonymous users) is tested via the mock.
        """
        import asyncio
        from unittest.mock import MagicMock, patch

        from opencontractserver.mcp.server import validate_corpus_slug

        # Mock the Corpus model's manager to avoid database access in async context
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value.exists.return_value = True

        async def run_test():
            with patch(
                "opencontractserver.corpuses.models.Corpus.objects.visible_to_user",
                return_value=mock_queryset,
            ):
                return await validate_corpus_slug(self.corpus.slug)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertTrue(result)
            # Verify the queryset was called with the correct slug
            mock_queryset.filter.assert_called_once_with(slug=self.corpus.slug)
        finally:
            loop.close()

    def test_validate_corpus_slug_invalid(self):
        """Test validate_corpus_slug returns False for nonexistent corpus.

        Mocks the Corpus queryset to avoid async database connection issues
        in parallel test environments.
        """
        import asyncio
        from unittest.mock import MagicMock, patch

        from opencontractserver.mcp.server import validate_corpus_slug

        # Mock the Corpus model's manager to return False for nonexistent slug
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value.exists.return_value = False

        async def run_test():
            with patch(
                "opencontractserver.corpuses.models.Corpus.objects.visible_to_user",
                return_value=mock_queryset,
            ):
                return await validate_corpus_slug("nonexistent-corpus-slug")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            self.assertFalse(result)
            # Verify the queryset was called with the nonexistent slug
            mock_queryset.filter.assert_called_once_with(slug="nonexistent-corpus-slug")
        finally:
            loop.close()


@pytest.mark.serial
@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})
class MCPScopedASGIRoutingTest(TransactionTestCase):
    """Tests for corpus-scoped ASGI routing.

    Uses TransactionTestCase because async tests with sync_to_async
    need data committed to be visible across database connections.

    Marked as serial because these tests use sync_to_async with Django ORM
    in manually created event loops, which can cause database connection
    corruption when run in parallel with pytest-xdist.

    CONN_MAX_AGE=0 prevents connection pooling issues with asyncio.run().
    """

    def setUp(self):
        """Create test data for each test."""
        self.owner = User.objects.create_user(
            username="scopedasgiowner",
            email="scopedasgi@test.com",
            password="testpass123",
        )

        self.corpus = Corpus.objects.create(
            title="ASGI Routing Test Corpus",
            description="Test corpus for ASGI routing",
            creator=self.owner,
            is_public=True,
        )

        self.private_corpus = Corpus.objects.create(
            title="Private ASGI Corpus",
            creator=self.owner,
            is_public=False,
        )

    def tearDown(self):
        """Close all database connections to prevent stale connections.

        Tests in this class use sync_to_async which runs database queries in a
        thread pool. When the event loop is closed, those threads may have stale
        connections that can corrupt subsequent tests. Explicitly closing all
        connections after each test prevents this issue.
        """
        from django import db

        db.connections.close_all()

    def test_asgi_routes_scoped_corpus_path(self):
        """Test ASGI app routes /mcp/corpus/{slug}/ to scoped handler."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received_messages.append(message)

            # Mock the scoped session manager
            mock_manager = AsyncMock()
            mock_manager.handle_request = AsyncMock()

            # Mock the lifespan manager - ensure_started should return the manager
            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock(return_value=mock_manager)

            # Create async mock functions that return the mock objects
            async def mock_get_lifespan(slug):
                return mock_lifespan

            # Use lowercase slug to match new regex pattern
            lowercase_slug = self.corpus.slug.lower()

            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{lowercase_slug}/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }

            with patch(
                "opencontractserver.mcp.server.get_scoped_lifespan_manager",
                side_effect=mock_get_lifespan,
            ), patch(
                "opencontractserver.mcp.server.validate_corpus_slug",
                return_value=True,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            # Verify scoped handlers were called
            mock_lifespan.ensure_started.assert_called_once()
            mock_manager.handle_request.assert_called_once()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_asgi_returns_404_for_private_corpus_without_auth(self):
        """Test ASGI app returns 404 for private corpus without auth.

        Mocks validate_corpus_slug to avoid database connection corruption
        when running with pytest-xdist. The sync_to_async database calls in
        manually created event loops can corrupt connections in parallel
        test environments.
        """
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received_messages.append(message)

            # Use lowercase slug to match the URL pattern (Django slugs are lowercase)
            lowercase_slug = self.private_corpus.slug.lower()
            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{lowercase_slug}/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }

            # Mock validate_corpus_slug to return False (private corpus not visible)
            # This avoids async database connection issues in parallel tests
            with patch(
                "opencontractserver.mcp.server.validate_corpus_slug",
                return_value=False,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            return received_messages

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            # Should get a 404 response (corpus not found since not visible)
            self.assertTrue(len(result) >= 2)
            self.assertEqual(result[0]["type"], "http.response.start")
            self.assertEqual(result[0]["status"], 404)
            body = json.loads(result[1]["body"])
            self.assertIn("not found or not accessible", body["error"])
        finally:
            loop.close()

    def test_asgi_returns_404_for_nonexistent_corpus(self):
        """Test ASGI app returns 404 for nonexistent corpus.

        Mocks validate_corpus_slug to avoid database connection corruption
        when running with pytest-xdist. The sync_to_async database calls in
        manually created event loops can corrupt connections in parallel
        test environments.
        """
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received_messages.append(message)

            scope = {
                "type": "http",
                "path": "/mcp/corpus/nonexistent-corpus-slug/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }

            # Mock validate_corpus_slug to return False (corpus doesn't exist)
            # This avoids async database connection issues in parallel tests
            with patch(
                "opencontractserver.mcp.server.validate_corpus_slug",
                return_value=False,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            return received_messages

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            # Should get a 404 response
            self.assertEqual(result[0]["status"], 404)
            body = json.loads(result[1]["body"])
            self.assertIn("not found or not accessible", body["error"])
        finally:
            loop.close()

    def test_asgi_routes_private_scoped_corpus_with_valid_bearer_token(self):
        """Authenticated scoped endpoints can target private corpuses.

        Uses ``asyncio.run`` (the pattern ``_MCPAsyncRunMixin`` was created
        to encapsulate) so this test does not mutate the thread-global
        event-loop state — the older
        ``new_event_loop / set_event_loop / close`` dance would race if
        xdist ever scheduled two async tests on the same OS thread.
        Migrating the rest of this class is deliberate follow-up.
        """
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received_messages.append(message)

            mock_manager = AsyncMock()
            mock_manager.handle_request = AsyncMock()

            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock(return_value=mock_manager)

            async def mock_get_lifespan(slug):
                return mock_lifespan

            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{self.private_corpus.slug}/",
                "method": "POST",
                "query_string": b"",
                "headers": [(b"authorization", b"Bearer valid-token")],
                "client": ("127.0.0.1", 12345),
            }

            with patch(
                "opencontractserver.mcp.server.get_user_from_jwt_token",
                return_value=self.owner,
            ), patch(
                "opencontractserver.mcp.server.get_scoped_lifespan_manager",
                side_effect=mock_get_lifespan,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            mock_lifespan.ensure_started.assert_called_once()
            mock_manager.handle_request.assert_called_once()

        asyncio.run(run_test())

    def test_asgi_handles_corpus_path_without_trailing_slash(self):
        """Test ASGI app handles /mcp/corpus/{slug} without trailing slash."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            # Mock the scoped session manager
            mock_manager = AsyncMock()
            mock_manager.handle_request = AsyncMock()

            # Mock the lifespan manager - ensure_started should return the manager
            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock(return_value=mock_manager)

            # Create async mock function that returns the mock lifespan
            async def mock_get_lifespan(slug):
                return mock_lifespan

            # Use lowercase slug to match the URL pattern
            lowercase_slug = self.corpus.slug.lower()

            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{lowercase_slug}",  # No trailing slash
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                pass

            with patch(
                "opencontractserver.mcp.server.get_scoped_lifespan_manager",
                side_effect=mock_get_lifespan,
            ), patch(
                "opencontractserver.mcp.server.validate_corpus_slug",
                return_value=True,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            # Verify scoped handlers were still called
            mock_lifespan.ensure_started.assert_called_once()
            mock_manager.handle_request.assert_called_once()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_http_router_routes_corpus_scoped_to_mcp(self):
        """Test HTTP router routes /mcp/corpus/* to MCP app."""
        import asyncio

        from config.asgi import create_http_router

        mcp_called = []

        async def mock_mcp_app(scope, receive, send):
            mcp_called.append(scope["path"])

        async def mock_django_app(scope, receive, send):
            pass

        router = create_http_router(mock_django_app, mock_mcp_app)

        async def run_test():
            async def mock_receive():
                return {"type": "http.disconnect"}

            async def mock_send(message):
                pass

            # Test /mcp/corpus/{slug}/ routes to MCP
            await router(
                {"type": "http", "path": f"/mcp/corpus/{self.corpus.slug}/"},
                mock_receive,
                mock_send,
            )
            await router(
                {"type": "http", "path": f"/mcp/corpus/{self.corpus.slug}"},
                mock_receive,
                mock_send,
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

        self.assertIn(f"/mcp/corpus/{self.corpus.slug}/", mcp_called)
        self.assertIn(f"/mcp/corpus/{self.corpus.slug}", mcp_called)


class MCPScopedEndpointInfoTest(TestCase):
    """Tests for scoped endpoint info in 404 responses."""

    def test_404_includes_corpus_scoped_endpoint_info(self):
        """Test 404 response includes corpus-scoped endpoint info."""
        import asyncio

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.disconnect"}

            async def mock_send(message):
                received_messages.append(message)

            scope = {
                "type": "http",
                "path": "/unknown/path",
                "method": "GET",
                "query_string": b"",
                "headers": [],
            }

            app = create_mcp_asgi_app()
            await app(scope, mock_receive, mock_send)

            return received_messages

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_test())
            body = json.loads(result[1]["body"])

            # Should include corpus_scoped endpoint info
            self.assertIn("corpus_scoped", body["endpoints"])
            corpus_scoped = body["endpoints"]["corpus_scoped"]
            self.assertEqual(corpus_scoped["path"], "/mcp/corpus/{corpus_slug}/")
            self.assertIn("shareable", corpus_scoped["description"].lower())
        finally:
            loop.close()


# =============================================================================
# CACHE BEHAVIOR TESTS
# =============================================================================


class MCPTTLLRUCacheTest(TestCase):
    """Tests for TTLLRUCache behavior including eviction and TTL expiration."""

    def test_cache_lru_eviction(self):
        """Test cache evicts least recently used items when maxsize is reached."""
        import asyncio

        from opencontractserver.mcp.server import TTLLRUCache

        evicted_keys = []

        def cleanup_callback(key, value):
            evicted_keys.append(key)

        async def run_test():
            cache = TTLLRUCache(
                maxsize=3, ttl_seconds=3600, cleanup_callback=cleanup_callback
            )

            # Add 3 items (at capacity)
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")
            await cache.set("key3", "value3")

            self.assertEqual(len(cache), 3)
            self.assertEqual(len(evicted_keys), 0)

            # Add a 4th item - should evict key1 (LRU)
            await cache.set("key4", "value4")

            self.assertEqual(len(cache), 3)
            self.assertIn("key1", evicted_keys)

            # Verify key1 is gone and key4 is present
            self.assertIsNone(await cache.get("key1"))
            self.assertEqual(await cache.get("key4"), "value4")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_cache_lru_access_updates_order(self):
        """Test that accessing an item updates its LRU position."""
        import asyncio

        from opencontractserver.mcp.server import TTLLRUCache

        evicted_keys = []

        def cleanup_callback(key, value):
            evicted_keys.append(key)

        async def run_test():
            cache = TTLLRUCache(
                maxsize=3, ttl_seconds=3600, cleanup_callback=cleanup_callback
            )

            # Add 3 items
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")
            await cache.set("key3", "value3")

            # Access key1, making it most recently used
            await cache.get("key1")

            # Add a 4th item - should evict key2 (now LRU since key1 was accessed)
            await cache.set("key4", "value4")

            self.assertIn("key2", evicted_keys)
            self.assertNotIn("key1", evicted_keys)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_cache_ttl_expiration(self):
        """Test cache entries expire after TTL."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import TTLLRUCache

        cleanup_called = []

        def cleanup_callback(key, value):
            cleanup_called.append(key)

        async def run_test():
            cache = TTLLRUCache(
                maxsize=10, ttl_seconds=60, cleanup_callback=cleanup_callback
            )

            # Mock time to simulate TTL expiration
            with patch("opencontractserver.mcp.server.time") as mock_time:
                # Set initial time
                mock_time.time.return_value = 1000

                await cache.set("key1", "value1")
                self.assertEqual(await cache.get("key1"), "value1")

                # Fast forward past TTL
                mock_time.time.return_value = 1061  # 61 seconds later

                # Should return None and call cleanup
                result = await cache.get("key1")
                self.assertIsNone(result)
                self.assertIn("key1", cleanup_called)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_cache_clear_calls_cleanup(self):
        """Test cache clear calls cleanup for all items."""
        import asyncio

        from opencontractserver.mcp.server import TTLLRUCache

        cleanup_called = []

        def cleanup_callback(key, value):
            cleanup_called.append(key)

        async def run_test():
            cache = TTLLRUCache(
                maxsize=10, ttl_seconds=3600, cleanup_callback=cleanup_callback
            )

            await cache.set("key1", "value1")
            await cache.set("key2", "value2")
            await cache.set("key3", "value3")

            await cache.clear()

            self.assertEqual(len(cache), 0)
            self.assertEqual(set(cleanup_called), {"key1", "key2", "key3"})

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_cache_remove_calls_cleanup(self):
        """Test cache remove calls cleanup for the removed item."""
        import asyncio

        from opencontractserver.mcp.server import TTLLRUCache

        cleanup_called = []

        def cleanup_callback(key, value):
            cleanup_called.append((key, value))

        async def run_test():
            cache = TTLLRUCache(
                maxsize=10, ttl_seconds=3600, cleanup_callback=cleanup_callback
            )

            await cache.set("key1", "value1")
            await cache.set("key2", "value2")

            # Remove key1
            result = await cache.remove("key1")
            self.assertTrue(result)
            self.assertIn(("key1", "value1"), cleanup_called)

            # Try to remove non-existent key
            result = await cache.remove("nonexistent")
            self.assertFalse(result)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


@pytest.mark.serial
@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})
class MCPUppercaseSlugTest(TransactionTestCase):
    """Tests for uppercase/mixed-case corpus slug handling.

    Uses TransactionTestCase because async tests with sync_to_async
    need data committed to be visible across database connections.

    Marked as serial because these tests use sync_to_async with Django ORM
    in manually created event loops, which can cause database connection
    corruption when run in parallel with pytest-xdist.

    CONN_MAX_AGE=0 prevents connection pooling issues with asyncio.run().
    """

    def setUp(self):
        """Create test data with mixed-case slug."""
        self.owner = User.objects.create_user(
            username="uppercaseowner",
            email="uppercase@test.com",
            password="testpass123",
        )

        # Create corpus - Django will generate a slug
        self.corpus = Corpus.objects.create(
            title="Legal-Contracts-2024",  # Mixed case title
            description="Test corpus with mixed case",
            creator=self.owner,
            is_public=True,
        )

    def tearDown(self):
        """Close all database connections to prevent stale connections."""
        from django import db

        db.connections.close_all()

    def test_uri_parser_accepts_uppercase_slugs(self):
        """Test URIParser accepts uppercase letters in slugs."""
        from opencontractserver.mcp.server import URIParser

        # Test with uppercase
        result = URIParser.parse_corpus("corpus://Legal-Contracts-2024")
        self.assertEqual(result, "Legal-Contracts-2024")

        # Test with mixed case
        result = URIParser.parse_document("document://MyCorpus/MyDoc")
        self.assertEqual(result, ("MyCorpus", "MyDoc"))

        # Test annotation with uppercase
        result = URIParser.parse_annotation("annotation://Corp/Doc/123")
        self.assertEqual(result, ("Corp", "Doc", 123))

        # Test thread with uppercase
        result = URIParser.parse_thread("thread://MyCorpus/threads/456")
        self.assertEqual(result, ("MyCorpus", 456))

    def test_asgi_path_regex_accepts_uppercase(self):
        """Test ASGI routing regex accepts uppercase corpus slugs."""
        import re

        # This is the pattern from create_mcp_asgi_app
        corpus_path_pattern = re.compile(r"^/mcp/corpus/([A-Za-z0-9\-]+)/?$")

        # Test uppercase
        match = corpus_path_pattern.match("/mcp/corpus/Legal-Contracts-2024/")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "Legal-Contracts-2024")

        # Test mixed case without trailing slash
        match = corpus_path_pattern.match("/mcp/corpus/MyCorpus")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "MyCorpus")

    def test_scoped_endpoint_with_uppercase_slug(self):
        """Test scoped endpoint works with uppercase corpus slug."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            # Mock the managers
            mock_manager = AsyncMock()
            mock_manager.handle_request = AsyncMock()

            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock(return_value=mock_manager)

            async def mock_get_lifespan(slug):
                return mock_lifespan

            # Use uppercase slug in path
            scope = {
                "type": "http",
                "path": "/mcp/corpus/Legal-Contracts-2024/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            received = []

            async def mock_send(message):
                received.append(message)

            with patch(
                "opencontractserver.mcp.server.get_scoped_lifespan_manager",
                side_effect=mock_get_lifespan,
            ), patch(
                "opencontractserver.mcp.server.validate_corpus_slug",
                return_value=True,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            # Verify the handler was called (not 404)
            mock_lifespan.ensure_started.assert_called_once()
            mock_manager.handle_request.assert_called_once()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


@pytest.mark.serial
@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})
class MCPPermissionChangeTest(TransactionTestCase):
    """Tests for corpus permission changes during active sessions.

    Marked as serial because these tests use sync_to_async with Django ORM
    in manually created event loops, which can cause database connection
    corruption when run in parallel with pytest-xdist.

    CONN_MAX_AGE=0 prevents connection pooling issues with asyncio.run().
    """

    def setUp(self):
        """Create test data."""
        self.owner = User.objects.create_user(
            username="permchangeowner",
            email="permchange@test.com",
            password="testpass123",
        )

        self.corpus = Corpus.objects.create(
            title="Permission Change Test Corpus",
            description="Test corpus for permission changes",
            creator=self.owner,
            is_public=True,  # Start as public
        )

    def tearDown(self):
        """Close all database connections to prevent stale connections."""
        from django import db

        db.connections.close_all()

    def test_scoped_server_revalidates_permissions_on_tool_call(self):
        """Test that scoped server re-validates corpus permissions on each tool call.

        Mocks the Corpus queryset to avoid async database connection issues
        in parallel test environments. Tests the function's logic by changing
        mock return values to simulate permission changes.
        """
        import asyncio
        from unittest.mock import MagicMock, patch

        from opencontractserver.mcp.server import validate_corpus_slug

        # Track call count to return different values on subsequent calls
        call_count = 0

        def mock_visible_to_user(user):
            nonlocal call_count
            call_count += 1
            mock_queryset = MagicMock()
            # First call: corpus is public (exists returns True)
            # Second call: corpus is private (exists returns False)
            mock_queryset.filter.return_value.exists.return_value = call_count == 1
            return mock_queryset

        async def run_test():
            with patch(
                "opencontractserver.corpuses.models.Corpus.objects.visible_to_user",
                side_effect=mock_visible_to_user,
            ):
                # Initially should be valid (corpus is public)
                is_valid = await validate_corpus_slug(self.corpus.slug)
                self.assertTrue(is_valid)

                # Second call should be invalid (simulating corpus became private)
                is_valid = await validate_corpus_slug(self.corpus.slug)
                self.assertFalse(is_valid)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_asgi_rejects_request_after_corpus_becomes_private(self):
        """Test ASGI endpoint rejects requests after corpus becomes private.

        Mocks the Corpus queryset to avoid async database connection issues
        in parallel test environments. The mock returns empty queryset to
        simulate a private corpus (not visible to anonymous users).
        """
        import asyncio
        from unittest.mock import MagicMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        # Mock queryset returns False for exists() - corpus not visible (private)
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value.exists.return_value = False

        async def run_test():
            received = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received.append(message)

            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{self.corpus.slug}/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }

            app = create_mcp_asgi_app()

            # Mock the visibility check to return False (corpus is private)
            with patch(
                "opencontractserver.corpuses.models.Corpus.objects.visible_to_user",
                return_value=mock_queryset,
            ):
                await app(scope, mock_receive, mock_send)

            # Should get 404 (corpus not found/not accessible)
            self.assertEqual(received[0]["type"], "http.response.start")
            self.assertEqual(received[0]["status"], 404)
            body = json.loads(received[1]["body"])
            self.assertIn("not found or not accessible", body["error"])

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


class MCPCleanupCallbackErrorTest(TestCase):
    """Tests for cleanup callback error handling."""

    def test_cleanup_callback_error_logged(self):
        """Test that cleanup callback errors are logged, not swallowed."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import _cleanup_lifespan_manager

        async def run_test():
            # Create a mock manager
            from unittest.mock import AsyncMock, MagicMock

            mock_manager = MagicMock()
            mock_manager.shutdown = AsyncMock()
            mock_manager.corpus_slug = "test-corpus"

            # Mock asyncio.get_event_loop to raise RuntimeError
            with patch("asyncio.get_event_loop", side_effect=RuntimeError("No loop")):
                with patch("opencontractserver.mcp.server.logger") as mock_logger:
                    # This should log a warning, not raise
                    _cleanup_lifespan_manager("test-key", mock_manager)

                    # Verify warning was logged
                    mock_logger.warning.assert_called_once()
                    call_args = mock_logger.warning.call_args[0][0]
                    self.assertIn("Could not schedule cleanup", call_args)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


class MCPSendErrorHandlingTest(TestCase):
    """Tests for error handling when send() fails."""

    def test_mcp_error_response_send_failure_logged(self):
        """Test that send() failures during error response are logged."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            # Mock send to fail
            async def mock_send_fails(message):
                raise ConnectionError("Client disconnected")

            scope = {
                "type": "http",
                "path": "/mcp",
                "method": "POST",
                "query_string": b"",
                "headers": [[b"content-type", b"application/json"]],
                "client": ("127.0.0.1", 12345),
            }

            # Mock the session manager to raise an error
            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock()

            mock_manager = AsyncMock()
            mock_manager.handle_request.side_effect = Exception("Test error")

            with patch(
                "opencontractserver.mcp.server.lifespan_manager", mock_lifespan
            ), patch(
                "opencontractserver.mcp.server.get_session_manager",
                return_value=mock_manager,
            ), patch(
                "opencontractserver.mcp.server.logger"
            ) as mock_logger:
                app = create_mcp_asgi_app()
                # This should not raise, even though send fails
                await app(scope, mock_receive, mock_send_fails)

                # Should have logged both the original error and the send failure
                self.assertTrue(mock_logger.error.called)
                self.assertTrue(mock_logger.warning.called)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


class MCPTTLLRUCacheNoCallbackTest(TestCase):
    """Tests for TTLLRUCache without cleanup callback."""

    def test_cache_without_cleanup_callback(self):
        """Test cache operations work without cleanup callback."""
        import asyncio

        from opencontractserver.mcp.server import TTLLRUCache

        async def run_test():
            # Create cache without cleanup callback
            cache = TTLLRUCache(maxsize=2, ttl_seconds=3600, cleanup_callback=None)

            # Add items
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")

            # Get items
            self.assertEqual(await cache.get("key1"), "value1")
            self.assertEqual(await cache.get("key2"), "value2")

            # Eviction should work without callback
            await cache.set("key3", "value3")  # Should evict key1
            self.assertIsNone(await cache.get("key1"))
            self.assertEqual(await cache.get("key3"), "value3")

            # Remove should work without callback
            result = await cache.remove("key2")
            self.assertTrue(result)

            # Clear should work without callback
            await cache.clear()
            self.assertEqual(len(cache), 0)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_cache_ttl_expiration_without_callback(self):
        """Test TTL expiration works without cleanup callback."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import TTLLRUCache

        async def run_test():
            cache = TTLLRUCache(maxsize=10, ttl_seconds=60, cleanup_callback=None)

            with patch("opencontractserver.mcp.server.time") as mock_time:
                mock_time.time.return_value = 1000
                await cache.set("key1", "value1")

                # Fast forward past TTL
                mock_time.time.return_value = 1061

                # Should return None (expired) without crashing
                result = await cache.get("key1")
                self.assertIsNone(result)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


@pytest.mark.serial
@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})
class MCPScopedLifespanManagerShutdownTest(TransactionTestCase):
    """Tests for ScopedMCPLifespanManager shutdown error handling.

    Uses TransactionTestCase because async tests with sync_to_async
    need data committed to be visible across database connections.

    Marked as serial because these tests use sync_to_async with Django ORM
    in manually created event loops, which can cause database connection
    corruption when run in parallel with pytest-xdist.

    CONN_MAX_AGE=0 prevents connection pooling issues with asyncio.run().
    """

    def setUp(self):
        """Create test data."""
        self.owner = User.objects.create_user(
            username="shutdowntestowner",
            email="shutdowntest@test.com",
            password="testpass123",
        )

        self.corpus = Corpus.objects.create(
            title="Shutdown Test Corpus",
            creator=self.owner,
            is_public=True,
        )

    def tearDown(self):
        """Close all database connections to prevent stale connections."""
        from django import db

        db.connections.close_all()

    def test_lifespan_manager_shutdown_error_handling(self):
        """Test ScopedMCPLifespanManager handles shutdown errors gracefully."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from opencontractserver.mcp.server import ScopedMCPLifespanManager

        async def run_test():
            manager = ScopedMCPLifespanManager(self.corpus.slug)

            # Manually set state as if started
            manager._started = True

            # Create a mock run_context that raises on __aexit__
            mock_context = MagicMock()
            mock_context.__aexit__ = AsyncMock(side_effect=Exception("Shutdown error"))
            manager._run_context = mock_context

            with patch("opencontractserver.mcp.server.logger") as mock_logger:
                # Should not raise, just log warning
                await manager.shutdown()

                # Verify warning was logged
                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args[0][0]
                self.assertIn("Error shutting down", call_args)

            # State should be reset
            self.assertFalse(manager._started)
            self.assertIsNone(manager._run_context)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


@pytest.mark.serial
@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})
class MCPScopedASGIErrorHandlingTest(TransactionTestCase):
    """Tests for scoped ASGI endpoint error handling.

    Uses TransactionTestCase because async tests with sync_to_async
    need data committed to be visible across database connections.

    Marked as serial because these tests use sync_to_async with Django ORM
    in manually created event loops, which can cause database connection
    corruption when run in parallel with pytest-xdist.

    CONN_MAX_AGE=0 prevents connection pooling issues with asyncio.run().
    """

    def setUp(self):
        """Create test data."""
        self.owner = User.objects.create_user(
            username="scopederrorowner",
            email="scopederror@test.com",
            password="testpass123",
        )

        self.corpus = Corpus.objects.create(
            title="Scoped Error Test Corpus",
            creator=self.owner,
            is_public=True,
        )

    def tearDown(self):
        """Close all database connections to prevent stale connections."""
        from django import db

        db.connections.close_all()

    def test_scoped_asgi_error_returns_500(self):
        """Test scoped ASGI endpoint returns 500 on internal error."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received_messages = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received_messages.append(message)

            # Mock the scoped session manager to raise an exception
            mock_manager = AsyncMock()
            mock_manager.handle_request.side_effect = Exception("Scoped test error")

            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock(return_value=mock_manager)

            async def mock_get_lifespan(slug):
                return mock_lifespan

            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{self.corpus.slug}/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }

            with patch(
                "opencontractserver.mcp.server.get_scoped_lifespan_manager",
                side_effect=mock_get_lifespan,
            ), patch(
                "opencontractserver.mcp.server.validate_corpus_slug",
                return_value=True,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

            # Should get a 500 error response
            self.assertTrue(len(received_messages) >= 2)
            self.assertEqual(received_messages[0]["type"], "http.response.start")
            self.assertEqual(received_messages[0]["status"], 500)
            body = json.loads(received_messages[1]["body"])
            self.assertIn("error", body)
            self.assertEqual(body["error"], "Scoped test error")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_scoped_asgi_send_failure_logged(self):
        """Test scoped ASGI logs send failures during error response."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            # Mock send to fail
            async def mock_send_fails(message):
                raise ConnectionError("Client disconnected")

            # Mock the scoped session manager to raise an exception
            mock_manager = AsyncMock()
            mock_manager.handle_request.side_effect = Exception("Scoped test error")

            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock(return_value=mock_manager)

            async def mock_get_lifespan(slug):
                return mock_lifespan

            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{self.corpus.slug}/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }

            with patch(
                "opencontractserver.mcp.server.get_scoped_lifespan_manager",
                side_effect=mock_get_lifespan,
            ), patch(
                "opencontractserver.mcp.server.validate_corpus_slug",
                return_value=True,
            ), patch(
                "opencontractserver.mcp.server.logger"
            ) as mock_logger:
                app = create_mcp_asgi_app()
                # Should not raise, even though send fails
                await app(scope, mock_receive, mock_send_fails)

                # Should have logged both the original error and the send failure
                self.assertTrue(mock_logger.error.called)
                self.assertTrue(mock_logger.warning.called)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


@pytest.mark.serial
@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})
class MCPScopedToolCallPermissionTest(TransactionTestCase):
    """Tests for scoped tool call permission errors via ASGI endpoint.

    Uses TransactionTestCase because tests use database operations.

    Marked as serial to prevent database connection issues when run
    in parallel with pytest-xdist.

    CONN_MAX_AGE=0 prevents connection pooling issues.
    """

    def setUp(self):
        """Create test data."""
        self.owner = User.objects.create_user(
            username="scopedpermowner",
            email="scopedperm@test.com",
            password="testpass123",
        )

        self.corpus = Corpus.objects.create(
            title="Scoped Permission Test Corpus",
            creator=self.owner,
            is_public=True,
        )

    def tearDown(self):
        """Close all database connections to prevent stale connections."""
        from django import db

        db.connections.close_all()

    def test_scoped_server_validates_corpus_on_creation(self):
        """Test that scoped server is created correctly for valid corpus."""
        from opencontractserver.mcp.server import create_scoped_mcp_server

        server = create_scoped_mcp_server(self.corpus.slug)
        self.assertIsNotNone(server)
        self.assertEqual(server.name, f"opencontracts-corpus-{self.corpus.slug}")

    def test_get_scoped_tool_definitions_has_no_corpus_slug_required(self):
        """Test scoped tool definitions don't require corpus_slug argument."""
        from opencontractserver.mcp.server import get_scoped_tool_definitions

        tools = get_scoped_tool_definitions(self.corpus.slug)

        # Find the list_documents tool
        list_docs_tool = next((t for t in tools if t.name == "list_documents"), None)
        self.assertIsNotNone(list_docs_tool)

        # Verify corpus_slug is not required
        required_params = list_docs_tool.inputSchema.get("required", [])
        self.assertNotIn("corpus_slug", required_params)

    def test_get_scoped_tool_definitions_includes_get_corpus_info(self):
        """Test scoped tool definitions include get_corpus_info tool."""
        from opencontractserver.mcp.server import get_scoped_tool_definitions

        tools = get_scoped_tool_definitions(self.corpus.slug)

        # Find the get_corpus_info tool
        corpus_info_tool = next((t for t in tools if t.name == "get_corpus_info"), None)
        self.assertIsNotNone(corpus_info_tool)

        # get_corpus_info should have no required params
        required_params = corpus_info_tool.inputSchema.get("required", [])
        self.assertEqual(required_params, [])


class MCPScopedToolsWithLabelSetTest(TestCase):
    """Tests for get_corpus_info with label set."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with label set."""
        from opencontractserver.annotations.models import AnnotationLabel, LabelSet

        cls.owner = User.objects.create_user(
            username="scopedlabelowner",
            email="scopedlabel@test.com",
            password="testpass123",
        )

        cls.label_set = LabelSet.objects.create(
            title="Scoped Test Label Set",
            description="Label set for scoped tool tests",
            creator=cls.owner,
            is_public=True,
        )

        cls.label1 = AnnotationLabel.objects.create(
            text="Scoped Label A",
            color="#111111",
            label_type="TOKEN_LABEL",
            description="First scoped label",
            creator=cls.owner,
            is_public=True,
        )

        cls.label2 = AnnotationLabel.objects.create(
            text="Scoped Label B",
            color="#222222",
            label_type="SPAN_LABEL",
            description="Second scoped label",
            creator=cls.owner,
            is_public=True,
        )

        cls.label_set.annotation_labels.add(cls.label1, cls.label2)

        cls.corpus = Corpus.objects.create(
            title="Scoped Corpus With Labels",
            description="Test corpus with label set for scoped tools",
            creator=cls.owner,
            is_public=True,
            label_set=cls.label_set,
            allow_comments=True,
        )

    def test_get_corpus_info_with_label_set(self):
        """Test get_corpus_info returns label set data."""
        from opencontractserver.mcp.tools import get_corpus_info

        result = get_corpus_info(self.corpus.slug)

        self.assertEqual(result["slug"], self.corpus.slug)
        self.assertEqual(result["title"], "Scoped Corpus With Labels")

        # Verify label set data
        self.assertIsNotNone(result["label_set"])
        self.assertEqual(result["label_set"]["title"], "Scoped Test Label Set")
        self.assertEqual(
            result["label_set"]["description"], "Label set for scoped tool tests"
        )
        self.assertEqual(len(result["label_set"]["labels"]), 2)

        # Verify label details
        label_texts = [label["text"] for label in result["label_set"]["labels"]]
        self.assertIn("Scoped Label A", label_texts)
        self.assertIn("Scoped Label B", label_texts)

        # Verify label properties
        label_a = next(
            lbl
            for lbl in result["label_set"]["labels"]
            if lbl["text"] == "Scoped Label A"
        )
        self.assertEqual(label_a["color"], "#111111")
        self.assertEqual(label_a["label_type"], "TOKEN_LABEL")
        self.assertEqual(label_a["description"], "First scoped label")

    def test_get_corpus_info_without_label_set(self):
        """Test get_corpus_info returns None for label_set when not present."""
        # Create corpus without label set
        corpus_no_labels = Corpus.objects.create(
            title="Corpus Without Labels",
            creator=self.owner,
            is_public=True,
        )

        from opencontractserver.mcp.tools import get_corpus_info

        result = get_corpus_info(corpus_no_labels.slug)

        self.assertEqual(result["slug"], corpus_no_labels.slug)
        self.assertIsNone(result["label_set"])


class MCPAnnotationResourceDocumentNotFoundTest(TestCase):
    """Tests for annotation resource when document is not found."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.owner = User.objects.create_user(
            username="annnotfoundowner",
            email="annnotfound@test.com",
            password="testpass123",
        )

        cls.corpus = Corpus.objects.create(
            title="Annotation Not Found Test Corpus",
            creator=cls.owner,
            is_public=True,
        )

    def test_get_annotation_resource_document_not_found(self):
        """Test get_annotation_resource raises when document not in corpus."""
        from opencontractserver.documents.models import Document
        from opencontractserver.mcp.resources import get_annotation_resource

        with self.assertRaises(Document.DoesNotExist):
            get_annotation_resource(self.corpus.slug, "nonexistent-document-slug", 123)


class MCPCleanupSessionManagerTest(TestCase):
    """Tests for _cleanup_session_manager function."""

    def test_cleanup_session_manager_logs(self):
        """Test _cleanup_session_manager logs info message."""
        from unittest.mock import MagicMock, patch

        from opencontractserver.mcp.server import _cleanup_session_manager

        mock_manager = MagicMock()

        with patch("opencontractserver.mcp.server.logger") as mock_logger:
            _cleanup_session_manager("test-key", mock_manager)

            # Should log info message
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            self.assertIn("Cleaning up session manager", call_args)
            self.assertIn("test-key", call_args)


class MCPScopedResourceDefinitionsEmptyCorpusTest(TestCase):
    """Tests for scoped resource definitions with nonexistent corpus."""

    def test_get_scoped_resource_definitions_nonexistent_corpus(self):
        """Test get_scoped_resource_definitions returns empty for nonexistent corpus."""
        from opencontractserver.mcp.server import get_scoped_resource_definitions

        resources = get_scoped_resource_definitions("nonexistent-corpus-slug")

        # Should return empty list for nonexistent corpus
        self.assertEqual(len(resources), 0)


class MCPCacheUpdateExistingKeyTest(TestCase):
    """Tests for TTLLRUCache update behavior."""

    def test_cache_set_updates_existing_key(self):
        """Test cache set updates value and timestamp for existing key."""
        import asyncio
        from unittest.mock import patch

        from opencontractserver.mcp.server import TTLLRUCache

        async def run_test():
            cache = TTLLRUCache(maxsize=10, ttl_seconds=60, cleanup_callback=None)

            with patch("opencontractserver.mcp.server.time") as mock_time:
                # Set initial value
                mock_time.time.return_value = 1000
                await cache.set("key1", "value1")

                # Update the value
                mock_time.time.return_value = 1030
                await cache.set("key1", "value2")

                # Value should be updated
                self.assertEqual(await cache.get("key1"), "value2")

                # TTL should be reset, so not expired yet at 1089
                mock_time.time.return_value = 1089
                self.assertEqual(await cache.get("key1"), "value2")

                # But should expire at 1091 (61 seconds after update)
                mock_time.time.return_value = 1091
                self.assertIsNone(await cache.get("key1"))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


class MCPCleanupLifespanManagerEventLoopRunningTest(TestCase):
    """Tests for _cleanup_lifespan_manager when event loop is running."""

    def test_cleanup_schedules_shutdown_task(self):
        """Test _cleanup_lifespan_manager schedules shutdown task when loop running."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from opencontractserver.mcp.server import _cleanup_lifespan_manager

        mock_manager = MagicMock()
        mock_manager.shutdown = AsyncMock()
        mock_manager.corpus_slug = "test-corpus"

        # Create a mock loop that is running
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        mock_loop.create_task = MagicMock()

        with patch("asyncio.get_event_loop", return_value=mock_loop), patch(
            "opencontractserver.mcp.server.logger"
        ) as mock_logger:
            _cleanup_lifespan_manager("test-key", mock_manager)

            # Should log info
            mock_logger.info.assert_called_once()

            # Should schedule shutdown task
            mock_loop.create_task.assert_called_once()
            # The argument should be the coroutine from manager.shutdown()
            call_args = mock_loop.create_task.call_args[0][0]
            self.assertIsNotNone(call_args)


class AsyncMCPTelemetryFunctionsTest(TestCase):
    """Direct tests for async MCP telemetry functions in opencontractserver/mcp/telemetry.py.

    These functions are always mocked at the server.py level in integration tests,
    so this class tests the actual function logic: property construction,
    context inclusion, and error_type handling.
    """

    def setUp(self):
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

    def tearDown(self):
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

    # ── arecord_mcp_tool_call ────────────────────────────────────────────

    def test_arecord_mcp_tool_call_success_no_context(self):
        """Test async tool call telemetry with no request context."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import arecord_mcp_tool_call

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(arecord_mcp_tool_call("list_documents"))

        self.assertTrue(result)
        mock_event.assert_called_once()
        event_name, props = mock_event.call_args[0]
        self.assertEqual(event_name, "mcp_tool_call")
        self.assertEqual(props["tool_name"], "list_documents")
        self.assertTrue(props["success"])
        self.assertEqual(props["transport"], "unknown")
        self.assertNotIn("client_ip_hash", props)
        self.assertNotIn("error_type", props)

    def test_arecord_mcp_tool_call_with_context(self):
        """Test async tool call telemetry includes client IP hash from context."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import (
            arecord_mcp_tool_call,
            set_request_context,
        )

        set_request_context(client_ip="10.0.0.1", transport="streamable_http")

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(arecord_mcp_tool_call("search_corpus"))

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertEqual(props["transport"], "streamable_http")
        self.assertIn("client_ip_hash", props)
        self.assertEqual(len(props["client_ip_hash"]), 16)

    def test_arecord_mcp_tool_call_failure_with_error_type(self):
        """Test async tool call telemetry records error_type on failure."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import arecord_mcp_tool_call

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(
                arecord_mcp_tool_call(
                    "bad_tool", success=False, error_type="ValueError"
                )
            )

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertFalse(props["success"])
        self.assertEqual(props["error_type"], "ValueError")

    def test_arecord_mcp_tool_call_failure_with_context_and_error(self):
        """Test async tool call telemetry with both context and error."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import (
            arecord_mcp_tool_call,
            set_request_context,
        )

        set_request_context(client_ip="192.168.1.1", transport="sse")

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(
                arecord_mcp_tool_call(
                    "unknown_tool", success=False, error_type="UnknownTool"
                )
            )

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertIn("client_ip_hash", props)
        self.assertEqual(props["error_type"], "UnknownTool")
        self.assertEqual(props["transport"], "sse")

    # ── arecord_mcp_resource_read ────────────────────────────────────────

    def test_arecord_mcp_resource_read_success_no_context(self):
        """Test async resource read telemetry with no request context."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import arecord_mcp_resource_read

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(arecord_mcp_resource_read("corpus"))

        self.assertTrue(result)
        event_name, props = mock_event.call_args[0]
        self.assertEqual(event_name, "mcp_resource_read")
        self.assertEqual(props["resource_type"], "corpus")
        self.assertTrue(props["success"])
        self.assertEqual(props["transport"], "unknown")
        self.assertNotIn("client_ip_hash", props)
        self.assertNotIn("error_type", props)

    def test_arecord_mcp_resource_read_with_context(self):
        """Test async resource read telemetry includes client IP hash."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import (
            arecord_mcp_resource_read,
            set_request_context,
        )

        set_request_context(client_ip="172.16.0.5", transport="streamable_http_scoped")

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(arecord_mcp_resource_read("document"))

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertIn("client_ip_hash", props)
        self.assertEqual(props["transport"], "streamable_http_scoped")

    def test_arecord_mcp_resource_read_failure_with_error_type(self):
        """Test async resource read telemetry records error_type on failure."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import arecord_mcp_resource_read

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(
                arecord_mcp_resource_read(
                    "unknown", success=False, error_type="ValueError"
                )
            )

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertFalse(props["success"])
        self.assertEqual(props["error_type"], "ValueError")

    def test_arecord_mcp_resource_read_failure_with_context_and_error(self):
        """Test async resource read telemetry with both context and error."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import (
            arecord_mcp_resource_read,
            set_request_context,
        )

        set_request_context(client_ip="10.10.10.10", transport="streamable_http")

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(
                arecord_mcp_resource_read(
                    "annotation", success=False, error_type="DoesNotExist"
                )
            )

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertIn("client_ip_hash", props)
        self.assertEqual(props["error_type"], "DoesNotExist")

    # ── arecord_mcp_request ──────────────────────────────────────────────

    def test_arecord_mcp_request_success_no_context(self):
        """Test async request telemetry with no request context."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import arecord_mcp_request

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(arecord_mcp_request("/mcp", method="POST"))

        self.assertTrue(result)
        event_name, props = mock_event.call_args[0]
        self.assertEqual(event_name, "mcp_request")
        self.assertEqual(props["endpoint"], "/mcp")
        self.assertEqual(props["method"], "POST")
        self.assertTrue(props["success"])
        self.assertEqual(props["transport"], "unknown")
        self.assertNotIn("client_ip_hash", props)
        self.assertNotIn("error_type", props)

    def test_arecord_mcp_request_with_context(self):
        """Test async request telemetry includes client IP hash."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import (
            arecord_mcp_request,
            set_request_context,
        )

        set_request_context(client_ip="8.8.8.8", transport="sse")

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(arecord_mcp_request("/sse", method="GET"))

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertIn("client_ip_hash", props)
        self.assertEqual(props["transport"], "sse")
        self.assertEqual(props["method"], "GET")

    def test_arecord_mcp_request_failure_with_error_type(self):
        """Test async request telemetry records error_type on failure."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import arecord_mcp_request

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(
                arecord_mcp_request("/mcp", success=False, error_type="ConnectionError")
            )

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertFalse(props["success"])
        self.assertEqual(props["error_type"], "ConnectionError")

    def test_arecord_mcp_request_failure_with_context_and_error(self):
        """Test async request telemetry with both context and error."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from opencontractserver.mcp.telemetry import (
            arecord_mcp_request,
            set_request_context,
        )

        set_request_context(client_ip="203.0.113.50", transport="streamable_http")

        with patch(
            "opencontractserver.mcp.telemetry.arecord_event",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_event:
            result = asyncio.run(
                arecord_mcp_request(
                    "/mcp/corpus/test-slug",
                    method="POST",
                    success=False,
                    error_type="TimeoutError",
                )
            )

        self.assertTrue(result)
        _, props = mock_event.call_args[0]
        self.assertIn("client_ip_hash", props)
        self.assertEqual(props["error_type"], "TimeoutError")
        self.assertEqual(props["endpoint"], "/mcp/corpus/test-slug")


class MCPServerCallToolExceptionTest(TestCase):
    """Tests for call_tool_handler exception path in server.py.

    Covers the `except Exception` branch where a tool handler raises
    and telemetry records the error_type.
    """

    def setUp(self):
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

    def tearDown(self):
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

    def test_call_tool_handler_exception_records_error_type(self):
        """Test call_tool_handler records error_type when handler raises."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from opencontractserver.mcp.server import TOOL_HANDLERS, call_tool_handler

        async def run_test():
            # Mock a tool handler that raises
            mock_handler = MagicMock(side_effect=RuntimeError("handler broke"))
            original = TOOL_HANDLERS.get("list_public_corpuses")
            TOOL_HANDLERS["list_public_corpuses"] = mock_handler

            try:
                with patch(
                    "opencontractserver.mcp.server.arecord_mcp_tool_call",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as mock_record:
                    with self.assertRaises(RuntimeError):
                        await call_tool_handler("list_public_corpuses", {})

                    # Verify failure telemetry with error_type was recorded
                    mock_record.assert_called_with(
                        "list_public_corpuses",
                        success=False,
                        error_type="RuntimeError",
                        corpus_slug=None,
                        document_slug=None,
                    )
            finally:
                if original is not None:
                    TOOL_HANDLERS["list_public_corpuses"] = original

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


class MCPScopedCallToolTelemetryTest(TransactionTestCase):
    """Tests for telemetry in the scoped server's call_tool handler.

    Uses TransactionTestCase because scoped server uses sync_to_async
    for corpus validation which requires cross-thread DB visibility.
    """

    def setUp(self):
        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()

        self.owner = User.objects.create_user(
            username="scopedtoolowner",
            email="scopedtool@test.com",
            password="testpass123",
        )
        self.corpus = Corpus.objects.create(
            title="Scoped Tool Telemetry Corpus",
            description="Test corpus",
            creator=self.owner,
            is_public=True,
        )

    def tearDown(self):
        from django import db

        from opencontractserver.mcp.telemetry import clear_request_context

        clear_request_context()
        db.connections.close_all()

    def test_scoped_asgi_success_records_request_telemetry(self):
        """Test scoped ASGI success path records arecord_mcp_request."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received.append(message)

            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{self.corpus.slug}/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("192.168.1.100", 54321),
            }

            # Mock corpus validation to pass
            mock_qs = MagicMock()
            mock_qs.filter.return_value.exists.return_value = True

            mock_scoped_manager = AsyncMock()
            mock_scoped_manager.handle_request = AsyncMock()

            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock(return_value=mock_scoped_manager)

            with patch(
                "opencontractserver.corpuses.models.Corpus.objects.visible_to_user",
                return_value=mock_qs,
            ), patch(
                "opencontractserver.mcp.server.get_scoped_lifespan_manager",
                new_callable=AsyncMock,
                return_value=mock_lifespan,
            ), patch(
                "opencontractserver.mcp.server.arecord_mcp_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_record:
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

                # Verify success telemetry was recorded for scoped path
                mock_record.assert_called_once_with(
                    f"/mcp/corpus/{self.corpus.slug}",
                    method="POST",
                    success=True,
                )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_scoped_asgi_error_records_failure_telemetry(self):
        """Test scoped ASGI error path records failure telemetry."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        async def run_test():
            received = []

            async def mock_receive():
                return {"type": "http.request", "body": b"{}"}

            async def mock_send(message):
                received.append(message)

            scope = {
                "type": "http",
                "path": f"/mcp/corpus/{self.corpus.slug}/",
                "method": "POST",
                "query_string": b"",
                "headers": [],
                "client": ("192.168.1.100", 54321),
            }

            # Mock corpus validation to pass
            mock_qs = MagicMock()
            mock_qs.filter.return_value.exists.return_value = True

            mock_scoped_manager = AsyncMock()
            mock_scoped_manager.handle_request = AsyncMock(
                side_effect=Exception("Scoped handler error")
            )

            mock_lifespan = AsyncMock()
            mock_lifespan.ensure_started = AsyncMock(return_value=mock_scoped_manager)

            with patch(
                "opencontractserver.corpuses.models.Corpus.objects.visible_to_user",
                return_value=mock_qs,
            ), patch(
                "opencontractserver.mcp.server.get_scoped_lifespan_manager",
                new_callable=AsyncMock,
                return_value=mock_lifespan,
            ), patch(
                "opencontractserver.mcp.server.arecord_mcp_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_record:
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

                # Verify failure telemetry was recorded for scoped path
                mock_record.assert_called_once_with(
                    f"/mcp/corpus/{self.corpus.slug}",
                    method="POST",
                    success=False,
                    error_type="Exception",
                )

            # Should get a 500 error response
            self.assertTrue(len(received) >= 2)
            self.assertEqual(received[0]["status"], 500)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


class MCPAuthenticatedToolsTest(TestCase):
    """Tests for authenticated MCP tool execution.

    Verifies that:
    - Read tools honor `visible_to_user(user)` for private resources.
    - `create_thread_message` enforces authentication, content limits,
      and visibility checks.
    """

    @classmethod
    def setUpTestData(cls):
        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )

        cls.owner = User.objects.create_user(
            username="mcpauthowner",
            email="mcpauth@test.com",
            password="testpass123",
        )
        cls.other_user = User.objects.create_user(
            username="mcpauthother",
            email="mcpauthother@test.com",
            password="testpass123",
        )
        cls.private_corpus = Corpus.objects.create(
            title="MCP Auth Private Corpus",
            creator=cls.owner,
            is_public=False,
        )
        cls.private_thread = Conversation.objects.create(
            title="Private Thread",
            creator=cls.owner,
            is_public=False,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=cls.private_corpus,
        )

    def test_list_public_corpuses_returns_private_for_owner(self):
        from opencontractserver.mcp.tools import list_public_corpuses

        result = list_public_corpuses(user=self.owner)
        slugs = [c["slug"] for c in result["corpuses"]]
        self.assertIn(self.private_corpus.slug, slugs)

    def test_list_public_corpuses_hides_private_for_anonymous(self):
        from opencontractserver.mcp.tools import list_public_corpuses

        result = list_public_corpuses(user=AnonymousUser())
        slugs = [c["slug"] for c in result["corpuses"]]
        self.assertNotIn(self.private_corpus.slug, slugs)

    def test_list_public_corpuses_no_user_arg_behaves_anonymously(self):
        from opencontractserver.mcp.tools import list_public_corpuses

        result = list_public_corpuses()
        slugs = [c["slug"] for c in result["corpuses"]]
        self.assertNotIn(self.private_corpus.slug, slugs)

    def test_create_thread_message_requires_authentication(self):
        from django.core.exceptions import PermissionDenied

        from opencontractserver.mcp.tools import create_thread_message

        with self.assertRaises(PermissionDenied):
            create_thread_message(
                corpus_slug=self.private_corpus.slug,
                thread_id=self.private_thread.id,
                content="hi",
                user=AnonymousUser(),
            )

        with self.assertRaises(PermissionDenied):
            create_thread_message(
                corpus_slug=self.private_corpus.slug,
                thread_id=self.private_thread.id,
                content="hi",
            )

    def test_create_thread_message_rejects_blank_content(self):
        from django.core.exceptions import ValidationError

        from opencontractserver.mcp.tools import create_thread_message

        with self.assertRaises(ValidationError):
            create_thread_message(
                corpus_slug=self.private_corpus.slug,
                thread_id=self.private_thread.id,
                content="   ",
                user=self.owner,
            )

    def test_create_thread_message_rejects_oversized_content(self):
        from django.core.exceptions import ValidationError

        from opencontractserver.constants.mcp import MAX_THREAD_MESSAGE_LENGTH
        from opencontractserver.mcp.tools import create_thread_message

        with self.assertRaises(ValidationError):
            create_thread_message(
                corpus_slug=self.private_corpus.slug,
                thread_id=self.private_thread.id,
                content="x" * (MAX_THREAD_MESSAGE_LENGTH + 1),
                user=self.owner,
            )

    def test_create_thread_message_success_sets_creator(self):
        from opencontractserver.conversations.models import (
            ChatMessage,
            MessageTypeChoices,
        )
        from opencontractserver.mcp.tools import create_thread_message

        result = create_thread_message(
            corpus_slug=self.private_corpus.slug,
            thread_id=self.private_thread.id,
            content="Hello from owner",
            user=self.owner,
        )
        message = ChatMessage.objects.get(id=int(result["id"]))
        self.assertEqual(message.creator, self.owner)
        self.assertEqual(message.conversation_id, self.private_thread.id)
        self.assertEqual(message.content, "Hello from owner")
        self.assertEqual(message.msg_type, MessageTypeChoices.HUMAN)

    def test_create_thread_message_rejects_locked_thread(self):
        from django.core.exceptions import PermissionDenied

        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )
        from opencontractserver.mcp.tools import create_thread_message

        # Use a per-test thread rather than mutating the ``setUpTestData``
        # cached object: ``TestCase`` rolls back the DB row but the cached
        # Python instance retains ``is_locked = True`` for the rest of the
        # run, which would silently corrupt any later test that reads the
        # attribute without a fresh DB query.
        locked_thread = Conversation.objects.create(
            title="Locked Thread",
            creator=self.owner,
            is_public=False,
            is_locked=True,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.private_corpus,
        )

        with self.assertRaises(PermissionDenied):
            create_thread_message(
                corpus_slug=self.private_corpus.slug,
                thread_id=locked_thread.id,
                content="locked thread write",
                user=self.owner,
            )

    def test_create_thread_message_denies_unrelated_user(self):
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.mcp.tools import create_thread_message

        # DoesNotExist is intentional here (not PermissionDenied): the tool
        # routes everything through ``Corpus.objects.visible_to_user(...)``,
        # which returns an empty queryset for invisible resources. Surfacing
        # the same exception for "doesn't exist" and "you can't see it"
        # prevents IDOR enumeration via different error classes.
        with self.assertRaises(Corpus.DoesNotExist):
            create_thread_message(
                corpus_slug=self.private_corpus.slug,
                thread_id=self.private_thread.id,
                content="trying to post",
                user=self.other_user,
            )

    def test_create_thread_message_rejects_parent_from_other_thread(self):
        """IDOR regression: supplying a parent message id that belongs to a
        thread the caller cannot see must surface ChatMessage.DoesNotExist,
        not silently graft the reply under the unrelated parent.
        """
        from opencontractserver.conversations.models import (
            ChatMessage,
            Conversation,
            ConversationTypeChoices,
        )
        from opencontractserver.mcp.tools import create_thread_message

        foreign_corpus = Corpus.objects.create(
            title="Foreign Corpus",
            creator=self.other_user,
            is_public=False,
        )
        foreign_thread = Conversation.objects.create(
            title="Foreign Thread",
            creator=self.other_user,
            is_public=False,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=foreign_corpus,
        )
        foreign_parent = ChatMessage.objects.create(
            conversation=foreign_thread,
            content="parent in another thread",
            creator=self.other_user,
        )

        with self.assertRaises(ChatMessage.DoesNotExist):
            create_thread_message(
                corpus_slug=self.private_corpus.slug,
                thread_id=self.private_thread.id,
                content="reply pretending to nest under a foreign parent",
                parent_message_id=foreign_parent.id,
                user=self.owner,
            )

    def test_create_thread_message_with_valid_parent_succeeds(self):
        """Happy path for an in-thread reply via ``parent_message_id``.

        The IDOR rejection case is covered above; this pins the success path
        end-to-end: a caller who can see the thread can supply a parent that
        also lives in the same thread and the resulting ChatMessage carries
        the parent FK. This call also exercises ``ChatMessage.objects.create``
        from inside a synchronous context — the same path the dispatcher hits
        via ``sync_to_async`` — so the two ``post_save`` notification signal
        handlers registered on ChatMessage are confirmed to run cleanly here.
        """
        from opencontractserver.conversations.models import ChatMessage
        from opencontractserver.mcp.tools import create_thread_message

        parent = ChatMessage.objects.create(
            conversation=self.private_thread,
            content="parent in same thread",
            creator=self.owner,
        )

        result = create_thread_message(
            corpus_slug=self.private_corpus.slug,
            thread_id=self.private_thread.id,
            content="reply that nests under valid parent",
            parent_message_id=parent.id,
            user=self.owner,
        )

        self.assertNotIn("error", result)
        self.assertEqual(result["parent_message_id"], str(parent.id))

        msg = ChatMessage.objects.get(id=int(result["id"]))
        self.assertEqual(msg.parent_message_id, parent.id)
        self.assertEqual(msg.conversation_id, self.private_thread.id)
        self.assertEqual(msg.creator_id, self.owner.id)
        self.assertEqual(msg.content, "reply that nests under valid parent")

    def test_create_thread_message_strips_content_before_save(self):
        """Validation and persistence must agree on the same normalised value
        so the row never carries surprising leading/trailing whitespace that
        passed only because of the strip-only emptiness check.
        """
        from opencontractserver.conversations.models import ChatMessage
        from opencontractserver.mcp.tools import create_thread_message

        result = create_thread_message(
            corpus_slug=self.private_corpus.slug,
            thread_id=self.private_thread.id,
            content="   leading and trailing   ",
            user=self.owner,
        )
        msg = ChatMessage.objects.get(id=int(result["id"]))
        self.assertEqual(msg.content, "leading and trailing")
        self.assertEqual(result["content"], "leading and trailing")

    def test_get_corpus_info_accepts_user(self):
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.mcp.tools import get_corpus_info

        info = get_corpus_info(self.private_corpus.slug, user=self.owner)
        self.assertEqual(info["slug"], self.private_corpus.slug)

        with self.assertRaises(Corpus.DoesNotExist):
            get_corpus_info(self.private_corpus.slug)

    def test_create_thread_message_unrelated_user_can_post_to_public_thread(self):
        """Public threads on public corpuses are intentionally writable by any
        authenticated MCP caller.

        This pins the documented policy from ``create_thread_message``'s
        docstring: write access piggybacks on read visibility. For a thread
        on a *public* corpus, every authenticated user can ``visible_to_user``
        the thread, so every authenticated user can post into it. Operators
        who need stricter gating (read-only spectators) must keep the corpus
        / thread private. If this test ever fails, the change requires an
        explicit policy review — not a one-line fix.
        """
        from opencontractserver.conversations.models import (
            ChatMessage,
            Conversation,
            ConversationTypeChoices,
        )
        from opencontractserver.mcp.tools import create_thread_message

        public_corpus = Corpus.objects.create(
            title="MCP Auth Public Corpus",
            creator=self.owner,
            is_public=True,
        )
        public_thread = Conversation.objects.create(
            title="Public Thread",
            creator=self.owner,
            is_public=True,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=public_corpus,
        )

        result = create_thread_message(
            corpus_slug=public_corpus.slug,
            thread_id=public_thread.id,
            content="Posting as an unrelated authenticated user",
            user=self.other_user,
        )
        message = ChatMessage.objects.get(id=int(result["id"]))
        self.assertEqual(message.creator, self.other_user)
        self.assertEqual(message.conversation_id, public_thread.id)


class MCPCallToolHandlerAuthTest(_MCPAsyncRunMixin, TransactionTestCase):
    """Tests covering the auth-aware dispatch in ``call_tool_handler``.

    Uses TransactionTestCase because ``sync_to_async`` runs the handler in a
    thread pool that does not see TestCase's open transaction.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="mcphandlerowner",
            email="mcphandler@test.com",
            password="testpass123",
        )
        self.private_corpus = Corpus.objects.create(
            title="Handler Private Corpus",
            creator=self.owner,
            is_public=False,
        )

    def tearDown(self):
        from django import db

        self._close_async_db_connections()
        db.connections.close_all()

    def test_handler_passes_user_to_tool(self):
        import json

        from opencontractserver.mcp.server import _mcp_user, call_tool_handler

        owner = self.owner
        expected_slug = self.private_corpus.slug

        async def run_test():
            token = _mcp_user.set(owner)
            try:
                return await call_tool_handler("list_public_corpuses", {})
            finally:
                _mcp_user.reset(token)

        result = self._run(run_test())
        payload = json.loads(result[0].text)
        slugs = [c["slug"] for c in payload["corpuses"]]
        self.assertIn(expected_slug, slugs)

    def test_handler_anonymous_when_no_user_set(self):
        import json

        from opencontractserver.mcp.server import call_tool_handler

        result = self._run(call_tool_handler("list_public_corpuses", {}))
        payload = json.loads(result[0].text)
        slugs = [c["slug"] for c in payload["corpuses"]]
        self.assertNotIn(self.private_corpus.slug, slugs)

    def test_handler_returns_permission_denied_as_error_payload(self):
        import json

        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )
        from opencontractserver.mcp.server import call_tool_handler

        thread = Conversation.objects.create(
            title="Permission Denied Thread",
            creator=self.owner,
            is_public=False,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.private_corpus,
        )

        result = self._run(
            call_tool_handler(
                "create_thread_message",
                {
                    "corpus_slug": self.private_corpus.slug,
                    "thread_id": thread.id,
                    "content": "should be denied",
                },
            )
        )
        payload = json.loads(result[0].text)
        self.assertIn("error", payload)

    def test_handler_strips_client_supplied_user_argument(self):
        """A client-supplied ``user`` argument must not collide with the
        ContextVar-resolved one. Without filtering, the dispatcher raised
        ``TypeError: got multiple values for keyword argument 'user'`` and
        the failure escaped the structured ``except (PermissionDenied,
        ValidationError)`` branch as a raw transport error."""
        import json

        from opencontractserver.mcp.server import _mcp_user, call_tool_handler

        owner = self.owner

        async def run_test():
            token = _mcp_user.set(owner)
            try:
                # ``user`` here is a hostile/malformed argument from the
                # MCP client. The dispatcher must drop it before forwarding
                # to the tool handler.
                return await call_tool_handler(
                    "list_public_corpuses", {"user": "attacker", "limit": 5}
                )
            finally:
                _mcp_user.reset(token)

        result = self._run(run_test())
        payload = json.loads(result[0].text)
        # The tool ran cleanly (no TypeError escape) and resolved the
        # authenticated user from the ContextVar, not the client argument.
        self.assertIn("corpuses", payload)


class MCPAsgiAppAuthTest(_MCPAsyncRunMixin, TestCase):
    """End-to-end checks for the JWT branch of ``create_mcp_asgi_app``.

    A bad token must surface as a 401 response from the ASGI callable before
    the request ever reaches the MCP session manager.
    """

    def _run_app(self, scope):
        from opencontractserver.mcp.server import create_mcp_asgi_app

        app = create_mcp_asgi_app()

        received = []

        async def mock_receive():
            return {"type": "http.disconnect"}

        async def mock_send(message):
            received.append(message)

        self._run(app(scope, mock_receive, mock_send))
        return received

    def test_invalid_bearer_token_returns_401_response(self):
        import json

        scope = {
            "type": "http",
            "path": "/mcp",
            "method": "POST",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer not-a-real-token"),
                (b"content-type", b"application/json"),
                (b"host", b"opencontracts.test"),
            ],
        }
        messages = self._run_app(scope)
        starts = [m for m in messages if m.get("type") == "http.response.start"]
        bodies = [m for m in messages if m.get("type") == "http.response.body"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]["status"], 401)
        self.assertTrue(bodies)
        payload = json.loads(bodies[0]["body"])
        self.assertIn("Invalid", payload.get("error", ""))

    def test_invalid_bearer_token_401_includes_www_authenticate_header(self):
        """Per RFC 6750 §3 + the MCP 2025-06-18 Authorization spec, a 401
        from a Bearer-protected resource must carry ``WWW-Authenticate``
        so interactive clients can discover the authorization server.

        Non-Auth0 mode (this test's default): the header degrades to the
        plain ``Bearer realm="opencontracts"`` value — no resource_metadata
        URL because there is no spec-compliant authorization server to
        advertise.
        """
        scope = {
            "type": "http",
            "path": "/mcp",
            "method": "POST",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer not-a-real-token"),
                (b"content-type", b"application/json"),
                (b"host", b"opencontracts.test"),
            ],
        }
        messages = self._run_app(scope)
        starts = [m for m in messages if m.get("type") == "http.response.start"]
        self.assertEqual(len(starts), 1)
        headers = dict(starts[0]["headers"])
        self.assertIn(b"www-authenticate", headers)
        www_auth = headers[b"www-authenticate"].decode("ascii")
        self.assertTrue(www_auth.startswith("Bearer realm="))
        # Without Auth0 there's nothing to point at, so no resource_metadata.
        self.assertNotIn("resource_metadata", www_auth)

    def test_invalid_bearer_token_401_advertises_resource_metadata_under_auth0(
        self,
    ):
        """In Auth0 mode the 401 must point Claude Desktop / Cursor at the
        OAuth protected-resource metadata document so they can drive the
        full Authorization-Code + PKCE flow without a preconfigured token."""
        from django.test import override_settings

        scope = {
            "type": "http",
            "path": "/mcp",
            "method": "POST",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer not-a-real-token"),
                (b"content-type", b"application/json"),
                (b"host", b"opencontracts.test"),
                (b"x-forwarded-proto", b"https"),
            ],
        }
        with override_settings(USE_AUTH0=True, AUTH0_DOMAIN="example.auth0.com"):
            messages = self._run_app(scope)
        starts = [m for m in messages if m.get("type") == "http.response.start"]
        self.assertEqual(len(starts), 1)
        headers = dict(starts[0]["headers"])
        www_auth = headers[b"www-authenticate"].decode("ascii")
        self.assertIn('Bearer realm="opencontracts"', www_auth)
        self.assertIn(
            'resource_metadata="https://opencontracts.test/.well-known/oauth-protected-resource"',
            www_auth,
        )

    def test_www_authenticate_rejects_malformed_forwarded_proto(self):
        """Only http/https may appear as the advertised metadata scheme."""
        from django.test import override_settings

        from opencontractserver.mcp.server import _build_www_authenticate_header

        scope = {
            "type": "http",
            "headers": [
                (b"host", b"opencontracts.test"),
                (b"x-forwarded-proto", b'https"\r\nx-injected: y'),
            ],
            "scheme": "http",
        }
        with override_settings(USE_AUTH0=True):
            header = _build_www_authenticate_header(scope).decode("ascii")

        self.assertIn(
            'resource_metadata="http://opencontracts.test/.well-known/oauth-protected-resource"',
            header,
        )
        self.assertNotIn("\r", header)
        self.assertNotIn("\n", header)
        self.assertNotIn("x-injected", header)

    def test_invalid_bearer_token_still_uses_global_rate_limit(self):
        """Rate limiting runs before JWT validation."""
        from unittest.mock import AsyncMock, patch

        scope = {
            "type": "http",
            "path": "/mcp",
            "method": "POST",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer not-a-real-token"),
                (b"content-type", b"application/json"),
                (b"host", b"opencontracts.test"),
            ],
        }

        with patch(
            "opencontractserver.mcp.server.check_mcp_rate_limit",
            new=AsyncMock(return_value=(True, "rate limited", 9)),
        ), patch("opencontractserver.mcp.server.get_user_from_jwt_token") as verifier:
            messages = self._run_app(scope)

        verifier.assert_not_called()
        starts = [m for m in messages if m.get("type") == "http.response.start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]["status"], 429)

    def test_valid_bearer_token_authenticates_and_does_not_401(self):
        """A valid JWT must NOT trigger the 401 branch; the ASGI layer
        must continue past the auth check with ``_mcp_user`` populated.

        We can't easily peek inside the ``_handle_mcp_request`` closure,
        so we assert the JWT verifier is invoked exactly once and the
        response is not a 401. Combined with the
        ``MCPCallToolHandlerAuthTest`` cases that prove tool dispatch
        consumes ``_mcp_user`` correctly, that fully covers the happy
        path end-to-end.
        """
        from unittest.mock import patch

        from opencontractserver.mcp.server import create_mcp_asgi_app

        user = User.objects.create_user(
            username="mcp_jwt_owner",
            email="mcpjwt@test.com",
            password="testpass123",
        )

        received: list = []

        async def mock_receive():
            return {"type": "http.request", "body": b"{}"}

        async def mock_send(message):
            received.append(message)

        scope = {
            "type": "http",
            "path": "/mcp",
            "method": "POST",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer valid-token"),
                (b"content-type", b"application/json"),
            ],
            "client": ("127.0.0.1", 12345),
        }

        call_count = {"n": 0}

        def fake_verifier(token):
            call_count["n"] += 1
            assert token == "valid-token"
            return user

        async def run_test():
            # ``server`` imports the JWT verifier at module load, so the
            # canonical patch target is the symbol on the server module.
            # Patching ``config.jwt_utils.get_user_from_jwt_token`` directly
            # used to *appear* to work when the import was inline (call-time
            # lookup), but is no longer the bound name on the runtime path.
            with patch(
                "opencontractserver.mcp.server.get_user_from_jwt_token",
                side_effect=fake_verifier,
            ):
                app = create_mcp_asgi_app()
                await app(scope, mock_receive, mock_send)

        self._run(run_test())

        self.assertEqual(call_count["n"], 1)
        starts = [m for m in received if m.get("type") == "http.response.start"]
        # The body is empty JSON so downstream parsing will produce some
        # error, but the auth layer must not 401. Anything else is fine.
        self.assertTrue(starts, "Expected a response from the ASGI app")
        self.assertNotEqual(starts[0]["status"], 401)


class MCPResourceAuthTest(_MCPAsyncRunMixin, TransactionTestCase):
    """Resource reads consume the same request user as tool calls."""

    def setUp(self):
        from django.core.files.base import ContentFile

        from opencontractserver.documents.models import Document, DocumentPath
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        self.owner = User.objects.create_user(
            username="mcp_resource_owner",
            email="mcpresource@test.com",
            password="testpass123",
        )
        self.collaborator = User.objects.create_user(
            username="mcp_resource_collaborator",
            email="mcpresourcecollab@test.com",
            password="testpass123",
        )
        self.private_corpus = Corpus.objects.create(
            title="Private Resource Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.private_document = Document.objects.create(
            title="Private Resource Document",
            creator=self.owner,
            is_public=False,
        )
        self.private_document.txt_extract_file.save(
            "private_resource.txt",
            ContentFile(b"private document text"),
        )
        DocumentPath.objects.create(
            document=self.private_document,
            corpus=self.private_corpus,
            path="/private-resource.txt",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.owner,
        )
        set_permissions_for_obj_to_user(
            self.collaborator,
            self.private_corpus,
            [PermissionTypes.READ],
        )

    def tearDown(self):
        from django import db

        self._close_async_db_connections()
        db.connections.close_all()

    def test_read_resource_handler_uses_authenticated_user(self):
        from opencontractserver.mcp.server import _mcp_user, read_resource_handler

        async def run_test():
            token = _mcp_user.set(self.owner)
            try:
                return await read_resource_handler(
                    f"corpus://{self.private_corpus.slug}"
                )
            finally:
                _mcp_user.reset(token)

        payload = json.loads(self._run(run_test()))
        self.assertEqual(payload["slug"], self.private_corpus.slug)

    def test_document_resource_uses_authenticated_corpus_access(self):
        from opencontractserver.mcp.server import _mcp_user, read_resource_handler

        async def run_test():
            token = _mcp_user.set(self.collaborator)
            try:
                return await read_resource_handler(
                    f"document://{self.private_corpus.slug}/{self.private_document.slug}"
                )
            finally:
                _mcp_user.reset(token)

        payload = json.loads(self._run(run_test()))
        self.assertEqual(payload["slug"], self.private_document.slug)
        self.assertEqual(payload["full_text"], "private document text")

    def test_read_resource_handler_preserves_anonymous_default(self):
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.mcp.server import read_resource_handler

        with self.assertRaises(Corpus.DoesNotExist):
            self._run(read_resource_handler(f"corpus://{self.private_corpus.slug}"))


class MCPCallToolHandlerValidationErrorTest(_MCPAsyncRunMixin, TransactionTestCase):
    """``ValidationError`` raised by a tool must surface as a structured
    error result, not bubble up as an MCP transport exception.

    Covers both the non-scoped (``call_tool_handler``) and the scoped
    (``create_scoped_mcp_server`` closure) dispatch paths so both
    branches of the except clause stay correct.
    """

    def setUp(self):
        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )

        self.owner = User.objects.create_user(
            username="mcp_validation_owner",
            email="mcpval@test.com",
            password="testpass123",
        )
        self.corpus = Corpus.objects.create(
            title="Validation Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.thread = Conversation.objects.create(
            title="Validation Thread",
            creator=self.owner,
            is_public=False,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
        )

    def tearDown(self):
        from django import db

        self._close_async_db_connections()
        db.connections.close_all()

    def test_non_scoped_validation_error_returns_error_payload(self):
        """Blank content triggers ``ValidationError`` inside the tool. The
        dispatcher must trap it and return a JSON error result.
        """
        from opencontractserver.mcp.server import _mcp_user, call_tool_handler

        async def run_test():
            token = _mcp_user.set(self.owner)
            try:
                return await call_tool_handler(
                    "create_thread_message",
                    {
                        "corpus_slug": self.corpus.slug,
                        "thread_id": self.thread.id,
                        "content": "   ",  # whitespace-only -> ValidationError
                    },
                )
            finally:
                _mcp_user.reset(token)

        result = self._run(run_test())
        payload = json.loads(result[0].text)
        self.assertIn("error", payload)
        self.assertIn("empty", payload["error"].lower())

    def test_scoped_validation_error_returns_error_payload(self):
        """Same contract via the scoped corpus closure."""
        from mcp.types import CallToolRequest, CallToolRequestParams

        from opencontractserver.mcp.server import (
            _mcp_user,
            create_scoped_mcp_server,
        )

        server = create_scoped_mcp_server(self.corpus.slug)
        call_tool = server.request_handlers[CallToolRequest]

        async def run_test():
            token = _mcp_user.set(self.owner)
            try:
                request = CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="create_thread_message",
                        arguments={
                            "thread_id": self.thread.id,
                            "content": "   ",  # whitespace-only -> ValidationError
                        },
                    ),
                )
                return await call_tool(request)
            finally:
                _mcp_user.reset(token)

        response = self._run(run_test())
        # The MCP server wraps tool results in ServerResult; the text
        # content is on response.root.content[0].text.
        text = response.root.content[0].text
        payload = json.loads(text)
        self.assertIn("error", payload)
        self.assertIn("empty", payload["error"].lower())

    def test_scoped_authenticated_create_thread_message_succeeds(self):
        """Closes the test-coverage gap flagged in review: the scoped
        ``create_thread_message`` write tool must work end-to-end when an
        authenticated user is set in ``_mcp_user``.
        """
        from mcp.types import CallToolRequest, CallToolRequestParams

        from opencontractserver.conversations.models import ChatMessage
        from opencontractserver.mcp.server import (
            _mcp_user,
            create_scoped_mcp_server,
        )

        server = create_scoped_mcp_server(self.corpus.slug)
        call_tool = server.request_handlers[CallToolRequest]

        async def run_test():
            token = _mcp_user.set(self.owner)
            try:
                request = CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="create_thread_message",
                        arguments={
                            "thread_id": self.thread.id,
                            "content": "scoped write happy path",
                        },
                    ),
                )
                return await call_tool(request)
            finally:
                _mcp_user.reset(token)

        response = self._run(run_test())
        text = response.root.content[0].text
        payload = json.loads(text)
        self.assertNotIn("error", payload)
        self.assertEqual(payload["content"], "scoped write happy path")
        # And the message really was persisted with the right creator.
        msg = ChatMessage.objects.get(id=payload["id"])
        self.assertEqual(msg.creator, self.owner)


class MCPNonScopedListToolsTest(_MCPAsyncRunMixin, TestCase):
    """Catch drift between the non-scoped ``list_tools()`` declaration and
    the ``TOOL_HANDLERS`` dispatch dict.

    The two registries are populated independently in ``server.py``; if a
    new tool is registered in one but forgotten in the other, the MCP
    surface either advertises a missing tool or hides a working one. This
    test pins both directions for every tool name, with explicit coverage
    of ``create_thread_message`` since it was the trigger for this gap
    audit.
    """

    def test_create_thread_message_advertised_in_list_tools(self):
        from mcp.types import ListToolsRequest

        from opencontractserver.mcp.server import TOOL_HANDLERS, mcp_server

        handler = mcp_server.request_handlers[ListToolsRequest]
        result = self._run(handler(ListToolsRequest(method="tools/list")))
        tool_names = {t.name for t in result.root.tools}

        self.assertIn(
            "create_thread_message",
            tool_names,
            "create_thread_message is registered in TOOL_HANDLERS but not "
            "declared by list_tools — non-scoped MCP clients won't see it.",
        )
        # And every list_tools entry must have a dispatcher (and vice
        # versa) so neither side can drift without a test failure.
        self.assertEqual(tool_names, set(TOOL_HANDLERS.keys()))


class MCPExtractBearerTokenTest(TestCase):
    """Edge cases for ``_extract_bearer_token``.

    The function quietly returns ``None`` on a few paths that aren't
    obvious from the call site — non-http scopes, empty bearer payload,
    bytes-case-insensitive header name — and each of those is load-bearing
    for the ASGI auth branch (returning ``None`` correctly falls through
    to the anonymous path instead of crashing on a malformed header).
    """

    def test_returns_none_for_non_http_scope(self):
        from opencontractserver.mcp.server import _extract_bearer_token

        scope = {
            "type": "websocket",
            "headers": [(b"authorization", b"Bearer abc123")],
        }
        self.assertIsNone(_extract_bearer_token(scope))

    def test_returns_none_when_no_authorization_header(self):
        from opencontractserver.mcp.server import _extract_bearer_token

        scope = {
            "type": "http",
            "headers": [(b"content-type", b"application/json")],
        }
        self.assertIsNone(_extract_bearer_token(scope))

    def test_returns_none_for_bearer_with_empty_value(self):
        """``Bearer `` with nothing after the space must yield ``None``,
        not the empty string — otherwise the JWT verifier is asked to
        decode the empty token and the failure path becomes 401 instead
        of the anonymous path."""
        from opencontractserver.mcp.server import _extract_bearer_token

        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer ")],
        }
        self.assertIsNone(_extract_bearer_token(scope))

    def test_returns_none_for_non_bearer_scheme(self):
        from opencontractserver.mcp.server import _extract_bearer_token

        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Basic dXNlcjpwYXNz")],
        }
        self.assertIsNone(_extract_bearer_token(scope))

    def test_case_insensitive_authorization_header_name(self):
        from opencontractserver.mcp.server import _extract_bearer_token

        scope = {
            "type": "http",
            "headers": [(b"Authorization", b"Bearer eyJabc")],
        }
        self.assertEqual(_extract_bearer_token(scope), "eyJabc")

    def test_strips_surrounding_whitespace_from_token(self):
        from opencontractserver.mcp.server import _extract_bearer_token

        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer   eyJabc  ")],
        }
        self.assertEqual(_extract_bearer_token(scope), "eyJabc")
