"""Tests for the chat-facing ``astart_deep_research`` kickoff tool."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms.tools.research_tools import astart_deep_research
from opencontractserver.research.models import ResearchReport

User = get_user_model()


class AstartDeepResearchTestCase(TransactionTestCase):
    """Uses TransactionTestCase because ``astart_deep_research`` invokes
    ``sync_to_async`` which dispatches DB work to a thread; TestCase's
    per-test transaction wouldn't be visible there."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)

    def test_creates_report_and_enqueues(self):
        with patch(
            "opencontractserver.tasks.research_tasks.run_deep_research.delay"
        ) as enq:
            # Tool is async; run it directly.
            import asyncio

            result = asyncio.run(
                astart_deep_research(
                    task_description="Find every indemnification clause.",
                    title="Indemnity Review",
                    corpus_id=self.corpus.pk,
                    user_id=self.user.pk,
                )
            )

        self.assertIn("Deep research started", result)
        self.assertEqual(ResearchReport.objects.count(), 1)
        report = ResearchReport.objects.first()
        assert report is not None
        self.assertEqual(report.title, "Indemnity Review")
        self.assertEqual(report.creator, self.user)
        self.assertEqual(report.corpus, self.corpus)
        enq.assert_called_once_with(report.pk)

    def test_returns_error_string_for_unknown_corpus(self):
        import asyncio

        with patch("opencontractserver.tasks.research_tasks.run_deep_research.delay"):
            result = asyncio.run(
                astart_deep_research(
                    task_description="x",
                    corpus_id=99999999,
                    user_id=self.user.pk,
                )
            )
        self.assertTrue(result.startswith("Error"))
        self.assertEqual(ResearchReport.objects.count(), 0)

    def test_invisible_group_is_indistinguishable_from_a_missing_one(self):
        """No slug-enumeration oracle through the kickoff tool.

        ``_load_group`` used an unfiltered ``CorpusGroup.objects.filter(
        slug=...)``. That was never an access hole — ``ResearchReportService.
        start`` still refused the run — but it made the two cases *reply
        differently*: a nonexistent slug returned this tool's not-found string,
        while a real-but-invisible one fell through to start()'s
        ``PermissionError`` text. The difference let a caller enumerate every
        group slug in the install. Both cases must now return the same refusal.
        """
        import asyncio

        from opencontractserver.corpuses.models import CorpusGroup

        other = User.objects.create_user(username="mallory", password="x")
        CorpusGroup.objects.create(
            title="Private Group", slug="private-group", creator=other
        )

        with patch("opencontractserver.tasks.research_tasks.run_deep_research.delay"):
            invisible = asyncio.run(
                astart_deep_research(
                    task_description="x",
                    corpus_id=self.corpus.pk,
                    user_id=self.user.pk,
                    corpus_group_slug="private-group",
                )
            )
            missing = asyncio.run(
                astart_deep_research(
                    task_description="x",
                    corpus_id=self.corpus.pk,
                    user_id=self.user.pk,
                    corpus_group_slug="no-such-group-at-all",
                )
            )

        # Same refusal for "exists but not yours" and "does not exist".
        self.assertEqual(
            invisible.replace("private-group", "SLUG"),
            missing.replace("no-such-group-at-all", "SLUG"),
        )
        self.assertTrue(invisible.startswith("Error"))
        self.assertEqual(ResearchReport.objects.count(), 0)
        # Symmetry alone would also be satisfied if BOTH paths started leaking
        # in some new way, so pin the direction too: nothing that exists only
        # when the row was actually found may reach the caller.
        self.assertNotIn("Private Group", invisible)
        self.assertNotIn("permission", invisible.lower())

    def test_concurrency_guard_returns_friendly_message(self):
        import asyncio

        with patch("opencontractserver.tasks.research_tasks.run_deep_research.delay"):
            # First call succeeds.
            asyncio.run(
                astart_deep_research(
                    task_description="first",
                    corpus_id=self.corpus.pk,
                    user_id=self.user.pk,
                )
            )
            # Second call hits the soft-block.
            second = asyncio.run(
                astart_deep_research(
                    task_description="second",
                    corpus_id=self.corpus.pk,
                    user_id=self.user.pk,
                )
            )
        self.assertIn("Could not start", second)
        self.assertEqual(ResearchReport.objects.count(), 1)
