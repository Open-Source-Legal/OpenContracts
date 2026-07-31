"""Tests for the SSRF-safe HTTP fetch helper.

No database required — these are pure-logic and mocked-network tests.
Run with:
    docker compose -f test.yml -p opencontracts run --rm django pytest \
        opencontractserver/tests/test_safe_http.py -q
"""

from __future__ import annotations

import socket
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import httpx
import pytest

from opencontractserver.constants.safe_http import (
    MAX_REDIRECTS,
    PUBLIC_DOMAIN_SOURCE_HOSTS,
)
from opencontractserver.utils import safe_http as _safe_http_module
from opencontractserver.utils.safe_http import (
    SSRFValidationError,
    _assert_public_ip,
    _resolve_allowlist,
    host_on_allowlist,
    register_allowlist_provider,
    safe_fetch_bytes,
    safe_fetch_text,
    validate_url,
)

# A valid allowlisted host whose IP we can control in tests.
ALLOWED_HOST = "uscode.house.gov"
ALLOWED_URL = f"https://{ALLOWED_HOST}/path"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _fake_getaddrinfo(ip_str):
    """Return a getaddrinfo patcher that resolves any host to *ip_str*.

    Accepts ANY address string (public, private, CGNAT, IPv4-mapped, or native
    IPv6) — each test decides whether that address should be accepted or
    rejected, so this helper is intentionally neutral about the IP's class.

    The family + sockaddr shape mirror real ``socket.getaddrinfo`` (AF_INET6 +
    4-tuple for IPv6, AF_INET + 2-tuple for IPv4), so a future check on the
    address family (``info[0]``) would still see faithful data.
    """
    is_ipv6 = ":" in ip_str
    family = socket.AF_INET6 if is_ipv6 else socket.AF_INET
    sockaddr = (ip_str, 0, 0, 0) if is_ipv6 else (ip_str, 0)

    def _inner(host, port, *args, **kwargs):
        return [(family, 1, 6, "", sockaddr)]

    return _inner


# Defined as aliases so the family/sockaddr shape lives in exactly one place
# (see _fake_getaddrinfo) rather than being duplicated per fixed address.
_fake_getaddrinfo_public = _fake_getaddrinfo("1.1.1.1")
_fake_getaddrinfo_ipv6_loopback = _fake_getaddrinfo("::1")


@contextmanager
def _mock_stream(status_code: int, body: bytes = b"", headers: dict | None = None):
    """Context-manager factory returned by a mocked ``httpx.Client.stream``."""
    resp = MagicMock()
    resp.status_code = status_code
    # Real httpx.Response.headers is case-insensitive; lowercase the keys (and the
    # lookups below) so a test passing {"Location": ...} (the conventional capital
    # L) is not silently misrouted to has_redirect_location=False the way a plain
    # case-sensitive dict would.
    hdr_dict = {k.lower(): v for k, v in (headers or {}).items()}
    # Mirror httpx 0.28.x: ``is_redirect`` is ANY 3xx, while
    # ``has_redirect_location`` additionally requires a redirect status code AND a
    # Location header present. safe_fetch_bytes keys off the latter.
    resp.is_redirect = 300 <= status_code < 400
    resp.has_redirect_location = (
        status_code in (301, 302, 303, 307, 308) and "location" in hdr_dict
    )
    resp.headers = MagicMock()
    resp.headers.get = lambda k, default=None: hdr_dict.get(k.lower(), default)

    def _raise_for_status():
        # Faithful to httpx: raise for ANY non-2xx (including a 3xx that was not
        # followed as a redirect, e.g. a malformed 301 with no Location), no-op
        # for 2xx. Redirect hops never reach this — they ``continue`` first.
        if not 200 <= status_code < 300:
            raise httpx.HTTPStatusError(
                f"{status_code}", request=MagicMock(), response=resp
            )

    resp.raise_for_status = _raise_for_status

    def iter_bytes():
        yield body

    resp.iter_bytes = iter_bytes
    yield resp


def _client_stream_that_returns(status_code, body=b"", headers=None):
    """Return a patcher target for ``httpx.Client.stream``."""

    def _stream_method(self_client, method, url, **kwargs):
        return _mock_stream(status_code, body, headers)

    return _stream_method


# ─────────────────────────────────────────────────────────────────────────────
# host_on_allowlist
# ─────────────────────────────────────────────────────────────────────────────


class TestHostOnAllowlist:
    def test_exact_match(self):
        assert host_on_allowlist("uscode.house.gov")

    def test_subdomain_of_allowlisted(self):
        # Not a direct entry, but suffix of "ecfr.gov"
        assert host_on_allowlist("api.ecfr.gov")

    def test_not_on_allowlist(self):
        assert not host_on_allowlist("evil.com")

    def test_case_insensitive(self):
        assert host_on_allowlist("USCODE.HOUSE.GOV")

    def test_trailing_dot_stripped(self):
        assert host_on_allowlist("uscode.house.gov.")


