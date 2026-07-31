"""Tier-2a generic citation-shape grammars (deterministic, no DB)."""

import contextlib
from unittest.mock import patch

from django.test import SimpleTestCase

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.grammars import GenericCitationExtractor


class FederalGrammarTests(SimpleTestCase):
    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _keys(self, text):
        return {c.canonical_key: c for c in self.ex.extract(text)}

    def test_usc_citation(self):
        c = self._keys("liability under 15 U.S.C. § 78j(b) is alleged")["usc-15:78j(b)"]
        assert c.jurisdiction == "us-federal"
        assert c.authority_type == C.AUTHORITY_TYPE_STATUTE
        assert c.detection_tier == C.DETECTION_TIER_GRAMMAR
        assert c.reference_type == C.REF_LAW

    def test_cfr_citation(self):
        c = self._keys("hazardous waste per 40 C.F.R. § 261.4 applies")["cfr-40:261.4"]
        assert c.authority_type == C.AUTHORITY_TYPE_REGULATION
        assert c.jurisdiction == "us-federal"

    def test_fed_reg_citation_strips_comma(self):
        keys = self._keys("published at 88 Fed. Reg. 1,722 (Jan. 11, 2023)")
        assert "fedreg:88.1722" in keys
        assert keys["fedreg:88.1722"].authority_type == C.AUTHORITY_TYPE_ADMIN_RULE

    def test_public_law_citation(self):
        assert "publ:117-58" in self._keys("enacted by Pub. L. No. 117-58")

    def test_statutes_at_large_citation(self):
        assert "stat:135.429" in self._keys("see 135 Stat. 429 for the text")

    def test_no_false_positive_on_plain_numbers(self):
        assert self._keys("the company has 15 offices and 40 employees") == {}


class StateGrammarTests(SimpleTestCase):
    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _keys(self, text):
        return {c.canonical_key: c for c in self.ex.extract(text)}

    def test_texas_business_orgs_code(self):
        c = self._keys("governed by Tex. Bus. Orgs. Code § 21.401")["tx-boc:21.401"]
        assert c.jurisdiction == "us-tx"
        assert c.authority_type == C.AUTHORITY_TYPE_STATUTE

    def test_delaware_code_dedups_to_dgcl_prefix(self):
        assert "dgcl:145" in self._keys("per Del. Code Ann. tit. 8 § 145")

    def test_california_corp_code(self):
        assert "ca-corp:300" in self._keys("Cal. Corp. Code § 300 requires")


class TexasGridAuthorityGrammarTests(SimpleTestCase):
    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _keys(self, text):
        return {
            candidate.canonical_key: candidate for candidate in self.ex.extract(text)
        }

    def test_puct_texas_admin_code_forms(self):
        tac = self._keys("The standard in 16 TAC § 25.361(c) controls.")[
            "tx-admin-puct:25.361(c)"
        ]
        assert tac.raw_text == "16 TAC § 25.361(c)"
        assert tac.jurisdiction == "us-tx"
        assert tac.authority_type == C.AUTHORITY_TYPE_REGULATION
        assert "tx-admin-puct:25.361" in self._keys("See 16 Tex. Admin. Code § 25.361.")

    def test_pack_names_with_required_markers_preserve_real_citations(self):
        assert "tx-util:37.0561" in self._keys(
            "Texas Utilities Code section 37.0561 applies."
        )
        assert "tx-util:37.0561" in self._keys("PURA § 37.0561 applies.")
        assert "oncor-tariff:6.1.2" in self._keys("See Oncor Tariff § 6.1.2.")

    def test_revision_request_identifiers(self):
        keys = self._keys("PGRR145 was coordinated with NPRR 1325.")
        assert keys["ercot-pgrr:145"].raw_text == "PGRR145"
        assert keys["ercot-nprr:1325"].raw_text == "NPRR 1325"
        assert all(
            candidate.authority_type == C.AUTHORITY_TYPE_ADMIN_RULE
            for candidate in keys.values()
        )

    def test_multilevel_ercot_guide_section(self):
        keys = self._keys("ERCOT Planning Guide § 9.2.1.1(1)(e) requires the study.")
        candidate = keys["ercot-planning:9.2.1.1(1)(e)"]
        assert candidate.raw_text == "ERCOT Planning Guide § 9.2.1.1(1)(e)"
        assert candidate.jurisdiction == "us-tx-ercot"
        assert "ercot-planning:9" in self._keys("ERCOT Planning Guide Section 9")

    def test_market_notice_identifier(self):
        keys = self._keys(
            "Implementation followed Market Notices M-B062326-01 and M-A301326-01."
        )
        candidate = keys["ercot-notice:M-B062326-01"]
        assert candidate.raw_text == "M-B062326-01"
        assert candidate.authority_type == C.AUTHORITY_TYPE_GUIDANCE
        assert "ercot-notice:M-A301326-01" in keys

    def test_grid_shapes_reject_nearby_ordinary_numbers(self):
        assert not self._keys(
            "Planning guide section 9 is discussed in project 1325 on 06/23/26."
        )
        assert not self._keys("The ERCOT Planning Guide 2026 edition is current.")
        assert not self._keys("The ERCOT Protocols 2026 edition is current.")
        assert not self._keys("The Texas Utilities Code 2026 edition is current.")
        assert not self._keys("The Oncor Tariff 2026 edition is current.")
        assert not self._keys(
            "The Oncor Electric Service Guidelines 2026 edition is current."
        )
        assert not self._keys("The 16 TAC 2026 edition is current.")
        assert not self._keys("The labels PGRR and NPRR are incomplete identifiers.")
        assert not self._keys("Inventory item B062326-01 is not a market notice.")


