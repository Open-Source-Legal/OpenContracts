"""Unit tests for BaseAuthorityDiscoveryProvider ABC and registry wiring.

Phase 2 (issue #2054): BaseAuthorityDiscoveryProvider crawls a publisher's
index/listing page(s) for candidates nobody has cited yet -- distinct from the
citation-KEYED BaseAuthoritySourceProvider (test_authority_source_provider_base.py).

These tests exercise:
  - The ABC contract (discover_candidates dispatch, de-dup, bounds, SSRF, and
    the public-domain license gate) via a local dummy provider.
  - Registry auto-discovery (ComponentType.AUTHORITY_DISCOVERY_PROVIDER,
    get_all_authority_discovery_providers_cached).
"""

from __future__ import annotations

from typing import ClassVar

from django.test import SimpleTestCase

from opencontractserver.pipeline.authority_discovery_providers.listing_index_provider import (
    ListingIndexDiscoveryProvider,
    ListingIndexRule,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
    DiscoveryResult,
    discovery_candidate_identity,
)
from opencontractserver.pipeline.registry import (
    ComponentType,
    get_all_authority_discovery_providers_cached,
    reset_registry,
)

# ---------------------------------------------------------------------------
# Local dummy provider -- not registered in the real discovery package, so it
# won't appear in the live registry scan, but is sufficient to test the ABC.
# ---------------------------------------------------------------------------


class _DummyDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    """Minimal concrete provider for unit testing the ABC contract.

    ``pages`` maps an index_url to its (already-"fetched") HTML text; a
    missing URL raises ``OSError`` to exercise the skipped_index_urls path
    without any real I/O.
    """

    title = "Dummy Discovery Provider"

    def __init__(self, pages: dict[str, str] | None = None):
        self._pages = pages or {}
        super().__init__()

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> str:
        if index_url not in self._pages:
            raise OSError(f"no such page: {index_url}")
        return self._pages[index_url]

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        # One candidate per non-blank line: "<canonical_key> <url>".
        candidates = []
        for line in html.splitlines():
            line = line.strip()
            if not line:
                continue
            key, _, url = line.partition(" ")
            candidates.append(
                DiscoveryCandidate(canonical_key=key, url=url or index_url)
            )
        return candidates


class _NonPublicDomainDiscoveryProvider(_DummyDiscoveryProvider):
    license: ClassVar[str] = "cc-by"


class _LinkOnlyDiscoveryProvider(_NonPublicDomainDiscoveryProvider):
    link_only_discovery: ClassVar[bool] = True


