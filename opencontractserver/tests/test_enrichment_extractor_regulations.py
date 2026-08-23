"""Tier-1 extraction of REGULATION-style citations.

The statute-style forms the extractor was built around ("Section 145 of the
DGCL") all use bare integer section numbers introduced by the word "Section".
Regulations do neither: their section numbers are dotted (22 C.F.R. § 120.41,
1 Tex. Admin. Code § 1301.051) and they are introduced by "§" far more often
than by the spelled-out word.

Found while installing an ITAR authority pack, where every one of the pack's
178 regulation sections was unreachable from real citations. Two distinct
failures, both silent:

  * "Section 120.10 of the ITAR" matched NOTHING — the section pattern
    consumed "120" and then required " of", but found ".".
  * "ITAR Section 120.41" matched the prefix and produced ``itar:120`` — a
    citation to the definition of "specially designed" quietly resolving to the
    Part 120 overview document. Wrong answers, not missing ones.

Roman-numeral divisions ("Category XI of the United States Munitions List")
were likewise unreachable. They are matched only behind BOTH a divider word and
a registered authority alias, so "Section I of the Agreement" cannot become a
citation.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from opencontractserver.enrichment.extractor import ReferenceExtractor

ALIASES = {
    "itar": "itar",
    "22 c.f.r.": "itar",
    "22 cfr": "itar",
    "international traffic in arms regulations": "itar",
    "united states munitions list": "usml",
    "usml": "usml",
    "delaware general corporation law": "dgcl",
    "dgcl": "dgcl",
}


class RegulationCitationExtractionTests(SimpleTestCase):
    def setUp(self) -> None:
        self.extractor = ReferenceExtractor(ALIASES)

    def keys(self, text: str) -> list[str | None]:
        return [c.canonical_key for c in self.extractor.extract(text)]

    # ---- dotted section numbers ------------------------------------------
    def test_dotted_section_of_the_authority(self) -> None:
        self.assertIn(
            "itar:120.10", self.keys("Section 120.10 of the ITAR introduces the USML.")
        )

    def test_dotted_section_after_the_authority(self) -> None:
        """The one that produced a WRONG key rather than no key."""
        keys = self.keys("See ITAR Section 120.41 for specially designed.")
        self.assertIn("itar:120.41", keys)
        self.assertNotIn("itar:120", keys)

    def test_multi_dotted_section(self) -> None:
        self.assertIn(
            "itar:120.10.5", self.keys("Section 120.10.5 of the ITAR applies.")
        )

    def test_sentence_final_period_is_not_swallowed(self) -> None:
        """`(?:\\.\\d+)*` needs digits after the dot, so a full stop is safe."""
        self.assertIn("itar:120", self.keys("See Section 120 of the ITAR."))

    # ---- the section symbol ----------------------------------------------
    def test_section_symbol_after_authority(self) -> None:
        self.assertIn("itar:120.41", self.keys("See ITAR § 120.41 for the test."))

    def test_section_symbol_with_spaced_alias(self) -> None:
        self.assertIn("itar:126.1", self.keys("22 C.F.R. § 126.1 denies the policy."))

    def test_double_section_symbol(self) -> None:
        self.assertIn("itar:120.1", self.keys("See ITAR §§ 120.1 and 120.2."))

    def test_section_symbol_without_space(self) -> None:
        self.assertIn(
            "itar:127.1", self.keys("A violation under ITAR §127.1 occurred.")
        )

    # ---- part-level citation ---------------------------------------------
    def test_part_of_the_authority(self) -> None:
        self.assertIn(
            "itar:122", self.keys("Registration is required by Part 122 of the ITAR.")
        )

    def test_part_requires_a_registered_authority(self) -> None:
        """The alias alternation is what keeps 'Part N of the X' from over-firing."""
        self.assertEqual([], self.keys("See Part 3 of the Purchase Agreement."))

    # ---- roman-numeral divisions -----------------------------------------
    def test_category_of_the_authority(self) -> None:
        self.assertIn(
            "usml:xi",
            self.keys(
                "Category XI of the United States Munitions List covers electronics."
            ),
        )

    def test_authority_then_category(self) -> None:
        self.assertIn("usml:viii", self.keys("USML Category VIII covers aircraft."))

    def test_division_keys_are_lowercased(self) -> None:
        """Authority-key matching is case-sensitive; an uppercase key is unreachable."""
        for key in self.keys("USML Category VIII covers aircraft."):
            self.assertIsNotNone(key)
            assert key is not None  # narrows for mypy
            self.assertEqual(key, key.lower())

    def test_division_requires_a_registered_authority(self) -> None:
        self.assertEqual([], self.keys("See Category IV of the Agreement."))

    def test_division_token_is_scoped_to_category(self) -> None:
        """Other divider words are intentionally NOT matched.

        Every registered alias on an install shares this pattern, so widening
        the divider list would fire against unrelated authority corpora for no
        demonstrated gain. Add a word here only alongside a test for the
        citation form it is meant to catch.
        """
        self.assertEqual([], self.keys("See Article IV of the DGCL."))

    # ---- statute forms must keep working ---------------------------------
    def test_integer_statute_form_still_matches(self) -> None:
        self.assertIn(
            "dgcl:145",
            self.keys("Section 145 of the Delaware General Corporation Law."),
        )

    def test_parenthetical_subsections_still_match(self) -> None:
        self.assertIn(
            "dgcl:141(b)",
            self.keys("Section 141(b) of the Delaware General Corporation Law."),
        )

    def test_letter_suffixed_section_still_matches(self) -> None:
        self.assertIn("dgcl:144a", self.keys("Section 144A of the DGCL applies."))


class ECCNStaysOutOfTier1Tests(SimpleTestCase):
    """ECCNs are a Tier-2a SHAPE and must not be emitted from Tier-1.

    The behaviour itself is covered in ``test_generic_grammars.ECCNGrammarTests``.
    What is guarded HERE is the architectural boundary: an earlier revision of
    this work put the pattern in the registry extractor and emitted ``ccl:``,
    which hardcodes one pack's prefix into core. A pack maps the shape-level
    ``eccn:`` key to its own with one ``equivalences`` row instead.

    Kept as a test rather than a comment because the tempting fix — "just add
    the pattern where the other citation patterns are" — reintroduces it
    silently and nothing else would fail.
    """

    def setUp(self) -> None:
        self.extractor = ReferenceExtractor({**ALIASES, "ccl": "ccl"})

    def keys(self, text: str) -> list[str | None]:
        return [c.canonical_key for c in self.extractor.extract(text)]

    def test_tier1_emits_no_key_for_a_bare_eccn(self) -> None:
        self.assertEqual([], self.keys("The item is controlled under ECCN 3A611."))

    def test_tier1_never_emits_a_ccl_key(self) -> None:
        found = self.keys("See ECCN 6A003, ECCN 7E611 and ECCN 9A610.a.")
        self.assertEqual([], [k for k in found if k and k.startswith("ccl:")])
