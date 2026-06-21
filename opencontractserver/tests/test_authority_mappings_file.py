"""Completeness + shape tests for the declarative authority-mappings YAML.

Supersedes the role of the old three-dict ``test_enrichment_classification_constants``
checks for the *file*: every shipped prefix is fully classified + displayed and
every equivalence key parses. The pure reader (``enrichment.data.mappings``) is
exercised directly so a malformed file is caught without touching the DB.
"""

from django.test import SimpleTestCase

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.data import mappings as M


class AuthorityMappingsFileCompletenessTests(SimpleTestCase):
    def test_every_prefix_is_fully_classified(self):
        prefixes = M.iter_prefixes()
        assert prefixes, "expected at least one shipped prefix"
        for prefix, spec in prefixes.items():
            assert M.is_valid_prefix(prefix), prefix
            assert spec["jurisdiction"], (prefix, "missing jurisdiction")
            assert spec["authority_type"] in C.ALL_AUTHORITY_TYPES, (
                prefix,
                spec["authority_type"],
            )
            assert spec["display_name"], (prefix, "missing display_name")

    def test_every_equivalence_key_parses(self):
        for entry in M.iter_equivalences():
            assert M.is_valid_canonical_key(entry["from_key"]), entry
            assert M.is_valid_canonical_key(entry["to_key"]), entry

    def test_shipped_prefixes_cover_the_known_registry_bodies(self):
        prefixes = set(M.iter_prefixes())
        for expected in (
            "dgcl",
            "securities-act",
            "exchange-act",
            "irc",
            "ica",
            "iaa",
            C.SEC_RULE_PREFIX,
        ):
            assert expected in prefixes, expected


class DerivedConstantsConsistencyTests(SimpleTestCase):
    """The constants the engine reads are derived from the YAML — pin them."""

    def test_authority_prefix_map_matches_yaml_aliases(self):
        prefixes = M.iter_prefixes()
        for prefix, spec in prefixes.items():
            for alias in spec["aliases"]:
                assert C.AUTHORITY_PREFIX[alias] == prefix, (alias, prefix)

    def test_classification_and_display_cover_every_prefix(self):
        for prefix, spec in M.iter_prefixes().items():
            assert C.PREFIX_CLASSIFICATION[prefix] == (
                spec["jurisdiction"],
                spec["authority_type"],
            )
            assert C.PREFIX_DISPLAY_NAME[prefix] == spec["display_name"]

    def test_legacy_aliases_survived_the_collapse(self):
        # The exact alias set the literal AUTHORITY_PREFIX used to ship.
        assert C.AUTHORITY_PREFIX["delaware general corporation law"] == "dgcl"
        assert C.AUTHORITY_PREFIX["dgcl"] == "dgcl"
        assert C.AUTHORITY_PREFIX["exchange act"] == "exchange-act"
        assert C.AUTHORITY_PREFIX["securities exchange act"] == "exchange-act"
        assert C.AUTHORITY_PREFIX["internal revenue code"] == "irc"


class MappingsReaderTests(SimpleTestCase):
    def test_iter_prefixes_rejects_bad_prefix(self):
        with self.assertRaises(ValueError):
            M.iter_prefixes({"prefixes": {"Bad Prefix!": {"display_name": "x"}}})

    def test_iter_equivalences_rejects_malformed_key(self):
        with self.assertRaises(ValueError):
            M.iter_equivalences(
                {"equivalences": [{"from_key": "garbage", "to_key": "usc-26:401"}]}
            )

    def test_iter_equivalences_rejects_missing_key(self):
        with self.assertRaises(ValueError):
            M.iter_equivalences({"equivalences": [{"to_key": "usc-26:401"}]})

    def test_iter_rewrite_rules_rejects_bad_regex(self):
        with self.assertRaises(ValueError):
            M.iter_rewrite_rules(
                {"rewrite_rules": [{"pattern": "irc:(", "replacement": "x"}]}
            )

    def test_is_valid_canonical_key(self):
        assert M.is_valid_canonical_key("usc-15:78j")
        assert M.is_valid_canonical_key("cfr-17:240.10b-5")
        assert not M.is_valid_canonical_key("nocolon")
        assert not M.is_valid_canonical_key("UPPER:1")
        assert not M.is_valid_canonical_key("prefix:")
        assert not M.is_valid_canonical_key(None)

    def test_apply_rewrite_rules_explicit_rules(self):
        rules = [{"pattern": r"^irc:(?P<n>.+)$", "replacement": r"usc-26:\g<n>"}]
        assert M.apply_rewrite_rules("irc:401", rules=rules) == ["usc-26:401"]
        # No match -> empty; original never echoed back.
        assert M.apply_rewrite_rules("dgcl:145", rules=rules) == []
        assert "irc:401" not in M.apply_rewrite_rules("irc:401", rules=rules)
