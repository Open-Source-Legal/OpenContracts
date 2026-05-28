"""Tests for the ResearchReport model."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.research.models import ResearchReport
from opencontractserver.types.enums import JobStatus

User = get_user_model()


class ResearchReportModelTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.other = User.objects.create_user(username="bob", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)

    def test_create_with_defaults(self):
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="Explain force majeure clauses.",
        )
        self.assertEqual(report.status, JobStatus.QUEUED.value)
        self.assertEqual(report.findings, [])
        self.assertEqual(report.citations, [])
        self.assertEqual(report.tool_call_log, [])
        self.assertEqual(report.warnings, [])
        self.assertEqual(report.model_usage, {})
        self.assertEqual(report.step_count, 0)
        self.assertGreater(report.max_steps, 0)
        self.assertFalse(report.cancel_requested)
        self.assertFalse(report.is_terminal)

    def test_slug_auto_generated_and_unique(self):
        r1 = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
            title="Lease Obligations",
        )
        r2 = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
            title="Lease Obligations",
        )
        self.assertTrue(r1.slug)
        self.assertNotEqual(r1.slug, r2.slug)

    def test_is_terminal(self):
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
        )
        for status in (
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        ):
            report.status = status
            report.save(update_fields=["status"])
            self.assertTrue(report.is_terminal)
        report.status = JobStatus.RUNNING.value
        report.save(update_fields=["status"])
        self.assertFalse(report.is_terminal)

    def test_visible_to_user_creator_only(self):
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
        )
        self.assertIn(report, ResearchReport.objects.visible_to_user(self.user))
        self.assertNotIn(report, ResearchReport.objects.visible_to_user(self.other))

    def test_visible_to_user_anonymous_sees_nothing(self):
        ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="x", is_public=True
        )
        self.assertEqual(ResearchReport.objects.visible_to_user(None).count(), 0)

    def test_visible_to_user_superuser_sees_all(self):
        admin = User.objects.create_superuser(username="admin", password="x")
        ResearchReport.objects.create(creator=self.user, corpus=self.corpus, prompt="x")
        ResearchReport.objects.create(
            creator=self.other, corpus=self.corpus, prompt="y"
        )
        self.assertEqual(ResearchReport.objects.visible_to_user(admin).count(), 2)
