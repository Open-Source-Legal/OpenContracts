"""In-pack authority source-provider discovery.

A self-contained authority pack may ship its own scraper under
``<pack>/providers/*.py``; the pipeline registry discovers it from the pack
directory (in-tree or via the ``AUTHORITY_PACK_PATHS`` setting) so the provider
travels WITH its authority instead of living in core's
``pipeline/authority_source_providers/`` package. A pack may ALSO ship a
DISCOVERY provider (Phase 2, issue #2054) under ``<pack>/discovery_providers/*.py``
via the same generalized mechanism -- see ``PackDiscoveryProviderDiscoveryTests``
below.

See ``docs/guides/authoring-authority-packs.md``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from opencontractserver.pipeline.registry import (
    authority_pack_dirs,
    get_all_authority_discovery_providers_cached,
    get_all_authority_source_providers_cached,
    reset_registry,
)

_REGISTRY_LOGGER = "opencontractserver.pipeline.registry"

# A minimal, importable provider shipped "inside a pack". Imported by file path
# under a synthetic module name, so its real OpenContracts imports must resolve.
_DEMO_PROVIDER_SRC = """
from typing import ClassVar

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)


class DemoPackProvider(BaseAuthoritySourceProvider):
    title = "Demo Pack Provider"
    supported_prefixes: ClassVar[tuple[str, ...]] = ("demo-1",)

    def _locate_impl(self, canonical_key, **kw):
        return AuthorityRequest(
            canonical_key=canonical_key, url="https://example.gov/x"
        )

    def _fetch_impl(self, request, **kw):
        return [AuthoritySection(key=request.canonical_key, heading="H", text="T")]
"""


class PackProviderDiscoveryTests(SimpleTestCase):
    """Registry-level discovery; no DB needed."""

    def setUp(self):
        # Always restore a clean registry for subsequent tests on this worker,
        # regardless of how this test exits.
        self.addCleanup(reset_registry)

    @staticmethod
    def _write_pack(root: Path) -> Path:
        pack = root / "demo-pack"
        providers = pack / "providers"
        providers.mkdir(parents=True)
        (providers / "demo_provider.py").write_text(
            _DEMO_PROVIDER_SRC, encoding="utf-8"
        )
        # A leading-underscore module must be skipped (private/helper convention).
        (providers / "_helper.py").write_text("X = 1\n", encoding="utf-8")
        return pack

    def test_in_pack_provider_is_discovered_and_routable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp))
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_registry()
                provs = get_all_authority_source_providers_cached()
                by_name = {p.name: p for p in provs}
                self.assertIn("DemoPackProvider", by_name)
                # The provider routes its declared prefix family.
                provider_cls = by_name["DemoPackProvider"].component_class
                assert provider_cls is not None
                provider = provider_cls()
                self.assertTrue(provider.can_handle("demo-1:1"))
                self.assertFalse(provider.can_handle("usc-15:78j"))

    def test_provider_absent_without_pack_path(self):
        # Sanity: without the pack on AUTHORITY_PACK_PATHS the demo provider is
        # not registered (the discovery is driven by the setting, not leakage).
        with override_settings(AUTHORITY_PACK_PATHS=[]):
            reset_registry()
            names = {p.name for p in get_all_authority_source_providers_cached()}
            self.assertNotIn("DemoPackProvider", names)
            # The shipped core providers are still discovered.
            self.assertIn("CFRAuthoritySourceProvider", names)

    def test_broken_pack_provider_is_logged_and_skipped(self):
        # A provider module that fails to import must be logged + skipped without
        # breaking discovery of the pack's other (valid) providers — one bad file
        # never crashes registry build.
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp))
            (pack / "providers" / "broken.py").write_text(
                "raise RuntimeError('boom in pack provider')\n", encoding="utf-8"
            )
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_registry()
                with self.assertLogs(_REGISTRY_LOGGER, level="WARNING") as cm:
                    names = {
                        p.name for p in get_all_authority_source_providers_cached()
                    }
            # The valid sibling still loads despite the broken module.
            self.assertIn("DemoPackProvider", names)
            self.assertTrue(
                any("Failed to import pack provider" in m for m in cm.output),
                cm.output,
            )

    def test_duplicate_provider_prefix_is_warned(self):
        # Two providers claiming the same supported_prefixes family resolve
        # non-deterministically; the registry makes the shadowing install loud.
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp))
            dup_src = _DEMO_PROVIDER_SRC.replace("DemoPackProvider", "DupPackProvider")
            (pack / "providers" / "dup_provider.py").write_text(
                dup_src, encoding="utf-8"
            )
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_registry()
                with self.assertLogs(_REGISTRY_LOGGER, level="WARNING") as cm:
                    get_all_authority_source_providers_cached()
            self.assertTrue(
                any(
                    "Duplicate authority-source-provider prefix" in m for m in cm.output
                ),
                cm.output,
            )


# A minimal, importable discovery provider shipped "inside a pack" (Phase 2,
# issue #2054). Same file-path-import convention as _DEMO_PROVIDER_SRC above.
_DEMO_DISCOVERY_PROVIDER_SRC = """
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)


class DemoPackDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "Demo Pack Discovery Provider"

    def _fetch_index_impl(self, index_url, **kw):
        return "<html></html>"

    def _parse_index_impl(self, html, *, index_url, **kw):
        return [DiscoveryCandidate(canonical_key="demo-pack:1", url=index_url)]
"""


class PackDiscoveryProviderDiscoveryTests(SimpleTestCase):
    """Registry-level discovery for BaseAuthorityDiscoveryProvider; no DB needed."""

    def setUp(self):
        self.addCleanup(reset_registry)

    @staticmethod
    def _write_pack(root: Path) -> Path:
        pack = root / "demo-discovery-pack"
        discovery_providers = pack / "discovery_providers"
        discovery_providers.mkdir(parents=True)
        (discovery_providers / "demo_discovery_provider.py").write_text(
            _DEMO_DISCOVERY_PROVIDER_SRC, encoding="utf-8"
        )
        (discovery_providers / "_helper.py").write_text("X = 1\n", encoding="utf-8")
        return pack

    def test_in_pack_discovery_provider_is_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp))
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_registry()
                provs = get_all_authority_discovery_providers_cached()
                by_name = {p.name: p for p in provs}
                self.assertIn("DemoPackDiscoveryProvider", by_name)
                provider_cls = by_name["DemoPackDiscoveryProvider"].component_class
                assert provider_cls is not None
                candidates = provider_cls()._parse_index_impl(
                    "<html></html>", index_url="https://x/1"
                )
                self.assertEqual(candidates[0].canonical_key, "demo-pack:1")

    def test_provider_absent_without_pack_path(self):
        with override_settings(AUTHORITY_PACK_PATHS=[]):
            reset_registry()
            names = {p.name for p in get_all_authority_discovery_providers_cached()}
            self.assertNotIn("DemoPackDiscoveryProvider", names)
            # The shipped core reference provider is still discovered.
            self.assertIn("ListingIndexDiscoveryProvider", names)

    def test_broken_pack_discovery_provider_is_logged_and_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self._write_pack(Path(tmp))
            (pack / "discovery_providers" / "broken.py").write_text(
                "raise RuntimeError('boom in pack discovery provider')\n",
                encoding="utf-8",
            )
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_registry()
                with self.assertLogs(_REGISTRY_LOGGER, level="WARNING") as cm:
                    names = {
                        p.name for p in get_all_authority_discovery_providers_cached()
                    }
            self.assertIn("DemoPackDiscoveryProvider", names)
            self.assertTrue(
                any("Failed to import pack provider" in m for m in cm.output),
                cm.output,
            )

    def test_source_provider_pack_and_discovery_provider_pack_do_not_collide(self):
        """A pack shipping BOTH <pack>/providers/ and <pack>/discovery_providers/
        must register both without either shadowing the other (module_ns
        disambiguates the synthetic import namespace)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = root / "dual-pack"
            providers_dir = pack / "providers"
            providers_dir.mkdir(parents=True)
            (providers_dir / "source_provider.py").write_text(
                _DEMO_PROVIDER_SRC, encoding="utf-8"
            )
            discovery_dir = pack / "discovery_providers"
            discovery_dir.mkdir(parents=True)
            (discovery_dir / "discovery_provider.py").write_text(
                _DEMO_DISCOVERY_PROVIDER_SRC, encoding="utf-8"
            )
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_registry()
                source_names = {
                    p.name for p in get_all_authority_source_providers_cached()
                }
                discovery_names = {
                    p.name for p in get_all_authority_discovery_providers_cached()
                }
        self.assertIn("DemoPackProvider", source_names)
        self.assertIn("DemoPackDiscoveryProvider", discovery_names)
        self.assertNotIn("DemoPackDiscoveryProvider", source_names)
        self.assertNotIn("DemoPackProvider", discovery_names)


class AuthorityPackDirsTests(SimpleTestCase):
    """``authority_pack_dirs`` never raises on a misconfigured setting entry."""

    def setUp(self):
        self.addCleanup(reset_registry)

    def test_non_directory_path_entry_is_warned_and_skipped(self):
        with override_settings(AUTHORITY_PACK_PATHS=["/no/such/authority/pack/dir"]):
            with self.assertLogs(_REGISTRY_LOGGER, level="WARNING") as cm:
                dirs = authority_pack_dirs()
            self.assertTrue(
                any("is not a directory" in m for m in cm.output), cm.output
            )
            self.assertNotIn(Path("/no/such/authority/pack/dir"), dirs)


