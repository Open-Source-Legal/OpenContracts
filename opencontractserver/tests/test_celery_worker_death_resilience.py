"""
Regression tests for Issue #1493: Celery resilience to worker death.

OpenContracts enables ``CELERY_TASK_ACKS_LATE`` and
``CELERY_TASK_REJECT_ON_WORKER_LOST`` so that a worker dying mid-task
(OOM, SIGKILL, host loss, deploy eviction) results in the broker redelivering
the message to another worker instead of silently dropping it.

Real-broker simulation of a SIGKILL'd worker would require a multi-process
test harness with rabbit/redis, which is out of scope for the unit-test
suite. Instead these tests pin the configuration that Celery itself uses to
make the redelivery decision, so a future settings change cannot silently
revert the resilience guarantee.
"""

from django.conf import settings
from django.test import SimpleTestCase

from config import celery_app


class CeleryWorkerDeathResilienceSettingsTests(SimpleTestCase):
    """Lock down the two settings and their propagation into the Celery app.

    Note: ``celery_app.conf`` is populated once at import time via
    ``config_from_object`` in ``config/celery_app.py``. These tests pin the
    *startup* configuration; they intentionally do not respond to
    ``@override_settings``, since Celery has already cached the values by the
    time any test runs.
    """

    def test_django_settings_enable_acks_late(self) -> None:
        self.assertTrue(
            getattr(settings, "CELERY_TASK_ACKS_LATE", False),
            "CELERY_TASK_ACKS_LATE must be True so the broker only acks "
            "after a task returns successfully (Issue #1493).",
        )

    def test_django_settings_enable_reject_on_worker_lost(self) -> None:
        self.assertTrue(
            getattr(settings, "CELERY_TASK_REJECT_ON_WORKER_LOST", False),
            "CELERY_TASK_REJECT_ON_WORKER_LOST must be True so SIGKILL'd "
            "workers cause redelivery instead of silent task loss "
            "(Issue #1493).",
        )

    def test_celery_app_picks_up_acks_late(self) -> None:
        self.assertTrue(
            celery_app.conf.task_acks_late,
            "Celery app config did not pick up task_acks_late from Django "
            "settings — the namespace='CELERY' wiring may be broken.",
        )

    def test_celery_app_picks_up_reject_on_worker_lost(self) -> None:
        self.assertTrue(
            celery_app.conf.task_reject_on_worker_lost,
            "Celery app config did not pick up task_reject_on_worker_lost "
            "from Django settings — the namespace='CELERY' wiring may be "
            "broken.",
        )

    def test_redis_visibility_timeout_exceeds_celery_default(self) -> None:
        """The Redis visibility timeout must be raised above the 1h default.

        With ``task_acks_late=True`` and Redis as broker, any task that runs
        longer than the broker's visibility timeout will be redelivered to a
        second worker while still executing on the first — an unconditional
        double execution. The global default of 3600s is shorter than worst
        case ingest/parse/embed runs, so we explicitly raise it.
        """
        transport_options = getattr(settings, "CELERY_BROKER_TRANSPORT_OPTIONS", {})
        visibility = transport_options.get("visibility_timeout")
        self.assertIsInstance(
            visibility,
            int,
            "CELERY_BROKER_TRANSPORT_OPTIONS must set 'visibility_timeout' "
            "to an integer number of seconds to override Celery's 1-hour "
            "Redis default (Issue #1493).",
        )
        assert isinstance(visibility, int)  # narrow for mypy
        self.assertGreater(
            visibility,
            3600,
            "visibility_timeout must exceed Celery's 1-hour default; "
            "otherwise long-running tasks will be double-delivered.",
        )