class BareActGrammarTests(SimpleTestCase):
    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _keys(self, text):
        return {c.canonical_key: c for c in self.ex.extract(text)}

    def test_bare_act_with_year(self):
        c = self._keys("subject to the Bank Holding Company Act of 1956")[
            "act:bank-holding-company-act-1956"
        ]
        assert c.authority_type == C.AUTHORITY_TYPE_STATUTE
        assert c.detection_confidence < 0.9  # lower precision than numeric cites
        assert c.normalized_data.get("section") is None

    def test_bare_act_without_year(self):
        assert "act:clean-water-act" in self._keys(
            "violations of the Clean Water Act were alleged"
        )

    def test_requires_multiple_capitalized_words(self):
        # "the Act" alone must NOT match (too generic).
        assert self._keys("as defined in the Act") == {}

    def test_known_act_canonicalizes_to_registry_prefix(self):
        # Every spelling/year variant of a known Act collapses to the SAME
        # registry prefix (not fragmented act:* slugs), so a bare whole-act
        # citation dedups with Tier-1 mentions and resolves to the existing
        # authority corpus.
        assert "exchange-act" in self._keys(
            "subject to the Securities Exchange Act of 1934"
        )
        assert "exchange-act" in self._keys("reporting under the Exchange Act")
        assert "securities-act" in self._keys(
            "registered under the Securities Act of 1933"
        )
        assert "securities-act" in self._keys("an exemption under the Securities Act")
        # No fragmented act:* variant survives for a recognised Act.
        keys = self._keys("the Securities Exchange Act of 1934 applies")
        assert not any(k.startswith("act:") for k in keys), keys

    def test_us_qualifier_does_not_fragment_known_act(self):
        # A leading "U.S." / "United States" qualifier must canonicalise like
        # the bare form (no act:u-s-securities-exchange-act-1934 fragment).
        assert "exchange-act" in self._keys(
            "violations of the U.S. Securities Exchange Act of 1934"
        )
        assert "exchange-act" in self._keys("the United States Securities Exchange Act")
        assert "securities-act" in self._keys(
            "registered under the U. S. Securities Act of 1933"
        )
        keys = self._keys("the U.S. Securities Exchange Act of 1934")
        assert not any(k.startswith("act:") for k in keys), keys

    def test_known_act_carries_classification_and_confidence(self):
        c = self._keys("liability under the Exchange Act")["exchange-act"]
        assert c.jurisdiction == "us-federal"
        assert c.authority_type == C.AUTHORITY_TYPE_STATUTE
        # Recognised body of law — higher confidence than an unknown bare Act.
        assert c.detection_confidence >= 0.9
        assert c.normalized_data.get("section") is None

    def test_unknown_act_keeps_open_vocab_slug(self):
        # An Act NOT in the registry alias table stays a low-confidence act:*
        # key so open-vocabulary discovery still surfaces it.
        keys = self._keys("under the Bank Holding Company Act of 1956")
        assert "act:bank-holding-company-act-1956" in keys
        assert keys["act:bank-holding-company-act-1956"].detection_confidence < 0.9


