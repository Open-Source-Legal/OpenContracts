"""Tests for Tier-2b LLM citation extractor (Phase 2)."""

from __future__ import annotations

import pytest
from django.test import TransactionTestCase

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.llm_citation_extractor import (
    CitationCandidate,
    LLMCitationExtractor,
    _derive_canonical_key,
    _normalize_authority_type,
    _normalize_jurisdiction,
    verify_and_place,
)

# ---------------------------------------------------------------------------
# verify_and_place
# ---------------------------------------------------------------------------


class TestVerifyAndPlace:
    """Pure-function tests — no async, no DB."""

    def _make_cand(self, raw_text, start, end, **kwargs):
        return CitationCandidate(
            raw_text=raw_text,
            start=start,
            end=end,
            jurisdiction="Federal",
            authority_type="statute",
            normalized_citation="",
            confidence=0.9,
            **kwargs,
        )

    def test_exact_offset_match(self):
        full = "Hello Section 141 of the DGCL applies here."
        chunk_start = 0
        chunk_text = full
        # "Hello " is 6 chars; citation is 23 chars; end = 6 + 23 = 29
        cand = self._make_cand("Section 141 of the DGCL", 6, 29)
        result = verify_and_place(full, chunk_start, chunk_text, cand)
        assert result is not None
        assert result["start"] == 6
        assert result["end"] == 29
        assert result["raw_text"] == "Section 141 of the DGCL"

    def test_exact_offset_match_with_nonzero_chunk_start(self):
        full = "Prefix text. Section 141 of the DGCL applies here."
        # chunk_start=12 so chunk_text starts with " Section ..."
        chunk_start = 12
        chunk_text = full[chunk_start:]
        # Within the chunk the citation is at offset 1 (after the leading space)
        cand = self._make_cand("Section 141 of the DGCL", 1, 24)
        result = verify_and_place(full, chunk_start, chunk_text, cand)
        assert result is not None
        assert result["start"] == 13  # 12 + 1
        assert result["end"] == 36  # 12 + 24
        assert result["raw_text"] == "Section 141 of the DGCL"

    def test_rejects_hallucination(self):
        full = "This text does not contain the citation at all."
        chunk_text = full
        cand = self._make_cand("Section 999 of the XYZ Act", 0, 26)
        result = verify_and_place(full, 0, chunk_text, cand)
        assert result is None

    def test_recovers_drifted_offsets(self):
        """raw_text is in chunk but at a different position than cand says."""
        full = "Preamble. Section 141 of the DGCL is relevant."
        chunk_start = 0
        chunk_text = full
        # cand says it's at offset 0 but it's really at 10
        cand = self._make_cand("Section 141 of the DGCL", 0, 23)
        result = verify_and_place(full, chunk_start, chunk_text, cand)
        # Should find it via fallback search
        assert result is not None
        assert result["raw_text"] == "Section 141 of the DGCL"
        assert result["start"] == 10
        assert result["end"] == 10 + len("Section 141 of the DGCL")

    def test_rejects_empty_raw_text(self):
        full = "Some text."
        cand = self._make_cand("", 0, 0)
        result = verify_and_place(full, 0, full, cand)
        assert result is None

    def test_bounds_out_of_range(self):
        """Offset beyond len(full_text) — must not raise, must fallback or reject."""
        full = "Short."
        # start beyond length
        cand = self._make_cand("Section 1", 100, 109)
        result = verify_and_place(full, 0, full, cand)
        # "Section 1" is not in "Short." so hallucination → None
        assert result is None


# ---------------------------------------------------------------------------
# _normalize_jurisdiction
# ---------------------------------------------------------------------------


