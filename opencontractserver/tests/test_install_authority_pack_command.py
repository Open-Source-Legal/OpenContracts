"""Tests for `manage.py install_authority_pack` — the registry fetch+install path.

Network-free: every test feeds the command a local registry tarball via
``--tarball`` (the same escape hatch air-gapped installs use). The tarball
mimics a git archive: a single ``<repo>-<ref>/`` top-level directory whose
immediate subdirectories are packs.
"""

import io
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from unittest import mock

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from opencontractserver.corpuses.management.commands import (
    install_authority_pack as cmd_module,
)
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

    def test_list_with_no_packs_says_so(self):
        self.tarball = _build_registry_tarball(self.tmp / "empty.tar.gz", packs={})
        out = self._run(list_packs=True)
        self.assertIn("No packs found", out)

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

    def test_requires_pack_name_or_list(self):
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn("pack name", str(ctx.exception))

    def test_missing_local_tarball_errors(self):
        self.tarball = self.tmp / "nope.tar.gz"
        with self.assertRaises(CommandError) as ctx:
            self._run("good_pack", fetch_only=True)
        self.assertIn("--tarball not found", str(ctx.exception))

    def test_multiple_top_level_roots_rejected(self):
        stray = tarfile.TarInfo("otherroot/file.txt")
        stray.size = 1
        self.tarball = _build_registry_tarball(
            self.tmp / "tworoots.tar.gz",
            packs={"good_pack": _minimal_pack()},
            extra_members=[stray],
        )
        with self.assertRaises(CommandError) as ctx:
            self._run("good_pack", fetch_only=True)
        self.assertIn("Unexpected tarball layout", str(ctx.exception))

    def test_network_fetch_builds_registry_url(self):
        """Without --tarball the command derives the archive URL from
        --repo/--ref and streams it via _download_tarball (mocked here)."""

        def fake_download(url, dest):
            shutil.copyfile(self.tarball, dest)

        out = io.StringIO()
        with override_settings(AUTHORITY_PACK_INSTALL_DIR=str(self.install_dir)):
            with mock.patch.object(
                cmd_module, "_download_tarball", side_effect=fake_download
            ) as download:
                call_command(
                    "install_authority_pack",
                    "good_pack",
                    fetch_only=True,
                    repo="https://example.test/registry/",
                    ref="v1.2",
                    stdout=out,
                )
        download.assert_called_once()
        expected_url = "https://example.test/registry/archive/v1.2.tar.gz"
        self.assertEqual(download.call_args.args[0], expected_url)
        self.assertIn(f"Fetching {expected_url}", out.getvalue())
        self.assertTrue((self.install_dir / "good_pack" / "pack.yaml").is_file())

    def test_extraction_size_cap_refuses_oversized_pack(self):
        with mock.patch.object(cmd_module, "MAX_EXTRACTED_BYTES", 8):
            with self.assertRaises(CommandError) as ctx:
                self._run("good_pack", fetch_only=True)
        self.assertIn("expands past", str(ctx.exception))
        self.assertFalse((self.install_dir / "good_pack").exists())

    def test_directory_typed_pack_yaml_refused(self):
        """A pack.yaml *directory* member gets the pack listed but must fail
        the post-extraction is_file() check rather than install."""
        bogus = tarfile.TarInfo(f"{PREFIX}/dir_pack/pack.yaml")
        bogus.type = tarfile.DIRTYPE
        self.tarball = _build_registry_tarball(
            self.tmp / "dirpack.tar.gz",
            packs={},
            extra_members=[bogus],
        )
        with self.assertRaises(CommandError) as ctx:
            self._run("dir_pack", fetch_only=True)
        self.assertIn("missing pack.yaml", str(ctx.exception))

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

    # ---- pre-install provider report -------------------------------------
    # `_report_pack_providers` — the code surface an operator sees before
    # any DB write. `--check` exercises it without installing.

    def test_pack_with_no_providers_gets_no_report(self):
        out = self._run("good_pack", creator="packowner", check=True)
        self.assertNotIn("provider module", out)

    def test_reports_shipped_provider_modules_and_manifest_declaration(self):
        manifest = {
            "name": "p",
            "corpora": [{"title": "Registry Pack A", "spec": "a.json"}],
            "providers": [
                {
                    "class": "DelegatingProvider",
                    "supported_prefixes": ["itar"],
                    "delegates_to": "CFRAuthoritySourceProvider",
                }
            ],
        }
        pack = _minimal_pack()
        pack["pack.yaml"] = yaml.safe_dump(manifest, allow_unicode=True)
        pack["providers/delegating_provider.py"] = "# stub, never imported by --check"
        self.tarball = _build_registry_tarball(
            self.tmp / "withprovider.tar.gz", packs={"provider_pack": pack}
        )

        out = self._run("provider_pack", creator="packowner", check=True)

        self.assertIn("ships 1 provider module(s)", out)
        self.assertIn("providers/delegating_provider.py", out)
        self.assertIn("declares: DelegatingProvider", out)
        self.assertIn("prefixes=['itar']", out)
        self.assertIn("delegates_to=CFRAuthoritySourceProvider", out)
        self.assertNotIn("AUTHORITY_PACK_LOAD_PROVIDERS is off", out)

    def test_reports_when_load_providers_disabled(self):
        pack = _minimal_pack()
        pack["providers/delegating_provider.py"] = "# stub, never imported by --check"
        self.tarball = _build_registry_tarball(
            self.tmp / "withprovider.tar.gz", packs={"provider_pack": pack}
        )

        with override_settings(AUTHORITY_PACK_LOAD_PROVIDERS=False):
            out = self._run("provider_pack", creator="packowner", check=True)

        self.assertIn(
            "AUTHORITY_PACK_LOAD_PROVIDERS is off — these will NOT be imported", out
        )


