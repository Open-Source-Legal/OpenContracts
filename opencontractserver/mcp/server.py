"""
OpenContracts MCP Server.

Model Context Protocol server providing read-only access to public OpenContracts resources.
Supports multiple transports:
- Streamable HTTP transport at /mcp (recommended, stateless mode)
- SSE transport at /sse (deprecated, for backward compatibility)
- stdio transport (for CLI usage)

Uses stateless mode for HTTP - each request is independent, avoiding session
initialization race conditions that plagued the older SSE transport.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, MutableMapping
from contextlib import AbstractAsyncContextManager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from opencontractserver.users.types import UserOrAnonymous

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from graphql_jwt.exceptions import JSONWebTokenError, JSONWebTokenExpired
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Resource, ResourceTemplate, TextContent, Tool
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

# Module-level import so test-time patching of this symbol is stable
# (see MCPAsgiAppAuthTest for the patch sites).
from config.jwt_utils import get_user_from_jwt_token
from config.ratelimit.decorators import MCPRateLimitError, check_mcp_rate_limit
from config.ratelimit.keys import get_client_ip_from_scope
from opencontractserver.constants.mcp import MAX_THREAD_MESSAGE_LENGTH

from .resources import (
    get_annotation_resource,
    get_corpus_resource,
    get_document_resource,
    get_thread_resource,
)
from .telemetry import (
    arecord_mcp_request,
    arecord_mcp_resource_read,
    arecord_mcp_tool_call,
    clear_request_context,
    get_user_agent_from_scope,
    set_request_context,
)
from .tools import (
    create_thread_message,
    get_document_text,
    get_scoped_tool_handlers,
    get_thread_messages,
    list_annotations,
    list_documents,
    list_public_corpuses,
    list_threads,
    search_corpus,
)

logger = logging.getLogger(__name__)

# ContextVar to thread the ASGI scope into tool handlers for per-tool rate limiting.
# Set at the ASGI app level before dispatching to the MCP session manager.
# Default is None (not an empty dict) to avoid sharing a mutable default across contexts.
_mcp_asgi_scope: ContextVar[MutableMapping[str, Any] | None] = ContextVar(
    "mcp_asgi_scope", default=None
)
_mcp_user: ContextVar[UserOrAnonymous | None] = ContextVar("mcp_user", default=None)


def _extract_bearer_token(scope: MutableMapping[str, Any]) -> str | None:
    # Only HTTP scopes carry a real Authorization header in the format
    # we expect; websocket/lifespan scopes don't, and middleware in some
    # ASGI stacks reshapes their ``headers`` differently.
    if scope.get("type") != "http":
        return None
    for name, value in scope.get("headers", []):
        if name.lower() == b"authorization":
            auth_header = value.decode("utf-8", errors="ignore")
            # The Authorization header must start with exactly ``Bearer ``
            # (case-insensitive scheme, single ASCII space). Comparing the
            # first 7 chars to the lowercased literal makes that contract
            # explicit; we then slice at index 7 and ``.strip()`` to remove
            # any incidental trailing whitespace inside the token value
            # itself. The JWT validator would have rejected a malformed
            # token downstream anyway, but rejecting non-standard prefixes
            # here keeps the auth boundary tight and the error obvious.
            if auth_header[:7].lower() == "bearer ":
                return auth_header[7:].strip() or None
    return None


def _build_www_authenticate_header(scope: MutableMapping[str, Any]) -> bytes:
    """Construct the ``WWW-Authenticate`` value for a 401 MCP response.

    Per the MCP 2025-06-18 Authorization spec (and RFC 9728), when the
    server rejects a request it advertises *where* the client should go
    to obtain a credential by pointing at the OAuth 2.0 protected-
    resource metadata document. Interactive MCP clients (Claude Desktop,
    Cursor) follow that pointer, fetch the metadata, discover the
    configured authorization server (Auth0), and drive the user through
    an Authorization-Code + PKCE flow — no preconfigured token needed.

    When ``USE_AUTH0=False`` there is no spec-compliant authorization
    server to advertise, so the header degrades to a plain
    ``Bearer realm=...`` value. Clients can still infer the credential
    *type* but will not auto-discover a login flow.
    """
    realm = b'Bearer realm="opencontracts"'
    if not getattr(settings, "USE_AUTH0", False):
        return realm

    # Derive the base URL from the ASGI scope. ``Host`` carries the
    # public hostname; ``X-Forwarded-Proto`` (set by the reverse proxy
    # in production) tells us the original scheme. Fall back to the
    # ASGI ``scope["scheme"]`` for direct connections (local dev).
    host = b""
    forwarded_proto = b""
    for name, value in scope.get("headers", []):
        lower = name.lower()
        if lower == b"host":
            host = value
        elif lower == b"x-forwarded-proto":
            forwarded_proto = value
    if not host:
        # No Host header at all is unusual — punt on the resource_metadata
        # hint rather than emitting a malformed URL.
        return realm
    raw_scheme = forwarded_proto.decode("ascii", errors="ignore") or str(
        scope.get("scheme", "http")
    )
    scheme = raw_scheme.split(",", 1)[0].strip().lower()
    if scheme not in {"http", "https"}:
        scheme = "http"
    # Defensive: a misconfigured reverse proxy could forward a ``Host``
    # carrying characters that have semantic meaning inside the
    # ``WWW-Authenticate`` value. The header is a comma-separated list of
    # auth-params, so ``,`` and ``;`` are particularly dangerous —
    # smuggling either into the embedded ``resource_metadata`` URL could
    # let a crafted Host header inject a sibling auth-param. Strip a
    # conservative set of characters and bail entirely if the result no
    # longer matches a plain hostname (letters, digits, dot, dash, colon,
    # square brackets for IPv6).
    raw_host = host.decode("ascii", errors="ignore")
    safe_host = raw_host
    for bad in ('"', "\r", "\n", " ", ",", ";", "\t"):
        safe_host = safe_host.replace(bad, "")
    if not safe_host or not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", safe_host):
        return realm
    base_url = f"{scheme}://{safe_host}"
    metadata_url = f"{base_url}/.well-known/oauth-protected-resource"
    return (f'Bearer realm="opencontracts", resource_metadata="{metadata_url}"').encode(
        "ascii", errors="ignore"
    )


async def _check_per_tool_rate_limit(name: str) -> None:
    """Check per-tool MCP rate limit using the ASGI scope from ContextVar.

    Raises ``MCPRateLimitError`` if the tool is rate limited.
    Silently skips when no ASGI scope is available (e.g. stdio transport,
    tests) since there is no network-level identity to key on.

    NOTE: ``create_thread_message`` (the first write tool) inherits the
    generic per-tool limit configured for MCP, not a write-specific bucket.
    The operator-facing knob lives in
    ``config.ratelimit.mcp_settings`` — adding a dedicated
    write-mutation throttle is deliberately deferred until a second write
    tool ships so the limit shape can be designed from two data points
    rather than guessed from one.
    """
    scope = _mcp_asgi_scope.get()
    if scope is not None:
        # skip_global=True because the ASGI app already ran the global check
        # before dispatching to the MCP handler.  Only per-tool limits are
        # checked here to avoid double-incrementing the global counter.
        is_limited, error_msg, _ = await check_mcp_rate_limit(
            scope, tool_name=name, skip_global=True
        )
        if is_limited:
            # slugs not available at this stage (extracted from arguments later)
            await arecord_mcp_tool_call(
                name, success=False, error_type="RateLimitExceeded"
            )
            raise MCPRateLimitError(error_msg)
    else:
        logger.debug(
            "MCP rate limiting skipped for tool %s: no ASGI scope available", name
        )


# Map tool names to implementations - at module level for testability.
#
# Write tools (``create_thread_message`` is the first) enforce
# authentication and per-resource permissions *inside the tool body* —
# the dispatcher does not gate writes by tool name. Anonymous callers
# that invoke a write tool see ``PermissionDenied`` from the tool,
# which the dispatcher surfaces as a structured ``{"error": ...}``
# payload. Do not add a wrapper-level write guard here; it would either
# duplicate the in-tool check or drift from it.
TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "list_public_corpuses": list_public_corpuses,
    "list_documents": list_documents,
    "get_document_text": get_document_text,
    "list_annotations": list_annotations,
    "search_corpus": search_corpus,
    "list_threads": list_threads,
    "get_thread_messages": get_thread_messages,
    "create_thread_message": create_thread_message,
}


class URIParser:
    """Parse MCP resource URIs safely using regex patterns."""

    # Slug pattern: alphanumeric and hyphens only
    SLUG_PATTERN = r"[A-Za-z0-9\-]+"

    PATTERNS = {
        "corpus": re.compile(rf"^corpus://({SLUG_PATTERN})$"),
        "document": re.compile(rf"^document://({SLUG_PATTERN})/({SLUG_PATTERN})$"),
        "annotation": re.compile(
            rf"^annotation://({SLUG_PATTERN})/({SLUG_PATTERN})/(\d+)$"
        ),
        "thread": re.compile(rf"^thread://({SLUG_PATTERN})/threads/(\d+)$"),
    }

    @classmethod
    def parse_corpus(cls, uri: str) -> str | None:
        """Parse corpus URI, returns corpus_slug or None."""
        match = cls.PATTERNS["corpus"].match(uri)
        return match.group(1) if match else None

    @classmethod
    def parse_document(cls, uri: str) -> tuple[str, str] | None:
        """Parse document URI, returns (corpus_slug, document_slug) or None."""
        match = cls.PATTERNS["document"].match(uri)
        return (match.group(1), match.group(2)) if match else None

    @classmethod
    def parse_annotation(cls, uri: str) -> tuple[str, str, int] | None:
        """Parse annotation URI, returns (corpus_slug, document_slug, annotation_id) or None."""
        match = cls.PATTERNS["annotation"].match(uri)
        return (match.group(1), match.group(2), int(match.group(3))) if match else None

    @classmethod
    def parse_thread(cls, uri: str) -> tuple[str, int] | None:
        """Parse thread URI, returns (corpus_slug, thread_id) or None."""
        match = cls.PATTERNS["thread"].match(uri)
        return (match.group(1), int(match.group(2))) if match else None


async def read_resource_handler(uri: str) -> str:
    """
    Resolve resource URI and return content.

    This is the handler function for MCP resource reads.
    Exposed at module level for testability.
    """
    # Convert AnyUrl to string if needed (MCP library uses pydantic AnyUrl)
    uri_str = str(uri)

    resource_type = "unknown"
    _corpus_slug: str | None = None
    _document_slug: str | None = None
    user = _mcp_user.get()
    try:
        # Try corpus URI
        corpus_slug = URIParser.parse_corpus(uri_str)
        if corpus_slug:
            resource_type = "corpus"
            _corpus_slug = corpus_slug
            result = await sync_to_async(get_corpus_resource)(corpus_slug, user=user)
            await arecord_mcp_resource_read(
                resource_type, success=True, corpus_slug=_corpus_slug
            )
            return result

        # Try document URI
        doc_parts = URIParser.parse_document(uri_str)
        if doc_parts:
            resource_type = "document"
            corpus_slug, document_slug = doc_parts
            _corpus_slug = corpus_slug
            _document_slug = document_slug
            result = await sync_to_async(get_document_resource)(
                corpus_slug, document_slug, user=user
            )
            await arecord_mcp_resource_read(
                resource_type,
                success=True,
                corpus_slug=_corpus_slug,
                document_slug=_document_slug,
            )
            return result

        # Try annotation URI
        ann_parts = URIParser.parse_annotation(uri_str)
        if ann_parts:
            resource_type = "annotation"
            corpus_slug, document_slug, annotation_id = ann_parts
            _corpus_slug = corpus_slug
            _document_slug = document_slug
            result = await sync_to_async(get_annotation_resource)(
                corpus_slug, document_slug, annotation_id, user=user
            )
            await arecord_mcp_resource_read(
                resource_type,
                success=True,
                corpus_slug=_corpus_slug,
                document_slug=_document_slug,
            )
            return result

        # Try thread URI
        thread_parts = URIParser.parse_thread(uri_str)
        if thread_parts:
            resource_type = "thread"
            corpus_slug, thread_id = thread_parts
            _corpus_slug = corpus_slug
            result = await sync_to_async(get_thread_resource)(
                corpus_slug, thread_id, user=user
            )
            await arecord_mcp_resource_read(
                resource_type, success=True, corpus_slug=_corpus_slug
            )
            return result

        raise ValueError(f"Invalid or unrecognized resource URI: {uri_str}")
    except Exception as e:
        await arecord_mcp_resource_read(
            resource_type,
            success=False,
            error_type=type(e).__name__,
            corpus_slug=_corpus_slug,
            document_slug=_document_slug,
        )
        raise


def _format_tool_error_text(e: BaseException) -> str:
    """Render a permission/validation error into the LLM-facing error string.

    ``ValidationError.messages`` is preferred for structured payloads; the
    plain ``PermissionDenied`` path falls back to ``str(e)``. Shared between
    the non-scoped ``call_tool_handler`` and the scoped ``call_tool``
    dispatcher so error serialisation stays in lockstep.
    """
    if isinstance(e, ValidationError):
        return "; ".join(e.messages) or "Validation error"
    if isinstance(e, PermissionDenied):
        return str(e) or "Permission denied"
    # Anything else reaching this helper is an unexpected exception type
    # (the call sites narrow to ``PermissionDenied``/``ValidationError``,
    # but the body is shared so be defensive). Returning "Permission
    # denied" for, say, a raw ``Exception`` would actively mislead the
    # LLM about what went wrong.
    return str(e) or "Unexpected error"


async def _record_and_return_tool_error(
    e: BaseException,
    *,
    name: str,
    corpus_slug: str | None,
    document_slug: str | None,
) -> list[TextContent]:
    """Telemetry + structured ``error`` payload for handled tool failures."""
    await arecord_mcp_tool_call(
        name,
        success=False,
        error_type=type(e).__name__,
        corpus_slug=corpus_slug,
        document_slug=document_slug,
    )
    return [
        TextContent(
            type="text",
            text=json.dumps({"error": _format_tool_error_text(e)}),
        )
    ]


async def call_tool_handler(name: str, arguments: dict) -> list[TextContent]:
    """
    Execute tool and return results.

    This is the handler function for MCP tool calls.
    Exposed at module level for testability.

    Includes per-tool rate limiting via the shared rate limiting engine.
    The ASGI scope is accessed through ``_mcp_asgi_scope`` ContextVar
    (set by the ASGI app before dispatching).
    """
    await _check_per_tool_rate_limit(name)

    # Extract resource slugs from arguments for telemetry (public identifiers only).
    # "corpus_slug" / "document_slug" are the enforced convention across all tools.
    # Extracted for telemetry; validated downstream before DB use.
    _corpus_slug = arguments.get("corpus_slug")
    _document_slug = arguments.get("document_slug")

    handler = TOOL_HANDLERS.get(name)
    if not handler:
        await arecord_mcp_tool_call(
            name,
            success=False,
            error_type="UnknownTool",
            corpus_slug=_corpus_slug,
            document_slug=_document_slug,
        )
        raise ValueError(f"Unknown tool: {name}")

    try:
        # Run synchronous Django ORM handlers in thread pool.
        # All TOOL_HANDLERS accept an optional `user`; passing None preserves
        # anonymous semantics. Drop any client-supplied ``user`` argument so
        # it can't collide with the kwarg below (TypeError would otherwise
        # escape the structured error branch as a raw transport error).
        user = _mcp_user.get()
        safe_arguments = {k: v for k, v in arguments.items() if k != "user"}
        result = await sync_to_async(handler)(user=user, **safe_arguments)
        await arecord_mcp_tool_call(
            name,
            success=True,
            corpus_slug=_corpus_slug,
            document_slug=_document_slug,
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except (PermissionDenied, ValidationError) as e:
        # Surface permission failures (e.g., write tools called by anonymous
        # callers) and input-validation errors (blank/oversized content, etc.)
        # as structured error results so the LLM can reason about them and
        # retry/correct, rather than receiving an opaque transport error.
        return await _record_and_return_tool_error(
            e,
            name=name,
            corpus_slug=_corpus_slug,
            document_slug=_document_slug,
        )
    except Exception as e:
        await arecord_mcp_tool_call(
            name,
            success=False,
            error_type=type(e).__name__,
            corpus_slug=_corpus_slug,
            document_slug=_document_slug,
        )
        raise


def create_mcp_server() -> Server:
    """Create and configure the MCP server instance."""
    mcp_server = Server("opencontracts")

    @mcp_server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources (none - use templates instead)."""
        # All resources require parameters, so we return empty list
        # Use list_resource_templates for URI patterns
        return []

    @mcp_server.list_resource_templates()
    async def list_resource_templates() -> list[ResourceTemplate]:
        """List available resource URI templates."""
        return [
            ResourceTemplate(
                uriTemplate="corpus://{corpus_slug}",
                name="Public Corpus",
                description="Access public corpus metadata and contents",
                mimeType="application/json",
            ),
            ResourceTemplate(
                uriTemplate="document://{corpus_slug}/{document_slug}",
                name="Public Document",
                description="Access public document with extracted text",
                mimeType="application/json",
            ),
            ResourceTemplate(
                uriTemplate="annotation://{corpus_slug}/{document_slug}/{annotation_id}",
                name="Document Annotation",
                description="Access specific annotation on a document",
                mimeType="application/json",
            ),
            ResourceTemplate(
                uriTemplate="thread://{corpus_slug}/threads/{thread_id}",
                name="Discussion Thread",
                description="Access public discussion thread with messages",
                mimeType="application/json",
            ),
        ]

    # Register the module-level handler with the MCP server
    mcp_server.read_resource()(read_resource_handler)

    @mcp_server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="list_public_corpuses",
                description=(
                    "List corpuses visible to the caller. Anonymous callers "
                    "see only public, published corpuses. Authenticated "
                    "callers additionally see private corpuses they own or "
                    "have been granted read access to. (Name retained for "
                    "backwards compatibility with existing MCP clients.)"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "default": 20,
                            "description": "Max results (1-100)",
                        },
                        "offset": {
                            "type": "integer",
                            "default": 0,
                            "description": "Pagination offset",
                        },
                        "search": {
                            "type": "string",
                            "default": "",
                            "description": "Search filter",
                        },
                    },
                },
            ),
            Tool(
                name="list_documents",
                description="List documents in a corpus",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corpus_slug": {
                            "type": "string",
                            "description": "Corpus identifier",
                        },
                        "limit": {"type": "integer", "default": 50},
                        "offset": {"type": "integer", "default": 0},
                        "search": {"type": "string", "default": ""},
                    },
                    "required": ["corpus_slug"],
                },
            ),
            Tool(
                name="get_document_text",
                description="Get full extracted text from a document",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corpus_slug": {
                            "type": "string",
                            "description": "Corpus identifier",
                        },
                        "document_slug": {
                            "type": "string",
                            "description": "Document identifier",
                        },
                    },
                    "required": ["corpus_slug", "document_slug"],
                },
            ),
            Tool(
                name="list_annotations",
                description="List annotations on a document",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corpus_slug": {"type": "string"},
                        "document_slug": {"type": "string"},
                        "page": {
                            "type": "integer",
                            "description": "Filter to page number",
                        },
                        "label_text": {
                            "type": "string",
                            "description": "Filter by label text",
                        },
                        "limit": {"type": "integer", "default": 100},
                        "offset": {"type": "integer", "default": 0},
                    },
                    "required": ["corpus_slug", "document_slug"],
                },
            ),
            Tool(
                name="search_corpus",
                description="Semantic search within a corpus",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corpus_slug": {"type": "string"},
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["corpus_slug", "query"],
                },
            ),
            Tool(
                name="list_threads",
                description="List discussion threads in a corpus",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corpus_slug": {"type": "string"},
                        "document_slug": {
                            "type": "string",
                            "description": "Optional document filter",
                        },
                        "limit": {"type": "integer", "default": 20},
                        "offset": {"type": "integer", "default": 0},
                    },
                    "required": ["corpus_slug"],
                },
            ),
            Tool(
                name="get_thread_messages",
                description="Get messages in a thread",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corpus_slug": {"type": "string"},
                        "thread_id": {"type": "integer"},
                        "flatten": {
                            "type": "boolean",
                            "default": False,
                            "description": "Return flat list",
                        },
                    },
                    "required": ["corpus_slug", "thread_id"],
                },
            ),
            Tool(
                name="create_thread_message",
                description="Create a new message in a thread (requires authenticated MCP session)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corpus_slug": {"type": "string"},
                        "thread_id": {"type": "integer"},
                        "content": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": MAX_THREAD_MESSAGE_LENGTH,
                        },
                        "parent_message_id": {"type": "integer"},
                    },
                    "required": ["corpus_slug", "thread_id", "content"],
                },
            ),
        ]

    # Register the module-level handler with the MCP server
    mcp_server.call_tool()(call_tool_handler)

    return mcp_server