class TestAdditiveCACertificates:
    def test_builds_system_context_and_loads_each_pem(self):
        context = MagicMock()
        with patch("ssl.create_default_context", return_value=context) as create:
            result = _safe_http_module._extra_ca_ssl_context(
                ("first audited PEM", "second audited PEM")
            )

        assert result is context
        create.assert_called_once()
        assert [
            call.kwargs["cadata"]
            for call in context.load_verify_locations.call_args_list
        ] == ["first audited PEM", "second audited PEM"]

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_rejects_empty_or_non_string_certificate(self, value):
        with pytest.raises(ValueError, match="non-empty PEM text"):
            _safe_http_module._extra_ca_ssl_context((value,))


# ─────────────────────────────────────────────────────────────────────────────
# validate_url — scheme rejection
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateUrlScheme:
    def test_http_scheme_rejected(self):
        """Plain http:// must be rejected even for allowlisted hosts."""
        with pytest.raises(SSRFValidationError, match="scheme"):
            validate_url(f"http://{ALLOWED_HOST}/path")

    def test_ftp_scheme_rejected(self):
        with pytest.raises(SSRFValidationError, match="scheme"):
            validate_url(f"ftp://{ALLOWED_HOST}/file.zip")

    def test_https_allowed(self):
        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            host = validate_url(ALLOWED_URL)
        assert host == ALLOWED_HOST

    def test_non_allowlisted_host_rejected(self):
        with pytest.raises(SSRFValidationError, match="allowlist"):
            validate_url("https://evil.com/steal")


# ─────────────────────────────────────────────────────────────────────────────
# _assert_public_ip — private-IP rejection
# ─────────────────────────────────────────────────────────────────────────────


