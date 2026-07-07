"""Tests for the desktop packaging helpers.

Covers the pure per-OS path resolution (``opencontractserver.desktop.paths``)
and the SPA catch-all view (``config.spa.spa_fallback``) — in particular its
directory-traversal guard, which must never serve a file outside
``OC_DESKTOP_SPA_ROOT``.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock, skipIf

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import (
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)

from config.spa import spa_fallback
from opencontractserver.desktop import paths

User = get_user_model()


class DesktopPathsTests(SimpleTestCase):
    def test_windows_data_dir(self):
        with mock.patch.object(sys, "platform", "win32"), mock.patch.dict(
            os.environ, {"LOCALAPPDATA": r"C:\Users\me\AppData\Local"}, clear=False
        ):
            os.environ.pop(paths.DATA_DIR_ENV, None)
            result = paths.default_app_data_dir()
        self.assertEqual(result.name, "OpenContracts")
        self.assertIn("AppData", str(result))

    def test_macos_data_dir(self):
        with mock.patch.object(sys, "platform", "darwin"), mock.patch(
            "os.path.expanduser", return_value="/Users/me"
        ):
            result = paths.default_app_data_dir()
        self.assertEqual(
            result, Path("/Users/me/Library/Application Support/OpenContracts")
        )

    def test_linux_xdg_data_dir(self):
        with mock.patch.object(sys, "platform", "linux"), mock.patch.dict(
            os.environ, {"XDG_DATA_HOME": "/home/me/.local/share"}, clear=False
        ):
            result = paths.default_app_data_dir()
        self.assertEqual(result, Path("/home/me/.local/share/OpenContracts"))

    def test_data_dir_override_wins(self):
        with mock.patch.dict(
            os.environ, {paths.DATA_DIR_ENV: "/tmp/oc-desktop-test"}, clear=False
        ):
            self.assertEqual(paths.app_data_dir(), Path("/tmp/oc-desktop-test"))

    def test_app_data_dir_falls_back_to_default(self):
        # With no override, app_data_dir() delegates to default_app_data_dir().
        with mock.patch.object(sys, "platform", "linux"), mock.patch.dict(
            os.environ, {"XDG_DATA_HOME": "/x"}, clear=False
        ):
            os.environ.pop(paths.DATA_DIR_ENV, None)
            self.assertEqual(paths.app_data_dir(), Path("/x/OpenContracts"))

    def test_well_known_locations(self):
        with mock.patch.dict(os.environ, {paths.DATA_DIR_ENV: "/data"}, clear=False):
            root = Path("/data")
            self.assertEqual(paths.pg_data_dir(), root / "pgdata")
            self.assertEqual(paths.media_dir(), root / "media")
            self.assertEqual(paths.static_dir(), root / "staticfiles")
            self.assertEqual(paths.celery_broker_dir(), root / "celery-broker")
            self.assertEqual(paths.logs_dir(), root / "logs")
            self.assertEqual(paths.first_run_marker(), root / ".bootstrapped")
            # subdir without create returns the path without touching the fs.
            self.assertEqual(paths.subdir("a", "b"), root / "a" / "b")

    def test_subdir_creates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {paths.DATA_DIR_ENV: tmp}, clear=False):
                created = paths.subdir("nested", "dir", create=True)
                self.assertTrue(created.is_dir())
                self.assertEqual(created, Path(tmp) / "nested" / "dir")


class SpaFallbackTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.root = tempfile.mkdtemp()
        (Path(self.root) / "index.html").write_text(
            "<html>SPA-INDEX</html>", encoding="utf-8"
        )
        assets = Path(self.root) / "assets"
        assets.mkdir()
        (assets / "app.js").write_text("console.log(1)", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_serves_real_asset(self):
        with override_settings(OC_DESKTOP_SPA_ROOT=self.root):
            resp = spa_fallback(self.factory.get("/assets/app.js"), "assets/app.js")
        self.assertEqual(resp.status_code, 200)

    def test_client_route_returns_index(self):
        with override_settings(OC_DESKTOP_SPA_ROOT=self.root):
            resp = spa_fallback(self.factory.get("/corpuses/1"), "corpuses/1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("Content-Type", ""))
        self.assertIn(b"SPA-INDEX", b"".join(resp.streaming_content))

    def test_traversal_is_blocked(self):
        # A ``../`` escape must NOT serve a file outside the SPA root; safe_join
        # rejects it and we fall back to index.html (served as text/html).
        with override_settings(OC_DESKTOP_SPA_ROOT=self.root):
            resp = spa_fallback(self.factory.get("/x"), "../../../../../../etc/passwd")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("Content-Type", ""))
        # The body must be the real index.html, not /etc/passwd or empty.
        body = b"".join(resp.streaming_content)
        self.assertIn(b"SPA-INDEX", body)
        self.assertNotIn(b"root:", body)

    def test_disabled_when_root_unset(self):
        with override_settings(OC_DESKTOP_SPA_ROOT=""):
            with self.assertRaises(Http404):
                spa_fallback(self.factory.get("/"), "")


class DesktopBootstrapTests(TestCase):
    """Tests for the ``desktop_bootstrap`` command's user + pipeline seeding."""

    @staticmethod
    def _command():
        """Build the command with real StringIO streams (mypy-clean, readable)."""
        from opencontractserver.documents.management.commands.desktop_bootstrap import (
            Command,
        )

        out, err = io.StringIO(), io.StringIO()
        return Command(stdout=out, stderr=err), out, err

    def test_seed_user_with_password(self):
        cmd, _out, _err = self._command()
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": "s3cret-pw-123"}, clear=False
        ):
            cmd._seed_user("alice", "alice@localhost")
        user = User.objects.get(username="alice")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password("s3cret-pw-123"))

    @staticmethod
    def _no_tty():
        """Force the non-interactive path (no password prompt) regardless of
        how the test runner's stdin is wired. The prompt lives in the shared
        opencontractserver.desktop.bootstrap helper."""
        return mock.patch(
            "opencontractserver.desktop.bootstrap.sys.stdin.isatty",
            return_value=False,
        )

    @staticmethod
    def _tty():
        return mock.patch(
            "opencontractserver.desktop.bootstrap.sys.stdin.isatty",
            return_value=True,
        )

    def test_seed_user_without_password_is_unusable(self):
        cmd, _out, _err = self._command()
        # Empty OC_DESKTOP_PASSWORD → treated as unset; no terminal → no prompt
        # → unusable password.
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": ""}, clear=False
        ), self._no_tty():
            cmd._seed_user("bob", "bob@localhost")
        user = User.objects.get(username="bob")
        self.assertTrue(user.is_superuser)
        self.assertFalse(user.has_usable_password())

    def test_seed_user_is_idempotent(self):
        cmd, _out, _err = self._command()
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": ""}, clear=False
        ), self._no_tty():
            cmd._seed_user("carol", "carol@localhost")
            cmd._seed_user("carol", "carol@localhost")  # no duplicate / no error
        self.assertEqual(User.objects.filter(username="carol").count(), 1)

    def test_seed_user_prompts_on_tty_and_enforces_min_length(self):
        cmd, _out, _err = self._command()
        # First attempt too short, then a valid pair — the prompt loops.
        answers = iter(["short", "longenough-pw", "longenough-pw"])
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": ""}, clear=False
        ), self._tty(), mock.patch(
            "getpass.getpass",
            side_effect=lambda *_a, **_k: next(answers),
        ):
            cmd._seed_user("erin", "erin@localhost")
        user = User.objects.get(username="erin")
        self.assertTrue(user.check_password("longenough-pw"))

    def test_seed_user_self_heals_passwordless_account(self):
        # A user left over from a headless first run (no usable password) gets
        # one on the next run instead of being stuck.
        cmd, _out, _err = self._command()
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": ""}, clear=False
        ), self._no_tty():
            cmd._seed_user("frank", "frank@localhost")
        self.assertFalse(User.objects.get(username="frank").has_usable_password())
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": "recovered-pw-1"}, clear=False
        ):
            cmd._seed_user("frank", "frank@localhost")
        user = User.objects.get(username="frank")
        self.assertTrue(user.check_password("recovered-pw-1"))
        self.assertEqual(User.objects.filter(username="frank").count(), 1)

    def test_seed_user_with_usable_password_never_reprompts(self):
        cmd, _out, _err = self._command()
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": "stable-pw-123"}, clear=False
        ):
            cmd._seed_user("gina", "gina@localhost")
        # Second run: env cleared, TTY present — but the account already has a
        # usable password, so no prompt happens (getpass would explode).
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": ""}, clear=False
        ), self._tty(), mock.patch(
            "getpass.getpass",
            side_effect=AssertionError("must not prompt"),
        ):
            cmd._seed_user("gina", "gina@localhost")
        self.assertTrue(
            User.objects.get(username="gina").check_password("stable-pw-123")
        )

    def test_seed_pipeline_settings_creates_singleton(self):
        from opencontractserver.documents.models import PipelineSettings

        cmd, _out, _err = self._command()
        with mock.patch(
            "opencontractserver.documents.management.commands."
            "desktop_bootstrap.call_command"
        ) as mock_call:
            ok = cmd._seed_pipeline_settings()
        mock_call.assert_called_once_with("migrate_pipeline_settings")
        self.assertTrue(ok)
        self.assertTrue(PipelineSettings.objects.filter(pk=1).exists())

    def test_seed_pipeline_settings_survives_migrate_failure(self):
        cmd, _out, err = self._command()
        with mock.patch(
            "opencontractserver.documents.management.commands."
            "desktop_bootstrap.call_command",
            side_effect=RuntimeError("boom"),
        ):
            # A migrate_pipeline_settings failure must not raise — PDF parsing
            # still works; only Tier-1 secrets/component settings degrade —
            # but it returns False so the caller can signal a retry.
            ok = cmd._seed_pipeline_settings()
        self.assertFalse(ok)
        self.assertIn("did not seed", err.getvalue())

    def test_handle_raises_on_pipeline_failure_so_marker_is_not_written(self):
        # handle() must exit non-zero (CommandError) when pipeline seeding fails,
        # so the launcher leaves the first-run marker unwritten and retries.
        from django.core.management.base import CommandError

        cmd, _out, _err = self._command()
        with mock.patch(
            "opencontractserver.documents.management.commands."
            "desktop_bootstrap.call_command",
            side_effect=RuntimeError("boom"),
        ), mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": ""}, clear=False
        ), self._no_tty():
            with self.assertRaises(CommandError):
                cmd.handle(username="dave", email="dave@localhost", skip_nltk=True)
        # The idempotent user seed still happened despite the pipeline failure.
        self.assertTrue(User.objects.filter(username="dave").exists())


