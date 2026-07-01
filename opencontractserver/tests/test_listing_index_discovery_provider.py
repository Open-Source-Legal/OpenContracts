"""Unit tests for ListingIndexDiscoveryProvider (Phase 2, issue #2054).

All HTTP is mocked -- no network calls are made (patching ``safe_fetch_text``,
the same convention as ``test_cfr_provider.py``). The fixture HTML is loaded
from ``opencontractserver/tests/fixtures/authority_sources/`` and is a
SYNTHETIC stand-in shaped like Bolivia's Gaceta Oficial (the issue's motivating
case) -- it is not scraped from, and makes no claim about, the real site's
current markup.

Test coverage:
  - ListingIndexRule validation (must declare a 'url' group; regex must compile).
  - _parse_index_impl: pure extraction of candidates from the fixture (criterion a).
  - _fetch_index_impl: patched safe_fetch_text -> raw HTML passthrough.
  - discover_candidates end-to-end with a patched fetch.
  - SSRF: a non-allowlisted index URL is rejected and never fetched (criterion d).
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

from django.test import SimpleTestCase

from opencontractserver.pipeline.authority_discovery_providers.listing_index_provider import (
    ListingIndexDiscoveryProvider,
    ListingIndexRule,
)

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "authority_sources"
_FIXTURE_HTML = (FIXTURE_DIR / "gaceta_listing_bolivia_synthetic.html").read_text(
    encoding="utf-8"
)

_INDEX_URL = "https://www.gacetaoficialdebolivia.gob.bo/gaceta/listado"

# A rule tuned to the synthetic fixture's markup (see the fixture file's own
# header comment: this is a hand-written test shape, not a verified live rule).
_BOLIVIA_GACETA_RULE = ListingIndexRule(
    link_pattern=(
        r'<a href="(?P<url>(?:https?://[^/"]+)?/gaceta/documento/(?P<id>[\w-]+))">'
        r"(?P<title>[^<]+)</a>"
    ),
    canonical_key_template="{prefix}:{id}",
    prefix="bo-gaceta",
)


class TestListingIndexRule(SimpleTestCase):
    def test_requires_named_url_group(self):
        with self.assertRaises(ValueError):
            ListingIndexRule(
                link_pattern=r"<a href=(?P<link>[^>]+)>",
                canonical_key_template="{prefix}:{link}",
                prefix="x",
            )

    def test_invalid_regex_raises(self):
        with self.assertRaises(ValueError):
            ListingIndexRule(
                link_pattern=r"(?P<url>[",
                canonical_key_template="{prefix}:{url}",
                prefix="x",
            )

    def test_valid_rule_constructs(self):
        rule = ListingIndexRule(
            link_pattern=r'href="(?P<url>[^"]+)"',
            canonical_key_template="{prefix}:{url}",
            prefix="x",
        )
        self.assertEqual(rule.prefix, "x")


class TestParseIndexImpl(SimpleTestCase):
    """Pure tests for _parse_index_impl against the synthetic fixture (criterion a)."""

    def setUp(self):
        self.provider = ListingIndexDiscoveryProvider()

    def _parse(self):
        return self.provider._parse_index_impl(
            _FIXTURE_HTML, index_url=_INDEX_URL, rule=_BOLIVIA_GACETA_RULE
        )

    def test_finds_three_candidates(self):
        """The fixture has 4 rows; one has no <a> link and must be skipped."""
        candidates = self._parse()
        self.assertEqual(len(candidates), 3)

    def test_canonical_keys(self):
        candidates = self._parse()
        keys = {c.canonical_key for c in candidates}
        self.assertEqual(
            keys, {"bo-gaceta:2024-1234", "bo-gaceta:2024-1235", "bo-gaceta:2024-1236"}
        )

    def test_relative_url_resolved_against_index_url(self):
        candidates = self._parse()
        by_key = {c.canonical_key: c for c in candidates}
        self.assertEqual(
            by_key["bo-gaceta:2024-1234"].url,
            "https://www.gacetaoficialdebolivia.gob.bo/gaceta/documento/2024-1234",
        )

    def test_absolute_url_preserved(self):
        candidates = self._parse()
        by_key = {c.canonical_key: c for c in candidates}
        self.assertEqual(
            by_key["bo-gaceta:2024-1236"].url,
            "https://www.gacetaoficialdebolivia.gob.bo/gaceta/documento/2024-1236",
        )

    def test_title_captured(self):
        candidates = self._parse()
        by_key = {c.canonical_key: c for c in candidates}
        self.assertIn("Decreto Supremo", by_key["bo-gaceta:2024-1235"].title)

    def test_extra_carries_index_url(self):
        candidates = self._parse()
        self.assertEqual(candidates[0].extra["index_url"], _INDEX_URL)

    def test_missing_rule_kwarg_raises(self):
        with self.assertRaises(ValueError):
            self.provider._parse_index_impl(_FIXTURE_HTML, index_url=_INDEX_URL)

    def test_template_field_missing_from_match_is_skipped_not_raised(self):
        """A canonical_key_template referencing a group the pattern doesn't
        capture must skip that match rather than blow up the whole page."""
        rule = ListingIndexRule(
            link_pattern=r'<a href="(?P<url>[^"]+)">[^<]*</a>',
            canonical_key_template="{prefix}:{nonexistent_group}",
            prefix="x",
        )
        candidates = self.provider._parse_index_impl(
            _FIXTURE_HTML, index_url=_INDEX_URL, rule=rule
        )
        self.assertEqual(candidates, [])

    def test_link_pattern_group_named_prefix_does_not_raise_typeerror(self):
        """A link_pattern that defines its OWN named group literally called
        'prefix' (e.g. a jurisdiction/prefix column in the source markup) must
        not crash with `TypeError: got multiple values for keyword argument
        'prefix'` -- rule.prefix (the deliberately-configured value) wins over
        the regex-captured one, per ListingIndexRule's docstring."""
        rule = ListingIndexRule(
            link_pattern=(
                r'<a href="(?P<url>/doc/(?P<prefix>[a-z]+)-(?P<id>\d+))">'
                r"(?P<title>[^<]+)</a>"
            ),
            canonical_key_template="{prefix}:{id}",
            prefix="configured-prefix",
        )
        html = '<a href="/doc/bo-42">Some Doc</a>'
        candidates = self.provider._parse_index_impl(
            html, index_url=_INDEX_URL, rule=rule
        )
        self.assertEqual(len(candidates), 1)
        # rule.prefix ("configured-prefix") wins; the regex-captured "bo" is
        # discarded, not concatenated or otherwise blended in.
        self.assertEqual(candidates[0].canonical_key, "configured-prefix:42")


