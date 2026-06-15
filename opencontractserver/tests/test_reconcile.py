"""reconcile() keeps the higher-precedence layer on span overlap."""

from django.test import SimpleTestCase

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import Candidate
from opencontractserver.enrichment.reconcile import reconcile


def _c(start, end, key, tier):
    return Candidate(
        reference_type=C.REF_LAW, start=start, end=end, raw_text=key,
        canonical_key=key, detection_tier=tier,
    )


class ReconcileTests(SimpleTestCase):
    def test_registry_wins_on_overlap(self):
        primary = [_c(0, 50, "exchange-act:10(b)", C.DETECTION_TIER_REGISTRY)]
        secondary = [_c(10, 30, "usc-15:78j(b)", C.DETECTION_TIER_GRAMMAR)]
        out = reconcile(primary, secondary)
        keys = {c.canonical_key for c in out}
        assert keys == {"exchange-act:10(b)"}  # grammar dropped (overlaps registry)

    def test_non_overlapping_grammar_kept(self):
        primary = [_c(0, 10, "dgcl:145", C.DETECTION_TIER_REGISTRY)]
        secondary = [_c(20, 40, "cfr-40:261.4", C.DETECTION_TIER_GRAMMAR)]
        out = reconcile(primary, secondary)
        assert {c.canonical_key for c in out} == {"dgcl:145", "cfr-40:261.4"}

    def test_grammar_self_overlap_first_wins(self):
        primary = []
        secondary = [
            _c(0, 20, "usc-15:78j(b)", C.DETECTION_TIER_GRAMMAR),
            _c(5, 25, "usc-15:78j", C.DETECTION_TIER_GRAMMAR),
        ]
        out = reconcile(primary, secondary)
        assert {c.canonical_key for c in out} == {"usc-15:78j(b)"}

    def test_primary_always_present(self):
        primary = [_c(0, 10, "dgcl:145", C.DETECTION_TIER_REGISTRY)]
        out = reconcile(primary, [])
        assert len(out) == 1
