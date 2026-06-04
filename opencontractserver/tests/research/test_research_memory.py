"""Tests for the deep-research durable context-management surface.

Covers the ``ResearchReportService`` plan/memory/recovery methods, the
``resume`` + stalled-reaper path, and the recovery-aware system-prompt
builder. These back the agent's ability to store more than fits in the
context window and to recover cleanly after a worker crash.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from opencontractserver.corpuses.models import Corpus
from opencontractserver.research.constants import (
    MAX_RESEARCH_MEMORY_KEY_CHARS,
    MAX_RESEARCH_MEMORY_KEYS,
    MAX_RESEARCH_MEMORY_TOTAL_CHARS,
    MAX_RESEARCH_MEMORY_VALUE_CHARS,
    MAX_RESEARCH_PLAN_CHARS,
    build_deep_research_system_prompt,
)
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import (
    ResearchMemoryError,
    ResearchMemoryLimitExceeded,
    ResearchReportService,
)
from opencontractserver.types.enums import JobStatus

User = get_user_model()


class ResearchPlanTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)
        self.report = ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="Investigate X."
        )

    def test_update_plan_persists_and_bumps_progress(self):
        before = self.report.last_progress_at
        stored = ResearchReportService.update_plan(self.report, "1. search\n2. report")
        self.report.refresh_from_db()
        self.assertEqual(stored, "1. search\n2. report")
        self.assertEqual(self.report.plan, "1. search\n2. report")
        after = self.report.last_progress_at
        self.assertIsNotNone(after)
        assert after is not None  # narrow Optional[datetime] for mypy
        if before is not None:
            self.assertGreaterEqual(after, before)

    def test_update_plan_clamps_to_ceiling_keeping_head(self):
        head = "HEAD-MARKER "
        plan = head + ("x" * (MAX_RESEARCH_PLAN_CHARS + 5_000))
        stored = ResearchReportService.update_plan(self.report, plan)
        self.assertLessEqual(len(stored), MAX_RESEARCH_PLAN_CHARS)
        self.assertTrue(stored.startswith(head))
        self.assertTrue(stored.endswith("[truncated]"))


class ResearchMemoryTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)
        self.report = ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="Investigate X."
        )

    def test_write_read_replace(self):
        result = ResearchReportService.write_memory(self.report, "doc-1", "first note")
        self.assertEqual(result["key"], "doc-1")
        self.assertEqual(result["keys"], 1)
        self.assertEqual(
            ResearchReportService.read_memory(self.report, "doc-1"), "first note"
        )

        ResearchReportService.write_memory(self.report, "doc-1", "second note")
        self.assertEqual(
            ResearchReportService.read_memory(self.report, "doc-1"), "second note"
        )

    def test_write_append_mode(self):
        ResearchReportService.write_memory(self.report, "log", "line one")
        ResearchReportService.write_memory(
            self.report, "log", "line two", mode="append"
        )
        self.assertEqual(
            ResearchReportService.read_memory(self.report, "log"),
            "line one\nline two",
        )

    def test_delete_memory(self):
        ResearchReportService.write_memory(self.report, "k", "v")
        self.assertTrue(ResearchReportService.delete_memory(self.report, "k"))
        self.assertFalse(ResearchReportService.delete_memory(self.report, "k"))
        self.assertIsNone(ResearchReportService.read_memory(self.report, "k"))

    def test_delete_memory_bumps_progress(self):
        # Pruning keys is forward progress: a successful delete must advance
        # last_progress_at so an agent that is only deleting doesn't look
        # stalled to the reaper. A no-op delete (missing key) does not.
        ResearchReportService.write_memory(self.report, "k", "v")
        self.report.refresh_from_db()
        before = self.report.last_progress_at
        assert before is not None  # write_memory always stamps it
        ResearchReport.objects.filter(pk=self.report.pk).update(
            last_progress_at=before - timedelta(seconds=600)
        )
        self.report.refresh_from_db()
        stale = self.report.last_progress_at
        assert stale is not None

        self.assertTrue(ResearchReportService.delete_memory(self.report, "k"))
        self.report.refresh_from_db()
        bumped = self.report.last_progress_at
        assert bumped is not None
        self.assertGreater(bumped, stale)

        # No-op delete (key already gone) leaves the clock untouched.
        self.assertFalse(ResearchReportService.delete_memory(self.report, "k"))
        self.report.refresh_from_db()
        self.assertEqual(self.report.last_progress_at, bumped)

    def test_empty_key_rejected(self):
        # Malformed input raises the base ResearchMemoryError, NOT the
        # LimitExceeded subclass (no cap was exceeded — the input is invalid).
        with self.assertRaises(ResearchMemoryError) as ctx:
            ResearchReportService.write_memory(self.report, "   ", "v")
        self.assertNotIsInstance(ctx.exception, ResearchMemoryLimitExceeded)

    def test_long_key_rejected(self):
        with self.assertRaises(ResearchMemoryLimitExceeded):
            ResearchReportService.write_memory(
                self.report, "k" * (MAX_RESEARCH_MEMORY_KEY_CHARS + 1), "v"
            )

    def test_unknown_mode_rejected(self):
        # Same as empty key: a validation error, not a capacity violation.
        with self.assertRaises(ResearchMemoryError) as ctx:
            ResearchReportService.write_memory(self.report, "k", "v", mode="prepend")
        self.assertNotIsInstance(ctx.exception, ResearchMemoryLimitExceeded)

    def test_oversized_value_rejected(self):
        with self.assertRaises(ResearchMemoryLimitExceeded):
            ResearchReportService.write_memory(
                self.report, "k", "x" * (MAX_RESEARCH_MEMORY_VALUE_CHARS + 1)
            )

    def test_append_over_value_cap_rejected(self):
        # The per-value cap is enforced against the COMBINED prior + appended
        # content, not just the new chunk. Seed just under the cap, then append
        # enough to push the combined value past it.
        seed = "x" * (MAX_RESEARCH_MEMORY_VALUE_CHARS - 5)
        ResearchReportService.write_memory(self.report, "log", seed)
        with self.assertRaises(ResearchMemoryLimitExceeded):
            ResearchReportService.write_memory(
                self.report, "log", "y" * 10, mode="append"
            )
        # The rejected append left the prior value intact.
        self.assertEqual(ResearchReportService.read_memory(self.report, "log"), seed)

    def test_key_count_cap(self):
        for i in range(MAX_RESEARCH_MEMORY_KEYS):
            ResearchReportService.write_memory(self.report, f"k{i}", "v")
        with self.assertRaises(ResearchMemoryLimitExceeded):
            ResearchReportService.write_memory(self.report, "one-too-many", "v")
        # Overwriting an existing key is still allowed at the cap.
        ResearchReportService.write_memory(self.report, "k0", "updated")
        self.assertEqual(
            ResearchReportService.read_memory(self.report, "k0"), "updated"
        )

    def test_total_store_cap(self):
        # Fill close to the total cap across a few keys, then overflow. Derive
        # the count from the constants so the test stays correct if the per-
        # value / total caps are ever changed to a non-divisible ratio.
        chunk = "x" * MAX_RESEARCH_MEMORY_VALUE_CHARS
        needed = MAX_RESEARCH_MEMORY_TOTAL_CHARS // MAX_RESEARCH_MEMORY_VALUE_CHARS
        # Guard: this test only exercises the total-store cap if the key-count
        # cap doesn't fire first. If the constants ever change so that filling
        # the store needs more keys than allowed, the key-count cap would trip
        # and we'd silently be testing the wrong constraint.
        self.assertLess(
            needed,
            MAX_RESEARCH_MEMORY_KEYS,
            "adjust test: filling the total cap now needs more keys than the "
            "key-count cap allows, so the wrong cap fires first",
        )
        for i in range(needed):
            ResearchReportService.write_memory(self.report, f"k{i}", chunk)
        with self.assertRaises(ResearchMemoryLimitExceeded):
            ResearchReportService.write_memory(self.report, "overflow", chunk)

    def test_memory_index(self):
        ResearchReportService.write_memory(self.report, "b-key", "bbb")
        ResearchReportService.write_memory(self.report, "a-key", "aaaa")
        index = ResearchReportService.memory_index(self.report)
        # Sorted by key.
        self.assertEqual([i["key"] for i in index], ["a-key", "b-key"])
        self.assertEqual(index[0]["bytes"], 4)

    def test_search_memory_across_memory_and_findings(self):
        ResearchReportService.write_memory(
            self.report, "doc-1", "indemnification applies\nunrelated line"
        )
        ResearchReportService.append_finding(
            self.report,
            {
                "section": "Findings",
                "claim": "indemnification is capped",
                "citations": [1],
            },
        )
        hits = ResearchReportService.search_memory(self.report, "indemnification")
        sources = {h["source"] for h in hits}
        self.assertIn("memory", sources)
        self.assertIn("finding", sources)
        # Empty query returns nothing.
        self.assertEqual(ResearchReportService.search_memory(self.report, "  "), [])

    def test_search_memory_respects_max_hits(self):
        body = "\n".join("match line" for _ in range(100))
        ResearchReportService.write_memory(self.report, "big", body)
        hits = ResearchReportService.search_memory(self.report, "match", max_hits=5)
        self.assertEqual(len(hits), 5)


class ResearchRecoveryDigestTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)
        self.report = ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="Investigate X."
        )

    def test_digest_empty_when_fresh(self):
        digest = ResearchReportService.build_recovery_digest(self.report)
        self.assertEqual(digest["plan"], "")
        self.assertEqual(digest["findings_digest"], "")
        self.assertEqual(digest["memory_index"], "")
        self.assertFalse(digest["is_resume"])

    def test_digest_populated_marks_resume(self):
        ResearchReportService.update_plan(self.report, "my plan")
        ResearchReportService.write_memory(self.report, "doc-1", "a note")
        ResearchReportService.append_finding(
            self.report,
            {"section": "S", "claim": "a claim", "citations": [7]},
        )
        digest = ResearchReportService.build_recovery_digest(self.report)
        self.assertEqual(digest["plan"], "my plan")
        self.assertIn("a claim", digest["findings_digest"])
        self.assertIn("7", digest["findings_digest"])
        self.assertIn("doc-1", digest["memory_index"])
        self.assertTrue(digest["is_resume"])


class ResearchResumeTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)

    def test_mark_started_preserves_started_at_on_resume(self):
        report = ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="x"
        )
        ResearchReportService.mark_started(report)
        original_start = report.started_at
        self.assertIsNotNone(original_start)

        ResearchReportService.mark_started(report, resuming=True)
        report.refresh_from_db()
        self.assertEqual(report.started_at, original_start)
        self.assertEqual(report.status, JobStatus.RUNNING.value)

    def test_mark_started_resuming_sets_start_when_started_at_is_none(self):
        # Resuming a report that never recorded a start (e.g. it went RUNNING
        # via a direct status write) must still stamp ``started_at`` rather than
        # leaving it None — the ``not (resuming and report.started_at)`` guard.
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
            status=JobStatus.RUNNING.value,
        )
        self.assertIsNone(report.started_at)
        ResearchReportService.mark_started(report, resuming=True)
        report.refresh_from_db()
        self.assertIsNotNone(report.started_at)
        self.assertEqual(report.status, JobStatus.RUNNING.value)

    def test_resume_enqueues_for_non_terminal(self):
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
            status=JobStatus.RUNNING.value,
        )
        with patch(
            "opencontractserver.tasks.research_tasks.run_deep_research.delay"
        ) as enqueued:
            self.assertTrue(ResearchReportService.resume(report))
        enqueued.assert_called_once_with(report.pk)

    def test_resume_noop_for_terminal(self):
        report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="x",
            status=JobStatus.COMPLETED.value,
        )
        with patch(
            "opencontractserver.tasks.research_tasks.run_deep_research.delay"
        ) as enqueued:
            self.assertFalse(ResearchReportService.resume(report))
        enqueued.assert_not_called()

    @override_settings(DEEP_RESEARCH_STUCK_THRESHOLD_SECONDS=600)
    def test_list_stalled_finds_only_cold_running_reports(self):
        now = timezone.now()
        stale = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="stale",
            status=JobStatus.RUNNING.value,
        )
        ResearchReport.objects.filter(pk=stale.pk).update(
            last_progress_at=now - timedelta(seconds=1200)
        )
        fresh = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="fresh",
            status=JobStatus.RUNNING.value,
        )
        ResearchReport.objects.filter(pk=fresh.pk).update(last_progress_at=now)
        done = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="done",
            status=JobStatus.COMPLETED.value,
        )
        ResearchReport.objects.filter(pk=done.pk).update(
            last_progress_at=now - timedelta(seconds=1200)
        )

        stalled = ResearchReportService.list_stalled()
        self.assertIn(stale.pk, stalled)
        self.assertNotIn(fresh.pk, stalled)
        self.assertNotIn(done.pk, stalled)

    @override_settings(DEEP_RESEARCH_STUCK_THRESHOLD_SECONDS=600)
    def test_reap_stalled_research_resumes_only_cold_running_reports(self):
        from opencontractserver.tasks.research_tasks import reap_stalled_research

        now = timezone.now()
        stale = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="stale",
            status=JobStatus.RUNNING.value,
        )
        ResearchReport.objects.filter(pk=stale.pk).update(
            last_progress_at=now - timedelta(seconds=1200)
        )
        fresh = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="fresh",
            status=JobStatus.RUNNING.value,
        )
        ResearchReport.objects.filter(pk=fresh.pk).update(last_progress_at=now)

        with patch(
            "opencontractserver.tasks.research_tasks.run_deep_research.delay"
        ) as enqueued:
            result = reap_stalled_research()

        # Only the cold RUNNING report is re-enqueued.
        enqueued.assert_called_once_with(stale.pk)
        self.assertEqual(result["resumed"], [stale.pk])
        self.assertEqual(result["stalled"], 1)


class DeepResearchSystemPromptTestCase(TestCase):
    def test_prompt_documents_memory_tools(self):
        prompt = build_deep_research_system_prompt(
            task_description="Investigate X.",
            corpus_title="Cases",
            corpus_description=None,
            max_steps=60,
        )
        self.assertIn("update_research_plan", prompt)
        self.assertIn("write_memory", prompt)
        self.assertIn("search_memory", prompt)
        self.assertIn("Managing your context window", prompt)

    def test_prompt_injects_recovery_surface_and_resume_preamble(self):
        prompt = build_deep_research_system_prompt(
            task_description="Investigate X.",
            corpus_title="Cases",
            corpus_description=None,
            max_steps=60,
            plan="STEP 1: search",
            findings_digest="- (S) a claim [cites: 7]",
            memory_index="- `doc-1` (5 chars): hello",
            resuming=True,
        )
        self.assertIn("RESUMING", prompt)
        self.assertIn("STEP 1: search", prompt)
        self.assertIn("a claim", prompt)
        self.assertIn("doc-1", prompt)

    def test_prompt_omits_empty_recovery_sections(self):
        prompt = build_deep_research_system_prompt(
            task_description="Investigate X.",
            corpus_title="Cases",
            corpus_description=None,
            max_steps=60,
            plan="",
            findings_digest="",
            memory_index="",
            resuming=False,
        )
        self.assertNotIn("Your current plan", prompt)
        self.assertNotIn("Findings recorded so far", prompt)
        self.assertNotIn("RESUMING", prompt)
