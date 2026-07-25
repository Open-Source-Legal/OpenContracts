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
    _is_header_anchor,
    _render_citations,
    _strip_fabricated_links,
    _verify_cite_spans,
)
from opencontractserver.tasks.research_tasks import _compose_salvage_body
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
            text=overrides.pop("label_text", "default"),
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
    # finalize() — weak-citation (section-header) lint  [issue #2180]
    # ------------------------------------------------------------------
    def test_finalize_flags_section_header_label_citation(self):
        # A citation whose anchor carries a section-header label (OC_SECTION)
        # anchors the top of a section, not the supporting passage — flag it.
        header = self._make_annotation(
            label_text="OC_SECTION", raw_text="ITEM 1A. RISK FACTORS"
        )
        report = self._make_report()
        report.findings = [
            {"section": "Risks", "claim": "c", "citations": [header.pk]},
        ]
        report.save(update_fields=["findings"])

        body = f'<cite ids="{header.pk}">the filing discloses supply risk</cite>.'
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[header.pk],
        )
        report.refresh_from_db()
        self.assertTrue(report.citations[0]["anchor_is_header"])
        self.assertTrue(
            any("section header" in str(w) for w in (report.warnings or [])),
            report.warnings,
        )

    def test_finalize_flags_llamaparse_heading_label_citation(self):
        # LlamaParse layout heading labels ("Section Header", …) are flagged
        # too, matched case-/separator-insensitively.
        header = self._make_annotation(
            label_text="Section Header", raw_text="Risk Factors"
        )
        report = self._make_report()
        report.findings = [
            {"section": "Risks", "claim": "c", "citations": [header.pk]},
        ]
        report.save(update_fields=["findings"])
        body = f'<cite ids="{header.pk}">the section covers supply risk</cite>.'
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[header.pk],
        )
        report.refresh_from_db()
        self.assertTrue(report.citations[0]["anchor_is_header"])

    def test_finalize_plural_weak_citation_warning(self):
        # Two header-anchored citations exercise the plural warning branch and
        # its "N citations anchor section headers" grammar.
        h1 = self._make_annotation(
            label_text="OC_SECTION", raw_text="ITEM 1A. RISK FACTORS"
        )
        h2 = self._make_annotation(label_text="Section Header", raw_text="Market Risk")
        report = self._make_report()
        report.findings = [
            {"section": "Risks", "claim": "c", "citations": [h1.pk, h2.pk]},
        ]
        report.save(update_fields=["findings"])
        body = (
            f'<cite ids="{h1.pk}">supply risk is disclosed</cite>. '
            f'<cite ids="{h2.pk}">market risk is disclosed</cite>.'
        )
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[h1.pk, h2.pk],
        )
        report.refresh_from_db()
        self.assertTrue(all(c["anchor_is_header"] for c in report.citations))
        self.assertTrue(
            any(
                "2 citations anchor section headers" in str(w)
                for w in (report.warnings or [])
            ),
            report.warnings,
        )

    def test_finalize_does_not_flag_structural_body_paragraph_citation(self):
        # Regression guard (review of #2180): the parsing pipeline marks EVERY
        # layout chunk structural=True — body paragraphs and sentence chunks
        # included (oc_text_parser / llamaparse_parser) — so the lint must key
        # on the annotation LABEL, not the structural flag. A structural body
        # sentence (the normal similarity_search hit) is a real citation and
        # must NOT be flagged.
        body_chunk = self._make_annotation(
            label_text="SENTENCE",
            structural=True,
            raw_text="The Company's primary raw materials include aluminum and copper.",
        )
        report = self._make_report()
        report.findings = [
            {"section": "Risks", "claim": "c", "citations": [body_chunk.pk]},
        ]
        report.save(update_fields=["findings"])
        body = f'<cite ids="{body_chunk.pk}">raw materials include aluminum</cite>.'
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[body_chunk.pk],
        )
        report.refresh_from_db()
        self.assertFalse(report.citations[0]["anchor_is_header"])
        self.assertFalse(
            any("section header" in str(w) for w in (report.warnings or [])),
            report.warnings,
        )

    def test_finalize_does_not_flag_body_clause_opening_with_section_ref(self):
        # A body-labelled clause that merely opens with a section reference
        # ("Section 8.1 requires ...") is a correct citation to operative
        # language — never flagged, since detection keys on the label, not text.
        clause = self._make_annotation(
            label_text="Paragraph",
            raw_text="Section 8.1 requires 30 days' written notice prior to termination.",
        )
        report = self._make_report()
        report.findings = [
            {"section": "Termination", "claim": "c", "citations": [clause.pk]},
        ]
        report.save(update_fields=["findings"])
        body = (
            f'<cite ids="{clause.pk}">30 days notice is required to terminate</cite>.'
        )
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[clause.pk],
        )
        report.refresh_from_db()
        self.assertFalse(report.citations[0]["anchor_is_header"])
        self.assertFalse(
            any("section header" in str(w) for w in (report.warnings or [])),
            report.warnings,
        )

    def test_is_header_anchor_keys_on_label(self):
        # Header-like labels (case-/separator-insensitive) are flagged...
        self.assertTrue(_is_header_anchor(label_text="OC_SECTION"))
        self.assertTrue(_is_header_anchor(label_text="Section Header"))
        self.assertTrue(_is_header_anchor(label_text="section_header"))
        self.assertTrue(_is_header_anchor(label_text="Title"))
        # ...body/content labels and a missing label are not.
        self.assertFalse(_is_header_anchor(label_text="Paragraph"))
        self.assertFalse(_is_header_anchor(label_text="SENTENCE"))
        self.assertFalse(_is_header_anchor(label_text="Table"))
        self.assertFalse(_is_header_anchor(label_text=None))
        self.assertFalse(_is_header_anchor(label_text=""))

    # ------------------------------------------------------------------
    # finalize() — quotation verification  [issue #2189]
    # ------------------------------------------------------------------
    def test_finalize_strips_fabricated_quote_and_warns(self):
        # The cited annotation's real language; the report's "quote" invents a
        # tail ("including those due to increases in raw material costs") that
        # appears nowhere in it — the #2189 failure mode.
        ann = self._make_annotation(
            raw_text=(
                "when we enter into fixed-price contracts with some of our "
                "customers, we take the risk of cost overruns"
            )
        )
        report = self._make_report()
        report.findings = [
            {"section": "Risks", "claim": "c", "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])
        body = (
            f'<cite ids="{ann.pk}">The filing warns: "On fixed-price contracts, '
            "we take the risk of cost overruns, including those due to increases "
            'in raw material costs"</cite>.'
        )
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        # The fabricated verbatim quote loses its quotation marks...
        self.assertNotIn('"On fixed-price contracts', report.content)
        # ...but the prose (now honest paraphrase) and the footnote survive.
        self.assertIn("cost overruns", report.content)
        self.assertIn("[^1]", report.content)
        self.assertTrue(
            any("did not match" in str(w) for w in (report.warnings or [])),
            report.warnings,
        )

    def test_finalize_preserves_grounded_quote(self):
        # A quote that IS a substring of the cited annotation text (modulo
        # whitespace/case) is kept verbatim, quotation marks intact.
        ann = self._make_annotation(
            raw_text=(
                "Prices for these raw materials have historically been "
                "volatile\nand we do not hedge our exposure."
            )
        )
        report = self._make_report()
        report.findings = [{"section": "S", "claim": "c", "citations": [ann.pk]}]
        report.save(update_fields=["findings"])
        body = (
            f'<cite ids="{ann.pk}">The company notes prices "have historically '
            'been volatile and we do not hedge our exposure"</cite>.'
        )
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        self.assertIn(
            '"have historically been volatile and we do not hedge our exposure"',
            report.content,
        )
        self.assertFalse(
            any("did not match" in str(w) for w in (report.warnings or [])),
            report.warnings,
        )

    def test_verify_cite_spans_skips_short_quotes(self):
        # A short quoted term (< RESEARCH_QUOTE_MIN_WORDS words) is a defined
        # term / scare-quote, not a passage claim — left alone even when it is
        # nowhere in the cited annotation.
        ann = self._make_annotation(raw_text="entirely unrelated language")
        body = (
            f'<cite ids="{ann.pk}">the agreement defines "Confidential '
            'Information" broadly</cite>'
        )
        verified, downgraded, _ = _verify_cite_spans(body, {ann.pk})
        self.assertEqual(downgraded, 0)
        self.assertEqual(verified, body)

    def test_verify_cite_spans_leaves_uncited_quotes_untouched(self):
        # A quote outside any <cite> span has no anchor to verify against.
        body = 'Background: the task asked about "a five word or longer thing".'
        verified, downgraded, _ = _verify_cite_spans(body, set())
        self.assertEqual(downgraded, 0)
        self.assertEqual(verified, body)

    def test_verify_cite_spans_matches_any_cited_annotation(self):
        # A span may cite several annotations; the quote need only match ONE.
        a1 = self._make_annotation(raw_text="the lessor may terminate on default")
        a2 = self._make_annotation(
            raw_text="tenant shall pay all real estate taxes and assessments"
        )
        body = (
            f'<cite ids="{a1.pk},{a2.pk}">tenant is liable: "shall pay all real '
            'estate taxes and assessments"</cite>'
        )
        verified, downgraded, _ = _verify_cite_spans(body, {a1.pk, a2.pk})
        self.assertEqual(downgraded, 0)
        self.assertEqual(verified, body)

    def test_verify_cite_spans_handles_curly_and_mismatched_quotes(self):
        # Curly (“...”) and mismatched pairs (straight-open/curly-close) are
        # matched and verified just like straight quotes.
        ann = self._make_annotation(raw_text="the tenant shall not sublet the premises")
        # Fabricated curly quote -> stripped.
        curly = f'<cite ids="{ann.pk}">it says “the landlord may sublet at will freely”</cite>'
        v, d, _ = _verify_cite_spans(curly, {ann.pk})
        self.assertEqual(d, 1)
        self.assertNotIn("“the landlord may sublet", v)
        # Grounded but with a mismatched open/close pair -> preserved.
        mismatched = f'<cite ids="{ann.pk}">note: "the tenant shall not sublet the premises”</cite>'
        v2, d2, _ = _verify_cite_spans(mismatched, {ann.pk})
        self.assertEqual(d2, 0)
        self.assertEqual(v2, mismatched)

    def test_verify_cite_spans_demotes_quote_when_anchor_has_no_text(self):
        # A quote attributed to a real, cited anchor that has NO raw_text cannot
        # be a verbatim citation of it — demote rather than silently pass it
        # through (the "looks cited but isn't" hole this fix targets).
        ann = self._make_annotation(raw_text="")
        body = f'<cite ids="{ann.pk}">the report states "a fully invented five word passage"</cite>'
        verified, downgraded, _ = _verify_cite_spans(body, {ann.pk})
        self.assertEqual(downgraded, 1)
        self.assertNotIn('"a fully invented', verified)
        # Short quoted terms still skip even without any anchor text.
        short = f'<cite ids="{ann.pk}">defines "Force Majeure" here</cite>'
        v2, d2, _ = _verify_cite_spans(short, {ann.pk})
        self.assertEqual(d2, 0)
        self.assertEqual(v2, short)

    # ------------------------------------------------------------------
    # Composer renders each finding once — NOT a doubler  [issue #2183]
    # ------------------------------------------------------------------
    def test_finalize_renders_each_claim_once(self):
        # The finalize composer emits the agent's body verbatim (cite-rendered);
        # it must never stitch a plain + cited variant of a sentence. Guards
        # against a regression that would double each claim.
        ann = self._make_annotation(raw_text="operative language here")
        report = self._make_report()
        sentence = "Aluminum and copper prices drive input-cost exposure"
        report.findings = [
            {"section": "Risks", "claim": sentence, "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])
        body = f'<cite ids="{ann.pk}">{sentence}</cite>.'
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        self.assertEqual(report.content.count(sentence), 1)
        self.assertIn("[^1]", report.content)

    # ------------------------------------------------------------------
    # finalize() — single rendering + pure-marker cites  [issue #2200]
    # ------------------------------------------------------------------
    def test_finalize_drops_summary_that_duplicates_the_body(self):
        # The observed regression: the agent passed the WHOLE report as BOTH
        # executive_summary and markdown_body, so the report rendered twice —
        # once with raw <cite> spans (the summary was never cite-rendered) and
        # once in footnote form. One rendering, one Executive Summary header.
        ann = self._make_annotation(raw_text="the lessee bears all repair costs")
        report = self._make_report()
        report.findings = [
            {"section": "Costs", "claim": "repairs", "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])

        whole_report = (
            "## Repair obligations\n\n"
            f'The lessee bears all repair costs <cite ids="{ann.pk}"/>.\n\n'
            "## Sources\n\n(All claims above are cited inline.)"
        )
        ResearchReportService.finalize(
            report,
            executive_summary=whole_report,
            markdown_body=whole_report,
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        self.assertEqual(report.content.count("Executive Summary"), 0)
        self.assertEqual(report.content.count("The lessee bears all repair costs"), 1)
        # The agent's stub Sources section is gone; the rendered one remains.
        self.assertNotIn("cited inline", report.content)
        self.assertEqual(report.content.count("## Sources"), 1)
        self.assertIn("[^1]", report.content)

    def test_finalize_renders_cite_tags_inside_the_executive_summary(self):
        # A <cite> tag in the summary used to leak raw into the stored content
        # because only the body was cite-rendered. Composition now happens
        # first, so one pass covers both.
        ann = self._make_annotation(raw_text="indemnity survives termination")
        report = self._make_report()
        report.findings = [
            {"section": "S", "claim": "indemnity", "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])
        ResearchReportService.finalize(
            report,
            executive_summary=f'Indemnity survives <cite ids="{ann.pk}"/>.',
            markdown_body="Body prose with no citations.",
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        self.assertNotIn("<cite", report.content)
        self.assertIn("Indemnity survives [^1]", report.content)
        self.assertIn("## Executive Summary", report.content)

    def test_finalize_collapses_cite_span_that_echoes_its_own_sentence(self):
        # #2200's self-quoting spans: the claim is written as prose and then
        # repeated verbatim inside the tag, doubling every bullet. The span
        # collapses to a bare footnote on the existing sentence.
        ann = self._make_annotation(
            raw_text="the tenant shall maintain the premises in good repair"
        )
        report = self._make_report()
        sentence = "The tenant must maintain the premises in good repair"
        report.findings = [
            {"section": "S", "claim": sentence, "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])
        body = f'- {sentence}. <cite ids="{ann.pk}">{sentence}.</cite>'
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=body,
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        self.assertEqual(report.content.count(sentence), 1)
        self.assertIn("[^1]", report.content)

    def test_render_citations_supports_self_closing_marker(self):
        ann = self._make_annotation()
        body = f'A cited sentence.<cite ids="{ann.pk}"/> Trailing prose.'
        rendered, citations = _render_citations(body, {ann.pk})
        self.assertEqual(rendered, "A cited sentence.[^1] Trailing prose.")
        self.assertEqual(len(citations), 1)

    # ------------------------------------------------------------------
    # finalize() — claim-support check  [issue #2201]
    # ------------------------------------------------------------------
    def test_finalize_strips_citation_the_anchor_cannot_support(self):
        # #2201 residual 2: a one-word mention span cited for a full sentence.
        # The citation goes; the prose stays as uncited analysis.
        mention = self._make_annotation(raw_text="aluminum")
        report = self._make_report()
        sentence = (
            "The company's fixed-price contracts expose it to margin "
            "compression from escalating tariffs on imported components"
        )
        report.findings = [
            {"section": "Risks", "claim": sentence, "citations": [mention.pk]},
        ]
        report.save(update_fields=["findings"])
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=f'{sentence} <cite ids="{mention.pk}"/>.',
            retrieved_annotation_ids=[mention.pk],
        )
        report.refresh_from_db()
        self.assertIn(sentence, report.content)
        self.assertNotIn("[^1]", report.content)
        self.assertEqual(report.citations, [])
        self.assertTrue(
            any("not supported" in str(w) for w in (report.warnings or [])),
            report.warnings,
        )

    def test_finalize_keeps_citation_the_anchor_does_support(self):
        # A genuine paraphrase of its anchor clears the coverage floor.
        ann = self._make_annotation(
            raw_text=(
                "Tenant shall reimburse Landlord for all real estate taxes, "
                "assessments and insurance premiums allocable to the premises"
            )
        )
        report = self._make_report()
        sentence = (
            "The tenant must reimburse the landlord for real estate taxes, "
            "assessments and insurance premiums allocable to the premises"
        )
        report.findings = [
            {"section": "Costs", "claim": sentence, "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=f'{sentence} <cite ids="{ann.pk}"/>.',
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        self.assertIn("[^1]", report.content)
        self.assertFalse(
            any("not supported" in str(w) for w in (report.warnings or [])),
            report.warnings,
        )

    def test_claim_support_skips_short_claims(self):
        # Below RESEARCH_CLAIM_SUPPORT_MIN_WORDS a coverage ratio is noise, so
        # short spans pass unchecked even against an unrelated anchor.
        ann = self._make_annotation(raw_text="entirely unrelated language")
        body = f'<cite ids="{ann.pk}">a broad indemnity clause</cite>'
        result = _verify_cite_spans(body, {ann.pk})
        self.assertEqual(result.cites_dropped, 0)
        self.assertEqual(result.markdown, body)

    def test_compose_salvage_body_renders_each_finding_once(self):
        report = self._make_report()
        report.findings = [
            {"section": "Risks", "claim": "unique-claim-alpha", "citations": [1]},
            {"section": "Risks", "claim": "unique-claim-beta", "citations": []},
        ]
        report.save(update_fields=["findings"])
        body = _compose_salvage_body(report, response_text="")
        self.assertEqual(body.count("unique-claim-alpha"), 1)
        self.assertEqual(body.count("unique-claim-beta"), 1)

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
