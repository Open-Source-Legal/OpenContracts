"""Declining to execute a pack's code, and the supported way to reuse a core provider.

Installing an authority pack that ships ``<pack>/providers/*.py`` IMPORTS that
Python into the web and worker processes. Extraction already refuses path
traversal and setuid bits (``tar.extract(..., filter="data")``); it cannot
refuse code. That is a materially larger blast radius than ``source_hosts``,
where "installing the pack is the trust decision" holds because the consequence
is bounded to which hosts may be fetched.

``AUTHORITY_PACK_LOAD_PROVIDERS`` lets an operator decline. It is safe to
decline because the pack contract (authority-packs ``SOURCE_PROVIDERS.md``,
clause P5) requires a pack to install and serve its sections with ``providers/``
deleted — so turning it off costs re-fetch and nothing else.

The tests below use a provider module that writes a sentinel **at import time**.
That is exactly what a pack MUST NOT do (clause P4), which is what makes it a
good probe here: if the sentinel appears, the module was imported, and no
assertion about registration can be fooled by a provider that merely failed to
register.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from opencontractserver.pipeline.registry import (
    get_all_authority_source_providers_cached,
    get_authority_source_provider,
    pack_provider_modules,
    reset_registry,
)

_REGISTRY_LOGGER = "opencontractserver.pipeline.registry"

# Writes a file when imported, so "was this module executed?" is answerable
# independently of whether its class ended up registered.
_PROVIDER_SRC = '''
from pathlib import Path

from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

Path(__file__).with_name("IMPORTED.sentinel").write_text("yes")


class TrustProbeSourceProvider(BaseAuthoritySourceProvider):
    title = "Trust Probe"
    description = "Fixture provider for AUTHORITY_PACK_LOAD_PROVIDERS tests."
    author = "test"
    supported_prefixes = ("trustprobe",)

    def can_handle(self, canonical_key: str) -> bool:
        return canonical_key.split(":", 1)[0] == "trustprobe"

    def _locate_impl(self, canonical_key, **kwargs):
        return AuthorityRequest(url="https://example.invalid/x")

    def _fetch_impl(self, request, **kwargs):
        raise NotImplementedError
'''


class _PackFixture(SimpleTestCase):
    """Builds a throwaway pack dir containing one provider module."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pack_dir = Path(self._tmp.name) / "trustprobe_pack"
        providers = self.pack_dir / "providers"
        providers.mkdir(parents=True)
        (providers / "trust_probe_provider.py").write_text(_PROVIDER_SRC)
        self.sentinel = providers / "IMPORTED.sentinel"
        reset_registry()
        self.addCleanup(reset_registry)

    def _class_names(self) -> set[str]:
        # ``class_name`` is the full dotted path; compare on the leaf so the
        # assertions read as the class a pack author actually writes.
        return {
            d.class_name.rsplit(".", 1)[-1]
            for d in get_all_authority_source_providers_cached()
        }


class LoadProvidersSettingTests(_PackFixture):
    def test_providers_load_by_default(self) -> None:
        """The default must not change: existing installs keep working."""
        with override_settings(
            AUTHORITY_PACK_PATHS=[str(self.pack_dir)],
            AUTHORITY_PACK_LOAD_PROVIDERS=True,
        ):
            names = self._class_names()

        self.assertIn("TrustProbeSourceProvider", names)
        self.assertTrue(
            self.sentinel.exists(), "fixture never imported; the test proves nothing"
        )

    def test_providers_are_not_imported_when_disabled(self) -> None:
        """Not merely unregistered — NOT EXECUTED."""
        with override_settings(
            AUTHORITY_PACK_PATHS=[str(self.pack_dir)],
            AUTHORITY_PACK_LOAD_PROVIDERS=False,
        ):
            names = self._class_names()

        self.assertNotIn("TrustProbeSourceProvider", names)
        self.assertFalse(
            self.sentinel.exists(),
            "the pack's module was IMPORTED despite AUTHORITY_PACK_LOAD_PROVIDERS "
            "being off — the setting gates registration but not execution, which "
            "is the only thing it was for",
        )

    def test_skipping_is_reported_with_a_count(self) -> None:
        """Silence would make 'turned off' and 'no packs installed' identical."""
        with override_settings(
            AUTHORITY_PACK_PATHS=[str(self.pack_dir)],
            AUTHORITY_PACK_LOAD_PROVIDERS=False,
        ):
            with self.assertLogs(_REGISTRY_LOGGER, level="INFO") as captured:
                self._class_names()

        messages = "\n".join(captured.output)
        self.assertIn("AUTHORITY_PACK_LOAD_PROVIDERS is off", messages)
        self.assertIn("trust_probe_provider.py", messages)

    def test_core_providers_survive_the_setting(self) -> None:
        """Only IN-PACK loading is declined; core providers are unaffected."""
        with override_settings(
            AUTHORITY_PACK_PATHS=[str(self.pack_dir)],
            AUTHORITY_PACK_LOAD_PROVIDERS=False,
        ):
            names = self._class_names()

        self.assertIn("CFRAuthoritySourceProvider", names)


class PackProviderModulesTests(_PackFixture):
    def test_lists_shipped_modules_without_importing_them(self) -> None:
        """The listing that --check and the skip log both depend on."""
        with override_settings(AUTHORITY_PACK_PATHS=[str(self.pack_dir)]):
            found = pack_provider_modules("providers")

        self.assertEqual([p.name for p in found], ["trust_probe_provider.py"])
        self.assertFalse(
            self.sentinel.exists(), "listing the modules executed one of them"
        )


class DelegationSeamTests(SimpleTestCase):
    """``get_authority_source_provider`` is the seam in-pack providers delegate through."""

    def setUp(self) -> None:
        reset_registry()
        self.addCleanup(reset_registry)

    def test_returns_a_usable_core_provider_instance(self) -> None:
        provider = get_authority_source_provider("CFRAuthoritySourceProvider")

        self.assertIsNotNone(provider)
        # The thing a delegating pack provider actually needs: routing plus a
        # pure locate it can hand a translated key to.
        self.assertTrue(provider.can_handle("cfr-22:120.4"))
        self.assertFalse(provider.can_handle("itar:120.4"))

    def test_unknown_provider_returns_none_rather_than_raising(self) -> None:
        """A pack must be able to decline, not crash registry build."""
        self.assertIsNone(get_authority_source_provider("NoSuchProviderClass"))
