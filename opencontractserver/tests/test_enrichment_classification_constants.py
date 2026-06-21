"""Phase-0 classification vocabulary lives in one place (no magic strings)."""

from django.test import SimpleTestCase

from opencontractserver.enrichment import constants as C


class ClassificationConstantsTests(SimpleTestCase):
    def test_authority_types_include_core_regimes(self):
        assert C.AUTHORITY_TYPE_STATUTE == "statute"
        assert C.AUTHORITY_TYPE_REGULATION == "regulation"
        assert C.AUTHORITY_TYPE_MUNICIPAL == "municipal-ordinance"
        assert C.AUTHORITY_TYPE_STATUTE in C.ALL_AUTHORITY_TYPES

    def test_every_static_prefix_is_classified(self):
        prefixes = set(C.AUTHORITY_PREFIX.values()) | {C.SEC_RULE_PREFIX}
        for prefix in prefixes:
            assert prefix in C.PREFIX_CLASSIFICATION, prefix
            assert prefix in C.PREFIX_DISPLAY_NAME, prefix
            jur, typ = C.PREFIX_CLASSIFICATION[prefix]
            assert typ in C.ALL_AUTHORITY_TYPES, (prefix, typ)

    def test_detection_tiers(self):
        assert C.DETECTION_TIER_REGISTRY == "registry"
        assert C.DETECTION_TIER_GRAMMAR == "grammar"
        assert C.DETECTION_TIER_LLM == "llm"

    def test_grammar_statute_meta_prefixes_are_classified(self):
        # ``act`` (an unknown named act), ``publ`` (Public Law), and ``stat``
        # (Statutes at Large) are federal-statute meta-prefixes the grammar
        # emits. classify_prefix must classify them so AuthorityFrontier rows
        # and governance-graph ghost nodes are never left (None, None). They are
        # deliberately NOT in PREFIX_CLASSIFICATION (which seeds AuthorityNamespace
        # rows) — they are catch-alls, not bodies of law.
        for prefix in ("act", "publ", "stat"):
            jur, typ = C.classify_prefix(prefix)
            assert jur == C.JURISDICTION_US_FEDERAL, prefix
            assert typ == C.AUTHORITY_TYPE_STATUTE, prefix
            assert prefix not in C.PREFIX_CLASSIFICATION, prefix

    def test_municipal_grammar_prefixes_are_classified(self):
        # The municipal grammar (issue #1995) emits ``muni`` (bare "Municipal
        # Code § N") and per-city ``muni-<city-slug>`` keys. classify_prefix must
        # recover authority_type=municipal-ordinance for both so a muni key is
        # never stranded at (None, None) type. Jurisdiction stays None — free
        # text yields a city but not its state; table-keyed codes carry the full
        # ``us-ca-san-francisco`` on the candidate instead. Like the state-code
        # prefixes, these are NOT in PREFIX_CLASSIFICATION.
        for prefix in ("muni", "muni-san-francisco", "muni-oakland"):
            jur, typ = C.classify_prefix(prefix)
            assert typ == C.AUTHORITY_TYPE_MUNICIPAL, prefix
            assert jur is None, prefix
            assert prefix not in C.PREFIX_CLASSIFICATION, prefix
