"""Tests for the ResearchReportService."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.research.constants import (
    RESEARCH_CITABLE_PASSAGE_MAX_HITS,
    RESEARCH_CITABLE_PASSAGE_PREVIEW_CHARS,
)
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import (
    ConcurrentResearchInProgress,
    ResearchCancelled,
    ResearchReportService,
    _claim_is_supported,
    _content_words,
    _derive_title_from_prompt,
    _is_header_anchor,
    _is_negated,
    _preceding_claim,
    _render_citations,
    _strip_fabricated_links,
    _strip_scaffold_headings,
    _summary_duplicates_body,
    _verify_cite_spans,
)
from opencontractserver.tasks.research_tasks import (
    _citable_passage_rows,
    _compose_salvage_body,
)
from opencontractserver.types.enums import JobStatus, PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


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
        verified, downgraded, *_ = _verify_cite_spans(body, {ann.pk})
        self.assertEqual(downgraded, 0)
        self.assertEqual(verified, body)

    def test_verify_cite_spans_leaves_uncited_quotes_untouched(self):
        # A quote outside any <cite> span has no anchor to verify against.
        body = 'Background: the task asked about "a five word or longer thing".'
        verified, downgraded, *_ = _verify_cite_spans(body, set())
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
        verified, downgraded, *_ = _verify_cite_spans(body, {a1.pk, a2.pk})
        self.assertEqual(downgraded, 0)
        self.assertEqual(verified, body)

    def test_verify_cite_spans_handles_curly_and_mismatched_quotes(self):
        # Curly (“...”) and mismatched pairs (straight-open/curly-close) are
        # matched and verified just like straight quotes.
        ann = self._make_annotation(raw_text="the tenant shall not sublet the premises")
        # Fabricated curly quote -> stripped.
        curly = f'<cite ids="{ann.pk}">it says “the landlord may sublet at will freely”</cite>'
        v, d, *_ = _verify_cite_spans(curly, {ann.pk})
        self.assertEqual(d, 1)
        self.assertNotIn("“the landlord may sublet", v)
        # Grounded but with a mismatched open/close pair -> preserved.
        mismatched = f'<cite ids="{ann.pk}">note: "the tenant shall not sublet the premises”</cite>'
        v2, d2, *_ = _verify_cite_spans(mismatched, {ann.pk})
        self.assertEqual(d2, 0)
        self.assertEqual(v2, mismatched)

    def test_verify_cite_spans_demotes_quote_when_anchor_has_no_text(self):
        # A quote attributed to a real, cited anchor that has NO raw_text cannot
        # be a verbatim citation of it — demote rather than silently pass it
        # through (the "looks cited but isn't" hole this fix targets).
        ann = self._make_annotation(raw_text="")
        body = f'<cite ids="{ann.pk}">the report states "a fully invented five word passage"</cite>'
        verified, downgraded, *_ = _verify_cite_spans(body, {ann.pk})
        self.assertEqual(downgraded, 1)
        self.assertNotIn('"a fully invented', verified)
        # Short quoted terms still skip even without any anchor text.
        short = f'<cite ids="{ann.pk}">defines "Force Majeure" here</cite>'
        v2, d2, *_ = _verify_cite_spans(short, {ann.pk})
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
        # Losing a whole section is the biggest blast radius of any guard here,
        # so the drop is reported rather than silent.
        self.assertTrue(
            any("restated the body" in w for w in report.warnings), report.warnings
        )

    def test_summary_duplicate_check_is_a_ratio_so_terse_summaries_are_at_risk(self):
        # Known limitation, pinned. Coverage is a ratio over the SUMMARY, so a
        # very short summary built mostly around one verbatim body sentence
        # reads as a copy and is dropped. A normal-length summary carrying the
        # same quote is nowhere near the threshold. finalize warns on the drop,
        # so the failure is visible rather than a silently missing section.
        quote = (
            "The tenant is liable for all structural repairs to the roof and "
            "exterior walls of the premises under Section 8 of the lease."
        )
        body = (
            f"## Findings\n\n{quote} The landlord retains responsibility for "
            "the foundation. Insurance obligations are allocated in Section 12."
        )
        terse = f'"{quote}" This is the core allocation.'
        self.assertTrue(_summary_duplicates_body(terse, body))

        roomy = (
            "The lease allocates repair duties asymmetrically. "
            f'"{quote}" The landlord keeps only the foundation, and insurance '
            "is handled separately in Section 12, so the tenant carries most of "
            "the physical risk of the building over the term."
        )
        self.assertFalse(_summary_duplicates_body(roomy, body))

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

    def test_finalize_accepts_a_retrieved_id_cited_without_a_finding(self):
        # find_citable_passages hands the agent a ready-to-paste cite handle and
        # the prompt says that id IS the handle, so the agent will cite straight
        # from a retrieval without a matching record_finding. Gating on findings
        # dropped exactly that citation — silently for a short claim, and for a
        # longer one under a "not supported" warning naming the wrong cause.
        # Retrieval, not record_finding, is the gate.
        ann = self._make_annotation(
            raw_text=(
                "The tenant shall maintain commercial general liability "
                "insurance throughout the term of this lease"
            )
        )
        report = self._make_report()
        report.findings = []  # nothing recorded
        report.save(update_fields=["findings"])
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=(
                "The tenant shall maintain commercial general liability "
                f'insurance throughout the term of this lease <cite ids="{ann.pk}"/>.'
            ),
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        self.assertNotIn("<cite", report.content)
        self.assertIn("[^1]", report.content)
        # Provenance follows the citation, not the finding.
        self.assertEqual(
            list(report.source_annotations.values_list("pk", flat=True)), [ann.pk]
        )

    def test_finalize_still_refuses_an_id_retrieval_never_surfaced(self):
        # The other half of the same rule: widening the door to document-cited
        # ids must not widen it to ids the run never retrieved. That intersection
        # is the closed citation graph, and since every retrieval tool is
        # permission-filtered, it is also what keeps a citation inside what the
        # run's creator may read.
        ann = self._make_annotation(raw_text="entirely unrelated language")
        report = self._make_report()
        report.findings = []
        report.save(update_fields=["findings"])
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=(
                "The tenant shall maintain commercial general liability "
                f'insurance throughout the term of this lease <cite ids="{ann.pk}"/>.'
            ),
            retrieved_annotation_ids=[],  # nothing was retrieved
        )
        report.refresh_from_db()
        self.assertNotIn("<cite", report.content)
        self.assertNotIn("[^1]", report.content)
        self.assertEqual(report.source_annotations.count(), 0)

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

    def test_claim_support_carries_the_sentence_across_split_markers(self):
        # The prompt asks for the combined `<cite ids="1,2"/>` form, but when the
        # agent splits it into consecutive markers the later one has only
        # whitespace before it. That must not let an unsupported anchor through
        # as a "short claim" — the sentence carries forward.
        good = self._make_annotation(
            raw_text=(
                "Tenant shall reimburse Landlord for all real estate taxes, "
                "assessments and insurance premiums allocable to the premises"
            )
        )
        mention = self._make_annotation(raw_text="aluminum")
        sentence = (
            "The tenant must reimburse the landlord for real estate taxes, "
            "assessments and insurance premiums allocable to the premises"
        )
        body = f'{sentence} <cite ids="{good.pk}"/> <cite ids="{mention.pk}"/>.'
        result = _verify_cite_spans(body, {good.pk, mention.pk})
        # The supported anchor keeps its marker; the unrelated one loses it.
        self.assertEqual(result.cites_dropped, 1)
        self.assertIn(f'<cite ids="{good.pk}"/>', result.markdown)
        self.assertNotIn(f'<cite ids="{mention.pk}"/>', result.markdown)
        self.assertIn(sentence, result.markdown)

    def test_finalize_warns_when_nothing_survives_composition(self):
        # A body that is nothing but scaffolding reduces to "" — a COMPLETED
        # report must say so rather than store a silently empty document.
        report = self._make_report()
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body="## Sources\n\n(All claims above are cited inline.)",
            retrieved_annotation_ids=[],
        )
        report.refresh_from_db()
        self.assertEqual(report.status, JobStatus.COMPLETED.value)
        self.assertEqual(report.content, "")
        self.assertTrue(
            any("no report content" in str(w) for w in (report.warnings or [])),
            report.warnings,
        )

    def test_preceding_claim_sentence_boundary_rules(self):
        # Pins the two deliberate constraints on _SENTENCE_BOUNDARY_RE, both of
        # which exist to keep the claim the support check sees intact.
        cases = [
            # The trailing whitespace requirement is what stops a decimal from
            # reading as a sentence end.
            ("The cap is 1.5 million dollars ", "The cap is 1.5 million dollars "),
            # ...and the "No." carve-out stops a legal reference from splitting
            # the claim, which would truncate it under the min-words floor and
            # skip the support check entirely.
            (
                "It governs Exhibit No. 4 for the term ",
                "It governs Exhibit No. 4 for the term ",
            ),
            ("see Schedule no. A-1 herein ", "see Schedule no. A-1 herein "),
            # An ordinary sentence end still ends a sentence, including a word
            # that merely ends in "no".
            ("Sentence one. Sentence two ", "Sentence two "),
            ("We visited the casino. Next we left ", "Next we left "),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                _, segment = _preceding_claim(text)
                self.assertEqual(segment, expected)

    def test_preceding_claim_truncates_at_other_legal_abbreviations(self):
        # Pins a KNOWN, deliberate limitation rather than desired behaviour:
        # only "No." is carved out of the boundary rule, so "Inc." / "U.S.C."
        # still split a sentence and hand the guards a truncated claim.
        #
        # Not extended, because the two errors are not symmetric. "No." is
        # unambiguous — a reference identifier always follows. "Inc." genuinely
        # ends sentences in filing prose, so suppressing that boundary would
        # MERGE two sentences into one claim, padding it with unrelated
        # vocabulary and eroding the coverage margin toward a false strip.
        # Truncation instead shortens the claim and fails open. Prefer that
        # until this uses real sentence segmentation.
        _, truncated = _preceding_claim(
            "Acquired by Karman Holdings Inc. reported strong margins "
        )
        self.assertEqual(truncated, "reported strong margins ")

        # And the boundary a merge would destroy — "Inc." ending a real
        # sentence — is currently split correctly.
        _, split = _preceding_claim(
            "The buyer was Karman Holdings Inc. The transaction closed in June "
        )
        self.assertEqual(split, "The transaction closed in June ")

    def test_claim_support_rejects_a_claim_that_inverts_its_anchor(self):
        # Bag-of-words coverage is blind to negation: "the tenant is NOT liable"
        # and "the tenant is liable" differ by one token and score identically
        # against the same anchor. In legal text that inversion is the
        # highest-stakes misattribution there is, so the polarity guard rejects
        # it. (Merely un-stopwording "not" would not: coverage stays ~0.86.)
        anchor = self._make_annotation(
            raw_text=(
                "The tenant is liable for repairs to the premises under "
                "Section 8 of the lease"
            )
        )
        faithful = (
            "The tenant is liable for repairs to the premises under Section 8 "
            "of the lease"
        )
        inverted = (
            "The tenant is not liable for repairs to the premises under "
            "Section 8 of the lease"
        )
        self.assertEqual(
            _verify_cite_spans(
                f'{faithful} <cite ids="{anchor.pk}"/>.', {anchor.pk}
            ).cites_dropped,
            0,
        )
        result = _verify_cite_spans(
            f'{inverted} <cite ids="{anchor.pk}"/>.', {anchor.pk}
        )
        self.assertEqual(result.cites_dropped, 1)
        self.assertNotIn("<cite", result.markdown)
        # The prose survives as uncited analysis, as with any stripped citation.
        self.assertIn(inverted, result.markdown)

    def test_claim_support_catches_prefix_negation_inversion(self):
        # Contracts negate by prefix as often as by particle. A token-exact
        # match missed the whole "non-…" family, leaving exactly the inversion
        # the polarity guard exists to catch.
        anchor = self._make_annotation(
            raw_text=(
                "The master agreement is cancelable by either party on sixty "
                "days written notice"
            )
        )
        inverted = (
            "The master agreement is non-cancelable by either party on sixty "
            "days written notice"
        )
        result = _verify_cite_spans(
            f'{inverted} <cite ids="{anchor.pk}"/>.', {anchor.pk}
        )
        self.assertEqual(result.cites_dropped, 1)
        self.assertNotIn("<cite", result.markdown)

    def test_is_negated_does_not_fire_on_lookalike_words(self):
        # The prefix is hyphenated and limited to "non-" precisely so ordinary
        # contract vocabulary does not read as a polarity marker.
        self.assertTrue(_is_negated("the lease is non-cancelable"))
        self.assertTrue(_is_negated("the lease shall not be cancelled"))
        self.assertFalse(_is_negated("the tenant is liable for repairs"))
        for benign in (
            "payment is due under section 8",
            "the note matures until 2030",
            "interest accrues monthly",
            "none of the above nonetheless applies",
        ):
            with self.subTest(text=benign):
                self.assertFalse(_is_negated(benign))

    def test_is_negated_ignores_the_citation_number_abbreviation(self):
        # "No." spells the reference abbreviation as well as the negation, and
        # exhibit/item/case numbers are everywhere in this domain. Reading them
        # as negation let a reference number appearing on only one side of a
        # near-verbatim restatement trip the inversion guard and strip a VALID
        # citation.
        # The abbreviating period is the discriminator, so lettered references
        # ("No. A-1") and bracketed ones are covered as well as numeric.
        for reference in (
            "the premises described in Exhibit No. 4",
            "Schedule No. A-1 lists the equipment",
            "Case No. 12-3456 governs",
            "as set out in Item No. 5",
            "see (No. 7) below",
        ):
            with self.subTest(text=reference):
                self.assertFalse(_is_negated(reference))
        # A bare "no" is still a negation — including before a number, which a
        # look-ahead-for-a-digit rule would have swallowed.
        for negation in (
            "there is no liability for consequential damages",
            "no obligation arises under this section",
            "there is no 30-day cure period",
        ):
            with self.subTest(text=negation):
                self.assertTrue(_is_negated(negation))

    def test_claim_support_keeps_a_citation_whose_claim_cites_an_exhibit_number(self):
        anchor = self._make_annotation(
            raw_text=(
                "The tenant shall maintain the premises described in the "
                "attached exhibit in good repair throughout the term of the lease"
            )
        )
        claim = (
            "The tenant shall maintain the premises described in Exhibit No. 4 "
            "in good repair throughout the term of the lease"
        )
        result = _verify_cite_spans(f'{claim} <cite ids="{anchor.pk}"/>.', {anchor.pk})
        self.assertEqual(result.cites_dropped, 0)
        self.assertIn(f'<cite ids="{anchor.pk}"/>', result.markdown)

    def test_claim_support_polarity_guard_spares_honest_paraphrase(self):
        # Legal text often negates lexically ("prohibited") rather than with a
        # marker. Such a paraphrase shares far fewer words with the anchor, so
        # it never reaches the high-coverage gate the polarity guard sits behind
        # — the citation must survive.
        anchor = self._make_annotation(
            raw_text=(
                "Tenant shall not sublet the premises or assign this lease "
                "without the prior written consent of Landlord"
            )
        )
        paraphrase = (
            "Subletting the premises and assignment of the lease are "
            "prohibited absent the prior written consent of Landlord"
        )
        result = _verify_cite_spans(
            f'{paraphrase} <cite ids="{anchor.pk}"/>.', {anchor.pk}
        )
        self.assertEqual(result.cites_dropped, 0)
        self.assertIn(f'<cite ids="{anchor.pk}"/>', result.markdown)

    def test_one_span_can_both_demote_a_quote_and_lose_its_citation(self):
        # The three guards are independent, so a single badly-anchored span can
        # trip quote verification AND claim support, incrementing both counters.
        # Intended, not double counting: two different edits land in the text
        # the reader sees — the quotation marks come off so no fabricated
        # verbatim survives, and the footnote comes off so the sentence is not
        # attributed. Warning about only one would leave the other unexplained.
        anchor = self._make_annotation(
            raw_text=(
                "The lease term commences on the first day of January and runs "
                "for five years"
            )
        )
        span = (
            '<cite ids="%d">"the tenant waives all consequential damages" under '
            "the negotiated indemnity schedule attached hereto</cite>" % anchor.pk
        )
        result = _verify_cite_spans(span, {anchor.pk})
        self.assertEqual(result.quotes_demoted, 1)
        self.assertEqual(result.cites_dropped, 1)
        # Both edits are visible: no quote glyphs, no citation, prose retained.
        self.assertNotIn('"', result.markdown)
        self.assertNotIn("<cite", result.markdown)
        self.assertIn("the tenant waives all consequential damages", result.markdown)

    def test_claim_support_polarity_guard_treats_multiple_anchors_as_a_union(self):
        # Known limitation, pinned so it stays a decision rather than a
        # surprise. Coverage is measured against the union of the cited
        # anchors, and the polarity guard follows suit: it asks whether ANY
        # anchor carries a negation marker. So a span citing two anchors that
        # disagree on polarity satisfies parity whichever way the claim reads,
        # and an inversion against one of them survives — even though the same
        # claim citing that anchor alone is correctly rejected (the control
        # below). Making polarity per-candidate while coverage stays a union
        # would be the inconsistency, not the fix; see _claim_is_supported.
        inverted = (
            "The tenant is not liable for structural repairs to the roof "
            "under Section 8 of this lease"
        )
        affirming = (
            "The tenant is liable for structural repairs to the roof under "
            "Section 8 of this lease"
        )
        negated_but_about_someone_else = (
            "The landlord is not liable for structural repairs to the roof "
            "under Section 8 of this lease"
        )
        self.assertFalse(_claim_is_supported(inverted, [affirming]))
        self.assertTrue(
            _claim_is_supported(inverted, [affirming, negated_but_about_someone_else])
        )

    def test_claim_support_polarity_guard_over_strips_lexical_negation(self):
        # The other side of the same known limitation. The guard reads polarity
        # off a fixed marker lexicon, so an anchor that negates lexically
        # ("excluding") reads as affirmative. A faithful claim restating it with
        # "not" then looks like an inversion at high coverage and loses its
        # citation. The failure is one-directional — an over-strip, never a
        # fabricated attribution — which is the right way round for this guard;
        # the honest fix is entailment, not a longer lexicon.
        # Contrast test_claim_support_polarity_guard_spares_honest_paraphrase,
        # where the paraphrase diverges enough to fall below the coverage gate.
        claim = (
            "The tenant is not responsible for painting the interior walls of "
            "the demised premises"
        )
        anchor = (
            "Tenant obligations, excluding painting the interior walls of the "
            "demised premises"
        )
        self.assertFalse(_claim_is_supported(claim, [anchor]))

    def test_claim_support_rejects_a_checked_claim_with_no_anchor_text(self):
        # A textless anchor (empty raw_text, a since-deleted row, or an id
        # retrieval never produced) cannot support anything, so a checked claim
        # citing only such anchors is unsupported by construction. Pinned
        # directly rather than only via the quote-verification path.
        long_claim = (
            "The company's fixed-price contracts expose it to margin "
            "compression from escalating tariffs on imported components"
        )
        self.assertFalse(_claim_is_supported(long_claim, []))
        self.assertFalse(_claim_is_supported(long_claim, ["", ""]))
        # A short claim still short-circuits ahead of the anchor check.
        self.assertTrue(_claim_is_supported("a broad indemnity clause", []))

    def test_content_words_keep_short_numeric_tokens(self):
        # RESEARCH_SUPPORT_MIN_TOKEN_CHARS used to drop "10"/"5%" from BOTH
        # sides, so a swapped figure produced no signal at all. Digit-bearing
        # tokens are exempt from the floor.
        words = _content_words("Landlord shall give 10 days notice and a 5% fee")
        self.assertIn("10", words)
        self.assertIn("5%", words)

    def test_strip_scaffold_headings_is_nesting_aware(self):
        # A subsection INSIDE the scaffolding section must go with it. Ending
        # the skip at the first heading of any depth leaked an orphaned
        # "### By Document" list into the report — the same class of scaffolding
        # escape #2200 is about.
        nested = (
            "## Findings\n\nBody text.\n\n"
            "## Sources\n\n(All claims above are cited inline.)\n\n"
            "### By Document\n\n- Lease.pdf, annotation 12\n"
        )
        cleaned, sections = _strip_scaffold_headings(nested)
        self.assertEqual(sections, 1)
        self.assertNotIn("By Document", cleaned)
        self.assertNotIn("Lease.pdf", cleaned)
        self.assertIn("Body text.", cleaned)

        # ...but a sibling section AFTER it is outside the scaffolding and
        # survives, as does a section following a deeper scaffolding heading.
        after, _ = _strip_scaffold_headings(
            "## Sources\n\n(stub)\n\n### Nested\n\nnested body\n\n"
            "## Appendix\n\nKept text.\n"
        )
        self.assertIn("Kept text.", after)
        self.assertNotIn("nested body", after)
        deep, _ = _strip_scaffold_headings(
            "## Findings\n\nBody.\n\n### Sources\n\nstub\n\n## Analysis\n\nAnalysis body.\n"
        )
        self.assertIn("Analysis body.", deep)
        self.assertNotIn("stub", deep)

    def test_strip_scaffold_headings_ignores_headings_inside_code_fences(self):
        # A "# Sources" COMMENT in a quoted snippet is not a heading. Reading it
        # as one swallowed the rest of the block AND the prose after it, leaving
        # an unterminated fence behind — silent content loss.
        fenced = (
            "## Findings\n\nThe filing includes this extract:\n\n"
            "```\n# Sources\nrevenue = 1_200_000\n```\n\n"
            "Further analysis follows here.\n"
        )
        cleaned, sections = _strip_scaffold_headings(fenced)
        self.assertEqual(sections, 0)
        self.assertIn("Further analysis follows here.", cleaned)
        self.assertIn("revenue = 1_200_000", cleaned)
        self.assertEqual(cleaned.count("```"), 2)

        # A real heading after the fence closes still strips, and tilde fences
        # are recognised too.
        mixed, count = _strip_scaffold_headings(
            "## Findings\n\n```\n# Sources\n```\n\n"
            "## Sources\n\nstub\n\n## Appendix\n\nKept.\n"
        )
        self.assertEqual(count, 1)
        self.assertNotIn("stub", mixed)
        self.assertIn("Kept.", mixed)
        tilde, tilde_count = _strip_scaffold_headings(
            "## Findings\n\n~~~\n# Sources\n~~~\n\nAfter.\n"
        )
        self.assertEqual(tilde_count, 0)
        self.assertIn("After.", tilde)

    def test_finalize_warns_when_an_agent_sources_section_is_stripped(self):
        # Dropping a whole section is a bigger blast radius than dropping a
        # heading line, so it must not be silent — same treatment as the
        # quote/claim-support guards.
        ann = self._make_annotation(raw_text="the lessee bears all repair costs")
        report = self._make_report()
        report.findings = [
            {"section": "S", "claim": "repairs", "citations": [ann.pk]},
        ]
        report.save(update_fields=["findings"])
        ResearchReportService.finalize(
            report,
            executive_summary="",
            markdown_body=(
                "## Repairs\n\n"
                f'The lessee bears all repair costs <cite ids="{ann.pk}"/>.\n\n'
                "## Sources\n\n(All claims above are cited inline.)"
            ),
            retrieved_annotation_ids=[ann.pk],
        )
        report.refresh_from_db()
        self.assertNotIn("cited inline", report.content)
        self.assertIn("The lessee bears all repair costs", report.content)
        self.assertTrue(
            any(
                "Sources/References section" in str(w) for w in (report.warnings or [])
            ),
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

    def test_echo_collapse_reports_itself_only_when_it_loses_text(self):
        # Echo collapse discards the whole inner span, so a collapse below full
        # coverage takes the uncovered remainder with it. Every other strip in
        # this pipeline is counted, and this one now is too — but gated on the
        # loss, so the observed shape (an exact restatement) stays silent
        # instead of putting a warning on every report that has one.
        sentence = (
            "The tenant is liable for all structural repairs to the roof and "
            "exterior walls of the premises under Section 8 of the lease"
        )
        ann = self._make_annotation(raw_text=sentence)

        exact = f'{sentence}. <cite ids="{ann.pk}">{sentence}</cite>'
        result = _verify_cite_spans(exact, {ann.pk})
        self.assertEqual(result.echoes_trimmed, 0)
        self.assertIn(f'<cite ids="{ann.pk}"/>', result.markdown)

        # The ratio is over the INNER text, so a tail this short is what it
        # takes to stay above the threshold and still lose something.
        lossy = f'{sentence}. <cite ids="{ann.pk}">{sentence} as amended</cite>'
        result = _verify_cite_spans(lossy, {ann.pk})
        self.assertEqual(result.echoes_trimmed, 1)
        self.assertNotIn("as amended", result.markdown)

        # A tail any longer drops the span under the threshold, so it is left
        # intact rather than collapsed — nothing to lose, nothing to report.
        kept = (
            f'{sentence}. <cite ids="{ann.pk}">{sentence}, which the parties '
            f"renegotiated in 2019</cite>"
        )
        result = _verify_cite_spans(kept, {ann.pk})
        self.assertEqual(result.echoes_trimmed, 0)
        self.assertIn("renegotiated in 2019", result.markdown)

    def test_echo_check_skips_spans_too_long_to_reach_the_threshold(self):
        # The inner text is the one input the verifier does not bound, and
        # SequenceMatcher costs time linear in it. The skip is arithmetic, not
        # a heuristic: coverage divides the longest matching block by
        # len(inner) and that block cannot exceed len(preceding), so a long
        # enough span cannot clear the threshold however it is written. The
        # span must therefore survive intact — same outcome, not computed.
        sentence = "The tenant is liable for structural repairs under Section 8"
        ann = self._make_annotation(raw_text=sentence)
        # Starts as a perfect echo, so only the length can rule it out.
        huge = sentence + (" and further provisions of the lease agreement" * 400)
        body = f'{sentence}. <cite ids="{ann.pk}">{huge}</cite>'
        result = _verify_cite_spans(body, {ann.pk})
        self.assertEqual(result.echoes_trimmed, 0)
        self.assertIn("further provisions of the lease agreement", result.markdown)

    def test_empty_wrapping_span_is_treated_as_a_marker(self):
        # A wrapping span with nothing in it asserts nothing, so it IS a marker.
        # Left as "", it skipped the echo check, produced an empty claim, and
        # fell through to the carried-over last_claim — so the same sentence
        # and anchor that the marker form correctly rejects sailed through the
        # claim-support guard. All three spellings must agree.
        anchor = self._make_annotation(
            raw_text=(
                "The tenant shall pay all real property taxes assessed against "
                "the premises"
            )
        )
        unsupported = (
            "The landlord shall remediate every environmental condition "
            "discovered on the site at its sole cost and expense"
        )
        supported = (
            "The tenant shall pay all real property taxes assessed against the "
            "premises"
        )
        marker = f'<cite ids="{anchor.pk}"/>'
        for span in (marker, f'<cite ids="{anchor.pk}"></cite>'):
            with self.subTest(span=span):
                self.assertEqual(
                    _verify_cite_spans(
                        f"{unsupported} {span}.", {anchor.pk}
                    ).cites_dropped,
                    1,
                )
                kept = _verify_cite_spans(f"{supported} {span}.", {anchor.pk})
                self.assertEqual(kept.cites_dropped, 0)
                # ...and the surviving citation renders in the marker form.
                self.assertIn(marker, kept.markdown)

    def test_claim_support_scopes_a_marker_to_its_own_clause(self):
        # In a compound sentence each marker's claim runs back to the previous
        # span, not to the sentence start, so an anchor answers for its OWN
        # clause. The consequence is that a short clause passes unchecked (the
        # min-words floor, same as any short claim anywhere) while a clause long
        # enough to check is genuinely checked — the guard is scoped, not
        # skipped.
        taxes = self._make_annotation(
            raw_text=(
                "The tenant shall pay all real property taxes assessed against "
                "the premises"
            )
        )
        insurance = self._make_annotation(
            raw_text=(
                "The tenant shall maintain commercial general liability "
                "insurance at all times"
            )
        )
        ids = {taxes.pk, insurance.pk}

        short = (
            f'The tenant shall pay taxes <cite ids="{taxes.pk}"/> and maintain '
            f'insurance <cite ids="{insurance.pk}"/>.'
        )
        self.assertEqual(_verify_cite_spans(short, ids).cites_dropped, 0)

        # Same shape, but the second clause is long enough to check and is NOT
        # what its anchor says — the citation goes, the prose stays.
        mismatched = (
            "The tenant shall pay all real property taxes assessed against the "
            f'premises during the term <cite ids="{taxes.pk}"/> and shall '
            "additionally indemnify the landlord for every environmental "
            f'remediation cost arising on the site <cite ids="{insurance.pk}"/>.'
        )
        result = _verify_cite_spans(mismatched, ids)
        self.assertEqual(result.cites_dropped, 1)
        self.assertIn(f'<cite ids="{taxes.pk}"/>', result.markdown)
        self.assertNotIn(f'<cite ids="{insurance.pk}"/>', result.markdown)
        self.assertIn("environmental remediation cost", result.markdown)

    def test_scaffold_stripping_covers_common_sources_heading_variants(self):
        # The premise of this fix is that the agent keeps writing scaffolding
        # the prompt forbids, so a heading just outside the set reproduces #2200
        # under a different name — and silently, since the warning only fires on
        # a strip. The set enumerates the names a report generator reaches for.
        for title in (
            "Sources",
            "Works Cited",
            "Reference List",
            "Sources Cited",
            "Citation",
            "Endnotes",
            "Bibliography",
        ):
            with self.subTest(heading=title):
                cleaned, sections = _strip_scaffold_headings(
                    f"Real prose.\n\n## {title}\n\n- [1] a fabricated citation\n"
                )
                self.assertEqual(sections, 1)
                self.assertNotIn("fabricated citation", cleaned)
                self.assertIn("Real prose.", cleaned)

    def test_scaffold_stripping_keeps_substantive_headings_that_merely_mention(self):
        # Why the match is exact rather than token-overlap: stripping a SECTION
        # deletes everything under it, and these are headings a real legal
        # research report carries. A token rule would delete all three.
        for title in (
            "Sources of Supply Risk",
            "References to Prior Agreements",
            "Citations in the Record",
        ):
            with self.subTest(heading=title):
                cleaned, sections = _strip_scaffold_headings(
                    f"## {title}\n\nSubstantive analysis the report needs.\n"
                )
                self.assertEqual(sections, 0)
                self.assertIn("Substantive analysis the report needs.", cleaned)
                self.assertIn(title, cleaned)

    def test_scaffold_stripping_ignores_fences_inside_the_skipped_section(self):
        # A section being skipped is discarded content, so its fences must not
        # move the surviving document's state. Tracking them meant one
        # unbalanced ``` inside the scaffolding — malformed LLM markdown, which
        # is precisely what this function exists to survive — suspended heading
        # detection permanently: the section never ended and the entire rest of
        # the report vanished without a warning.
        body = "\n".join(
            [
                "Real prose before.",
                "## Sources",
                "```",
                "- [1] a fabricated citation",
                "## Appendix",
                "Substantive appendix content.",
                "## Conclusion",
                "The conclusion.",
            ]
        )
        cleaned, sections = _strip_scaffold_headings(body)
        self.assertEqual(sections, 1)
        self.assertNotIn("fabricated citation", cleaned)
        # Everything after the scaffolding section survives.
        self.assertIn("## Appendix", cleaned)
        self.assertIn("Substantive appendix content.", cleaned)
        self.assertIn("## Conclusion", cleaned)
        self.assertIn("The conclusion.", cleaned)

        # A balanced fence inside the skipped section goes with it, and the
        # document after it is likewise untouched.
        cleaned, sections = _strip_scaffold_headings(
            "\n".join(
                [
                    "Prose.",
                    "## Sources",
                    "```",
                    "- [1] x",
                    "```",
                    "## Appendix",
                    "Kept.",
                ]
            )
        )
        self.assertEqual(sections, 1)
        self.assertNotIn("```", cleaned)
        self.assertIn("Kept.", cleaned)

    def test_scaffold_stripping_needs_a_closing_fence_at_least_as_long(self):
        # CommonMark's other fence rule: a closing fence must run at least as
        # long as the opening one. Closing on any 3+ run ended a ```` block at
        # the literal ``` line inside it, so the ## Sources in that literal
        # content read as real scaffolding, started a section skip, and
        # swallowed every remaining line of the document.
        body = "\n".join(
            [
                "Intro.",
                "````",
                "```",
                "## Sources",
                "````",
                "## Sources",
                "- a fabricated citation list",
                "## Findings",
                "Real content.",
            ]
        )
        cleaned, sections = _strip_scaffold_headings(body)
        self.assertEqual(sections, 1)
        # The heading inside the literal block survives as content...
        self.assertEqual(cleaned.count("## Sources"), 1)
        # ...the real scaffolding section is stripped...
        self.assertNotIn("fabricated citation list", cleaned)
        # ...and everything after it is still here.
        self.assertIn("## Findings", cleaned)
        self.assertIn("Real content.", cleaned)

    def test_scaffold_stripping_closes_a_fence_only_on_its_own_character(self):
        # CommonMark closes a fence on its own character, so a ``~~~`` line
        # inside a backtick block is content. Toggling on any fence line left
        # heading detection suspended for the rest of the document after such a
        # block, which fails QUIET — scaffolding silently unstripped.
        body = "\n".join(
            [
                "Intro paragraph.",
                "```",
                "# Sources",
                "~~~",
                "```",
                "## Sources",
                "- a fabricated citation list",
                "## Findings",
                "Real content.",
            ]
        )
        cleaned, sections = _strip_scaffold_headings(body)
        self.assertEqual(sections, 1)
        # The heading inside the fence is content and survives...
        self.assertIn("# Sources", cleaned)
        # ...while the real scaffolding section after the fence closes is gone.
        self.assertNotIn("fabricated citation list", cleaned)
        self.assertIn("Real content.", cleaned)

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


class CitablePassageRowsTestCase(TestCase):
    """``_citable_passage_rows`` — the row shaping behind the deep-research
    ``find_citable_passages`` tool (issue #2201).

    The permission/ordering semantics live in
    ``AnnotationService.search_corpus_annotation_text`` and are covered in
    ``test_corpus_annotations_query``; this pins the LLM-facing contract the
    agent actually reads — a real citeable id, a paste-ready ``cite`` handle,
    the ``similarity_search``-shaped keys, and the hit/preview caps.
    """

    user: User
    corpus: Corpus
    doc: Document
    annotation: Annotation

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="rows-owner", password="x")
        cls.corpus = Corpus.objects.create(title="Rows", creator=cls.user)
        cls.doc = Document.objects.create(
            title="Lease.pdf", creator=cls.user, file_type="application/pdf"
        )
        DocumentPath.objects.create(
            document=cls.doc,
            corpus=cls.corpus,
            path="/lease.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.user,
        )
        label = AnnotationLabel.objects.create(
            text="SENTENCE", label_type="TOKEN_LABEL", creator=cls.user
        )
        cls.annotation = Annotation.objects.create(
            annotation_label=label,
            document=cls.doc,
            corpus=cls.corpus,
            creator=cls.user,
            page=3,
            raw_text="The tenant shall maintain the premises in good repair.",
            json={},
        )
        set_permissions_for_obj_to_user(cls.user, cls.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(cls.user, cls.doc, [PermissionTypes.CRUD])

    def _rows(self, phrase, **kwargs):
        return _citable_passage_rows(
            corpus_id=self.corpus.pk,
            user=self.user,
            phrase=phrase,
            document_id=kwargs.pop("document_id", None),
            limit=kwargs.pop("limit", RESEARCH_CITABLE_PASSAGE_MAX_HITS),
        )

    def test_row_carries_a_paste_ready_cite_handle_and_search_shaped_keys(self):
        rows = self._rows("maintain the premises")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # The handle is exactly what the prompt tells the agent to paste, and
        # what _CITE_SPAN_RE / _render_citations consume.
        self.assertEqual(row["cite"], f'<cite ids="{self.annotation.pk}"/>')
        self.assertEqual(row["annotation_id"], self.annotation.pk)
        self.assertGreater(row["annotation_id"], 0)
        # similarity_search-shaped so the agent handles both tools identically.
        self.assertEqual(row["document_id"], self.doc.pk)
        self.assertEqual(row["document_title"], "Lease.pdf")
        self.assertEqual(row["page"], 3)
        self.assertEqual(row["label"], "SENTENCE")
        self.assertIn("maintain the premises", row["content"])

    def test_content_is_capped_at_the_preview_ceiling(self):
        long_text = "maintain the premises " + ("x" * 5000)
        Annotation.objects.create(
            annotation_label=self.annotation.annotation_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            raw_text=long_text,
            json={},
        )
        rows = self._rows("maintain the premises")
        self.assertTrue(
            all(
                len(r["content"]) <= RESEARCH_CITABLE_PASSAGE_PREVIEW_CHARS
                for r in rows
            ),
            [len(r["content"]) for r in rows],
        )

    def test_limit_is_clamped_to_the_hit_ceiling(self):
        for i in range(RESEARCH_CITABLE_PASSAGE_MAX_HITS + 3):
            Annotation.objects.create(
                annotation_label=self.annotation.annotation_label,
                document=self.doc,
                corpus=self.corpus,
                creator=self.user,
                raw_text=f"maintain the premises clause {i}",
                json={},
            )
        # A model asking for more than the ceiling cannot dump the corpus back
        # into the context window.
        rows = self._rows("maintain the premises", limit=999)
        self.assertEqual(len(rows), RESEARCH_CITABLE_PASSAGE_MAX_HITS)
        # The floor is this tool's rule, not the service's: a model that omits
        # limit or sends 0 still gets its tightest anchor, so the only empty
        # result it can see is a genuine miss.
        for asked in (0, None, -1):
            with self.subTest(limit=asked):
                self.assertEqual(
                    len(self._rows("maintain the premises", limit=asked)), 1
                )

    def test_no_match_returns_no_rows(self):
        self.assertEqual(self._rows("a phrase that appears nowhere"), [])
