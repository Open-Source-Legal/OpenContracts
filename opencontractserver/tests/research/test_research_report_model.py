"""Tests for the ResearchReport model."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

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

    def test_duration_seconds_computed_from_timestamps(self):
        """duration_seconds is derived from started_at/completed_at, not stored.

        Guards the invariant relied on by the status-tool duration tests, which
        set the timestamps directly (bypassing finalize()) and expect the
        property to compute the elapsed wall-clock time.
        """
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
        )
        # No timestamps yet → None (not 0).
        self.assertIsNone(report.duration_seconds)

        # Set timestamps directly, bypassing finalize(): the property must still
        # compute correctly, proving it reads from the fields at access time.
        now = timezone.now()
        report.started_at = now - timedelta(seconds=125)
        report.completed_at = now
        report.save(update_fields=["started_at", "completed_at"])
        duration = report.duration_seconds
        self.assertIsNotNone(duration)
        assert duration is not None  # narrow Optional for type-checker
        self.assertAlmostEqual(duration, 125.0)

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

    def test_visible_to_user_superuser_has_no_blanket_access(self):
        """A superuser is authorized like any normal user (scoped admin
        access, 2026-05): it does NOT see reports authored by others, only
        its own. ``ResearchReport`` visibility is purely creator-based
        (no is_public / guardian), so a no-grant admin's report list is
        scoped to its own authorship.
        """
        # Unique username avoids colliding with the migration-seeded
        # superuser ("admin") created by 0003_create_initial_superuser when
        # DJANGO_SUPERUSER_USERNAME is set in the environment.
        admin = User.objects.create_superuser(username="scoped-admin", password="x")
        # Reports authored by *other* users must NOT be visible to the admin.
        user_report = ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="x"
        )
        other_report = ResearchReport.objects.create(
            creator=self.other, corpus=self.corpus, prompt="y"
        )
        # An admin-authored report, by contrast, IS visible to the admin.
        admin_report = ResearchReport.objects.create(
            creator=admin, corpus=self.corpus, prompt="z"
        )
        visible = ResearchReport.objects.visible_to_user(admin)
        self.assertIn(admin_report, visible)
        self.assertNotIn(user_report, visible)
        self.assertNotIn(other_report, visible)
