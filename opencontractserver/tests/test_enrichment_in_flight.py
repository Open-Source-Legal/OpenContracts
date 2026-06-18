"""In-flight (incremental) enrichment persistence — provisional lifecycle.

Covers the streaming design in ``EnrichmentService.apply``:

* references are committed per document and marked ``is_provisional`` mid-run,
* a successful run finalizes its rows in one atomic flip,
* a failed run leaves its rows provisional (and a later run reclaims them),
* the writer's claim rules (re-stamp provisional, never downgrade finalized),
* the crawl seed acts on finalized rows only, while the display shows in-flight.

See docs/superpowers/specs/2026-06-17-in-flight-authority-detection-design.md.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis
from opencontractserver.annotations.models import AuthorityFrontier, CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import Candidate
from opencontractserver.enrichment.resolver import Resolution
from opencontractserver.enrichment.services import (
    CorpusReferenceService,
    EnrichmentService,
)
from opencontractserver.enrichment.services.authority_frontier_service import (
    AuthorityFrontierService,
)
from opencontractserver.enrichment.writer import EnrichmentWriter
from opencontractserver.types.enums import JobStatus

User = get_user_model()

LAW_TEXT = (
    "We are subject to Section 203 of the Delaware General Corporation Law. "
    "Indemnification is governed by Section 145 of the Delaware General "
    "Corporation Law. Shares were issued pursuant to Section 4(a)(2) of the "
    "Securities Act."
)


class _InFlightBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="inflight", password="p")
        self.corpus = Corpus.objects.create(title="S-1", creator=self.user)
        self.primary = Document.objects.create(title="S-1 primary", creator=self.user)
        self.primary.txt_extract_file.save(
            "primary.txt", ContentFile(LAW_TEXT.encode("utf-8"))
        )
        self.primary_in_corpus, _, _ = self.corpus.add_document(
            document=self.primary, user=self.user
        )

    def _make_analysis(self) -> Analysis:
        analyzer = EnrichmentService.get_or_create_analyzer(self.user.id)
        return Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator_id=self.user.id,
            status=JobStatus.RUNNING.value,
        )

    def _law_refs(self):
        return CorpusReference.objects.filter(
            corpus=self.corpus, reference_type=C.REF_LAW
        )


class ApplyFinalizationTests(_InFlightBase):
    def test_successful_apply_finalizes_all_references(self):
        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        refs = self._law_refs()
        assert refs.exists()
        # Every reference is finalized after a successful run...
        assert refs.filter(is_provisional=True).count() == 0
        # ...and attributed to the producing analysis.
        analysis_id = out["analysis_id"]
        assert refs.exclude(created_by_analysis_id=analysis_id).count() == 0

    def test_references_are_provisional_during_the_run(self):
        """Before finalization (which runs after the doc-graph reconcile), the
        per-document writes have already committed provisional rows — proving
        references are queryable mid-run, not only at the end."""
        seen = {}
        # Observation point: reconcile_document_graph is the first post-loop step,
        # after every per-doc write has committed but before the finalize flip —
        # so provisional rows are guaranteed visible here. This couples the test
        # to that single call site; if a refactor inlines or moves the reconcile,
        # this spy breaks — which is correct, because the once-at-end reconcile is
        # a load-bearing design seam (a per-doc reconcile would prune live edges).
        # The mid-run-commit invariant is independently covered by
        # FailedRunLeavesProvisionalTests, so the spy is not its sole guardian.
        original = EnrichmentWriter.reconcile_document_graph

        def spy(writer_self):
            seen["provisional_mid_run"] = CorpusReference.objects.filter(
                corpus=writer_self.corpus,
                reference_type=C.REF_LAW,
                is_provisional=True,
            ).count()
            return original(writer_self)

        with patch.object(EnrichmentWriter, "reconcile_document_graph", spy):
            EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        # Rows were provisional mid-run...
        assert seen["provisional_mid_run"] > 0
        # ...and finalized by the time apply() returns.
        assert self._law_refs().filter(is_provisional=True).count() == 0


class FailedRunLeavesProvisionalTests(_InFlightBase):
    def _fail_after_writes(self):
        """Force a failure AFTER the per-document writes commit (the doc-graph
        reconcile is the first post-loop step, before finalization)."""

        def boom(_writer_self):
            raise RuntimeError("injected post-write failure")

        with patch.object(EnrichmentWriter, "reconcile_document_graph", boom):
            with self.assertRaises(RuntimeError):
                EnrichmentService().apply(
                    corpus_id=self.corpus.id, creator_id=self.user.id
                )

    def test_failed_run_leaves_references_provisional_and_analysis_failed(self):
        self._fail_after_writes()
        refs = self._law_refs()
        # Per-document writes committed independently of the later failure...
        assert refs.exists()
        # ...and stayed provisional (no finalize flip on the failed path).
        assert refs.filter(is_provisional=False).count() == 0
        # The Analysis is marked FAILED.
        analysis = Analysis.objects.filter(analyzed_corpus=self.corpus).latest("id")
        assert analysis.status == JobStatus.FAILED.value

    def test_later_successful_run_reclaims_and_finalizes_provisional(self):
        self._fail_after_writes()
        assert self._law_refs().filter(is_provisional=True).exists()

        # A subsequent successful run re-detects the same keys, claims the
        # orphaned provisional rows, and finalizes them.
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        refs = self._law_refs()
        assert refs.exists()
        assert refs.filter(is_provisional=True).count() == 0


class WriterClaimRuleTests(_InFlightBase):
    """Unit-level coverage of EnrichmentWriter's provisional/claim semantics."""

    def _resolution(self):
        cand = Candidate(
            reference_type=C.REF_LAW,
            start=0,
            end=12,
            raw_text="Faketest Act",
            canonical_key="faketest:1",
            jurisdiction=None,
            authority_type=None,
            detection_tier=C.DETECTION_TIER_GRAMMAR,
            detection_confidence=0.9,
        )
        return Resolution(
            candidate=cand,
            source_document_id=self.primary_in_corpus.id,
            resolution_status=C.STATUS_EXTERNAL,
            canonical_key="faketest:1",
            normalized_data=dict(cand.normalized_data),
        )

    def test_new_row_provisional_then_claim_then_no_downgrade(self):
        a1 = self._make_analysis()
        a2 = self._make_analysis()
        res = self._resolution()

        # 1) New row written provisional, attributed to a1.
        EnrichmentWriter(self.corpus, self.user.id, analysis=a1).write(
            [res], provisional=True, reconcile_graph=False
        )
        ref = CorpusReference.objects.get(canonical_key="faketest:1")
        assert ref.is_provisional is True
        assert ref.created_by_analysis_id == a1.id

        # 2) Re-touch a still-provisional row → CLAIM: re-stamped to a2.
        EnrichmentWriter(self.corpus, self.user.id, analysis=a2).write(
            [res], provisional=True, reconcile_graph=False
        )
        ref.refresh_from_db()
        assert ref.is_provisional is True
        assert ref.created_by_analysis_id == a2.id

        # 3) Finalize the row, then re-touch → must NOT downgrade or re-stamp.
        CorpusReference.objects.filter(pk=ref.pk).update(is_provisional=False)
        EnrichmentWriter(self.corpus, self.user.id, analysis=a1).write(
            [res], provisional=True, reconcile_graph=False
        )
        ref.refresh_from_db()
        assert ref.is_provisional is False  # never downgraded
        assert ref.created_by_analysis_id == a2.id  # finalized row untouched

    def test_overlapping_runs_last_writer_finalizes_without_corruption(self):
        """Documents the concurrency semantics (writer claim rule + spec §8).

        Under (currently un-prevented) overlapping same-corpus runs, the claim
        rule reassigns a still-provisional row to the latest writer, so the
        FIRST run's finalize misses it and the LAST run's finalize owns it. This
        is deterministic (no threads — TestCase wraps each test in one
        transaction, so a faithful thread test would need TransactionTestCase +
        synchronization and would be flaky; the property is a WHERE-clause-scope
        consequence, fully testable by interleaving two analyses by hand)."""
        a1 = self._make_analysis()
        a2 = self._make_analysis()
        res = self._resolution()

        # Run A writes the row provisional (owns it).
        EnrichmentWriter(self.corpus, self.user.id, analysis=a1).write(
            [res], provisional=True, reconcile_graph=False
        )
        ref = CorpusReference.objects.get(canonical_key="faketest:1")
        assert ref.created_by_analysis_id == a1.id and ref.is_provisional

        # Run B re-touches the still-provisional row mid-flight → claims it.
        EnrichmentWriter(self.corpus, self.user.id, analysis=a2).write(
            [res], provisional=True, reconcile_graph=False
        )

        # Run A finalizes first (the exact filter apply() uses). Its key no
        # longer matches the claimed row, so A finalizes nothing.
        flipped_a = CorpusReference.objects.filter(
            created_by_analysis=a1, is_provisional=True
        ).update(is_provisional=False)
        ref.refresh_from_db()
        assert flipped_a == 0
        assert ref.is_provisional is True  # A did not finalize B's claimed row

        # Run B finalizes last → owns and finalizes the row. Correct end state,
        # no finalized row ever downgraded.
        flipped_b = CorpusReference.objects.filter(
            created_by_analysis=a2, is_provisional=True
        ).update(is_provisional=False)
        ref.refresh_from_db()
        assert flipped_b == 1
        assert ref.is_provisional is False
        assert ref.created_by_analysis_id == a2.id


