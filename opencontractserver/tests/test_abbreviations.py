from django.test import SimpleTestCase

from opencontractserver.enrichment import abbreviations as A
from opencontractserver.enrichment import constants as C


class AbbreviationTableTests(SimpleTestCase):
    def test_known_state_code_classifies(self):
        prefix, jur, typ = A.STATE_CODE_ABBREVIATIONS["Tex. Bus. Orgs. Code"]
        assert prefix == "tx-boc"
        assert jur == "us-tx"
        assert typ == C.AUTHORITY_TYPE_STATUTE

    def test_delaware_code_maps_to_dgcl_for_dedup(self):
        prefix, _jur, _typ = A.STATE_CODE_ABBREVIATIONS["Del. Code Ann. tit. 8"]
        assert prefix == "dgcl"

    def test_all_entries_have_three_tuple(self):
        for abbr, value in A.STATE_CODE_ABBREVIATIONS.items():
            assert len(value) == 3, abbr
            assert value[2] in C.ALL_AUTHORITY_TYPES, abbr
