"""Tests for the ResearchReportService."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import (
    ConcurrentResearchInProgress,
    ResearchCancelled,
    ResearchReportService,
    _derive_title_from_prompt,
    _render_citations,
    _strip_fabricated_links,
)
from opencontractserver.types.enums import JobStatus

User = get_user_model()


@override_settings(DEEP_RESEARCH_CONCURRENCY_GUARD_SECONDS=3600)
class ResearchReportServiceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.outsider = User.objects.create_user(username="eve", password="x")
        self.corpus = Corpus.objects.create(
            title="Cases", creator=self.user, is_public=False
        )
        # A second public corpus so visibility checks have something to chew on.
        self.public_corpus = Corpus.objects.create(
            title="Public", creator=self.user, is_public=True
        )

    # ------------------------------------------------------------------
    # start()
    # ------------------------------------------------------------------
    def test_start_creates_queued_row_and_enqueues_task(self):
        # ``ResearchReportService.start`` defers the Celery ``delay`` to
        # ``transaction.on_commit`` so the row is durable before the worker
        # picks it up. In a ``TestCase`` (transaction rolled back at tear-down)
        # those callbacks never fire unless we explicitly capture them.
        with patch(
            "opencontractserver.tasks.research_tasks.run_deep_research.delay"
        ) as enqueued, self.captureOnCommitCallbacks(execute=True):
            report = ResearchReportService.start(
                user=self.user,
                corpus=self.corpus,
                prompt="Find the indemnification clauses.",
            )

        self.assertEqual(report.status, JobStatus.QUEUED.value)
        self.assertEqual(report.creator, self.user)
        self.assertEqual(report.corpus, self.corpus)
        self.assertEqual(report.prompt, "Find the indemnification clauses.")
        self.assertTrue(report.slug)
        enqueued.assert_called_once_with(report.pk)

    def test_start_denies_without_corpus_read(self):
        # outsider has no READ on the private corpus.
        with self.assertRaises(PermissionError):
            ResearchReportService.start(
                user=self.outsider,
                corpus=self.corpus,
                prompt="x",
            )

    def test_start_uses_supplied_title(self):
        with patch("opencontractserver.tasks.research_tasks.run_deep_research.delay"):
            report = ResearchReportService.start(
                user=self.user,
                corpus=self.corpus,
                prompt="x",
                title="Custom Title",
            )
        self.assertEqual(report.title, "Custom Title")

    def test_start_concurrency_guard_blocks_second_job(self):
        with patch("opencontractserver.tasks.research_tasks.run_deep_research.delay"):
            ResearchReportService.start(
                user=self.user, corpus=self.corpus, prompt="first"
            )
            with self.assertRaises(ConcurrentResearchInProgress):
                ResearchReportService.start(
                    user=self.user, corpus=self.corpus, prompt="second"
                )

    def test_start_concurrency_guard_allows_after_terminal(self):
        with patch("opencontractserver.tasks.research_tasks.run_deep_research.delay"):
            r1 = ResearchReportService.start(
                user=self.user, corpus=self.corpus, prompt="first"
            )
            ResearchReportService.mark_completed(r1)
            r2 = ResearchReportService.start(
                user=self.user, corpus=self.corpus, prompt="second"
            )
        self.assertNotEqual(r1.pk, r2.pk)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def _make_report(self, **overrides) -> ResearchReport:
        kwargs = dict(creator=self.user, corpus=self.corpus, prompt="x")
        kwargs.update(overrides)
        return ResearchReport.objects.create(**kwargs)

    def test_mark_started_sets_running_and_timestamps(self):
        report = self._make_report()
        ResearchReportService.mark_started(report)
        report.refresh_from_db()
        self.assertEqual(report.status, JobStatus.RUNNING.value)
        self.assertIsNotNone(report.started_at)
        self.assertIsNotNone(report.last_progress_at)

    def test_mark_completed_records_warnings_and_usage(self):
        report = self._make_report()
        ResearchReportService.mark_completed(
            report,
            warnings=["budget_exhausted"],
            model_usage={"total_tokens": 4321},
        )
        report.refresh_from_db()
        self.assertEqual(report.status, JobStatus.COMPLETED.value)
        self.assertIn("budget_exhausted", report.warnings)
        self.assertEqual(report.model_usage["total_tokens"], 4321)
        self.assertIsNotNone(report.completed_at)

    def test_mark_failed_records_error(self):
        report = self._make_report()
        ResearchReportService.mark_failed(report, "boom")
        report.refresh_from_db()
        self.assertEqual(report.status, JobStatus.FAILED.value)
        self.assertEqual(report.error_message, "boom")

    def test_mark_cancelled_sets_status(self):
        report = self._make_report()
        ResearchReportService.mark_cancelled(report)
        report.refresh_from_db()
        self.assertEqual(report.status, JobStatus.CANCELLED.value)
        self.assertIsNotNone(report.completed_at)

    # ------------------------------------------------------------------
    # Scratchpad
    # ------------------------------------------------------------------
    def test_append_finding_persists_and_bumps_progress(self):
        report = self._make_report()
        ResearchReportService.append_finding(
            report,
            {"section": "Risks", "claim": "X", "citations": [1, 2]},
        )
        ResearchReportService.append_finding(
            report,
            {"section": "Risks", "claim": "Y", "citations": [3]},
        )
        report.refresh_from_db()
        self.assertEqual(len(report.findings), 2)
        self.assertEqual(report.step_count, 2)
        self.assertIsNotNone(report.last_progress_at)

    def test_append_tool_call_does_not_bump_progress(self):
        report = self._make_report()
        ResearchReportService.append_tool_call(
            report, {"tool": "similarity_search", "args": {"q": "foo"}}
        )
        report.refresh_from_db()
        self.assertEqual(len(report.tool_call_log), 1)
        self.assertIsNone(report.last_progress_at)

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------
    def test_request_cancel_by_creator_flips_flag(self):
        report = self._make_report()
        ResearchReportService.request_cancel(self.user, report)
        report.refresh_from_db()
        self.assertTrue(report.cancel_requested)

    def test_request_cancel_by_outsider_denied(self):
        report = self._make_report()
        with self.assertRaises(PermissionError):
            ResearchReportService.request_cancel(self.outsider, report)

    def test_request_cancel_on_terminal_is_noop(self):
        report = self._make_report(status=JobStatus.COMPLETED.value)
        ResearchReportService.request_cancel(self.user, report)
        report.refresh_from_db()
        self.assertFalse(report.cancel_requested)

    def test_cancel_if_requested_raises_when_flag_set(self):
        report = self._make_report(cancel_requested=True)
        with self.assertRaises(ResearchCancelled):
            ResearchReportService.cancel_if_requested(report)

    def test_cancel_if_requested_passes_when_flag_clear(self):
        report = self._make_report()
        # Returns False / does not raise
        self.assertFalse(ResearchReportService.cancel_if_requested(report))

    # ------------------------------------------------------------------
    # finalize() — citation post-processing
    # ------------------------------------------------------------------
    def _make_annotation(self, **overrides) -> Annotation:
        label, _ = AnnotationLabel.objects.get_or_create(
            text="default",
            defaults={"creator": self.user, "label_type": "TOKEN_LABEL"},
        )
        doc = overrides.pop(
            "document",
            Document.objects.create(
                title="Lease.pdf", creator=self.user, file_type="application/pdf"
            ),
        )
        kwargs = dict(
            creator=self.user,
            document=doc,
            annotation_label=label,
            page=overrides.pop("page", 1),
            raw_text=overrides.pop("raw_text", "matched text"),
            json={},
        )
        kwargs.update(overrides)
        return Annotation.objects.create(**kwargs)

    def _make_label(self, text: str) -> AnnotationLabel:
        return AnnotationLabel.objects.create(
            text=text, creator=self.user, label_type="TOKEN_LABEL"
        )

    # ------------------------------------------------------------------
    # header_like_citation_ids() — section-header anchor detection (#2180)
    # ------------------------------------------------------------------
    def test_header_like_citation_ids_flags_structural_section_headers(self):
        # Both the Docling snake_case and LlamaParse Title-Case header labels
        # collapse onto the same normalized key and are flagged.
        snake = self._make_annotation(
            raw_text="ITEM 1A. RISK FACTORS",
            structural=True,
            annotation_label=self._make_label("section_header"),
        )
        title_case = self._make_annotation(
            raw_text="ITEM 3. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT "
            "MARKET RISK.",
            structural=True,
            annotation_label=self._make_label("Section Header"),
        )
        # A substantive body paragraph is ALSO structural but must NOT be
        # flagged (its label is a body label).
        body = self._make_annotation(
            raw_text="Fixed-price contracts expose the company to cost overruns "
            "when input prices rise faster than expected.",
            structural=True,
            annotation_label=self._make_label("text"),
        )
        # A non-structural (user-authored) annotation is never flagged, even
        # with a header-shaped label.
        user_ann = self._make_annotation(
            raw_text="Risk Factors",
            structural=False,
            annotation_label=self._make_label("Section Header"),
        )

        flagged = ResearchReportService.header_like_citation_ids(
            [snake.pk, title_case.pk, body.pk, user_ann.pk]
        )
        self.assertEqual({aid for aid, _ in flagged}, {snake.pk, title_case.pk})
        # The preview carries the anchor's raw_text so a caller can name it.
        previews = dict(flagged)
        self.assertIn("ITEM 1A", previews[snake.pk])

    def test_header_like_citation_ids_handles_null_label_and_unknowns(self):
        null_label = self._make_annotation(
            raw_text="ITEM 2. PROPERTIES", structural=True, annotation_label=None
        )
        # Null label -> normalizes to "" -> never a header. Empty input and
        # non-existent ids yield nothing rather than raising.
        self.assertEqual(
            ResearchReportService.header_like_citation_ids([null_label.pk]), []
        )
        self.assertEqual(ResearchReportService.header_like_citation_ids([]), [])
        self.assertEqual(ResearchReportService.header_like_citation_ids([987654]), [])

    def test_header_only_rejection_rejects_all_header_finding(self):
        h1 = self._make_annotation(
            raw_text="ITEM 1A. RISK FACTORS",
            structural=True,
            annotation_label=self._make_label("section_header"),
        )
        h2 = self._make_annotation(
            raw_text="ITEM 3. MARKET RISK",
            structural=True,
            annotation_label=self._make_label("Section Header"),
        )
        msg = ResearchReportService.header_only_rejection([h1.pk, h2.pk])
        # ``assert`` (not assertIsNotNone) so mypy narrows ``str | None`` -> ``str``
        # for the assertIn checks below.
        assert msg is not None
        # The message names the offending anchors so the agent can re-anchor.
        self.assertIn(str(h1.pk), msg)
        self.assertIn("ITEM 1A", msg)
        self.assertIn("similarity_search", msg)

    def test_header_only_rejection_passes_mixed_and_headerless(self):
        header = self._make_annotation(
            raw_text="ITEM 1A. RISK FACTORS",
            structural=True,
            annotation_label=self._make_label("section_header"),
        )
        body = self._make_annotation(
            raw_text="Fixed-price contracts expose the company to cost overruns.",
            structural=True,
            annotation_label=self._make_label("text"),
        )
        # A finding that also cites a substantive passage is allowed through.
        self.assertIsNone(
            ResearchReportService.header_only_rejection([header.pk, body.pk])
        )
        # A finding with no header at all is fine.
        self.assertIsNone(ResearchReportService.header_only_rejection([body.pk]))
        # No citations -> nothing to reject.
        self.assertIsNone(ResearchReportService.header_only_rejection([]))

    def test_finalize_strips_header_anchor_from_mixed_citation(self):
        header = self._make_annotation(
            raw_text="ITEM 1A. RISK FACTORS",
            structural=True,
            annotation_label=self._make_label("section_header"),
        )
        body = self._make_annotation(
            raw_text="Fixed-price contracts expose the company to cost overruns.",
            structural=True,
            annotation_label=self._make_label("text"),
        )
        report = self._make_report()
        report.findings = [
            {
                "section": "Risks",
                "claim": "fixed-price cost-overrun risk",
                "citations": [header.pk, body.pk],
            }
        ]
        report.save(update_fields=["findings"])

        body_md = (
            f'<cite ids="{header.pk},{body.pk}">Fixed-price contracts carry '
            f"cost-overrun risk.</cite>"
        )
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body_md,
            retrieved_annotation_ids=[header.pk, body.pk],
        )
        report.refresh_from_db()
        # Only the substantive body annotation becomes a footnote/source; the
        # section header is dropped even though it was named in the cite tag.
        self.assertEqual({c["annotation_id"] for c in report.citations}, {body.pk})
        self.assertIn(body, report.source_annotations.all())
        self.assertNotIn(header, report.source_annotations.all())
        # The claim still renders with its (body) footnote.
        self.assertIn("[^1]", report.content)

    def test_finalize_with_grounded_citations(self):
        ann1 = self._make_annotation(raw_text="force majeure clause")
        ann2 = self._make_annotation(raw_text="termination clause")
        report = self._make_report()
        report.findings = [
            {
                "section": "Risks",
                "claim": "the lease has a broad force majeure clause",
                "citations": [ann1.pk],
            }
        ]
        report.save(update_fields=["findings"])

        body = f'<cite ids="{ann1.pk},{ann2.pk}">The lease has a broad clause</cite>.'
        ResearchReportService.finalize(
            report,
            executive_summary="Concise summary.",
            markdown_body=body,
            retrieved_annotation_ids=[ann1.pk, ann2.pk],
        )
        report.refresh_from_db()
        self.assertEqual(report.status, JobStatus.COMPLETED.value)
        self.assertIn("Executive Summary", report.content)
        self.assertIn("[^1]", report.content)
        self.assertIn("## Sources", report.content)
        # M2M populated.
        self.assertIn(ann1, report.source_annotations.all())

    def test_finalize_drops_citations_not_in_retrieved_set(self):
        ann = self._make_annotation()
        rogue = self._make_annotation()  # exists but never "retrieved"
        report = self._make_report()
        # Findings cite the rogue id — the agent shouldn't normally do this
        # (arecord_finding validates), but finalize must still defend.
        report.findings = [
            {"section": "S", "claim": "claim", "citations": [rogue.pk]},
        ]
        report.save(update_fields=["findings"])

        body = f'<cite ids="{rogue.pk}">claim</cite>'
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[ann.pk],  # rogue is NOT here
        )
        report.refresh_from_db()
        # No footnote, no Sources block, no rogue annotation linked.
        self.assertNotIn("[^1]", report.content)
        self.assertNotIn("## Sources", report.content)
        self.assertNotIn(rogue, report.source_annotations.all())

    def test_finalize_skips_deleted_annotations(self):
        ann = self._make_annotation()
        report = self._make_report()
        report.findings = [
            {"section": "S", "claim": "c", "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])
        ann_id = ann.pk
        ann.delete()  # citation now dangles

        body = f'<cite ids="{ann_id}">claim</cite>'
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[ann_id],
        )
        report.refresh_from_db()
        self.assertEqual(report.citations, [])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def test_derive_title_handles_empty_and_long_prompts(self):
        self.assertEqual(_derive_title_from_prompt(""), "Untitled Research Report")
        long = "x" * 200
        self.assertLessEqual(len(_derive_title_from_prompt(long)), 80)
        self.assertTrue(
            _derive_title_from_prompt("## Heading\nBody").startswith("Heading")
        )

    def test_render_citations_dedupes_repeated_ids(self):
        # Build minimal annotation rows so _render_citations can hydrate them.
        ann = self._make_annotation()
        body = (
            f'<cite ids="{ann.pk}">first</cite> ' f'<cite ids="{ann.pk}">second</cite>'
        )
        rendered, citations = _render_citations(body, {ann.pk})
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["footnote"], 1)
        # Both occurrences point at footnote 1.
        self.assertEqual(rendered.count("[^1]"), 2)

    # ------------------------------------------------------------------
    # _strip_fabricated_links() — kill agent-invented hyperlinks
    # ------------------------------------------------------------------
    def test_strip_fabricated_links_neutralises_external_targets(self):
        # Every externally-resolvable target the agent might invent is
        # downgraded to its label; in-app relative links and fragments survive.
        cases = [
            ("see [the MSA](https://example.com)", "see the MSA"),
            ("see [the MSA](http://example.com/path?q=1)", "see the MSA"),
            ("ref [x](//example.com/proto-relative)", "ref x"),
            ("bare [domain](example.com/terms)", "bare domain"),
            ("mail [us](mailto:legal@example.com)", "mail us"),
            ("an ![logo](https://example.com/a.png) image", "an logo image"),
            # In-app + fragment links are legitimate and must be preserved.
            (
                "open [the doc](/d/alice/cases/lease)",
                "open [the doc](/d/alice/cases/lease)",
            ),
            ("jump [down](#summary)", "jump [down](#summary)"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(_strip_fabricated_links(source), expected)

    def test_strip_fabricated_links_leaves_footnotes_untouched(self):
        # Footnote markers/definitions look bracket-y but have no (target);
        # they must pass through unharmed so citations keep working.
        body = "A claim[^1] and another[^2].\n\n[^1]: *Doc* (doc 1) annotation 5"
        self.assertEqual(_strip_fabricated_links(body), body)

    def test_strip_fabricated_links_leaves_reference_style_links_unchanged(self):
        # Known, deliberate gap: only inline ``[text](url)`` links are stripped.
        # Reference-style links pass through (the agent's observed fabrication
        # pattern is the inline example.com placeholder, not reference style).
        # This pins current behaviour so the gap reads as intentional.
        body = "See [the MSA][1] for details.\n\n[1]: https://example.com/msa"
        self.assertEqual(_strip_fabricated_links(body), body)

    def test_strip_fabricated_links_does_not_match_dotted_prose(self):
        # The bare-domain branch requires a >=2 char trailing segment, so dotted
        # identifiers that are not real domains are not mistaken for link targets.
        cases = [
            ("version [v1.0](v1.0) shipped", "version [v1.0](v1.0) shipped"),
            ("clause [a](section_a.2) applies", "clause [a](section_a.2) applies"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(_strip_fabricated_links(source), expected)

    def test_strip_fabricated_links_handles_empty_label(self):
        # An empty-label fabricated link ``[](url)`` strips to "" without
        # crashing; surrounding whitespace collapses gracefully in finalize.
        self.assertEqual(
            _strip_fabricated_links("lead [](https://example.com) trail"),
            "lead  trail",
        )
        self.assertEqual(_strip_fabricated_links("[](https://example.com)"), "")

    def test_finalize_strips_fabricated_links_from_content(self):
        # End-to-end: an agent that ignores the prompt and embeds an
        # example.com link in both the summary and the body must not leak
        # that link into the stored, rendered report.
        ann = self._make_annotation(raw_text="indemnity clause")
        report = self._make_report()
        report.findings = [
            {"section": "Risks", "claim": "broad indemnity", "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])

        body = (
            f'The lease has a <cite ids="{ann.pk}">broad indemnity clause</cite>. '
            "Full text at [the source](https://example.com/lease)."
        )
        ResearchReportService.finalize(
            report,
            executive_summary="Summary; details at [here](https://example.com).",
            markdown_body=body,
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        # The fabricated link is gone, but the prose (and the real citation
        # footnote) survive.
        self.assertNotIn("example.com", report.content)
        self.assertNotIn("](http", report.content)
        self.assertIn("the source", report.content)
        self.assertIn("[^1]", report.content)
        self.assertIn("## Sources", report.content)