class TestAssertPublicIp:
    @pytest.mark.parametrize(
        "private_ip",
        [
            "127.0.0.1",  # loopback
            "10.0.0.5",  # RFC-1918 private
            "169.254.169.254",  # cloud metadata (link-local)
            "192.168.1.1",  # RFC-1918
        ],
    )
    def test_ipv4_private_rejected(self, private_ip):
        with patch(
            "socket.getaddrinfo",
            side_effect=_fake_getaddrinfo(private_ip),
        ):
            with pytest.raises(SSRFValidationError, match="non-public"):
                _assert_public_ip(ALLOWED_HOST)

    def test_ipv6_loopback_rejected(self):
        with patch(
            "socket.getaddrinfo",
            side_effect=_fake_getaddrinfo_ipv6_loopback,
        ):
            with pytest.raises(SSRFValidationError, match="non-public"):
                _assert_public_ip(ALLOWED_HOST)

    def test_public_ip_passes(self):
        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            # Should not raise
            _assert_public_ip(ALLOWED_HOST)

    def test_public_native_ipv6_passes(self):
        """A public native IPv6 address passes and does not trip the CGNAT check.

        The CGNAT membership test is an IPv4 network; the ``isinstance(ip,
        IPv4Address)`` guard means a native IPv6 address skips it entirely (rather
        than relying on ``IPv6Address in IPv4Network`` returning False, which only
        holds on CPython 3.11+). 2606:4700:4700::1111 is Cloudflare's public DNS.
        """
        with patch(
            "socket.getaddrinfo",
            side_effect=_fake_getaddrinfo("2606:4700:4700::1111"),
        ):
            _assert_public_ip(ALLOWED_HOST)  # must not raise

    def test_dns_failure_raises_ssrf_error(self):
        with patch(
            "socket.getaddrinfo",
            side_effect=socket.gaierror("NXDOMAIN"),
        ):
            with pytest.raises(SSRFValidationError, match="DNS resolution failed"):
                _assert_public_ip("nonexistent.host.invalid")

    def test_empty_getaddrinfo_rejected(self):
        """getaddrinfo returning [] (no raise) must fail CLOSED, not fall through.

        An empty result would otherwise skip the per-address loop and let
        _assert_public_ip return as if the host were safe, while httpx still
        resolves independently at connect time.
        """
        with patch("socket.getaddrinfo", side_effect=lambda *a, **k: []):
            with pytest.raises(SSRFValidationError, match="no addresses resolved"):
                _assert_public_ip(ALLOWED_HOST)

    @pytest.mark.parametrize(
        "cgnat_ip",
        [
            "100.64.0.0",  # network address — low boundary of the /10 block
            "100.64.0.1",  # first usable CGNAT address
            "100.100.100.100",  # mid-range
            "100.127.255.254",  # last usable CGNAT address
            "100.127.255.255",  # high boundary of the /10 block
        ],
    )
    def test_cgnat_shared_address_space_rejected(self, cgnat_ip):
        """RFC 6598 CGNAT (100.64.0.0/10) must be rejected (issue #2026).

        ``ipaddress`` classifies this block as neither private nor reserved nor
        global on current CPython (verified on 3.11 and 3.12), so the property
        denylist alone would let a host resolving here through. The explicit
        ``_CGNAT_NETWORK`` membership check closes the gap version-independently.
        """
        with patch(
            "socket.getaddrinfo",
            side_effect=_fake_getaddrinfo(cgnat_ip),
        ):
            with pytest.raises(SSRFValidationError, match="non-public"):
                _assert_public_ip(ALLOWED_HOST)

    @pytest.mark.parametrize(
        "public_ip",
        [
            "100.63.255.255",  # one below the CGNAT block (public 100.0.0.0/8)
            "100.128.0.0",  # one above the CGNAT block
        ],
    )
    def test_cgnat_boundary_addresses_outside_block_pass(self, public_ip):
        """Addresses adjacent to but outside 100.64.0.0/10 are public and pass.

        Guards against the explicit CGNAT check being widened into an
        off-by-one over-block of legitimate 100.0.0.0/8 public space.
        """
        with patch(
            "socket.getaddrinfo",
            side_effect=_fake_getaddrinfo(public_ip),
        ):
            _assert_public_ip(ALLOWED_HOST)  # must not raise

    @pytest.mark.parametrize(
        "mapped_ip",
        [
            "::ffff:100.64.0.1",  # IPv4-mapped CGNAT — slips past on 3.11 unmapped
            "::ffff:10.0.0.1",  # IPv4-mapped RFC-1918
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
            "::ffff:169.254.169.254",  # IPv4-mapped cloud metadata
        ],
    )
    def test_ipv4_mapped_ipv6_rejected(self, mapped_ip):
        """IPv4-mapped IPv6 is unwrapped and checked as its embedded IPv4 (issue #2026).

        On CPython 3.11 the IPv6 ``is_private`` / ``_CGNAT_NETWORK`` checks do
        NOT reflect the mapped IPv4 for the CGNAT-mapped form, so a resolver
        returning ``::ffff:100.64.0.1`` (or a mapped private/loopback/metadata
        address) would otherwise slip past every check. ``_assert_public_ip``
        unwraps ``ipv4_mapped`` first, so all of these are rejected
        version-independently.
        """
        with patch(
            "socket.getaddrinfo",
            side_effect=_fake_getaddrinfo(mapped_ip),
        ):
            with pytest.raises(SSRFValidationError, match="non-public"):
                _assert_public_ip(ALLOWED_HOST)

    @pytest.mark.parametrize(
        "tunnel_ip",
        [
            "64:ff9b::10.0.0.1",  # NAT64 well-known prefix (RFC 6052) -> 10.0.0.1
            "64:ff9b:1::a00:1",  # NAT64 local prefix (RFC 8215) -> 10.0.0.1
            "2002:6440:1::",  # 6to4 (RFC 3056) embedding CGNAT 100.64.0.1
            "2002:c0a8:0101::",  # 6to4 embedding 192.168.1.1
            "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo (RFC 4380)
            "::100.64.0.1",  # deprecated IPv4-compatible (::/96), CGNAT payload
        ],
    )
    def test_ipv6_embedded_ipv4_tunnels_rejected(self, tunnel_ip):
        """NAT64 / 6to4 / Teredo / IPv4-compatible forms are rejected (issue #2049).

        Unlike IPv4-mapped IPv6 (which needs the explicit ``ipv4_mapped`` unwrap
        because a mapped CGNAT address reports ``is_private=False``), CPython
        already classifies these whole prefixes as ``is_private`` / ``is_reserved``
        — verified on 3.11 and 3.12 — so the property denylist covers them without
        any per-form extraction. This pins that coverage: if a future Python ever
        stopped classifying one of these prefixes, this test would fail rather than
        silently opening an SSRF hole. (Counters the review claim that these forms
        bypass the guard; e.g. ``2002:0a00:0001::`` reports ``is_private=True``,
        not False.)
        """
        with patch(
            "socket.getaddrinfo",
            side_effect=_fake_getaddrinfo(tunnel_ip),
        ):
            with pytest.raises(SSRFValidationError, match="non-public"):
                _assert_public_ip(ALLOWED_HOST)


