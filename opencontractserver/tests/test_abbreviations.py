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


class MunicipalAbbreviationTableTests(SimpleTestCase):
    def test_known_municipal_code_classifies(self):
        prefix, jur, typ = A.MUNICIPAL_CODE_ABBREVIATIONS[
            "San Francisco Municipal Code"
        ]
        assert prefix == "muni-san-francisco"
        assert jur == "us-ca-san-francisco"
        assert typ == C.AUTHORITY_TYPE_MUNICIPAL

    def test_all_entries_have_three_tuple_and_municipal_type(self):
        for abbr, value in A.MUNICIPAL_CODE_ABBREVIATIONS.items():
            assert len(value) == 3, abbr
            assert value[2] == C.AUTHORITY_TYPE_MUNICIPAL, abbr

    def test_jurisdiction_codes_are_hierarchical_below_state(self):
        # Municipal jurisdictions must be us-<state>-<city> (a city sits BELOW a
        # state in the hierarchy) so the crawl/frontier per-jurisdiction caps and
        # the governance graph roll them up under the right state.
        for abbr, (_prefix, jur, _typ) in A.MUNICIPAL_CODE_ABBREVIATIONS.items():
            parts = jur.split("-")
            assert parts[0] == "us", abbr
            assert len(parts) >= 3, (abbr, jur)

    def test_prefix_matches_municipal_shape(self):
        # Every table prefix must be ``muni-<city-slug>`` so it shares a
        # namespace with the open-vocab grammar (and classify_prefix recognises
        # it). A drifted prefix would silently fragment from its open-vocab twin.
        # Assert through the PUBLIC classify_prefix surface (not the private
        # _MUNI_PREFIX_RE) so the test pins the contract, not the implementation.
        for abbr, (prefix, _jur, _typ) in A.MUNICIPAL_CODE_ABBREVIATIONS.items():
            assert C.classify_prefix(prefix)[1] == C.AUTHORITY_TYPE_MUNICIPAL, (
                abbr,
                prefix,
            )
            assert prefix.startswith("muni-"), (abbr, prefix)

    def test_abbreviated_and_spelled_forms_share_one_prefix(self):
        # The Bluebook abbreviation and the spelled-out name of the same city
        # must collapse to ONE authority (no fragmentation across spellings).
        assert (
            A.MUNICIPAL_CODE_ABBREVIATIONS["S.F. Mun. Code"][0]
            == A.MUNICIPAL_CODE_ABBREVIATIONS["San Francisco Municipal Code"][0]
        )