class SqlAlchemyResultUrlTests(SimpleTestCase):
    """The Django DATABASE_URL → Celery SQLAlchemy result-backend mapping."""

    def test_postgres_scheme_mapped(self):
        from opencontractserver.desktop.db import sqlalchemy_result_backend_url

        self.assertEqual(
            sqlalchemy_result_backend_url("postgres://u:p@h:5432/db"),
            "db+postgresql://u:p@h:5432/db",
        )

    def test_query_string_preserved(self):
        from opencontractserver.desktop.db import sqlalchemy_result_backend_url

        self.assertEqual(
            sqlalchemy_result_backend_url("postgresql://u@h/db?sslmode=require"),
            "db+postgresql://u@h/db?sslmode=require",
        )

    def test_non_postgres_passthrough(self):
        from opencontractserver.desktop.db import sqlalchemy_result_backend_url

        self.assertEqual(
            sqlalchemy_result_backend_url("sqlite:////tmp/x.db"),
            "db+sqlite:////tmp/x.db",
        )


class DesktopSettingsImportTests(SimpleTestCase):
    """config.settings.desktop must import cleanly even under a hostile env.

    base.py branches on USE_AUTH0 / STORAGE_BACKEND at its own import time with
    no fallbacks, so a stray ``USE_AUTH0=true`` / ``STORAGE_BACKEND=GCP`` in the
    process environment must not crash the desktop profile's import.
    """

    def test_imports_under_hostile_env(self):
        repo_root = Path(__file__).resolve().parents[2]
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.desktop",
            "DJANGO_READ_DOT_ENV_FILE": "False",
            "USE_AUTH0": "true",  # base would require AUTH0_* with no defaults
            "STORAGE_BACKEND": "GCP",  # base would require GS_BUCKET_NAME
            "OC_DESKTOP_DATA_DIR": tempfile.mkdtemp(),
            "PYTHONPATH": str(repo_root),
        }
        # Drop any inherited DATABASE_URL so the profile's setdefault is exercised.
        env.pop("DATABASE_URL", None)
        script = (
            "import config.settings.desktop as s;"
            "assert s.USE_AUTH0 is False, s.USE_AUTH0;"
            "assert s.STORAGE_BACKEND == 'LOCAL', s.STORAGE_BACKEND;"
            "assert s.CELERY_RESULT_BACKEND.startswith('db+postgresql://'), "
            "s.CELERY_RESULT_BACKEND;"
            "print('DESKTOP_IMPORT_OK')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            env=env,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DESKTOP_IMPORT_OK", result.stdout)


