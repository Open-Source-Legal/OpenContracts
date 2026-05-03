"""
Dynamic discovery endpoints for crawlers and AI agents.

Serves robots.txt, llms.txt, llms-full.txt, sitemap.xml,
.well-known/mcp.json, and a RESTful search API with live data
from the database.
"""

import json
import logging
from xml.etree.ElementTree import Element, SubElement, tostring

from django.contrib.auth.models import AnonymousUser
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from config.telemetry import record_event
from opencontractserver.constants.discovery import (
    DISCOVERY_CACHE_SECONDS,
    MAX_PUBLIC_CORPUSES,
    MAX_SEARCH_RESULTS,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath

try:
    from opencontractserver.mcp.config import RATE_LIMIT_REQUESTS
except ImportError:
    RATE_LIMIT_REQUESTS = 100

logger = logging.getLogger(__name__)

# Standardized human-readable rate limit string for all discovery endpoints
RATE_LIMIT_DISPLAY = f"{RATE_LIMIT_REQUESTS} requests/minute per IP"


def _record_discovery_event(endpoint: str, request: HttpRequest) -> None:
    """Fire a PostHog event for a discovery endpoint hit."""
    try:
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        record_event(
            "discovery_endpoint_served",
            {
                "endpoint": endpoint,
                "user_agent": user_agent,
            },
        )
    except Exception:
        pass


def _get_base_url(request: HttpRequest) -> str:
    """Derive the canonical base URL from the request."""
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    return f"{scheme}://{host}"


def _sanitize_markdown_title(title: str) -> str:
    """Strip leading '#' characters from a title to prevent Markdown injection."""
    return title.lstrip("#").strip()


def _get_public_corpus_queryset():
    """Return a queryset of public corpuses visible to anonymous users.

    The queryset is annotated with ``active_document_count`` and capped at
    ``MAX_PUBLIC_CORPUSES`` to prevent unbounded memory usage.
    """
    anonymous = AnonymousUser()
    return (
        Corpus.objects.visible_to_user(anonymous)
        .annotate(
            active_document_count=Count(
                "document_paths",
                filter=Q(
                    document_paths__is_current=True,
                    document_paths__is_deleted=False,
                ),
                distinct=True,
            )
        )
        .order_by("-created")[:MAX_PUBLIC_CORPUSES]
    )


def _get_public_corpuses() -> list[dict]:
    """Return summary dicts for public corpuses visible to anonymous users."""
    return [
        {
            "slug": corpus.slug,
            "title": corpus.title,
            "description": corpus.description or "",
            "document_count": corpus.active_document_count,
        }
        for corpus in _get_public_corpus_queryset()
    ]


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------
@require_GET
@cache_page(DISCOVERY_CACHE_SECONDS)
def robots_txt(request: HttpRequest) -> HttpResponse:
    base_url = _get_base_url(request)
    lines = [
        "# https://www.robotstxt.org/robotstxt.html",
        "",
        "# Default: allow all crawlers",
        "User-agent: *",
        "Disallow:",
        "",
        "# AI crawlers — explicitly welcomed",
        "User-agent: GPTBot",
        "Allow: /",
        "",
        "User-agent: ChatGPT-User",
        "Allow: /",
        "",
        "User-agent: ClaudeBot",
        "Allow: /",
        "",
        "User-agent: anthropic-ai",
        "Allow: /",
        "",
        "User-agent: Google-Extended",
        "Allow: /",
        "",
        "User-agent: PerplexityBot",
        "Allow: /",
        "",
        "User-agent: Bytespider",
        "Allow: /",
        "",
        "User-agent: cohere-ai",
        "Allow: /",
        "",
        "# AI agent documentation (see https://llmstxt.org)",
        f"# LLM instructions: {base_url}/llms.txt",
        f"# Full API reference: {base_url}/llms-full.txt",
        "",
        "# Sitemaps",
        f"Sitemap: {base_url}/sitemap.xml",
        "",
    ]
    _record_discovery_event("robots_txt", request)
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# llms.txt
# ---------------------------------------------------------------------------
@require_GET
@cache_page(DISCOVERY_CACHE_SECONDS)
def llms_txt(request: HttpRequest) -> HttpResponse:
    base_url = _get_base_url(request)
    corpuses = _get_public_corpuses()

    lines = [
        "# OpenContracts",
        "",
        (
            "> OpenContracts is an open-source document analytics platform for "
            "analyzing, annotating, and querying complex documents. It provides a "
            "Model Context Protocol (MCP) server for AI agent access."
        ),
        "",
        "## MCP Server",
        "",
        (
            "This instance exposes a read-only MCP server that AI agents can "
            "connect to for accessing public corpuses, documents, annotations, "
            "and discussion threads."
        ),
        "",
        f"- Endpoint (global): {base_url}/mcp/",
        f"- Endpoint (corpus-scoped): {base_url}/mcp/corpus/{{corpus_slug}}/",
        "- Protocol: JSON-RPC 2.0 (MCP spec 2025-03-26)",
        "- Auth: None required (public data only)",
        f"- Rate limit: {RATE_LIMIT_DISPLAY}",
        "",
        "### Connecting",
        "",
        "Use any MCP-compatible client. For Claude Desktop, add to config:",
        "",
        "```json",
        "{",
        '  "mcpServers": {',
        '    "opencontracts": {',
        '      "command": "npx",',
        f'      "args": ["mcp-remote", "{base_url}/mcp/"]',
        "    }",
        "  }",
        "}",
        "```",
        "",
        "### Available Tools",
        "",
        "- `list_public_corpuses`: List all public corpuses (paginated, searchable)",
        "- `list_documents`: List documents in a corpus",
        "- `get_document_text`: Get full extracted text from a document",
        "- `list_annotations`: List annotations on a document (filter by page or label)",
        "- `search_corpus`: Semantic vector search within a corpus",
        "- `list_threads`: List discussion threads in a corpus",
        "- `get_thread_messages`: Get messages in a thread (flat or hierarchical)",
        "",
        "### Available Resources (URI-based)",
        "",
        "- `corpus://{corpus_slug}` - Corpus metadata",
        "- `document://{corpus_slug}/{document_slug}` - Document with text",
        "- `annotation://{corpus_slug}/{document_slug}/{annotation_id}` - Annotation details",
        "- `thread://{corpus_slug}/threads/{thread_id}` - Discussion thread",
        "",
        "## REST Search API",
        "",
        (
            f"A simple JSON search endpoint at `{base_url}/api/search/?q=QUERY` "
            "is available for crawlers and lightweight integrations."
        ),
        "",
    ]

    # Dynamic corpus listing
    if corpuses:
        lines.append("## Available Collections")
        lines.append("")
        for c in corpuses:
            slug = c["slug"]
            title = _sanitize_markdown_title(c["title"])
            doc_count = c["document_count"]
            desc = (c["description"] or "").replace("\n", " ").replace("\r", "")
            # Truncate long descriptions to keep llms.txt concise
            if len(desc) > 120:
                desc = desc[:117] + "..."
            entry = f"- **{title}** (slug: `{slug}`, {doc_count} documents)"
            if desc:
                entry += f": {desc}"
            lines.append(entry)
        lines.append("")

    lines.extend(
        [
            "## Links",
            "",
            f"- [Full MCP documentation]({base_url}/llms-full.txt)",
            "- [Source code](https://github.com/Open-Source-Legal/OpenContracts)",
            "- [Project documentation](https://contracts.opensource.legal)",
            "",
        ]
    )
    _record_discovery_event("llms_txt", request)
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# llms-full.txt
# ---------------------------------------------------------------------------
@require_GET
@cache_page(DISCOVERY_CACHE_SECONDS)
def llms_full_txt(request: HttpRequest) -> HttpResponse:
    base_url = _get_base_url(request)
    corpuses = _get_public_corpuses()

    lines = [
        "# OpenContracts - Full MCP Documentation",
        "",
        (
            "> OpenContracts is an open-source document analytics platform for "
            "analyzing, annotating, and querying complex documents. It provides a "
            "Model Context Protocol (MCP) server for AI agent access to public data."
        ),
        "",
        "## MCP Server Overview",
        "",
        (
            "OpenContracts exposes a read-only MCP server so that AI assistants can "
            "access public corpuses, documents, annotations, and discussion threads "
            "without authentication."
        ),
        "",
        f"- Global endpoint: {base_url}/mcp/",
        f"- Corpus-scoped endpoint: {base_url}/mcp/corpus/{{corpus_slug}}/",
        "- Protocol: JSON-RPC 2.0 (MCP specification 2025-03-26)",
        "- Transport: Streamable HTTP (recommended), SSE (deprecated)",
        "- Authentication: None required (public data only)",
        f"- Rate limit: {RATE_LIMIT_DISPLAY}",
        "- Security: Read-only, slug-based identifiers, no internal IDs exposed",
        "",
        "## Connecting",
        "",
        "### Claude Desktop (Global Access)",
        "",
        "Add to `~/.config/Claude/claude_desktop_config.json`:",
        "",
        "```json",
        "{",
        '  "mcpServers": {',
        '    "opencontracts": {',
        '      "command": "npx",',
        f'      "args": ["mcp-remote", "{base_url}/mcp/"]',
        "    }",
        "  }",
        "}",
        "```",
        "",
        "### Claude Desktop (Corpus-Scoped)",
        "",
        "```json",
        "{",
        '  "mcpServers": {',
        '    "my-corpus": {',
        '      "command": "npx",',
        f'      "args": ["mcp-remote", "{base_url}/mcp/corpus/MY_CORPUS_SLUG/"]',
        "    }",
        "  }",
        "}",
        "```",
        "",
        "### Direct HTTP (curl)",
        "",
        "```bash",
        f"curl -X POST {base_url}/mcp/ \\",
        '  -H "Content-Type: application/json" \\',
        '  -H "Accept: application/json, text/event-stream" \\',
        """  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'""",
        "```",
        "",
        "## Tools Reference",
        "",
        "### list_public_corpuses",
        "",
        "List public corpuses visible to anonymous users.",
        "",
        "Parameters:",
        "- limit (int, default 20, max 100): Number of results",
        "- offset (int, default 0): Pagination offset",
        "- search (string, optional): Filter by title or description",
        "",
        (
            "Returns: { total_count, corpuses: [{ slug, title, description, "
            "document_count, created }] }"
        ),
        "",
        "Example request:",
        "```json",
        "{",
        '  "jsonrpc": "2.0",',
        '  "method": "tools/call",',
        '  "params": {',
        '    "name": "list_public_corpuses",',
        '    "arguments": { "limit": 10 }',
        "  },",
        '  "id": 1',
        "}",
        "```",
        "",
        "### list_documents",
        "",
        "List documents in a public corpus.",
        "",
        "Parameters:",
        "- corpus_slug (string, required): Corpus identifier",
        "- limit (int, default 50, max 100): Number of results",
        "- offset (int, default 0): Pagination offset",
        "- search (string, optional): Filter by title or description",
        "",
        (
            "Returns: { total_count, documents: [{ slug, title, description, "
            "file_type, page_count, created }] }"
        ),
        "",
        "### get_document_text",
        "",
        "Retrieve full extracted text from a document.",
        "",
        "Parameters:",
        "- corpus_slug (string, required): Corpus identifier",
        "- document_slug (string, required): Document identifier",
        "",
        "Returns: { document_slug, page_count, text }",
        "",
        "### list_annotations",
        "",
        "List annotations on a document with optional filtering.",
        "",
        "Parameters:",
        "- corpus_slug (string, required): Corpus identifier",
        "- document_slug (string, required): Document identifier",
        "- page (int, optional): Filter by page number",
        "- label_text (string, optional): Filter by label text",
        "- limit (int, default 100, max 100): Number of results",
        "- offset (int, default 0): Pagination offset",
        "",
        (
            "Returns: { total_count, annotations: [{ id, page, raw_text, "
            "annotation_label: { text, color, label_type }, structural, created }] }"
        ),
        "",
        "### search_corpus",
        "",
        (
            "Semantic vector search within a corpus. Falls back to text search "
            "if embeddings are unavailable."
        ),
        "",
        "Parameters:",
        "- corpus_slug (string, required): Corpus identifier",
        "- query (string, required): Search query text",
        "- limit (int, default 10, max 50): Number of results",
        "",
        "Returns: { query, results: [{ type, slug, title, similarity_score }] }",
        "",
        "### list_threads",
        "",
        "List discussion threads in a corpus or document.",
        "",
        "Parameters:",
        "- corpus_slug (string, required): Corpus identifier",
        "- document_slug (string, optional): Filter to a specific document",
        "- limit (int, default 20, max 100): Number of results",
        "- offset (int, default 0): Pagination offset",
        "",
        (
            "Returns: { total_count, threads: [{ id, title, message_count, "
            "is_pinned, is_locked }] }"
        ),
        "",
        "### get_thread_messages",
        "",
        "Retrieve all messages in a thread.",
        "",
        "Parameters:",
        "- corpus_slug (string, required): Corpus identifier",
        "- thread_id (int, required): Thread identifier",
        "- flatten (bool, default false): Return flat list instead of tree",
        "",
        (
            "Returns: { thread_id, title, messages: [{ id, content, author, "
            "created_at, replies? }] }"
        ),
        "",
        "## Resources Reference",
        "",
        (
            "Resources use URI patterns for direct content access via the "
            "`resources/read` method."
        ),
        "",
        "### corpus://{corpus_slug}",
        "",
        (
            "Corpus metadata including title, description, document count, "
            "label set, and timestamps."
        ),
        "",
        "### document://{corpus_slug}/{document_slug}",
        "",
        (
            "Document metadata and full extracted text. Returns JSON with fields: "
            "slug, title, description, file_type, page_count, text_preview "
            "(first 500 characters of extracted text), full_text (complete "
            "extracted text), created (ISO 8601 timestamp), corpus (corpus slug). "
            "The text_preview field is useful for quick inspection without "
            "consuming the full text, which can be large."
        ),
        "",
        "### annotation://{corpus_slug}/{document_slug}/{annotation_id}",
        "",
        (
            "Annotation details including raw text, label, page number, "
            "bounding box coordinates, and created timestamp."
        ),
        "",
        "### thread://{corpus_slug}/threads/{thread_id}",
        "",
        "Discussion thread with hierarchical message tree.",
        "",
        "Example:",
        "```json",
        "{",
        '  "jsonrpc": "2.0",',
        '  "method": "resources/read",',
        '  "params": { "uri": "document://my-corpus/contract-2024" },',
        '  "id": 1',
        "}",
        "```",
        "",
        "## REST Search API",
        "",
        (
            f"A lightweight JSON search endpoint is available at "
            f"`{base_url}/api/search/` for crawlers and integrations that "
            "prefer simple HTTP GET over GraphQL or MCP."
        ),
        "",
        "### GET /api/search/",
        "",
        "Parameters (query string):",
        "- q (string, required): Search query text",
        "- corpus (string, optional): Corpus slug to scope the search",
        "- limit (int, optional, default 10, max 50): Number of results",
        "",
        "Example:",
        "```bash",
        f"curl '{base_url}/api/search/?q=indemnification&corpus=my-corpus&limit=5'",
        "```",
        "",
        (
            "Returns: { query, corpus?, results: [{ type, slug, title, "
            "description, similarity_score }] }"
        ),
        "",
        (
            "When a corpus is specified, semantic vector search is attempted "
            "first and falls back to text matching. Without a corpus, the "
            "endpoint searches across all public corpus titles/descriptions "
            "and document titles/descriptions."
        ),
        "",
        "## Corpus-Scoped Endpoints",
        "",
        (
            f"When using `{base_url}/mcp/corpus/{{corpus_slug}}/`, the "
            "`corpus_slug` parameter is automatically injected into all tool "
            "calls. The `list_public_corpuses` tool is replaced by "
            "`get_corpus_info` which returns detailed information about the "
            "scoped corpus."
        ),
        "",
        (
            "Scoped endpoints are ideal for sharing - the URL contains the "
            "corpus context, so collaborators do not need to know the corpus slug."
        ),
        "",
    ]

    # Dynamic corpus listing
    if corpuses:
        lines.append("## Available Collections")
        lines.append("")
        lines.append(
            "The following public corpuses are currently available on this instance:"
        )
        lines.append("")
        for c in corpuses:
            slug = c["slug"]
            title = _sanitize_markdown_title(c["title"])
            doc_count = c["document_count"]
            desc = (c["description"] or "").replace("\n", " ").replace("\r", "")
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"- Slug: `{slug}`")
            lines.append(f"- Documents: {doc_count}")
            if desc:
                lines.append(f"- Description: {desc}")
            lines.append(f"- Corpus-scoped MCP: `{base_url}/mcp/corpus/{slug}/`")
            lines.append("")

    lines.extend(
        [
            "## Architecture",
            "",
            "```",
            "MCP Client  <--JSON-RPC 2.0-->  ASGI Router (/mcp/*)",
            "                                     |",
            "                            +--------+--------+",
            "                            |                 |",
            "                    Global Server     Corpus-Scoped Server",
            "                    (all corpuses)    (single corpus, cached)",
            "                            |                 |",
            "                            +--------+--------+",
            "                                     |",
            "                              Django ORM",
            "                          visible_to_user()",
            "                           (AnonymousUser)",
            "```",
            "",
            "## Links",
            "",
            "- [Source code](https://github.com/Open-Source-Legal/OpenContracts)",
            "- [Project site](https://contracts.opensource.legal)",
            "- [MCP specification](https://modelcontextprotocol.io)",
            "",
        ]
    )
    _record_discovery_event("llms_full_txt", request)
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# sitemap.xml
# ---------------------------------------------------------------------------
@require_GET
@cache_page(DISCOVERY_CACHE_SECONDS)
def sitemap_xml(request: HttpRequest) -> HttpResponse:
    """Generate an XML sitemap listing public corpuses and their documents."""
    base_url = _get_base_url(request)

    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    # Homepage
    url_el = SubElement(urlset, "url")
    SubElement(url_el, "loc").text = f"{base_url}/"
    SubElement(url_el, "changefreq").text = "weekly"
    SubElement(url_el, "priority").text = "1.0"

    # Public corpuses - reuse shared queryset (already capped at MAX_PUBLIC_CORPUSES)
    public_corpuses = list(_get_public_corpus_queryset())
    for corpus in public_corpuses:
        if not corpus.slug:
            continue
        url_el = SubElement(urlset, "url")
        SubElement(url_el, "loc").text = f"{base_url}/c/{corpus.slug}"
        if corpus.modified:
            SubElement(url_el, "lastmod").text = corpus.modified.strftime("%Y-%m-%d")
        SubElement(url_el, "changefreq").text = "weekly"
        SubElement(url_el, "priority").text = "0.8"

    # Public documents within those corpuses (via DocumentPath)
    public_corpus_ids = [c.id for c in public_corpuses]
    if public_corpus_ids:
        doc_paths = (
            DocumentPath.objects.filter(
                corpus_id__in=public_corpus_ids,
                is_current=True,
                is_deleted=False,
            )
            .select_related("document", "corpus")
            .order_by("-document__modified")[:1000]
        )
        for dp in doc_paths:
            doc = dp.document
            corpus = dp.corpus
            if not doc.slug or not corpus or not corpus.slug:
                continue
            url_el = SubElement(urlset, "url")
            SubElement(url_el, "loc").text = f"{base_url}/c/{corpus.slug}/d/{doc.slug}"
            if doc.modified:
                SubElement(url_el, "lastmod").text = doc.modified.strftime("%Y-%m-%d")
            SubElement(url_el, "changefreq").text = "monthly"
            SubElement(url_el, "priority").text = "0.6"

    # Discovery endpoints
    for ep_path in ["/llms.txt", "/llms-full.txt"]:
        url_el = SubElement(urlset, "url")
        SubElement(url_el, "loc").text = f"{base_url}{ep_path}"
        SubElement(url_el, "changefreq").text = "weekly"
        SubElement(url_el, "priority").text = "0.5"

    xml_bytes = tostring(urlset, encoding="unicode", xml_declaration=False)
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes

    _record_discovery_event("sitemap_xml", request)
    return HttpResponse(xml_str, content_type="application/xml; charset=utf-8")