# Create the global MCP server instance
mcp_server = create_mcp_server()

# =============================================================================
# CORPUS-SCOPED MCP SERVER SUPPORT
# =============================================================================
# Supports scoped MCP endpoints at /mcp/corpus/{corpus_slug}/ where all tools
# are automatically scoped to a specific corpus.


def get_scoped_tool_definitions(corpus_slug: str) -> list[Tool]:
    """
    Get tool definitions for a corpus-scoped MCP endpoint.

    These tools have corpus_slug removed from required parameters since it's
    auto-injected from the URL path.

    Args:
        corpus_slug: The corpus slug this endpoint is scoped to

    Returns:
        List of Tool definitions for the scoped endpoint
    """
    return [
        Tool(
            name="get_corpus_info",
            description=f"Get detailed information about the '{corpus_slug}' corpus",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="list_documents",
            description=f"List documents in the '{corpus_slug}' corpus",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50},
                    "offset": {"type": "integer", "default": 0},
                    "search": {"type": "string", "default": ""},
                },
            },
        ),
        Tool(
            name="get_document_text",
            description="Get full extracted text from a document",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_slug": {
                        "type": "string",
                        "description": "Document identifier",
                    },
                },
                "required": ["document_slug"],
            },
        ),
        Tool(
            name="list_annotations",
            description="List annotations on a document",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_slug": {"type": "string"},
                    "page": {
                        "type": "integer",
                        "description": "Filter to page number",
                    },
                    "label_text": {
                        "type": "string",
                        "description": "Filter by label text",
                    },
                    "limit": {"type": "integer", "default": 100},
                    "offset": {"type": "integer", "default": 0},
                },
                "required": ["document_slug"],
            },
        ),
        Tool(
            name="search_corpus",
            description=f"Semantic search within the '{corpus_slug}' corpus",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_threads",
            description=f"List discussion threads in the '{corpus_slug}' corpus",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_slug": {
                        "type": "string",
                        "description": "Optional document filter",
                    },
                    "limit": {"type": "integer", "default": 20},
                    "offset": {"type": "integer", "default": 0},
                },
            },
        ),
        Tool(
            name="get_thread_messages",
            description="Get messages in a thread",
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "integer"},
                    "flatten": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return flat list",
                    },
                },
                "required": ["thread_id"],
            },
        ),
        Tool(
            name="create_thread_message",
            description=(
                "Create a new message in a thread within the "
                f"'{corpus_slug}' corpus (requires authenticated MCP session). "
                "Note: corpus_slug is injected from the endpoint URL and must "
                "not be supplied by the client."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "integer"},
                    "content": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_THREAD_MESSAGE_LENGTH,
                    },
                    "parent_message_id": {"type": "integer"},
                },
                "required": ["thread_id", "content"],
            },
        ),
    ]


