"""
Unified identity resolution for rate limiting.

Provides IP extraction from three context types (Django ``HttpRequest``,
ASGI scope for WebSocket, ASGI scope for MCP) and a unified key builder
that maps user/IP into a cache key string.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import MutableMapping
from typing import Any

from config.ratelimit.engine import UNKNOWN_IP

logger = logging.getLogger(__name__)


def _mask_ipv6(ip_str: str) -> str:
    """Normalise an IPv6 address to its subnet prefix for rate limiting.

    Groups IPv6 addresses by ``RATELIMIT_IPV6_MASK`` (default ``/64``) so
    that clients rotating through addresses within the same subnet share a
    single rate-limit counter.  IPv4 addresses are returned unchanged.

    Args:
        ip_str: Raw IP address string.

    Returns:
        The masked IPv6 network address, or the original string for IPv4
        or unparseable values.
    """
    from django.conf import settings

    mask = getattr(settings, "RATELIMIT_IPV6_MASK", 64)
    try:
        addr = ipaddress.ip_address(ip_str)
        if isinstance(addr, ipaddress.IPv6Address):
            network = ipaddress.IPv6Network(f"{ip_str}/{mask}", strict=False)
            return str(network.network_address)
    except ValueError:
        pass
    return ip_str


# ---------------------------------------------------------------------------
#  IP extraction — one function per request context type
# ---------------------------------------------------------------------------


def _pick_xff_ip(xff_value: str) -> str:
    """Select the trusted IP from an ``X-Forwarded-For`` header value.

    Returns the entry at position ``-RATELIMIT_PROXIES_COUNT`` from the
    right (the IP appended by the Nth trusted proxy).  The default is
    ``1`` (rightmost entry = single proxy such as Traefik/nginx).

    Args:
        xff_value: The raw ``X-Forwarded-For`` header value (comma-separated IPs).

    Returns:
        The selected IP string, or :data:`UNKNOWN_IP` if the header is empty.

    Raises:
        ValueError: If ``RATELIMIT_PROXIES_COUNT`` is ``<= 0``.  Callers
            must check ``proxies_count > 0`` before calling this function;
            when ``proxies_count == 0`` the ``X-Forwarded-For`` header
            should be ignored entirely (app receives connections directly
            and XFF is client-controlled).
    """
    from django.conf import settings

    proxies_count = getattr(settings, "RATELIMIT_PROXIES_COUNT", 1)
    if proxies_count <= 0:
        raise ValueError(
            f"_pick_xff_ip called with RATELIMIT_PROXIES_COUNT={proxies_count}. "
            f"When proxies_count <= 0, X-Forwarded-For should not be consulted "
            f"because it is entirely client-controlled."
        )

    parts = [p.strip() for p in xff_value.split(",") if p.strip()]
    if not parts:
        return UNKNOWN_IP

    # Trust the Nth entry from the right (1 = rightmost = single proxy)
    index = -proxies_count
    try:
        return parts[index]
    except IndexError:
        # Fewer entries than proxies_count — use leftmost as safe fallback
        logger.warning(
            "RATELIMIT_PROXIES_COUNT=%d exceeds number of X-Forwarded-For "
            "entries (%d). Using leftmost entry as fallback. Check your "
            "proxy chain configuration.",
            proxies_count,
            len(parts),
        )
        return parts[0]


def get_client_ip_from_http(request) -> str:
    """Extract client IP from a Django ``HttpRequest``.

    Checks ``HTTP_X_FORWARDED_FOR`` first (for reverse-proxy setups like
    Traefik/nginx), then falls back to ``REMOTE_ADDR``.

    When ``RATELIMIT_PROXIES_COUNT`` is ``0`` the ``X-Forwarded-For``
    header is ignored entirely and only ``REMOTE_ADDR`` is used.  This is
    the correct behaviour when the app receives connections directly
    without a reverse proxy: XFF would be entirely client-controlled and
    thus untrustworthy.

    .. note::
        ``RATELIMIT_PROXIES_COUNT`` controls which ``X-Forwarded-For``
        entry is used.  The default is ``1`` (rightmost entry = single
        proxy such as Traefik/nginx).  ``2`` = second from right (two
        proxies, e.g. CDN + load balancer).

    IPv6 addresses are masked to ``RATELIMIT_IPV6_MASK`` (default ``/64``)
    so clients within the same subnet share a rate-limit counter.

    Args:
        request: A Django ``HttpRequest`` (or any object with a ``META`` dict).

    Returns:
        Client IP address string, or ``"unknown"`` if unavailable.
    """
    from django.conf import settings

    proxies_count = getattr(settings, "RATELIMIT_PROXIES_COUNT", 1)

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for and proxies_count > 0:
        return _mask_ipv6(_pick_xff_ip(x_forwarded_for))
    return _mask_ipv6(request.META.get("REMOTE_ADDR", UNKNOWN_IP))


def get_client_ip_from_scope(scope: MutableMapping[str, Any]) -> str:
    """Extract client IP from an ASGI scope dict.

    Uses the same ``RATELIMIT_PROXIES_COUNT`` setting as
    :func:`get_client_ip_from_http` to select the trusted entry from
    ``X-Forwarded-For``.  When ``RATELIMIT_PROXIES_COUNT`` is ``0`` the
    ``X-Forwarded-For`` header is ignored entirely.

    IPv6 addresses are masked to ``RATELIMIT_IPV6_MASK`` (default ``/64``).

    Args:
        scope: ASGI scope dictionary.

    Returns:
        Client IP address string, or ``"unknown"`` if unavailable.
    """
    from django.conf import settings

    proxies_count = getattr(settings, "RATELIMIT_PROXIES_COUNT", 1)
    headers = dict(scope.get("headers", []))

    # Proxy-injected headers — only trusted when behind a reverse proxy
    # (proxies_count > 0).  When proxies_count == 0 the app receives
    # connections directly, so both X-Forwarded-For and X-Real-IP are
    # entirely client-controlled and must be ignored.
    if proxies_count > 0:
        xff = headers.get(b"x-forwarded-for")
        if xff:
            return _mask_ipv6(_pick_xff_ip(xff.decode()))

        # X-Real-IP (common in nginx setups)
        x_real_ip = headers.get(b"x-real-ip")
        if x_real_ip:
            return _mask_ipv6(x_real_ip.decode().strip())

    # Direct client connection
    client = scope.get("client")
    if client and len(client) >= 1:
        return _mask_ipv6(client[0])

    return UNKNOWN_IP


# ---------------------------------------------------------------------------
#  Unified rate limit key builder
# ---------------------------------------------------------------------------


def get_rate_limit_key(
    *,
    user: Any = None,
    ip: str = UNKNOWN_IP,
    strategy: str = "user_or_ip",
) -> str:
    """Build a rate limit cache key from user and/or IP.

    Args:
        user: Django user instance (or ``None`` / ``AnonymousUser``).
        ip: Client IP address string.
        strategy: Key strategy:
            - ``"user_or_ip"`` (default): ``user:{id}`` if authenticated,
              else ``ip:{ip}``.
            - ``"ip"``: always ``ip:{ip}``.
            - ``"user"``: always ``user:{id}`` (raises if anonymous).

    Returns:
        A string suitable for use as the ``key`` argument to
        :func:`~config.ratelimit.engine.is_rate_limited`.

    Raises:
        ValueError: If strategy is ``"user"`` and no authenticated user
                    is available.
    """
    if strategy == "ip":
        return f"ip:{ip}"

    if strategy == "user":
        if not user or not is_authenticated(user):
            raise ValueError("Authenticated user required for 'user' key strategy")
        return f"user:{user.id}"

    # Default: user_or_ip
    if user and is_authenticated(user):
        return f"user:{user.id}"
    return f"ip:{ip}"


def is_authenticated(user: Any) -> bool:
    """Check if a user object is authenticated, handling both property and method forms.

    The callable guard exists because ``is_authenticated`` was a method
    (``CallableBool``) prior to Django 1.10 and some third-party user
    models or test mocks may still use the legacy callable form.
    """
    is_auth = getattr(user, "is_authenticated", False)
    if callable(is_auth):
        return is_auth()
    return bool(is_auth)
