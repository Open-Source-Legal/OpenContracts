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

_TEXT = "This entity is governed by the Guam Administrative Adjudication Law in all respects."

# Canonical key the LLM will return
_CANON_KEY = "act:guam-administrative-adjudication-law"


def _make_llm_citation(confidence: float) -> dict:
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