def get_scoped_resource_definitions(
    corpus_slug: str, limit: int = 50, user: UserOrAnonymous | None = None
) -> list[Resource]:
    """
    Get concrete resource definitions for a corpus-scoped MCP endpoint.

    Dynamically queries the database to list actual documents and threads
    in the corpus as readable resources. Uses CorpusDocumentService for
    proper document retrieval.

    Args:
        corpus_slug: The corpus slug this endpoint is scoped to
        limit: Maximum number of documents/threads to include (default 50 each)

    Returns:
        List of concrete Resource definitions
    """
    from django.contrib.auth.models import AnonymousUser

    from opencontractserver.conversations.models import (
        Conversation,
        ConversationTypeChoices,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    resources: list[Resource] = []
    effective_user = user or AnonymousUser()

    try:
        corpus = Corpus.objects.visible_to_user(effective_user).get(slug=corpus_slug)
    except Corpus.DoesNotExist:
        return resources

    # Add corpus resource
    resources.append(
        Resource(
            uri=AnyUrl(f"corpus://{corpus_slug}"),
            name="Corpus",
            description=f"Access the '{corpus_slug}' corpus metadata and contents",
            mimeType="application/json",
        )
    )

    # Add document resources using CorpusDocumentService
    documents = CorpusDocumentService.get_corpus_documents(
        user=effective_user, corpus=corpus, include_deleted=False
    )[:limit]
    for doc in documents:
        resources.append(
            Resource(
                uri=AnyUrl(f"document://{corpus_slug}/{doc.slug}"),
                name=f"Document: {doc.title or doc.slug}",
                description=doc.description[:100] if doc.description else "Document",
                mimeType="application/json",
            )
        )

    # Add thread resources
    threads = (
        Conversation.objects.visible_to_user(effective_user)
        .filter(
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=corpus,
        )
        .order_by("-created")[:limit]
    )
    for thread in threads:
        resources.append(
            Resource(
                uri=AnyUrl(f"thread://{corpus_slug}/threads/{thread.id}"),
                name=f"Thread: {thread.title or f'Thread {thread.id}'}",
                description=(
                    thread.description[:100]
                    if thread.description
                    else "Discussion thread"
                ),
                mimeType="application/json",
            )
        )

    return resources


def get_scoped_resource_template_definitions(
    corpus_slug: str,
) -> list[ResourceTemplate]:
    """
    Get resource template definitions for a corpus-scoped MCP endpoint.

    Args:
        corpus_slug: The corpus slug this endpoint is scoped to

    Returns:
        List of ResourceTemplate definitions for parameterized resources
    """
    return [
        ResourceTemplate(
            uriTemplate=f"document://{corpus_slug}/{{document_slug}}",
            name="Document",
            description="Access document with extracted text",
            mimeType="application/json",
        ),
        ResourceTemplate(
            uriTemplate=f"annotation://{corpus_slug}/{{document_slug}}/{{annotation_id}}",
            name="Annotation",
            description="Access specific annotation on a document",
            mimeType="application/json",
        ),
        ResourceTemplate(
            uriTemplate=f"thread://{corpus_slug}/threads/{{thread_id}}",
            name="Discussion Thread",
            description="Access discussion thread with messages",
            mimeType="application/json",
        ),
    ]


def create_scoped_mcp_server(corpus_slug: str) -> Server:
    """
    Create an MCP server instance scoped to a specific corpus.

    All tools will automatically operate within the context of the specified corpus.
    Validates corpus permissions on every tool call to prevent access after
    corpus becomes private.

    Args:
        corpus_slug: The corpus slug to scope the server to

    Returns:
        Configured MCP Server instance scoped to the corpus
    """
    scoped_server = Server(f"opencontracts-corpus-{corpus_slug}")

    # Get scoped tool handlers
    scoped_handlers = get_scoped_tool_handlers(corpus_slug)

    def _validate_corpus_sync(user: UserOrAnonymous | None = None) -> bool:
        """Synchronously validate the scoped corpus is still visible to the caller."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.corpuses.models import Corpus

        effective_user = user or AnonymousUser()
        return (
            Corpus.objects.visible_to_user(effective_user)
            .filter(slug=corpus_slug)
            .exists()
        )

    @scoped_server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available concrete resources for this scoped corpus."""
        # Use sync_to_async since this queries the database
        return await sync_to_async(get_scoped_resource_definitions)(
            corpus_slug, user=_mcp_user.get()
        )

    @scoped_server.list_resource_templates()
    async def list_resource_templates() -> list[ResourceTemplate]:
        """List available resource templates for this scoped corpus."""
        return get_scoped_resource_template_definitions(corpus_slug)

    # Resource handler - reuse the global handler (it validates corpus access)
    scoped_server.read_resource()(read_resource_handler)

    @scoped_server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools for this scoped corpus."""
        return get_scoped_tool_definitions(corpus_slug)

    @scoped_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """
        Execute scoped tool and return results.

        Validates corpus permissions on every call to prevent access
        if corpus becomes private between manager creation and tool execution.
        Includes per-tool rate limiting via the shared engine.

        Structure mirrors the non-scoped ``call_tool_handler`` so every
        error path is recorded exactly once:
          * Unknown-tool check sits *outside* the ``try`` so the ``ValueError``
            it raises is not also caught by ``except Exception``.
          * Corpus-visibility check sits *inside* the ``try`` so its
            ``PermissionDenied`` flows through ``_record_and_return_tool_error``
            and becomes a structured ``{"error": ...}`` LLM-facing payload.
          * Do not reintroduce a pre-raise ``arecord_mcp_tool_call`` for either
            check — the structured-error handler and ``except Exception`` already
            record. Earlier revisions recorded twice, which silently inflated
            failure counts in telemetry.
        """
        await _check_per_tool_rate_limit(name)

        # Extract document_slug from arguments for telemetry
        _document_slug = arguments.get("document_slug")

        # Pick up the authenticated user (if any) from the ASGI-level
        # ContextVar so scoped endpoints honor per-user visibility.
        user = _mcp_user.get()

        # Unknown-tool guard outside the try block — mirrors the non-scoped
        # dispatcher. Records once and propagates as a transport error, which
        # is acceptable because clients discover tools via ``tools/list`` so
        # this path is unreachable in normal use.
        handler = scoped_handlers.get(name)
        if not handler:
            await arecord_mcp_tool_call(
                name,
                success=False,
                error_type="UnknownTool",
                corpus_slug=corpus_slug,
                document_slug=_document_slug,
            )
            raise ValueError(f"Unknown tool: {name}")

        try:
            # Re-validate corpus on every tool call so corpora that go private
            # after the scoped manager was cached still surface a structured
            # permission-denied result rather than a transport error. Kept
            # inside the try block so Django's ``PermissionDenied`` is caught
            # by the structured-error branch below (Python's ``PermissionError``
            # would route through ``except Exception`` and bubble up as a raw
            # transport error — do not change to ``PermissionError``).
            is_valid = await sync_to_async(_validate_corpus_sync)(user)
            if not is_valid:
                raise PermissionDenied(f"Corpus '{corpus_slug}' is not accessible")

            # Run synchronous Django ORM handlers in thread pool. All scoped
            # handlers accept an optional `user`; passing None preserves
            # anonymous semantics for unauthenticated callers. Drop any
            # client-supplied ``user`` argument so it can't collide with the
            # kwarg below.
            safe_arguments = {k: v for k, v in arguments.items() if k != "user"}
            result = await sync_to_async(handler)(user=user, **safe_arguments)
            await arecord_mcp_tool_call(
                name,
                success=True,
                corpus_slug=corpus_slug,
                document_slug=_document_slug,
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except (PermissionDenied, ValidationError) as e:
            # Same rationale as the non-scoped dispatcher: surface
            # permission failures and Django input-validation errors as
            # structured tool results so the LLM can react to them.
            return await _record_and_return_tool_error(
                e,
                name=name,
                corpus_slug=corpus_slug,
                document_slug=_document_slug,
            )
        except Exception as e:
            await arecord_mcp_tool_call(
                name,
                success=False,
                error_type=type(e).__name__,
                corpus_slug=corpus_slug,
                document_slug=_document_slug,
            )
            raise

    return scoped_server


# =============================================================================
# CACHE MANAGEMENT FOR SCOPED MCP ENDPOINTS
# =============================================================================
# TTL+LRU cache to prevent unbounded memory growth while maintaining performance.
# - TTL: Entries expire after 1 hour to handle corpus permission changes
# - LRU: Maximum 100 entries, evicts least-recently-used when full
# - Async cleanup: Properly closes async contexts on eviction


class TTLLRUCache:
    """
    A cache with TTL expiration and LRU eviction.

    Thread-safe for concurrent access via asyncio.Lock.
    Calls cleanup_callback when items are evicted.

    Thread Safety / Event Loop Notes:
    ---------------------------------
    The asyncio.Lock is created lazily on first use within an async context.
    This cache is designed for use within a single event loop (the ASGI server's
    main event loop). The lock provides safety for concurrent coroutines within
    that loop.

    Important limitations:
    - All async methods (get, set, remove, clear) must be called from async contexts
    - The cache should be instantiated at module level (as done for _scoped_session_managers
      and _scoped_lifespan_managers) and used within the ASGI application
    - __len__ is not async-safe and should only be used for monitoring/debugging

    The cleanup_callback runs synchronously within the lock, so it should be fast.
    For async cleanup (like shutting down MCP session managers), the callback
    should schedule async work via loop.create_task() rather than awaiting directly.
    """

    def __init__(
        self,
        maxsize: int = 100,
        ttl_seconds: float = 3600,  # 1 hour default
        cleanup_callback: Callable[[str, Any], None] | None = None,
    ) -> None:
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._cleanup_callback = cleanup_callback
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Get item from cache, returns None if not found or expired."""
        async with self._lock:
            if key not in self._cache:
                return None

            value, timestamp = self._cache[key]
            if time.time() - timestamp > self._ttl_seconds:
                # Expired - remove and cleanup
                del self._cache[key]
                if self._cleanup_callback:
                    self._cleanup_callback(key, value)
                logger.debug(f"Cache entry expired: {key}")
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: Any) -> None:
        """Set item in cache, evicting LRU if at capacity."""
        async with self._lock:
            # If key exists, remove it first (to update timestamp)
            if key in self._cache:
                del self._cache[key]

            # Evict LRU entries if at capacity
            while len(self._cache) >= self._maxsize:
                oldest_key, (oldest_value, _) = self._cache.popitem(last=False)
                if self._cleanup_callback:
                    self._cleanup_callback(oldest_key, oldest_value)
                logger.info(f"Cache LRU eviction: {oldest_key}")

            self._cache[key] = (value, time.time())

    async def remove(self, key: str) -> bool:
        """Remove item from cache. Returns True if removed."""
        async with self._lock:
            if key in self._cache:
                value, _ = self._cache.pop(key)
                if self._cleanup_callback:
                    self._cleanup_callback(key, value)
                return True
            return False

    async def clear(self) -> None:
        """Clear all items from cache, calling cleanup on each."""
        async with self._lock:
            for key, (value, _) in list(self._cache.items()):
                if self._cleanup_callback:
                    self._cleanup_callback(key, value)
            self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


