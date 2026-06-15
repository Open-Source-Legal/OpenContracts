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
