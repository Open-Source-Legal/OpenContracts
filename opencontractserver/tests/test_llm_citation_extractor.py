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

    def test_verify_and_place_picks_nearest_occurrence(self):
        """When raw_text appears multiple times, pick the occurrence nearest cand.start."""
        citation = "42 U.S.C. § 1983"
        # Build a string where the citation appears near offset 10 and again near offset 200.
        # Pad with filler so the second occurrence lands around 200.
        padding = "x" * 180
        chunk_text = f"See {citation} for relief. {padding} Also {citation} applies."
        first_occ = chunk_text.index(citation)  # ~4
        second_occ = chunk_text.index(citation, first_occ + 1)  # ~200+

        # cand.start is near the SECOND occurrence (does not exactly match)
        cand = self._make_cand(citation, second_occ + 3, second_occ + 3 + len(citation))

        # The exact fast-path will miss because start + 3 shifts the check.
        # Recovery should pick the SECOND occurrence, not the first.
        result = verify_and_place(chunk_text, 0, chunk_text, cand)
        assert result is not None
        # Result should land at the second occurrence, not the first
        assert result["start"] == second_occ
        assert result["end"] == second_occ + len(citation)
        assert result["raw_text"] == citation


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


class TestLLMMaxConcurrencyResolver:
    """The global concurrency cap is the code constant unless a deployment
    overrides it via ENRICHMENT_LLM_MAX_CONCURRENCY. Pure-function — no DB."""

    def test_default_is_the_constant(self, settings):
        settings.ENRICHMENT_LLM_MAX_CONCURRENCY = None
        assert C.llm_max_concurrency() == C.LLM_MAX_CONCURRENCY

    def test_setting_overrides_the_constant(self, settings):
        settings.ENRICHMENT_LLM_MAX_CONCURRENCY = 3
        assert C.llm_max_concurrency() == 3

    def test_extractor_resolves_when_unset_and_explicit_wins(self, settings):
        settings.ENRICHMENT_LLM_MAX_CONCURRENCY = 5
        assert LLMCitationExtractor()._max_concurrency == 5
        # An explicit constructor arg overrides the global cap.
        assert LLMCitationExtractor(max_concurrency=2)._max_concurrency == 2


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

    async def test_aextract_same_span_two_keys_dedups_to_one(self):
        """Same span appearing in two overlapping chunks deduplicates to one Candidate.

        The TestModel returns the same raw_text at the same absolute position
        from both chunk 0 and chunk 1, but with different normalized_citation
        strings. After dedup on (start, end) only one Candidate must survive.
        """
        from pydantic_ai.models.test import TestModel

        import opencontractserver.enrichment.llm_citation_extractor as mod

        citation_text = "42 U.S.C. § 1983"
        # Place citation near the start so it falls in the overlap of chunk 0 and 1.
        # Window=60, overlap=20 → step=40. The citation at offset 5 is in both chunks.
        prefix = "See "
        text = prefix + citation_text + " " + ("A" * 200)

        citation_start = len(prefix)  # 4
        citation_end = citation_start + len(citation_text)

        call_count = 0

        # Alternate normalized_citation between calls to prove key doesn't matter.
        def _make_model(nc: str):
            return TestModel(
                custom_output_args={
                    "citations": [
                        {
                            "raw_text": citation_text,
                            "start": citation_start,
                            "end": citation_end,
                            "jurisdiction": "Federal",
                            "authority_type": "statute",
                            "normalized_citation": nc,
                            "confidence": 0.9,
                        }
                    ]
                }
            )

        models = [_make_model("usc:42-1983"), _make_model("act:civil-rights-42-1983")]
        original_build = mod.abuild_agent_model
        original_one_shot = mod._one_shot_structured

        async def fake_build(spec):
            return None  # model value unused; we patch _one_shot_structured

        async def fake_one_shot(*, chunk_text, model):
            nonlocal call_count
            m = models[min(call_count, len(models) - 1)]
            call_count += 1
            # Only return the citation if it actually appears in this chunk.
            if citation_text in chunk_text:
                from opencontractserver.enrichment.llm_citation_extractor import (
                    ChunkCitationExtraction,
                    CitationCandidate,
                )

                # Adjust offsets to be chunk-relative.
                chunk_start_offset = text.index(chunk_text[:20])
                local_start = citation_start - chunk_start_offset
                local_end = citation_end - chunk_start_offset
                if local_start >= 0 and local_end <= len(chunk_text):
                    return ChunkCitationExtraction(
                        citations=[
                            CitationCandidate(
                                raw_text=citation_text,
                                start=local_start,
                                end=local_end,
                                jurisdiction="Federal",
                                authority_type="statute",
                                normalized_citation=m.custom_output_args["citations"][
                                    0
                                ]["normalized_citation"],
                                confidence=0.9,
                            )
                        ]
                    )
            from opencontractserver.enrichment.llm_citation_extractor import (
                ChunkCitationExtraction,
            )

            return ChunkCitationExtraction(citations=[])

        mod.abuild_agent_model = fake_build
        mod._one_shot_structured = fake_one_shot
        try:
            extractor = LLMCitationExtractor(window=60, overlap=20)
            results = await extractor.aextract(text)
        finally:
            mod.abuild_agent_model = original_build
            mod._one_shot_structured = original_one_shot

        # Exactly one Candidate for the span, regardless of differing keys.
        span_results = [
            r for r in results if r.start == citation_start and r.end == citation_end
        ]
        assert len(span_results) == 1, (
            f"Expected 1 Candidate for the span, got {len(span_results)}: "
            f"{[(r.start, r.end, r.canonical_key) for r in span_results]}"
        )

    async def test_aextract_multi_chunk(self):
        """Text longer than window → chunked; Candidate offsets are absolute."""
        import opencontractserver.enrichment.llm_citation_extractor as mod

        citation_text = "Section 5 of the Securities Act"
        # Place the citation in the second chunk (past the first window).
        window = 60
        overlap = 10
        # First chunk covers [0, 60); second covers [50, 110).
        # Put the citation at offset 55 so it falls into chunk 1 only.
        prefix = "A" * 55
        full_text = prefix + citation_text + " and more text here."

        citation_start = 55

        original_build = mod.abuild_agent_model
        original_one_shot = mod._one_shot_structured

        async def fake_build(spec):
            return None

        async def fake_one_shot(*, chunk_text, model):
            from opencontractserver.enrichment.llm_citation_extractor import (
                ChunkCitationExtraction,
                CitationCandidate,
            )

            if citation_text not in chunk_text:
                return ChunkCitationExtraction(citations=[])
            local_start = chunk_text.index(citation_text)
            local_end = local_start + len(citation_text)
            return ChunkCitationExtraction(
                citations=[
                    CitationCandidate(
                        raw_text=citation_text,
                        start=local_start,
                        end=local_end,
                        jurisdiction="Federal",
                        authority_type="statute",
                        normalized_citation="securities-act:5",
                        confidence=0.85,
                    )
                ]
            )

        mod.abuild_agent_model = fake_build
        mod._one_shot_structured = fake_one_shot
        try:
            extractor = LLMCitationExtractor(window=window, overlap=overlap)
            results = await extractor.aextract(full_text)
        finally:
            mod.abuild_agent_model = original_build
            mod._one_shot_structured = original_one_shot

        assert len(results) == 1
        c = results[0]
        assert c.start == citation_start
        assert c.end == citation_start + len(citation_text)
        assert full_text[c.start : c.end] == citation_text

    async def test_aextract_confidence_boundary(self):
        """Confidence exactly at LLM_CONFIDENCE_FLOOR → not needs_review; just below → needs_review."""
        import opencontractserver.enrichment.llm_citation_extractor as mod

        text = "The Clean Air Act § 112 governs air quality standards."
        citation_text = "Clean Air Act § 112"

        original_build = mod.abuild_agent_model
        original_one_shot = mod._one_shot_structured

        async def fake_build(spec):
            return None

        async def _run_with_confidence(confidence: float):
            from opencontractserver.enrichment.llm_citation_extractor import (
                ChunkCitationExtraction,
                CitationCandidate,
            )

            async def fake_one_shot(*, chunk_text, model):
                if citation_text not in chunk_text:
                    return ChunkCitationExtraction(citations=[])
                local_start = chunk_text.index(citation_text)
                local_end = local_start + len(citation_text)
                return ChunkCitationExtraction(
                    citations=[
                        CitationCandidate(
                            raw_text=citation_text,
                            start=local_start,
                            end=local_end,
                            jurisdiction="Federal",
                            authority_type="statute",
                            normalized_citation="",
                            confidence=confidence,
                        )
                    ]
                )

            mod.abuild_agent_model = fake_build
            mod._one_shot_structured = fake_one_shot
            try:
                extractor = LLMCitationExtractor(window=len(text) + 50)
                return await extractor.aextract(text)
            finally:
                mod.abuild_agent_model = original_build
                mod._one_shot_structured = original_one_shot

        # Exactly at floor (0.7) → needs_review is False (code uses < FLOOR)
        results_at_floor = await _run_with_confidence(C.LLM_CONFIDENCE_FLOOR)
        assert len(results_at_floor) == 1
        assert results_at_floor[0].normalized_data.get("needs_review") is False

        # Just below floor (0.69) → needs_review is True
        results_below = await _run_with_confidence(0.69)
        assert len(results_below) == 1
        assert results_below[0].normalized_data.get("needs_review") is True

    async def test_aextract_unknown_jurisdiction_type(self):
        """Unknown jurisdiction and authority_type produce a Candidate with None for both."""
        import opencontractserver.enrichment.llm_citation_extractor as mod

        text = "As per the Mars Planetary Code § 7, all colonies must comply."
        citation_text = "Mars Planetary Code § 7"

        original_build = mod.abuild_agent_model
        original_one_shot = mod._one_shot_structured

        async def fake_build(spec):
            return None

        async def fake_one_shot(*, chunk_text, model):
            from opencontractserver.enrichment.llm_citation_extractor import (
                ChunkCitationExtraction,
                CitationCandidate,
            )

            if citation_text not in chunk_text:
                return ChunkCitationExtraction(citations=[])
            local_start = chunk_text.index(citation_text)
            local_end = local_start + len(citation_text)
            return ChunkCitationExtraction(
                citations=[
                    CitationCandidate(
                        raw_text=citation_text,
                        start=local_start,
                        end=local_end,
                        jurisdiction="Mars",
                        authority_type="poem",
                        normalized_citation="",
                        confidence=0.8,
                    )
                ]
            )

        mod.abuild_agent_model = fake_build
        mod._one_shot_structured = fake_one_shot
        try:
            extractor = LLMCitationExtractor(window=len(text) + 50)
            results = await extractor.aextract(text)
        finally:
            mod.abuild_agent_model = original_build
            mod._one_shot_structured = original_one_shot

        # Candidate IS produced — unknown fields don't drop the result.
        assert len(results) == 1
        c = results[0]
        assert (
            c.jurisdiction is None
        ), f"Expected None jurisdiction, got {c.jurisdiction!r}"
        assert (
            c.authority_type is None
        ), f"Expected None authority_type, got {c.authority_type!r}"
        assert c.raw_text == citation_text