def _cleanup_lifespan_manager(key: str, manager: ScopedMCPLifespanManager) -> None:
    """Cleanup callback for evicted lifespan managers."""
    logger.info(f"Cleaning up lifespan manager for corpus: {key}")
    # Schedule async cleanup in the event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.shutdown())
    except RuntimeError as e:
        # No event loop available - log and skip async cleanup
        # This can happen during interpreter shutdown or when called from non-async context
        logger.warning(
            f"Could not schedule cleanup for lifespan manager '{key}': {e}. "
            "Resources may not be fully released."
        )


def _cleanup_session_manager(key: str, manager: StreamableHTTPSessionManager) -> None:
    """Cleanup callback for evicted session managers."""
    logger.info(f"Cleaning up session manager for corpus: {key}")
    # StreamableHTTPSessionManager doesn't require explicit cleanup in stateless mode


# Caches for scoped managers with TTL (1 hour) and LRU eviction (max 100 entries)
_scoped_session_managers: TTLLRUCache = TTLLRUCache(
    maxsize=100, ttl_seconds=3600, cleanup_callback=_cleanup_session_manager
)
_scoped_lifespan_managers: TTLLRUCache = TTLLRUCache(
    maxsize=100, ttl_seconds=3600, cleanup_callback=_cleanup_lifespan_manager
)


