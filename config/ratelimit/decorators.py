"""
Protocol-specific rate limiting adapters.

Thin wrappers around the shared engine for each protocol:
- ``graphql_ratelimit`` / ``graphql_ratelimit_dynamic`` — GraphQL resolvers
- ``check_ws_rate_limit`` — WebSocket consumers
- ``check_mcp_rate_limit`` — MCP ASGI application
- ``view_ratelimit`` — Standard Django views
"""

from __future__ import annotations

import functools
import json
import logging
import time
from collections.abc import MutableMapping
from typing import Any, Callable

from django.conf import settings
from django.http import HttpResponse
from graphql import GraphQLError

from config.ratelimit.engine import (
    PERIOD_NAMES,
    ais_rate_limited,
    is_rate_limited,
    parse_rate,
)
from config.ratelimit.keys import (
    get_client_ip_from_http,
    get_client_ip_from_scope,
    get_rate_limit_key,
    is_authenticated,
)
from config.ratelimit.rates import RateLimits, get_tier_adjusted_rate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Protocol-specific error classes
# ---------------------------------------------------------------------------


class RateLimitExceeded(GraphQLError):
    """Custom exception for rate limit exceeded errors in GraphQL."""

    def __init__(self, message: str = "Rate limit exceeded. Please try again later."):
        super().__init__(message)


class MCPRateLimitError(Exception):
    """Rate limit exceeded for an MCP tool call.

    A named exception (instead of generic ``ValueError``) so callers and
    tests can catch rate-limit rejections specifically.
    """

    def __init__(self, message: str = "Rate limit exceeded. Please try again later."):
        super().__init__(message)


# ---------------------------------------------------------------------------
#  Error message formatting
# ---------------------------------------------------------------------------


def _format_exceeded_message(rate: str) -> str:
    """Build a human-readable rate limit exceeded message."""
    try:
        count, _ = parse_rate(rate)
        period_key = rate.split("/")[1]
        period_name = PERIOD_NAMES.get(period_key, "period")
        return (
            f"Limit exceeded: Max {count} requests per {period_name}. "
            f"Please try again later."
        )
    except (ValueError, IndexError):
        return "Rate limit exceeded. Please try again later."


# ---------------------------------------------------------------------------
#  GraphQL decorators
# ---------------------------------------------------------------------------


def _graphql_rate_limit_check(
    func_name: str,
    root: Any,
    info: Any,
    rate: str,
    key: str | Callable | None,
    block: bool,
    group: str | None,
    **kwargs: Any,
) -> bool | None:
    """Shared pre-check logic for GraphQL rate limiting decorators.

    Returns ``None`` if the request should be let through without rate limiting
    (missing context, disabled, anonymous with user-only key).
    Returns ``True`` if rate limited and ``block=True`` (raises RateLimitExceeded).
    Returns ``False`` if the request passed the rate limit check.
    """
    if not info or not hasattr(info, "context"):
        if not getattr(settings, "TESTING", False):
            logger.warning(
                "Rate limiting skipped for %s: "
                "info object is None or missing context.",
                func_name,
            )
        return None

    request = info.context

    if not request or not hasattr(request, "META"):
        if not getattr(settings, "TESTING", False):
            logger.warning(
                "Rate limiting skipped for %s: "
                "context is not a Django request object (type=%s).",
                func_name,
                type(request).__name__,
            )
        return None

    if getattr(settings, "RATELIMIT_DISABLE", False):
        return None

    limit_key = _resolve_graphql_key(key, root, info, request, block, **kwargs)
    if limit_key is None:
        return None

    grp = group or func_name
    is_limited = is_rate_limited(grp, limit_key, rate)

    if is_limited and block:
        logger.warning(
            "Rate limit exceeded for %s — Key: %s, Rate: %s",
            func_name,
            limit_key,
            rate,
        )
        raise RateLimitExceeded(_format_exceeded_message(rate))

    # Expose throttle state on the request so resolvers using block=False
    # can detect when the limit was exceeded (analogous to view_ratelimit
    # setting request.limited).
    if hasattr(request, "META"):
        request.limited = is_limited

    return is_limited


