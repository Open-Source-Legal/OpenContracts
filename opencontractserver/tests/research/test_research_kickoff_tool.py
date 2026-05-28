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
