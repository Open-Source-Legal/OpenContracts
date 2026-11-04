"""
Pins the stock ``local.yml`` wiring that issue #2514 found broken.

Nothing else exercises these files: the test stack uses ``test.yml`` and a
different worker command, so a regression here only surfaces on a fresh install.
"""

import shlex
from pathlib import Path
from typing import Any

import yaml
from django.test import SimpleTestCase

ROOT_DIR = Path(__file__).resolve().parents[2]
WORKER_START = ROOT_DIR / "compose" / "local" / "django" / "celery" / "worker" / "start"


class TestEmbedderKeyWiring(SimpleTestCase):
    """Django and the embedders must resolve the same API key on a stock install."""

    services: dict[str, Any]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with (ROOT_DIR / "local.yml").open(encoding="utf-8") as stream:
            cls.services = yaml.safe_load(stream)["services"]

    def test_clients_forward_the_key_each_embedder_expects(self):
        # Both images read VECTOR_EMBEDDER_API_KEY; the multimodal one sources it
        # from a different host var, so each client key pairs with its own service.
        expected = {
            "VECTOR_EMBEDDER_API_KEY": "vector-embedder",
            "MULTIMODAL_EMBEDDER_API_KEY": "multimodal-embedder",
        }
        for client in ("django", "celeryworker"):
            for client_key, service in expected.items():
                with self.subTest(client=client, key=client_key):
                    self.assertEqual(
                        self.services[client]["environment"][client_key],
                        self.services[service]["environment"][
                            "VECTOR_EMBEDDER_API_KEY"
                        ],
                    )


class TestWorkerAutoreload(SimpleTestCase):
    """The worker must reload on source edits, and never on its own output."""

    argv: list[str]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        command = next(
            line
            for line in WORKER_START.read_text(encoding="utf-8").splitlines()
            if line.startswith("watchfiles ")
        )
        cls.argv = shlex.split(command)

    def _option(self, name):
        return self.argv[self.argv.index(name) + 1]

    def test_only_python_changes_trigger_a_reload(self):
        self.assertEqual(self._option("--filter"), "python")

    def test_local_media_root_is_ignored(self):
        # watchfiles resolves ignore paths against the cwd, so this must be the
        # full path to MEDIA_ROOT: a bare ``media`` matches only /app/media.
        self.assertIn(
            "opencontractserver/media", self._option("--ignore-paths").split(",")
        )

    def test_watched_paths_follow_the_target_command(self):
        # The first positional is the target, so a path placed ahead of it would
        # be run as the command and the worker would never start.
        target_index = self.argv.index("--target-type") + 2
        self.assertTrue(self.argv[target_index].startswith("celery "))
        self.assertEqual(
            self.argv[target_index + 1 :], ["opencontractserver", "config"]
        )