class BootstrapTests(SimpleTestCase):
    """Pure logic of the stdlib-only self-bootstrap (`desktop.bootstrap`)."""

    def test_python_version_window(self):
        from opencontractserver.desktop import bootstrap

        for supported in ((3, 10), (3, 11), (3, 12)):
            self.assertIsNone(bootstrap.python_version_error(supported))
        for unsupported in ((3, 9), (3, 13), (3, 14)):
            message = bootstrap.python_version_error(unsupported)
            assert message is not None  # narrows the type for mypy
            self.assertIn("python.org", message)

    def test_venv_python_per_os(self):
        from opencontractserver.desktop import bootstrap

        venv_path = Path("/data/venv")
        with mock.patch.object(os, "name", "posix"):
            self.assertEqual(
                bootstrap.venv_python(venv_path), venv_path / "bin" / "python"
            )
        with mock.patch.object(os, "name", "nt"):
            self.assertEqual(
                bootstrap.venv_python(venv_path),
                venv_path / "Scripts" / "python.exe",
            )

    def test_requirements_fingerprint_tracks_content(self):
        from opencontractserver.desktop import bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "desktop.txt"
            second = Path(tmp) / "base.txt"
            first.write_text("pkg-a==1.0\n")
            second.write_text("pkg-b==2.0\n")
            before = bootstrap.requirements_fingerprint([first, second])
            self.assertEqual(
                before, bootstrap.requirements_fingerprint([first, second])
            )
            second.write_text("pkg-b==2.1\n")
            self.assertNotEqual(
                before, bootstrap.requirements_fingerprint([first, second])
            )

    def test_deps_ready_requires_every_sentinel(self):
        from opencontractserver.desktop import bootstrap

        with mock.patch("importlib.util.find_spec", return_value=object()):
            self.assertTrue(bootstrap.deps_ready())
        with mock.patch("importlib.util.find_spec", return_value=None):
            self.assertFalse(bootstrap.deps_ready())

    def test_repo_root_contains_entrypoints(self):
        from opencontractserver.desktop import bootstrap

        root = bootstrap.repo_root()
        self.assertTrue((root / "manage.py").is_file())
        self.assertTrue((root / "oc-desktop.py").is_file())


