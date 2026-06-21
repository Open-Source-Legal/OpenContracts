"""SSRF-safe HTTP fetch helper for public-domain authority sources.

All outbound HTTP from authority providers MUST go through ``safe_fetch_bytes``
or ``safe_fetch_text``.  They enforce:

- Scheme allowlist (HTTPS only).
- Host allowlist (government public-domain hosts only).
- DNS-resolved IP must be public — no private/loopback/link-local/multicast/
  reserved/unspecified addresses (closes multi-A-record / DNS-rebinding windows).
- Manual redirect loop that re-validates EVERY hop independently.
- Streamed size cap (both Content-Length header and actual bytes).
- Connect + read timeouts.

``SSRFValidationError`` (subclasses ``ValueError``) is raised for every safety
violation so callers can distinguish "blocked for safety" from "network error".

DNS-rebind TOCTOU note
----------------------
This helper validates DNS at check time but httpx re-resolves at connect time,
so a DNS-rebind time-of-check/time-of-use window technically exists.  In
practice it is not exploitable here because the allowlist is a fixed set of
public-domain ``.gov`` hosts whose DNS the attacker cannot control, and
``_assert_public_ip`` rejects if ANY resolved address is non-public.
Full DNS-pinning (resolve once, connect to the pinned IP with the hostname as
SNI) is a documented follow-up improvement for defence-in-depth.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from opencontractserver.constants.safe_http import (
    ALLOWED_SCHEMES,
    CONNECT_TIMEOUT_SECONDS,
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    PUBLIC_DOMAIN_SOURCE_HOSTS,
    READ_TIMEOUT_SECONDS,
)


class SSRFValidationError(ValueError):
    """Raised when a URL/host/IP/redirect fails an SSRF safety check.

    Distinct from network errors so the gate can record a precise
    ``candidate_sources`` reason and callers can distinguish 'blocked for
    safety' from 'upstream was down'.
    """


def host_on_allowlist(
    host: str, *, allowlist: frozenset[str] = PUBLIC_DOMAIN_SOURCE_HOSTS
) -> bool:
    """Return True if *host* is on *allowlist* (exact or dotted-suffix match).

    ``"uscode.house.gov"`` matches the allowlist entry ``"uscode.house.gov"``
    (exact) or ``"house.gov"`` (suffix).
    """
    host = host.lower().rstrip(".")
    if host in allowlist:
        return True
    # Exact matches are handled above; this is the subdomain check — host must be
    # a dotted child of an allowlisted domain (e.g. "api.ecfr.gov" of "ecfr.gov"),
    # NOT merely share a suffix ("notecfr.gov" must not match).
    return any(host.endswith("." + a) for a in allowlist)


def _assert_public_ip(host: str) -> None:
    """Resolve *host* and raise if ANY resolved address is non-public.

    Rejecting when *any* address is unsafe (not just the first) closes the
    multi-A-record / partial-rebind window.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFValidationError(f"DNS resolution failed for {host!r}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise SSRFValidationError(f"{host!r} resolves to non-public address {ip}")


def validate_url(
    url: str, *, allowlist: frozenset[str] = PUBLIC_DOMAIN_SOURCE_HOSTS
) -> str:
    """Validate scheme + host allowlist + public-IP.

    Returns the (lowercased) hostname on success.
    Raises ``SSRFValidationError`` on any violation.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFValidationError(f"scheme {parsed.scheme!r} not allowed")
    host = parsed.hostname
    if not host:
        raise SSRFValidationError(f"no host in URL {url!r}")
    if not host_on_allowlist(host, allowlist=allowlist):
        raise SSRFValidationError(f"host {host!r} not on public-domain allowlist")
    _assert_public_ip(host)
    return host


def safe_fetch_bytes(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    allowlist: frozenset[str] = PUBLIC_DOMAIN_SOURCE_HOSTS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[bytes, str]:
    """SSRF-safe GET. Returns ``(body_bytes, final_host)``.

    - Validates the initial URL (scheme / allowlist / public-IP).
    - Follows up to ``MAX_REDIRECTS`` redirects MANUALLY, re-validating each hop.
    - Streams the body and aborts past *max_bytes* (Content-Length AND actual bytes).
    - Enforces connect + read timeouts via ``httpx.Timeout``.
    """
    # httpx requires either a single default or all four phases set explicitly;
    # spell them out so READ_TIMEOUT_SECONDS clearly applies to read/write/pool
    # and CONNECT_TIMEOUT_SECONDS only to connect.
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS,
        read=READ_TIMEOUT_SECONDS,
        write=READ_TIMEOUT_SECONDS,
        pool=READ_TIMEOUT_SECONDS,
    )
    current = url
    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
        for _ in range(MAX_REDIRECTS + 1):
            final_host = validate_url(current, allowlist=allowlist)
            with client.stream("GET", current, params=params, headers=headers) as r:
                if r.is_redirect:
                    loc = r.headers.get("location", "")
                    # Resolve relative Location against the current URL.
                    current = str(httpx.URL(current).join(loc))
                    params = None  # only the first hop carries query params
                    continue
                r.raise_for_status()
                cl = r.headers.get("content-length")
                if cl:
                    try:
                        cl_int = int(cl)
                    except (ValueError, TypeError):
                        raise SSRFValidationError(f"malformed content-length {cl!r}")
                    if cl_int > max_bytes:
                        raise SSRFValidationError(
                            f"content-length {cl} exceeds cap of {max_bytes} bytes"
                        )
                chunks: list[bytes] = []
                total = 0
                for chunk in r.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise SSRFValidationError(
                            f"response exceeded size cap of {max_bytes} bytes"
                        )
                    chunks.append(chunk)
                return b"".join(chunks), final_host
        raise SSRFValidationError(f"exceeded {MAX_REDIRECTS} redirects")


def safe_fetch_text(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    allowlist: frozenset[str] = PUBLIC_DOMAIN_SOURCE_HOSTS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[str, str]:
    """SSRF-safe GET returning ``(text, final_host)``.

    Thin wrapper around ``safe_fetch_bytes`` that decodes the body as UTF-8
    (replacing undecodable bytes) and returns the text alongside the final host.
    """
    body, final_host = safe_fetch_bytes(
        url,
        params=params,
        headers=headers,
        allowlist=allowlist,
        max_bytes=max_bytes,
    )
    return body.decode("utf-8", errors="replace"), final_host
