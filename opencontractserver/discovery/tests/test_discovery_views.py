"""Tests for discovery endpoint views (robots.txt, llms.txt, sitemap.xml, etc.)."""

import json
from xml.etree.ElementTree import fromstring

from django.test import TestCase, override_settings

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.users.models import User


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class RobotsTxtTest(TestCase):
    """Tests for the dynamic robots.txt endpoint."""

    def test_returns_text_plain(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])

    def test_allows_all_crawlers(self):
        response = self.client.get("/robots.txt")
        content = response.content.decode()
        self.assertIn("User-agent: *", content)
        self.assertIn("Disallow:", content)
        # Ensure Disallow is empty (allows everything)
        for line in content.splitlines():
            if line.strip().startswith("Disallow:"):
                self.assertEqual(line.strip(), "Disallow:")

    def test_includes_ai_crawler_user_agents(self):
        response = self.client.get("/robots.txt")
        content = response.content.decode()
        for bot in [
            "GPTBot",
            "ClaudeBot",
            "anthropic-ai",
            "Google-Extended",
            "PerplexityBot",
        ]:
            self.assertIn(f"User-agent: {bot}", content)
            self.assertIn("Allow: /", content)

    def test_includes_sitemap_reference(self):
        response = self.client.get("/robots.txt")
        content = response.content.decode()
        self.assertIn("Sitemap:", content)
        self.assertIn("/sitemap.xml", content)

    def test_includes_llms_txt_references(self):
        response = self.client.get("/robots.txt")
        content = response.content.decode()
        self.assertIn("/llms.txt", content)
        self.assertIn("/llms-full.txt", content)

    def test_only_get_allowed(self):
        response = self.client.post("/robots.txt")
        self.assertEqual(response.status_code, 405)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class LlmsTxtTest(TestCase):
    """Tests for the dynamic llms.txt endpoint."""

    owner: User
    public_corpus: Corpus
    private_corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="llms_test_user",
            password="testpass123",
        )
        cls.public_corpus = Corpus.objects.create(
            title="Public Legal Corpus",
            description="A corpus of legal documents for testing",
            creator=cls.owner,
            is_public=True,
        )
        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            description="Should not appear",
            creator=cls.owner,
            is_public=False,
        )

    def test_returns_text_plain(self):
        response = self.client.get("/llms.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])

    def test_follows_llmstxt_spec_format(self):
        """Verify H1 title, blockquote, and H2 sections per llmstxt.org spec."""
        response = self.client.get("/llms.txt")
        content = response.content.decode()
        # H1 title — rebranded from OpenContracts to cite in v3 release line
        self.assertIn("# cite", content)
        # Blockquote summary (citation-graph framing)
        self.assertIn("> cite is the citation layer", content)
        # H2 sections
        self.assertIn("## MCP Server", content)
        self.assertIn("## Available Collections", content)
        self.assertIn("## Links", content)

    def test_includes_mcp_connection_info(self):
        response = self.client.get("/llms.txt")
        content = response.content.decode()
        self.assertIn("/mcp/", content)
        self.assertIn("JSON-RPC 2.0", content)
        self.assertIn("list_public_corpuses", content)
        self.assertIn("get_document_text", content)

    def test_includes_public_corpuses(self):
        response = self.client.get("/llms.txt")
        content = response.content.decode()
        self.assertIn("Public Legal Corpus", content)
        self.assertIn(self.public_corpus.slug, content)

    def test_excludes_private_corpuses(self):
        response = self.client.get("/llms.txt")
        content = response.content.decode()
        self.assertNotIn("Private Corpus", content)
        self.assertNotIn("Should not appear", content)

    def test_resolves_hostname(self):
        """Ensure no THIS_HOST placeholders remain."""
        response = self.client.get("/llms.txt")
        content = response.content.decode()
        self.assertNotIn("THIS_HOST", content)
        # MCP endpoint should use actual host
        self.assertIn("http://testserver/mcp/", content)

    def test_uses_inline_markdown_links(self):
        """Verify links use inline [text](url) format, not reference style."""
        response = self.client.get("/llms.txt")
        content = response.content.decode()
        self.assertIn("[Full MCP documentation](", content)
        self.assertIn("[Source code](", content)

    def test_only_get_allowed(self):
        response = self.client.post("/llms.txt")
        self.assertEqual(response.status_code, 405)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class LlmsFullTxtTest(TestCase):
    """Tests for the dynamic llms-full.txt endpoint."""

    owner: User
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="llms_full_test_user",
            password="testpass123",
        )
        cls.corpus = Corpus.objects.create(
            title="Full Test Corpus",
            description="Corpus for full docs test",
            creator=cls.owner,
            is_public=True,
        )

    def test_returns_text_plain(self):
        response = self.client.get("/llms-full.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])

    def test_includes_full_tool_reference(self):
        response = self.client.get("/llms-full.txt")
        content = response.content.decode()
        # Check all tool sections exist
        for tool in [
            "list_public_corpuses",
            "list_documents",
            "get_document_text",
            "list_annotations",
            "search_corpus",
            "list_threads",
            "get_thread_messages",
        ]:
            self.assertIn(f"### {tool}", content)

    def test_includes_parameter_details(self):
        response = self.client.get("/llms-full.txt")
        content = response.content.decode()
        self.assertIn("Parameters:", content)
        self.assertIn("Returns:", content)
        self.assertIn("corpus_slug (string, required)", content)

    def test_includes_resource_reference(self):
        response = self.client.get("/llms-full.txt")
        content = response.content.decode()
        self.assertIn("## Resources Reference", content)
        self.assertIn("corpus://{corpus_slug}", content)
        self.assertIn("document://{corpus_slug}/{document_slug}", content)

    def test_includes_example_request(self):
        response = self.client.get("/llms-full.txt")
        content = response.content.decode()
        self.assertIn('"jsonrpc": "2.0"', content)
        self.assertIn('"method": "tools/call"', content)

    def test_includes_architecture_diagram(self):
        response = self.client.get("/llms-full.txt")
        content = response.content.decode()
        self.assertIn("## Architecture", content)
        self.assertIn("MCP Client", content)

    def test_includes_corpus_listing_with_scoped_url(self):
        response = self.client.get("/llms-full.txt")
        content = response.content.decode()
        self.assertIn("## Available Collections", content)
        self.assertIn("Full Test Corpus", content)
        self.assertIn(f"/mcp/corpus/{self.corpus.slug}/", content)

    def test_resolves_hostname(self):
        response = self.client.get("/llms-full.txt")
        content = response.content.decode()
        self.assertNotIn("THIS_HOST", content)
        self.assertIn("http://testserver/mcp/", content)

    def test_only_get_allowed(self):
        response = self.client.post("/llms-full.txt")
        self.assertEqual(response.status_code, 405)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class SitemapXmlTest(TestCase):
    """Tests for the dynamic sitemap.xml endpoint."""

    owner: User
    public_corpus: Corpus
    private_corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="sitemap_test_user",
            password="testpass123",
        )
        cls.public_corpus = Corpus.objects.create(
            title="Sitemap Corpus",
            description="Public corpus for sitemap",
            creator=cls.owner,
            is_public=True,
        )
        cls.private_corpus = Corpus.objects.create(
            title="Private Sitemap Corpus",
            creator=cls.owner,
            is_public=False,
        )

    def test_returns_xml(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])

    def test_valid_xml(self):
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        # Should parse without error
        root = fromstring(content)
        self.assertEqual(
            root.tag, "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
        )

    def test_includes_homepage(self):
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        self.assertIn("http://testserver/", content)

    def test_includes_public_corpus(self):
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        self.assertIn(f"/c/{self.public_corpus.slug}", content)

    def test_excludes_private_corpus(self):
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        self.assertNotIn(f"/c/{self.private_corpus.slug}", content)

    def test_includes_discovery_endpoints(self):
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        self.assertIn("/llms.txt", content)
        self.assertIn("/llms-full.txt", content)

    def test_only_get_allowed(self):
        response = self.client.post("/sitemap.xml")
        self.assertEqual(response.status_code, 405)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class WellKnownMcpTest(TestCase):
    """Tests for the .well-known/mcp.json endpoint."""

    owner: User
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="mcp_json_test_user",
            password="testpass123",
        )
        cls.corpus = Corpus.objects.create(
            title="MCP Discovery Corpus",
            description="For MCP JSON testing",
            creator=cls.owner,
            is_public=True,
        )

    def test_returns_json(self):
        response = self.client.get("/.well-known/mcp.json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])

    def test_valid_json_structure(self):
        response = self.client.get("/.well-known/mcp.json")
        data = json.loads(response.content)
        self.assertIn("mcpServers", data)
        self.assertIn("cite", data["mcpServers"])

    def test_global_server_entry(self):
        response = self.client.get("/.well-known/mcp.json")
        data = json.loads(response.content)
        server = data["mcpServers"]["cite"]
        self.assertIn("/mcp/", server["url"])
        self.assertEqual(server["transport"], "streamable-http")
        self.assertIsNone(server["authentication"])

    def test_includes_corpus_scoped_servers(self):
        response = self.client.get("/.well-known/mcp.json")
        data = json.loads(response.content)
        slug = self.corpus.slug
        key = f"cite-{slug}"
        self.assertIn(key, data["mcpServers"])
        self.assertIn(f"/mcp/corpus/{slug}/", data["mcpServers"][key]["url"])

    def test_resolves_hostname(self):
        response = self.client.get("/.well-known/mcp.json")
        data = json.loads(response.content)
        server = data["mcpServers"]["cite"]
        self.assertIn("http://testserver", server["url"])
        self.assertNotIn("THIS_HOST", server["url"])

    def test_only_get_allowed(self):
        response = self.client.post("/.well-known/mcp.json")
        self.assertEqual(response.status_code, 405)

    def test_authentication_advertised_when_auth0_enabled(self):
        """When USE_AUTH0 is on, mcp.json must point clients at the
        OAuth protected-resource metadata URL so interactive MCP clients
        (Claude Desktop, Cursor) can discover Auth0 as the AS."""
        with override_settings(USE_AUTH0=True, AUTH0_DOMAIN="example.auth0.com"):
            response = self.client.get("/.well-known/mcp.json")
        data = json.loads(response.content)
        global_server = data["mcpServers"]["cite"]
        self.assertIsNotNone(global_server["authentication"])
        self.assertEqual(global_server["authentication"]["type"], "oauth2")
        self.assertIn(
            "/.well-known/oauth-protected-resource",
            global_server["authentication"]["metadataUrl"],
        )
        # The same auth block must be attached to corpus-scoped server entries
        # so clients discover auth uniformly whichever endpoint they pick.
        slug = self.corpus.slug
        scoped_server = data["mcpServers"][f"cite-{slug}"]
        self.assertEqual(
            scoped_server["authentication"], global_server["authentication"]
        )

    def test_authenticated_server_advertised_under_auth0(self):
        """When Auth0 is enabled, mcp.json advertises the authenticated
        /mcp/me entrypoint pointing at its path-based protected-resource
        metadata so clients can start the sign-in flow."""
        with override_settings(USE_AUTH0=True, AUTH0_DOMAIN="example.auth0.com"):
            response = self.client.get("/.well-known/mcp.json")
        data = json.loads(response.content)
        self.assertIn("cite-authenticated", data["mcpServers"])
        authed = data["mcpServers"]["cite-authenticated"]
        self.assertIn("/mcp/me/", authed["url"])
        self.assertEqual(
            authed["authentication"]["metadataUrl"],
            "http://testserver/.well-known/oauth-protected-resource/mcp/me",
        )

    def test_authenticated_server_absent_without_auth0(self):
        """Without an interactive AS, the authed entrypoint is not advertised
        (operators hand out bearer tokens out of band)."""
        response = self.client.get("/.well-known/mcp.json")
        data = json.loads(response.content)
        self.assertNotIn("cite-authenticated", data["mcpServers"])


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class WellKnownOAuthProtectedResourceTest(TestCase):
    """Tests for the RFC 9728 /.well-known/oauth-protected-resource endpoint."""

    def test_returns_404_when_auth0_disabled(self):
        """Non-Auth0 deployments have no spec-compliant AS to advertise;
        the endpoint must 404 rather than emit a metadata document with
        an empty ``authorization_servers`` list that would loop clients."""
        with override_settings(USE_AUTH0=False):
            response = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(response.status_code, 404)

    def test_returns_404_when_auth0_domain_missing(self):
        """USE_AUTH0=True with no AUTH0_DOMAIN is a misconfiguration —
        prefer a clean 404 over emitting ``https:///`` to clients."""
        with override_settings(USE_AUTH0=True, AUTH0_DOMAIN=""):
            response = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(response.status_code, 404)

    def test_returns_metadata_when_auth0_enabled(self):
        """Per RFC 9728: clients fetch this document to discover where to
        send the user for interactive sign-in."""
        with override_settings(USE_AUTH0=True, AUTH0_DOMAIN="example.auth0.com"):
            response = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])
        data = json.loads(response.content)
        self.assertIn("http://testserver/mcp", data["resource"])
        self.assertEqual(data["authorization_servers"], ["https://example.auth0.com/"])
        self.assertEqual(data["bearer_methods_supported"], ["header"])
        self.assertIn("openid", data["scopes_supported"])
        self.assertIn("/.well-known/mcp.json", data["resource_documentation"])

    def test_only_get_allowed(self):
        with override_settings(USE_AUTH0=True, AUTH0_DOMAIN="example.auth0.com"):
            response = self.client.post("/.well-known/oauth-protected-resource")
        self.assertEqual(response.status_code, 405)

    def test_path_based_metadata_for_authed_resource(self):
        """RFC 9728 §3.1 path-based document for /mcp/me returns a matching
        ``resource`` so clients that derive the URL from the resource id
        resolve it."""
        with override_settings(USE_AUTH0=True, AUTH0_DOMAIN="example.auth0.com"):
            response = self.client.get("/.well-known/oauth-protected-resource/mcp/me")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["resource"], "http://testserver/mcp/me")
        self.assertEqual(data["authorization_servers"], ["https://example.auth0.com/"])

    def test_path_based_metadata_returns_404_without_auth0(self):
        """The path-based variant must 404 when Auth0 is disabled, exactly like
        the root document — the ``auth0_domain`` check fires before the
        ``resource_path`` lookup, so a known resource path is no excuse to leak
        metadata when there is no authorization server to point at."""
        with override_settings(USE_AUTH0=False):
            response = self.client.get("/.well-known/oauth-protected-resource/mcp/me")
        self.assertEqual(response.status_code, 404)

    def test_unknown_resource_path_returns_404(self):
        """Only known MCP resources get metadata; arbitrary paths 404 rather
        than advertise an AS for something we don't serve."""
        with override_settings(USE_AUTH0=True, AUTH0_DOMAIN="example.auth0.com"):
            response = self.client.get("/.well-known/oauth-protected-resource/bogus")
        self.assertEqual(response.status_code, 404)

    def test_authed_path_is_advertised_as_protected_resource(self):
        """Pin the discovery↔MCP coupling: the authenticated MCP path is a
        hardcoded literal in ``_OAUTH_PROTECTED_RESOURCES`` (to avoid importing
        the heavy MCP server module). If ``MCP_AUTHED_PATH`` is ever renamed
        without updating that tuple, discovery would silently 404 the new
        path's metadata — fail loudly here instead."""
        from opencontractserver.discovery.views import _OAUTH_PROTECTED_RESOURCES
        from opencontractserver.mcp.server import MCP_AUTHED_PATH

        self.assertIn(MCP_AUTHED_PATH, _OAUTH_PROTECTED_RESOURCES)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class DiscoveryNoCorpusesTest(TestCase):
    """Tests for discovery endpoints when no public corpuses exist."""

    def test_llms_txt_without_corpuses(self):
        response = self.client.get("/llms.txt")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Should still have the core sections
        self.assertIn("# cite", content)
        self.assertIn("## MCP Server", content)
        # But no Available Collections section
        self.assertNotIn("## Available Collections", content)

    def test_llms_full_txt_without_corpuses(self):
        response = self.client.get("/llms-full.txt")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("## Available Collections", content)

    def test_sitemap_without_corpuses(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Should still have homepage
        self.assertIn("http://testserver/", content)

    def test_mcp_json_without_corpuses(self):
        response = self.client.get("/.well-known/mcp.json")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Should still have global server
        self.assertIn("cite", data["mcpServers"])
        # But no corpus-scoped servers beyond the global one
        self.assertEqual(len(data["mcpServers"]), 1)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class SearchApiTest(TestCase):
    """Tests for the public search API endpoint."""

    owner: User
    public_corpus: Corpus
    private_corpus: Corpus
    public_doc: Document
    private_doc: Document

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="search_test_user",
            password="testpass123",
        )
        cls.public_corpus = Corpus.objects.create(
            title="Indemnification Clauses",
            description="A collection of indemnification provisions",
            creator=cls.owner,
            is_public=True,
        )
        cls.private_corpus = Corpus.objects.create(
            title="Secret Clauses",
            description="Private collection",
            creator=cls.owner,
            is_public=False,
        )
        cls.public_doc = Document.objects.create(
            title="Sample Indemnity Agreement",
            description="Contains standard indemnification language",
            creator=cls.owner,
            is_public=True,
        )
        cls.private_doc = Document.objects.create(
            title="Secret Indemnity Agreement",
            description="Private indemnification document",
            creator=cls.owner,
        )
        # Link documents to corpuses via DocumentPath
        DocumentPath.objects.create(
            document=cls.public_doc,
            corpus=cls.public_corpus,
            creator=cls.owner,
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=cls.private_doc,
            corpus=cls.private_corpus,
            creator=cls.owner,
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_returns_json(self):
        response = self.client.get("/api/search/?q=indemnification")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])

    def test_requires_query_param(self):
        response = self.client.get("/api/search/")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("error", data)

    def test_empty_query_rejected(self):
        response = self.client.get("/api/search/?q=")
        self.assertEqual(response.status_code, 400)

    def test_only_get_allowed(self):
        response = self.client.post("/api/search/?q=test")
        self.assertEqual(response.status_code, 405)

    def test_global_search_finds_public_corpus(self):
        response = self.client.get("/api/search/?q=indemnification")
        data = json.loads(response.content)
        self.assertEqual(data["query"], "indemnification")
        slugs = [r["slug"] for r in data["results"]]
        self.assertIn(self.public_corpus.slug, slugs)

    def test_global_search_excludes_private_corpus(self):
        response = self.client.get("/api/search/?q=Secret")
        data = json.loads(response.content)
        slugs = [r["slug"] for r in data["results"]]
        self.assertNotIn(self.private_corpus.slug, slugs)

    def test_global_search_finds_public_documents(self):
        response = self.client.get("/api/search/?q=Indemnity+Agreement")
        data = json.loads(response.content)
        slugs = [r["slug"] for r in data["results"]]
        self.assertIn(self.public_doc.slug, slugs)

    def test_global_search_excludes_private_documents(self):
        response = self.client.get("/api/search/?q=Secret+Indemnity")
        data = json.loads(response.content)
        slugs = [r["slug"] for r in data["results"]]
        self.assertNotIn(self.private_doc.slug, slugs)

    def test_corpus_scoped_search(self):
        response = self.client.get(
            f"/api/search/?q=indemnity&corpus={self.public_corpus.slug}"
        )
        data = json.loads(response.content)
        self.assertEqual(data["corpus"], self.public_corpus.slug)
        # Should find the document within the corpus
        slugs = [r["slug"] for r in data["results"]]
        self.assertIn(self.public_doc.slug, slugs)

    def test_corpus_scoped_search_nonexistent_corpus(self):
        response = self.client.get("/api/search/?q=test&corpus=nonexistent-slug")
        self.assertEqual(response.status_code, 404)

    def test_corpus_scoped_search_private_corpus_returns_404(self):
        response = self.client.get(
            f"/api/search/?q=test&corpus={self.private_corpus.slug}"
        )
        self.assertEqual(response.status_code, 404)

    def test_limit_parameter(self):
        response = self.client.get("/api/search/?q=indemnification&limit=1")
        data = json.loads(response.content)
        self.assertLessEqual(len(data["results"]), 1)

    def test_limit_capped_at_max(self):
        """Verify limit is capped even if client requests more."""
        from opencontractserver.constants.discovery import MAX_SEARCH_RESULTS

        response = self.client.get("/api/search/?q=indemnification&limit=999")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertLessEqual(len(data["results"]), MAX_SEARCH_RESULTS)
        # Ensure the cap is actually applied (not just zero results)
        self.assertIsInstance(data["results"], list)

    def test_invalid_limit_defaults(self):
        response = self.client.get("/api/search/?q=indemnification&limit=abc")
        self.assertEqual(response.status_code, 200)

    def test_result_structure(self):
        response = self.client.get("/api/search/?q=indemnification")
        data = json.loads(response.content)
        self.assertIn("query", data)
        self.assertIn("results", data)
        for result in data["results"]:
            self.assertIn("type", result)
            self.assertIn("slug", result)
            self.assertIn("title", result)
            self.assertIn("description", result)
            self.assertIn("similarity_score", result)

    def test_no_results_returns_empty_list(self):
        response = self.client.get("/api/search/?q=zzzznonexistentquery")
        data = json.loads(response.content)
        self.assertEqual(data["results"], [])