def graphql_ratelimit(
    key: str | Callable | None = None,
    rate: str = "10/m",
    block: bool = True,
    group: str | None = None,
):
    """Rate limit decorator for GraphQL resolvers.

    .. note::
        The ``method`` parameter from ``django_ratelimit`` is intentionally
        not supported.  GraphQL requests are always ``POST`` and method
        filtering is meaningless in this context.  No existing callers
        passed ``method=`` at the time of migration (verified via codebase
        grep).

    Args:
        key: Key strategy — ``None``/``"user_or_ip"`` (default), ``"ip"``,
             ``"user"``, or a custom callable ``(root, info, **kwargs) -> str``.
        rate: Rate limit string (e.g. ``"10/m"``).
        block: Whether to raise ``RateLimitExceeded`` when the limit is hit.
        group: Cache group name (defaults to the decorated function's name).
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(root, info, *args, **kwargs):
            # Return value intentionally discarded: when block=True the
            # helper raises RateLimitExceeded; when block=False it sets
            # request.limited=True and the resolver runs regardless,
            # matching the old django-ratelimit behavior.
            _graphql_rate_limit_check(
                func.__name__, root, info, rate, key, block, group, **kwargs
            )
            return func(root, info, *args, **kwargs)

        return wrapper

    return decorator


def graphql_ratelimit_dynamic(
    get_rate: Callable[[Any, Any], str],
    key: str | Callable | None = None,
    block: bool = True,
    group: str | None = None,
):
    """Dynamic rate limit decorator that determines the rate from the user tier.

    Args:
        get_rate: Callable taking ``(root, info)`` and returning a rate string.
        key: Key strategy (same options as ``graphql_ratelimit``).
        block: Whether to raise on limit exceeded.
        group: Cache group name.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(root, info, *args, **kwargs):
            resolved_rate = get_rate(root, info)
            # Return value intentionally discarded: when block=True the
            # helper raises RateLimitExceeded; when block=False it sets
            # request.limited=True and the resolver runs regardless,
            # matching the old django-ratelimit behavior.
            _graphql_rate_limit_check(
                func.__name__, root, info, resolved_rate, key, block, group, **kwargs
            )
            return func(root, info, *args, **kwargs)

        return wrapper

    return decorator


def _resolve_graphql_key(key, root, info, request, block: bool, **kwargs) -> str | None:
    """Resolve the rate limit key for a GraphQL request.

    Returns ``None`` when the ``"user"`` strategy is used with an anonymous
    user and ``block=False`` (indicating the request should be let through).
    """
    if key is None or key == "user_or_ip":
        ip = get_client_ip_from_http(request)
        return get_rate_limit_key(user=request.user, ip=ip)

    if key == "ip":
        ip = get_client_ip_from_http(request)
        return get_rate_limit_key(ip=ip, strategy="ip")

    if key == "user":
        if not request.user or not is_authenticated(request.user):
            if block:
                raise GraphQLError("Authentication required for this operation")
            return None
        return get_rate_limit_key(user=request.user, strategy="user")

    if callable(key):
        return key(root, info, **kwargs)

    # Static key string
    return str(key)


# ---------------------------------------------------------------------------
#  WebSocket adapter
# ---------------------------------------------------------------------------


