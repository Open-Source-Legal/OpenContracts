"""Unit tests for the deterministic ReferenceExtractor (no DB)."""

from unittest.mock import patch

from django.test import SimpleTestCase

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import ReferenceExtractor


class ReferenceExtractorTests(SimpleTestCase):
    def setUp(self) -> None:
        self.extractor = ReferenceExtractor()

    def test_law_dgcl_section(self):
        text = (
            "...indemnification under Section 145 of the Delaware General "
            "Corporation Law, our amended and restated certificate..."
        )
        cands = self.extractor.extract(text)
        law = [c for c in cands if c.reference_type == C.REF_LAW]
        assert any(c.canonical_key == "dgcl:145" for c in law), [
            c.canonical_key for c in law
        ]
        hit = next(c for c in law if c.canonical_key == "dgcl:145")
        assert text[hit.start : hit.end].lower().startswith("section 145")
        assert hit.normalized_data["authority"] == "dgcl"
        assert hit.normalized_data["section"] == "145"

    def test_law_securities_act_subsection(self):
        text = "exempt pursuant to Section 4(a)(2) of the Securities Act and Rule 506."
        cands = self.extractor.extract(text)
        assert any(c.canonical_key == "securities-act:4(a)(2)" for c in cands), [
            c.canonical_key for c in cands
        ]

    def test_law_section_203_dgcl(self):
        text = "We are subject to Section 203 of the Delaware General Corporation Law."
        cands = self.extractor.extract(text)
        assert any(c.canonical_key == "dgcl:203" for c in cands)

    def test_prefix_form_law_citation(self):
        """Form D style: authority name BEFORE the section number."""
        text = (
            "Securities Act Section 4(a)(5) and Investment Company Act "
            "Section 3(c)(1) apply to this offering."
        )
        cands = self.extractor.extract(text)
        keys = {c.canonical_key for c in cands if c.reference_type == C.REF_LAW}
        assert "securities-act:4(a)(5)" in keys, keys
        assert "ica:3(c)(1)" in keys, keys

    def test_prefix_and_suffix_forms_do_not_double_count(self):
        text = "Section 145 of the Delaware General Corporation Law applies."
        cands = self.extractor.extract(text)
        law = [c for c in cands if c.reference_type == C.REF_LAW]
        assert len(law) == 1

    def test_sec_rule_citation(self):
        """Bare SEC rule citations: Rule 506(b), Rule 504(b)(1), Rule 10b-5."""
        text = (
            "The offering relies on Rule 506(b) of Regulation D; resales may "
            "use Rule 144A, and liability arises under Rule 10b-5."
        )
        cands = self.extractor.extract(text)
        keys = {c.canonical_key for c in cands if c.reference_type == C.REF_LAW}
        assert "sec-rule:506(b)" in keys, keys
        assert "sec-rule:144a" in keys, keys
        assert "sec-rule:10b-5" in keys, keys

    def test_relative_law_citation_with_authority_context(self):
        """Statute-internal idiom: '§ 251 of this title' keyed via the
        document's own authority (passed by the caller from custom_meta)."""
        text = (
            "Any corporation organized under § 251 of this title may merge, "
            "and Section 141(b) of this title governs the board."
        )
        cands = self.extractor.extract(text, default_authority="dgcl")
        keys = {c.canonical_key for c in cands if c.reference_type == C.REF_LAW}
        assert "dgcl:251" in keys, keys
        assert "dgcl:141(b)" in keys, keys
        hit = next(c for c in cands if c.canonical_key == "dgcl:251")
        assert hit.normalized_data["relative"] is True
        assert hit.normalized_data["authority"] == "dgcl"

    def test_relative_law_citation_skipped_without_authority(self):
        """No authority context -> relative citations cannot be keyed; skip."""
        text = "Any corporation organized under § 251 of this title may merge."
        cands = self.extractor.extract(text)
        assert not [c for c in cands if c.reference_type == C.REF_LAW]

    def test_named_citation_not_duplicated_by_relative_grammar(self):
        text = "Section 145 of the Delaware General Corporation Law applies."
        cands = self.extractor.extract(text, default_authority="dgcl")
        law = [c for c in cands if c.reference_type == C.REF_LAW]
        assert len(law) == 1
        assert law[0].canonical_key == "dgcl:145"
        assert "relative" not in law[0].normalized_data

    def test_exhibit_reference_candidate(self):
        text = "The form of underwriting agreement is filed as Exhibit 1.1 hereto."
        cands = self.extractor.extract(text)
        docs = [c for c in cands if c.reference_type == C.REF_DOCUMENT]
        assert docs and docs[0].normalized_data["exhibit_number"] == "1.1"

    def test_internal_section_reference_candidate(self):
        text = 'For more information, see "Risk Factors" beginning on page 20.'
        cands = self.extractor.extract(text)
        secs = [c for c in cands if c.reference_type == C.REF_SECTION]
        assert secs and secs[0].normalized_data["heading"] == "Risk Factors"
        hit = secs[0]
        assert "Risk Factors" in text[hit.start : hit.end]

    def test_defined_term_parenthetical(self):
        text = 'Fervo Energy, Inc. (the "Company") is a Delaware corporation.'
        cands = self.extractor.extract(text)
        terms = [c for c in cands if c.reference_type == C.REF_DEFINED_TERM]
        assert terms and terms[0].canonical_key == "term:company"
        assert terms[0].normalized_data["term"] == "Company"
        assert "Company" in text[terms[0].start : terms[0].end]

    def test_defined_term_means_clause(self):
        text = '"Change of Control" means any transaction in which control passes.'
        cands = self.extractor.extract(text)
        terms = [c for c in cands if c.reference_type == C.REF_DEFINED_TERM]
        assert any(c.canonical_key == "term:change-of-control" for c in terms)

    def test_defined_term_strips_trailing_comma_inside_quotes(self):
        text = 'the senior notes (collectively, the "Notes," and together...)'
        cands = self.extractor.extract(text)
        terms = [c for c in cands if c.reference_type == C.REF_DEFINED_TERM]
        assert any(c.canonical_key == "term:notes" for c in terms)

    def test_defined_terms_deduped_by_slug(self):
        text = (
            'Acme Inc. (the "Company"). The Company grows. '
            '"Company" means Acme Inc. as defined.'
        )
        cands = self.extractor.extract(text)
        company = [
            c
            for c in cands
            if c.reference_type == C.REF_DEFINED_TERM
            and c.canonical_key == "term:company"
        ]
        assert len(company) == 1  # deduped across both patterns

    def test_defined_term_cap_is_total_in_document_order(self):
        # The MAX_DEFINED_TERMS cap is a TOTAL per document, applied after
        # merging both grammar forms in document order — a wall of
        # parenthetical definitions must not starve an earlier "means"-form
        # definition (review finding: the old per-regex loop returned before
        # the means regex ever ran).
        means_first = '"Change of Control" means any transfer of control. ' + " ".join(
            f'(the "Term{chr(65 + i // 26)}{chr(65 + i % 26)} Item")'
            for i in range(C.MAX_DEFINED_TERMS)
        )
        cands = self.extractor.extract(means_first)
        terms = [c for c in cands if c.reference_type == C.REF_DEFINED_TERM]
        assert len(terms) == C.MAX_DEFINED_TERMS  # cap holds
        assert any(c.canonical_key == "term:change-of-control" for c in terms)

    def test_defined_term_cap_drops_matches_beyond_position_cap(self):
        # Conversely, a "means"-form definition AFTER the cap-filling
        # parentheticals is dropped: first N definition sites by position win.
        means_last = (
            " ".join(
                f'(the "Term{chr(65 + i // 26)}{chr(65 + i % 26)} Item")'
                for i in range(C.MAX_DEFINED_TERMS)
            )
            + ' "Change of Control" means any transfer of control.'
        )
        cands = self.extractor.extract(means_last)
        terms = [c for c in cands if c.reference_type == C.REF_DEFINED_TERM]
        assert len(terms) == C.MAX_DEFINED_TERMS
        assert not any(c.canonical_key == "term:change-of-control" for c in terms)

    def test_reference_type_filter_skips_unwanted_defined_terms(self):
        text = 'Fervo Energy, Inc. (the "Company") cites Exhibit 1.1.'
        with patch.object(ReferenceExtractor, "_terms", side_effect=AssertionError):
            cands = self.extractor.extract(
                text, reference_types=C.DEFAULT_REFERENCE_TYPES
            )
        assert not [c for c in cands if c.reference_type == C.REF_DEFINED_TERM]
        assert any(c.reference_type == C.REF_DOCUMENT for c in cands)

    def test_defined_terms_not_in_default_reference_types(self):
        # Opt-in: DEFINED_TERM is detected by the extractor but excluded from the
        # default scan/apply set.
        assert C.REF_DEFINED_TERM not in C.DEFAULT_REFERENCE_TYPES
        assert C.REF_DEFINED_TERM in C.ALL_REFERENCE_TYPES

    def test_no_false_positive_on_plain_text(self):
        text = "The company sells software to enterprise customers worldwide."
        assert self.extractor.extract(text) == []


class CandidateClassificationTests(SimpleTestCase):
    def test_candidate_has_classification_defaults(self):
        from opencontractserver.enrichment import constants as C
        from opencontractserver.enrichment.extractor import Candidate

        c = Candidate(reference_type=C.REF_LAW, start=0, end=3, raw_text="x")
        assert c.jurisdiction is None
        assert c.authority_type is None
        assert c.detection_tier == C.DETECTION_TIER_REGISTRY
        assert c.detection_confidence == 1.0

    def test_registry_extractor_marks_tier(self):
        from opencontractserver.enrichment.extractor import ReferenceExtractor

        cands = ReferenceExtractor().extract(
            "Section 145 of the Delaware General Corporation Law"
        )
        assert cands
        assert all(c.detection_tier == "registry" for c in cands)