class GrammarRobustnessTests(SimpleTestCase):
    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _keys(self, text):
        return {c.canonical_key for c in self.ex.extract(text)}

    def test_public_law_short_form_without_no(self):
        # Bluebook short form "Pub. L. 117-58" (no "No.") is the dominant form.
        assert "publ:117-58" in self._keys("enacted by Pub. L. 117-58 in 2021")

    def test_state_code_tolerates_ocr_double_space(self):
        # OCR / line-break wraps insert extra whitespace inside abbreviations;
        # the \\s+-flexible alternation + normalized lookup must still match.
        assert "tx-boc:21.401" in self._keys(
            "governed by Tex. Bus. Orgs.  Code § 21.401"
        )


class MunicipalKnownGrammarTests(SimpleTestCase):
    """Table-keyed municipal codes (issue #1995) → full jurisdiction."""

    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _keys(self, text):
        return {c.canonical_key: c for c in self.ex.extract(text)}

    def test_san_francisco_municipal_code(self):
        c = self._keys("governed by San Francisco Municipal Code § 1234")[
            "muni-san-francisco:1234"
        ]
        assert c.jurisdiction == "us-ca-san-francisco"
        assert c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        assert c.detection_tier == C.DETECTION_TIER_GRAMMAR
        assert c.reference_type == C.REF_LAW

    def test_bluebook_abbreviation_shares_spelled_out_prefix(self):
        # "S.F. Mun. Code" and "San Francisco Municipal Code" are ONE authority.
        assert "muni-san-francisco:56.5" in self._keys("see S.F. Mun. Code § 56.5")

    def test_abbreviated_city_municipal_code_resolves_to_canonical(self):
        # The abbreviated-city + spelled-"Municipal Code" forms are tabled so the
        # abbreviation slug (l-a / s-f) never fragments from the canonical
        # muni-los-angeles / muni-san-francisco authority.
        la = self._keys("L.A. Municipal Code § 12.21")
        assert "muni-los-angeles:12.21" in la
        assert "muni-l-a:12.21" not in la
        assert "muni-san-francisco:5" in self._keys("S.F. Municipal Code § 5")

    def test_multi_segment_section_locator(self):
        # Municipal codes nest deeper than a single ".N" (Seattle: 6.02.010).
        c = self._keys("per Seattle Municipal Code § 6.02.010")["muni-seattle:6.02.010"]
        assert c.jurisdiction == "us-wa-seattle"

    def test_nyc_administrative_code(self):
        c = self._keys("violation of N.Y.C. Admin. Code § 27-2004")[
            "muni-new-york:27-2004"
        ]
        assert c.jurisdiction == "us-ny-new-york"

    def test_nyc_municipal_code_form_resolves_to_table_prefix(self):
        # "New York City Municipal Code" is tabled as an alias of NYC's
        # Administrative Code, so it resolves to the single ``muni-new-york``
        # authority (full jurisdiction) and does NOT fragment to the open-vocab
        # ``muni-new-york-city`` slug that "New York City" (ends in "City") would
        # otherwise yield. Guards the namespace-sharing invariant for NYC.
        keys = self._keys("New York City Municipal Code § 27-2004")
        assert "muni-new-york:27-2004" in keys
        assert "muni-new-york-city:27-2004" not in keys
        assert keys["muni-new-york:27-2004"].jurisdiction == "us-ny-new-york"

    def test_code_phrase_before_city(self):
        assert "muni-chicago:1-2" in self._keys(
            "under the Municipal Code of Chicago § 1-2"
        )

    def test_code_of_ordinances_form(self):
        assert "muni-houston:10-1" in self._keys(
            "Houston Code of Ordinances § 10-1 applies"
        )

    def test_confidence_below_structured_federal(self):
        # "calibrated below structured federal cites" (issue #1995).
        c = self._keys("San Francisco Municipal Code § 1234")["muni-san-francisco:1234"]
        assert c.detection_confidence < 0.9

    def test_known_code_does_not_double_emit_with_generic_shadow(self):
        # The table pass claims the span; the open-vocab pass must skip it, so a
        # known code yields exactly ONE municipal candidate (not table+generic).
        cands = [
            c
            for c in self.ex.extract("San Francisco Municipal Code § 1234")
            if c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        ]
        assert len(cands) == 1, [c.canonical_key for c in cands]
        assert cands[0].jurisdiction == "us-ca-san-francisco"

    def test_tolerates_ocr_double_space(self):
        assert "muni-san-francisco:1234" in self._keys(
            "San Francisco  Municipal  Code § 1234"
        )


