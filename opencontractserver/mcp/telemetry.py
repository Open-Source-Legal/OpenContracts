"""
MCP Telemetry module.

Provides telemetry tracking for MCP (Model Context Protocol) tool and resource usage.
Tracks usage statistics without capturing query content or outputs for privacy.

Privacy notes:
- IP addresses are hashed with a secret salt before being stored
- Raw IP addresses are never sent to PostHog or stored
- Only the truncated hash is used as a client identifier
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Generator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from config.telemetry import arecord_event, record_event

logger = logging.getLogger(__name__)

# Length of the truncated IP hash (16 hex chars = 64 bits of entropy)
# Sufficient for unique client identification without storing full hash
IP_HASH_LENGTH = 16

# Maximum length for stored User-Agent strings.  The User-Agent header is
# attacker-controlled input; without a cap a malicious client could send
# multi-megabyte values that get stored in context dicts and forwarded to
# telemetry backends.  512 characters is generous for any real-world UA.
MAX_USER_AGENT_LENGTH = 512

# Context variable to store request metadata (client IP, transport type)
# This allows the telemetry functions to access request context without
# needing to pass it through all function calls
_mcp_request_context: ContextVar[dict[str, Any]] = ContextVar(
    "mcp_request_context", default={}
)


def set_request_context(
    client_ip: str | None = None,
    transport: str = "unknown",
    user_agent: str | None = None,
) -> None:
    """
    Set the request context for MCP telemetry.

    Should be called at the start of each MCP request handler to capture
    request metadata that will be included in telemetry events.

    Args:
        client_ip: The client's IP address (will be hashed for privacy)
        transport: The transport type (e.g., 'streamable_http', 'sse', 'stdio')
        user_agent: The User-Agent header value identifying the MCP client/agent
    """
    # Truncate user_agent to prevent oversized attacker-controlled input from
    # being stored in context dicts and forwarded to telemetry backends.
    truncated_ua = user_agent[:MAX_USER_AGENT_LENGTH] if user_agent else None

    _mcp_request_context.set(
        {
            "client_ip_hash": _hash_ip(client_ip) if client_ip else None,
            "transport": transport,
            "user_agent": truncated_ua,
        }
    )


def clear_request_context() -> None:
    """Clear the request context after handling a request."""
    _mcp_request_context.set({})


@contextmanager
def isolated_telemetry_context() -> Generator[None]:
    """
    Context manager that ensures telemetry context is isolated.

    Clears context on entry and exit, guaranteeing cleanup even if
    the test crashes. Use this in tests to prevent context leakage
    between test cases.

    Example:
        def test_something(self):
            with isolated_telemetry_context():
                set_request_context(client_ip="1.2.3.4", transport="test")
                # test code here
            # context is automatically cleared
    """
    clear_request_context()
    try:
        yield
    finally:
        clear_request_context()


def _hash_ip(ip: str) -> str:
    """
    Hash an IP address for privacy using a secret salt.

    Uses SHA-256 with a secret salt to create a one-way hash that allows
    tracking unique clients without storing actual IP addresses. The salt
    prevents rainbow table attacks (IPv4 only has ~4 billion addresses).

    Args:
        ip: The IP address to hash

    Returns:
        First IP_HASH_LENGTH characters of the hex-encoded SHA-256 hash
    """
    from django.conf import settings

    salt = getattr(settings, "TELEMETRY_IP_SALT", "default-salt")
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()[:IP_HASH_LENGTH]


def _get_request_context() -> dict[str, Any]:
    """Get the current request context."""
    return _mcp_request_context.get()


def _build_context_properties() -> dict[str, Any]:
    """Build the common properties dict from the current request context.

    Includes transport, hashed client IP, and user agent when available.
    """
    context = _get_request_context()
    properties: dict[str, Any] = {
        "transport": context.get("transport", "unknown"),
    }
    if context.get("client_ip_hash"):
        properties["client_ip_hash"] = context["client_ip_hash"]
    if context.get("user_agent"):
        properties["user_agent"] = context["user_agent"]
    return properties


def record_mcp_tool_call(
    tool_name: str,
    success: bool = True,
    error_type: str | None = None,
    corpus_slug: str | None = None,
    document_slug: str | None = None,
) -> bool:
    """
    Record a telemetry event for an MCP tool call.

    Args:
        tool_name: Name of the tool that was called
        success: Whether the tool call succeeded
        error_type: Type of error if the call failed (e.g., 'ValueError', 'PermissionError')
        corpus_slug: Slug of the corpus being accessed (no user-identifying info)
        document_slug: Slug of the document being accessed (no user-identifying info)

    Returns:
        True if event was successfully queued, False otherwise
    """
    properties = _build_context_properties()
    properties["tool_name"] = tool_name
    properties["success"] = success

    if not success and error_type:
        properties["error_type"] = error_type
    if corpus_slug:
        properties["corpus_slug"] = corpus_slug
    if document_slug:
        properties["document_slug"] = document_slug

    return record_event("mcp_tool_call", properties)


def record_mcp_resource_read(
    resource_type: str,
    success: bool = True,
    error_type: str | None = None,
    corpus_slug: str | None = None,
    document_slug: str | None = None,
) -> bool:
    """
    Record a telemetry event for an MCP resource read.

    Args:
        resource_type: Type of resource that was read (e.g., 'corpus', 'document')
        success: Whether the resource read succeeded
        error_type: Type of error if the read failed
        corpus_slug: Slug of the corpus being accessed (no user-identifying info)
        document_slug: Slug of the document being accessed (no user-identifying info)

    Returns:
        True if event was successfully queued, False otherwise
    """
    properties = _build_context_properties()
    properties["resource_type"] = resource_type
    properties["success"] = success

    if not success and error_type:
        properties["error_type"] = error_type
    if corpus_slug:
        properties["corpus_slug"] = corpus_slug
    if document_slug:
        properties["document_slug"] = document_slug

    return record_event("mcp_resource_read", properties)


def record_mcp_request(
    endpoint: str,
    method: str = "POST",
    success: bool = True,
    error_type: str | None = None,
) -> bool:
    """
    Record a telemetry event for an MCP endpoint request.

    This tracks overall MCP traffic without tool/resource specifics.
    Should be called for both successful and failed requests to enable
    error rate calculations.

    Args:
        endpoint: The MCP endpoint path (e.g., '/mcp', '/sse')
        method: HTTP method used
        success: Whether the request succeeded
        error_type: Type of error if the request failed

    Returns:
        True if event was successfully queued, False otherwise
    """
    properties = _build_context_properties()
    properties["endpoint"] = endpoint
    properties["method"] = method
    properties["success"] = success

    if not success and error_type:
        properties["error_type"] = error_type

    return record_event("mcp_request", properties)


async def arecord_mcp_tool_call(
    tool_name: str,
    success: bool = True,
    error_type: str | None = None,
    corpus_slug: str | None = None,
    document_slug: str | None = None,
) -> bool:
    """
    Async version of ``record_mcp_tool_call``.

    Safe to call from ASGI / async handlers. Uses ``arecord_event`` to
    avoid synchronous ORM calls on the event loop.
    """
    properties = _build_context_properties()
    properties["tool_name"] = tool_name
    properties["success"] = success

    if not success and error_type:
        properties["error_type"] = error_type
    if corpus_slug:
        properties["corpus_slug"] = corpus_slug
    if document_slug:
        properties["document_slug"] = document_slug

    return await arecord_event("mcp_tool_call", properties)


async def arecord_mcp_resource_read(
    resource_type: str,
    success: bool = True,
    error_type: str | None = None,
    corpus_slug: str | None = None,
    document_slug: str | None = None,
) -> bool:
    """
    Async version of ``record_mcp_resource_read``.

    Safe to call from ASGI / async handlers. Uses ``arecord_event`` to
    avoid synchronous ORM calls on the event loop.
    """
    properties = _build_context_properties()
    properties["resource_type"] = resource_type
    properties["success"] = success

    if not success and error_type:
        properties["error_type"] = error_type
    if corpus_slug:
        properties["corpus_slug"] = corpus_slug
    if document_slug:
        properties["document_slug"] = document_slug

    return await arecord_event("mcp_resource_read", properties)


async def arecord_mcp_request(
    endpoint: str,
    method: str = "POST",
    success: bool = True,
    error_type: str | None = None,
) -> bool:
    """
    Async version of ``record_mcp_request``.

    Safe to call from ASGI / async handlers. Uses ``arecord_event`` to
    avoid synchronous ORM calls on the event loop.
    """
    properties = _build_context_properties()
    properties["endpoint"] = endpoint
    properties["method"] = method
    properties["success"] = success

    if not success and error_type:
        properties["error_type"] = error_type

    return await arecord_event("mcp_request", properties)


def get_user_agent_from_scope(scope: MutableMapping[str, Any]) -> str | None:
    """Extract User-Agent header from an ASGI scope.

    MCP clients and AI agents typically identify themselves via User-Agent
    (e.g., ``Claude-Code/1.0``, ``cursor/0.45``).

    Returns ``None`` when no User-Agent is present.  The result is truncated
    to :data:`MAX_USER_AGENT_LENGTH` characters to bound attacker-controlled
    input.

    .. note::
       Converting the ASGI header list to a ``dict`` means that if a client
       sends duplicate ``user-agent`` headers only the last value is kept.
       This is acceptable because RFC 9110 §5.5 specifies a single
       User-Agent value, so duplicates indicate a misbehaving client.
    """
    headers = dict(scope.get("headers", []))
    ua = headers.get(b"user-agent")
    if ua:
        value = ua.decode("utf-8", errors="replace").strip()
        return value[:MAX_USER_AGENT_LENGTH] if value else None
    return None


def get_claimed_client_ip_from_scope(scope: dict[str, Any]) -> str | None:
    """Extract client IP address from an ASGI scope for telemetry purposes.

    Unlike the rate-limiting IP extractor (which picks the rightmost trusted
    proxy entry for anti-spoofing), this function returns the **leftmost**
    ``X-Forwarded-For`` entry -- the claimed original client IP.  For
    telemetry (hashed, privacy-preserving) this is the right choice: we want
    to identify the true origin, even if it could be spoofed.

    Returns ``None`` when no IP can be determined.

    .. note::
       Converting the ASGI header list to a ``dict`` drops duplicate header
       values (only the last value for a given name is kept).  For the
       headers inspected here (``x-forwarded-for``, ``x-real-ip``) this is
       safe: proxies append to a single ``X-Forwarded-For`` value rather
       than adding extra headers, and ``X-Real-IP`` is always singular.
    """
    headers = dict(scope.get("headers", []))

    # X-Forwarded-For: pick leftmost (original client claim)
    xff = headers.get(b"x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.decode().split(",") if p.strip()]
        if parts:
            return parts[0]

    # X-Real-IP
    x_real_ip = headers.get(b"x-real-ip")
    if x_real_ip:
        return x_real_ip.decode().strip()

    # Direct client connection
    client = scope.get("client")
    if client and len(client) >= 1:
        return client[0]

    return None
