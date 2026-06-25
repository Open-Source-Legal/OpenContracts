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


class CrawlAnalyzerConvergeTests(TransactionTestCase):
    def setUp(self):
        self.user = _make_user("crawl-analyzer-user")

    def test_get_or_create_is_idempotent_and_keyed_on_task_name(self):
        from opencontractserver.enrichment import constants as C
        from opencontractserver.enrichment.services.crawl_authorities_service import (
            CrawlAuthoritiesService,
        )

        a1 = CrawlAuthoritiesService.get_or_create_analyzer(creator_id=self.user.id)
        a2 = CrawlAuthoritiesService.get_or_create_analyzer(creator_id=self.user.id)
        assert a1.pk == a2.pk
        assert a1.task_name == C.CRAWL_ANALYZER_TASK
        assert CrawlAuthoritiesService.get_analyzer().pk == a1.pk


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


def _make_empty_corpus_ref_mock():
    """Return a chainable MagicMock that returns [] for values_list (no outbound cites)."""
    mock_qs = MagicMock()
    mock_qs.filter.return_value = mock_qs
    mock_qs.exclude.return_value = mock_qs
    mock_qs.values_list.return_value.distinct.return_value = []
    return mock_qs


class ApplyAnalysisReuseTests(TransactionTestCase):
    """A crawl must reuse ONE provenance Analysis per authority corpus.

    Every section of an authority bootstraps into the SAME corpus (the
    provider ``title`` is constant — all ``usc-*`` sections land in the single
    "United States Code" corpus), so the BFS calls apply() on that one corpus
    once per ingested section. Without reuse, each apply() would mint a fresh
    Analysis, leaving N provenance rows on one corpus (issue #2027).
    """

    def test_apply_reuses_one_analysis_per_authority_corpus(self):
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.enrichment.services import (
            AuthorityFrontierService,
            EnrichmentService,
        )
        from opencontractserver.types.enums import JobStatus

        user = _make_user("apply-reuse-user")

        # Two depth-0 rows of the same authority; both bootstrap into ONE corpus.
        for i in range(2):
            AuthorityFrontier.objects.create(
                canonical_key=f"usc-15:{500 + i}",
                authority="usc-15",
                jurisdiction="us-federal",
                authority_type=C.AUTHORITY_TYPE_STATUTE,
                mention_count=5,
                depth=0,
                discovery_state="queued",
            )

        # The shared authority corpus + the provenance Analysis the FIRST apply
        # "creates" (apply is mocked, so we stand it up here and hand back its id).
        corpus = Corpus.objects.create(title="United States Code", creator=user)
        analyzer = EnrichmentService.get_or_create_analyzer(user.id)
        provenance = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            creator_id=user.id,
            status=JobStatus.RUNNING.value,
        )

        def _ingest_same_corpus(
            *, creator_id, frontier_row, make_public=True, relink_async=True
        ):
            AuthorityFrontierService.mark(frontier_row, "ingested")
            return {
                "status": "ingested",
                "corpus_id": corpus.id,
                "documents_created": 1,
                "documents_updated": 0,
                "documents_skipped": 0,
                "documents_restamped": 0,
                "canonical_key": frontier_row.canonical_key,
            }

        seen_analyses: list[Analysis | None] = []

        def _mock_apply(
            *, corpus_id, creator_id, types=None, analysis=None, extra_tiers=None
        ):
            # Record what the crawl threaded in, and mimic apply()'s real return
            # contract: a fresh provenance Analysis on the first (analysis=None)
            # call, the same one echoed back when reused.
            seen_analyses.append(analysis)
            return {
                "references_created": 0,
                "analysis_id": provenance.id if analysis is None else analysis.id,
            }

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=_ingest_same_corpus,
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            side_effect=_mock_apply,
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=_make_empty_corpus_ref_mock(),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=1,
                min_demand=1,
                max_authorities=50,
                per_jurisdiction_cap=100,
                token_budget=0,
            )

        self.assertEqual(summary["authorities_ingested"], 2)
        # apply() ran once per ingested section, both on the shared corpus.
        self.assertEqual(len(seen_analyses), 2)
        # First section lets apply mint the provenance Analysis (None passed in);
        # the second section REUSES it rather than minting a second row.
        self.assertIsNone(seen_analyses[0])
        reused = seen_analyses[1]
        assert reused is not None  # narrows Analysis | None -> Analysis for mypy
        self.assertEqual(reused.id, provenance.id)
        # No second enrichment Analysis was created for the corpus.
        self.assertEqual(
            Analysis.objects.filter(analyzed_corpus=corpus).count(),
            1,
            "crawl must reuse one provenance Analysis per authority corpus",
        )


