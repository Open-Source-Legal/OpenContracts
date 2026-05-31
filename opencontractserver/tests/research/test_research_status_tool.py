"""Tests for the chat-facing ``acheck_deep_research_status`` tool and the
``ResearchReportService.list_recent_for_corpus`` read helper."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms.tools.research_tools import acheck_deep_research_status
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import ResearchReportService
from opencontractserver.types.enums import JobStatus

User = get_user_model()


class ListRecentForCorpusTestCase(TestCase):
    """Direct tests for the service read helper (no async boundary)."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.other = User.objects.create_user(username="bob", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)
        self.other_corpus = Corpus.objects.create(title="Other", creator=self.user)

    def test_orders_newest_first_and_scopes_to_corpus(self):
        r1 = ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="a", title="First"
        )
        r2 = ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="b", title="Second"
        )
        # A report on a different corpus must not leak in.
        ResearchReport.objects.create(
            creator=self.user, corpus=self.other_corpus, prompt="c", title="Elsewhere"
        )
        result = ResearchReportService.list_recent_for_corpus(
            user=self.user, corpus=self.corpus
        )
        self.assertEqual([r.pk for r in result], [r2.pk, r1.pk])

    def test_creator_only(self):
        # Bob's report (even on Alice's corpus) is not visible to Alice.
        ResearchReport.objects.create(
            creator=self.other, corpus=self.corpus, prompt="x", title="Bob's"
        )
        result = ResearchReportService.list_recent_for_corpus(
            user=self.user, corpus=self.corpus
        )
        self.assertEqual(result, [])

    def test_limit_is_clamped(self):
        for i in range(7):
            ResearchReport.objects.create(
                creator=self.user, corpus=self.corpus, prompt="x", title=f"R{i}"
            )
        result = ResearchReportService.list_recent_for_corpus(
            user=self.user, corpus=self.corpus, limit=3
        )
        self.assertEqual(len(result), 3)


class AcheckDeepResearchStatusTestCase(TransactionTestCase):
    """The tool wraps DB work in ``sync_to_async`` (thread); use
    TransactionTestCase so writes are visible across the boundary — same
    rationale as the kickoff-tool test."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.other = User.objects.create_user(username="bob", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)

    def _run(self):
        return asyncio.run(
            acheck_deep_research_status(corpus_id=self.corpus.pk, user_id=self.user.pk)
        )

    def test_empty_message_when_no_reports(self):
        result = self._run()
        self.assertIn("No deep-research jobs found", result)

    def test_running_report_shows_progress_and_link(self):
        running = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
            title="Running Job",
            status=JobStatus.RUNNING.value,
            step_count=3,
            max_steps=10,
        )
        result = self._run()
        self.assertIn("Running Job", result)
        self.assertIn("RUNNING", result)
        self.assertIn("step 3/10", result)
        self.assertIn(f"/research/{running.slug}", result)

    def test_completed_report_shows_duration(self):
        now = timezone.now()
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
            title="Done Job",
            status=JobStatus.COMPLETED.value,
        )
        report.started_at = now - timedelta(seconds=125)
        report.completed_at = now
        report.save(update_fields=["started_at", "completed_at"])
        result = self._run()
        self.assertIn("Done Job", result)
        self.assertIn("COMPLETED", result)
        self.assertIn("finished in 2m 5s", result)

    def test_sub_minute_duration_omits_minutes_segment(self):
        """Mirror the frontend formatResearchDuration() helper: a sub-minute run
        reads "42s", not "0m 42s"."""
        now = timezone.now()
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
            title="Quick Job",
            status=JobStatus.COMPLETED.value,
        )
        report.started_at = now - timedelta(seconds=42)
        report.completed_at = now
        report.save(update_fields=["started_at", "completed_at"])
        result = self._run()
        self.assertIn("finished in 42s", result)
        self.assertNotIn("0m 42s", result)

    def test_creator_only_excludes_other_users(self):
        ResearchReport.objects.create(
            creator=self.other,
            corpus=self.corpus,
            prompt="x",
            title="Bob Secret",
            status=JobStatus.RUNNING.value,
        )
        result = self._run()
        self.assertNotIn("Bob Secret", result)
        self.assertIn("No deep-research jobs found", result)

    def test_unknown_corpus_returns_error_string(self):
        result = asyncio.run(
            acheck_deep_research_status(corpus_id=99999999, user_id=self.user.pk)
        )
        self.assertTrue(result.startswith("Error"))