class ScopedMCPLifespanManager:
    """
    Manages the lifecycle of a scoped MCP session manager.

    Handles proper startup and shutdown of async contexts.
    """

    def __init__(self, corpus_slug: str) -> None:
        self.corpus_slug = corpus_slug
        self._started = False
        self._run_context: AbstractAsyncContextManager[None] | None = None
        self._lock = asyncio.Lock()

    async def ensure_started(self) -> StreamableHTTPSessionManager:
        """
        Ensure the scoped session manager is running.

        Returns:
            The session manager instance for this corpus.
        """
        async with self._lock:
            if not self._started:
                manager = await get_scoped_session_manager(self.corpus_slug)
                self._run_context = manager.run()
                await self._run_context.__aenter__()
                self._started = True
                logger.info(
                    f"MCP Scoped StreamableHTTP session manager started for corpus: {self.corpus_slug}"
                )
            return await get_scoped_session_manager(self.corpus_slug)

    async def shutdown(self) -> None:
        """
        Shutdown the scoped session manager, properly closing async context.

        Called during cache eviction or server shutdown.
        """
        async with self._lock:
            if self._started and self._run_context:
                try:
                    await self._run_context.__aexit__(None, None, None)
                    logger.info(
                        f"MCP Scoped StreamableHTTP session manager stopped for corpus: {self.corpus_slug}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Error shutting down scoped session manager for {self.corpus_slug}: {e}"
                    )
                finally:
                    self._started = False
                    self._run_context = None