# ─────────────────────────────────────────────────────────────────────────────
# safe_fetch_bytes — redirect re-validation
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFetchBytesRedirect:
    def test_empty_location_header_rejected(self):
        """A redirect status with a present-but-empty Location fails fast.

        ``Location: `` (header present, value empty) would otherwise resolve to
        the current URL and loop to the redirect cap with a misleading "exceeded
        N redirects". It now raises a clear empty-Location error on the first hop.
        """

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(302, b"", {"location": ""})

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(SSRFValidationError, match="empty Location"):
                    safe_fetch_bytes(ALLOWED_URL)

    @pytest.mark.parametrize("status_code", [301, 304])
    def test_non_location_3xx_not_looped_but_raises(self, status_code):
        """A 3xx WITHOUT a Location is not looped — it falls through to raise_for_status.

        httpx reports ``is_redirect=True`` for any 3xx (including 304/a malformed
        301 with no Location); keying off ``has_redirect_location`` means such a
        response is NOT followed as a redirect. It then reaches ``raise_for_status``,
        which raises for any non-2xx — so the function raises ``HTTPStatusError``
        rather than looping to the redirect cap (the old ``is_redirect`` behaviour)
        or silently returning a body.
        """

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(status_code, b"")  # no Location header

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(httpx.HTTPStatusError):
                    safe_fetch_bytes(ALLOWED_URL)

    def test_capital_location_header_is_followed(self):
        """A capital-L ``Location`` (the conventional casing) is honoured.

        Real httpx headers are case-insensitive; this pins that ``_mock_stream``
        matches, so a future redirect test written with ``{"Location": ...}`` is
        not silently a no-op (``has_redirect_location`` False).
        """
        call_count = 0

        def _stream_dispatch(self_client, method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_stream(302, b"", {"Location": f"https://{ALLOWED_HOST}/x"})
            return _mock_stream(200, b"final")

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                body, _ = safe_fetch_bytes(ALLOWED_URL)
        assert body == b"final"
        assert call_count == 2, "the capital-L redirect must actually be followed"

    def test_redirect_to_private_ip_literal_rejected_by_allowlist(self):
        """A redirect to a private-IP *literal* (``https://127.0.0.1/``) is rejected.

        Note this is caught at the ALLOWLIST layer: ``127.0.0.1`` is not in
        ``PUBLIC_DOMAIN_SOURCE_HOSTS`` so ``validate_url`` rejects it before
        ``_assert_public_ip`` runs. The IP layer for an *allowlisted* host that
        resolves private is exercised separately by
        ``test_redirect_to_allowlisted_host_resolving_private_rejected``.
        """
        redirect_target = "https://127.0.0.1/"

        def _stream_dispatch(self_client, method, url, **kwargs):
            if urlparse(str(url)).hostname == ALLOWED_HOST:
                return _mock_stream(302, b"", {"location": redirect_target})
            return _mock_stream(200, b"ok")

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(SSRFValidationError, match="allowlist"):
                    safe_fetch_bytes(ALLOWED_URL)

    def test_redirect_to_allowlisted_host_resolving_private_rejected(self):
        """The real threat: a redirect to an ALLOWLISTED host that DNS-resolves to a
        private IP must be rejected by the IP check, not just the allowlist.

        Hop 1 (uscode.house.gov) resolves public and 302-redirects to another
        allowlisted host (ecfr.gov); that host then resolves to a private IP. The
        rejection must come from ``_assert_public_ip`` (``match="non-public"``),
        which is exactly the redirect-hop rebind surface this guard exists for.
        """

        def _getaddrinfo(host, port, *args, **kwargs):
            # The redirect target (ecfr.gov) resolves private; hop-1 host public.
            ip = "127.0.0.1" if "ecfr" in host else "1.1.1.1"
            return [(socket.AF_INET, 1, 6, "", (ip, 0))]

        def _stream_dispatch(self_client, method, url, **kwargs):
            if urlparse(str(url)).hostname == ALLOWED_HOST:
                return _mock_stream(302, b"", {"location": "https://www.ecfr.gov/x"})
            return _mock_stream(200, b"ok")

        with patch("socket.getaddrinfo", side_effect=_getaddrinfo):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(SSRFValidationError, match="non-public"):
                    safe_fetch_bytes(ALLOWED_URL)

    def test_redirect_to_non_allowlisted_host_rejected(self):
        """Redirect to a non-allowlisted public host must also be rejected."""

        def _stream_dispatch(self_client, method, url, **kwargs):
            # Match the host EXACTLY rather than `"house.gov" in url`: a
            # substring test is not airtight — it would also match URLs like
            # https://evil.com/?ref=house.gov or https://house.gov.evil.com/ and
            # misroute the mock. Parsing the host mirrors how the production
            # allowlist (validate_url -> urlparse().hostname) actually decides,
            # so the dispatcher only fires for the genuine first hop.
            if urlparse(str(url)).hostname == ALLOWED_HOST:
                return _mock_stream(302, b"", {"location": "https://evil.com/x"})
            return _mock_stream(200, b"ok")

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(SSRFValidationError, match="allowlist"):
                    safe_fetch_bytes(ALLOWED_URL)


# ─────────────────────────────────────────────────────────────────────────────
# safe_fetch_bytes — redirect-count cap (MAX_REDIRECTS exhaustion)
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFetchBytesRedirectCap:
    def test_redirect_chain_exhaustion_raises(self):
        """More than ``MAX_REDIRECTS`` consecutive redirects must raise, not loop.

        Every hop redirects to another *allowlisted* path so that ONLY the
        redirect-count cap (not an allowlist or IP failure) can terminate the
        loop — proving the ``range(MAX_REDIRECTS + 1)`` bound is what stops it.
        """

        def _always_redirect(self_client, method, url, **kwargs):
            return _mock_stream(302, b"", {"location": f"https://{ALLOWED_HOST}/next"})

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _always_redirect):
                with pytest.raises(SSRFValidationError, match="redirects"):
                    safe_fetch_bytes(ALLOWED_URL)

    def test_max_redirects_followed_then_success(self):
        """A chain of exactly ``MAX_REDIRECTS`` hops then a 200 must succeed."""
        call_count = 0

        def _stream_dispatch(self_client, method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= MAX_REDIRECTS:
                return _mock_stream(302, b"", {"location": f"https://{ALLOWED_HOST}/h"})
            return _mock_stream(200, b"final")

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                body, host = safe_fetch_bytes(ALLOWED_URL)
        assert body == b"final"
        assert host == ALLOWED_HOST


# ─────────────────────────────────────────────────────────────────────────────
# safe_fetch_bytes — default User-Agent (caller header overrides)
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFetchBytesUserAgent:
    @staticmethod
    def _capture_headers(captured: dict):
        def _stream_dispatch(self_client, method, url, **kwargs):
            captured["headers"] = kwargs.get("headers")
            return _mock_stream(200, b"ok")

        return _stream_dispatch

    def test_default_user_agent_applied_when_none_supplied(self):
        captured: dict = {}
        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", self._capture_headers(captured)):
                safe_fetch_bytes(ALLOWED_URL)
        assert "OpenContracts" in captured["headers"]["User-Agent"]

    def test_caller_user_agent_overrides_default(self):
        captured: dict = {}
        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", self._capture_headers(captured)):
                safe_fetch_bytes(ALLOWED_URL, headers={"User-Agent": "custom-agent/9"})
        assert captured["headers"]["User-Agent"] == "custom-agent/9"

    def test_caller_headers_preserved_alongside_default_ua(self):
        """A caller header that is not User-Agent coexists with the default UA."""
        captured: dict = {}
        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", self._capture_headers(captured)):
                safe_fetch_bytes(ALLOWED_URL, headers={"Accept": "application/json"})
        assert captured["headers"]["Accept"] == "application/json"
        assert "OpenContracts" in captured["headers"]["User-Agent"]

    def test_caller_user_agent_override_is_case_insensitive(self):
        """A lowercase caller ``user-agent`` overrides the default, not duplicates it.

        The merge target is ``httpx.Headers`` (case-insensitive), so a caller
        header in any casing collapses onto the single canonical ``User-Agent``
        line rather than emitting two conflicting ones.
        """
        captured: dict = {}
        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", self._capture_headers(captured)):
                safe_fetch_bytes(ALLOWED_URL, headers={"user-agent": "lower-cased/1"})
        assert captured["headers"]["User-Agent"] == "lower-cased/1"
        ua_lines = [k for k, _ in captured["headers"].raw if k.lower() == b"user-agent"]
        assert len(ua_lines) == 1, f"expected exactly one User-Agent line: {ua_lines}"

    def test_user_agent_forwarded_on_every_redirect_hop(self):
        """The UA is sent on the post-redirect hop too, not just the first.

        ``request_headers`` is built once before the redirect loop and reused on
        every hop. This captures the headers on each hop and asserts the UA is
        present on the second (post-redirect) request — so a future refactor that
        moved header construction into the loop, or reverted to ``headers=headers``
        after a redirect, would be caught.
        """
        seen_user_agents: list = []

        def _stream_dispatch(self_client, method, url, **kwargs):
            seen_user_agents.append((kwargs.get("headers") or {}).get("User-Agent"))
            if len(seen_user_agents) == 1:  # first hop → redirect to an allowed path
                return _mock_stream(302, b"", {"location": f"https://{ALLOWED_HOST}/n"})
            return _mock_stream(200, b"ok")  # second hop → final response

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                safe_fetch_bytes(ALLOWED_URL)

        assert len(seen_user_agents) == 2, "expected one redirect hop + the final hop"
        assert all(
            "OpenContracts" in (ua or "") for ua in seen_user_agents
        ), f"User-Agent missing on a hop: {seen_user_agents}"


# ─────────────────────────────────────────────────────────────────────────────
# safe_fetch_bytes — cross-host redirect credential stripping (RFC 9110 §15.4)
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFetchBytesCredentialStripping:
    def test_credentials_stripped_on_cross_host_redirect(self):
        """Authorization/Cookie are dropped when a redirect crosses to a new host.

        httpx forwards request headers verbatim across origins; safe_fetch_bytes
        strips per-service credentials so a caller's Authorization/Cookie cannot
        leak from one allowlisted .gov host to another (here uscode.house.gov ->
        www.ecfr.gov, both allowlisted).
        """
        captured: list = []

        def _dispatch(self_client, method, url, **kwargs):
            captured.append(kwargs.get("headers"))
            if len(captured) == 1:  # first hop → cross-host redirect
                return _mock_stream(302, b"", {"location": "https://www.ecfr.gov/x"})
            return _mock_stream(200, b"ok")

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _dispatch):
                safe_fetch_bytes(
                    ALLOWED_URL,
                    headers={"Authorization": "Bearer secret", "Cookie": "sid=1"},
                )

        # Hop 1 (original host) carries the credentials; hop 2 (new host) must not.
        assert captured[0].get("Authorization") == "Bearer secret"
        assert "Authorization" not in captured[1]
        assert "Cookie" not in captured[1]
        # The default User-Agent still travels to the redirect target.
        assert "OpenContracts" in captured[1].get("User-Agent", "")

    def test_credentials_preserved_on_same_host_redirect(self):
        """A same-host redirect keeps the credentials — no cross-origin leak occurs."""
        captured: list = []

        def _dispatch(self_client, method, url, **kwargs):
            captured.append(kwargs.get("headers"))
            if len(captured) == 1:  # first hop → SAME-host redirect
                return _mock_stream(302, b"", {"location": f"https://{ALLOWED_HOST}/n"})
            return _mock_stream(200, b"ok")

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _dispatch):
                safe_fetch_bytes(ALLOWED_URL, headers={"Authorization": "Bearer s"})

        assert captured[1].get("Authorization") == "Bearer s"

    def test_credentials_stripped_on_cross_port_redirect(self):
        """A same-host but different-PORT redirect is cross-origin → strip credentials.

        ``netloc`` (host AND port) is compared, so ``uscode.house.gov`` ->
        ``uscode.house.gov:9000`` counts as a different service. (``.host`` alone
        would miss it.)
        """
        captured: list = []

        def _dispatch(self_client, method, url, **kwargs):
            captured.append(kwargs.get("headers"))
            if len(captured) == 1:  # first hop → same host, different port
                return _mock_stream(
                    302, b"", {"location": f"https://{ALLOWED_HOST}:9000/p"}
                )
            return _mock_stream(200, b"ok")

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _dispatch):
                safe_fetch_bytes(ALLOWED_URL, headers={"Authorization": "Bearer s"})

        assert "Authorization" not in captured[1]


