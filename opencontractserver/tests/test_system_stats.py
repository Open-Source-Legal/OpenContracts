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
    user: User
    corpus: Corpus
    doc: Document
    label: AnnotationLabel
    expected_corpus_count: int

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
        # Creating a user auto-provisions a personal corpus via signal, so the
        # live corpus total is the explicit corpus PLUS that personal corpus.
        # ``compute_values`` counts every corpus, so the stats must equal the
        # real total rather than a hardcoded "1" that ignores the signal.
        cls.expected_corpus_count = Corpus.objects.count()

    def test_compute_values_keys_and_counts(self):
        values = SystemStats.compute_values()
        self.assertEqual(set(values.keys()), set(SystemStats.COUNT_FIELDS))
        self.assertEqual(values["corpus_count"], self.expected_corpus_count)
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
        self.assertEqual(refreshed.corpus_count, self.expected_corpus_count)
        self.assertEqual(refreshed.annotation_count, 2)

        # Persisted, not just in-memory.
        reread = SystemStats.get()
        self.assertEqual(reread.annotation_count, 2)
        self.assertIsNotNone(reread.computed_at)

    def test_telemetry_shares_compute_values(self):
        # DRY contract: the telemetry heartbeat must build its usage payload
        # from SystemStats.compute_values() (not its own count code) so the
        # materialised snapshot and the heartbeat can never drift. Invoke the
        # heartbeat with telemetry enabled and a mocked sink, then assert every
        # SystemStats count field is emitted with the value compute_values()
        # reports — verifying the actual payload, not just that the import
        # survives.
        from unittest.mock import patch

        from django.test import override_settings

        from opencontractserver.tasks import telemetry_tasks

        expected = SystemStats.compute_values()
        with override_settings(MODE="PRODUCTION", TELEMETRY_ENABLED=True):
            with patch.object(telemetry_tasks, "record_event") as mock_event:
                payload = telemetry_tasks.send_usage_heartbeat()

        mock_event.assert_called_once()
        event_name, event_payload = mock_event.call_args[0]
        self.assertEqual(event_name, "usage_heartbeat")
        for field in SystemStats.COUNT_FIELDS:
            self.assertEqual(event_payload[field], expected[field])
        # The returned dict mirrors exactly what was sent.
        self.assertEqual(payload, event_payload)

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
        self.assertEqual(data["corpusCount"], self.expected_corpus_count)
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
        self.assertEqual(
            result["data"]["systemStats"]["corpusCount"], self.expected_corpus_count
        )