async def get_scoped_session_manager(corpus_slug: str) -> StreamableHTTPSessionManager:
    """
    Get or create a session manager for a corpus-scoped MCP endpoint.

    Uses TTL+LRU cache to prevent unbounded memory growth.
    """
    manager = await _scoped_session_managers.get(corpus_slug)
    if manager is None:
        scoped_server = create_scoped_mcp_server(corpus_slug)
        manager = StreamableHTTPSessionManager(
            app=scoped_server,
            event_store=None,
            json_response=False,
            stateless=True,
        )
        await _scoped_session_managers.set(corpus_slug, manager)
    return manager


async def get_scoped_lifespan_manager(corpus_slug: str) -> ScopedMCPLifespanManager:
    """
    Get or create a lifespan manager for a corpus-scoped MCP endpoint.

    Uses TTL+LRU cache to prevent unbounded memory growth.
    """
    manager = await _scoped_lifespan_managers.get(corpus_slug)
    if manager is None:
        manager = ScopedMCPLifespanManager(corpus_slug)
        await _scoped_lifespan_managers.set(corpus_slug, manager)
    return manager


async def validate_corpus_slug(
    corpus_slug: str, user: UserOrAnonymous | None = None
) -> bool:
    """
    Validate that a corpus slug exists and is accessible to the caller.

    Args:
        corpus_slug: The corpus slug to validate
        user: Optional authenticated user; None preserves anonymous behavior.

    Returns:
        True if the corpus exists and is visible to the caller, False otherwise
    """
    from django.contrib.auth.models import AnonymousUser

    from opencontractserver.corpuses.models import Corpus

    def _check() -> bool:
        effective_user = user or AnonymousUser()
        return (
            Corpus.objects.visible_to_user(effective_user)
            .filter(slug=corpus_slug)
            .exists()
        )

    return await sync_to_async(_check)()


