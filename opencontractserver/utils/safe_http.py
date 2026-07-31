"""SSRF-safe HTTP fetch helper for public-domain authority sources.

All outbound HTTP from authority providers MUST go through ``safe_fetch_bytes``
or ``safe_fetch_text``.  They enforce:

- Scheme allowlist (HTTPS only).
- Host allowlist (government public-domain hosts only).
- DNS-resolved IP must be public — no private/loopback/link-local/multicast/
  reserved/unspecified/CGNAT addresses (closes multi-A-record / DNS-rebinding
  windows).
- Manual redirect loop that re-validates EVERY hop independently.
- DNS pinning: the connection for each hop is made to the SAME address that
  was just validated, never a second, independently-resolved address.
- Streamed size cap (both Content-Length header and actual bytes).
- Connect + read timeouts.

``SSRFValidationError`` (subclasses ``ValueError``) is raised for every safety
violation so callers can distinguish "blocked for safety" from "network error".

DNS pinning (issue #2048)
-------------------------
``_assert_public_ip`` resolves a host and rejects it if any address is
non-public, but returns the validated addresses too. ``safe_fetch_bytes`` pins
its connection to the FIRST validated address via ``_DNSPinnedTransport``
(a custom ``httpx.HTTPTransport``) instead of handing the hostname to
httpx/httpcore and letting them resolve it again independently at connect
time — closing the DNS-rebind time-of-check/time-of-use window a resolve-then-
reresolve design would otherwise leave open. Each redirect hop gets its own
pin, resolved fresh, since a redirect can land on a different host entirely.
The original hostname is still sent as the TLS SNI/certificate-verification
name and the ``Host`` header, so certificate validation and server-side vhost
routing are unaffected. ``validate_url`` itself does not pin anything — it is
a standalone check for callers that issue their own request afterward (e.g.
via ``requests``) rather than through ``safe_fetch_bytes``.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import ssl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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


logger = logging.getLogger(__name__)

# Injectable default-allowlist provider. The authority subsystem registers
# ``effective_source_allowlist`` (baseline ∪ installed packs' source_hosts) at app
# startup so a self-contained pack can widen WHICH hosts are reachable without this
# pure SSRF util importing the enrichment/pipeline layer. When ``allowlist`` is
# omitted (None) the registered provider is consulted; if none is registered (or it
# raises) the call falls back to the hardcoded baseline — fail-CLOSED to the
# smallest trusted set, never wider. The SSRF checks themselves (scheme, public-IP,
# per-hop revalidation, size caps) are unaffected: only the host set changes.
_allowlist_provider: Callable[[], frozenset[str]] | None = None


def register_allowlist_provider(
    provider: Callable[[], frozenset[str]] | None,
) -> None:
    """Install (or clear, with ``None``) the dynamic default-allowlist provider."""
    global _allowlist_provider
    _allowlist_provider = provider


@contextmanager
def scoped_default_allowlist(allowlist: frozenset[str]) -> Iterator[None]:
    """Temporarily replace the default host allowlist for standalone work.

    Authority-pack artifact builders do not run inside a long-lived Django
    process, but still need the same manifest-declared host expansion as the
    app.  This context keeps that expansion narrow and restores the prior
    provider even when collection fails.  All other SSRF checks remain active.
    """

    previous = _allowlist_provider
    register_allowlist_provider(lambda: allowlist)
    try:
        yield
    finally:
        register_allowlist_provider(previous)


def _resolve_allowlist(allowlist: frozenset[str] | None) -> frozenset[str]:
    """Resolve the effective allowlist for a call.

    An explicit ``allowlist`` (a caller passing its own set) always wins. When
    omitted (``None``) the registered provider is consulted, falling back to the
    hardcoded baseline if none is registered or it raises (fail-closed).
    """
    if allowlist is not None:
        return allowlist
    if _allowlist_provider is not None:
        try:
            return _allowlist_provider()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "allowlist provider failed; falling back to baseline: %s", exc
            )
    return PUBLIC_DOMAIN_SOURCE_HOSTS


def host_on_allowlist(host: str, *, allowlist: frozenset[str] | None = None) -> bool:
    """Return True if *host* is on the effective allowlist (exact or dotted-suffix).

    ``allowlist=None`` (the default) resolves to the registered effective allowlist
    (baseline ∪ installed packs' source_hosts), else the hardcoded baseline.
    ``"uscode.house.gov"`` matches the allowlist entry ``"uscode.house.gov"``
    (exact) or ``"house.gov"`` (suffix).
    """
    allowlist = _resolve_allowlist(allowlist)
    host = host.lower().rstrip(".")
    if host in allowlist:
        return True
    # Exact matches are handled above; this is the subdomain check — host must be
    # a dotted child of an allowlisted domain (e.g. "api.ecfr.gov" of "ecfr.gov"),
    # NOT merely share a suffix ("notecfr.gov" must not match).
    return any(host.endswith("." + a) for a in allowlist)


def _assert_public_ip(
    host: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve *host*, raise if ANY resolved address is non-public, and return the
    validated addresses (AS RESOLVED — see note below) for the caller to pin the
    outbound connection to.

    Rejecting when *any* address is unsafe (not just the first) closes the
    multi-A-record / partial-rebind window. RFC 6598 CGNAT space, which the
    ``ipaddress`` property denylist below does not cover, is rejected explicitly
    via ``_CGNAT_NETWORK`` (see ``CGNAT_SHARED_ADDRESS_SPACE_CIDR`` for why).
    IPv4-mapped IPv6 addresses (``::ffff:a.b.c.d``) are unwrapped to their
    embedded IPv4 first: the OS connects to that IPv4, but its is_private /
    _CGNAT_NETWORK membership do not reflect the mapping on every CPython
    version (the CGNAT-mapped form slips through on 3.11), so the mapped form of
    a private/CGNAT address must not bypass the checks. The unwrap is used ONLY
    for the safety check; the returned list carries each address in the form it
    was actually resolved to (mapped IPv6 included), since that is the literal
    ``safe_fetch_bytes`` pins the TCP connection to — see its DNS-pinning note.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFValidationError(f"DNS resolution failed for {host!r}") from exc
    if not infos:
        # getaddrinfo can return an EMPTY list without raising on some resolver
        # configs (e.g. a name with no A/AAAA records, or OS-level filtering). An
        # empty loop below would fall through and silently declare the host safe
        # (fail-OPEN), after which the pinned connect would have no address to
        # target — so reject explicitly and fail CLOSED.
        raise SSRFValidationError(f"no addresses resolved for {host!r}")
    validated: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        resolved_ip = ipaddress.ip_address(info[4][0])
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
        # needed.
        check_ip = resolved_ip
        if (
            isinstance(check_ip, ipaddress.IPv6Address)
            and check_ip.ipv4_mapped is not None
        ):
            check_ip = check_ip.ipv4_mapped
        if (
            check_ip.is_private
            or check_ip.is_loopback
            or check_ip.is_link_local
            or check_ip.is_multicast
            or check_ip.is_reserved
            or check_ip.is_unspecified
            or (
                isinstance(check_ip, ipaddress.IPv4Address)
                and check_ip in _CGNAT_NETWORK
            )
        ):
            raise SSRFValidationError(
                f"{host!r} resolves to non-public address {check_ip}"
            )
        validated.append(resolved_ip)
    return validated


def _validate_scheme_allowlist_and_ip(
    url: str, *, allowlist: frozenset[str] | None
) -> tuple[str, list[ipaddress.IPv4Address | ipaddress.IPv6Address]]:
    """Shared implementation behind ``validate_url`` and the DNS-pinning path in
    ``safe_fetch_bytes``.

    Returns ``(host, validated_ips)``: the validated IPs are the exact addresses
    ``_assert_public_ip`` already resolved and checked, so a caller that also
    needs the resolved IP (to pin the outbound connection) never triggers a
    second, independent DNS round-trip.
    """
    allowlist = _resolve_allowlist(allowlist)
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFValidationError(f"scheme {parsed.scheme!r} not allowed")
    host = parsed.hostname
    if not host:
        raise SSRFValidationError(f"no host in URL {url!r}")
    if not host_on_allowlist(host, allowlist=allowlist):
        raise SSRFValidationError(f"host {host!r} not on public-domain allowlist")
    ips = _assert_public_ip(host)
    return host, ips


def validate_url(url: str, *, allowlist: frozenset[str] | None = None) -> str:
    """Validate scheme + host allowlist + public-IP.

    Returns the (lowercased) hostname on success.
    Raises ``SSRFValidationError`` on any violation. ``allowlist=None`` resolves to
    the registered effective allowlist (see :func:`host_on_allowlist`).

    This does not pin a connection to the resolved IP — it is a standalone
    validation used by callers that make their own request afterward (e.g. via
    ``requests``); callers that also need to CONNECT should use
    ``safe_fetch_bytes``, which pins each hop to the address validated here.
    """
    host, _ips = _validate_scheme_allowlist_and_ip(url, allowlist=allowlist)
    return host


def _extra_ca_ssl_context(
    extra_ca_certificates: tuple[str, ...] | None,
) -> ssl.SSLContext | None:
    """Build a normal system-trust context with additive PEM certificates.

    Some official publishers serve a valid leaf certificate while omitting an
    intermediate from the TLS handshake.  Callers may supply the missing CA
    certificates as audited PEM text.  This never disables hostname or chain
    verification and never replaces the platform trust store.
    """

    if not extra_ca_certificates:
        return None
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    for index, certificate in enumerate(extra_ca_certificates):
        if not isinstance(certificate, str) or not certificate.strip():
            raise ValueError(
                f"extra_ca_certificates[{index}] must be non-empty PEM text"
            )
        try:
            context.load_verify_locations(cadata=certificate)
        except ssl.SSLError as exc:
            raise ValueError(
                f"extra_ca_certificates[{index}] is not a valid CA certificate"
            ) from exc
    return context


class _DNSPinnedTransport(httpx.HTTPTransport):
    """``httpx.HTTPTransport`` that connects to a pre-resolved, pre-validated IP
    instead of letting httpx/httpcore resolve DNS independently at connect time.

    This closes the DNS-rebind time-of-check/time-of-use window: without it, a
    resolver could return a public address when ``_assert_public_ip`` validates
    the host and a private one moments later when httpx independently resolves
    it to connect.

    ``handle_request`` rewrites the outbound request's URL host to
    ``pinned_ip`` before delegating to the base transport. httpcore's
    connection pool routes strictly off ``request.url.host``, so the TCP
    connect targets the pinned address; because that address is already a
    numeric literal, the OS resolver returns it immediately without a second
    network round-trip. Two things are deliberately left pointing at the
    ORIGINAL hostname so the swap is invisible past the TCP layer:

    - The ``Host`` header, which httpx already finalized from the original URL
      before the transport ever sees the request (so server-side vhost/CDN
      routing still works).
    - The ``sni_hostname`` extension, which httpcore's connection layer uses as
      the TLS ``server_hostname`` — both the SNI ClientHello field and the name
      matched against the server's certificate — so certificate validation
      still checks the real hostname rather than the bare IP.
    """

    def __init__(
        self,
        *,
        pinned_ip: str,
        sni_hostname: str,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        super().__init__(verify=ssl_context if ssl_context is not None else True)
        self._pinned_ip = pinned_ip
        self._sni_hostname = sni_hostname

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_with(host=self._pinned_ip)
        request.extensions = {
            **request.extensions,
            "sni_hostname": self._sni_hostname,
        }
        return super().handle_request(request)


def safe_fetch_bytes(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    allowlist: frozenset[str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    extra_ca_certificates: tuple[str, ...] | None = None,
) -> tuple[bytes, str]:
    """SSRF-safe GET. Returns ``(body_bytes, final_host)``.

    - Validates the initial URL (scheme / allowlist / public-IP).
    - Follows up to ``MAX_REDIRECTS`` redirects MANUALLY, re-validating each hop.
    - DNS-pins each hop: the connection is made to the address just validated
      for that hop, never re-resolved independently at connect time (see the
      module docstring's "DNS pinning" section and ``_DNSPinnedTransport``).
    - Streams the body and aborts past *max_bytes* (Content-Length AND actual bytes).
    - Enforces connect + read timeouts via the module-level ``_DEFAULT_TIMEOUT``.

    Caller params note: *params* are forwarded only on the INITIAL request. On any
    redirect (same-host or cross-host) the redirect Location is the authoritative
    next URL, so *params* are NOT re-appended — a caller whose params are a
    required filter (e.g. the eCFR section/part filter) is relying on that endpoint
    not redirecting.

    Caller headers note: on a cross-host redirect only the STANDARD credential
    headers (``CROSS_HOST_STRIPPED_HEADERS``) are stripped. Do NOT pass a
    non-standard per-service credential header (``X-Api-Key``, ``X-Auth-Token``,
    …) — it would be forwarded to the redirect target host.
    """
    # Resolve the effective allowlist ONCE so every redirect hop below is
    # validated against the same host set (the registered provider is consulted
    # only here, not per-hop).
    allowlist = _resolve_allowlist(allowlist)
    ssl_context = _extra_ca_ssl_context(extra_ca_certificates)
    # Default User-Agent so fetches identify OpenContracts to .gov servers
    # rather than going out as an anonymous httpx client; a caller-supplied
    # User-Agent (e.g. the FR/CFR providers) overrides it. httpx.Headers is
    # case-insensitive, so a caller passing "user-agent" in any casing replaces
    # the default instead of producing two conflicting User-Agent header lines.
    request_headers = httpx.Headers({"User-Agent": DEFAULT_USER_AGENT})
    if headers:
        request_headers.update(headers)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        # Validate THIS hop and pin the connection to the address just
        # resolved+validated above (see ``_DNSPinnedTransport``). A fresh
        # transport/client is built on every iteration — not reused across
        # hops — because a redirect can land on a different host, and
        # therefore a different validated IP, than the previous hop; pinning
        # must never carry a stale IP forward onto a new host.
        final_host, ips = _validate_scheme_allowlist_and_ip(
            current, allowlist=allowlist
        )
        if ssl_context is not None:
            transport = _DNSPinnedTransport(
                pinned_ip=str(ips[0]),
                sni_hostname=final_host,
                ssl_context=ssl_context,
            )
        else:
            transport = _DNSPinnedTransport(
                pinned_ip=str(ips[0]),
                sni_hostname=final_host,
            )
        with httpx.Client(
            transport=transport, follow_redirects=False, timeout=_DEFAULT_TIMEOUT
        ) as client:
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
    allowlist: frozenset[str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    extra_ca_certificates: tuple[str, ...] | None = None,
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
        extra_ca_certificates=extra_ca_certificates,
    )
    return body.decode("utf-8", errors="replace"), final_host
