"""Security regressions for the crawl_authorities agent surface."""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from opencontractserver.analyzer.models import Analysis
from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.corpuses.models import Corpus
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services.authority_frontier_service import (
    AuthorityFrontierService,
)
from opencontractserver.enrichment.services.crawl_authorities_service import (
    CrawlAuthoritiesService,
)
from opencontractserver.llms.tools.core_tools.corpus_references import crawl_authorities

User = get_user_model()

# The module whose collaborators the DB tests patch (seed / bootstrap / apply).
_SERVICE_MODULE = "opencontractserver.enrichment.services.crawl_authorities_service"


def _make_user(username):
    """Local user factory — keeps this module self-contained.

    Inlined rather than imported from a sibling test module so a rename there
    cannot silently break these security regressions.
    """
    return User.objects.create_user(username=username, password="x")


class CrawlBoundsSanitizationTests(TestCase):
    """Pure-logic bound clamping — no ORM, so plain ``TestCase`` (no DB flush)."""

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
        # per_jurisdiction_cap floors at 1 (0 would park every row); an extreme
        # high value still clamps down to the cap.
        self.assertEqual(
            bounds["per_jurisdiction_cap"], C.CRAWL_MAX_PER_JURISDICTION_CAP
        )
        # token_budget=-1 must NOT become 0 (the "unbounded" sentinel) — a capped
        # path maps non-positive requests to the bounded default.
        self.assertEqual(bounds["token_budget"], C.CRAWL_DEFAULT_TOKEN_BUDGET)

    def test_negative_per_jurisdiction_cap_floors_to_one_not_zero(self):
        # A negative cap must not clamp to 0 (which parks every dequeued row at
        # deferred_cap and silently halts the whole crawl).
        bounds = CrawlAuthoritiesService._sanitize_bounds(
            max_depth=1,
            min_demand=1,
            max_authorities=1,
            per_jurisdiction_cap=-1,
            token_budget=1000,
        )
        self.assertEqual(
            bounds["per_jurisdiction_cap"], C.CRAWL_MIN_PER_JURISDICTION_CAP
        )
        # A legitimate small positive budget is preserved (not forced to default).
        self.assertEqual(bounds["token_budget"], 1000)

    def test_positive_token_budget_above_max_clamps_to_max(self):
        """A positive over-cap token_budget clamps down to CRAWL_MAX_TOKEN_BUDGET."""
        bounds = CrawlAuthoritiesService._sanitize_bounds(
            max_depth=1,
            min_demand=1,
            max_authorities=1,
            per_jurisdiction_cap=1,
            token_budget=C.CRAWL_MAX_TOKEN_BUDGET + 1,
        )
        self.assertEqual(bounds["token_budget"], C.CRAWL_MAX_TOKEN_BUDGET)

    def test_sanitize_token_budget_non_integer_falls_back_to_default(self):
        """A non-integer token_budget maps to the bounded default, never 0."""
        # Deliberately passing non-int values to exercise the except branch.
        self.assertEqual(
            CrawlAuthoritiesService._sanitize_token_budget("nope"),  # type: ignore[arg-type]
            C.CRAWL_DEFAULT_TOKEN_BUDGET,
        )
        self.assertEqual(
            CrawlAuthoritiesService._sanitize_token_budget(None),  # type: ignore[arg-type]
            C.CRAWL_DEFAULT_TOKEN_BUDGET,
        )


