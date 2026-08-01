"""The ``PipelineSettings`` singleton must survive a ``TransactionTestCase`` flush.

Sibling of ``test_authority_namespace.py::AuthorityNamespaceFlushReseedTests``,
which guards the same invariant for the shipped ``AuthorityNamespace`` rows.

Why this matters more than "a settings row went missing": ``get_instance()``
re-creates the singleton lazily, so an absent row does not fail loudly — it
**deadlocks**. An ``async`` test under Django's ``TestCase`` reaches
``get_embedder`` -> ``get_default_embedder_path`` -> ``PipelineSettings.
get_instance`` on the asgiref executor thread, which holds its own database
connection. That connection cannot see the main thread's uncommitted row, so it
issues a competing ``INSERT`` and blocks on the test transaction's lock, while
the main thread is parked in ``AsyncToSync.__call__`` waiting for the executor.
Neither advances until ``pytest-timeout`` fires at 600s, and the hang leaves
``unittest.mock.patch`` decorators un-exited — so it also fails every later test
in the class sharing the patched target.

Observed in CI as 5 failures in
``test_core_agents.py::TestCoreAgentFactoriesDefaults`` (two 600.01s timeouts
plus three ``'Mocked default prompt'`` assertion errors), reproducible locally
with ``pytest test_pipeline_settings.py test_core_agents.py::
TestCoreAgentFactoriesDefaults``.
"""

from __future__ import annotations

from django.test import TestCase, TransactionTestCase

from opencontractserver.documents.models import PipelineSettings


class PipelineSettingsRealFlushTests(TransactionTestCase):
    """End-to-end: the real ``flush`` command must leave the singleton intact.

    The sibling test below emits ``post_migrate`` by hand. This one runs the
    actual command Django invokes on every ``TransactionTestCase`` teardown, so
    it also pins the assumption the fix rests on — that ``flush`` emits
    ``post_migrate`` at all (it does not when ``available_apps`` is set, which
    is why this class does not set it).
    """

    def test_flush_truncates_then_post_migrate_restores_the_singleton(self):
        from django.core.management import call_command

        self.assertTrue(PipelineSettings.objects.filter(pk=1).exists())

        call_command("flush", verbosity=0, interactive=False)
        PipelineSettings.clear_cache()

        self.assertTrue(
            PipelineSettings.objects.filter(pk=1).exists(),
            "flush truncated the singleton and post_migrate did not restore it",
        )


class PipelineSettingsFlushReseedTests(TestCase):
    """``post_migrate`` must restore the singleton on the apps-less emission."""

    def test_post_migrate_without_apps_reseeds(self):
        """``flush`` emits ``post_migrate`` WITHOUT an ``apps`` kwarg.

        ``migrate`` passes the historical project state as ``apps``; ``flush``
        does not (``django/core/management/commands/flush.py`` vs
        ``migrate.py``). The flush-path emission is the one that has to
        re-seed, so a receiver that bails when ``apps`` is absent would leave
        the very gap this guards.
        """
        from django.apps import apps as global_apps
        from django.db.models.signals import post_migrate

        # Simulate the truncation a TransactionTestCase flush performs. The
        # delete rolls back with this TestCase's transaction.
        PipelineSettings.objects.all().delete()
        PipelineSettings.clear_cache()
        self.assertFalse(PipelineSettings.objects.exists())

        cfg = global_apps.get_app_config("documents")
        post_migrate.send(
            sender=cfg,
            app_config=cfg,
            verbosity=0,
            interactive=False,
            using="default",
        )

        self.assertTrue(
            PipelineSettings.objects.filter(pk=1).exists(),
            "post_migrate must restore the singleton after a flush",
        )

    def test_reseed_is_idempotent_and_preserves_operator_edits(self):
        """A converged row must not be reset on every subsequent emission.

        ``post_migrate`` fires on every ``migrate`` too, so a receiver that
        wrote unconditionally would silently revert an operator's System
        Settings changes on the next deploy.
        """
        from django.apps import apps as global_apps
        from django.db.models.signals import post_migrate

        settings_row = PipelineSettings.get_instance()
        settings_row.default_embedder = "operator.chosen.Embedder"
        settings_row.save()

        cfg = global_apps.get_app_config("documents")
        post_migrate.send(
            sender=cfg,
            app_config=cfg,
            verbosity=0,
            interactive=False,
            using="default",
        )

        self.assertEqual(PipelineSettings.objects.count(), 1)
        PipelineSettings.clear_cache()
        self.assertEqual(
            PipelineSettings.get_instance().default_embedder,
            "operator.chosen.Embedder",
        )
