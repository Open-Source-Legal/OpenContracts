"""SSRF-safe HTTP fetch helper for public-domain authority sources.

All outbound HTTP from authority providers MUST go through ``safe_fetch_bytes``
or ``safe_fetch_text``.  They enforce:

- Scheme allowlist (HTTPS only).
- Host allowlist (government public-domain hosts only).
- DNS-resolved IP must be public — no private/loopback/link-local/multicast/
  reserved/unspecified/CGNAT addresses (closes multi-A-record / DNS-rebinding
  windows).
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
SNI) is the defence-in-depth follow-up tracked in issue #2048.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from opencontractserver.constants.safe_http import (
    ALLOWED_SCHEMES,
    CGNAT_SHARED_ADDRESS_SPACE_CIDR,
    CONNECT_TIMEOUT_SECONDS,
    CROSS_HOST_STRIPPED_HEADERS,
    DEFAULT_USER_AGENT,
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    PUBLIC_DOMAIN_SOURCE_HOSTS,
    READ_TIMEOUT_SECONDS,
)

# Built once at import. ``ip in _CGNAT_NETWORK`` is a cheap containment check
# (see CGNAT_SHARED_ADDRESS_SPACE_CIDR for why the ipaddress property denylist
# alone is insufficient). It is an IPv4 network, so ``_assert_public_ip`` guards
# the membership test with ``isinstance(ip, IPv4Address)``: an IPv4-mapped IPv6
# address is already unwrapped to its embedded IPv4 before then, and a native
# IPv6 address is skipped here (it is covered by the is_* properties) rather than
# relying on ``IPv6Address in IPv4Network`` — which returns False only on CPython
# 3.11+ and raises TypeError on 3.10.
_CGNAT_NETWORK = ipaddress.ip_network(CGNAT_SHARED_ADDRESS_SPACE_CIDR)

# Built once at import (like _CGNAT_NETWORK) — a pure-constant object derived
# from the module-level timeout constants. httpx requires either a single
# default or all four phases set explicitly; spell them out so
# READ_TIMEOUT_SECONDS clearly applies to read/write/pool and
# CONNECT_TIMEOUT_SECONDS only to connect. Because it is frozen at import, a test
# that needs to override timeouts must patch ``safe_http._DEFAULT_TIMEOUT``
# directly — patching the CONNECT_/READ_TIMEOUT_SECONDS constants has no effect.
_DEFAULT_TIMEOUT = httpx.Timeout(
    connect=CONNECT_TIMEOUT_SECONDS,
    read=READ_TIMEOUT_SECONDS,
    write=READ_TIMEOUT_SECONDS,
    pool=READ_TIMEOUT_SECONDS,
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
    multi-A-record / partial-rebind window. RFC 6598 CGNAT space, which the
    ``ipaddress`` property denylist below does not cover, is rejected explicitly
    via ``_CGNAT_NETWORK`` (see ``CGNAT_SHARED_ADDRESS_SPACE_CIDR`` for why).
    IPv4-mapped IPv6 addresses (``::ffff:a.b.c.d``) are unwrapped to their
    embedded IPv4 first: the OS connects to that IPv4, but its is_private /
    _CGNAT_NETWORK membership do not reflect the mapping on every CPython
    version (the CGNAT-mapped form slips through on 3.11), so the mapped form of
    a private/CGNAT address must not bypass the checks.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFValidationError(f"DNS resolution failed for {host!r}") from exc
    if not infos:
        # getaddrinfo can return an EMPTY list without raising on some resolver
        # configs (e.g. a name with no A/AAAA records, or OS-level filtering). An
        # empty loop below would fall through and silently declare the host safe
        # (fail-OPEN), after which httpx still resolves independently at connect
        # time — so reject explicitly and fail CLOSED.
        raise SSRFValidationError(f"no addresses resolved for {host!r}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # Unwrap IPv4-mapped IPv6 so the checks below run against the real IPv4
        # destination (see docstring). Native IPv6 is left as-is.
        #
        # Only IPv4-MAPPED IPv6 needs this: it is the one embedded form whose
        # is_private / CGNAT status does not reflect the embedded IPv4 (a mapped
        # CGNAT address reports is_private=False). The OTHER IPv6-embedded-IPv4
        # forms — NAT64 (64:ff9b::/96 and RFC 8215 64:ff9b:1::/48), 6to4
        # (2002::/16), Teredo (2001:0::/32), and deprecated IPv4-compatible
        # (::/96) — are already rejected because CPython flags those whole
        # prefixes is_private / is_reserved (verified on 3.11 and 3.12; pinned by
        # test_ipv6_embedded_ipv4_tunnels_rejected), so no per-form extraction is
        # needed. The separate DNS-rebind TOCTOU is tracked in #2048.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or (isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK)
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
    - Enforces connect + read timeouts via the module-level ``_DEFAULT_TIMEOUT``.

    Caller headers note: on a cross-host redirect only the STANDARD credential
    headers (``CROSS_HOST_STRIPPED_HEADERS``) are stripped. Do NOT pass a
    non-standard per-service credential header (``X-Api-Key``, ``X-Auth-Token``,
    …) — it would be forwarded to the redirect target host.
    """
    # Default User-Agent so fetches identify OpenContracts to .gov servers
    # rather than going out as an anonymous httpx client; a caller-supplied
    # User-Agent (e.g. the FR/CFR providers) overrides it. httpx.Headers is
    # case-insensitive, so a caller passing "user-agent" in any casing replaces
    # the default instead of producing two conflicting User-Agent header lines.
    request_headers = httpx.Headers({"User-Agent": DEFAULT_USER_AGENT})
    if headers:
        request_headers.update(headers)
    current = url
    with httpx.Client(follow_redirects=False, timeout=_DEFAULT_TIMEOUT) as client:
        for _ in range(MAX_REDIRECTS + 1):
            final_host = validate_url(current, allowlist=allowlist)
            with client.stream(
                "GET", current, params=params, headers=request_headers
            ) as r:
                # ``has_redirect_location`` (not ``is_redirect``) is the precise
                # check: in httpx ``is_redirect`` is ANY 3xx, so a 304 Not Modified
                # (or any non-Location 3xx) would otherwise be treated as a
                # redirect, resolve Location "" back to the current URL, and loop
                # to the redirect cap with a misleading error.
                if r.has_redirect_location:
                    loc = r.headers.get("location", "")
                    if not loc:
                        # Redirect status with a present-but-empty Location: would
                        # resolve to the current URL and loop until the cap. Fail
                        # fast with the real reason instead.
                        raise SSRFValidationError(
                            f"redirect from {current!r} has an empty Location header"
                        )
                    # Resolve relative Location against the current URL (reuse the
                    # parsed objects rather than re-parsing the string twice).
                    current_url = httpx.URL(current)
                    next_url = current_url.join(loc)
                    # On a cross-ORIGIN redirect (different host OR port, e.g.
                    # ecfr.gov -> federalregister.gov) drop per-service credential
                    # headers: httpx, unlike browsers/requests, forwards them
                    # verbatim across origins (RFC 9110 §15.4), so a caller-
                    # supplied Authorization/Cookie would otherwise leak from one
                    # allowlisted .gov service to another. Compare ``netloc`` (host
                    # AND port), not ``host`` — a same-host/different-port redirect
                    # is still a different service. The default User-Agent is kept.
                    if next_url.netloc != current_url.netloc:
                        request_headers = httpx.Headers(
                            {
                                k: v
                                for k, v in request_headers.items()
                                if k.lower() not in CROSS_HOST_STRIPPED_HEADERS
                            }
                        )
                    current = str(next_url)
                    # Drop the caller's query params on EVERY redirect (not just
                    # cross-host): the redirect Location is the authoritative next
                    # URL and carries its own query string, so re-appending the
                    # original params would corrupt it. A caller whose params are a
                    # required filter (e.g. the eCFR section/part filter) therefore
                    # relies on that endpoint NOT redirecting; if it ever did, the
                    # filter would not carry to the target — by design, since the
                    # target may not accept it.
                    params = None
                    # Exiting this ``with`` on ``continue`` closes the response
                    # and releases the connection. We deliberately do NOT call
                    # ``r.read()`` first: the redirect body is unused, and
                    # reading an attacker-influenced redirect body would be an
                    # unbounded read that bypasses the per-hop size cap below.
                    continue
                r.raise_for_status()
                cl = r.headers.get("content-length")
                if cl:
                    try:
                        cl_int = int(cl)
                    except (ValueError, TypeError):
                        raise SSRFValidationError(f"malformed content-length {cl!r}")
                    if cl_int < 0:
                        # A negative Content-Length (some servers send -1 for
                        # streamed responses) parses fine but would silently slip
                        # the > max_bytes guard below, making the header fast-fail
                        # dead code. Treat it as malformed.
                        raise SSRFValidationError(f"negative content-length {cl!r}")
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
    Inherits ``safe_fetch_bytes``' behaviour, including the default ``User-Agent``
    and the cross-host credential-header stripping (see its docstring).
    """
    body, final_host = safe_fetch_bytes(
        url,
        params=params,
        headers=headers,
        allowlist=allowlist,
        max_bytes=max_bytes,
    )
    return body.decode("utf-8", errors="replace"), final_host