# ─────────────────────────────────────────────────────────────────────────────
# safe_fetch_bytes — size cap
# ─────────────────────────────────────────────────────────────────────────────

SMALL_CAP = 10  # bytes — tiny cap for tests so we don't allocate 500 MB


class TestSafeFetchBytesSize:
    def test_content_length_over_cap_rejected(self):
        """A Content-Length header exceeding the cap must be rejected before streaming."""

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(
                200,
                b"x" * 5,
                {"content-length": str(SMALL_CAP + 1)},
            )

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(SSRFValidationError, match="content-length"):
                    safe_fetch_bytes(ALLOWED_URL, max_bytes=SMALL_CAP)

    def test_streamed_bytes_over_cap_rejected(self):
        """Actual streamed bytes exceeding the cap must be rejected mid-stream."""

        def _stream_dispatch(self_client, method, url, **kwargs):
            # Body larger than the cap, no Content-Length header
            return _mock_stream(200, b"x" * (SMALL_CAP + 5))

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(SSRFValidationError, match="exceeded size cap"):
                    safe_fetch_bytes(ALLOWED_URL, max_bytes=SMALL_CAP)

    def test_body_within_cap_succeeds(self):
        body = b"hello"

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(200, body)

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                result, host = safe_fetch_bytes(ALLOWED_URL, max_bytes=SMALL_CAP)
        assert result == body
        assert host == ALLOWED_HOST