# Session manager for stateless HTTP transport
# Stateless mode = no session handshake required, each request is independent
# This avoids the "Received request before initialization was complete" bug
# that affected the older SSE transport
session_manager: StreamableHTTPSessionManager | None = None


def get_session_manager() -> StreamableHTTPSessionManager:
    """Get or create the session manager instance."""
    global session_manager
    if session_manager is None:
        session_manager = StreamableHTTPSessionManager(
            app=mcp_server,
            event_store=None,  # No resumability needed for stateless
            json_response=False,  # Use SSE streaming for responses
            stateless=True,  # Key: each request is independent
        )
    return session_manager


class MCPLifespanManager:
    """
    Manages the MCP session manager lifecycle within Django's ASGI context.

    Since Django doesn't have a native lifespan protocol like Starlette,
    we manage the session manager's run() context lazily on first request.
    """

    def __init__(self) -> None:
        self._started = False
        self._run_context: AbstractAsyncContextManager[None] | None = None
        self._lock = asyncio.Lock()

    async def ensure_started(self) -> None:
        """Ensure the session manager is running."""
        async with self._lock:
            if not self._started:
                manager = get_session_manager()
                self._run_context = manager.run()
                await self._run_context.__aenter__()
                self._started = True
                logger.info("MCP StreamableHTTP session manager started")


# Global lifespan manager for Streamable HTTP
lifespan_manager = MCPLifespanManager()

# SSE transport for backward compatibility with older clients
# The SSE transport is deprecated but some clients still use it
sse_transport = SseServerTransport("/sse/messages/")


async def handle_sse_connection(request: Request) -> Response:
    """
    Handle SSE connection for deprecated SSE transport.

    This endpoint establishes an SSE stream and runs the MCP server
    to handle client requests sent via POST to /sse/messages/.
    """
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )
    # Return empty response after SSE stream closes
    return Response()


# Create Starlette app for SSE transport routes
sse_starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse_connection, methods=["GET"]),
        Mount("/sse/messages/", app=sse_transport.handle_post_message),
    ]
)


ASGIScope = MutableMapping[str, Any]
ASGIMessage = MutableMapping[str, Any]
ASGIReceive = Callable[[], Awaitable[ASGIMessage]]
ASGISend = Callable[[ASGIMessage], Awaitable[None]]
ASGIApp = Callable[[ASGIScope, ASGIReceive, ASGISend], Awaitable[None]]


