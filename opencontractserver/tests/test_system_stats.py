"""Tests for the materialised SystemStats snapshot (issue #1908).

Covers the singleton model (``compute_values`` / ``refresh`` / ``get``), the
DRY contract that telemetry shares ``compute_values``, and the GraphQL
``systemStats`` resolver.
"""

from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import LabelType
from opencontractserver.users.models import SystemStats, User


class _Context:
    """Minimal info.context stand-in for graphene.test.Client."""

    def __init__(self, user):
        self.user = user


class TestSystemStats(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="stats-user", email="su@test.com", password="x"
        )
        cls.corpus = Corpus.objects.create(title="C", creator=cls.user)
        cls.doc = Document.objects.create(title="D", creator=cls.user)
        cls.label = AnnotationLabel.objects.create(
            text="L", creator=cls.user, label_type=LabelType.TOKEN_LABEL
        )
        # Two non-structural + one structural annotation: annotation_count is
        # non-structural only.
        for i in range(2):
            Annotation.objects.create(
                raw_text=f"a{i}",
                document=cls.doc,
                annotation_label=cls.label,
                creator=cls.user,
                structural=False,
            )
        Annotation.objects.create(
            raw_text="struct",
            document=cls.doc,
            annotation_label=cls.label,
            creator=cls.user,
            structural=True,
        )

    def test_compute_values_keys_and_counts(self):
        values = SystemStats.compute_values()
        self.assertEqual(set(values.keys()), set(SystemStats.COUNT_FIELDS))
        self.assertEqual(values["corpus_count"], 1)
        self.assertEqual(values["annotation_count"], 2)  # non-structural only
        self.assertGreaterEqual(values["user_count"], 1)

    def test_get_is_singleton(self):
        a = SystemStats.get()
        b = SystemStats.get()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.pk, SystemStats.SINGLETON_PK)
        self.assertEqual(SystemStats.objects.count(), 1)

    def test_save_pins_singleton_pk(self):
        # Even attempting a different pk collapses onto the singleton row.
        stats = SystemStats(id=99)
        stats.save()
        self.assertEqual(stats.pk, SystemStats.SINGLETON_PK)
        self.assertEqual(SystemStats.objects.count(), 1)

    def test_refresh_persists_and_stamps(self):
        before = SystemStats.get()
        self.assertIsNone(before.computed_at)

        refreshed = SystemStats.refresh()
        self.assertIsNotNone(refreshed.computed_at)
        self.assertEqual(refreshed.corpus_count, 1)
        self.assertEqual(refreshed.annotation_count, 2)

        # Persisted, not just in-memory.
        reread = SystemStats.get()
        self.assertEqual(reread.annotation_count, 2)
        self.assertIsNotNone(reread.computed_at)

    def test_telemetry_shares_compute_values(self):
        # DRY contract: the telemetry payload's count keys are exactly the
        # SystemStats count fields (telemetry adds version/age on top).
        from opencontractserver.tasks import telemetry_tasks

        self.assertTrue(
            set(SystemStats.COUNT_FIELDS).issubset(
                set(SystemStats.compute_values().keys())
            )
        )
        # The telemetry task must import SystemStats (not its own count code).
        self.assertTrue(hasattr(telemetry_tasks, "SystemStats"))

    def test_refresh_system_stats_task(self):
        from opencontractserver.tasks.stats_tasks import refresh_system_stats

        result = refresh_system_stats()
        self.assertIsNotNone(result)
        self.assertEqual(result["annotation_count"], 2)
        self.assertIn("computed_at", result)

    def test_graphql_system_stats_resolver(self):
        SystemStats.refresh()
        client = Client(schema)
        result = client.execute(
            """
            query {
              systemStats {
                corpusCount
                annotationCount
                userCount
                computedAt
              }
            }
            """,
            context_value=_Context(self.user),
        )
        self.assertNotIn("errors", result)
        data = result["data"]["systemStats"]
        self.assertEqual(data["corpusCount"], 1)
        self.assertEqual(data["annotationCount"], 2)
        self.assertIsNotNone(data["computedAt"])

    def test_graphql_system_stats_anonymous(self):
        # Global aggregates are readable without auth (landing/dashboard use).
        from django.contrib.auth.models import AnonymousUser

        SystemStats.refresh()
        client = Client(schema)
        result = client.execute(
            "query { systemStats { corpusCount } }",
            context_value=_Context(AnonymousUser()),
        )
        self.assertNotIn("errors", result)
        self.assertEqual(result["data"]["systemStats"]["corpusCount"], 1)