class MunicipalGenericGrammarTests(SimpleTestCase):
    """Open-vocabulary municipal shape — cities NOT in the table."""

    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _keys(self, text):
        return {c.canonical_key: c for c in self.ex.extract(text)}

    def test_unknown_city_keyed_under_city_slug(self):
        c = self._keys("Oakland Municipal Code § 5.04.010 requires")[
            "muni-oakland:5.04.010"
        ]
        assert c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        # State unknown from free text — jurisdiction is honestly left None.
        assert c.jurisdiction is None

    def test_open_vocab_confidence_below_table(self):
        c = self._keys("Oakland Municipal Code § 5")["muni-oakland:5"]
        assert c.detection_confidence < 0.8  # below _CONF_MUNICIPAL

    def test_bare_municipal_code_without_city(self):
        c = self._keys("see the bare Municipal Code § 5.2 here")["muni:5.2"]
        assert c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        assert c.jurisdiction is None

    def test_section_word_and_sec_connectors(self):
        assert "muni-oakland:5" in self._keys("Oakland Municipal Code Section 5")
        assert "muni-oakland:5-1" in self._keys("Oakland Municipal Code Sec. 5-1")

    def test_leading_article_stopword_stripped_from_city(self):
        # "the Portland Municipal Code" -> muni-portland (not muni-the-portland).
        assert "muni-portland:1" in self._keys("This Portland Municipal Code § 1")

    def test_ordinance_form(self):
        c = self._keys("pursuant to Ordinance No. 2021-15")["muni:ord-2021-15"]
        assert c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        assert c.detection_confidence < 0.8

    def test_city_qualified_ordinance(self):
        assert "muni-berkeley:ord-7123" in self._keys(
            "Berkeley Ordinance No. 7123 imposes"
        )

    def test_ordinance_tolerates_ocr_double_space(self):
        # The "Ordinance\\s+No." separator is \\s+, so an OCR double-space wrap
        # between the words still matches.
        assert "muni:ord-2021-15" in self._keys("see Ordinance  No. 2021-15 here")

    def test_bare_city_placeholder_collapses_to_muni(self):
        # A template placeholder "City Municipal Code § 5" (no real city name)
        # must NOT invent a ``muni-city`` authority — "city"/"county" are
        # stopwords, so it collapses to the honest bare ``muni:`` key.
        assert "muni:5" in self._keys("City Municipal Code § 5")
        assert "muni-city:5" not in self._keys("City Municipal Code § 5")
        assert "muni:5" in self._keys("County Municipal Code § 5")

    def test_trailing_city_qualifier_preserved(self):
        # Only LEADING stopwords drop: a trailing "City"/"County" in a real
        # place name survives so the authority isn't fragmented.
        assert "muni-kansas-city:5" in self._keys("Kansas City Municipal Code § 5")
        assert "muni-marin-county:7" in self._keys(
            "Marin County Code of Ordinances § 7"
        )

    def test_citation_signal_lead_word_not_absorbed_into_city(self):
        # A capitalised Bluebook signal / sentence-lead directly before the city
        # ("See Oakland …") must not be absorbed into the slug (muni-see-oakland);
        # the leading signal is stripped so the real city authority is preserved.
        see = self._keys("See Oakland Municipal Code § 5")
        assert "muni-oakland:5" in see
        assert "muni-see-oakland:5" not in see
        assert "muni-portland:1" in self._keys("Under Portland Municipal Code § 1")

    def test_open_vocab_tolerates_ocr_double_space(self):
        # The open-vocab path (not only the table path) tolerates OCR double-space
        # within and around the code phrase.
        assert "muni-oakland:5" in self._keys("Oakland  Municipal  Code § 5")

    def test_signal_stopwords_do_not_collide_with_place_names(self):
        # The signal denylist must never swallow a real jurisdiction whose name
        # starts with a Bluebook signal — regression guard against re-adding a
        # colliding stopword like "contra" (would corrupt "Contra Costa" to
        # ``muni-costa``).
        assert "muni-contra-costa:4.1" in self._keys(
            "Contra Costa Code of Ordinances § 4.1"
        )
        assert "muni-contra-costa-county:4.1" in self._keys(
            "Contra Costa County Code of Ordinances § 4.1"
        )

    def test_real_three_word_city_not_truncated(self):
        # The {0,3} city bound must keep a genuine 3-word municipality intact
        # ("San Luis Obispo"); a tighter {0,2} bound would corrupt it to
        # ``muni-luis-obispo``.
        assert "muni-san-luis-obispo:5" in self._keys(
            "San Luis Obispo Municipal Code § 5"
        )

    def test_non_stopword_lead_lands_in_slug_at_provisional_confidence(self):
        # The stopword list is deliberately MINIMAL (only unambiguous non-place
        # leads), so a capitalised NON-stopword word before the city is NOT
        # stripped — it lands in the slug ("Regarding Oakland" ->
        # muni-regarding-oakland) and is surfaced as a PROVISIONAL candidate
        # (confidence < 0.8, jurisdiction None) rather than silently mis-keyed as
        # muni-oakland. Pins the minimal-stopword design + the provisional
        # contract that downstream consumers tier-filter on.
        keys = self._keys("Regarding Oakland Municipal Code § 5")
        assert "muni-regarding-oakland:5" in keys
        assert "muni-oakland:5" not in keys
        c = keys["muni-regarding-oakland:5"]
        assert c.jurisdiction is None
        assert c.detection_confidence < 0.8

    def test_nyc_ordinance_form_is_provisional_not_table_resolved(self):
        # An ordinance-form NYC cite goes through the open-vocab provisional path
        # (ordinance numbers are NOT table-upgradeable — see _municipal_generic),
        # so it carries the provisional contract (low confidence, jurisdiction
        # None) rather than resolving to the table's muni-new-york authority.
        # Pins the documented behaviour: ordinance numbers are discovery signals,
        # not resolved authorities.
        muni = [
            c
            for c in self.ex.extract("New York City Ordinance No. 2023-45")
            if c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        ]
        assert muni
        for c in muni:
            assert c.jurisdiction is None
            assert c.detection_confidence < 0.8

    def test_open_vocab_prefix_classifies_to_municipal(self):
        # An open-vocab city prefix must classify (never strand at None type).
        jur, typ = C.classify_prefix("muni-oakland")
        assert typ == C.AUTHORITY_TYPE_MUNICIPAL
        assert jur is None


