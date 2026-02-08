"""
IP address extraction utilities for rate limiting.

Handles proxy headers (X-Forwarded-For) for both Django HTTP requests
and ASGI WebSocket scopes.
"""


def get_client_ip_from_request(request) -> str:
    """
    Get the client's IP from a Django HTTP request.

    Handles X-Forwarded-For for requests behind proxies (e.g. Traefik).
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "unknown")


def get_client_ip_from_scope(scope: dict) -> str:
    """
    Get the client's IP from an ASGI WebSocket scope.

    Handles X-Forwarded-For for requests behind proxies (e.g. Traefik).
    """
    headers = dict(scope.get("headers", []))

    # ASGI headers are byte strings
    x_forwarded_for = headers.get(b"x-forwarded-for", b"").decode("utf-8")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    client = scope.get("client")
    if client:
        return client[0]  # (host, port) tuple

    return "unknown"