class CrawlAuthoritiesSecurityTests(TransactionTestCase):
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

        with patch(
            f"{_SERVICE_MODULE}.AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={
                "frontier_created": 0,
                "frontier_updated": 1,
                "queued_keys": [seeded.canonical_key],
            },
        ), patch(
            f"{_SERVICE_MODULE}.AuthorityDiscoveryService.discover_and_bootstrap",
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

    def test_tool_wrapper_extreme_bounds_are_sanitized_by_the_service(self):
        """The wrapper forwards bounds straight to ``crawl()`` — the single,
        load-bearing sanitizing layer (it also protects the Celery-task path).

        Extreme model-supplied bounds passed to the wrapper therefore still come
        out clamped in the actual run; the run's summary echoes the sanitized
        bounds, not the raw inputs. (Verifying end-to-end rather than mocking
        ``crawl`` is what guards against the prior bug where the wrapper clamped
        but a direct ``crawl`` caller did not.)

        A real QUEUED row is seeded so the BFS loop body actually runs (a real
        ``dequeue_queued`` claim against the DB) rather than short-circuiting on
        an empty ``canonical_keys`` set — the sanitized bounds must hold up
        through a real iteration, not just in ``_sanitize_bounds`` isolation.
        """
        user = _make_user("wrapper-clamp-user")
        seeded = AuthorityFrontier.objects.create(
            canonical_key="usc-15:70-wrapper-clamp",
            authority="usc-15",
            discovery_state=C.DISCOVERY_STATE_QUEUED,
            mention_count=5,
        )

        with patch(
            f"{_SERVICE_MODULE}.AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={
                "frontier_created": 0,
                "frontier_updated": 1,
                "queued_keys": [seeded.canonical_key],
            },
        ), patch(
            f"{_SERVICE_MODULE}.AuthorityDiscoveryService.discover_and_bootstrap",
            return_value={"status": C.DISCOVERY_STATE_FAILED},
        ) as bootstrap:
            summary = crawl_authorities(
                creator_id=user.id,
                corpus_id=1,
                max_depth=999,
                min_demand=-5,
                max_authorities=1_000_000,
                per_jurisdiction_cap=123456,
                token_budget=-1,
            )

        # The BFS loop actually dequeued and processed the seeded row — proof
        # the sanitized bounds were exercised by a real iteration, not skipped.
        self.assertEqual(bootstrap.call_count, 1)
        self.assertEqual(
            bootstrap.call_args.kwargs["frontier_row"].canonical_key,
            seeded.canonical_key,
        )

        self.assertEqual(summary["max_depth"], C.CRAWL_MAX_MAX_DEPTH)
        self.assertEqual(summary["min_demand"], 0)
        self.assertEqual(summary["max_authorities"], C.CRAWL_MAX_MAX_AUTHORITIES)
        self.assertEqual(
            summary["per_jurisdiction_cap"], C.CRAWL_MAX_PER_JURISDICTION_CAP
        )
        self.assertEqual(summary["token_budget"], C.CRAWL_DEFAULT_TOKEN_BUDGET)

    def test_celery_task_path_clamps_extreme_bounds(self):
        """The Celery analyzer task is clamped by the SAME service guard.

        Calling the task directly (``.apply()``) bypasses the input-schema gate,
        so this proves the protection lives in ``CrawlAuthoritiesService.crawl``
        — not only in the schema or the LLM-tool wrapper. A task caller that
        smuggles past the schema still gets clamped bounds in the run summary.

        A real QUEUED row is seeded so the BFS loop body actually runs (a real
        ``dequeue_queued`` claim against the DB) rather than short-circuiting on
        an empty ``canonical_keys`` set.
        """
        from opencontractserver.tasks.corpus_analysis_tasks import (
            crawl_authorities as crawl_authorities_task,
        )

        user = _make_user("celery-task-clamp-user")
        corpus = Corpus.objects.create(title="Crawl Corpus", creator=user)
        analyzer = CrawlAuthoritiesService.get_or_create_analyzer(user.id)
        analysis = Analysis.objects.create(
            analyzer=analyzer, analyzed_corpus=corpus, creator=user
        )
        seeded = AuthorityFrontier.objects.create(
            canonical_key="usc-15:71-celery-clamp",
            authority="usc-15",
            discovery_state=C.DISCOVERY_STATE_QUEUED,
            mention_count=5,
        )

        with patch(
            f"{_SERVICE_MODULE}.AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={
                "frontier_created": 0,
                "frontier_updated": 1,
                "queued_keys": [seeded.canonical_key],
            },
        ), patch(
            f"{_SERVICE_MODULE}.AuthorityDiscoveryService.discover_and_bootstrap",
            return_value={"status": C.DISCOVERY_STATE_FAILED},
        ) as bootstrap:
            summary = (
                crawl_authorities_task.si(  # type: ignore[attr-defined]
                    corpus_id=corpus.id,
                    analysis_id=analysis.id,
                    max_depth=999,
                    min_demand=-5,
                    max_authorities=1_000_000,
                    per_jurisdiction_cap=123456,
                    token_budget=-1,
                )
                .apply()
                .get()
            )

        # The BFS loop actually dequeued and processed the seeded row.
        self.assertEqual(bootstrap.call_count, 1)
        self.assertEqual(
            bootstrap.call_args.kwargs["frontier_row"].canonical_key,
            seeded.canonical_key,
        )

        self.assertEqual(summary["max_depth"], C.CRAWL_MAX_MAX_DEPTH)
        self.assertEqual(summary["min_demand"], 0)
        self.assertEqual(summary["max_authorities"], C.CRAWL_MAX_MAX_AUTHORITIES)
        self.assertEqual(
            summary["per_jurisdiction_cap"], C.CRAWL_MAX_PER_JURISDICTION_CAP
        )
        self.assertEqual(summary["token_budget"], C.CRAWL_DEFAULT_TOKEN_BUDGET)

    def test_crawl_honors_token_budget_cap_in_bfs_loop(self):
        """A positive over-cap token_budget is clamped, AND the clamped value
        actually stops the BFS loop mid-run once spend crosses it.

        A real QUEUED row is seeded and ingested by the loop's first
        iteration (real ``dequeue_queued`` claim, not the empty-``queued_keys``
        short-circuit); ``_estimate_tokens`` is patched to report a spend that
        exceeds a tiny ``token_budget``, so the loop's SECOND iteration must
        observe the cap and stop with ``stop_reason == "token_budget"`` — proof
        the check is enforced against live ``tokens_spent`` inside the loop,
        not just echoed back from ``_sanitize_bounds``.
        """
        user = _make_user("token-cap-bfs-user")
        seeded = AuthorityFrontier.objects.create(
            canonical_key="usc-15:72-token-budget",
            authority="usc-15",
            discovery_state=C.DISCOVERY_STATE_QUEUED,
            mention_count=5,
            depth=0,
        )

        def _ingest_row(
            *, creator_id, frontier_row, make_public=True, relink_async=True
        ):
            AuthorityFrontierService.mark(frontier_row, C.DISCOVERY_STATE_INGESTED)
            return {"status": C.DISCOVERY_STATE_INGESTED, "corpus_id": 99}

        with patch(
            f"{_SERVICE_MODULE}.AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={
                "frontier_created": 0,
                "frontier_updated": 1,
                "queued_keys": [seeded.canonical_key],
            },
        ), patch(
            f"{_SERVICE_MODULE}.AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=_ingest_row,
        ), patch(
            f"{_SERVICE_MODULE}.CrawlAuthoritiesService._estimate_tokens",
            return_value=500,
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                corpus_id=1,
                max_depth=0,  # no child-seed branch; isolate the budget check
                max_authorities=5,
                token_budget=1,  # positive, so NOT the non-positive/default path
            )

        # The clamp is a no-op for an in-range positive request...
        self.assertEqual(summary["token_budget"], 1)
        # ...but the loop still ran one real iteration (real dequeue + ingest)
        # before the cap fired on the next iteration's check.
        self.assertEqual(summary["authorities_ingested"], 1)
        self.assertEqual(summary["tokens_spent_estimate"], 500)
        self.assertEqual(summary["stop_reason"], "token_budget")
        seeded.refresh_from_db()
        self.assertEqual(seeded.discovery_state, C.DISCOVERY_STATE_INGESTED)

    def test_crawl_keys_updated_when_scoped_crawl_ingests_and_seeds_children(self):
        """crawl_keys grows after a scoped-corpus crawl ingests a row and re-seeds,
        and the newly-seeded child key is actually dequeue-eligible in the SAME
        run — i.e. the growth is not a no-op.

        ``mock_refs`` returns a real (non-empty) outbound canonical key, so
        ``seed_child_keys`` creates a real depth+1 ``AuthorityFrontier`` row and
        ``crawl_keys.update(seeded["queued_keys"])`` has something to add.
        ``max_authorities=2`` lets the loop run a SECOND iteration: if
        ``crawl_keys`` had NOT grown, the second ``dequeue_queued`` call would
        be scoped to only the (now-ingested) parent key and return nothing,
        the run would stop at ``authorities_ingested == 1``, and the child row
        would remain ``queued`` forever. Asserting ``== 2`` and that the child
        row is ``INGESTED`` proves the growth path is load-bearing.
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
        child_key = "usc-15:51-child"

        ingested_keys: list[str] = []

        def _ingest_row(
            *, creator_id, frontier_row, make_public=True, relink_async=True
        ):
            AuthorityFrontierService.mark(frontier_row, C.DISCOVERY_STATE_INGESTED)
            ingested_keys.append(frontier_row.canonical_key)
            return {"status": C.DISCOVERY_STATE_INGESTED, "corpus_id": 99}

        mock_refs = MagicMock()
        mock_refs.filter.return_value = mock_refs
        mock_refs.exclude.return_value = mock_refs
        # Non-empty outbound citation so seed_child_keys actually creates a
        # depth+1 row and crawl_keys.update(...) has a real key to add — this
        # is the growth path Finding 2 requires the test to exercise.
        mock_refs.values_list.return_value.distinct.return_value = [child_key]

        with patch(
            f"{_SERVICE_MODULE}.AuthorityFrontierService.seed_from_wanted_authorities",
            return_value={
                "frontier_created": 1,
                "frontier_updated": 0,
                "queued_keys": [seeded.canonical_key],
            },
        ), patch(
            f"{_SERVICE_MODULE}.AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=_ingest_row,
        ), patch(
            f"{_SERVICE_MODULE}.EnrichmentService.apply",
            return_value={"references_created": 0},
        ), patch(
            f"{_SERVICE_MODULE}.CorpusReferenceService.for_corpus_by_source",
            return_value=mock_refs,
        ):
            summary = CrawlAuthoritiesService.crawl(
                creator_id=user.id,
                corpus_id=1,
                max_depth=1,  # depth=0 < 1 → child-seed branch runs
                # seed_child_keys always seeds new rows at mention_count=1, so
                # min_demand must not exceed that or the child is dequeue-dead
                # on arrival regardless of crawl_keys scoping.
                min_demand=0,
                max_authorities=2,  # room for a second BFS iteration
                token_budget=0,
            )

        self.assertEqual(summary["children_seeded"], 1)
        # Both the depth-0 parent AND the depth-1 child were ingested — the
        # second dequeue only found the child because crawl_keys grew to
        # include it.
        self.assertEqual(summary["authorities_ingested"], 2)
        self.assertEqual(summary["corpus_id"], 1)
        self.assertEqual(ingested_keys, [seeded.canonical_key, child_key])

        child_row = AuthorityFrontier.objects.get(canonical_key=child_key)
        self.assertEqual(child_row.discovery_state, C.DISCOVERY_STATE_INGESTED)
        self.assertEqual(child_row.depth, 1)


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