class TestNormalizeJurisdiction:
    def test_federal_variants(self):
        assert _normalize_jurisdiction("federal") == "us-federal"
        assert _normalize_jurisdiction("Federal") == "us-federal"
        assert _normalize_jurisdiction("US") == "us-federal"
        assert _normalize_jurisdiction("United States") == "us-federal"

    def test_state_codes(self):
        assert _normalize_jurisdiction("Delaware") == "us-de"
        assert _normalize_jurisdiction("delaware") == "us-de"
        assert _normalize_jurisdiction("California") == "us-ca"
        assert _normalize_jurisdiction("New York") == "us-ny"
        assert _normalize_jurisdiction("Texas") == "us-tx"
        assert _normalize_jurisdiction("Florida") == "us-fl"
        assert _normalize_jurisdiction("Massachusetts") == "us-ma"
        assert _normalize_jurisdiction("Washington") == "us-wa"
        assert _normalize_jurisdiction("Illinois") == "us-il"

    def test_unknown_returns_none(self):
        assert _normalize_jurisdiction("Mars") is None
        assert _normalize_jurisdiction("") is None
        assert _normalize_jurisdiction("   ") is None


# ---------------------------------------------------------------------------
# _normalize_authority_type
# ---------------------------------------------------------------------------


class TestNormalizeAuthorityType:
    def test_known_types(self):
        assert _normalize_authority_type("statute") == C.AUTHORITY_TYPE_STATUTE
        assert _normalize_authority_type("Statute") == C.AUTHORITY_TYPE_STATUTE
        assert _normalize_authority_type("regulation") == C.AUTHORITY_TYPE_REGULATION
        assert _normalize_authority_type("case_law") == C.AUTHORITY_TYPE_CASE
        assert _normalize_authority_type("case law") == C.AUTHORITY_TYPE_CASE
        assert _normalize_authority_type("case") == C.AUTHORITY_TYPE_CASE
        assert (
            _normalize_authority_type("constitution") == C.AUTHORITY_TYPE_CONSTITUTION
        )
        assert _normalize_authority_type("ordinance") == C.AUTHORITY_TYPE_MUNICIPAL
        assert _normalize_authority_type("municipal") == C.AUTHORITY_TYPE_MUNICIPAL
        assert (
            _normalize_authority_type("administrative") == C.AUTHORITY_TYPE_ADMIN_RULE
        )
        assert _normalize_authority_type("admin") == C.AUTHORITY_TYPE_ADMIN_RULE
        assert _normalize_authority_type("rule") == C.AUTHORITY_TYPE_ADMIN_RULE
        assert _normalize_authority_type("guidance") == C.AUTHORITY_TYPE_GUIDANCE
        assert _normalize_authority_type("treaty") == C.AUTHORITY_TYPE_TREATY

    def test_unknown_returns_none(self):
        assert _normalize_authority_type("poem") is None
        assert _normalize_authority_type("") is None


# ---------------------------------------------------------------------------
# _derive_canonical_key
# ---------------------------------------------------------------------------


class TestDeriveCanonicalKey:
    def test_already_keyed(self):
        assert (
            _derive_canonical_key("dgcl:145", "Section 145 of the DGCL") == "dgcl:145"
        )

    def test_named_act_synthesis(self):
        key = _derive_canonical_key("Delaware General Corporation Law § 145", "§ 145")
        assert key is not None
        assert key.startswith("act:")

    def test_raw_text_fallback(self):
        key = _derive_canonical_key("", "Section 145 of the DGCL")
        assert key is not None
        assert key.startswith("act:")

    def test_slug_capped_at_80(self):
        long_text = "A" * 200
        key = _derive_canonical_key("", long_text)
        assert key is not None
        # "act:" + slug; slug must be ≤ 80 chars
        slug = key[len("act:") :]
        assert len(slug) <= 80

    def test_empty_inputs_returns_none(self):
        result = _derive_canonical_key("", "")
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = _derive_canonical_key("   ", "   ")
        assert result is None


# ---------------------------------------------------------------------------
# aextract — async integration tests with TestModel
# ---------------------------------------------------------------------------


