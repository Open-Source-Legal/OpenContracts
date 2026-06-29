"""Security regressions for the crawl_authorities agent surface."""

from django.test import TransactionTestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services.authority_frontier_service import (
    AuthorityFrontierService,
)
from opencontractserver.enrichment.services.crawl_authorities_service import (
    CrawlAuthoritiesService,
)
from opencontractserver.llms.tools.core_tools.corpus_references import crawl_authorities
from opencontractserver.tests.test_crawl_authorities import _make_user


class CrawlAuthoritiesSecurityTests(TransactionTestCase):
    def test_crawl_bounds_are_clamped_before_service_execution(self):
        bounds = CrawlAuthoritiesService._sanitize_bounds(
            max_depth=999,
            min_demand=-5,
            max_authorities=1_000_000,
            per_jurisdiction_cap=123456,
            token_budget=-1,
        )

        self.assertEqual(bounds["max_depth"], C.CRAWL_MAX_MAX_DEPTH)
        self.assertEqual(bounds["min_demand"], 0)
        self.assertEqual(bounds["max_authorities"], C.CRAWL_MAX_MAX_AUTHORITIES)
        self.assertEqual(
            bounds["per_jurisdiction_cap"], C.CRAWL_MAX_PER_JURISDICTION_CAP
        )
        self.assertEqual(bounds["token_budget"], 0)

    def test_corpus_crawl_does_not_claim_unseeded_global_frontier(self):
        user = _make_user("scoped-crawl-user")
        seeded = AuthorityFrontier.objects.create(
            canonical_key="usc-15:1-seeded",
            authority="usc-15",
            discovery_state=C.DISCOVERY_STATE_QUEUED,
            mention_count=5,
        )
        unrelated = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2-global",
            authority="usc-15",
            discovery_state=C.DISCOVERY_STATE_QUEUED,
            mention_count=100,
        )

        original_seed = (
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities"
        )
        original_bootstrap = (
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap"
        )
        from unittest.mock import patch

        with patch(
            original_seed,
            return_value={
                "frontier_created": 0,
                "frontier_updated": 1,
                "queued_keys": [seeded.canonical_key],
            },
        ), patch(
            original_bootstrap,
            return_value={"status": C.DISCOVERY_STATE_FAILED},
        ) as bootstrap:
            CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                corpus_id=123,
                max_depth=1,
                min_demand=1,
                max_authorities=1,
                token_budget=0,
            )

        self.assertEqual(bootstrap.call_count, 1)
        self.assertEqual(
            bootstrap.call_args.kwargs["frontier_row"].canonical_key,
            seeded.canonical_key,
        )
        unrelated.refresh_from_db()
        self.assertEqual(unrelated.discovery_state, C.DISCOVERY_STATE_QUEUED)

    def test_tool_wrapper_clamps_extreme_model_supplied_bounds(self):
        user = _make_user("wrapper-clamp-user")
        captured = {}

        def fake_crawl(**kwargs):
            captured.update(kwargs)
            return {"ok": True}

        from unittest.mock import patch

        with patch.object(CrawlAuthoritiesService, "crawl", side_effect=fake_crawl):
            crawl_authorities(
                creator_id=user.id,
                corpus_id=1,
                max_depth=999,
                min_demand=-5,
                max_authorities=1_000_000,
                per_jurisdiction_cap=123456,
                token_budget=-1,
            )

        self.assertEqual(captured["max_depth"], C.CRAWL_MAX_MAX_DEPTH)
        self.assertEqual(captured["min_demand"], 0)
        self.assertEqual(captured["max_authorities"], C.CRAWL_MAX_MAX_AUTHORITIES)
        self.assertEqual(
            captured["per_jurisdiction_cap"], C.CRAWL_MAX_PER_JURISDICTION_CAP
        )
        self.assertEqual(captured["token_budget"], 0)

    def test_clamp_int_falls_back_to_lower_for_non_integer_value(self):
        """_clamp_int returns the lower-bound when value is not int-convertible."""
        # Deliberately passing non-int values to exercise the except branch.
        self.assertEqual(
            CrawlAuthoritiesService._clamp_int(None, lower=3, upper=10),  # type: ignore[arg-type]
            3,
        )
        self.assertEqual(
            CrawlAuthoritiesService._clamp_int("not-a-number", lower=5, upper=20),  # type: ignore[arg-type]
            5,
        )

    def test_crawl_keys_updated_when_scoped_crawl_ingests_and_seeds_children(self):
        """crawl_keys grows after a scoped-corpus crawl ingests a row and re-seeds.

        Requires: seed returns queued_keys (non-None crawl_keys), the row is
        ingested, and row.depth < max_depth so the child-seed path executes.
        The crawl_keys.update(seeded.get("queued_keys") or []) line is only
        reached when all three conditions hold simultaneously.
        """
        user = _make_user("crawl-keys-grow-user")
        seeded = AuthorityFrontier.objects.create(
            canonical_key="usc-15:50-seed",
            authority="usc-15",
            jurisdiction="us-federal",
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state=C.DISCOVERY_STATE_QUEUED,
            mention_count=5,
            depth=0,
        )

        from unittest.mock import MagicMock, patch

        _module = "opencontractserver.enrichment.services.crawl_authorities_service"

        def _ingest_row(
            *, creator_id, frontier_row, make_public=True, relink_async=True
        ):
            AuthorityFrontierService.mark(frontier_row, C.DISCOVERY_STATE_INGESTED)
            return {"status": C.DISCOVERY_STATE_INGESTED, "corpus_id": 99}

        mock_refs = MagicMock()
        mock_refs.filter.return_value = mock_refs
        mock_refs.exclude.return_value = mock_refs
        mock_refs.values_list.return_value.distinct.return_value = []

        with patch(
            f"{_module}.AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={
                "frontier_created": 1,
                "frontier_updated": 0,
                "queued_keys": [seeded.canonical_key],
            },
        ), patch(
            f"{_module}.AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=_ingest_row,
        ), patch(
            f"{_module}.EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            f"{_module}.CorpusReferenceService.for_corpus",
            return_value=mock_refs,
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                corpus_id=1,
                max_depth=1,  # depth=0 < 1 → child-seed branch runs
                max_authorities=1,
                token_budget=0,
            )

        self.assertEqual(summary["authorities_ingested"], 1)
        self.assertEqual(summary["corpus_id"], 1)


class AuthorityFrontierScopingTests(TransactionTestCase):
    def test_dequeue_queued_with_empty_canonical_keys_returns_empty_without_claiming(
        self,
    ):
        """dequeue_queued short-circuits on an empty key set, claiming no rows."""
        AuthorityFrontier.objects.create(
            canonical_key="usc-42:200-empty-test",
            authority="usc-42",
            discovery_state=C.DISCOVERY_STATE_QUEUED,
            mention_count=10,
        )

        # Empty set → the early-return branch fires and the DB row is untouched.
        result = AuthorityFrontierService.dequeue_queued(canonical_keys=set())
        self.assertEqual(result, [])

        # Empty list form should also short-circuit.
        result_list = AuthorityFrontierService.dequeue_queued(canonical_keys=[])
        self.assertEqual(result_list, [])

        # The queued row must not have been claimed (still queued).
        row = AuthorityFrontier.objects.get(canonical_key="usc-42:200-empty-test")
        self.assertEqual(row.discovery_state, C.DISCOVERY_STATE_QUEUED)
