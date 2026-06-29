"""Security regressions for the crawl_authorities agent surface."""

from django.test import TransactionTestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
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