# ─────────────────────────────────────────────────────────────────────────────
# Happy-path: safe_fetch_bytes and safe_fetch_text
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFetchBytesHappyPath:
    def test_returns_body_and_host(self):
        body = b"<law>text</law>"

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(200, body)

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                result, host = safe_fetch_bytes(ALLOWED_URL)
        assert result == body
        assert host == ALLOWED_HOST

    def test_fetch_text_decodes_utf8(self):
        body = "Section 1. — café".encode()

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(200, body)

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                text, host = safe_fetch_text(ALLOWED_URL)
        assert "café" in text
        assert host == ALLOWED_HOST

    def test_fetch_text_replaces_invalid_bytes(self):
        """Non-UTF-8 bytes must be replaced, not raise."""
        body = b"good \xff bad"

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(200, body)

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                text, _ = safe_fetch_text(ALLOWED_URL)
        assert "good" in text
        assert "�" in text  # replacement character for \xff


# ─────────────────────────────────────────────────────────────────────────────
# Multi-A-record: ALL addresses are checked, not just the first
# ─────────────────────────────────────────────────────────────────────────────


class TestMultiARecord:
    def test_private_second_record_rejected(self):
        """If one A-record is public but another is private, validation must fail.

        This proves that ``_assert_public_ip`` iterates ALL resolved addresses
        rather than stopping at the first public one — closing the multi-A-record
        / partial-rebind window.
        """

        def _mixed_getaddrinfo(host, port, *args, **kwargs):
            # First address: public (1.1.1.1), second: private (10.0.0.1)
            return [
                (2, 1, 6, "", ("1.1.1.1", 0)),
                (2, 1, 6, "", ("10.0.0.1", 0)),
            ]

        with patch("socket.getaddrinfo", side_effect=_mixed_getaddrinfo):
            with pytest.raises(SSRFValidationError, match="non-public"):
                _assert_public_ip(ALLOWED_HOST)

    def test_all_public_records_pass(self):
        """Multiple public A-records must all pass validation."""

        def _all_public(host, port, *args, **kwargs):
            return [
                (2, 1, 6, "", ("1.1.1.1", 0)),
                (2, 1, 6, "", ("8.8.8.8", 0)),
            ]

        with patch("socket.getaddrinfo", side_effect=_all_public):
            _assert_public_ip(ALLOWED_HOST)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Malformed Content-Length: non-integer value raises SSRFValidationError
