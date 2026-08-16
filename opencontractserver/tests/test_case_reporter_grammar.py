"""Case-reporter citation grammar ("569 F.3d 326").

A Tier-2a citation SHAPE: recognisable without knowing which body of case law
(if any) is installed, exactly like the HTS family it sits beside. Tests go
through ``GenericCitationExtractor`` rather than the private matcher, so they
cover registration and reference-type filtering too.

The precision cases matter more than the recall cases here. A reporter pattern
that is even slightly loose mines statute citations, Federal Register cites and
ordinary numbers, and every false positive becomes a dangling reference to a
case that does not exist.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.grammars import GenericCitationExtractor


class CaseReporterGrammarTests(SimpleTestCase):
    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _cites(self, text):
        return [
            c
            for c in self.ex.extract(text, reference_types={C.REF_LAW})
            if (c.canonical_key or "").startswith(f"{C.CASE_REPORTER_PREFIX}:")
        ]

    # ---- recall ---------------------------------------------------------- #
    def test_federal_reporter_citation(self):
        cands = self._cites("United States v. Pulungan, 569 F.3d 326 (7th Cir. 2009)")
        assert len(cands) == 1
        c = cands[0]
        assert c.canonical_key == f"{C.CASE_REPORTER_PREFIX}:569-f3d-326"
        assert c.reference_type == C.REF_LAW
        assert c.jurisdiction == C.JURISDICTION_US_FEDERAL
        assert c.authority_type == C.AUTHORITY_TYPE_CASE
        assert c.detection_tier == C.DETECTION_TIER_GRAMMAR
        assert c.normalized_data["volume"] == "569"
        assert c.normalized_data["page"] == "326"

    def test_supreme_court_reporters(self):
        for text, key in (
            ("Brown v. Board of Education, 347 U.S. 483 (1954)", "347-us-483"),
            ("Kisor v. Wilkie, 139 S. Ct. 2400 (2019)", "139-sct-2400"),
        ):
            cands = self._cites(text)
            assert len(cands) == 1, text
            assert cands[0].canonical_key == f"{C.CASE_REPORTER_PREFIX}:{key}"

    def test_district_and_specialty_reporters(self):
        for text, key in (
            ("Karn v. Dep't of State, 925 F. Supp. 1 (D.D.C. 1996)", "925-fsupp-1"),
            ("In re Debtor, 512 B.R. 99", "512-br-99"),
            ("Smith v. Commissioner, 140 T.C. 12", "140-tc-12"),
        ):
            cands = self._cites(text)
            assert len(cands) == 1, text
            assert cands[0].canonical_key == f"{C.CASE_REPORTER_PREFIX}:{key}"

    def test_spacing_variants_normalise_to_one_key(self):
        """'S. Ct.' and 'S.Ct.' are the same reporter."""
        a = self._cites("139 S. Ct. 2400")
        b = self._cites("139 S.Ct. 2400")
        assert a and b
        assert a[0].canonical_key == b[0].canonical_key

    def test_multiple_citations_in_one_passage(self):
        text = (
            "The court followed 569 F.3d 326, distinguished 347 U.S. 483, and "
            "declined to extend 925 F. Supp. 1."
        )
        keys = {c.canonical_key for c in self._cites(text)}
        assert len(keys) == 3

    # ---- precision ------------------------------------------------------- #
    def test_statute_citations_are_not_mined(self):
        """'22 U.S.C. 2778(c)' contains 'U.S.' but is not a reporter citation."""
        assert self._cites("Liability arises under 22 U.S.C. 2778(c).") == []

    def test_cfr_and_federal_register_citations_are_not_mined(self):
        for text in (
            "See 15 C.F.R. 744.11 and 22 C.F.R. 121.1.",
            "Published at 91 FR 46281, July 23, 2026.",
            "Supplement No. 4 to Part 744 applies.",
        ):
            assert self._cites(text) == [], text

    def test_ordinary_numbers_are_not_mined(self):
        for text in (
            "A payload of 500 kg to a range of 300 km.",
            "The 2024 revision affected 12 entries across 3 parts.",
            "Invoice 4821 totalled 1200 USD.",
        ):
            assert self._cites(text) == [], text

    def test_unlisted_reporter_yields_nothing(self):
        """The reporter alternation is closed: no speculative keys."""
        assert self._cites("Doe v. Roe, 12 Zz. Rep. 34 (1999)") == []

    def test_no_case_corpus_required(self):
        """A shape grammar does not depend on any pack being installed.

        The emitted prefix is shape-level and deliberately NOT whatever prefix a
        case-law pack binds to its own corpus — a pack maps it to its key with
        one equivalences row. Emitting a pack's key from core would bake one
        pack's naming convention into the framework.
        """
        cands = self._cites("569 F.3d 326")
        assert len(cands) == 1
        assert cands[0].canonical_key.startswith(f"{C.CASE_REPORTER_PREFIX}:")
