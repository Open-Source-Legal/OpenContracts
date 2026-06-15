"""Tests for the bounded recursive authority crawl engine (Phase 5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import CrawlAuthoritiesService

User = get_user_model()


def _make_user(username="crawl-user"):
    return User.objects.create_user(username=username, password="x")


def _make_bootstrap_mock(status="ingested", corpus_id=999):
    """Return a callable that marks the frontier row terminal (like the real method)."""

    def _mock(*, creator_id, frontier_row, make_public=True, relink_async=True):
        from opencontractserver.enrichment.services import AuthorityFrontierService

        AuthorityFrontierService.mark(frontier_row, status)
        if status == "ingested":
            return {
                "status": "ingested",
                "corpus_id": corpus_id,
                "documents_created": 1,
                "documents_updated": 0,
                "documents_skipped": 0,
                "documents_restamped": 0,
                "canonical_key": frontier_row.canonical_key,
            }
        return {"status": status, "canonical_key": frontier_row.canonical_key}

    return _mock


class ImportTest(TransactionTestCase):
    def test_import(self):
        """CrawlAuthoritiesService is importable."""
        self.assertIsNotNone(CrawlAuthoritiesService)


class CeleryTaskImportTest(TransactionTestCase):
    def test_crawl_authorities_task_importable(self):
        from opencontractserver.tasks.corpus_analysis_tasks import crawl_authorities

        self.assertTrue(
            getattr(crawl_authorities, "is_corpus_analyzer_task", False),
            "crawl_authorities must be decorated with @corpus_analyzer_task",
        )


class IdempotencyTests(TransactionTestCase):
    """Crawling the same authority twice must not create duplicate rows.

    We patch ``seed_from_wanted_authorities`` to a no-op and pre-seed frontier
    rows directly — this avoids the need for a full Corpus+Annotation+
    CorpusReference fixture (which requires source_annotation FK) while still
    exercising the BFS loop's idempotency guarantee.
    """

    def test_recrawl_creates_zero_duplicate_frontier_rows(self):
        """Running crawl twice on same data leaves exactly one frontier row per key."""
        user = _make_user("idem-user")
        # Pre-seed the frontier row that the crawl would normally discover.
        AuthorityFrontier.objects.create(
            canonical_key="usc-15:78j",
            authority="usc-15",
            jurisdiction="us-federal",
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            mention_count=5,
            discovery_state="queued",
        )

        mock_bootstrap = _make_bootstrap_mock("ingested", corpus_id=1001)

        # Build a chainable mock that returns [] when values_list is called.
        _empty_qs = MagicMock()
        _empty_qs.filter.return_value = _empty_qs
        _empty_qs.exclude.return_value = _empty_qs
        _empty_qs.values_list.return_value.distinct.return_value = []

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 1},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=mock_bootstrap,
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=_empty_qs,  # no outbound cites
        ):
            CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=1,
                min_demand=1,
                max_authorities=10,
                per_jurisdiction_cap=10,
                token_budget=0,
            )
            # Second crawl — row is now 'ingested', dequeue_queued finds nothing queued.
            summary2 = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=1,
                min_demand=1,
                max_authorities=10,
                per_jurisdiction_cap=10,
                token_budget=0,
            )

        self.assertEqual(
            AuthorityFrontier.objects.filter(canonical_key="usc-15:78j").count(),
            1,
            "second crawl must not create a duplicate frontier row",
        )
        self.assertEqual(
            summary2["authorities_ingested"],
            0,
            "second crawl must ingest nothing new when frontier row is already ingested",
        )

    def test_ingested_rows_skipped_on_recrawl(self):
        """After run 1 marks a row 'ingested', run 2 sees no queued rows."""
        user = _make_user("idem-skip-user")
        AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            jurisdiction="us-federal",
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            mention_count=5,
            discovery_state="queued",
        )

        mock_bootstrap = _make_bootstrap_mock("ingested", corpus_id=1002)

        # Chainable mock that returns [] for values_list (no outbound cites).
        _empty_qs2 = MagicMock()
        _empty_qs2.filter.return_value = _empty_qs2
        _empty_qs2.exclude.return_value = _empty_qs2
        _empty_qs2.values_list.return_value.distinct.return_value = []

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 1},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=mock_bootstrap,
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=_empty_qs2,
        ):
            CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=0,
                min_demand=1,
                max_authorities=10,
                per_jurisdiction_cap=10,
                token_budget=0,
            )
            row = AuthorityFrontier.objects.get(canonical_key="usc-15:2")
            self.assertEqual(row.discovery_state, "ingested")

            summary2 = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=0,
                min_demand=1,
                max_authorities=10,
                per_jurisdiction_cap=10,
                token_budget=0,
            )

        self.assertEqual(summary2["authorities_ingested"], 0)
        self.assertEqual(summary2["stop_reason"], "frontier_drained")

    def test_child_seed_is_idempotent(self):
        """seed_child_keys called twice with same keys creates zero duplicates.

        Note: the child key must roll to a root that differs from the parent key.
        ``candidate_keys("usc-15:78j(b)")[-1]`` returns ``"usc-15:78j"`` (the
        parent), so we use ``"usc-15:78aa"`` which rolls to itself.
        """
        from opencontractserver.enrichment.services import AuthorityFrontierService

        parent = AuthorityFrontier.objects.create(
            canonical_key="usc-15:78j",
            authority="usc-15",
            depth=0,
            mention_count=3,
            discovery_state="ingested",
        )
        # "usc-15:78aa" rolls to "usc-15:78aa" (distinct from parent "usc-15:78j")
        child_raw_key = "usc-15:78aa"
        result1 = AuthorityFrontierService.seed_child_keys(parent, [child_raw_key])
        result2 = AuthorityFrontierService.seed_child_keys(parent, [child_raw_key])

        self.assertEqual(result1["child_created"], 1)
        self.assertEqual(result2["child_created"], 0)
        self.assertEqual(result2["child_skipped"], 1)
        self.assertEqual(
            AuthorityFrontier.objects.filter(authority="usc-15").count(),
            2,  # parent + one child only
        )