class ConcurrentLLMApplyTests(TestCase):
    """The LLM apply path runs the concurrent cross-document orchestrator
    (_aresolve_documents) instead of the sync per-document loop. Verify it
    persists llm-tier references and finalizes them on success."""

    OPEN_VOCAB_TEXT = (
        "This filing references the Fictional Securities Practices Act in "
        "section 12, which governs disclosure obligations."
    )

    def setUp(self):
        self.user = User.objects.create_user(username="llm-apply", password="p")
        self.corpus = Corpus.objects.create(title="LLM Corpus", creator=self.user)
        self.doc = Document.objects.create(title="LLM doc", creator=self.user)
        self.doc.txt_extract_file.save(
            "doc.txt", ContentFile(self.OPEN_VOCAB_TEXT.encode("utf-8"))
        )
        self.corpus.add_document(document=self.doc, user=self.user)

    def test_llm_tier_apply_persists_and_finalizes_open_vocab_ref(self):
        from pydantic_ai.models.test import TestModel

        # Canned open-vocabulary citation the registry/grammar tiers can't know.
        # Offsets are nominal — verify_and_place recovers by searching the chunk
        # for raw_text, which IS present in OPEN_VOCAB_TEXT.
        canned = {
            "raw_text": "Fictional Securities Practices Act",
            "start": 0,
            "end": 34,
            "jurisdiction": "Federal",
            "authority_type": "statute",
            "normalized_citation": "fspa:12",
            "confidence": 0.95,
        }

        async def fake_build(spec):
            return TestModel(custom_output_args={"citations": [canned]})

        # Both aextract and the orchestrator build via the extractor module's
        # abuild_agent_model name (the single seam), so patch it there.
        with patch(
            "opencontractserver.enrichment.llm_citation_extractor.abuild_agent_model",
            fake_build,
        ):
            # LLM tier only (registry stays the base): the grammar tier would
            # catch the open-vocab "…Act" span and win reconcile, masking the
            # llm-tier candidate. Dropping it isolates the concurrent LLM path.
            out = EnrichmentService().apply(
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                extra_tiers=[C.DETECTION_TIER_LLM],
            )

        llm_ref = CorpusReference.objects.filter(
            corpus=self.corpus,
            reference_type=C.REF_LAW,
            detection_tier=C.DETECTION_TIER_LLM,
            canonical_key="fspa:12",
        ).first()
        assert llm_ref is not None, "concurrent LLM path did not persist the ref"
        # Finalized on success (the orchestrator's writes are provisional, the
        # post-loop flip finalizes them) and attributed to the producing run.
        assert llm_ref.is_provisional is False
        assert llm_ref.created_by_analysis_id == out["analysis_id"]