class SpaDistTests(SimpleTestCase):
    """SPA bundle acquisition helpers (`desktop.spa_dist`)."""

    def test_release_tag_candidates_cover_both_spellings(self):
        from opencontractserver.desktop import spa_dist

        self.assertEqual(
            spa_dist.release_tag_candidates("3.0.0b4"),
            ["v3.0.0b4", "v3.0.0.b4"],
        )
        self.assertEqual(spa_dist.release_tag_candidates("3.1.0"), ["v3.1.0"])

    def test_find_asset_url(self):
        from opencontractserver.desktop import spa_dist

        release = {
            "assets": [
                {"name": "other.zip", "browser_download_url": "https://x/other"},
                {
                    "name": spa_dist.SPA_ASSET_NAME,
                    "browser_download_url": "https://x/spa",
                },
            ]
        }
        self.assertEqual(spa_dist.find_asset_url(release), "https://x/spa")
        self.assertIsNone(spa_dist.find_asset_url({"assets": []}))

    def test_safe_extract_blocks_traversal(self):
        import zipfile

        from opencontractserver.desktop import spa_dist

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "evil.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../evil.txt", "pwned")
            dest = Path(tmp) / "dest"
            dest.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                with self.assertRaises(ValueError):
                    spa_dist.safe_extract_zip(archive, dest)
            self.assertFalse((Path(tmp) / "evil.txt").exists())

    def test_safe_extract_extracts_good_archive(self):
        import zipfile

        from opencontractserver.desktop import spa_dist

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "good.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("dist/index.html", "<html></html>")
                archive.writestr("dist/assets/app.js", "console.log(1)")
            dest = Path(tmp) / "dest"
            dest.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                spa_dist.safe_extract_zip(archive, dest)
            self.assertTrue((dest / "dist" / "index.html").is_file())
            self.assertTrue((dest / "dist" / "assets" / "app.js").is_file())

    def test_ensure_spa_prefers_repo_dist(self):
        from opencontractserver.desktop import spa_dist

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            dist = repo / "frontend" / "dist"
            dist.mkdir(parents=True)
            (dist / "index.html").write_text("<html></html>")
            self.assertEqual(spa_dist.ensure_spa(repo, "0.0.0"), dist)

    @staticmethod
    def _cached_spa(tmp: str) -> tuple[Path, Path, Path]:
        """A repo without dist and an app-data dir holding a cached SPA."""
        repo = Path(tmp) / "repo"
        repo.mkdir()
        data_dir = Path(tmp) / "appdata"
        cached = data_dir / "spa" / "dist"
        cached.mkdir(parents=True)
        (cached / "index.html").write_text("<html></html>")
        return repo, data_dir, cached

    def test_ensure_spa_uses_version_matched_cache(self):
        from opencontractserver.desktop import spa_dist

        with tempfile.TemporaryDirectory() as tmp:
            repo, data_dir, cached = self._cached_spa(tmp)
            (data_dir / "spa" / ".version").write_text("0.0.0\n")
            with mock.patch.dict(
                os.environ, {paths.DATA_DIR_ENV: str(data_dir)}, clear=False
            ), mock.patch.object(
                spa_dist,
                "download_spa",
                side_effect=AssertionError("must not re-download"),
            ):
                self.assertEqual(spa_dist.ensure_spa(repo, "0.0.0"), cached)

    def test_ensure_spa_refreshes_stale_cache(self):
        # A cache stamped for an older version must trigger a re-download so a
        # backend upgrade cannot silently keep serving a stale frontend.
        from opencontractserver.desktop import spa_dist

        with tempfile.TemporaryDirectory() as tmp:
            repo, data_dir, _cached = self._cached_spa(tmp)
            (data_dir / "spa" / ".version").write_text("0.0.1\n")
            fresh = Path(tmp) / "fresh-dist"
            with mock.patch.dict(
                os.environ, {paths.DATA_DIR_ENV: str(data_dir)}, clear=False
            ), mock.patch.object(
                spa_dist, "download_spa", return_value=fresh
            ) as download:
                self.assertEqual(spa_dist.ensure_spa(repo, "0.0.2"), fresh)
            download.assert_called_once_with("0.0.2")

    def test_ensure_spa_falls_back_to_stale_cache_offline(self):
        # Refresh failed (offline): the stale cache is better than no UI.
        from opencontractserver.desktop import spa_dist

        with tempfile.TemporaryDirectory() as tmp:
            repo, data_dir, cached = self._cached_spa(tmp)  # no .version stamp
            with mock.patch.dict(
                os.environ, {paths.DATA_DIR_ENV: str(data_dir)}, clear=False
            ), mock.patch.object(
                spa_dist, "download_spa", return_value=None
            ), mock.patch.object(
                spa_dist, "build_spa_with_yarn", return_value=None
            ):
                self.assertEqual(spa_dist.ensure_spa(repo, "0.0.2"), cached)

    def test_download_spa_returns_none_without_asset(self):
        from opencontractserver.desktop import spa_dist

        with mock.patch.object(spa_dist, "_release_asset_urls", return_value=None):
            self.assertIsNone(spa_dist.download_spa("0.0.0"))

    def test_verify_checksum(self):
        import hashlib

        from opencontractserver.desktop import spa_dist

        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.zip"
            bundle.write_bytes(b"bundle-bytes")
            good = hashlib.sha256(b"bundle-bytes").hexdigest()

            def fake_urlopen(digest):
                response = mock.MagicMock()
                response.read.return_value = f"{digest}  bundle.zip\n".encode()
                response.__enter__.return_value = response
                return mock.patch.object(
                    spa_dist.urllib.request, "urlopen", return_value=response
                )

            with fake_urlopen(good):
                self.assertTrue(spa_dist._verify_checksum(bundle, "https://x/sha"))
            with fake_urlopen("0" * 64):
                self.assertFalse(spa_dist._verify_checksum(bundle, "https://x/sha"))

    def test_verify_checksum_malformed_response_degrades_gracefully(self):
        # An empty .sha256 body (truncated response, proxy interstitial) must
        # raise ValueError — the type download_spa catches — never IndexError,
        # which would crash the launcher instead of degrading to "no UI".
        from opencontractserver.desktop import spa_dist

        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.zip"
            bundle.write_bytes(b"bundle-bytes")
            response = mock.MagicMock()
            response.read.return_value = b"   \n"
            response.__enter__.return_value = response
            with mock.patch.object(
                spa_dist.urllib.request, "urlopen", return_value=response
            ):
                with self.assertRaises(ValueError):
                    spa_dist._verify_checksum(bundle, "https://x/sha")