# ─────────────────────────────────────────────────────────────────────────────


class TestMalformedContentLength:
    def test_non_integer_content_length_raises(self):
        """A Content-Length header with a non-integer value must raise SSRFValidationError.

        Protects against servers returning Content-Length: "chunked" or other
        malformed values that would previously cause a ValueError crash at ``int(cl)``.
        """

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(200, b"hello", {"content-length": "not-a-number"})

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(
                    SSRFValidationError, match="malformed content-length"
                ):
                    safe_fetch_bytes(ALLOWED_URL)

    def test_negative_content_length_raises(self):
        """A negative Content-Length (e.g. -1) parses but must be rejected as malformed.

        ``int("-1")`` succeeds and ``-1 > max_bytes`` is False, so without an
        explicit guard the header fast-fail would be skipped for negative values.
        """

        def _stream_dispatch(self_client, method, url, **kwargs):
            return _mock_stream(200, b"hi", {"content-length": "-1"})

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(
                    SSRFValidationError, match="negative content-length"
                ):
                    safe_fetch_bytes(ALLOWED_URL)

    def test_none_content_length_not_checked(self):
        """Absent Content-Length header must not raise; the streamed-bytes cap applies."""
        body = b"short body"

        def _stream_dispatch(self_client, method, url, **kwargs):
            # No content-length header
            return _mock_stream(200, body)

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                result, _ = safe_fetch_bytes(ALLOWED_URL)
        assert result == body


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_allowlist — fail-closed to the hardcoded baseline
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveAllowlistBaselineFallback:
    """With no dynamic provider registered, the effective allowlist is exactly
    the hardcoded ``PUBLIC_DOMAIN_SOURCE_HOSTS`` baseline (fail-closed)."""

    @contextmanager
    def _no_provider(self):
        # The app installs the pack-aware provider at startup; drop it for the
        # duration of the test and always restore the original afterwards.
        original = _safe_http_module._allowlist_provider
        register_allowlist_provider(None)
        try:
            yield
        finally:
            register_allowlist_provider(original)

    def test_resolves_to_baseline_without_provider(self):
        with self._no_provider():
            assert _resolve_allowlist(None) is PUBLIC_DOMAIN_SOURCE_HOSTS
            # And host checks fall through to the baseline set.
            assert host_on_allowlist(ALLOWED_HOST)
            assert not host_on_allowlist("tcpbolivia.bo")  # pack host, not baseline

    def test_explicit_allowlist_overrides_even_without_provider(self):
        with self._no_provider():
            custom = frozenset({"example.gov"})
            assert _resolve_allowlist(custom) is custom


# ─────────────────────────────────────────────────────────────────────────────
# DNS pinning (issue #2048) — connect must target the VALIDATED address, never
# a second, independently-resolved one.
# ─────────────────────────────────────────────────────────────────────────────


