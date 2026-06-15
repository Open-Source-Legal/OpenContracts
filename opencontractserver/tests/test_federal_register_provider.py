"""Unit tests for FederalRegisterAuthoritySourceProvider.

All HTTP is mocked — no network calls are made.  Fixtures are loaded from
``opencontractserver/tests/fixtures/authority_sources/``.

Test coverage:
  - _locate_impl: URL, citation, and extra derivation (pure).
  - can_handle: matching and non-matching prefixes.
  - _fetch_impl: three mocked requests.get calls in sequence:
      (1) citation redirect (302 + Location header),
      (2) document JSON,
      (3) raw-text body.
  - Fall-back to ``abstract`` when the raw-text GET raises.
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


def _make_json_mock() -> MagicMock:
    """Return a mock simulating the document JSON response."""
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = _FIXTURE_JSON
    m.raise_for_status = MagicMock()
    return m


def _make_raw_text_mock() -> MagicMock:
    """Return a mock simulating the raw plain-text body response."""
    m = MagicMock()
    m.status_code = 200
    m.text = _FIXTURE_BODY
    m.raise_for_status = MagicMock()
    return m


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


class TestFederalRegisterFetchImpl(SimpleTestCase):
    """Tests for _fetch_impl with three mocked requests.get calls."""

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_returns_one_section(self, mock_get: MagicMock):
        mock_get.side_effect = [
            _make_redirect_mock(),
            _make_json_mock(),
            _make_raw_text_mock(),
        ]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(len(sections), 1)

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_section_type(self, mock_get: MagicMock):
        mock_get.side_effect = [
            _make_redirect_mock(),
            _make_json_mock(),
            _make_raw_text_mock(),
        ]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertIsInstance(sections[0], AuthoritySection)

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_key_from_json_citation(self, mock_get: MagicMock):
        """Key is derived from the JSON citation field (authoritative page)."""
        mock_get.side_effect = [
            _make_redirect_mock(),
            _make_json_mock(),
            _make_raw_text_mock(),
        ]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        # JSON fixture has citation "88 FR 2371" → key "fedreg:88.2371"
        self.assertEqual(sections[0].key, "fedreg:88.2371")

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_heading_matches_json_title(self, mock_get: MagicMock):
        mock_get.side_effect = [
            _make_redirect_mock(),
            _make_json_mock(),
            _make_raw_text_mock(),
        ]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(sections[0].heading, _FIXTURE_JSON["title"])

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_text_from_raw_body(self, mock_get: MagicMock):
        mock_get.side_effect = [
            _make_redirect_mock(),
            _make_json_mock(),
            _make_raw_text_mock(),
        ]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(sections[0].text, _FIXTURE_BODY)

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_source_url_is_html_url(self, mock_get: MagicMock):
        mock_get.side_effect = [
            _make_redirect_mock(),
            _make_json_mock(),
            _make_raw_text_mock(),
        ]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(sections[0].source_url, _FIXTURE_JSON["html_url"])

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_three_requests_made(self, mock_get: MagicMock):
        """Exactly three GET calls should be made for a successful fetch."""
        mock_get.side_effect = [
            _make_redirect_mock(),
            _make_json_mock(),
            _make_raw_text_mock(),
        ]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        provider._fetch_impl(req)
        self.assertEqual(mock_get.call_count, 3)

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_fallback_to_abstract_on_raw_text_failure(self, mock_get: MagicMock):
        """If the raw-text GET raises, text should fall back to the abstract."""
        # side_effect list entries are either return values (MagicMock instances)
        # or exceptions to raise.  Use the exception class/instance directly so
        # mock_get raises it on the third call.
        mock_get.side_effect = [
            _make_redirect_mock(),
            _make_json_mock(),
            Exception("connection error"),
        ]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        sections = provider._fetch_impl(req)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].text, _FIXTURE_JSON["abstract"])

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_fetch_raises_on_bad_redirect_location(self, mock_get: MagicMock):
        """A Location header with no recognisable document_number raises ValueError."""
        bad_redirect = MagicMock()
        bad_redirect.status_code = 302
        bad_redirect.headers = {"Location": "/unrecognised/path"}
        bad_redirect.raise_for_status = MagicMock()

        mock_get.side_effect = [bad_redirect]
        provider = FederalRegisterAuthoritySourceProvider()
        req = provider._locate_impl("fedreg:88.1722")
        with self.assertRaises(ValueError):
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

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_raw_text_url_offhost_falls_back_to_abstract(self, mock_get: "MagicMock"):
        """raw_text_url on a non-federalregister.gov host must NOT be fetched."""
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
        # Override raw_text_url to an off-host URL.
        fixture_json_offhost = dict(fixture_json)
        fixture_json_offhost["raw_text_url"] = "https://evil.attacker.example.com/steal"

        redirect_mock = _make_redirect_mock()
        json_mock = MagicMock()
        json_mock.status_code = 200
        json_mock.json.return_value = fixture_json_offhost
        json_mock.raise_for_status = MagicMock()

        # Only 2 calls should be made (redirect + JSON); NOT 3.
        mock_get.side_effect = [redirect_mock, json_mock]

        req = self.provider._locate_impl("fedreg:88.1722")
        sections = self.provider._fetch_impl(req)

        # Must have fallen back to abstract (no 3rd request made).
        self.assertEqual(
            mock_get.call_count, 2, "should not fetch off-host raw_text_url"
        )
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].text, fixture_json_offhost["abstract"])

    @patch(
        "opencontractserver.pipeline.authority_source_providers."
        "federal_register_provider.requests.get"
    )
    def test_malformed_citation_falls_back_to_request_key(self, mock_get: "MagicMock"):
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

        redirect_mock = _make_redirect_mock()
        json_mock = MagicMock()
        json_mock.status_code = 200
        json_mock.json.return_value = fixture_json_bad
        json_mock.raise_for_status = MagicMock()
        raw_mock = _make_raw_text_mock()

        mock_get.side_effect = [redirect_mock, json_mock, raw_mock]

        req = self.provider._locate_impl("fedreg:88.1722")
        sections = self.provider._fetch_impl(req)

        self.assertEqual(sections[0].key, "fedreg:88.1722")