class TrigramMigrationGuardTests(TestCase):
    """annotations/0074 must skip (not crash) when pg_trgm is unavailable.

    The embedded desktop Postgres (`pgserver`) bundles no contrib extensions;
    an unconditional TrigramExtension() bricked every desktop install at
    first migrate. Real deployments (like this test DB) have pg_trgm and get
    the index as before.
    """

    @staticmethod
    def _migration_module():
        import importlib

        return importlib.import_module(
            "opencontractserver.annotations.migrations."
            "0074_annotation_raw_text_trigram_index"
        )

    def test_pg_trgm_available_on_real_postgres(self):
        from django.db import connection

        mod = self._migration_module()
        with connection.schema_editor() as schema_editor:
            self.assertTrue(mod._pg_trgm_available(schema_editor))

    def test_add_index_skips_without_pg_trgm(self):
        mod = self._migration_module()
        schema_editor = mock.Mock()
        with mock.patch.object(mod, "_pg_trgm_available", return_value=False):
            mod._add_trigram_index(None, schema_editor)
        schema_editor.execute.assert_not_called()

    def test_add_index_creates_extension_and_index_when_available(self):
        mod = self._migration_module()
        schema_editor = mock.Mock()
        with mock.patch.object(mod, "_pg_trgm_available", return_value=True):
            mod._add_trigram_index(None, schema_editor)
        executed = " ".join(
            call.args[0] for call in schema_editor.execute.call_args_list
        )
        self.assertIn("CREATE EXTENSION IF NOT EXISTS pg_trgm", executed)
        self.assertIn("annotation_raw_text_trgm_gin", executed)