class TestDNSPinning:
    """Proves ``safe_fetch_bytes`` pins the real TCP connection to the address
    ``_assert_public_ip`` already validated, instead of letting httpx/httpcore
    resolve the hostname again independently at connect time.

    Unlike every other test in this file (which mocks ``httpx.Client.stream``
    and therefore never reaches the transport layer at all), this test lets the
    REAL ``httpx``/``httpcore`` request path run all the way down to
    ``HTTPConnection._connect`` — the lowest point before an actual socket
    would be opened — and intercepts only there, so the assertions are about
    genuine transport-level behaviour, not about what argument was handed to a
    mocked-away ``stream()`` call.
    """

    VALIDATED_IP = "1.1.1.1"  # a real public address (Cloudflare DNS)
    REBIND_IP = "127.0.0.1"  # what a second, independent resolution could return

    def _rebinding_getaddrinfo(self, host, port, *args, **kwargs):
        self._getaddrinfo_calls += 1
        ip = self.VALIDATED_IP if self._getaddrinfo_calls == 1 else self.REBIND_IP
        return [(socket.AF_INET, 1, 6, "", (ip, 0))]

    def test_connect_targets_the_validated_ip_not_a_fresh_resolution(self):
        """Simulate a DNS rebind: the FIRST ``getaddrinfo`` call (made during
        ``_assert_public_ip`` validation) returns a public-looking address; ANY
        further call would return a private "rebound" address instead. If
        ``safe_fetch_bytes`` handed httpx the bare hostname (the pre-fix
        behaviour) rather than the pinned IP, httpx/httpcore would resolve the
        host again at connect time and this second call would return the
        rebind address — exactly the TOCTOU window issue #2048 closes.
        """
        self._getaddrinfo_calls = 0
        captured: dict = {}

        def _spy_connect(self_conn, request):
            # ``self_conn._origin.host`` is exactly what httpcore's connection
            # pool uses to open the TCP socket (see HTTPConnection._connect —
            # ``self._network_backend.connect_tcp(host=self._origin.host, ...)``).
            captured["origin_host"] = self_conn._origin.host.decode("ascii")
            captured["sni_hostname"] = request.extensions.get("sni_hostname")
            # Abort BEFORE any real socket/network I/O; the test only cares
            # about what target httpcore was about to connect to.
            raise RuntimeError("stop-before-real-network-io")

        with patch("socket.getaddrinfo", side_effect=self._rebinding_getaddrinfo):
            with patch(
                "httpcore._sync.connection.HTTPConnection._connect", _spy_connect
            ):
                with pytest.raises(RuntimeError, match="stop-before-real-network-io"):
                    safe_fetch_bytes(ALLOWED_URL)

        assert captured["origin_host"] == self.VALIDATED_IP, (
            "the TCP connect must target the address _assert_public_ip already "
            f"validated, not a fresh resolution; got {captured['origin_host']!r}"
        )
        assert captured["origin_host"] != self.REBIND_IP
        assert captured["origin_host"] != ALLOWED_HOST, (
            "the connection target must be the pinned IP literal, not the "
            "hostname (which would let httpx/httpcore re-resolve it)"
        )
        assert captured["sni_hostname"] == ALLOWED_HOST, (
            "TLS SNI / certificate-verification name must stay the ORIGINAL "
            "hostname so certificate validation and server-side vhost routing "
            "keep working even though the TCP layer connects to the pinned IP"
        )
        assert self._getaddrinfo_calls == 1, (
            "getaddrinfo must be called exactly once per hop — safe_fetch_bytes "
            "must hand httpx the pinned IP directly rather than letting it "
            "re-resolve the hostname a second time at connect time"
        )

    def test_public_native_ipv6_address_is_pinned_correctly(self):
        """The pinning path must also work for a native IPv6 validated address
        (not just IPv4), including passing it through as a valid httpx URL host.
        """
        ipv6_ip = "2606:4700:4700::1111"  # Cloudflare public DNS, public IPv6
        captured: dict = {}

        def _ipv6_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET6, 1, 6, "", (ipv6_ip, 0, 0, 0))]

        def _spy_connect(self_conn, request):
            captured["origin_host"] = self_conn._origin.host.decode("ascii")
            raise RuntimeError("stop-before-real-network-io")

        with patch("socket.getaddrinfo", side_effect=_ipv6_getaddrinfo):
            with patch(
                "httpcore._sync.connection.HTTPConnection._connect", _spy_connect
            ):
                with pytest.raises(RuntimeError, match="stop-before-real-network-io"):
                    safe_fetch_bytes(ALLOWED_URL)

        assert captured["origin_host"] == ipv6_ip


class TestDNSPinningPerHopIndependence:
    """Each redirect hop must be pinned to ITS OWN freshly-validated address —
    a new host reached via redirect must never reuse a previous hop's pin.

    This drives the redirect chain with the same ``httpx.Client.stream`` mock
    pattern used everywhere else in this file (cheap, no transport-level
    plumbing needed here) and instead records the arguments every
    ``_DNSPinnedTransport`` was constructed with, one per hop.
    """

    def test_redirect_hop_gets_a_fresh_pin_for_the_new_host(self):
        redirect_target_host = "www.ecfr.gov"

        def _host_specific_getaddrinfo(host, port, *args, **kwargs):
            ip = "1.1.1.1" if host == ALLOWED_HOST else "8.8.8.8"
            return [(socket.AF_INET, 1, 6, "", (ip, 0))]

        pins: list[tuple[str, str]] = []
        # Capture the REAL class before patching the module attribute below —
        # the factory must delegate to the original transport, not to itself
        # (patching ``_DNSPinnedTransport`` in place means the bare name would
        # otherwise resolve back to this very factory and recurse forever).
        real_transport_cls = _safe_http_module._DNSPinnedTransport

        def _recording_transport_factory(*, pinned_ip: str, sni_hostname: str):
            pins.append((pinned_ip, sni_hostname))
            return real_transport_cls(pinned_ip=pinned_ip, sni_hostname=sni_hostname)

        def _stream_dispatch(self_client, method, url, **kwargs):
            if urlparse(str(url)).hostname == ALLOWED_HOST:
                return _mock_stream(
                    302, b"", {"location": f"https://{redirect_target_host}/x"}
                )
            return _mock_stream(200, b"ok")

        with patch("socket.getaddrinfo", side_effect=_host_specific_getaddrinfo):
            with patch.object(
                _safe_http_module, "_DNSPinnedTransport", _recording_transport_factory
            ):
                with patch("httpx.Client.stream", _stream_dispatch):
                    body, host = safe_fetch_bytes(ALLOWED_URL)

        assert body == b"ok"
        assert host == redirect_target_host
        assert pins == [
            ("1.1.1.1", ALLOWED_HOST),
            ("8.8.8.8", redirect_target_host),
        ], "each hop must be pinned to its OWN validated host/IP pair"
