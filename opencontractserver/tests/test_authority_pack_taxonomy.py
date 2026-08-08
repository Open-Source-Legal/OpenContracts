"""Pack-declared citation vocabulary: shape rules + abbreviation tables.

A pack carries its jurisdiction's citation vocabulary IN the pack (its
authority-mappings YAML's ``shape_rules`` / ``abbreviations`` sections); the engine
merges them onto the Python baseline at runtime, so the vocabulary travels with the
pack. The shipped baseline always wins a collision (a pack extends, never
overrides). See ``docs/guides/authoring-authority-packs.md``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from opencontractserver.enrichment.constants import classify_prefix
from opencontractserver.enrichment.grammars import GenericCitationExtractor
from opencontractserver.enrichment.services.authority_pack_config import (
    reset_pack_config_cache,
)

_PACK_MAPPINGS = """\
prefixes:
  bo-ley:
    display_name: "Leyes de Bolivia"
    jurisdiction: bo
    authority_type: statute
    aliases: ["ley"]
shape_rules:
  - pattern: '^bo-ley-\\d+$'
    jurisdiction: bo
    authority_type: statute
abbreviations:
  state:
    "Bol. Civ. Code":
      prefix: bo-civ
      jurisdiction: bo
      authority_type: statute
      requires_section_marker: true
"""


class PackTaxonomyExtensionTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(reset_pack_config_cache)

    @staticmethod
    def _write_pack(root: Path) -> Path:
        pack = root / "bolivia-shapes"
        pack.mkdir(parents=True)
        (pack / "pack.yaml").write_text(
            "name: bolivia-shapes\nmappings: m.yaml\n", encoding="utf-8"
        )
        (pack / "m.yaml").write_text(_PACK_MAPPINGS, encoding="utf-8")
        return pack

    def test_pack_shape_rule_classifies_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp))
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_pack_config_cache()
                # A pack shape family classifies without a core edit.
                self.assertEqual(classify_prefix("bo-ley-1234"), ("bo", "statute"))
                # Baseline still wins / works.
                self.assertEqual(classify_prefix("usc-15"), ("us-federal", "statute"))

    def test_shape_rule_absent_without_pack(self):
        with override_settings(AUTHORITY_PACK_PATHS=[]):
            reset_pack_config_cache()
            self.assertEqual(classify_prefix("bo-ley-1234"), (None, None))

    def test_pack_abbreviation_is_matched_by_extractor(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp))
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_pack_config_cache()
                cands = GenericCitationExtractor().extract(
                    "as set out in Bol. Civ. Code § 42 and elsewhere"
                )
                hit = [c for c in cands if c.canonical_key == "bo-civ:42"]
                self.assertTrue(hit, f"pack abbreviation not matched; got {cands}")
                self.assertEqual(hit[0].jurisdiction, "bo")
                self.assertEqual(hit[0].authority_type, "statute")

    def test_pack_abbreviation_can_require_a_locator_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp))
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_pack_config_cache()
                extractor = GenericCitationExtractor()
                section_hit = extractor.extract("Bol. Civ. Code Section 42 applies")
                self.assertTrue(
                    any(
                        candidate.canonical_key == "bo-civ:42"
                        for candidate in section_hit
                    )
                )
                self.assertFalse(
                    extractor.extract("The Bol. Civ. Code 2026 edition is current")
                )

    def test_baseline_abbreviation_still_matched(self):
        # A pack must not displace the shipped baseline tables.
        with override_settings(AUTHORITY_PACK_PATHS=[]):
            reset_pack_config_cache()
            cands = GenericCitationExtractor().extract("see Cal. Corp. Code § 300")
            self.assertTrue(any(c.canonical_key == "ca-corp:300" for c in cands))