async def check_ws_rate_limit(
    consumer: Any,
    operation_type: str,
    group_suffix: str | None = None,
    send_message: bool = True,
) -> bool:
    """Check rate limit for a WebSocket consumer.

    Sends a ``RATE_LIMITED`` error message to the client if the limit is
    exceeded (unless ``send_message=False``).  Does **not** close the
    connection — the caller decides whether to close or just skip the
    operation.

    .. note::
        The rate limit budget is **shared** across all concurrent
        WebSocket connections for the same user (or IP for anonymous
        users).  For example, if a user has two browser tabs each with
        an open WebSocket, operations from both tabs count against the
        same counter.  This is intentional — it prevents circumventing
        limits by opening multiple connections.

    Args:
        consumer: A Django Channels ``AsyncWebsocketConsumer`` instance.
        operation_type: ``RateLimits`` attribute name (e.g. ``"AI_QUERY"``).
        group_suffix: Optional override for the cache group suffix.
                      Defaults to ``operation_type``.
        send_message: Whether to send a JSON error frame to the client.
                      Set to ``False`` for connection-phase checks where
                      the connection will be closed immediately and the
                      client won't see the message.

    Returns:
        ``True`` if rate limited (caller should abort processing),
        ``False`` if the request is allowed.
    """
    user = consumer.scope.get("user")
    ip = get_client_ip_from_scope(consumer.scope)
    limit_key = get_rate_limit_key(user=user, ip=ip)

    try:
        base_rate = getattr(RateLimits, operation_type)
    except AttributeError:
        valid = [
            attr
            for attr in dir(RateLimits)
            if attr.isupper() and not attr.startswith("_")
        ]
        raise ValueError(
            f"Unknown rate limit category {operation_type!r}. "
            f"Valid categories: {', '.join(sorted(valid))}"
        )
    rate = get_tier_adjusted_rate(user, base_rate)

    grp = f"ws:{group_suffix or operation_type}"

    is_limited = await ais_rate_limited(grp, limit_key, rate)

    if is_limited:
        if send_message:
            count: int | str
            try:
                count, period_seconds = parse_rate(rate)
                period_key = rate.split("/")[1]
                period_name = PERIOD_NAMES.get(period_key, "period")
                # Remaining seconds in the current window (not the full period)
                retry_after = period_seconds - (int(time.time()) % period_seconds)
            except (ValueError, IndexError):
                count, period_name, retry_after = "?", "period", 60

            await consumer.send(
                text_data=json.dumps(
                    {
                        "type": "RATE_LIMITED",
                        "error": (
                            f"Rate limit exceeded. "
                            f"Max {count} requests per {period_name}."
                        ),
                        "retry_after": retry_after,
                    }
                )
            )
        logger.warning(
            "WS rate limit exceeded: %s for key=%s, rate=%s",
            operation_type,
            limit_key,
            rate,
        )
        return True

    return False


# ---------------------------------------------------------------------------
#  MCP adapter
# ---------------------------------------------------------------------------


# Maps MCP tool names to existing rate limit categories.
# NOTE: Keys must be kept in sync with TOOL_HANDLERS in opencontractserver/mcp/server.py
# and the scoped tool definitions in opencontractserver/mcp/tools.py.
MCP_TOOL_RATE_MAP: dict[str, str] = {
    "list_public_corpuses": "READ_LIGHT",
    "list_documents": "READ_MEDIUM",
    "get_document_text": "READ_MEDIUM",
    "list_annotations": "READ_MEDIUM",
    "search_corpus": "READ_HEAVY",
    "list_threads": "READ_MEDIUM",
    "get_thread_messages": "READ_MEDIUM",
    "get_corpus_info": "READ_LIGHT",
}


async def check_mcp_rate_limit(
    scope: MutableMapping[str, Any],
    tool_name: str | None = None,
    *,
    skip_global: bool = False,
) -> tuple[bool, str, int]:
    """Check MCP rate limits: global cap + optional per-tool limit.

    MCP is always anonymous, so no tier adjustment is applied.
    # TODO: if MCP gains auth, pass user to get_tier_adjusted_rate here

    Args:
        scope: ASGI scope dictionary (used for IP extraction).
        tool_name: Optional MCP tool name for per-tool rate limiting.
        skip_global: If ``True``, skip the global cap check.  Used by
            tool handlers that are called after the ASGI app has already
            performed the global check, avoiding double-incrementing the
            global counter.

    Returns:
        Tuple of ``(is_limited, error_message, retry_after)``.  When
        ``is_limited`` is ``False``, ``error_message`` is an empty string
        and ``retry_after`` is ``0``.
    """
    ip = get_client_ip_from_scope(scope)
    limit_key = f"ip:{ip}"

    # 1. Global cap (skipped when called from tool handlers that already
    #    passed through the ASGI-level global check).
    if not skip_global:
        global_rate = RateLimits.MCP_GLOBAL
        if await ais_rate_limited("mcp:global", limit_key, global_rate):
            retry_after = _compute_retry_after(global_rate)
            return (
                True,
                "Rate limit exceeded. Please wait before making more requests.",
                retry_after,
            )

    # 2. Per-tool limit
    if tool_name and tool_name in MCP_TOOL_RATE_MAP:
        category = MCP_TOOL_RATE_MAP[tool_name]
        tool_rate = getattr(RateLimits, category)
        if await ais_rate_limited(f"mcp:tool:{tool_name}", limit_key, tool_rate):
            retry_after = _compute_retry_after(tool_rate)
            return True, f"Rate limit exceeded for {tool_name}.", retry_after

    return False, "", 0


