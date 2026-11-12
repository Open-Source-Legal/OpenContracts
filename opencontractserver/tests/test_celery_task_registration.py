"""Every Celery task must be registered when a worker starts.

A worker registers only the tasks its startup imports reach
(``app.autodiscover_tasks()`` → each app's ``tasks`` package). A task module
imported lazily from inside another task is missing from the worker's main
process, which discards its messages as "unregistered task". That stranded
every chunked (long) PDF in ``processing`` until the stuck-document sweep
failed it, because ``chunk_tasks`` was only imported inside ``ingest_doc``.

Unit tests run tasks eagerly in-process, so they cannot see this; the check
runs in a fresh interpreter to reproduce a worker's startup imports exactly.
"""

import json
import subprocess
import sys

from django.test import SimpleTestCase

_CHECK = """
import importlib, json, pkgutil
import django
django.setup()
from config.celery_app import app
app.loader.import_default_modules()
at_startup = set(app.tasks)
package = importlib.import_module("opencontractserver.tasks")
for module in pkgutil.iter_modules(package.__path__):
    importlib.import_module(f"opencontractserver.tasks.{module.name}")
print(json.dumps(sorted(set(app.tasks) - at_startup)))
"""


class CeleryTaskRegistrationTest(SimpleTestCase):
    def test_all_task_modules_register_at_worker_startup(self):
        result = subprocess.run(
            [sys.executable, "-c", _CHECK],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
        missing = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(
            missing,
            [],
            "Tasks not registered at worker startup; import their module in "
            "opencontractserver/tasks/__init__.py",
        )
