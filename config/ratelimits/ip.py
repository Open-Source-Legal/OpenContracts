"""
IP address extraction utilities for rate limiting.

This module provides functions to extract client IP addresses from both
Django HTTP requests and ASGI WebSocket scopes, handling proxy headers
like X-Forwarded-For.
"""


def get_client_ip_from_request(request) -> str:
    """
    Get the client's IP address from a Django HTTP request.

    Handles X-Forwarded-For header for requests behind proxies (e.g., Traefik).

    Args:
        request: Django HttpRequest object

    Returns:
        The client's IP address as a string
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return x_forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "unknown")


def get_client_ip_from_scope(scope: dict) -> str:
    """
    Get the client's IP address from an ASGI WebSocket scope.

    Handles X-Forwarded-For header for requests behind proxies (e.g., Traefik).

    Args:
        scope: The ASGI scope dictionary

    Returns:
        The client's IP address as a string
    """
    # Check headers for X-Forwarded-For (common when behind proxies)
    headers = dict(scope.get("headers", []))

    # Headers are byte strings in ASGI
    x_forwarded_for = headers.get(b"x-forwarded-for", b"").decode("utf-8")
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return x_forwarded_for.split(",")[0].strip()

    # Fall back to client address from scope
    client = scope.get("client")
    if client:
        return client[0]  # (host, port) tuple

    return "unknown"
