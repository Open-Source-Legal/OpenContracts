"""Tests for the desktop packaging helpers.

Covers the pure per-OS path resolution (``opencontractserver.desktop.paths``)
and the SPA catch-all view (``config.spa.spa_fallback``) — in particular its
directory-traversal guard, which must never serve a file outside
``OC_DESKTOP_SPA_ROOT``.
"""

import io
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

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

    def test_traversal_is_blocked(self):
        # A ``../`` escape must NOT serve a file outside the SPA root; safe_join
        # rejects it and we fall back to index.html (served as text/html).
        with override_settings(OC_DESKTOP_SPA_ROOT=self.root):
            resp = spa_fallback(self.factory.get("/x"), "../../../../../../etc/passwd")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("Content-Type", ""))

    def test_disabled_when_root_unset(self):
        with override_settings(OC_DESKTOP_SPA_ROOT=""):
            with self.assertRaises(Http404):
                spa_fallback(self.factory.get("/"), "")


class DesktopBootstrapTests(TestCase):
    """Tests for the ``desktop_bootstrap`` command's user + pipeline seeding."""

    def _command(self):
        from opencontractserver.documents.management.commands.desktop_bootstrap import (
            Command,
        )

        # Real StringIO streams (not MagicMock) so the command's OutputWrapper
        # type is satisfied; read them back with getvalue().
        self.out = io.StringIO()
        self.err = io.StringIO()
        return Command(stdout=self.out, stderr=self.err)

    def test_seed_user_with_password(self):
        cmd = self._command()
        with mock.patch.dict(
            os.environ, {"OC_DESKTOP_PASSWORD": "s3cret-pw-123"}, clear=False
        ):
            cmd._seed_user("alice", "alice@localhost")
        user = User.objects.get(username="alice")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password("s3cret-pw-123"))

    def test_seed_user_without_password_is_unusable(self):
        cmd = self._command()
        # Empty OC_DESKTOP_PASSWORD → treated as unset → unusable password.
        with mock.patch.dict(os.environ, {"OC_DESKTOP_PASSWORD": ""}, clear=False):
            cmd._seed_user("bob", "bob@localhost")
        user = User.objects.get(username="bob")
        self.assertTrue(user.is_superuser)
        self.assertFalse(user.has_usable_password())

    def test_seed_user_is_idempotent(self):
        cmd = self._command()
        with mock.patch.dict(os.environ, {"OC_DESKTOP_PASSWORD": ""}, clear=False):
            cmd._seed_user("carol", "carol@localhost")
            cmd._seed_user("carol", "carol@localhost")  # no duplicate / no error
        self.assertEqual(User.objects.filter(username="carol").count(), 1)

    def test_seed_pipeline_settings_creates_singleton(self):
        from opencontractserver.documents.models import PipelineSettings

        cmd = self._command()
        with mock.patch(
            "opencontractserver.documents.management.commands."
            "desktop_bootstrap.call_command"
        ) as mock_call:
            cmd._seed_pipeline_settings()
        mock_call.assert_called_once_with("migrate_pipeline_settings")
        self.assertTrue(PipelineSettings.objects.filter(pk=1).exists())

    def test_seed_pipeline_settings_survives_migrate_failure(self):
        cmd = self._command()
        with mock.patch(
            "opencontractserver.documents.management.commands."
            "desktop_bootstrap.call_command",
            side_effect=RuntimeError("boom"),
        ):
            # A migrate_pipeline_settings failure must not raise — PDF parsing
            # still works; only Tier-1 secrets/component settings degrade.
            cmd._seed_pipeline_settings()
        self.assertIn("did not seed", self.err.getvalue())
