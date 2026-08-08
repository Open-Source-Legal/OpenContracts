"""Unit tests for BaseAuthoritySourceProvider ABC and registry wiring.

These tests exercise:
  - The ABC contract (can_handle / locate / fetch dispatch).
  - A local dummy provider that satisfies the abstract interface.
  - Registry auto-discovery (get_all_authority_source_providers_cached returns a
    list/tuple without raising, even when no concrete providers are installed yet).
  - ComponentType.AUTHORITY_SOURCE_PROVIDER enum member existence.
"""

from django.test import SimpleTestCase

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    DiscoveryCandidate,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.pipeline.registry import (
    ComponentType,
    get_all_authority_source_providers_cached,
    reset_registry,
)

# ---------------------------------------------------------------------------
# Local dummy provider — not registered in the real discovery package, so it
# won't appear in the live registry scan, but is sufficient to test the ABC.
# ---------------------------------------------------------------------------


class _DummyProvider(BaseAuthoritySourceProvider):
    """Minimal concrete provider for unit testing the ABC contract."""

    title = "Dummy"
    description = "Dummy provider for tests"
    supported_prefixes = ("usc-15",)

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        candidate = all_kwargs.get("discovery_candidate")
        return AuthorityRequest(
            canonical_key=canonical_key,
            url="http://x",
            citation=f"dummy citation for {canonical_key}",
            extra={"candidate_url": candidate.url if candidate else None},
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySection]:
        return []


class TestBaseAuthoritySourceProviderABC(SimpleTestCase):
    """Tests for the BaseAuthoritySourceProvider ABC contract."""

    def setUp(self):
        self.provider = _DummyProvider()

    # ---- can_handle ---------------------------------------------------------

    def test_can_handle_matching_prefix(self):
        self.assertIs(self.provider.can_handle("usc-15:78j"), True)

    def test_can_handle_prefix_boundary(self):
        """Prefix match is exact on the pre-colon segment."""
        self.assertIs(self.provider.can_handle("usc-15:2"), True)

    def test_can_handle_non_matching_prefix(self):
        self.assertIs(self.provider.can_handle("cfr-40:1"), False)

    def test_can_handle_partial_prefix_not_matched(self):
        """'usc-150:1' should not match the 'usc-15' prefix."""
        self.assertIs(self.provider.can_handle("usc-150:1"), False)

    # ---- locate -------------------------------------------------------------

    def test_locate_returns_authority_request(self):
        req = self.provider.locate("usc-15:78j")
        self.assertIsInstance(req, AuthorityRequest)

    def test_locate_canonical_key_propagated(self):
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(req.canonical_key, "usc-15:78j")

    def test_locate_url_set(self):
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(req.url, "http://x")

    def test_locate_round_trips_listing_discovery_candidate(self):
        candidate = DiscoveryCandidate(
            canonical_key="usc-15:78j",
            url="https://example.gov/discovered",
            title="Discovered section",
            extra={"source_identifier": "attachment-7"},
        )
        req = self.provider.locate("usc-15:78j", discovery_candidate=candidate)
        self.assertIs(req.discovery_candidate, candidate)
        self.assertEqual(req.extra["candidate_url"], candidate.url)

    # ---- fetch --------------------------------------------------------------

    def test_fetch_returns_list(self):
        req = self.provider.locate("usc-15:78j")
        result = self.provider.fetch(req)
        self.assertIsInstance(result, list)

    def test_fetch_returns_empty_for_dummy(self):
        req = self.provider.locate("usc-15:78j")
        self.assertEqual(self.provider.fetch(req), [])

    # ---- class-level attributes --------------------------------------------

    def test_supported_prefixes_class_var(self):
        self.assertEqual(_DummyProvider.supported_prefixes, ("usc-15",))

    def test_license_default(self):
        self.assertEqual(_DummyProvider.license, "public-domain")


class TestAuthoritySourceProviderRegistry(SimpleTestCase):
    """Tests for AUTHORITY_SOURCE_PROVIDER registry wiring."""

    def setUp(self):
        # Reset the singleton so these tests get a clean discovery run.
        reset_registry()

    def tearDown(self):
        reset_registry()

    def test_component_type_enum_member_exists(self):
        """ComponentType.AUTHORITY_SOURCE_PROVIDER must be defined."""
        self.assertEqual(
            ComponentType.AUTHORITY_SOURCE_PROVIDER.value, "authority_source_provider"
        )

    def test_get_all_authority_source_providers_cached_returns_iterable(self):
        """Registry discovery must succeed (even when no providers are installed)."""
        result = get_all_authority_source_providers_cached()
        # Must be iterable and not raise.
        self.assertIsInstance(result, (list, tuple))

    def test_get_all_authority_source_providers_cached_discovers_providers(self):
        """Concrete providers register via the auto-discovery package, so once
        they ship the registry returns a non-empty list and a usc-handler."""
        providers = get_all_authority_source_providers_cached()
        self.assertTrue(
            any(
                d.component_class is not None
                and d.component_class().can_handle("usc-15:1")
                for d in providers
            )
        )