class EarlyPasswordPromptTests(SimpleTestCase):
    """The stdlib-only prompt helpers in ``desktop.bootstrap``."""

    def test_prompt_returns_none_without_tty(self):
        from opencontractserver.desktop import bootstrap

        with mock.patch(
            "opencontractserver.desktop.bootstrap.sys.stdin.isatty",
            return_value=False,
        ):
            self.assertIsNone(bootstrap.prompt_for_password())

    def test_prompt_survives_ctrl_c(self):
        from opencontractserver.desktop import bootstrap

        with mock.patch(
            "opencontractserver.desktop.bootstrap.sys.stdin.isatty",
            return_value=True,
        ), mock.patch("getpass.getpass", side_effect=KeyboardInterrupt):
            self.assertIsNone(bootstrap.prompt_for_password())

    def test_early_prompt_sets_env_before_install(self):
        from opencontractserver.desktop import bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            env = {paths.DATA_DIR_ENV: tmp}
            env.pop("OC_DESKTOP_PASSWORD", None)
            with mock.patch.dict(os.environ, env, clear=False):
                os.environ.pop("OC_DESKTOP_PASSWORD", None)
                with mock.patch.object(
                    bootstrap, "prompt_for_password", return_value="chosen-pw-123"
                ):
                    bootstrap.maybe_prompt_first_run_password()
                self.assertEqual(os.environ.get("OC_DESKTOP_PASSWORD"), "chosen-pw-123")
                os.environ.pop("OC_DESKTOP_PASSWORD", None)

    def test_early_prompt_skipped_after_first_run(self):
        from opencontractserver.desktop import bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".bootstrapped").write_text("ok\n")
            with mock.patch.dict(
                os.environ, {paths.DATA_DIR_ENV: tmp}, clear=False
            ), mock.patch.object(
                bootstrap,
                "prompt_for_password",
                side_effect=AssertionError("must not prompt"),
            ):
                os.environ.pop("OC_DESKTOP_PASSWORD", None)
                bootstrap.maybe_prompt_first_run_password()
                self.assertIsNone(os.environ.get("OC_DESKTOP_PASSWORD"))


