"""Regression tests for Redis URL fidelity across Django and Celery settings."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from django.test import SimpleTestCase

ROOT_DIR = Path(__file__).resolve().parents[2]


class RedisSettingsUrlTestCase(SimpleTestCase):
    def load_local_settings(self, **overrides: str) -> dict[str, Any]:
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.local",
            "STORAGE_BACKEND": "LOCAL",
            "DATABASE_URL": "postgres://user:password@localhost:5432/opencontracts",
        }
        # The container entrypoint in an integration test process may have
        # exported a broker value already. Test Django's own fallback contract
        # unless a case explicitly provides an override below.
        env.pop("CELERY_BROKER_URL", None)
        env.pop("CELERY_RESULT_BACKEND", None)
        env.update(overrides)
        program = """
import json
from config.settings import local
from config.celery_app import app

print(json.dumps({
    'channel_host': local.CHANNEL_LAYERS['default']['CONFIG']['hosts'][0],
    'broker': local.CELERY_BROKER_URL,
    'backend': local.CELERY_RESULT_BACKEND,
    'app_broker': app.conf.broker_url,
    'app_backend': app.conf.result_backend,
}))
"""
        result = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_multidigit_redis_database_is_preserved(self):
        url = "redis://redis:6379/15"
        settings = self.load_local_settings(REDIS_URL=url)

        self.assertEqual(settings["channel_host"]["address"], url)
        self.assertEqual(settings["channel_host"]["socket_timeout"], None)
        self.assertEqual(settings["broker"], url)
        self.assertEqual(settings["backend"], url)
        self.assertEqual(settings["app_broker"], url)
        self.assertEqual(settings["app_backend"], url)

    def test_explicit_celery_urls_override_redis_default(self):
        settings = self.load_local_settings(
            REDIS_URL="redis://redis:6379/0",
            CELERY_BROKER_URL="redis://redis:6379/15",
            CELERY_RESULT_BACKEND="redis://redis:6379/14",
        )

        self.assertEqual(settings["channel_host"]["address"], "redis://redis:6379/0")
        self.assertEqual(settings["broker"], "redis://redis:6379/15")
        self.assertEqual(settings["backend"], "redis://redis:6379/14")
        self.assertEqual(settings["app_broker"], "redis://redis:6379/15")
        self.assertEqual(settings["app_backend"], "redis://redis:6379/14")