def create_mcp_asgi_app() -> ASGIApp:
    """
    Create an ASGI application that handles MCP requests.

    Supports multiple transports and scoping modes:
    - Streamable HTTP at /mcp (recommended, stateless mode)
    - Corpus-scoped HTTP at /mcp/corpus/{corpus_slug}/ (scoped to single corpus)
    - SSE at /sse (deprecated, for backward compatibility)

    All requests are delegated to the appropriate transport handler.
    Telemetry context is set for each request to track client IP and transport.
    """
    # Regex to match corpus-scoped endpoints: /mcp/corpus/{slug}/ or /mcp/corpus/{slug}
    # Reuses URIParser.SLUG_PATTERN to ensure consistency
    corpus_path_pattern = re.compile(rf"^/mcp/corpus/({URIParser.SLUG_PATTERN})/?$")

    async def app(scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http":
            return

        # Store scope in ContextVar so tool handlers can access it
        # for per-tool rate limiting.  The token is saved so we can
        # reset it in the finally block, preventing stale scope data
        # from leaking into subsequent requests on the same task.
        _scope_token = _mcp_asgi_scope.set(scope)
        try:
            # Rate limit before JWT validation so invalid-token traffic still
            # consumes the same global MCP bucket as ordinary requests.
            is_limited, error_msg, retry_after = await check_mcp_rate_limit(scope)
            if is_limited:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"retry-after", str(retry_after).encode()],
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": json.dumps(
                            {
                                "error": error_msg,
                                "hint": "Please wait before making more requests",
                                "retry_after": retry_after,
                            }
                        ).encode(),
                    }
                )
                return

            # Resolve the per-request user up-front so we can use a single
            # _mcp_user.set() / .reset() pair.  Stacked sets are fragile —
            # adding another set between the original .set(None) and .set(user)
            # would silently break the reset chain.
            user_for_request: UserOrAnonymous | None = None
            token = _extract_bearer_token(scope)
            if token:
                try:
                    user_for_request = await sync_to_async(get_user_from_jwt_token)(
                        token
                    )
                    logger.info(
                        "MCP: authenticated user pk=%s",
                        getattr(user_for_request, "pk", None),
                    )
                except (JSONWebTokenExpired, JSONWebTokenError) as exc:
                    logger.warning(
                        "MCP: rejected invalid JWT (%s)", exc.__class__.__name__
                    )
                    www_authenticate = _build_www_authenticate_header(scope)
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 401,
                            "headers": [
                                [b"content-type", b"application/json"],
                                # RFC 6750 §3 + MCP 2025-06-18 Authorization §2.4:
                                # always include WWW-Authenticate on a 401 from a
                                # Bearer-protected resource so interactive clients
                                # can discover the authorization server.
                                [b"www-authenticate", www_authenticate],
                            ],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": json.dumps(
                                {"error": "Invalid or expired authentication token"}
                            ).encode(),
                        }
                    )
                    return

            _user_token = _mcp_user.set(user_for_request)
            try:
                await _handle_mcp_request(scope, receive, send)
            finally:
                _mcp_user.reset(_user_token)
        finally:
            _mcp_asgi_scope.reset(_scope_token)

    async def _handle_mcp_request(
        scope: ASGIScope, receive: ASGIReceive, send: ASGISend
    ) -> None:
        path = scope.get("path", "")

        # Check for corpus-scoped endpoint: /mcp/corpus/{corpus_slug}/
        corpus_match = corpus_path_pattern.match(path)
        if corpus_match:
            corpus_slug = corpus_match.group(1)

            # Set telemetry context for this request
            client_ip = get_client_ip_from_scope(scope)
            user_agent = get_user_agent_from_scope(scope)
            set_request_context(
                client_ip=client_ip,
                transport="streamable_http_scoped",
                user_agent=user_agent,
            )

            # Validate the corpus exists and is visible to this request's user.
            if not await validate_corpus_slug(corpus_slug, _mcp_user.get()):
                try:
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 404,
                            "headers": [[b"content-type", b"application/json"]],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": json.dumps(
                                {
                                    "error": f"Corpus '{corpus_slug}' not found or not accessible",
                                    "hint": "Use /mcp/corpus/{corpus_slug}/ with a valid accessible corpus slug",
                                }
                            ).encode(),
                        }
                    )
                finally:
                    clear_request_context()
                return

            # Ensure scoped session manager is running and get the manager
            scoped_lifespan = await get_scoped_lifespan_manager(corpus_slug)
            scoped_manager = await scoped_lifespan.ensure_started()

            try:
                await scoped_manager.handle_request(scope, receive, send)
                await arecord_mcp_request(
                    f"/mcp/corpus/{corpus_slug}",
                    method=scope.get("method", "POST"),
                    success=True,
                )
            except Exception as e:
                logger.error(f"MCP Scoped Streamable HTTP request error: {e}")
                await arecord_mcp_request(
                    f"/mcp/corpus/{corpus_slug}",
                    method=scope.get("method", "POST"),
                    success=False,
                    error_type=type(e).__name__,
                )
                # Try to send error response; if this fails (client disconnect), log it
                try:
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 500,
                            "headers": [[b"content-type", b"application/json"]],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": json.dumps({"error": str(e)}).encode(),
                        }
                    )
                except Exception as send_error:
                    logger.warning(
                        f"Failed to send error response for scoped MCP request: {send_error}"
                    )
            finally:
                clear_request_context()
            return

        # Handle global Streamable HTTP endpoint (recommended)
        if path == "/mcp/" or path == "/mcp":
            # Set telemetry context for this request
            client_ip = get_client_ip_from_scope(scope)
            user_agent = get_user_agent_from_scope(scope)
            set_request_context(
                client_ip=client_ip,
                transport="streamable_http",
                user_agent=user_agent,
            )

            # Ensure session manager is running
            await lifespan_manager.ensure_started()

            manager = get_session_manager()
            try:
                await manager.handle_request(scope, receive, send)
                # Record successful request telemetry
                await arecord_mcp_request(
                    "/mcp", method=scope.get("method", "POST"), success=True
                )
            except Exception as e:
                logger.error(f"MCP Streamable HTTP request error: {e}")
                # Record error telemetry before clearing context
                await arecord_mcp_request(
                    "/mcp",
                    method=scope.get("method", "POST"),
                    success=False,
                    error_type=type(e).__name__,
                )
                # Try to send error response; if this fails (client disconnect), log it
                try:
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 500,
                            "headers": [[b"content-type", b"application/json"]],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": json.dumps({"error": str(e)}).encode(),
                        }
                    )
                except Exception as send_error:
                    logger.warning(
                        f"Failed to send error response for MCP request: {send_error}"
                    )
            finally:
                clear_request_context()

        # Handle deprecated SSE transport for backward compatibility
        elif path == "/sse" or path.startswith("/sse/"):
            # Set telemetry context for this request
            client_ip = get_client_ip_from_scope(scope)
            user_agent = get_user_agent_from_scope(scope)
            set_request_context(
                client_ip=client_ip,
                transport="sse",
                user_agent=user_agent,
            )

            try:
                await sse_starlette_app(scope, receive, send)
                # Record successful request telemetry
                await arecord_mcp_request(
                    "/sse", method=scope.get("method", "GET"), success=True
                )
            except Exception as e:
                logger.error(f"MCP SSE request error: {e}")
                # Record error telemetry before clearing context
                await arecord_mcp_request(
                    "/sse",
                    method=scope.get("method", "GET"),
                    success=False,
                    error_type=type(e).__name__,
                )
                # Try to send error response; if this fails (client disconnect), log it
                try:
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 500,
                            "headers": [[b"content-type", b"application/json"]],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": json.dumps({"error": str(e)}).encode(),
                        }
                    )
                except Exception as send_error:
                    logger.warning(
                        f"Failed to send error response for SSE request: {send_error}"
                    )
            finally:
                clear_request_context()

        else:
            # Return 404 with helpful information about available endpoints
            try:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [[b"content-type", b"application/json"]],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": json.dumps(
                            {
                                "error": "Not found",
                                "endpoints": {
                                    "streamable_http": {
                                        "path": "/mcp",
                                        "methods": ["POST", "GET"],
                                        "description": "MCP Streamable HTTP endpoint (recommended)",
                                    },
                                    "corpus_scoped": {
                                        "path": "/mcp/corpus/{corpus_slug}/",
                                        "methods": ["POST", "GET"],
                                        "description": "Corpus-scoped MCP endpoint (shareable link for single corpus)",
                                    },
                                    "sse": {
                                        "path": "/sse",
                                        "methods": ["GET"],
                                        "description": "MCP SSE endpoint (deprecated, for backward compatibility)",
                                    },
                                },
                            }
                        ).encode(),
                    }
                )
            finally:
                # Ensure context is cleared even for 404 responses
                clear_request_context()

    return app


# ASGI application for mounting in Django
mcp_asgi_app = create_mcp_asgi_app()


async def main() -> None:
    """Run MCP server with stdio transport (for CLI usage)."""
    # Set telemetry context for stdio transport (no client IP available)
    set_request_context(client_ip=None, transport="stdio")
    try:
        async with stdio_server() as streams:
            await mcp_server.run(
                streams[0],  # read_stream
                streams[1],  # write_stream
                mcp_server.create_initialization_options(),
            )
    finally:
        clear_request_context()


if __name__ == "__main__":
    # Setup Django before running
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

    import django

    django.setup()

    asyncio.run(main())
