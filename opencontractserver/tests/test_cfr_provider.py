"""Unit tests for CFRAuthoritySourceProvider.

All HTTP is mocked — no network calls are made.  The fixture XML is loaded
from ``opencontractserver/tests/fixtures/authority_sources/``.

Test coverage:
  - _locate_impl: URL, params, citation, and extra derivation (pure).
  - can_handle: matching and non-matching prefixes.
  - _fetch_impl: patched safe_fetch_bytes → parse GPO XML fixture → AuthoritySection.
  - Registry discovery: cfr handler visible via get_all_authority_source_providers_cached().
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

from django.test import SimpleTestCase

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.authority_source_providers.cfr_provider import (
    _SNAPSHOT_DATE,
    CFRAuthoritySourceProvider,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
)
from opencontractserver.pipeline.registry import (
    get_all_authority_source_providers_cached,
    reset_registry,
)

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "authority_sources"

_FIXTURE_XML = (FIXTURE_DIR / "cfr_title40_261.4.xml").read_bytes()


class TestCFRLocateImpl(SimpleTestCase):
    """Pure tests for _locate_impl — no I/O, no mocking."""

    def setUp(self):
        self.provider = CFRAuthoritySourceProvider()

    def test_locate_basic_key(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertIsInstance(req, AuthorityRequest)

    def test_locate_url_contains_title_and_date(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertIn("/title-40.xml", req.url)
        self.assertIn(_SNAPSHOT_DATE, req.url)

    def test_locate_params_part(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertEqual(req.params.get("part"), "261")

    def test_locate_params_section(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertEqual(req.params.get("section"), "261.4")

    def test_locate_citation(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertEqual(req.citation, "40 CFR 261.4")

    def test_locate_extra_title(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertEqual(req.extra.get("title"), "40")

    def test_locate_extra_section(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertEqual(req.extra.get("section"), "261.4")

    def test_locate_extra_part(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertEqual(req.extra.get("part"), "261")

    def test_locate_source_url(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertIn("section-261.4", req.extra.get("source_url", ""))
        self.assertIn("title-40", req.extra.get("source_url", ""))

    def test_locate_canonical_key_preserved(self):
        req = self.provider._locate_impl("cfr-40:261.4")
        self.assertEqual(req.canonical_key, "cfr-40:261.4")

    # --- Alternate key: cfr-17:240.10b-5 ---

    def test_locate_hyphenated_section_part(self):
        """240.10b-5 → part '240' (integer prefix before first '.')."""
        req = self.provider._locate_impl("cfr-17:240.10b-5")
        self.assertEqual(req.params.get("part"), "240")

    def test_locate_hyphenated_section_section_param(self):
        req = self.provider._locate_impl("cfr-17:240.10b-5")
        self.assertEqual(req.params.get("section"), "240.10b-5")

    def test_locate_hyphenated_section_citation(self):
        req = self.provider._locate_impl("cfr-17:240.10b-5")
        self.assertEqual(req.citation, "17 CFR 240.10b-5")

    def test_locate_hyphenated_section_url_title(self):
        req = self.provider._locate_impl("cfr-17:240.10b-5")
        self.assertIn("/title-17.xml", req.url)

    def test_locate_snapshot_date_override(self):
        req = self.provider._locate_impl("cfr-40:261.4", snapshot_date="2023-07-01")
        self.assertIn("2023-07-01", req.url)


class TestCFRCanHandle(SimpleTestCase):
    """Tests for can_handle regex-based prefix matching."""

    def setUp(self):
        self.provider = CFRAuthoritySourceProvider()

    def test_can_handle_cfr_40(self):
        self.assertTrue(self.provider.can_handle("cfr-40:261.4"))

    def test_can_handle_cfr_17(self):
        self.assertTrue(self.provider.can_handle("cfr-17:240.10b-5"))

    def test_can_handle_cfr_1(self):
        self.assertTrue(self.provider.can_handle("cfr-1:1.1"))

    def test_cannot_handle_usc(self):
        self.assertFalse(self.provider.can_handle("usc-15:78j"))

    def test_cannot_handle_fedreg(self):
        self.assertFalse(self.provider.can_handle("fedreg:88.1722"))

    def test_cannot_handle_bare_cfr(self):
        """'cfr' without a title number must not match."""
        self.assertFalse(self.provider.can_handle("cfr:1.1"))

    def test_cannot_handle_non_numeric_title(self):
        self.assertFalse(self.provider.can_handle("cfr-abc:1.1"))


_SAFE_FETCH_PATH = "opencontractserver.pipeline.authority_source_providers.cfr_provider.safe_fetch_bytes"


class TestCFRFetchImpl(SimpleTestCase):
    """Tests for _fetch_impl with mocked HTTP (patching safe_fetch_bytes)."""

    def _patch_fetch(self, fixture_bytes: bytes = _FIXTURE_XML):
        """Return a patcher that makes safe_fetch_bytes return *fixture_bytes*."""
        return patch(_SAFE_FETCH_PATH, return_value=(fixture_bytes, "www.ecfr.gov"))

    def test_fetch_returns_one_section(self):
        with self._patch_fetch():
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            sections = provider._fetch_impl(req)
        self.assertEqual(len(sections), 1)

    def test_fetch_section_type(self):
        with self._patch_fetch():
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            sections = provider._fetch_impl(req)
        self.assertIsInstance(sections[0], AuthoritySection)

    def test_fetch_section_key(self):
        with self._patch_fetch():
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            sections = provider._fetch_impl(req)
        self.assertEqual(sections[0].key, "cfr-40:261.4")

    def test_fetch_heading_contains_exclusions(self):
        with self._patch_fetch():
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            sections = provider._fetch_impl(req)
        self.assertIn("Exclusions", sections[0].heading)

    def test_fetch_text_starts_with_a(self):
        with self._patch_fetch():
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            sections = provider._fetch_impl(req)
        self.assertTrue(sections[0].text.startswith("(a)"))

    def test_fetch_text_contains_solid_wastes(self):
        with self._patch_fetch():
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            sections = provider._fetch_impl(req)
        self.assertIn("solid wastes", sections[0].text)

    def test_fetch_source_url_set(self):
        with self._patch_fetch():
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            sections = provider._fetch_impl(req)
        self.assertIn("section-261.4", sections[0].source_url or "")

    def test_fetch_passes_params(self):
        with patch(
            _SAFE_FETCH_PATH, return_value=(_FIXTURE_XML, "www.ecfr.gov")
        ) as mock_fetch:
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            provider._fetch_impl(req)
        _call_kwargs = mock_fetch.call_args
        self.assertEqual(_call_kwargs[1]["params"], {"part": "261", "section": "261.4"})

    def test_fetch_section_not_found_returns_empty(self):
        """If the section attribute is absent in the XML, return []."""
        with self._patch_fetch():
            provider = CFRAuthoritySourceProvider()
            # Request a non-existent section.
            req = provider._locate_impl("cfr-40:999.1")
            sections = provider._fetch_impl(req)
        self.assertEqual(sections, [])


class TestCFRRegistryDiscovery(SimpleTestCase):
    """Confirm CFR provider is visible via get_all_authority_source_providers_cached."""

    def setUp(self):
        reset_registry()

    def tearDown(self):
        reset_registry()

    def test_cfr_handler_discovered(self):
        providers = get_all_authority_source_providers_cached()
        cfr_handlers = [
            d
            for d in providers
            if d.component_class is not None
            and d.component_class().can_handle("cfr-40:261.4")
        ]
        self.assertTrue(
            len(cfr_handlers) >= 1,
            "Expected at least one registered provider to handle 'cfr-40:261.4'",
        )


class TestCFRValidation(SimpleTestCase):
    """_validate_cfr_components rejects invalid citation components."""

    def setUp(self):
        self.provider = CFRAuthoritySourceProvider()

    def test_valid_simple(self):
        from opencontractserver.pipeline.authority_source_providers.cfr_provider import (
            _validate_cfr_components,
        )

        _validate_cfr_components("40", "261", "261.4")  # must not raise

    def test_valid_hyphenated_section(self):
        from opencontractserver.pipeline.authority_source_providers.cfr_provider import (
            _validate_cfr_components,
        )

        _validate_cfr_components("17", "240", "240.10b-5")  # must not raise

    def test_invalid_title(self):
        from opencontractserver.pipeline.authority_source_providers.cfr_provider import (
            _validate_cfr_components,
        )

        with self.assertRaises(ValueError):
            _validate_cfr_components("abc", "261", "261.4")

    def test_invalid_section_with_quote(self):
        """Single quote in section must be rejected."""
        from opencontractserver.pipeline.authority_source_providers.cfr_provider import (
            _validate_cfr_components,
        )

        with self.assertRaises(ValueError):
            _validate_cfr_components("40", "261", "261.4' or '1'='1")

    def test_locate_rejects_invalid_section(self):
        """_locate_impl must raise ValueError for a section with injection chars."""
        with self.assertRaises(ValueError):
            self.provider._locate_impl("cfr-40:261.4'/etc")

    def test_fetch_ssrf_error_propagates(self):
        """An SSRFValidationError from safe_fetch_bytes must propagate out of _fetch_impl."""
        from opencontractserver.utils.safe_http import SSRFValidationError

        with patch(
            _SAFE_FETCH_PATH,
            side_effect=SSRFValidationError("host not on allowlist"),
        ):
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            with self.assertRaises(SSRFValidationError):
                provider._fetch_impl(req)

    def test_fetch_http_error_propagates(self):
        """An HTTP status error from safe_fetch_bytes must propagate out of _fetch_impl."""
        import httpx

        with patch(
            _SAFE_FETCH_PATH,
            side_effect=httpx.HTTPStatusError(
                "500 Server Error",
                request=httpx.Request("GET", "https://www.ecfr.gov/"),
                response=httpx.Response(500),
            ),
        ):
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            with self.assertRaises(httpx.HTTPStatusError):
                provider._fetch_impl(req)

    def test_fetch_uses_safe_fetch_bytes(self):
        """safe_fetch_bytes must be invoked during _fetch_impl (not raw requests/httpx)."""
        with patch(
            _SAFE_FETCH_PATH, return_value=(_FIXTURE_XML, "www.ecfr.gov")
        ) as mock_safe:
            provider = CFRAuthoritySourceProvider()
            req = provider._locate_impl("cfr-40:261.4")
            provider._fetch_impl(req)
        self.assertTrue(
            mock_safe.called,
            "safe_fetch_bytes must be called by _fetch_impl; raw HTTP must not be used",
        )