_SAFE_FETCH_PATH = (
    "opencontractserver.pipeline.authority_discovery_providers."
    "listing_index_provider.safe_fetch_text"
)


class TestFetchIndexImpl(SimpleTestCase):
    """Tests for _fetch_index_impl with mocked HTTP (patching safe_fetch_text)."""

    def test_fetch_returns_body_text(self):
        with patch(_SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "www.example.gov")):
            provider = ListingIndexDiscoveryProvider()
            html = provider._fetch_index_impl(_INDEX_URL)
        self.assertEqual(html, _FIXTURE_HTML)

    def test_fetch_passes_user_agent_header(self):
        with patch(
            _SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "www.example.gov")
        ) as mock_fetch:
            provider = ListingIndexDiscoveryProvider()
            provider._fetch_index_impl(_INDEX_URL)
        _, call_kwargs = mock_fetch.call_args
        self.assertIn("User-Agent", call_kwargs["headers"])


class TestDiscoverCandidatesEndToEnd(SimpleTestCase):
    """discover_candidates() with a patched fetch -- full pipeline, no network."""

    def test_end_to_end_discovery(self):
        with patch(_SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "www.example.gov")):
            provider = ListingIndexDiscoveryProvider()
            result = provider.discover_candidates(
                [_INDEX_URL], rule=_BOLIVIA_GACETA_RULE
            )
        self.assertEqual(len(result.candidates), 3)
        self.assertFalse(result.capped)
        self.assertEqual(result.skipped_index_urls, {})

    def test_end_to_end_respects_max_candidates(self):
        with patch(_SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "www.example.gov")):
            provider = ListingIndexDiscoveryProvider()
            result = provider.discover_candidates(
                [_INDEX_URL], rule=_BOLIVIA_GACETA_RULE, max_candidates=2
            )
        self.assertEqual(len(result.candidates), 2)
        self.assertTrue(result.capped)

    def test_end_to_end_survives_link_pattern_prefix_group_collision(self):
        """discover_candidates() -- the public entrypoint the management
        command calls -- must not raise when link_pattern defines its own
        'prefix' group, regardless of the pure-parse-level test above."""
        rule = ListingIndexRule(
            link_pattern=(
                r'<a href="(?P<url>/doc/(?P<prefix>[a-z]+)-(?P<id>\d+))">'
                r"(?P<title>[^<]+)</a>"
            ),
            canonical_key_template="{prefix}:{id}",
            prefix="configured-prefix",
        )
        html = '<a href="/doc/bo-42">Some Doc</a>'
        with patch(_SAFE_FETCH_PATH, return_value=(html, "www.example.gov")):
            provider = ListingIndexDiscoveryProvider()
            result = provider.discover_candidates([_INDEX_URL], rule=rule)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].canonical_key, "configured-prefix:42")


class TestSSRFRejection(SimpleTestCase):
    """A URL that would fail safe_http validation is rejected and never fetched
    (issue #2054 test criterion d). No mocking -- the REAL safe_fetch_text/
    SSRF gate runs, and the host-allowlist check fires before any DNS
    resolution or socket connect (see opencontractserver/utils/safe_http.py::
    validate_url), so this needs no network access and is fully deterministic."""

    def test_non_allowlisted_host_is_rejected_and_never_fetched(self):
        provider = ListingIndexDiscoveryProvider()
        result = provider.discover_candidates(
            ["https://evil.example.com/listing"], rule=_BOLIVIA_GACETA_RULE
        )
        self.assertEqual(result.candidates, [])
        reason = result.skipped_index_urls["https://evil.example.com/listing"]
        self.assertIn("blocked", reason)
        self.assertIn("allowlist", reason)

    def test_http_scheme_is_also_rejected(self):
        """Belt-and-suspenders: the scheme check runs before the allowlist
        check, so a downgraded (non-HTTPS) URL is rejected too."""
        provider = ListingIndexDiscoveryProvider()
        result = provider.discover_candidates(
            ["http://www.ecfr.gov/listing"], rule=_BOLIVIA_GACETA_RULE
        )
        self.assertEqual(result.candidates, [])
        self.assertIn("http://www.ecfr.gov/listing", result.skipped_index_urls)