class MunicipalFalsePositiveTests(SimpleTestCase):
    """Explicit false-positive guards (issue #1995 precision bar)."""

    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _muni_keys(self, text):
        return {
            c.canonical_key
            for c in self.ex.extract(text)
            if c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        }

    def test_no_match_without_section_anchor(self):
        # The required §/Section/Sec. + number is the core guard.
        assert (
            self._muni_keys("the city adopted a new Municipal Code last year") == set()
        )

    def test_lowercase_code_phrase_excluded(self):
        assert self._muni_keys("the city updated its municipal code recently") == set()

    def test_state_administrative_code_not_municipal(self):
        # "Texas Administrative Code" is a STATE regulation, NOT a municipal code:
        # "Administrative Code" must never be open-vocab-matched as municipal.
        assert self._muni_keys("see the Texas Administrative Code § 1.5 here") == set()

    def test_bare_ordinance_without_number_excluded(self):
        assert self._muni_keys("the city passed an Ordinance last spring") == set()

    def test_plain_numbers_excluded(self):
        assert self._muni_keys("the company has 15 offices and 40 employees") == set()

    def test_internal_ordinance_number_low_confidence_no_jurisdiction(self):
        # The ordinance form has a deliberately LOWER precision bar than the code
        # grammar (it needs no §/Section anchor), so internal procedural numbering
        # like "Employee Ordinance No. 7" still matches (here keyed
        # ``muni-employee`` — any capitalised lead word is taken as a pseudo-city).
        # The tradeoff is documented by the invariants every such match carries:
        # confidence below the table tier (<0.8) and a None jurisdiction, so
        # downstream consumers can filter it. It never reaches the trusted tier.
        muni = [
            c
            for c in self.ex.extract("governed by Employee Ordinance No. 7")
            if c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        ]
        assert muni  # the low-precision form does match (documented tradeoff)
        for c in muni:
            assert c.jurisdiction is None
            assert c.detection_confidence < 0.8