class BoundsTerminationTests(TransactionTestCase):
    """Each bound must set the matching stop_reason and the loop must terminate."""

    def _make_queued_rows(
        self,
        n,
        jurisdiction="us-federal",
        authority="usc-15",
        mention_count=5,
        depth=0,
    ):
        """Create n queued frontier rows with distinct keys."""
        rows = []
        for i in range(n):
            row = AuthorityFrontier.objects.create(
                canonical_key=f"{authority}:{100 + i}",
                authority=authority,
                jurisdiction=jurisdiction,
                authority_type=C.AUTHORITY_TYPE_STATUTE,
                mention_count=mention_count,
                depth=depth,
                discovery_state="queued",
            )
            rows.append(row)
        return rows

    def _ingest_mock(self, corpus_id_start=2000):
        """Return a mock that marks rows ingested and returns an incrementing corpus_id."""
        call_count = [0]

        def _side_effect(
            *, creator_id, frontier_row, make_public=True, relink_async=True
        ):
            from opencontractserver.enrichment.services import AuthorityFrontierService

            AuthorityFrontierService.mark(frontier_row, "ingested")
            cid = corpus_id_start + call_count[0]
            call_count[0] += 1
            return {
                "status": "ingested",
                "corpus_id": cid,
                "documents_created": 1,
                "documents_updated": 0,
                "documents_skipped": 0,
                "documents_restamped": 0,
                "canonical_key": frontier_row.canonical_key,
            }

        return _side_effect

    def test_max_authorities_caps_run(self):
        """Queuing 10 rows with max_authorities=3 → ingested==3, stop_reason='max_authorities'."""
        user = _make_user("max-auth-user")
        self._make_queued_rows(10)

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=self._ingest_mock(),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=_make_empty_corpus_ref_mock(),
        ), patch(
            # seed_from_wanted_authorities is called first; patch to no-op
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=0,
                min_demand=1,
                max_authorities=3,
                per_jurisdiction_cap=100,
                token_budget=0,
            )

        self.assertEqual(summary["stop_reason"], "max_authorities")
        self.assertEqual(summary["authorities_ingested"], 3)

    def test_min_demand_floor(self):
        """Rows with mention_count=1 and min_demand=2 → nothing ingested, stop='frontier_drained'."""
        user = _make_user("min-demand-user")
        self._make_queued_rows(5, mention_count=1)  # below the floor

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=0,
                min_demand=2,
                max_authorities=50,
                per_jurisdiction_cap=100,
                token_budget=0,
            )

        self.assertEqual(summary["stop_reason"], "frontier_drained")
        self.assertEqual(summary["authorities_ingested"], 0)
        # blocked_by_bound must be non-empty — non-silent accounting
        self.assertGreater(
            summary["blocked_by_bound"].get("min_demand_or_depth", 0),
            0,
            "blocked_by_bound must report rows left below the min_demand floor",
        )

    def test_max_depth_halts_recursion(self):
        """Re-extraction always yields a fresh child key; max_depth=1 → no depth>1 rows."""
        user = _make_user("max-depth-user")
        # One seed row at depth=0.
        AuthorityFrontier.objects.create(
            canonical_key="usc-15:200",
            authority="usc-15",
            jurisdiction="us-federal",
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            mention_count=5,
            depth=0,
            discovery_state="queued",
        )

        child_key = "usc-15:201"
        # After ingesting the depth-0 row, for_corpus returns one new key.
        mock_refs = MagicMock()
        mock_refs.filter.return_value = mock_refs
        mock_refs.exclude.return_value = mock_refs
        mock_refs.values_list.return_value.distinct.return_value = [child_key]

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=self._ingest_mock(corpus_id_start=3000),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 1},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=mock_refs,
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=1,
                min_demand=1,
                max_authorities=50,
                per_jurisdiction_cap=100,
                token_budget=0,
            )

        # The depth=0 row was ingested and seeded a depth=1 child.
        # The depth=1 child was also ingested (max_depth=1 means depth<=1 is ok).
        # No depth=2 rows should exist because row.depth < max_depth is False at depth=1.
        self.assertFalse(
            AuthorityFrontier.objects.filter(depth__gt=1).exists(),
            "no frontier rows should be created at depth > max_depth",
        )

    def test_per_jurisdiction_cap(self):
        """5 ingestable us-de rows with cap=2 → 2 ingested, 3 parked at deferred_cap."""
        user = _make_user("juris-cap-user")
        self._make_queued_rows(
            5, jurisdiction="us-de", authority="dgcl", mention_count=10
        )

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=self._ingest_mock(corpus_id_start=4000),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=_make_empty_corpus_ref_mock(),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=0,
                min_demand=1,
                max_authorities=50,
                per_jurisdiction_cap=2,
                token_budget=0,
            )

        self.assertEqual(summary["per_jurisdiction"].get("us-de", 0), 2)
        self.assertEqual(
            summary["blocked_by_bound"].get("jurisdiction_cap:us-de", 0),
            3,
        )
        # Parked rows must be at deferred_cap (not queued, not ingested).
        parked = AuthorityFrontier.objects.filter(
            discovery_state="deferred_cap"
        ).count()
        self.assertEqual(parked, 3)

    def test_token_budget_halts(self):
        """token_budget set below one authority's estimate → stop_reason='token_budget'."""
        user = _make_user("token-budget-user")
        self._make_queued_rows(5, mention_count=5)

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=self._ingest_mock(corpus_id_start=5000),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=_make_empty_corpus_ref_mock(),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ), patch(
            # Each authority "costs" 1000 tokens; budget is 500 → stop after first.
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CrawlAuthoritiesService._estimate_tokens",
            return_value=1000,
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=1,
                min_demand=1,
                max_authorities=50,
                per_jurisdiction_cap=100,
                token_budget=500,  # less than one authority's 1000-token cost
            )

        self.assertEqual(summary["stop_reason"], "token_budget")
        # Exactly 1: the first authority ingests (cost 1000), then the budget
        # check (1000 >= 500) halts the loop before a second dequeue.
        self.assertEqual(summary["authorities_ingested"], 1)

    def test_token_budget_halts_at_max_depth_zero(self):
        """token_budget must still fire when max_depth=0.

        Regression: token accounting used to live inside the
        ``row.depth < max_depth`` re-extract guard, so a max_depth=0 crawl never
        accumulated tokens_spent and the budget silently no-op'd — it would
        ingest every row up to max_authorities. Accounting now happens on every
        ingest regardless of depth, so the budget halts after the first
        authority exactly as it does for max_depth>=1.
        """
        user = _make_user("token-budget-depth0-user")
        self._make_queued_rows(5, mention_count=5)

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=self._ingest_mock(corpus_id_start=6000),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=_make_empty_corpus_ref_mock(),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CrawlAuthoritiesService._estimate_tokens",
            return_value=1000,
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=0,  # the path that previously made token_budget a no-op
                min_demand=1,
                max_authorities=50,
                per_jurisdiction_cap=100,
                token_budget=500,  # less than one authority's 1000-token cost
            )

        self.assertEqual(summary["stop_reason"], "token_budget")
        self.assertEqual(summary["authorities_ingested"], 1)
        self.assertGreaterEqual(summary["tokens_spent_estimate"], 500)

    def test_summary_has_no_silent_truncation(self):
        """Summary always has required keys; frontier_residual sums to total row count."""
        user = _make_user("no-truncation-user")
        self._make_queued_rows(3, mention_count=1)  # below min_demand

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=0,
                min_demand=5,
                max_authorities=50,
                per_jurisdiction_cap=100,
                token_budget=0,
            )

        required_keys = {
            "stop_reason",
            "outcomes",
            "blocked_by_bound",
            "per_jurisdiction",
            "frontier_residual",
        }
        for key in required_keys:
            self.assertIn(key, summary, f"summary missing required key: {key}")

        total_in_census = sum(summary["frontier_residual"].values())
        total_in_db = AuthorityFrontier.objects.count()
        self.assertEqual(
            total_in_census,
            total_in_db,
            f"frontier_residual sums to {total_in_census} but DB has {total_in_db} rows",
        )

    def test_extracted_child_reuses_existing_frontier_row(self):
        """Re-extraction that yields a key already in the frontier → seed_child_keys skips it.

        Verifies that a pre-existing frontier row (at any state) for a child
        canonical_key is not duplicated and its state is not reset.
        """
        user = _make_user("child-reuse-user")

        # Parent row at depth 0 — the one that will be ingested.
        AuthorityFrontier.objects.create(
            canonical_key="usc-15:300",
            authority="usc-15",
            jurisdiction="us-federal",
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            mention_count=5,
            depth=0,
            discovery_state="queued",
        )
        # Child row already exists at "ingested" state — seed_child_keys must
        # treat it as a duplicate and leave it untouched.
        child_key = "usc-15:301"
        AuthorityFrontier.objects.create(
            canonical_key=child_key,
            authority="usc-15",
            jurisdiction="us-federal",
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            mention_count=3,
            depth=1,
            discovery_state="ingested",
        )

        # Confirm exactly 2 rows before the crawl.
        self.assertEqual(AuthorityFrontier.objects.count(), 2)

        # Mock: re-extraction returns the already-existing child key.
        mock_refs = MagicMock()
        mock_refs.filter.return_value = mock_refs
        mock_refs.exclude.return_value = mock_refs
        mock_refs.values_list.return_value.distinct.return_value = [child_key]

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=_make_bootstrap_mock("ingested", corpus_id=6000),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 1},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=mock_refs,
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=1,
                min_demand=1,
                max_authorities=50,
                per_jurisdiction_cap=100,
                token_budget=0,
            )

        # Still exactly 2 rows — no duplicate was created.
        self.assertEqual(
            AuthorityFrontier.objects.filter(canonical_key=child_key).count(),
            1,
            "seed_child_keys must not create a duplicate row for an existing key",
        )
        # The existing row's state must not have been reset.
        child = AuthorityFrontier.objects.get(canonical_key=child_key)
        self.assertEqual(
            child.discovery_state,
            "ingested",
            "seed_child_keys must not reset an existing row's state",
        )

    def test_deferred_cap_rows_not_re_dequeued(self):
        """5 queued rows in the same jurisdiction with cap=2 → 2 ingested, 3 deferred_cap.

        The loop must terminate (not hang) and no deferred_cap row must be
        processed by discover_and_bootstrap (assert call count == ingested count).
        """
        user = _make_user("defer-cap-requeue-user")
        self._make_queued_rows(
            5, jurisdiction="us-de", authority="dgcl", mention_count=10
        )

        bootstrap_calls = []

        def _tracking_bootstrap(
            *, creator_id, frontier_row, make_public=True, relink_async=True
        ):
            from opencontractserver.enrichment.services import AuthorityFrontierService

            bootstrap_calls.append(frontier_row.canonical_key)
            AuthorityFrontierService.mark(frontier_row, "ingested")
            return {
                "status": "ingested",
                "corpus_id": 7000 + len(bootstrap_calls),
                "documents_created": 1,
                "documents_updated": 0,
                "documents_skipped": 0,
                "documents_restamped": 0,
                "canonical_key": frontier_row.canonical_key,
            }

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=_tracking_bootstrap,
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=_make_empty_corpus_ref_mock(),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=0,
                min_demand=1,
                max_authorities=50,
                per_jurisdiction_cap=2,
                token_budget=0,
            )

        # Exactly 2 ingested, 3 parked at deferred_cap.
        self.assertEqual(summary["authorities_ingested"], 2)
        self.assertEqual(summary["per_jurisdiction"].get("us-de", 0), 2)
        parked = AuthorityFrontier.objects.filter(
            discovery_state="deferred_cap"
        ).count()
        self.assertEqual(parked, 3)
        # discover_and_bootstrap must have been called only for ingested rows.
        self.assertEqual(
            len(bootstrap_calls),
            2,
            "discover_and_bootstrap must not be called for deferred_cap rows",
        )

    def test_crawl_with_dotted_section_child_key(self):
        """Re-extraction that yields a dotted CFR section key preserves the full key.

        ``cfr-40:261.4`` must be stored as-is (the dot-suffix is NOT stripped by
        ``candidate_keys``, which only strips parenthesised subsection suffixes).
        The resulting frontier row must sit at parent.depth+1.
        """
        user = _make_user("dotted-key-user")

        # Seed row at depth 0 that will be ingested.
        AuthorityFrontier.objects.create(
            canonical_key="cfr-40:261",
            authority="cfr-40",
            jurisdiction="us-federal",
            authority_type=C.AUTHORITY_TYPE_REGULATION,
            mention_count=5,
            depth=0,
            discovery_state="queued",
        )

        dotted_child_key = "cfr-40:261.4"

        mock_refs = MagicMock()
        mock_refs.filter.return_value = mock_refs
        mock_refs.exclude.return_value = mock_refs
        mock_refs.values_list.return_value.distinct.return_value = [dotted_child_key]

        with patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=_make_bootstrap_mock("ingested", corpus_id=8000),
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".EnrichmentService.apply",
            return_value={"references_created": 1},
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".CorpusReferenceService.for_corpus",
            return_value=mock_refs,
        ), patch(
            "opencontractserver.enrichment.services.crawl_authorities_service"
            ".AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={"frontier_created": 0, "frontier_updated": 0},
        ):
            CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                max_depth=1,
                min_demand=1,
                max_authorities=50,
                per_jurisdiction_cap=100,
                token_budget=0,
            )

        # The dotted key must exist as-is — not truncated to "cfr-40:261".
        self.assertTrue(
            AuthorityFrontier.objects.filter(canonical_key=dotted_child_key).exists(),
            f"frontier row for dotted key '{dotted_child_key}' must exist after crawl",
        )
        child = AuthorityFrontier.objects.get(canonical_key=dotted_child_key)
        self.assertEqual(
            child.depth,
            1,
            "dotted child key must be seated at parent.depth + 1",
        )
