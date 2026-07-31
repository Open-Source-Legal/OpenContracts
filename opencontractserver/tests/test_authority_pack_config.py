"""Validation + fault-isolation of pack-declared citation vocabulary.

``enrichment/services/authority_pack_config.py`` reads each installed pack's
authority-mappings YAML and merges its ``shape_rules`` / ``abbreviations`` onto
the Python baseline. The happy path (a well-formed pack actually changing
classification / extraction) is covered by ``test_authority_pack_taxonomy``; this
module pins the *defensive* contract:

* the fail-fast validators (``iter_shape_rules`` / ``iter_abbreviations``) raise
  ``ValueError`` on every malformed shape so ``load_authority_pack`` aborts a bad
  install loudly, and
* the runtime scan (``pack_declared_shape_rules`` / ``pack_declared_abbreviations``
  / ``iter_pack_mapping_files`` / ``_load_yaml``) downgrades those raises to
  log-and-skip so a single broken pack can never break extraction for every
  jurisdiction.

No database required — the config is read from pack files on disk.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from opencontractserver.enrichment.services import authority_pack_config as apc

_MODULE = "opencontractserver.enrichment.services.authority_pack_config"

# A reliably-unparseable YAML document (unterminated flow sequence).
_BAD_YAML = "name: oops\nsource: [unterminated"


class IterShapeRulesValidationTests(SimpleTestCase):
    """``iter_shape_rules`` — every malformed shape raises ``ValueError``."""

    def test_none_returns_empty(self):
        self.assertEqual(apc.iter_shape_rules({}), [])
        self.assertEqual(apc.iter_shape_rules({"shape_rules": None}), [])

    def test_not_a_list_raises(self):
        with self.assertRaisesMessage(ValueError, "must be a list"):
            apc.iter_shape_rules({"shape_rules": {"pattern": "^x$"}})

    def test_entry_without_pattern_raises(self):
        with self.assertRaisesMessage(ValueError, "needs a 'pattern'"):
            apc.iter_shape_rules({"shape_rules": [{"jurisdiction": "bo"}]})

    def test_uncompilable_pattern_raises(self):
        with self.assertRaisesMessage(ValueError, "bad regex"):
            apc.iter_shape_rules({"shape_rules": [{"pattern": "([unclosed"}]})

    def test_unknown_authority_type_raises(self):
        with self.assertRaisesMessage(ValueError, "not in "):
            apc.iter_shape_rules(
                {
                    "shape_rules": [
                        {"pattern": "^bo-ley-\\d+$", "authority_type": "not_a_type"}
                    ]
                }
            )

    def test_valid_entry_normalised(self):
        out = apc.iter_shape_rules(
            {"shape_rules": [{"pattern": "^bo-ley-\\d+$", "authority_type": "statute"}]}
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["authority_type"], "statute")
        self.assertIsNone(out[0]["jurisdiction"])  # absent -> None


class IterAbbreviationsValidationTests(SimpleTestCase):
    """``iter_abbreviations`` — every malformed shape raises ``ValueError``."""

    def test_none_returns_empty_groups(self):
        self.assertEqual(apc.iter_abbreviations({}), {"state": {}, "municipal": {}})

    def test_not_a_mapping_raises(self):
        with self.assertRaisesMessage(ValueError, "must be a mapping"):
            apc.iter_abbreviations({"abbreviations": ["nope"]})

    def test_group_not_a_mapping_raises(self):
        with self.assertRaisesMessage(ValueError, "must be a mapping"):
            apc.iter_abbreviations({"abbreviations": {"state": ["nope"]}})

    def test_entry_without_prefix_raises(self):
        with self.assertRaisesMessage(ValueError, "needs 'prefix'"):
            apc.iter_abbreviations(
                {"abbreviations": {"state": {"Bol. Civ. Code": {"jurisdiction": "bo"}}}}
            )

    def test_unknown_authority_type_raises(self):
        with self.assertRaisesMessage(ValueError, "not in "):
            apc.iter_abbreviations(
                {
                    "abbreviations": {
                        "state": {
                            "Bol. Civ. Code": {
                                "prefix": "bo-civ",
                                "authority_type": "not_a_type",
                            }
                        }
                    }
                }
            )

    def test_valid_entry_normalised(self):
        out = apc.iter_abbreviations(
            {
                "abbreviations": {
                    "municipal": {
                        "Some Ord.": {
                            "prefix": "bo-ord",
                            "authority_type": "statute",
                            "requires_section_marker": True,
                        }
                    }
                }
            }
        )
        self.assertEqual(out["municipal"]["Some Ord."]["prefix"], "bo-ord")
        self.assertTrue(out["municipal"]["Some Ord."]["requires_section_marker"])
        self.assertEqual(out["state"], {})

    def test_section_marker_flag_must_be_boolean(self):
        with self.assertRaisesMessage(ValueError, "must be true or false"):
            apc.iter_abbreviations(
                {
                    "abbreviations": {
                        "state": {
                            "Bol. Civ. Code": {
                                "prefix": "bo-civ",
                                "requires_section_marker": "yes",
                            }
                        }
                    }
                }
            )


class LoadYamlTests(SimpleTestCase):
    """``_load_yaml`` never raises — bad / non-mapping YAML degrades to ``{}``."""

    def test_malformed_yaml_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.yaml"
            path.write_text(_BAD_YAML, encoding="utf-8")
            self.assertEqual(apc._load_yaml(path), {})

    def test_non_mapping_yaml_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.yaml"
            path.write_text("- just\n- a\n- list\n", encoding="utf-8")
            self.assertEqual(apc._load_yaml(path), {})

    def test_validate_pack_taxonomy_extensions_passes_for_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.yaml"
            path.write_text(
                "shape_rules:\n  - pattern: '^bo-ley-\\d+$'\n", encoding="utf-8"
            )
            # Should not raise.
            apc.validate_pack_taxonomy_extensions(path)


class IterPackMappingFilesSkipTests(SimpleTestCase):
    """``iter_pack_mapping_files`` skips packs it cannot use, never raises."""

    def _patch_dirs(self, *dirs: Path):
        return mock.patch.object(apc, "authority_pack_dirs", return_value=list(dirs))

    def test_pack_without_manifest_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "no-manifest"
            pack.mkdir()
            with self._patch_dirs(pack):
                self.assertEqual(list(apc.iter_pack_mapping_files()), [])

    def test_pack_with_malformed_manifest_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "bad-manifest"
            pack.mkdir()
            (pack / "pack.yaml").write_text(_BAD_YAML, encoding="utf-8")
            with self._patch_dirs(pack):
                with self.assertLogs(_MODULE, level="WARNING"):
                    self.assertEqual(list(apc.iter_pack_mapping_files()), [])

    def test_pack_without_mappings_key_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "no-mappings"
            pack.mkdir()
            (pack / "pack.yaml").write_text("name: x\n", encoding="utf-8")
            with self._patch_dirs(pack):
                errors: list = []
                self.assertEqual(list(apc.iter_pack_mapping_files(errors)), [])
            # Content-only pack: skipped by design, NOT an error.
            self.assertEqual(errors, [])

    def test_declared_but_missing_mappings_file_is_skipped_and_reported(self):
        # `mappings: typo.yaml` with no such file is the classic authoring
        # mistake: the pack must be skipped with a warning AND land in the
        # errors sink so load_installed can surface it — not vanish silently.
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "typo-mappings"
            pack.mkdir()
            (pack / "pack.yaml").write_text(
                "name: x\nmappings: typo.yaml\n", encoding="utf-8"
            )
            with self._patch_dirs(pack):
                errors: list = []
                with self.assertLogs(_MODULE, level="WARNING"):
                    self.assertEqual(list(apc.iter_pack_mapping_files(errors)), [])
        self.assertEqual(len(errors), 1)
        self.assertIn("not found", errors[0][1])

    def test_well_formed_pack_is_yielded(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "ok"
            pack.mkdir()
            (pack / "pack.yaml").write_text(
                "name: x\nmappings: m.yaml\n", encoding="utf-8"
            )
            (pack / "m.yaml").write_text("shape_rules: []\n", encoding="utf-8")
            with self._patch_dirs(pack):
                yielded = list(apc.iter_pack_mapping_files())
            self.assertEqual([p for p, _, _ in yielded], [pack])
            # The parsed manifest rides along so callers (e.g. load_installed
            # deriving the pack's baseline origin) never re-read pack.yaml.
            self.assertEqual(yielded[0][2].get("name"), "x")


class RuntimeScanFaultIsolationTests(SimpleTestCase):
    """A pack whose mappings are malformed is logged + skipped, not raised."""

    def setUp(self):
        self.addCleanup(apc.reset_pack_config_cache)

    def _patch_dirs(self, *dirs: Path):
        return mock.patch.object(apc, "authority_pack_dirs", return_value=list(dirs))

    @staticmethod
    def _write_pack(root: Path, mappings_body: str) -> Path:
        pack = root / "broken-vocab"
        pack.mkdir()
        (pack / "pack.yaml").write_text("name: x\nmappings: m.yaml\n", encoding="utf-8")
        (pack / "m.yaml").write_text(mappings_body, encoding="utf-8")
        return pack

    def test_malformed_shape_rules_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            # shape_rules is a string, not a list -> iter_shape_rules raises;
            # the scan must downgrade to a logged skip and return no rules.
            pack = self._write_pack(Path(tmp), "shape_rules: not-a-list\n")
            with self._patch_dirs(pack):
                apc.reset_pack_config_cache()
                with self.assertLogs(_MODULE, level="WARNING"):
                    rules = apc.pack_declared_shape_rules()
            self.assertEqual(rules, ())

    def test_malformed_abbreviations_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp), "abbreviations: not-a-mapping\n")
            with self._patch_dirs(pack):
                apc.reset_pack_config_cache()
                with self.assertLogs(_MODULE, level="WARNING"):
                    state, municipal = apc.pack_declared_abbreviations()
            self.assertEqual((state, municipal), ({}, {}))
