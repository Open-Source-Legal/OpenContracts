"""Architecture invariant: every shipped Celery task must register on a
freshly-booted worker.

Background (investigation 2026-06-01): the Celery worker does **not**
discover the central ``opencontractserver/tasks/`` package directly —
``autodiscover_tasks()`` only finds per-app ``tasks.py`` modules, and the
only one that exists is ``opencontractserver/users/tasks.py``. The central
package is imported as a *side effect* of Django boot (admin/signal/service
imports eventually trigger ``opencontractserver/tasks/__init__.py``), and
that ``__init__`` eagerly imports a curated list of submodules. The
``@shared_task`` decorator only registers a task when its module is
imported, so any task module missing from that boot chain is silently
absent from the worker's registry.

``run_deep_research`` (research) and the ``memory_tasks`` beat tasks were
only reachable via lazy, function-local producer-side imports, so they
queued fine from the web process but were *unregistered on the worker* —
a real worker would reject the message with "Received unregistered task".
The defect hides from the unit suite because ``config.settings.test`` runs
Celery in ``CELERY_TASK_ALWAYS_EAGER`` mode, where ``.delay()`` runs inline
in the same process that just lazily imported the module.

This test boots a worker the way the worker boots — in a clean subprocess,
running only ``django.setup()`` + ``autodiscover_tasks()`` +
``import_default_modules()`` and **never** importing the producer
services — then asserts the canonical task names are present in
``app.tasks``. Running in a subprocess is essential: the in-process pytest
interpreter has already imported many modules, which would mask a missing
boot-time registration.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

# Canonical task names that MUST be registered on a freshly-booted worker.
# These are tasks reachable only through lazy/beat dispatch (no module-level
# import on the boot path), which is exactly the class of task that silently
# fails to register. Add an entry here whenever a task is dispatched by name
# (beat schedule) or via a lazy, function-local ``.delay()`` import -- i.e.
# any task whose defining module is NOT transitively imported from
# ``opencontractserver/tasks/__init__.py`` at worker boot.
REQUIRED_TASK_NAMES = [
    "opencontractserver.tasks.research_tasks.run_deep_research",
    "opencontractserver.tasks.research_tasks.reap_stalled_research",
    "opencontractserver.tasks.memory_tasks.check_conversations_for_curation",
    "opencontractserver.tasks.memory_tasks.curate_corpus_memory",
    # Beat-only (referenced by name in CELERY_BEAT_SCHEDULE, no module-level
    # producer import) — issue #1908.
    "opencontractserver.tasks.stats_tasks.refresh_system_stats",
]

# Replicates the Celery worker boot path (``celery -A config.celery_app
# worker``) in a clean interpreter and reports which of the required task
# names made it into the registry. It must NOT import any producer service
# (e.g. ``research.services.research_reports``) — doing so would import the
# task module directly and mask the very defect this test guards against.
_BOOT_SCRIPT = textwrap.dedent("""
    import json
    import django

    django.setup()

    from config.celery_app import app

    # The worker calls autodiscover at startup and finalizes task discovery
    # via import_default_modules during bootstrap. Mirror both here.
    app.autodiscover_tasks()
    app.loader.import_default_modules()

    required = {required!r}
    present = {{name: name in app.tasks for name in required}}
    print(json.dumps(present))
    """).format(required=REQUIRED_TASK_NAMES)


@pytest.mark.serial
def test_required_tasks_register_on_fresh_worker_boot() -> None:
    """Tasks dispatched by name/lazy import must register at worker boot.

    Boots a worker in a clean subprocess and asserts every name in
    ``REQUIRED_TASK_NAMES`` is in ``app.tasks``. A missing name means the
    task module is absent from the boot import chain (most commonly: not
    imported in ``opencontractserver/tasks/__init__.py``), so the real
    worker would reject the queued message as an unregistered task.
    """
    env = dict(os.environ)
    # Settings module choice is irrelevant to registration (it is about
    # import wiring, not eager mode); fall back to the test settings.
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

    result = subprocess.run(
        [sys.executable, "-c", _BOOT_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        # Django setup in a fresh interpreter is ~5-15s; 90s is generous but
        # fails fast if the subprocess genuinely hangs.
        timeout=90,
    )

    assert result.returncode == 0, (
        "Worker boot subprocess failed.\n"
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )

    # The boot script prints a single JSON object on its final stdout line.
    last_line = result.stdout.strip().splitlines()[-1]
    present = json.loads(last_line)

    missing = [name for name, ok in present.items() if not ok]
    assert not missing, (
        "These Celery tasks did NOT register on a fresh worker boot: "
        f"{missing}. Add the defining module to "
        "opencontractserver/tasks/__init__.py (and __all__) so the "
        "@shared_task decorator runs during worker startup. A worker would "
        "otherwise reject these as 'Received unregistered task'."
    )