class CrawlSeedFinalizedOnlyTests(_InFlightBase):
    def test_wanted_authorities_display_includes_provisional_seed_excludes(self):
        # Finalized baseline (dgcl/securities-act) from a successful run.
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        # Add a provisional-only authority (no finalized rows for it).
        cand = Candidate(
            reference_type=C.REF_LAW,
            start=0,
            end=12,
            raw_text="Faketest Act",
            canonical_key="faketest:1",
            jurisdiction=None,
            authority_type=None,
            detection_tier=C.DETECTION_TIER_GRAMMAR,
            detection_confidence=0.9,
        )
        res = Resolution(
            candidate=cand,
            source_document_id=self.primary_in_corpus.id,
            resolution_status=C.STATUS_EXTERNAL,
            canonical_key="faketest:1",
            normalized_data=dict(cand.normalized_data),
        )
        EnrichmentWriter(
            self.corpus, self.user.id, analysis=self._make_analysis()
        ).write([res], provisional=True, reconcile_graph=False)

        # Display surface (default) shows the in-flight authority.
        display = {
            w["authority"]
            for w in CorpusReferenceService.wanted_authorities(
                self.user, corpus_id=self.corpus.id
            )
        }
        assert "faketest" in display
        assert "dgcl" in display

        # Crawl surface (finalized_only) excludes it but keeps finalized ones.
        finalized = {
            w["authority"]
            for w in CorpusReferenceService.wanted_authorities(
                self.user, corpus_id=self.corpus.id, finalized_only=True
            )
        }
        assert "faketest" not in finalized
        assert "dgcl" in finalized

        # The frontier seed (crawl act-on point) never queues the provisional key.
        AuthorityFrontierService.seed_from_wanted_authorities(
            self.user, corpus_id=self.corpus.id
        )
        assert not AuthorityFrontier.objects.filter(canonical_key="faketest:1").exists()
        assert AuthorityFrontier.objects.filter(canonical_key="dgcl:145").exists()
