"""Tests for the SSRF-safe HTTP fetch helper.

No database required — these are pure-logic and mocked-network tests.
Run with:
    docker compose -f test.yml -p opencontracts run --rm django pytest \
        opencontractserver/tests/test_safe_http.py -q
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest

from opencontractserver.utils.safe_http import (
    SSRFValidationError,
    _assert_public_ip,
    host_on_allowlist,
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


def _fake_getaddrinfo_public(host, port, *args, **kwargs):
    """Simulate a public IP (1.1.1.1) for any host."""
    return [(2, 1, 6, "", ("1.1.1.1", 0))]


def _fake_getaddrinfo_private(ip_str):
    """Return a getaddrinfo patcher that resolves to *ip_str*."""

    def _inner(host, port, *args, **kwargs):
        return [(2, 1, 6, "", (ip_str, 0))]

    return _inner


def _fake_getaddrinfo_ipv6_loopback(host, port, *args, **kwargs):
    return [(10, 1, 6, "", ("::1", 0, 0, 0))]


@contextmanager
def _mock_stream(status_code: int, body: bytes = b"", headers: dict | None = None):
    """Context-manager factory returned by a mocked ``httpx.Client.stream``."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_redirect = status_code in (301, 302, 303, 307, 308)
    resp.has_redirect_location = resp.is_redirect
    resp.headers = MagicMock()
    hdr_dict = headers or {}
    resp.headers.get = lambda k, default=None: hdr_dict.get(k, default)
    resp.raise_for_status = MagicMock()

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
            side_effect=_fake_getaddrinfo_private(private_ip),
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

    def test_dns_failure_raises_ssrf_error(self):
        import socket as _socket

        with patch(
            "socket.getaddrinfo",
            side_effect=_socket.gaierror("NXDOMAIN"),
        ):
            with pytest.raises(SSRFValidationError, match="DNS resolution failed"):
                _assert_public_ip("nonexistent.host.invalid")


# ─────────────────────────────────────────────────────────────────────────────
# safe_fetch_bytes — redirect re-validation
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFetchBytesRedirect:
    def test_redirect_to_private_ip_rejected(self):
        """
        First hop: allowlisted host → 302 → Location: https://127.0.0.1/
        The redirect target must fail IP validation (SSRFValidationError).
        """
        redirect_target = "https://127.0.0.1/"

        call_count = 0

        @contextmanager
        def _stream_side_effect(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First hop: 302 redirect to a private IP URL
                yield from [
                    _mock_stream(302, b"", {"location": redirect_target})
                ].__iter__()
            else:
                # Should never reach a second network call
                yield from [_mock_stream(200, b"ok")].__iter__()

        def _stream_dispatch(self_client, method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_stream(302, b"", {"location": redirect_target})
            return _mock_stream(200, b"ok")

        with patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo_public):
            with patch("httpx.Client.stream", _stream_dispatch):
                with pytest.raises(SSRFValidationError):
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