# ---------------------------------------------------------------------------
# .well-known/mcp.json
# ---------------------------------------------------------------------------
@require_GET
@cache_page(DISCOVERY_CACHE_SECONDS)
def well_known_mcp(request: HttpRequest) -> HttpResponse:
    """MCP server discovery endpoint per emerging .well-known convention."""
    base_url = _get_base_url(request)
    corpuses = _get_public_corpuses()

    servers = {
        "opencontracts": {
            "url": f"{base_url}/mcp/",
            "description": (
                "Read-only access to public document corpuses, annotations, "
                "and discussion threads"
            ),
            "transport": "streamable-http",
            "authentication": None,
            "rateLimit": RATE_LIMIT_DISPLAY,
        }
    }

    # Add corpus-scoped servers for each public corpus
    for c in corpuses:
        slug = c["slug"]
        title = c["title"]
        servers[f"opencontracts-{slug}"] = {
            "url": f"{base_url}/mcp/corpus/{slug}/",
            "description": f"Scoped access to: {title}",
            "transport": "streamable-http",
            "authentication": None,
        }

    data = {"mcpServers": servers}

    _record_discovery_event("well_known_mcp", request)
    return HttpResponse(
        json.dumps(data, indent=2),
        content_type="application/json; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# Public search API  (GET /api/search/)
# ---------------------------------------------------------------------------
@require_GET
def search_api(request: HttpRequest) -> JsonResponse:
    """RESTful search endpoint for crawlers and lightweight integrations.

    Accepts GET requests with query parameters and returns JSON results.
    All requests are evaluated as anonymous regardless of authentication —
    this is intentional public-only search.

    Query parameters:
        q (required): Search query text.
        corpus (optional): Corpus slug to scope the search.
        limit (optional): Max results, capped at MAX_SEARCH_RESULTS (default 10).

    When ``corpus`` is provided the endpoint attempts semantic (vector)
    search and falls back to text matching.  Without ``corpus`` it performs
    a text search across all public corpus titles/descriptions and document
    titles/descriptions.

    Response JSON includes a ``similarity_score`` field per result which is
    a float when vector search was used, or ``null`` when only text matching
    was applied.
    """
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse(
            {"error": "Missing required query parameter 'q'."},
            status=400,
        )

    corpus_slug = request.GET.get("corpus", "").strip() or None
    try:
        limit = min(max(int(request.GET.get("limit", 10)), 1), MAX_SEARCH_RESULTS)
    except (ValueError, TypeError):
        limit = 10

    anonymous = AnonymousUser()

    _record_discovery_event("search_api", request)

    if corpus_slug:
        return _search_within_corpus(query, corpus_slug, limit, anonymous)

    return _search_global(query, limit, anonymous)


def _search_within_corpus(
    query: str, corpus_slug: str, limit: int, user
) -> JsonResponse:
    """Search documents within a single public corpus."""
    try:
        corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
    except Corpus.DoesNotExist:
        return JsonResponse({"error": "Corpus not found."}, status=404)

    corpus_doc_ids = corpus.get_documents().values_list("id", flat=True)
    results = []

    # Attempt vector search first, fall through to text search on empty results
    try:
        embedder_path, query_vector = corpus.embed_text(query)
        if query_vector:
            doc_results = list(
                Document.objects.filter(id__in=corpus_doc_ids).search_by_embedding(  # type: ignore[attr-defined]
                    query_vector, embedder_path, top_k=limit
                )
            )
            for doc in doc_results:
                results.append(
                    {
                        "type": "document",
                        "slug": doc.slug,
                        "title": doc.title or "",
                        "description": (doc.description or "")[:200],
                        "corpus": corpus_slug,
                        "similarity_score": float(getattr(doc, "similarity_score", 0)),
                    }
                )
            if results:
                return JsonResponse(
                    {"query": query, "corpus": corpus_slug, "results": results}
                )
    except Exception:
        logger.debug("Vector search failed, falling back to text search", exc_info=True)

    # Text search fallback — corpus access already verified above,
    # so query documents directly via corpus membership
    documents = list(
        Document.objects.filter(id__in=corpus_doc_ids).filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )[:limit]
    )
    for doc in documents:
        results.append(
            {
                "type": "document",
                "slug": doc.slug,
                "title": doc.title or "",
                "description": (doc.description or "")[:200],
                "corpus": corpus_slug,
                "similarity_score": None,
            }
        )

    return JsonResponse({"query": query, "corpus": corpus_slug, "results": results})


