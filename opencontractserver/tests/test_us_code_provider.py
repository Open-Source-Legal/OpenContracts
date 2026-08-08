"""Unit tests for USCodeAuthoritySourceProvider (OLRC USLM 1.0 XML).

All tests are pure — no network calls, no DB.  HTTP is replaced by patching
``_load_title_xml`` to return fixture bytes from
``tests/fixtures/authority_sources/usc15_s2.xml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch

from django.test import SimpleTestCase

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
    _DEFAULT_RELEASE_POINT,
    USCodeAuthoritySourceProvider,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
)
from opencontractserver.pipeline.registry import (
    get_all_authority_source_providers_cached,
    reset_registry,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "authority_sources"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


class TestUSCodeLocate(SimpleTestCase):
    """_locate_impl is pure — no I/O, no mocking needed."""

    def setUp(self):
        self.provider = USCodeAuthoritySourceProvider()

    def test_locate_canonical_key_preserved(self):
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(req.canonical_key, "usc-15:78j")

    def test_locate_returns_authority_request(self):
        req = self.provider.locate("usc-15:78j")
        self.assertIsInstance(req, AuthorityRequest)

    def test_locate_title_in_extra(self):
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(req.extra["title"], "15")

    def test_locate_section_in_extra_verbatim(self):
        """Section string must be preserved exactly — no int-cast."""
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(req.extra["section"], "78j")

    def test_locate_citation_format(self):
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(req.citation, "15 U.S.C. § 78j")

    def test_locate_identifier_in_extra(self):
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(req.extra["identifier"], "/us/usc/t15/s78j")

    def test_locate_url_contains_usc15(self):
        req = self.provider.locate("usc-15:78j")
        self.assertIn("usc15", req.url)

    def test_locate_url_contains_release_point(self):
        req = self.provider.locate("usc-15:78j")
        flat = _DEFAULT_RELEASE_POINT.replace("/", "-")
        self.assertIn(flat, req.url)

    def test_locate_hyphenated_section_no_int_cast(self):
        """Sections like '80a-1' must not be corrupted (e.g. truncated to '80')."""
        req = self.provider.locate("usc-15:80a-1")
        self.assertEqual(req.extra["section"], "80a-1")
        self.assertEqual(req.extra["identifier"], "/us/usc/t15/s80a-1")

    def test_locate_alphanumeric_section(self):
        req = self.provider.locate("usc-15:78aaa")
        self.assertEqual(req.extra["section"], "78aaa")

    def test_locate_single_digit_title_padded_in_url(self):
        """Title 7 must appear as 'usc07' in the URL (zero-padded)."""
        req = self.provider.locate("usc-7:1")
        self.assertIn("usc07", req.url)

    def test_locate_source_url_non_empty(self):
        req = self.provider.locate("usc-15:78j")
        self.assertTrue(req.extra.get("source_url"))

    def test_locate_release_point_in_extra(self):
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(req.extra["release_point"], _DEFAULT_RELEASE_POINT)


class TestUSCodeCanHandle(SimpleTestCase):
    """can_handle uses regex — accepts any usc-{digits} prefix."""

    def setUp(self):
        self.provider = USCodeAuthoritySourceProvider()

    def test_can_handle_usc15(self):
        self.assertTrue(self.provider.can_handle("usc-15:2"))

    def test_can_handle_usc7(self):
        self.assertTrue(self.provider.can_handle("usc-7:1"))

    def test_can_handle_usc26(self):
        self.assertTrue(self.provider.can_handle("usc-26:1"))

    def test_cannot_handle_cfr(self):
        self.assertFalse(self.provider.can_handle("cfr-40:261.4"))

    def test_cannot_handle_dgcl(self):
        self.assertFalse(self.provider.can_handle("dgcl:145"))

    def test_cannot_handle_fedreg(self):
        self.assertFalse(self.provider.can_handle("fedreg:88.1722"))

    def test_cannot_handle_usc_no_digits(self):
        """'usc-abc:1' is not a valid USC prefix."""
        self.assertFalse(self.provider.can_handle("usc-abc:1"))

    def test_can_handle_two_digit_title(self):
        self.assertTrue(self.provider.can_handle("usc-42:1983"))


class TestUSCodeFetch(SimpleTestCase):
    """_fetch_impl with _load_title_xml patched to return fixture bytes."""

    def setUp(self):
        self.provider = USCodeAuthoritySourceProvider()
        self.fixture_bytes = _fixture_bytes("usc15_s2.xml")

    def _make_request(self, canonical_key: str = "usc-15:2") -> AuthorityRequest:
        return self.provider.locate(canonical_key)

    def _fetch_with_fixture(
        self, canonical_key: str = "usc-15:2"
    ) -> list[AuthoritySection]:
        request = self._make_request(canonical_key)
        with patch.object(
            self.provider, "_load_title_xml", return_value=self.fixture_bytes
        ):
            return cast(list[AuthoritySection], self.provider.fetch(request))

    # ---- basic shape --------------------------------------------------------

    def test_fetch_returns_one_section(self):
        sections = self._fetch_with_fixture()
        self.assertEqual(len(sections), 1)

    def test_fetch_returns_authority_section_instances(self):
        sections = self._fetch_with_fixture()
        self.assertIsInstance(sections[0], AuthoritySection)

    # ---- key ----------------------------------------------------------------

    def test_section_key(self):
        sections = self._fetch_with_fixture()
        self.assertEqual(sections[0].key, "usc-15:2")

    def test_section_key_lowercase(self):
        sections = self._fetch_with_fixture()
        self.assertEqual(sections[0].key, sections[0].key.lower())

    # ---- heading ------------------------------------------------------------

    def test_heading_exact(self):
        sections = self._fetch_with_fixture()
        self.assertEqual(sections[0].heading, "Monopolizing trade a felony; penalty")

    def test_heading_stripped(self):
        """Leading/trailing whitespace must be stripped from the heading."""
        sections = self._fetch_with_fixture()
        self.assertEqual(sections[0].heading, sections[0].heading.strip())

    # ---- text ---------------------------------------------------------------

    def test_text_starts_with_monopolize(self):
        sections = self._fetch_with_fixture()
        self.assertTrue(
            sections[0].text.startswith("Every person who shall monopolize"),
            f"text was: {sections[0].text!r}",
        )

    def test_text_excludes_stat_citation(self):
        """sourceCredit content ('Stat.') must not appear in body text."""
        sections = self._fetch_with_fixture()
        self.assertNotIn("Stat.", sections[0].text)

    def test_text_excludes_pub_l(self):
        """sourceCredit content ('Pub. L.') must not appear in body text."""
        sections = self._fetch_with_fixture()
        self.assertNotIn("Pub. L.", sections[0].text)

    def test_text_excludes_amendments_note(self):
        """Notes heading ('Amendments') must not appear in body text."""
        sections = self._fetch_with_fixture()
        self.assertNotIn("Amendments", sections[0].text)

    def test_text_non_empty(self):
        sections = self._fetch_with_fixture()
        self.assertTrue(sections[0].text.strip())

    # ---- source_url ---------------------------------------------------------

    def test_source_url_non_empty(self):
        sections = self._fetch_with_fixture()
        self.assertTrue(sections[0].source_url)

    # ---- missing section ----------------------------------------------------

    def test_missing_section_returns_empty_list(self):
        """If the section is not in the XML, return [] (don't raise)."""
        request = self.provider.locate("usc-15:9999")
        with patch.object(
            self.provider, "_load_title_xml", return_value=self.fixture_bytes
        ):
            sections = self.provider.fetch(request)
        self.assertEqual(sections, [])


class TestUSCodeRegistryDiscovery(SimpleTestCase):
    """USCodeAuthoritySourceProvider must be discoverable via the registry."""

    def setUp(self):
        reset_registry()

    def tearDown(self):
        reset_registry()

    def test_registry_includes_usc_provider(self):
        all_providers = get_all_authority_source_providers_cached()
        can_handle_usc = any(
            defn.component_class is not None
            and defn.component_class().can_handle("usc-15:1")
            for defn in all_providers
        )
        self.assertTrue(
            can_handle_usc,
            "No registered provider can handle 'usc-15:1'; "
            "USCodeAuthoritySourceProvider may not be discovered.",
        )

    def test_registry_not_empty(self):
        all_providers = get_all_authority_source_providers_cached()
        self.assertGreater(len(all_providers), 0)


class TestUSCodeValidation(SimpleTestCase):
    """_validate_usc_components rejects invalid citation components."""

    def setUp(self):
        self.provider = USCodeAuthoritySourceProvider()

    def test_valid_simple_section(self):
        """Single-digit section like '2' must not raise."""
        from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
            _validate_usc_components,
        )

        _validate_usc_components("15", "2")  # must not raise

    def test_valid_alphanum_section(self):
        from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
            _validate_usc_components,
        )

        _validate_usc_components("15", "78j")  # must not raise

    def test_valid_hyphenated_section(self):
        from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
            _validate_usc_components,
        )

        _validate_usc_components("15", "80a-1")  # must not raise

    def test_invalid_title_alpha(self):
        from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
            _validate_usc_components,
        )

        with self.assertRaises(ValueError):
            _validate_usc_components("abc", "78j")

    def test_invalid_section_with_slash(self):
        """Slash in section component must be rejected (injection guard)."""
        from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
            _validate_usc_components,
        )

        with self.assertRaises(ValueError):
            _validate_usc_components("15", "78j/../../etc/passwd")

    def test_invalid_section_with_quote(self):
        """Single quote in section component must be rejected (XPath guard)."""
        from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
            _validate_usc_components,
        )

        with self.assertRaises(ValueError):
            _validate_usc_components("15", "78j' or '1'='1")

    def test_locate_rejects_invalid_section(self):
        """locate() must raise ValueError for a bad section component."""
        with self.assertRaises(ValueError):
            self.provider.locate("usc-15:78j/../../etc")

    def test_size_cap_raises_on_oversized_download(self):
        """_load_title_xml must raise when safe_fetch_bytes reports oversized response."""
        from unittest.mock import patch

        from opencontractserver.utils.safe_http import SSRFValidationError

        req = self.provider.locate("usc-15:2")
        with patch(
            "opencontractserver.pipeline.authority_source_providers."
            "us_code_provider.safe_fetch_bytes",
            side_effect=SSRFValidationError("response exceeded size cap"),
        ):
            with self.assertRaises(
                SSRFValidationError,
                msg="Expected SSRFValidationError for oversized download",
            ):
                self.provider._load_title_xml(req)

    def test_load_title_xml_uses_safe_fetch_bytes(self):
        """safe_fetch_bytes must be invoked during _load_title_xml (not raw HTTP)."""
        import io
        import zipfile
        from unittest.mock import patch

        # Build a minimal ZIP in-memory containing the expected XML member.
        padded = "15"
        member_name = f"usc{padded}.xml"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(member_name, b"<root/>")
        zip_bytes = buf.getvalue()

        req = self.provider.locate("usc-15:2")

        with patch(
            "opencontractserver.pipeline.authority_source_providers."
            "us_code_provider.safe_fetch_bytes",
            return_value=(zip_bytes, "uscode.house.gov"),
        ) as mock_safe:
            self.provider._load_title_xml(req)

        self.assertTrue(
            mock_safe.called,
            "safe_fetch_bytes must be called by _load_title_xml; raw HTTP must not be used",
        )
        # Title ZIPs exceed the 50 MB default body cap, so the loader must pass
        # the dedicated larger override rather than relying on the default.
        from opencontractserver.constants.safe_http import OLRC_TITLE_ZIP_MAX_BYTES

        self.assertEqual(
            mock_safe.call_args.kwargs.get("max_bytes"),
            OLRC_TITLE_ZIP_MAX_BYTES,
            "_load_title_xml must request the OLRC title-ZIP size override",
        )
