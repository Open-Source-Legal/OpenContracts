"""Unit tests for FederalRegisterAuthoritySourceProvider.

All HTTP is mocked — no network calls are made.  Fixtures are loaded from
``opencontractserver/tests/fixtures/authority_sources/``.

Test coverage:
  - _locate_impl: URL, citation, and extra derivation (pure).
  - can_handle: matching and non-matching prefixes.
  - _fetch_impl: step 1 mocked via requests.get (no-follow redirect); step 2
    mocked via safe_fetch_bytes; step 3 mocked via safe_fetch_text (both
    SSRF-safe helpers that re-validate every redirect hop):
      (1) citation redirect (302 + Location header) — requests.get,
      (2) document JSON — safe_fetch_bytes,
      (3) raw-text body — safe_fetch_text.
  - Fall-back to ``abstract`` when step-3 safe_fetch_text raises.
  - Step-2 SSRF block (off-allowlist redirect hop) propagates, not swallowed.
  - Registry discovery: fedreg handler visible via
    get_all_authority_source_providers_cached().
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.authority_source_providers.federal_register_provider import (
    _FR_API_BASE,
    FederalRegisterAuthoritySourceProvider,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
)
from opencontractserver.pipeline.registry import (
    get_all_authority_source_providers_cached,
    reset_registry,
)

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "authority_sources"

_FIXTURE_JSON_TEXT = (FIXTURE_DIR / "fedreg_2023-00485.json").read_text()
_FIXTURE_JSON = json.loads(_FIXTURE_JSON_TEXT)
_FIXTURE_BODY = (FIXTURE_DIR / "fedreg_2023-00485.txt").read_text()

# Location header value the redirect mock returns.
_REDIRECT_LOCATION = (
    "/documents/2023/01/13/2023-00485/"
    "gulf-of-mexico-ocs-oil-and-gas-lease-sales-259-and-261"
)


def _make_redirect_mock() -> MagicMock:
    """Return a mock simulating the 302 citation redirect."""
    m = MagicMock()
    m.status_code = 302
    m.headers = {"Location": _REDIRECT_LOCATION}
    m.raise_for_status = MagicMock()
    return m


def _json_bytes(doc: dict = _FIXTURE_JSON) -> tuple[bytes, str]:
    """Return a ``(body_bytes, host)`` pair as ``safe_fetch_bytes`` would for step 2."""
    return json.dumps(doc).encode("utf-8"), "www.federalregister.gov"


class TestFederalRegisterLocateImpl(SimpleTestCase):
    """Pure tests for _locate_impl — no I/O, no mocking."""

    def setUp(self):
        self.provider = FederalRegisterAuthoritySourceProvider()

    def test_locate_returns_authority_request(self):
        req = self.provider._locate_impl("fedreg:88.1722")
        self.assertIsInstance(req, AuthorityRequest)

    def test_locate_canonical_key(self):
        req = self.provider._locate_impl("fedreg:88.1722")
        self.assertEqual(req.canonical_key, "fedreg:88.1722")

    def test_locate_url_is_step1_citation_redirect(self):
        req = self.provider._locate_impl("fedreg:88.1722")
        self.assertEqual(req.url, f"{_FR_API_BASE}/citation/88-FR-1722")

    def test_locate_citation_format(self):
        req = self.provider._locate_impl("fedreg:88.1722")
        self.assertEqual(req.citation, "88 FR 1722")

    def test_locate_extra_volume(self):
        req = self.provider._locate_impl("fedreg:88.1722")
        self.assertEqual(req.extra.get("volume"), "88")

    def test_locate_extra_page(self):
        req = self.provider._locate_impl("fedreg:88.1722")
        self.assertEqual(req.extra.get("page"), "1722")

    def test_locate_alternate_key(self):
        req = self.provider._locate_impl("fedreg:88.2371")
        self.assertEqual(req.url, f"{_FR_API_BASE}/citation/88-FR-2371")
        self.assertEqual(req.citation, "88 FR 2371")


class TestFederalRegisterCanHandle(SimpleTestCase):
    """Tests for can_handle prefix matching."""

    def setUp(self):
        self.provider = FederalRegisterAuthoritySourceProvider()

    def test_can_handle_fedreg(self):
        self.assertTrue(self.provider.can_handle("fedreg:88.1722"))

    def test_can_handle_fedreg_alternate_page(self):
        self.assertTrue(self.provider.can_handle("fedreg:88.2371"))

    def test_cannot_handle_usc(self):
        self.assertFalse(self.provider.can_handle("usc-15:1"))

    def test_cannot_handle_cfr(self):
        self.assertFalse(self.provider.can_handle("cfr-40:261.4"))

    def test_cannot_handle_dgcl(self):
        self.assertFalse(self.provider.can_handle("dgcl:145"))


_REQUESTS_GET_PATH = (
    "opencontractserver.pipeline.authority_source_providers."
    "federal_register_provider.requests.get"
)
_SAFE_FETCH_BYTES_PATH = (
    "opencontractserver.pipeline.authority_source_providers."
    "federal_register_provider.safe_fetch_bytes"
)
_SAFE_FETCH_TEXT_PATH = (
    "opencontractserver.pipeline.authority_source_providers."
    "federal_register_provider.safe_fetch_text"
)


@patch(_SAFE_FETCH_TEXT_PATH, return_value=(_FIXTURE_BODY, "www.federalregister.gov"))
@patch(_SAFE_FETCH_BYTES_PATH, return_value=_json_bytes())
@patch(_REQUESTS_GET_PATH, return_value=_make_redirect_mock())
class TestFederalRegisterFetchImpl(SimpleTestCase):
    """Tests for _fetch_impl.

    Step 1 (citation redirect) uses requests.get with ``allow_redirects=False``.
    Step 2 (doc JSON) uses safe_fetch_bytes (re-validates redirect hops).
    Step 3 (raw_text_url body) uses safe_fetch_text.

    Class-level @patch decorators supply the default happy-path mocks; tests that
    need a variant override the relevant mock's ``return_value`` in the body. The
    decorator-injected args arrive innermost-first: requests.get, safe_fetch_bytes,
    safe_fetch_text.
    """

    def test_fetch_returns_one_section(self, _mock_get, _mock_bytes, _mock_text):
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(len(sections), 1)

    def test_fetch_section_type(self, _mock_get, _mock_bytes, _mock_text):
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertIsInstance(sections[0], AuthoritySection)

    def test_fetch_key_from_json_citation(self, _mock_get, _mock_bytes, _mock_text):
        """Key is derived from the JSON citation field (authoritative page)."""
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        # JSON fixture has citation "88 FR 2371" → key "fedreg:88.2371"
        self.assertEqual(sections[0].key, "fedreg:88.2371")

    def test_fetch_heading_matches_json_title(self, _mock_get, _mock_bytes, _mock_text):
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(sections[0].heading, _FIXTURE_JSON["title"])

    def test_fetch_text_from_raw_body(self, _mock_get, _mock_bytes, _mock_text):
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(sections[0].text, _FIXTURE_BODY)

    def test_fetch_source_url_is_html_url(self, _mock_get, _mock_bytes, _mock_text):
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(sections[0].source_url, _FIXTURE_JSON["html_url"])

    def test_fetch_one_requests_get_call_made(
        self, mock_get: MagicMock, mock_bytes: MagicMock, _mock_text
    ):
        """Step 1 uses requests.get (once); step 2 uses safe_fetch_bytes (once)."""
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        provider._fetch_impl(req)
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_bytes.call_count, 1)

    def test_fetch_fallback_to_abstract_on_raw_text_failure(
        self, _mock_get, _mock_bytes, mock_text: MagicMock
    ):
        """If safe_fetch_text raises, text should fall back to the abstract."""
        mock_text.side_effect = Exception("connection error")
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].text, _FIXTURE_JSON["abstract"])

    def test_fetch_raises_on_bad_redirect_location(
        self, mock_get: MagicMock, _mock_bytes, _mock_text
    ):
        """A Location header with no recognisable document_number raises ValueError."""
        bad_redirect = MagicMock()
        bad_redirect.status_code = 302
        bad_redirect.headers = {"Location": "/unrecognised/path"}
        bad_redirect.raise_for_status = MagicMock()

        mock_get.return_value = bad_redirect
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        with self.assertRaises(ValueError):
            provider._fetch_impl(req)

    def test_fetch_raises_on_url_special_chars_in_doc_number(
        self, mock_get: MagicMock, _mock_bytes, _mock_text
    ):
        """A Location whose doc-number segment carries URL-special chars must raise.

        ``_LOCATION_DOC_NUMBER_RE`` restricts the capture to ``[\\w-]+`` so a
        malformed/attacker-influenced Location like
        ``/documents/2023/01/13/2023-00485?q=x/slug`` does not match (and raises
        ValueError) rather than silently interpolating ``2023-00485?q=x`` into the
        step-2 URL and hitting the wrong endpoint.
        """
        bad_redirect = MagicMock()
        bad_redirect.status_code = 302
        bad_redirect.headers = {"Location": "/documents/2023/01/13/2023-00485?q=x/s"}
        bad_redirect.raise_for_status = MagicMock()

        mock_get.return_value = bad_redirect
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        with self.assertRaises(ValueError):
            provider._fetch_impl(req)

    def test_step2_ssrf_block_propagates(
        self, _mock_get, mock_bytes: MagicMock, _mock_text
    ):
        """A blocked step-2 redirect hop (safe_fetch_bytes raises) must propagate.

        Regression for the HIGH review finding: step 2 previously used
        redirect-following requests.get, which would silently follow a redirect
        to a private/internal host. Routing step 2 through safe_fetch_bytes means
        an off-allowlist hop raises SSRFValidationError — and, unlike the step-3
        body fetch, it is NOT swallowed into an abstract fallback.
        """
        from opencontractserver.utils.safe_http import SSRFValidationError

        mock_bytes.side_effect = SSRFValidationError(
            "host '169.254.169.254' resolves to non-public address"
        )
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        with self.assertRaises(SSRFValidationError):
            provider._fetch_impl(req)


class TestFederalRegisterRegistryDiscovery(SimpleTestCase):
    """Confirm fedreg provider is visible via get_all_authority_source_providers_cached."""

    def setUp(self):
        reset_registry()

    def tearDown(self):
        reset_registry()

    def test_fedreg_handler_discovered(self):
        providers = get_all_authority_source_providers_cached()
        fedreg_handlers = [
            d
            for d in providers
            if d.component_class is not None
            and d.component_class().can_handle("fedreg:88.1722")
        ]
        self.assertTrue(
            len(fedreg_handlers) >= 1,
            "Expected at least one registered provider to handle 'fedreg:88.1722'",
        )


class TestFederalRegisterSecurity(SimpleTestCase):
    """Security tests for FederalRegisterAuthoritySourceProvider."""

    def setUp(self):
        self.provider = FederalRegisterAuthoritySourceProvider()

    def test_locate_rejects_non_digit_volume(self):
        """_locate_impl must raise ValueError for a non-digit volume."""
        with self.assertRaises(ValueError):
            self.provider._locate_impl("fedreg:abc.1722")

    def test_locate_rejects_non_digit_page(self):
        """_locate_impl must raise ValueError for a non-digit page."""
        with self.assertRaises(ValueError):
            self.provider._locate_impl("fedreg:88.abc")

    def test_locate_valid_digits_ok(self):
        """_locate_impl must not raise for valid digit volume and page."""
        req = self.provider._locate_impl("fedreg:88.2371")  # must not raise
        self.assertEqual(req.canonical_key, "fedreg:88.2371")

    def test_raw_text_url_offhost_falls_back_to_abstract(self):
        """safe_fetch_text raises SSRFValidationError for off-host raw_text_url;
        _fetch_impl must fall back to the abstract instead of propagating."""
        import json
        import pathlib

        from opencontractserver.utils.safe_http import SSRFValidationError

        fixture_json = json.loads(
            (
                pathlib.Path(__file__).parent
                / "fixtures"
                / "authority_sources"
                / "fedreg_2023-00485.json"
            ).read_text()
        )
        # Override raw_text_url to an off-host URL.
        fixture_json_offhost = dict(fixture_json)
        fixture_json_offhost["raw_text_url"] = "https://evil.attacker.example.com/steal"

        with patch(_REQUESTS_GET_PATH, return_value=_make_redirect_mock()):
            with patch(
                _SAFE_FETCH_BYTES_PATH, return_value=_json_bytes(fixture_json_offhost)
            ):
                with patch(
                    _SAFE_FETCH_TEXT_PATH,
                    side_effect=SSRFValidationError(
                        "host 'evil.attacker.example.com' not on "
                        "public-domain allowlist"
                    ),
                ):
                    req = self.provider._locate_impl("fedreg:88.1722")
                    sections = self.provider._fetch_impl(req)

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].text, fixture_json_offhost["abstract"])

    def test_raw_text_url_oversize_falls_back_to_abstract(self):
        """A size-cap SSRFValidationError on the step-3 body fetch degrades to abstract.

        Regression for issue #2026: the raw-text size cap now lives inside the
        SSRF-safe fetch helper, which raises ``SSRFValidationError`` when the
        body exceeds ``max_bytes`` (``content-length``/streamed bytes). This
        proves an oversize ``raw_text_url`` body still degrades to the abstract
        rather than propagating — the behaviour the removed
        ``test_fetch_oversize_raw_text_falls_back_to_abstract`` used to guard,
        now flowing through the same ``except SSRFValidationError`` branch as the
        off-host case above.
        """
        from opencontractserver.utils.safe_http import SSRFValidationError

        with patch(_REQUESTS_GET_PATH, return_value=_make_redirect_mock()):
            with patch(_SAFE_FETCH_BYTES_PATH, return_value=_json_bytes()):
                with patch(
                    _SAFE_FETCH_TEXT_PATH,
                    side_effect=SSRFValidationError(
                        "response exceeded size cap of 50000 bytes"
                    ),
                ):
                    req = self.provider._locate_impl("fedreg:88.1722")
                    sections = self.provider._fetch_impl(req)

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].text, _FIXTURE_JSON["abstract"])

    def test_malformed_citation_falls_back_to_request_key(self):
        """If JSON citation doesn't match FR regex, key falls back to request key."""
        import json
        import pathlib

        fixture_json = json.loads(
            (
                pathlib.Path(__file__).parent
                / "fixtures"
                / "authority_sources"
                / "fedreg_2023-00485.json"
            ).read_text()
        )
        fixture_json_bad = dict(fixture_json)
        fixture_json_bad["citation"] = "MALFORMED CITATION"

        with patch(_REQUESTS_GET_PATH, return_value=_make_redirect_mock()):
            with patch(
                _SAFE_FETCH_BYTES_PATH, return_value=_json_bytes(fixture_json_bad)
            ):
                with patch(
                    _SAFE_FETCH_TEXT_PATH,
                    return_value=(_FIXTURE_BODY, "www.federalregister.gov"),
                ):
                    req = self.provider._locate_impl("fedreg:88.1722")
                    sections = self.provider._fetch_impl(req)

        self.assertEqual(sections[0].key, "fedreg:88.1722")