def _compute_retry_after(rate: str) -> int:
    """Compute remaining seconds in the current rate-limit window.

    Returns the number of seconds until the current fixed-window resets,
    which is the appropriate ``Retry-After`` value for 429 responses.

    Falls back to ``60`` if the rate string cannot be parsed.
    """
    try:
        _, period_seconds = parse_rate(rate)
        return period_seconds - (int(time.time()) % period_seconds)
    except (ValueError, IndexError, ZeroDivisionError):
        return 60


# ---------------------------------------------------------------------------
#  Django view decorator
# ---------------------------------------------------------------------------


def view_ratelimit(
    key: Callable[[str, Any], str] | None = None,
    rate: str = "10/m",
    block: bool = False,
    group: str | None = None,
):
    """Rate limit decorator for standard Django views.

    Drop-in replacement for ``django_ratelimit.decorators.ratelimit``.
    Sets ``request.limited = True`` when the limit is exceeded (compatible
    with ``block=False`` usage pattern in admin auth views).

    .. note::
        Unlike the old ``django_ratelimit`` decorator, this version does
        **not** support string key specifications (e.g. ``"ip"``,
        ``"user"``, ``"header:X-Api-Key"``).  Pass a **callable**
        ``(group, request) -> str`` for custom keying, or ``None`` for
        the default IP-based key.

    Args:
        key: Key function ``(group, request) -> str``, or ``None`` for
             IP-based keying.  String key specs are **not** supported
             (a ``ValueError`` will be raised).
        rate: Rate limit string (e.g. ``"5/m"``).
        block: If ``True``, return an HTTP 429 response automatically.
        group: Cache group name (defaults to the decorated function's name).
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(request_or_self, *args, **kwargs):
            # Support both function views and method views (e.g. View.get)
            if hasattr(request_or_self, "META"):
                request = request_or_self
            elif args and hasattr(args[0], "META"):
                request = args[0]
            else:
                # Can't determine request — skip rate limiting
                logger.warning(
                    "view_ratelimit: could not locate request object in "
                    "arguments for %s, skipping rate limit",
                    func.__name__,
                )
                return func(request_or_self, *args, **kwargs)

            if getattr(settings, "RATELIMIT_DISABLE", False):
                request.limited = False
                return func(request_or_self, *args, **kwargs)

            # Resolve key
            grp = group or func.__name__
            if callable(key):
                limit_key = key(grp, request)
            elif key is not None:
                raise ValueError(
                    f"view_ratelimit 'key' must be a callable or None, "
                    f"got {type(key).__name__}: {key!r}. Use a callable "
                    f"(group, request) -> str for custom keying."
                )
            else:
                limit_key = f"ip:{get_client_ip_from_http(request)}"

            is_limited = is_rate_limited(grp, limit_key, rate)
            request.limited = is_limited

            if is_limited and block:
                # Compute Retry-After from remaining seconds in the current
                # rate-limit window (RFC 6585).
                try:
                    _, period_seconds = parse_rate(rate)
                    retry_after = period_seconds - (int(time.time()) % period_seconds)
                except (ValueError, ZeroDivisionError):
                    retry_after = 60

                response = HttpResponse(
                    "Too many requests. Please try again later.",
                    status=429,
                    content_type="text/plain",
                )
                response["Retry-After"] = str(retry_after)
                return response

            return func(request_or_self, *args, **kwargs)

        return wrapper

    return decorator