class EnvPasswordFloorTests(TestCase):
    """OC_DESKTOP_PASSWORD must not bypass the minimum-length floor."""

    def test_short_env_password_is_ignored(self):
        from opencontractserver.documents.management.commands.desktop_bootstrap import (
            Command,
        )

        out, err = io.StringIO(), io.StringIO()
        cmd = Command(stdout=out, stderr=err)
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": "short"}, clear=False
        ), mock.patch(
            "opencontractserver.desktop.bootstrap.sys.stdin.isatty",
            return_value=False,
        ):
            cmd._seed_user("hana", "hana@localhost")
        user = User.objects.get(username="hana")
        self.assertFalse(user.has_usable_password())
        self.assertIn("shorter than", out.getvalue())


class LauncherPureHelperTests(SimpleTestCase):
    """Targeted tests for launcher.py's pure helpers.

    The module is coverage-omitted as process orchestration (setup.cfg), but
    these helpers have deterministic logic worth pinning regardless.
    """

    def test_free_port_prefers_stable_default(self):
        from opencontractserver.desktop import launcher

        # The stable default should win when nothing holds it; if something in
        # the test environment does, the fallback must yield a usable port.
        port = launcher._free_port()
        self.assertTrue(1 <= port <= 65535)
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", launcher.DEFAULT_PORT))
            fallback = launcher._free_port()
        self.assertNotEqual(fallback, launcher.DEFAULT_PORT)
        self.assertTrue(1 <= fallback <= 65535)

    def test_keyring_username_is_stable_and_data_dir_scoped(self):
        from opencontractserver.desktop import launcher

        with mock.patch.dict(os.environ, {paths.DATA_DIR_ENV: "/data/a"}, clear=False):
            first = launcher._keyring_username()
            again = launcher._keyring_username()
        with mock.patch.dict(os.environ, {paths.DATA_DIR_ENV: "/data/b"}, clear=False):
            other = launcher._keyring_username()
        self.assertEqual(first, again)  # deterministic per data dir
        self.assertNotEqual(first, other)  # scoped per data dir
        self.assertTrue(first.startswith("django-secret-key-"))


class PrivateDirPermissionTests(SimpleTestCase):
    """ensure_private_dir must tighten PRE-EXISTING permissive dirs too.

    Path.mkdir(mode=0o700, exist_ok=True) silently skips the mode when the
    dir already exists (e.g. `python -m venv` created the app-data root with
    umask defaults on a first run), which is exactly the gap this guards.
    """

    @staticmethod
    def _mode(path):
        return os.stat(path).st_mode & 0o777

    @skipIf(os.name == "nt", "POSIX permission bits")
    def test_tightens_preexisting_permissive_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            root.mkdir(mode=0o755)
            (root / "media").mkdir(mode=0o755)
            with mock.patch.dict(
                os.environ, {paths.DATA_DIR_ENV: str(root)}, clear=False
            ):
                created = paths.subdir("media", create=True)
            self.assertEqual(self._mode(root), 0o700)
            self.assertEqual(self._mode(created), 0o700)

    @skipIf(os.name == "nt", "POSIX permission bits")
    def test_applies_mode_to_intermediate_parents(self):
        # parents=True never applies mode= to intermediate levels either.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            with mock.patch.dict(
                os.environ, {paths.DATA_DIR_ENV: str(root)}, clear=False
            ):
                leaf = paths.subdir("celery-broker", "in", create=True)
            self.assertEqual(self._mode(root), 0o700)
            self.assertEqual(self._mode(root / "celery-broker"), 0o700)
            self.assertEqual(self._mode(leaf), 0o700)