class TestBaseAuthorityDiscoveryProviderABC(SimpleTestCase):
    """Tests for the BaseAuthorityDiscoveryProvider ABC contract."""

    # ---- class-level attributes --------------------------------------------

    def test_license_default(self):
        self.assertEqual(_DummyDiscoveryProvider.license, "public-domain")

    def test_priority_default(self):
        self.assertEqual(_DummyDiscoveryProvider.priority, 100)

    def test_enabled_default(self):
        self.assertTrue(_DummyDiscoveryProvider.enabled)

    # ---- discover_candidates: happy path ------------------------------------

    def test_discover_candidates_returns_discovery_result(self):
        provider = _DummyDiscoveryProvider({"https://x/1": "key-a https://x/a"})
        result = provider.discover_candidates(["https://x/1"])
        self.assertIsInstance(result, DiscoveryResult)

    def test_discover_candidates_collects_from_one_page(self):
        provider = _DummyDiscoveryProvider(
            {"https://x/1": "key-a https://x/a\nkey-b https://x/b"}
        )
        result = provider.discover_candidates(["https://x/1"])
        keys = {c.canonical_key for c in result.candidates}
        self.assertEqual(keys, {"key-a", "key-b"})
        self.assertEqual(result.skipped_index_urls, {})
        self.assertFalse(result.capped)

    def test_discover_candidates_collects_across_pages(self):
        provider = _DummyDiscoveryProvider(
            {
                "https://x/1": "key-a https://x/a",
                "https://x/2": "key-b https://x/b",
            }
        )
        result = provider.discover_candidates(["https://x/1", "https://x/2"])
        keys = {c.canonical_key for c in result.candidates}
        self.assertEqual(keys, {"key-a", "key-b"})

    # ---- de-duplication ------------------------------------------------------

    def test_discover_candidates_dedupes_exact_identity_across_pages(self):
        """A paginated listing whose pages overlap must not seed an exact link twice."""
        provider = _DummyDiscoveryProvider(
            {
                "https://x/1": "key-a https://x/a",
                "https://x/2": "key-a https://x/a\nkey-b https://x/b",
            }
        )
        result = provider.discover_candidates(["https://x/1", "https://x/2"])
        keys = [c.canonical_key for c in result.candidates]
        self.assertEqual(sorted(keys), ["key-a", "key-b"])

    def test_same_key_with_changed_url_is_a_distinct_candidate(self):
        provider = _DummyDiscoveryProvider(
            {"https://x/1": ("key-a https://x/old\n" "key-a https://x/reseeded")}
        )
        result = provider.discover_candidates(["https://x/1"])
        self.assertEqual(
            [candidate.url for candidate in result.candidates],
            ["https://x/old", "https://x/reseeded"],
        )

    def test_changed_listing_metadata_is_a_distinct_observation(self):
        first = DiscoveryCandidate(
            canonical_key="key-a",
            url="https://x/stable",
            title="Planning Guide Section 9",
            extra={
                "source_identifier": "planning-guide-9",
                "current_version": True,
            },
        )
        changed = DiscoveryCandidate(
            canonical_key=first.canonical_key,
            url=first.url,
            title=first.title,
            extra={
                "source_identifier": "planning-guide-9",
                "current_version": False,
            },
        )
        provider_name = type(_DummyDiscoveryProvider()).__name__
        self.assertNotEqual(
            discovery_candidate_identity(
                first,
                discovery_provider=provider_name,
            ),
            discovery_candidate_identity(
                changed,
                discovery_provider=provider_name,
            ),
        )

    def test_excluding_old_url_keeps_reseeded_same_key_reachable(self):
        provider = _DummyDiscoveryProvider(
            {"https://x/1": "key-a https://x/old\nkey-a https://x/reseeded"}
        )
        old = DiscoveryCandidate(canonical_key="key-a", url="https://x/old")
        old_identity = discovery_candidate_identity(
            old,
            discovery_provider=type(provider).__name__,
        )
        result = provider.discover_candidates(
            ["https://x/1"],
            max_candidates=1,
            exclude_identities={old_identity},
        )
        self.assertEqual(
            [candidate.url for candidate in result.candidates],
            ["https://x/reseeded"],
        )

    # ---- bounds (issue #2054 test criterion c) -------------------------------

    def test_discover_candidates_stops_at_max_candidates(self):
        provider = _DummyDiscoveryProvider(
            {
                "https://x/1": "key-a https://x/a\nkey-b https://x/b",
                "https://x/2": "key-c https://x/c\nkey-d https://x/d",
            }
        )
        result = provider.discover_candidates(
            ["https://x/1", "https://x/2"], max_candidates=1
        )
        self.assertEqual(len(result.candidates), 1)
        self.assertTrue(result.capped)

    def test_excluded_candidate_identity_advances_beyond_cap(self):
        provider = _DummyDiscoveryProvider(
            {"https://x/1": "key-a https://x/a\nkey-b https://x/b"}
        )
        first = provider.discover_candidates(["https://x/1"], max_candidates=1)
        first_identity = discovery_candidate_identity(
            first.candidates[0],
            discovery_provider=type(provider).__name__,
        )
        second = provider.discover_candidates(
            ["https://x/1"],
            max_candidates=1,
            exclude_identities={first_identity},
        )
        self.assertEqual(
            [candidate.canonical_key for candidate in second.candidates],
            ["key-b"],
        )
        self.assertEqual(second.excluded_count, 1)

    def test_discover_candidates_not_capped_when_under_limit(self):
        provider = _DummyDiscoveryProvider({"https://x/1": "key-a https://x/a"})
        result = provider.discover_candidates(["https://x/1"], max_candidates=10)
        self.assertFalse(result.capped)

    def test_not_capped_when_exactly_at_limit_with_nothing_left_one_page(self):
        """Boundary case: total distinct candidates == max_candidates, and
        nothing more remains (single page, cap hit on its last candidate).
        Nothing was actually truncated, so capped must be False even though
        the cap was technically reached."""
        provider = _DummyDiscoveryProvider(
            {"https://x/1": "key-a https://x/a\nkey-b https://x/b"}
        )
        result = provider.discover_candidates(["https://x/1"], max_candidates=2)
        self.assertEqual(
            {c.canonical_key for c in result.candidates}, {"key-a", "key-b"}
        )
        self.assertFalse(result.capped)

    def test_not_capped_when_exactly_at_limit_with_nothing_left_across_pages(self):
        """Same boundary, but the cap lands on the last candidate of the LAST
        of several index_urls -- still nothing left, so still not capped."""
        provider = _DummyDiscoveryProvider(
            {
                "https://x/1": "key-a https://x/a",
                "https://x/2": "key-b https://x/b",
            }
        )
        result = provider.discover_candidates(
            ["https://x/1", "https://x/2"], max_candidates=2
        )
        self.assertEqual(
            {c.canonical_key for c in result.candidates}, {"key-a", "key-b"}
        )
        self.assertFalse(result.capped)

    def test_max_candidates_clamped_to_at_least_one(self):
        """A non-positive max_candidates must not disable bounding entirely."""
        provider = _DummyDiscoveryProvider(
            {"https://x/1": "key-a https://x/a\nkey-b https://x/b"}
        )
        result = provider.discover_candidates(["https://x/1"], max_candidates=0)
        self.assertEqual(len(result.candidates), 1)
        self.assertTrue(result.capped)

    # ---- fetch-error resilience -----------------------------------------------

    def test_discover_candidates_records_skipped_url_and_continues(self):
        provider = _DummyDiscoveryProvider({"https://x/2": "key-b https://x/b"})
        result = provider.discover_candidates(["https://x/1", "https://x/2"])
        self.assertIn("https://x/1", result.skipped_index_urls)
        keys = {c.canonical_key for c in result.candidates}
        self.assertEqual(keys, {"key-b"})

    # ---- SSRF (issue #2054 test criterion d) ---------------------------------

    def test_ssrf_blocked_host_is_rejected_and_never_fetched(self):
        """A non-allowlisted index URL is rejected by safe_http and skipped.

        Uses the REAL ListingIndexDiscoveryProvider (not the dummy) so the
        actual safe_fetch_text/SSRF gate runs -- no mocking, no network call:
        the host-allowlist check happens before any DNS resolution or socket
        connect, so this is deterministic and fast.
        """
        provider = ListingIndexDiscoveryProvider()
        rule = ListingIndexRule(
            link_pattern=r'href="(?P<url>[^"]+)"',
            canonical_key_template="{prefix}:{url}",
            prefix="x",
        )
        result = provider.discover_candidates(
            ["https://evil.example.com/index"], rule=rule
        )
        self.assertEqual(result.candidates, [])
        self.assertIn("https://evil.example.com/index", result.skipped_index_urls)
        self.assertIn(
            "blocked", result.skipped_index_urls["https://evil.example.com/index"]
        )

    # ---- license gate ---------------------------------------------------------

    def test_non_public_domain_license_refuses_to_run(self):
        provider = _NonPublicDomainDiscoveryProvider(
            {"https://x/1": "key-a https://x/a"}
        )
        with self.assertRaises(PermissionError):
            provider.discover_candidates(["https://x/1"])

    def test_non_public_index_can_opt_into_link_only_enumeration(self):
        provider = _LinkOnlyDiscoveryProvider({"https://x/1": "key-a https://x/a"})
        result = provider.discover_candidates(["https://x/1"])
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(
            result.candidates[0].extra,
            {
                "discovery_mode": "link-only",
                "publisher_license": "cc-by",
            },
        )


class TestAuthorityDiscoveryProviderRegistry(SimpleTestCase):
    """Tests for AUTHORITY_DISCOVERY_PROVIDER registry wiring."""

    def setUp(self):
        reset_registry()

    def tearDown(self):
        reset_registry()

    def test_component_type_enum_member_exists(self):
        self.assertEqual(
            ComponentType.AUTHORITY_DISCOVERY_PROVIDER.value,
            "authority_discovery_provider",
        )

    def test_get_all_authority_discovery_providers_cached_returns_iterable(self):
        result = get_all_authority_discovery_providers_cached()
        self.assertIsInstance(result, (list, tuple))

    def test_listing_index_discovery_provider_is_discovered(self):
        providers = get_all_authority_discovery_providers_cached()
        names = {d.name for d in providers}
        self.assertIn("ListingIndexDiscoveryProvider", names)

    def test_listing_index_discovery_provider_license_surfaced(self):
        providers = get_all_authority_discovery_providers_cached()
        sample = next(d for d in providers if d.name == "ListingIndexDiscoveryProvider")
        self.assertEqual(sample.component_class, ListingIndexDiscoveryProvider)