class MunicipalGoldenCorpusTests(SimpleTestCase):
    """Golden cross-municipality corpus — one realistic multi-city paragraph."""

    CORPUS = (
        "The premises must comply with San Francisco Municipal Code § 1234 and "
        "the Los Angeles Municipal Code § 12.21, as well as N.Y.C. Admin. Code "
        "§ 27-2004. Operations in Washington follow Seattle Municipal Code "
        "§ 6.02.010, while the Illinois site is governed by the Municipal Code "
        "of Chicago § 1-2 and the Houston facility by the Houston Code of "
        "Ordinances § 10-1. The Oakland Municipal Code § 5.04.010 also applies, "
        "as does Ordinance No. 2021-15."
    )

    def setUp(self):
        self.ex = GenericCitationExtractor()
        self.by_key = {c.canonical_key: c for c in self.ex.extract(self.CORPUS)}

    def test_all_known_municipalities_detected_with_jurisdiction(self):
        expected = {
            "muni-san-francisco:1234": "us-ca-san-francisco",
            "muni-los-angeles:12.21": "us-ca-los-angeles",
            "muni-new-york:27-2004": "us-ny-new-york",
            "muni-seattle:6.02.010": "us-wa-seattle",
            "muni-chicago:1-2": "us-il-chicago",
            "muni-houston:10-1": "us-tx-houston",
        }
        for key, jur in expected.items():
            assert key in self.by_key, f"missing {key}: {sorted(map(str, self.by_key))}"
            assert self.by_key[key].jurisdiction == jur, key
            assert self.by_key[key].authority_type == C.AUTHORITY_TYPE_MUNICIPAL

    def test_open_vocab_city_and_ordinance_detected(self):
        assert "muni-oakland:5.04.010" in self.by_key
        assert self.by_key["muni-oakland:5.04.010"].jurisdiction is None
        assert "muni:ord-2021-15" in self.by_key

    def test_every_municipal_confidence_below_federal(self):
        muni = [
            c
            for c in self.by_key.values()
            if c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        ]
        assert muni  # sanity: the corpus produced municipal mentions
        assert all(c.detection_confidence < 0.9 for c in muni)

    def test_cross_municipality_coverage(self):
        # At least six distinct municipal authorities across five states.
        prefixes = {
            (c.canonical_key or "").split(":", 1)[0]
            for c in self.by_key.values()
            if c.authority_type == C.AUTHORITY_TYPE_MUNICIPAL
        }
        assert len(prefixes) >= 6, prefixes


class ReferenceTypeFilterTests(SimpleTestCase):
    """Coverage for the ``reference_types`` gate on ``extract()``.

    Every grammar pass in this module exclusively emits ``REF_LAW``
    candidates, so a caller that does not want ``REF_LAW`` should short-
    circuit ALL nine passes rather than run them and filter downstream (the
    optimization mirrors the one already applied to
    ``ReferenceExtractor.extract``).
    """

    # All module-level grammar functions plus the instance-method passes that
    # ``GenericCitationExtractor.extract`` calls when REF_LAW is wanted.
    _MODULE_LEVEL_PASSES = (
        "_usc",
        "_cfr",
        "_fedreg",
        "_publ",
        "_stat",
        "_puct_texas_admin_code",
        "_ercot_authorities",
        "_bare_acts",
    )
    _INSTANCE_PASSES = ("_states", "_municipal", "_municipal_generic")

    def setUp(self):
        self.ex = GenericCitationExtractor()
        # A single blob that would trip every grammar pass if run.
        self.text = (
            "liability under 15 U.S.C. § 78j(b), hazardous waste per 40 "
            "C.F.R. § 261.4, published at 88 Fed. Reg. 1,722, enacted by "
            "Pub. L. No. 117-58, see 135 Stat. 429, subject to the Clean "
            "Water Act, governed by Cal. Corp. Code § 300, and per San "
            "Francisco Municipal Code § 1234 and Ordinance No. 2021-15."
        )

    def _patch_all_passes(self):
        stack = contextlib.ExitStack()
        for name in self._MODULE_LEVEL_PASSES:
            stack.enter_context(
                patch(
                    f"opencontractserver.enrichment.grammars.{name}",
                    side_effect=AssertionError(f"{name} should not run"),
                )
            )
        for name in self._INSTANCE_PASSES:
            stack.enter_context(
                patch.object(
                    GenericCitationExtractor,
                    name,
                    side_effect=AssertionError(f"{name} should not run"),
                )
            )
        return stack

    def test_reference_types_without_law_skips_every_grammar_pass(self):
        with self._patch_all_passes():
            cands = self.ex.extract(self.text, reference_types={C.REF_SECTION})
        assert cands == []

    def test_reference_types_with_law_still_runs_grammar_passes(self):
        cands = self.ex.extract(self.text, reference_types={C.REF_LAW})
        assert any(c.canonical_key == "usc-15:78j(b)" for c in cands)
        assert all(c.reference_type == C.REF_LAW for c in cands)

    def test_reference_types_none_is_unfiltered(self):
        default = {c.canonical_key for c in self.ex.extract(self.text)}
        explicit = {
            c.canonical_key for c in self.ex.extract(self.text, reference_types=None)
        }
        assert default == explicit