@pytest.mark.serial
class TestLLMCitationExtractorAsync(TransactionTestCase):
    """Async integration tests for LLMCitationExtractor using pydantic-ai TestModel."""

    async def test_aextract_empty_text(self):
        """Empty text → empty list, no model call."""
        extractor = LLMCitationExtractor()
        import opencontractserver.enrichment.llm_citation_extractor as mod

        call_count = 0
        original = mod.abuild_agent_model

        async def should_not_be_called(spec):
            nonlocal call_count
            call_count += 1
            return await original(spec)

        mod.abuild_agent_model = should_not_be_called
        try:
            result = await extractor.aextract("")
            assert result == []
            assert call_count == 0
        finally:
            mod.abuild_agent_model = original

    async def test_aextract_whitespace_only(self):
        """Whitespace-only text → empty list, no model call."""
        extractor = LLMCitationExtractor()
        result = await extractor.aextract("   \n\t  ")
        assert result == []

    async def test_aextract_valid_citation(self):
        """One valid citation → one Candidate with correct abs offsets, tier=llm."""
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod

        text = "The board acted under Section 141(b) of the Delaware General Corporation Law."
        # "The board acted under " is 22 chars; citation is 54 chars; end = 22 + 54 = 76
        citation_text = "Section 141(b) of the Delaware General Corporation Law"
        citation_start = text.index(citation_text)
        citation_end = citation_start + len(citation_text)

        canned_citation = {
            "raw_text": citation_text,
            "start": citation_start,
            "end": citation_end,
            "jurisdiction": "Delaware",
            "authority_type": "statute",
            "normalized_citation": "dgcl:141(b)",
            "confidence": 0.95,
        }

        test_model = TestModel(custom_output_args={"citations": [canned_citation]})

        async def fake_build(spec):
            return test_model

        original = mod.abuild_agent_model
        mod.abuild_agent_model = fake_build
        try:
            extractor = LLMCitationExtractor(window=len(text) + 100)
            results = await extractor.aextract(text)
        finally:
            mod.abuild_agent_model = original

        assert len(results) == 1
        c = results[0]
        assert c.detection_tier == C.DETECTION_TIER_LLM
        assert c.reference_type == C.REF_LAW
        assert c.raw_text == citation_text
        assert c.start == citation_start
        assert c.end == citation_end
        assert c.jurisdiction == "us-de"
        assert c.authority_type == C.AUTHORITY_TYPE_STATUTE
        assert c.detection_confidence == 0.95
        assert c.normalized_data.get("needs_review") is False

    async def test_aextract_low_confidence_needs_review(self):
        """Low confidence (< LLM_CONFIDENCE_FLOOR) → Candidate present but needs_review=True."""
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod

        text = "See Section 5 of the Securities Act."
        citation_text = "Section 5 of the Securities Act"
        citation_start = text.index(citation_text)
        citation_end = citation_start + len(citation_text)

        canned_citation = {
            "raw_text": citation_text,
            "start": citation_start,
            "end": citation_end,
            "jurisdiction": "Federal",
            "authority_type": "statute",
            "normalized_citation": "securities-act:5",
            "confidence": 0.5,  # below floor
        }

        test_model = TestModel(custom_output_args={"citations": [canned_citation]})

        async def fake_build(spec):
            return test_model

        original = mod.abuild_agent_model
        mod.abuild_agent_model = fake_build
        try:
            extractor = LLMCitationExtractor(window=len(text) + 100)
            results = await extractor.aextract(text)
        finally:
            mod.abuild_agent_model = original

        assert len(results) == 1
        c = results[0]
        assert c.normalized_data.get("needs_review") is True
        assert c.detection_confidence == 0.5

    async def test_aextract_hallucination_dropped(self):
        """Citation raw_text absent from text → dropped."""
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod

        text = "This text has nothing matching the hallucinated citation."

        canned_citation = {
            "raw_text": "NONEXISTENT AUTHORITY § 99",
            "start": 0,
            "end": 26,
            "jurisdiction": "Federal",
            "authority_type": "statute",
            "normalized_citation": "",
            "confidence": 0.9,
        }

        test_model = TestModel(custom_output_args={"citations": [canned_citation]})

        async def fake_build(spec):
            return test_model

        original = mod.abuild_agent_model
        mod.abuild_agent_model = fake_build
        try:
            extractor = LLMCitationExtractor(window=len(text) + 100)
            results = await extractor.aextract(text)
        finally:
            mod.abuild_agent_model = original

        assert results == []
