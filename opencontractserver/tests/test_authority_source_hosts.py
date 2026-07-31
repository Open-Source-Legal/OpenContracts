"""Pack-declared SSRF source hosts.

A self-contained scraping pack declares the hosts it fetches from in its
``pack.yaml`` (``source_hosts: [...]``); those are unioned with the hardcoded
``PUBLIC_DOMAIN_SOURCE_HOSTS`` baseline at runtime so the host travels WITH the
pack. Installing the pack (in-tree, or on ``AUTHORITY_PACK_PATHS``) IS the trust
decision. See ``docs/guides/authoring-authority-packs.md``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import yaml
from django.test import SimpleTestCase, override_settings

from opencontractserver.enrichment.data.authority_packs.texas_electric_law.providers.texas_statute_provider import (
    TexasStatuteAuthoritySourceProvider,
)
from opencontractserver.enrichment.services import authority_source_hosts as ash
from opencontractserver.enrichment.services.authority_source_hosts import (
    effective_source_allowlist,
    is_valid_source_host,
    reset_source_hosts_cache,
    source_hosts_for_pack_component,
)
from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
    USCodeAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import host_on_allowlist

_MODULE = "opencontractserver.enrichment.services.authority_source_hosts"


class SourceHostValidationTests(SimpleTestCase):
    def test_accepts_bare_multi_label_hosts(self):
        self.assertTrue(is_valid_source_host("tcpbolivia.bo"))
        self.assertTrue(is_valid_source_host("gacetaoficialdebolivia.gob.bo"))
        self.assertTrue(is_valid_source_host("UScode.House.GOV"))  # normalised

    def test_rejects_non_hosts(self):
        for bad in (
            "",
            "localhost",  # single label
            "https://x.gov",  # scheme
            "x.gov:443",  # port
            "x.gov/path",  # path
            "a b.gov",  # whitespace
            "под.gov",  # non-ascii
        ):
            self.assertFalse(is_valid_source_host(bad), bad)

    def test_component_host_ownership_is_pack_local_and_core_is_unscoped(self):
        self.assertEqual(
            source_hosts_for_pack_component(TexasStatuteAuthoritySourceProvider),
            ("capitol.texas.gov", "legis.texas.gov"),
        )
        self.assertEqual(
            source_hosts_for_pack_component(USCodeAuthoritySourceProvider),
            (),
        )


class PackSourceHostAllowlistTests(SimpleTestCase):
    """No DB needed — the union is read from pack.yaml on disk."""

    def setUp(self):
        # The union is process-cached; restore a clean cache for later tests.
        self.addCleanup(reset_source_hosts_cache)

    @staticmethod
    def _write_pack(root: Path, hosts: list[str]) -> Path:
        pack = root / "scrape-pack"
        pack.mkdir(parents=True)
        (pack / "pack.yaml").write_text(
            yaml.safe_dump({"name": "scrape", "source_hosts": hosts}),
            encoding="utf-8",
        )
        return pack

    def test_installed_pack_widens_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp), ["tcpbolivia.bo"])
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_source_hosts_cache()
                eff = effective_source_allowlist()
                self.assertIn("tcpbolivia.bo", eff)
                self.assertIn("ecfr.gov", eff)  # baseline preserved
                # The dynamic default (provider registered at app startup) makes
                # the pack host pass the allowlist — including subdomains.
                self.assertTrue(host_on_allowlist("tcpbolivia.bo"))
                self.assertTrue(host_on_allowlist("www.tcpbolivia.bo"))

    def test_host_not_allowed_without_pack(self):
        with override_settings(AUTHORITY_PACK_PATHS=[]):
            reset_source_hosts_cache()
            self.assertNotIn("tcpbolivia.bo", effective_source_allowlist())
            self.assertFalse(host_on_allowlist("tcpbolivia.bo"))
            # Baseline still resolves through the dynamic default.
            self.assertTrue(host_on_allowlist("ecfr.gov"))

    def test_malformed_source_hosts_in_manifest_ignored_not_raised(self):
        # A bad host in the union path is logged + skipped (one bad manifest must
        # not break every fetch); the loader is where it fails loudly.
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp), ["https://nope.gov", "tcpbolivia.bo"])
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_source_hosts_cache()
                eff = effective_source_allowlist()
                self.assertIn("tcpbolivia.bo", eff)
                self.assertNotIn("https://nope.gov", eff)


class PackSourceHostManifestSkipTests(SimpleTestCase):
    """Manifest-level fault isolation: an unusable pack is skipped, never raised.

    The discoverable pack set is pinned (``authority_pack_dirs`` patched) so each
    case asserts on exactly the malformed pack — one bad manifest must not break
    the union for every other pack.
    """

    def setUp(self):
        self.addCleanup(reset_source_hosts_cache)

    def _patch_dirs(self, *dirs: Path):
        return mock.patch.object(ash, "authority_pack_dirs", return_value=list(dirs))

    def test_pack_without_manifest_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "no-manifest"
            pack.mkdir()
            with self._patch_dirs(pack):
                reset_source_hosts_cache()
                self.assertEqual(ash.pack_declared_source_hosts(), frozenset())

    def test_pack_with_malformed_manifest_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "bad-manifest"
            pack.mkdir()
            (pack / "pack.yaml").write_text("a: [unterminated", encoding="utf-8")
            with self._patch_dirs(pack):
                reset_source_hosts_cache()
                with self.assertLogs(_MODULE, level="WARNING"):
                    self.assertEqual(ash.pack_declared_source_hosts(), frozenset())

    def test_source_hosts_not_a_list_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "scalar-hosts"
            pack.mkdir()
            # ``source_hosts`` as a bare string (not a list) is a manifest error.
            (pack / "pack.yaml").write_text(
                "name: x\nsource_hosts: tcpbolivia.bo\n", encoding="utf-8"
            )
            with self._patch_dirs(pack):
                reset_source_hosts_cache()
                with self.assertLogs(_MODULE, level="WARNING"):
                    self.assertEqual(ash.pack_declared_source_hosts(), frozenset())
