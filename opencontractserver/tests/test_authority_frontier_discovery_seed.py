"""Tests for AuthorityFrontierService.seed_from_discovery (Phase 2, issue #2054).

Mirrors seed_child_keys' idempotency contract exactly (see that method's
docstring): a canonical_key that already has a row -- at ANY depth/state -- is
skipped, so re-running discovery never creates duplicates and never resets an
in-flight row.
"""

from __future__ import annotations

from django.test import TestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services.authority_frontier_service import (
    AuthorityFrontierService,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    DiscoveryCandidate,
)


class SeedFromDiscoveryTests(TestCase):
    def test_creates_new_rows(self):
        candidates = [
            DiscoveryCandidate(
                canonical_key="bo-gaceta:2024-1234",
                url="https://x/1234",
                title="Ley 1234",
            ),
            DiscoveryCandidate(
                canonical_key="bo-gaceta:2024-1235",
                url="https://x/1235",
                title="DS 1235",
            ),
        ]
        result = AuthorityFrontierService.seed_from_discovery(
            candidates, discovery_provider="ListingIndexDiscoveryProvider"
        )
        self.assertEqual(result["discovery_created"], 2)
        self.assertEqual(result["discovery_appended"], 0)
        self.assertEqual(result["discovery_skipped"], 0)
        self.assertEqual(
            set(result["queued_keys"]),
            {"bo-gaceta:2024-1234", "bo-gaceta:2024-1235"},
        )

    def test_created_row_fields(self):
        candidates = [
            DiscoveryCandidate(
                canonical_key="bo-gaceta:2024-1234",
                url="https://x/1234",
                title="Ley 1234",
            )
        ]
        AuthorityFrontierService.seed_from_discovery(
            candidates, discovery_provider="ListingIndexDiscoveryProvider"
        )
        row = AuthorityFrontier.objects.get(canonical_key="bo-gaceta:2024-1234")
        self.assertEqual(row.discovery_state, C.DISCOVERY_STATE_QUEUED)
        self.assertEqual(row.depth, 0)
        self.assertIsNone(row.provider)
        self.assertEqual(row.mention_count, 1)
        self.assertEqual(row.authority, "bo-gaceta")
        self.assertEqual(len(row.candidate_sources), 1)
        self.assertEqual(
            row.candidate_sources[0]["discovery_provider"],
            "ListingIndexDiscoveryProvider",
        )
        self.assertEqual(row.candidate_sources[0]["url"], "https://x/1234")
        self.assertEqual(row.candidate_sources[0]["title"], "Ley 1234")
        self.assertEqual(len(row.candidate_sources[0]["discovery_id"]), 64)

    def test_candidate_extra_is_durable_for_source_provider_handoff(self):
        candidate = DiscoveryCandidate(
            canonical_key="puct-project:58211:item:4:document:99",
            url="https://interchange.puc.texas.gov/document/99",
            title="Attachment 99",
            extra={
                "document_id": "99",
                "discovery_mode": "link-only",
                "rights_status": "REVIEW_REQUIRED",
            },
        )
        AuthorityFrontierService.seed_from_discovery(
            [candidate], discovery_provider="PUCTProjectDiscoveryProvider"
        )
        row = AuthorityFrontier.objects.get(canonical_key=candidate.canonical_key)
        self.assertEqual(row.candidate_sources[0]["extra"], candidate.extra)

    def test_idempotent_no_duplicates_on_rerun(self):
        candidates = [
            DiscoveryCandidate(
                canonical_key="bo-gaceta:2024-9999", url="https://x/9999"
            )
        ]
        AuthorityFrontierService.seed_from_discovery(candidates, discovery_provider="P")
        result2 = AuthorityFrontierService.seed_from_discovery(
            candidates, discovery_provider="P"
        )
        self.assertEqual(result2["discovery_created"], 0)
        self.assertEqual(result2["discovery_appended"], 0)
        self.assertEqual(result2["discovery_skipped"], 1)
        self.assertEqual(
            AuthorityFrontier.objects.filter(
                canonical_key="bo-gaceta:2024-9999"
            ).count(),
            1,
        )

    def test_new_candidate_for_existing_key_appends_without_overwrite(self):
        """A changed listing candidate augments the append-only source trail."""
        first = [
            DiscoveryCandidate(
                canonical_key="bo-gaceta:2024-4242", url="https://x/first"
            )
        ]
        second = [
            DiscoveryCandidate(
                canonical_key="bo-gaceta:2024-4242", url="https://x/second"
            )
        ]
        AuthorityFrontierService.seed_from_discovery(first, discovery_provider="P")
        result = AuthorityFrontierService.seed_from_discovery(
            second, discovery_provider="P"
        )
        row = AuthorityFrontier.objects.get(canonical_key="bo-gaceta:2024-4242")
        self.assertEqual(result["discovery_appended"], 1)
        self.assertEqual(result["discovery_skipped"], 0)
        self.assertEqual(len(row.candidate_sources), 2)
        self.assertEqual(row.candidate_sources[0]["url"], "https://x/first")
        self.assertEqual(row.candidate_sources[1]["url"], "https://x/second")
        self.assertNotEqual(
            row.candidate_sources[0]["discovery_id"],
            row.candidate_sources[1]["discovery_id"],
        )

    def test_changed_metadata_at_same_url_appends_new_observation(self):
        first = DiscoveryCandidate(
            canonical_key="ercot-planning:9",
            url="https://x/planning-guide-9",
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
        AuthorityFrontierService.seed_from_discovery(
            [first],
            discovery_provider="P",
        )
        result = AuthorityFrontierService.seed_from_discovery(
            [changed],
            discovery_provider="P",
        )
        row = AuthorityFrontier.objects.get(canonical_key=first.canonical_key)
        self.assertEqual(result["discovery_appended"], 1)
        self.assertEqual(len(row.candidate_sources), 2)
        self.assertNotEqual(
            row.candidate_sources[0]["discovery_id"],
            row.candidate_sources[1]["discovery_id"],
        )
        self.assertEqual(
            row.candidate_sources[1]["extra"]["current_version"],
            False,
        )

    def test_never_resets_in_flight_row(self):
        row = AuthorityFrontier.objects.create(
            canonical_key="bo-gaceta:2024-5555",
            authority="bo-gaceta",
            discovery_state=C.DISCOVERY_STATE_IN_PROGRESS,
        )
        candidates = [
            DiscoveryCandidate(
                canonical_key="bo-gaceta:2024-5555", url="https://x/5555"
            )
        ]
        result = AuthorityFrontierService.seed_from_discovery(
            candidates, discovery_provider="P"
        )
        row.refresh_from_db()
        self.assertEqual(result["discovery_created"], 0)
        self.assertEqual(result["discovery_appended"], 1)
        self.assertEqual(result["discovery_skipped"], 0)
        self.assertEqual(row.discovery_state, C.DISCOVERY_STATE_IN_PROGRESS)
        self.assertEqual(row.candidate_sources[0]["url"], "https://x/5555")

    def test_never_resets_ingested_row(self):
        row = AuthorityFrontier.objects.create(
            canonical_key="bo-gaceta:2024-6666",
            authority="bo-gaceta",
            discovery_state=C.DISCOVERY_STATE_INGESTED,
        )
        candidates = [
            DiscoveryCandidate(
                canonical_key="bo-gaceta:2024-6666", url="https://x/6666"
            )
        ]
        AuthorityFrontierService.seed_from_discovery(candidates, discovery_provider="P")
        row.refresh_from_db()
        self.assertEqual(row.discovery_state, C.DISCOVERY_STATE_INGESTED)
        self.assertEqual(row.candidate_sources[0]["url"], "https://x/6666")

    def test_jurisdiction_and_authority_type_classified_when_known(self):
        candidates = [
            DiscoveryCandidate(canonical_key="usc-15:9999", url="https://x/9999")
        ]
        AuthorityFrontierService.seed_from_discovery(candidates, discovery_provider="P")
        row = AuthorityFrontier.objects.get(canonical_key="usc-15:9999")
        self.assertEqual(row.jurisdiction, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(row.authority_type, C.AUTHORITY_TYPE_STATUTE)

    def test_unrecognized_authority_gets_null_classification(self):
        candidates = [
            DiscoveryCandidate(
                canonical_key="totally-unknown-prefix:1", url="https://x/1"
            )
        ]
        AuthorityFrontierService.seed_from_discovery(candidates, discovery_provider="P")
        row = AuthorityFrontier.objects.get(canonical_key="totally-unknown-prefix:1")
        self.assertIsNone(row.jurisdiction)
        self.assertIsNone(row.authority_type)

    def test_empty_candidates_is_a_noop(self):
        result = AuthorityFrontierService.seed_from_discovery(
            [], discovery_provider="P"
        )
        self.assertEqual(result["discovery_created"], 0)
        self.assertEqual(result["discovery_appended"], 0)
        self.assertEqual(result["discovery_skipped"], 0)
        self.assertEqual(result["queued_keys"], [])