def _search_global(query: str, limit: int, user) -> JsonResponse:
    """Search across all public corpuses and their documents.

    All requests are evaluated as anonymous regardless of authentication
    (intentional public-only search).  Results are split evenly between
    corpus and document matches so that one type cannot suppress the other.
    """
    results: list[dict] = []

    # Reserve at least half the slots for each type so corpuses can't
    # suppress all document results (and vice-versa).
    corpus_limit = max(limit // 2, 1)
    doc_limit = max(limit - corpus_limit, 1)

    # Search corpuses by title/description
    matching_corpuses = list(
        Corpus.objects.visible_to_user(user)
        .filter(Q(title__icontains=query) | Q(description__icontains=query))
        .order_by("-created")[:corpus_limit]
    )
    for corpus in matching_corpuses:
        results.append(
            {
                "type": "corpus",
                "slug": corpus.slug,
                "title": corpus.title or "",
                "description": (corpus.description or "")[:200],
                "similarity_score": None,
            }
        )

    # Search documents across all public corpuses.
    # If corpuses used fewer slots than reserved, give the surplus to documents.
    remaining = limit - len(results)
    doc_limit = max(remaining, doc_limit)
    if doc_limit > 0:
        # Re-query all public corpus IDs (not just title-matched ones)
        # so documents in any public corpus are discoverable
        public_corpus_ids = Corpus.objects.visible_to_user(user).values_list(
            "id", flat=True
        )
        matching_docs = list(
            Document.objects.visible_to_user(user, lightweight=True)
            .filter(
                path_records__corpus_id__in=public_corpus_ids,
                path_records__is_current=True,
                path_records__is_deleted=False,
            )
            .filter(Q(title__icontains=query) | Q(description__icontains=query))
            .only("slug", "title", "description", "modified")
            .distinct()
            .order_by("-modified")[:doc_limit]
        )
        for doc in matching_docs:
            results.append(
                {
                    "type": "document",
                    "slug": doc.slug,
                    "title": doc.title or "",
                    "description": (doc.description or "")[:200],
                    "similarity_score": None,
                }
            )

    return JsonResponse({"query": query, "results": results[:limit]})
