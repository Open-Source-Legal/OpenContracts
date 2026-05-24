"""Regression tests for ``PipelineSettings`` singleton cache isolation across tests.

The autouse ``_invalidate_pipeline_settings_singleton_cache`` fixture in
``opencontractserver/conftest.py`` guarantees that every test starts with a
fresh DB read of the singleton, even if a previous test on the same xdist
worker explicitly populated the cache with non-default values (most commonly
``PipelineSettings.objects.all().delete()`` followed by
``PipelineSettings.objects.create(id=1)`` with an empty ``default_embedder``).

These tests are intentionally ordered: the first one pollutes the cache the
way a real test would; the second one then asserts the autouse fixture
restored the migration-seeded ``default_embedder`` for the next test.

Historical symptom: a flaky ``ValueError: get_embedder() resolved no
embedder_path`` in ``TestPydanticAIConversationAdaptersAsync``,
``TestDuplicateToolRegistration``, and ``TestApprovalFlow`` whenever a
``test_pipeline_component_base.py`` class happened to schedule on the same
worker first.
"""

from django.conf import settings
from django.test import TestCase

from opencontractserver.documents.models import PipelineSettings


class PipelineSettingsCacheIsolationTests(TestCase):
    """Two-test sequence that proves cache pollution does not survive between tests."""

    def test_a_pollute_cache_with_empty_default_embedder(self):
        """First test: empty out the singleton and force the cache to remember it.

        Mimics what ``TestPipelineComponentBaseSettings.setUp`` does in
        ``test_pipeline_component_base.py``. The mutation happens inside this
        test's transaction; when the transaction rolls back, the DB returns
        to the migration-seeded state but the cache holds the empty Python
        instance until something invalidates it.
        """
        PipelineSettings.objects.all().delete()
        PipelineSettings.objects.create(id=1)
        # Force the cache to remember the polluted-empty instance.
        polluted = PipelineSettings.get_instance(use_cache=True)
        self.assertEqual(polluted.default_embedder, "")

    def test_b_next_test_sees_migration_seeded_default_embedder(self):
        """Second test: the autouse fixture must have cleared the polluted cache.

        Without the autouse ``_invalidate_pipeline_settings_singleton_cache``
        fixture, the cache from the previous test would still hold the empty
        instance and ``get_instance()`` would return ``default_embedder=""`` —
        which is exactly the failure mode the historical bug produced.

        With the fixture, the cache is empty entering this test, so
        ``get_instance()`` re-reads from the DB (where the migration-seeded
        row still has ``default_embedder=settings.DEFAULT_EMBEDDER``) and
        repopulates the cache.
        """
        instance = PipelineSettings.get_instance(use_cache=True)
        self.assertEqual(instance.default_embedder, settings.DEFAULT_EMBEDDER)
