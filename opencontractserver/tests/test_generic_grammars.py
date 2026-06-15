"""Tier-2a generic citation-shape grammars (deterministic, no DB)."""

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
