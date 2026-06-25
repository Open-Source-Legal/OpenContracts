"""In-pack authority source-provider discovery.

A self-contained authority pack may ship its own scraper under
``<pack>/providers/*.py``; the pipeline registry discovers it from the pack
directory (in-tree or via the ``AUTHORITY_PACK_PATHS`` setting) so the provider
travels WITH its authority instead of living in core's
``pipeline/authority_source_providers/`` package.

See ``docs/guides/authoring-authority-packs.md``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from opencontractserver.pipeline.registry import (
    get_all_authority_source_providers_cached,
    reset_registry,
)

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