# A pack whose provider imports a helper module at the pack root. This is the
# shape that only works when the registry creates the pack's parent packages —
# an in-tree pack could reach its own helper by absolute dotted path, and a
# sideloaded copy of that same pack could not.
_SIBLING_HELPER_SRC = """
CLASSIFICATION = "sibling-resolved"
"""

_SIBLING_PROVIDER_SRC = """
from typing import ClassVar

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

from ..pack_helper import CLASSIFICATION


class SiblingImportProvider(BaseAuthoritySourceProvider):
    title = "Sibling Import Provider"
    supported_prefixes: ClassVar[tuple[str, ...]] = ("sibling-1",)
    classification: ClassVar[str] = CLASSIFICATION

    def _locate_impl(self, canonical_key, **kw):
        return AuthorityRequest(
            canonical_key=canonical_key, url="https://example.gov/x"
        )

    def _fetch_impl(self, request, **kw):
        return [AuthoritySection(key=request.canonical_key, heading="H", text="T")]
"""


class PackSiblingImportTests(SimpleTestCase):
    """A pack must be able to import its OWN modules, wherever it is mounted."""

    def setUp(self):
        self.addCleanup(reset_registry)

    def test_provider_can_import_a_helper_at_the_pack_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "sibling-pack"
            providers = pack / "providers"
            providers.mkdir(parents=True)
            (pack / "pack.yaml").write_text("name: sibling_pack\n", encoding="utf-8")
            (pack / "pack_helper.py").write_text(_SIBLING_HELPER_SRC, encoding="utf-8")
            (providers / "sibling_provider.py").write_text(
                _SIBLING_PROVIDER_SRC, encoding="utf-8"
            )
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_registry()
                by_name = {
                    definition.name: definition
                    for definition in get_all_authority_source_providers_cached()
                }
                self.assertIn(
                    "SiblingImportProvider",
                    by_name,
                    "a pack provider importing a pack-root helper failed to load",
                )
                provider_cls = by_name["SiblingImportProvider"].component_class
                assert provider_cls is not None
                self.assertEqual(
                    getattr(provider_cls, "classification"),
                    "sibling-resolved",
                )

    def test_same_pack_name_from_a_new_directory_reloads_its_helper(self):
        """A re-mounted pack name must run the NEW directory's code.

        The synthetic parent package is keyed by pack name, and an import
        resolves against ``sys.modules`` before it consults that package's
        ``__path__`` — so without dropping the cached submodules, remounting the
        same pack name from a different directory hands back the previous
        directory's helper and the pack silently runs code it does not contain.
        """
        self.addCleanup(reset_registry)
        for value in ("first", "second"):
            with tempfile.TemporaryDirectory() as tmp:
                pack = Path(tmp) / "remounted-pack"
                (pack / "providers").mkdir(parents=True)
                (pack / "pack.yaml").write_text(
                    "name: remounted_pack\n", encoding="utf-8"
                )
                (pack / "pack_helper.py").write_text(
                    f'CLASSIFICATION = "{value}"\n', encoding="utf-8"
                )
                (pack / "providers" / "sibling_provider.py").write_text(
                    _SIBLING_PROVIDER_SRC, encoding="utf-8"
                )
                with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                    reset_registry()
                    by_name = {
                        definition.name: definition
                        for definition in (get_all_authority_source_providers_cached())
                    }
                    provider_cls = by_name["SiblingImportProvider"].component_class
                    assert provider_cls is not None
                    self.assertEqual(
                        getattr(provider_cls, "classification"),
                        value,
                        "a remounted pack name served a stale helper module",
                    )

    def test_both_component_families_share_one_helper_module_object(self):
        """One pack, one helper module — not one copy per component family.

        The families are discovered in separate passes; if each built its own
        parent package the helper would be imported twice, and any state or
        identity it carries would silently diverge between a pack's source and
        discovery providers.
        """
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "shared-helper-pack"
            (pack / "providers").mkdir(parents=True)
            (pack / "discovery_providers").mkdir(parents=True)
            (pack / "pack.yaml").write_text("name: shared_pack\n", encoding="utf-8")
            (pack / "pack_helper.py").write_text(_SIBLING_HELPER_SRC, encoding="utf-8")
            (pack / "providers" / "sibling_provider.py").write_text(
                _SIBLING_PROVIDER_SRC, encoding="utf-8"
            )
            with override_settings(AUTHORITY_PACK_PATHS=[str(pack)]):
                reset_registry()
                get_all_authority_source_providers_cached()
                get_all_authority_discovery_providers_cached()
                helper_modules = [
                    name
                    for name in sys.modules
                    if name.endswith(".pack_helper") and "shared-helper-pack" in name
                ]
        self.assertEqual(
            helper_modules,
            ["_authority_pack.shared-helper-pack.pack_helper"],
            "the pack's helper must resolve to exactly one module object",
        )
