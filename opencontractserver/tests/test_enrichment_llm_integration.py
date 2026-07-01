"""Integration tests for Tier-2b LLM detection wired into EnrichmentService."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import EnrichmentService

User = get_user_model()

_TEXT = (
    "This entity is governed by Section 5 of the Guam Administrative "
    "Adjudication Law in all respects."
)

# Canonical key the LLM will return. A SECTIONED key (not a bare act:* body of
# law) so the confidence-routing tests below isolate the confidence dimension —
# a locator-less act:* concept would now ALSO be flagged needs_review by
# _is_concept_key, which would conflate the two routing reasons. The concept
# heuristic itself is covered by test_discover_llm_concept_flagged_to_review.
_CANON_KEY = "guam-aal:5"


def _make_llm_citation(confidence: float) -> dict:
    citation_text = "Section 5 of the Guam Administrative Adjudication Law"
    return {
        "raw_text": citation_text,
        "start": _TEXT.index(citation_text),
        "end": _TEXT.index(citation_text) + len(citation_text),
        "jurisdiction": "Federal",
        "authority_type": "statute",
        "normalized_citation": "guam-aal:5",
        "confidence": confidence,
    }


def _make_llm_concept_citation(confidence: float) -> dict:
    """A body-of-law reference with NO section locator -> derives a locator-less
    act:* concept key (act:guam-administrative-adjudication-law)."""
    citation_text = "the Guam Administrative Adjudication Law"
    return {
        "raw_text": citation_text,
        "start": _TEXT.index(citation_text),
        "end": _TEXT.index(citation_text) + len(citation_text),
        "jurisdiction": "Federal",
        "authority_type": "statute",
        "normalized_citation": "",
        "confidence": confidence,
    }


@pytest.mark.serial
class TestEnrichmentLLMIntegration(TransactionTestCase):
    """Sync integration tests — discover()/apply() bridge async via async_to_sync."""

    def setUp(self):
        self.user = User.objects.create_user(username="llmtest", password="p")
        self.other_user = User.objects.create_user(username="llmother", password="p")
        self.corpus = Corpus.objects.create(title="LLMTestCorpus", creator=self.user)
        self.doc = Document.objects.create(title="LLMDoc", creator=self.user)
        self.doc.txt_extract_file.save("llmdoc.txt", ContentFile(_TEXT.encode("utf-8")))
        self.corpus.add_document(document=self.doc, user=self.user)

    def test_discover_llm_high_confidence(self):
        """High-confidence LLM citation (0.9) appears in by_key, review_candidates == []."""
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod

        canned = _make_llm_citation(0.9)
        test_model = TestModel(custom_output_args={"citations": [canned]})
        original = mod.abuild_agent_model

        async def fake_build(spec):
            return test_model

        mod.abuild_agent_model = fake_build
        try:
            out = EnrichmentService().discover(
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                use_llm=True,
            )
        finally:
            mod.abuild_agent_model = original

        assert out["review_candidates"] == []
        # The key should appear in by_key with llm detection_tier
        found = any(
            entry.get("detection_tier") == C.DETECTION_TIER_LLM
            for entry in out["by_key"].values()
        )
        assert (
            found
        ), f"Expected LLM-tier entry in by_key. Got: {list(out['by_key'].keys())}"

    def test_discover_llm_concept_flagged_to_review(self):
        """A high-confidence but locator-less act:* concept (a body of law with no
        section) is flagged needs_review by the normalization heuristic —
        surfaced for triage, NOT promoted into by_key — even though its
        confidence clears the floor."""
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod

        canned = _make_llm_concept_citation(0.95)  # well above the 0.7 floor
        test_model = TestModel(custom_output_args={"citations": [canned]})
        original = mod.abuild_agent_model

        async def fake_build(spec):
            return test_model

        mod.abuild_agent_model = fake_build
        try:
            out = EnrichmentService().discover(
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                use_llm=True,
            )
        finally:
            mod.abuild_agent_model = original

        # The concept must NOT appear in by_key (the resolved/promoted surface)...
        llm_keys = [
            k
            for k, e in out["by_key"].items()
            if e.get("detection_tier") == C.DETECTION_TIER_LLM
        ]
        assert llm_keys == [], f"concept leaked into by_key: {llm_keys}"
        # ...and MUST be surfaced in the review bucket for triage.
        assert any(
            r["detection_tier"] == C.DETECTION_TIER_LLM
            for r in out["review_candidates"]
        )

    def test_discover_llm_low_confidence_review_bucket(self):
        """Low-confidence LLM citation (0.4 < 0.7 floor) goes to review_candidates, NOT by_key."""
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod

        canned = _make_llm_citation(0.4)
        test_model = TestModel(custom_output_args={"citations": [canned]})
        original = mod.abuild_agent_model

        async def fake_build(spec):
            return test_model

        mod.abuild_agent_model = fake_build
        try:
            out = EnrichmentService().discover(
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                use_llm=True,
            )
        finally:
            mod.abuild_agent_model = original

        # Should NOT appear in by_key (review bucket is excluded from rollup)
        llm_keys = [
            k
            for k, e in out["by_key"].items()
            if e.get("detection_tier") == C.DETECTION_TIER_LLM
        ]
        assert llm_keys == [], f"Low-confidence LLM key leaked into by_key: {llm_keys}"
        # MUST appear in review_candidates
        assert len(out["review_candidates"]) > 0
        review_tiers = {r["detection_tier"] for r in out["review_candidates"]}
        assert C.DETECTION_TIER_LLM in review_tiers

    def test_discover_no_llm(self):
        """use_llm=False: abuild_agent_model is never called, review_candidates == []."""
        import opencontractserver.enrichment.llm_citation_extractor as mod

        call_count = 0
        original = mod.abuild_agent_model

        async def should_not_be_called(spec):
            nonlocal call_count
            call_count += 1
            return await original(spec)

        mod.abuild_agent_model = should_not_be_called
        try:
            out = EnrichmentService().discover(
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                use_llm=False,
            )
        finally:
            mod.abuild_agent_model = original

        assert call_count == 0, "LLM was called despite use_llm=False"
        assert out["review_candidates"] == []

    def test_reconcile_grammar_beats_llm_on_overlap(self):
        """Grammar-detected CFR citation takes precedence; overlapping LLM candidate is suppressed.

        When the grammar tier and LLM tier both produce a candidate for the same
        span, reconcile() keeps only the grammar candidate. The discover() result
        must have exactly one entry for that canonical key with detection_tier="grammar",
        and no separate LLM-tier entry for that span.
        """
        from django.core.files.base import ContentFile

        import opencontractserver.enrichment.llm_citation_extractor as mod

        # Text contains a CFR citation that the grammar will detect.
        cfr_text = "40 C.F.R. § 261.4"
        doc_text = f"Pursuant to {cfr_text}, hazardous waste exclusions apply."

        # Create a separate document for this test to avoid cross-test contamination.
        doc2 = Document.objects.create(title="CFRDoc", creator=self.user)
        doc2.txt_extract_file.save("cfrdoc.txt", ContentFile(doc_text.encode("utf-8")))
        corpus2 = Corpus.objects.create(title="CFRCorpus", creator=self.user)
        corpus2.add_document(document=doc2, user=self.user)

        cfr_start = doc_text.index(cfr_text)
        cfr_end = cfr_start + len(cfr_text)

        # LLM returns the same span as the grammar citation.
        canned_llm = {
            "raw_text": cfr_text,
            "start": cfr_start,
            "end": cfr_end,
            "jurisdiction": "Federal",
            "authority_type": "regulation",
            "normalized_citation": "act:some-other-key",
            "confidence": 0.9,
        }

        original_build = mod.abuild_agent_model

        async def fake_build(spec):
            from pydantic_ai.models.test import TestModel

            return TestModel(custom_output_args={"citations": [canned_llm]})

        mod.abuild_agent_model = fake_build
        try:
            out = EnrichmentService().discover(
                corpus_id=corpus2.id,
                creator_id=self.user.id,
                use_llm=True,
            )
        finally:
            mod.abuild_agent_model = original_build

        # Grammar key for "40 C.F.R. § 261.4" is "cfr-40:261.4"
        grammar_key = "cfr-40:261.4"
        assert grammar_key in out["by_key"], (
            f"Grammar key {grammar_key!r} missing from by_key. "
            f"Keys: {list(out['by_key'].keys())}"
        )
        entry = out["by_key"][grammar_key]
        assert (
            entry["detection_tier"] == C.DETECTION_TIER_GRAMMAR
        ), f"Expected grammar tier for {grammar_key!r}, got {entry['detection_tier']!r}"

        # The LLM key for the same span must NOT appear as a separate entry.
        llm_tier_entries = [
            k
            for k, e in out["by_key"].items()
            if e.get("detection_tier") == C.DETECTION_TIER_LLM and k != grammar_key
        ]
        # There should be no LLM entry that conflicts with the grammar-detected span.
        # The LLM candidate's canonical key would be "act:some-other-key".
        llm_overlap_keys = [k for k in llm_tier_entries if "some-other-key" in k]
        assert (
            llm_overlap_keys == []
        ), f"LLM candidate for grammar-detected span leaked into by_key: {llm_overlap_keys}"

    def _shared_corpus_with_hidden_private_doc(self):
        """Create a SHARED (non-public) corpus other_user can READ, holding a
        private document other_user CANNOT read; return ``(corpus, document)``.

        The corpus is *shared* (corpus-level READ granted) rather than public:
        adding a document to a public corpus auto-propagates public status onto
        the corpus-isolated copy (``Corpus.add_document``: ``is_public =
        corpus.is_public or document.is_public``), which would make the document
        legitimately visible and defeat the scenario. A shared, non-public
        corpus keeps the copy ``is_public=False`` so document-level visibility —
        the document side of ``MIN(corpus, document)`` — is what excludes it.
        """
        from opencontractserver.corpuses.services.corpus_documents import (
            CorpusDocumentService,
        )
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        shared_corpus = Corpus.objects.create(
            title="SharedCorpusWithPrivateDoc", creator=self.user, is_public=False
        )
        # other_user can READ the corpus (the corpus side of MIN) ...
        set_permissions_for_obj_to_user(
            self.other_user, shared_corpus, [PermissionTypes.READ]
        )

        private_doc = Document.objects.create(
            title="PrivateLLMDoc", creator=self.user, is_public=False
        )
        private_doc.txt_extract_file.save(
            "private-llm-doc.txt", ContentFile(_TEXT.encode("utf-8"))
        )
        # ... but NOT the document. Because the corpus is private, the
        # corpus-isolated copy stays is_public=False, so other_user lacks
        # document-level READ on it.
        shared_corpus.add_document(document=private_doc, user=self.user)

        # Sanity: under corpus-as-gate the document IS reachable to other_user
        # (corpus READ alone unlocks it via the wide loader), so a
        # documents_scanned == 0 result proves the MIN(corpus, document) filter
        # excluded it — not that the corpus is empty. The visible-to-user
        # variant then hides it because other_user lacks document-level READ.
        assert CorpusDocumentService.get_corpus_documents(
            self.other_user, shared_corpus, include_caml=False
        ).exists()
        assert not CorpusDocumentService.get_corpus_documents_visible_to_user(
            self.other_user, shared_corpus, include_caml=False
        ).exists()
        return shared_corpus, private_doc

    def test_discover_uses_document_visibility_for_shared_corpus(self):
        """A user who can READ a corpus but not a private document inside it must
        not have that document scanned or leaked through review_candidates.
        """
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod

        shared_corpus, _private_doc = self._shared_corpus_with_hidden_private_doc()

        canned = _make_llm_citation(0.4)
        test_model = TestModel(custom_output_args={"citations": [canned]})
        original = mod.abuild_agent_model
        call_count = 0

        async def fake_build(spec):
            nonlocal call_count
            call_count += 1
            return test_model

        mod.abuild_agent_model = fake_build
        try:
            out = EnrichmentService().discover(
                corpus_id=shared_corpus.id,
                creator_id=self.other_user.id,
                use_llm=True,
            )
        finally:
            mod.abuild_agent_model = original

        assert out["documents_scanned"] == 0
        assert out["documents_visible_to_caller"] == 0
        # Corpus-as-gate still sees the private doc, so the exclusion is surfaced
        # rather than silent.
        assert out["documents_total_in_corpus"] == 1
        assert out["documents_excluded_by_visibility"] == 1
        assert out["total_candidates"] == 0
        assert out["review_candidates"] == []
        assert call_count == 0, "LLM was called for a document hidden from the user"

        # Positive control: the corpus OWNER still sees the document. Without
        # this, an over-restrictive visibility filter (one that returned nothing
        # for everyone) would pass all the negative assertions above.
        owner_out = EnrichmentService().discover(
            corpus_id=shared_corpus.id, creator_id=self.user.id
        )
        assert owner_out["documents_scanned"] >= 1
        assert owner_out["documents_excluded_by_visibility"] == 0

    def test_scan_uses_document_visibility_for_shared_corpus(self):
        """scan() returns verbatim ``raw_text`` excerpts in samples /
        unresolved_samples, so a user with corpus READ but not document READ must
        scan nothing — the same exposure discover() guards against."""
        shared_corpus, _private_doc = self._shared_corpus_with_hidden_private_doc()

        out = EnrichmentService().scan(
            corpus_id=shared_corpus.id, creator_id=self.other_user.id
        )

        assert out["documents_scanned"] == 0
        # Corpus-as-gate still sees the private doc, so the exclusion is
        # surfaced (with a baseline to compute the exclusion fraction from)
        # rather than silent — mirrors discover()'s contract.
        assert out["documents_total_in_corpus"] == 1
        assert out["documents_excluded_by_visibility"] == 1
        assert out["total_candidates"] == 0
        assert out["samples"] == []

        # Positive control: the corpus OWNER still scans the document.
        owner_out = EnrichmentService().scan(
            corpus_id=shared_corpus.id, creator_id=self.user.id
        )
        assert owner_out["documents_scanned"] >= 1
        assert owner_out["documents_excluded_by_visibility"] == 0

    def test_apply_uses_document_visibility_for_shared_corpus(self):
        """apply() persists Annotation / CorpusReference rows derived from
        document text, so a user with corpus READ but not document READ must
        cause no writes (the durable form of the discover()/scan() exposure).

        Also pins the audit WARNING that makes the exclusion auditable rather
        than invisible: without ``assertLogs`` here, deleting the
        ``logger.warning(...)`` call in ``_document_visibility_audit`` would
        leave every other assertion in this module passing.
        """
        from opencontractserver.annotations.models import Annotation

        shared_corpus, private_doc = self._shared_corpus_with_hidden_private_doc()

        with self.assertLogs(
            "opencontractserver.enrichment.services.enrichment_service",
            level="WARNING",
        ) as logs:
            out = EnrichmentService().apply(
                corpus_id=shared_corpus.id, creator_id=self.other_user.id
            )
        assert any(
            "document(s) excluded" in msg and "apply" in msg for msg in logs.output
        ), logs.output

        assert out["documents_scanned"] == 0
        assert out["documents_total_in_corpus"] == 1
        assert out["documents_excluded_by_visibility"] == 1
        assert out["annotations_created"] == 0
        assert out["references_created"] == 0
        # No annotations were persisted onto the document hidden from the caller.
        assert not Annotation.objects.filter(document=private_doc).exists()

        # Positive control: the corpus OWNER still enriches the document
        # (documents_scanned counts the visible set, so this holds regardless of
        # how many references the text yields). No exclusion -> no WARNING.
        owner_out = EnrichmentService().apply(
            corpus_id=shared_corpus.id, creator_id=self.user.id
        )
        assert owner_out["documents_scanned"] >= 1
        assert owner_out["documents_total_in_corpus"] == owner_out["documents_scanned"]
        assert owner_out["documents_excluded_by_visibility"] == 0

    def test_document_visibility_audit_clamps_negative_exclusion(self):
        """``_document_visibility_audit`` issues two unsynchronized queries
        (the MIN-filtered list, then a separate corpus-as-gate COUNT). If a
        document is removed from the corpus in between, the COUNT can come
        back lower than the already-fetched list, making the raw difference
        negative. ``excluded`` must clamp to 0 instead of surfacing a
        nonsensical negative exclusion count to callers.
        """
        from unittest.mock import MagicMock, patch

        service = EnrichmentService()
        user, corpus, documents = service._load(self.corpus.id, self.user.id)
        assert len(documents) == 1

        # Simulate the COUNT racing behind len(documents): the corpus-as-gate
        # total comes back smaller than the document list already fetched.
        racing_queryset = MagicMock()
        racing_queryset.count.return_value = 0
        with patch(
            "opencontractserver.enrichment.services.enrichment_service."
            "CorpusDocumentService.get_corpus_documents",
            return_value=racing_queryset,
        ):
            total_in_corpus, excluded = service._document_visibility_audit(
                user, corpus, documents, surface="test"
            )

        assert total_in_corpus == 0
        assert excluded == 0

    def test_apply_skips_review_bucket(self):
        """apply() never writes a CorpusReference for a low-confidence (review-
        bucket) LLM citation even with the LLM tier enabled."""
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod
        from opencontractserver.annotations.models import CorpusReference

        canned = _make_llm_citation(0.4)
        test_model = TestModel(custom_output_args={"citations": [canned]})
        original = mod.abuild_agent_model

        async def fake_build(spec):
            return test_model

        mod.abuild_agent_model = fake_build
        try:
            EnrichmentService().apply(
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                extra_tiers=[C.DETECTION_TIER_GRAMMAR, C.DETECTION_TIER_LLM],
            )
        finally:
            mod.abuild_agent_model = original

        # The low-confidence LLM key must not be persisted
        llm_refs = CorpusReference.objects.filter(
            corpus=self.corpus,
            reference_type=C.REF_LAW,
        )
        llm_tier_refs = [
            r for r in llm_refs if r.detection_tier == C.DETECTION_TIER_LLM
        ]
        assert llm_tier_refs == [], (
            f"Expected no LLM-tier CorpusReference for low-confidence citation; "
            f"got {len(llm_tier_refs)}: {[r.canonical_key for r in llm_tier_refs]}"
        )
