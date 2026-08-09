"""Tests for `manage.py install_authority_pack` — the registry fetch+install path.

Network-free: every test feeds the command a local registry tarball via
``--tarball`` (the same escape hatch air-gapped installs use). The tarball
mimics a git archive: a single ``<repo>-<ref>/`` top-level directory whose
immediate subdirectories are packs.
"""

import io
import json
import tarfile
import tempfile
from pathlib import Path

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from opencontractserver.corpuses.models import Corpus

User = get_user_model()

PREFIX = "authority-packs-main"


def _minimal_pack() -> dict[str, str]:
    """File map (relative to the pack dir) for the smallest valid v1 pack."""
    manifest = {
        "name": "p",
        "corpora": [{"title": "Registry Pack A", "spec": "a.json"}],
    }
    spec = {
        "sections": [
            {"key": "cpe:1", "heading": "Artículo 1", "text": "Texto del artículo."}
        ]
    }
    return {
        "pack.yaml": yaml.safe_dump(manifest, allow_unicode=True),
        "a.json": json.dumps(spec),
    }


def _build_registry_tarball(
    dest: Path,
    packs: dict[str, dict[str, str]],
    extra_members: list[tarfile.TarInfo] | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Write a git-archive-shaped registry tarball to ``dest``."""
    with tarfile.open(dest, "w:gz") as tar:
        for rel, content in (extra_files or {"README.md": "registry readme"}).items():
            data = content.encode()
            info = tarfile.TarInfo(f"{PREFIX}/{rel}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for pack_name, files in packs.items():
            for rel, content in files.items():
                data = content.encode()
                info = tarfile.TarInfo(f"{PREFIX}/{pack_name}/{rel}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        for member in extra_members or []:
            tar.addfile(member, io.BytesIO(b"x" * member.size))
    return dest


class InstallAuthorityPackCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User.objects.create_user(username="packowner", password="x")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.install_dir = self.tmp / "installed"
        self.tarball = _build_registry_tarball(
            self.tmp / "registry.tar.gz",
            packs={"good_pack": _minimal_pack(), "other_pack": _minimal_pack()},
        )

    def _run(self, *args, **kwargs) -> str:
        out = io.StringIO()
        with override_settings(AUTHORITY_PACK_INSTALL_DIR=str(self.install_dir)):
            call_command(
                "install_authority_pack",
                *args,
                tarball=str(self.tarball),
                stdout=out,
                **kwargs,
            )
        return out.getvalue()

    # ---- listing --------------------------------------------------------

    def test_list_shows_only_pack_directories(self):
        out = self._run(list_packs=True)
        self.assertIn("good_pack", out)
        self.assertIn("other_pack", out)
        self.assertNotIn("README", out)

    # ---- fetch ----------------------------------------------------------

    def test_fetch_only_materialises_without_db_writes(self):
        before = Corpus.objects.count()
        out = self._run("good_pack", fetch_only=True)
        self.assertIn("materialised", out)
        self.assertTrue((self.install_dir / "good_pack" / "pack.yaml").is_file())
        self.assertEqual(Corpus.objects.count(), before)

    def test_refetch_replaces_previous_directory(self):
        self._run("good_pack", fetch_only=True)
        stale = self.install_dir / "good_pack" / "stale.txt"
        stale.write_text("left over from a previous fetch")
        out = self._run("good_pack", fetch_only=True)
        self.assertIn("Replacing previously fetched pack", out)
        self.assertFalse(stale.exists())

    def test_unknown_pack_errors_with_available_names(self):
        with self.assertRaises(CommandError) as ctx:
            self._run("missing_pack", fetch_only=True)
        self.assertIn("good_pack", str(ctx.exception))

    def test_invalid_pack_name_rejected_before_any_io(self):
        with self.assertRaises(CommandError):
            self._run("../evil", fetch_only=True)
        with self.assertRaises(CommandError):
            self._run("Bad.Name", fetch_only=True)

    def test_traversal_member_cannot_escape_staging(self):
        """A hostile ../ member inside the pack subtree must not be written
        outside the staging dir (tarfile's 'data' filter rejects it)."""
        evil = tarfile.TarInfo(f"{PREFIX}/good_pack/../../escape.txt")
        evil.size = 1
        tarball = _build_registry_tarball(
            self.tmp / "evil.tar.gz",
            packs={"good_pack": _minimal_pack()},
            extra_members=[evil],
        )
        self.tarball = tarball
        with self.assertRaises(Exception):
            self._run("good_pack", fetch_only=True)
        self.assertFalse((self.tmp / "escape.txt").exists())
        self.assertFalse((self.install_dir / "escape.txt").exists())

    # ---- install --------------------------------------------------------

    def test_install_creates_corpus_via_load_authority_pack(self):
        out = self._run("good_pack", creator="packowner")
        self.assertTrue(Corpus.objects.filter(title="Registry Pack A").exists())
        self.assertIn("Restart web/worker", out)

    def test_check_preflights_without_db_writes(self):
        before = Corpus.objects.count()
        out = self._run("good_pack", creator="packowner", check=True)
        self.assertEqual(Corpus.objects.count(), before)
        self.assertIn("pack is valid", out)

    def test_install_requires_creator(self):
        with self.assertRaises(CommandError) as ctx:
            self._run("good_pack")
        self.assertIn("--creator", str(ctx.exception))

    def test_missing_pack_yaml_refused(self):
        tarball = _build_registry_tarball(
            self.tmp / "nopack.tar.gz",
            packs={"good_pack": {"README.md": "just a readme, no manifest"}},
        )
        self.tarball = tarball
        with self.assertRaises(CommandError) as ctx:
            self._run("good_pack", fetch_only=True)
        self.assertIn("not found in registry", str(ctx.exception))

    def test_installed_pack_is_discoverable_as_bundle_root(self):
        self._run("good_pack", fetch_only=True)
        from opencontractserver.pipeline.registry import authority_pack_dirs

        with override_settings(AUTHORITY_PACK_INSTALL_DIR=str(self.install_dir)):
            dirs = [p.name for p in authority_pack_dirs()]
        self.assertIn("good_pack", dirs)