class DownloadTarballTests(SimpleTestCase):
    """Direct tests for the network fetch helper, with `requests` mocked."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name) / "out.tar.gz"

    @staticmethod
    def _mock_get(status_code: int = 200, chunks: tuple[bytes, ...] = ()):
        """A stand-in for requests.get usable as a context manager."""
        resp = mock.MagicMock()
        resp.status_code = status_code
        resp.iter_content.return_value = list(chunks)
        get = mock.MagicMock()
        get.return_value.__enter__.return_value = resp
        return get

    def test_rejects_non_http_scheme(self):
        with self.assertRaises(CommandError) as ctx:
            cmd_module._download_tarball("ftp://registry/main.tar.gz", self.dest)
        self.assertIn("http(s)", str(ctx.exception))
        self.assertFalse(self.dest.exists())

    def test_non_200_response_raises(self):
        with mock.patch("requests.get", self._mock_get(status_code=404)):
            with self.assertRaises(CommandError) as ctx:
                cmd_module._download_tarball("https://r/a.tar.gz", self.dest)
        self.assertIn("HTTP 404", str(ctx.exception))

    def test_streams_body_to_dest(self):
        with mock.patch("requests.get", self._mock_get(chunks=(b"abc", b"def"))):
            cmd_module._download_tarball("https://r/a.tar.gz", self.dest)
        self.assertEqual(self.dest.read_bytes(), b"abcdef")

    def test_size_cap_trips_mid_stream_before_writing_overflow_chunk(self):
        with mock.patch.object(cmd_module, "MAX_TARBALL_BYTES", 4), mock.patch(
            "requests.get", self._mock_get(chunks=(b"abcd", b"efgh"))
        ):
            with self.assertRaises(CommandError) as ctx:
                cmd_module._download_tarball("https://r/a.tar.gz", self.dest)
        self.assertIn("exceeds", str(ctx.exception))
        self.assertEqual(self.dest.read_bytes(), b"abcd")
