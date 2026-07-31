"""
Tests for Issue #437: Embedder Consistency Management.

Covers:
- Corpus.preferred_embedder auto-population from default embedder on creation
- Corpus.created_with_embedder audit field
- Immutability of preferred_embedder after documents are added
- ReEmbedCorpus mutation
- Fork with embedder override
- Startup system check for default embedder changes
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.utils import get_default_embedder_path

User = get_user_model()


# ---------------------------------------------------------------------------
# Model-level tests
# ---------------------------------------------------------------------------


class TestCorpusEmbedderAutoPopulation(TestCase):
    """Test that preferred_embedder is frozen at corpus creation time."""

    def setUp(self):
        self.user = User.objects.create_user(username="embedtest", password="testpass")

    def test_preferred_embedder_auto_populated_from_default(self):
        """Corpus without explicit embedder gets default embedder frozen."""
        corpus = Corpus.objects.create(title="Auto Embed", creator=self.user)
        self.assertEqual(corpus.preferred_embedder, get_default_embedder_path())

    def test_created_with_embedder_set_on_creation(self):
        """created_with_embedder is set automatically and matches preferred."""
        corpus = Corpus.objects.create(title="Audit Trail", creator=self.user)
        self.assertEqual(corpus.created_with_embedder, get_default_embedder_path())

    def test_explicit_embedder_preserved(self):
        """Corpus with explicit embedder keeps it, not the default."""
        custom_path = "my.custom.Embedder"
        corpus = Corpus.objects.create(
            title="Custom Embed",
            creator=self.user,
            preferred_embedder=custom_path,
        )
        self.assertEqual(corpus.preferred_embedder, custom_path)
        self.assertEqual(corpus.created_with_embedder, custom_path)

    @patch(
        "opencontractserver.pipeline.utils.get_default_embedder_path",
        return_value="opencontractserver.pipeline.embedders.test_embedder.TestEmbedder",
    )
    def test_auto_population_uses_current_default(self, _mock_path):
        """Auto-population uses the default embedder from PipelineSettings."""
        corpus = Corpus.objects.create(title="Current Default", creator=self.user)
        self.assertEqual(
            corpus.preferred_embedder,
            "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder",
        )

    @patch(
        "opencontractserver.pipeline.utils.get_default_embedder_path",
        return_value="",
    )
    def test_auto_population_with_empty_default(self, _mock_path):
        """When default embedder is empty string and preferred_embedder is None,
        preferred_embedder is set to empty string (not left as None)."""
        corpus = Corpus.objects.create(title="Empty Default", creator=self.user)
        self.assertEqual(corpus.preferred_embedder, "")

    def test_explicit_empty_string_embedder_preserved(self):
        """Corpus with explicit empty-string embedder keeps it, not the default."""
        corpus = Corpus.objects.create(
            title="Explicit Empty",
            creator=self.user,
            preferred_embedder="",
        )
        self.assertEqual(corpus.preferred_embedder, "")

    def test_created_with_embedder_not_changed_on_update(self):
        """created_with_embedder doesn't change when corpus is updated."""
        corpus = Corpus.objects.create(title="Immutable Audit", creator=self.user)
        original = corpus.created_with_embedder

        corpus.title = "Updated Title"
        corpus.save()
        corpus.refresh_from_db()

        self.assertEqual(corpus.created_with_embedder, original)


class TestCorpusHasDocuments(TestCase):
    """Test the has_documents() helper method."""

    def setUp(self):
        self.user = User.objects.create_user(username="hasdoctest", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_empty_corpus_has_no_documents(self):
        self.assertFalse(self.corpus.has_documents())


# ---------------------------------------------------------------------------
# Mutation-level tests
# ---------------------------------------------------------------------------


class TestUpdateCorpusEmbedderImmutability(TestCase):
    """Test that UpdateCorpusMutation rejects embedder changes after documents."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mutationtest", password="testpass"
        )
        self.corpus = Corpus.objects.create(
            title="Mutation Test",
            creator=self.user,
            preferred_embedder="old.Embedder",
        )
        # Grant permissions
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        set_permissions_for_obj_to_user(
            self.user,
            self.corpus,
            [PermissionTypes.CRUD, PermissionTypes.PUBLISH, PermissionTypes.PERMISSION],
        )
        self.factory = RequestFactory()

    def _execute_mutation(self, mutation_str, variables=None):
        """Execute a GraphQL mutation."""
        from config.graphql.schema import schema
        from config.graphql.testing import Client as GrapheneClient

        request = self.factory.post("/graphql")
        request.user = self.user
        client = GrapheneClient(schema)
        return client.execute(mutation_str, variables=variables, context_value=request)

    def test_embedder_change_allowed_on_empty_corpus(self):
        """Changing preferred_embedder is allowed when corpus has no documents."""
        from graphql_relay import to_global_id

        global_id = to_global_id("CorpusType", self.corpus.pk)
        mutation = """
            mutation UpdateCorpus($id: String!, $preferredEmbedder: String) {
                updateCorpus(id: $id, preferredEmbedder: $preferredEmbedder) {
                    ok
                    message
                }
            }
        """
        result = self._execute_mutation(
            mutation,
            variables={"id": global_id, "preferredEmbedder": "new.Embedder"},
        )
        data = result.get("data", {}).get("updateCorpus", {})
        self.assertTrue(data.get("ok"), f"Mutation failed: {data}")

        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.preferred_embedder, "new.Embedder")

    def test_embedder_change_rejected_with_documents(self):
        """Changing preferred_embedder is rejected when corpus has documents."""
        from graphql_relay import to_global_id

        from opencontractserver.documents.models import Document, DocumentPath

        # Add a document to the corpus
        doc = Document.objects.create(title="Test Doc", creator=self.user)
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/docs/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        global_id = to_global_id("CorpusType", self.corpus.pk)
        mutation = """
            mutation UpdateCorpus($id: String!, $preferredEmbedder: String) {
                updateCorpus(id: $id, preferredEmbedder: $preferredEmbedder) {
                    ok
                    message
                }
            }
        """
        result = self._execute_mutation(
            mutation,
            variables={"id": global_id, "preferredEmbedder": "new.Embedder"},
        )
        data = result.get("data", {}).get("updateCorpus", {})
        self.assertFalse(data.get("ok"))
        self.assertIn("Cannot change preferred_embedder", data.get("message", ""))

        # Verify embedder was not changed
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.preferred_embedder, "old.Embedder")

    def test_same_embedder_value_allowed_with_documents(self):
        """Setting preferred_embedder to same value is allowed even with docs."""
        from graphql_relay import to_global_id

        from opencontractserver.documents.models import Document, DocumentPath

        doc = Document.objects.create(title="Test Doc", creator=self.user)
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/docs/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        global_id = to_global_id("CorpusType", self.corpus.pk)
        mutation = """
            mutation UpdateCorpus($id: String!, $preferredEmbedder: String) {
                updateCorpus(id: $id, preferredEmbedder: $preferredEmbedder) {
                    ok
                    message
                }
            }
        """
        result = self._execute_mutation(
            mutation,
            variables={"id": global_id, "preferredEmbedder": "old.Embedder"},
        )
        data = result.get("data", {}).get("updateCorpus", {})
        self.assertTrue(data.get("ok"), f"Mutation failed: {data}")


class TestReEmbedCorpusMutation(TestCase):
    """Test the ReEmbedCorpus mutation."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="reembedtest", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", password="testpass"
        )
        self.corpus = Corpus.objects.create(
            title="ReEmbed Test",
            creator=self.user,
            preferred_embedder="old.Embedder",
        )
        self.factory = RequestFactory()

    def _execute_mutation(self, mutation_str, variables=None, user=None):
        from config.graphql.schema import schema
        from config.graphql.testing import Client as GrapheneClient

        request = self.factory.post("/graphql")
        request.user = user or self.user
        client = GrapheneClient(schema)
        return client.execute(mutation_str, variables=variables, context_value=request)

    @patch("opencontractserver.tasks.corpus_tasks.reembed_corpus.delay")
    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    def test_reembed_dispatches_task(self, mock_get_component, mock_delay):
        """ReEmbedCorpus locks corpus and dispatches background task."""
        from graphql_relay import to_global_id

        mock_get_component.return_value = type(
            "FakeEmbedder", (BaseEmbedder,), {"vector_size": 384}
        )

        mutation = """
            mutation ReEmbed($corpusId: String!, $newEmbedder: String!) {
                reEmbedCorpus(corpusId: $corpusId, newEmbedder: $newEmbedder) {
                    ok
                    message
                }
            }
        """
        global_id = to_global_id("CorpusType", self.corpus.pk)
        result = self._execute_mutation(
            mutation,
            variables={
                "corpusId": global_id,
                "newEmbedder": "new.Embedder",
            },
        )
        data = result.get("data", {}).get("reEmbedCorpus", {})
        self.assertTrue(data.get("ok"), f"Mutation failed: {data}")

        # Corpus should be locked
        self.corpus.refresh_from_db()
        self.assertTrue(self.corpus.backend_lock)

    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    def test_reembed_rejects_non_creator(self, mock_get_component):
        """Only the corpus creator can trigger re-embedding."""
        from graphql_relay import to_global_id

        mock_get_component.return_value = type(
            "FakeEmbedder", (BaseEmbedder,), {"vector_size": 384}
        )

        mutation = """
            mutation ReEmbed($corpusId: String!, $newEmbedder: String!) {
                reEmbedCorpus(corpusId: $corpusId, newEmbedder: $newEmbedder) {
                    ok
                    message
                }
            }
        """
        global_id = to_global_id("CorpusType", self.corpus.pk)
        result = self._execute_mutation(
            mutation,
            variables={
                "corpusId": global_id,
                "newEmbedder": "new.Embedder",
            },
            user=self.other_user,
        )
        data = result.get("data", {}).get("reEmbedCorpus", {})
        self.assertFalse(data.get("ok"))

    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    def test_reembed_noop_when_same_embedder(self, mock_get_component):
        """ReEmbedCorpus is a no-op when the embedder hasn't changed."""
        from graphql_relay import to_global_id

        mock_get_component.return_value = type(
            "FakeEmbedder", (BaseEmbedder,), {"vector_size": 384}
        )

        mutation = """
            mutation ReEmbed($corpusId: String!, $newEmbedder: String!) {
                reEmbedCorpus(corpusId: $corpusId, newEmbedder: $newEmbedder) {
                    ok
                    message
                }
            }
        """
        global_id = to_global_id("CorpusType", self.corpus.pk)
        result = self._execute_mutation(
            mutation,
            variables={
                "corpusId": global_id,
                "newEmbedder": "old.Embedder",
            },
        )
        data = result.get("data", {}).get("reEmbedCorpus", {})
        self.assertTrue(data.get("ok"))
        self.assertIn("already uses", data.get("message", ""))

    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    def test_reembed_rejects_locked_corpus(self, mock_get_component):
        """ReEmbedCorpus rejects when corpus is already locked."""
        from graphql_relay import to_global_id

        mock_get_component.return_value = type(
            "FakeEmbedder", (BaseEmbedder,), {"vector_size": 384}
        )

        self.corpus.backend_lock = True
        self.corpus.save()

        mutation = """
            mutation ReEmbed($corpusId: String!, $newEmbedder: String!) {
                reEmbedCorpus(corpusId: $corpusId, newEmbedder: $newEmbedder) {
                    ok
                    message
                }
            }
        """
        global_id = to_global_id("CorpusType", self.corpus.pk)
        result = self._execute_mutation(
            mutation,
            variables={
                "corpusId": global_id,
                "newEmbedder": "new.Embedder",
            },
        )
        data = result.get("data", {}).get("reEmbedCorpus", {})
        self.assertFalse(data.get("ok"))
        self.assertIn("locked", data.get("message", ""))

    def test_reembed_rejects_invalid_embedder(self):
        """ReEmbedCorpus rejects when the embedder path is invalid."""
        from graphql_relay import to_global_id

        mutation = """
            mutation ReEmbed($corpusId: String!, $newEmbedder: String!) {
                reEmbedCorpus(corpusId: $corpusId, newEmbedder: $newEmbedder) {
                    ok
                    message
                }
            }
        """
        global_id = to_global_id("CorpusType", self.corpus.pk)
        result = self._execute_mutation(
            mutation,
            variables={
                "corpusId": global_id,
                "newEmbedder": "totally.nonexistent.Embedder",
            },
        )
        data = result.get("data", {}).get("reEmbedCorpus", {})
        self.assertFalse(data.get("ok"))


# ---------------------------------------------------------------------------
# Re-embed task tests
# ---------------------------------------------------------------------------


class TestReEmbedCorpusTask(TestCase):
    """Test the reembed_corpus Celery task."""

    def setUp(self):
        self.user = User.objects.create_user(username="tasktest", password="testpass")
        self.corpus = Corpus.objects.create(
            title="Task Test",
            creator=self.user,
            preferred_embedder="old.Embedder",
            backend_lock=True,
        )

    @patch(
        "opencontractserver.tasks.embeddings_task.calculate_embeddings_for_annotation_batch.delay"
    )
    def test_reembed_updates_preferred_embedder(self, mock_batch_delay):
        """Task updates corpus.preferred_embedder to the new value."""
        from opencontractserver.tasks.corpus_tasks import reembed_corpus

        result = reembed_corpus(self.corpus.pk, "new.Embedder")

        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.preferred_embedder, "new.Embedder")
        self.assertFalse(self.corpus.backend_lock)  # Unlocked
        self.assertEqual(result["errors"], [])

    @patch(
        "opencontractserver.tasks.embeddings_task.calculate_embeddings_for_annotation_batch.delay"
    )
    def test_reembed_queues_batches_for_missing_embeddings(self, mock_batch_delay):
        """Task queues batch embedding tasks for annotations missing the new embedder."""
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import Document, DocumentPath

        # Create a document with an annotation
        doc = Document.objects.create(title="Test Doc", creator=self.user)
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        Annotation.objects.create(
            raw_text="Test annotation",
            document=doc,
            corpus=self.corpus,
            creator=self.user,
        )

        from opencontractserver.tasks.corpus_tasks import reembed_corpus

        result = reembed_corpus(self.corpus.pk, "new.Embedder")

        self.assertEqual(result["total_annotations"], 1)
        self.assertEqual(result["already_embedded"], 0)
        self.assertGreater(result["tasks_queued"], 0)
        mock_batch_delay.assert_called()

    def test_reembed_nonexistent_corpus(self):
        """Task handles nonexistent corpus gracefully."""
        from opencontractserver.tasks.corpus_tasks import reembed_corpus

        result = reembed_corpus(99999, "new.Embedder")
        self.assertIn("Corpus not found", result["errors"])

    @patch(
        "opencontractserver.tasks.embeddings_task.calculate_embeddings_for_annotation_batch.delay"
    )
    def test_reembed_unlocks_on_error(self, mock_batch_delay):
        """Corpus is unlocked even if the task encounters an error."""
        mock_batch_delay.side_effect = Exception("Task queue error")

        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import Document, DocumentPath

        doc = Document.objects.create(title="Test Doc", creator=self.user)
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        Annotation.objects.create(
            raw_text="Test annotation",
            document=doc,
            corpus=self.corpus,
            creator=self.user,
        )

        from opencontractserver.tasks.corpus_tasks import reembed_corpus

        result = reembed_corpus(self.corpus.pk, "new.Embedder")

        self.corpus.refresh_from_db()
        self.assertFalse(self.corpus.backend_lock)
        self.assertTrue(self.corpus.error)
        self.assertGreater(len(result["errors"]), 0)

    @patch(
        "opencontractserver.tasks.embeddings_task.calculate_embeddings_for_annotation_batch.delay"
    )
    def test_reembed_skips_already_embedded_annotations(self, mock_batch_delay):
        """Task skips annotations that already have embeddings for the new embedder."""
        from opencontractserver.annotations.models import Annotation, Embedding
        from opencontractserver.documents.models import Document, DocumentPath

        doc = Document.objects.create(title="Test Doc", creator=self.user)
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        ann = Annotation.objects.create(
            raw_text="Already embedded",
            document=doc,
            corpus=self.corpus,
            creator=self.user,
        )
        # Pre-create embedding for the target embedder
        Embedding.objects.create(
            annotation=ann,
            embedder_path="new.Embedder",
            creator=self.user,
        )

        from opencontractserver.tasks.corpus_tasks import reembed_corpus

        result = reembed_corpus(self.corpus.pk, "new.Embedder")

        self.assertEqual(result["total_annotations"], 1)
        self.assertEqual(result["already_embedded"], 1)
        self.assertEqual(result["tasks_queued"], 0)
        mock_batch_delay.assert_not_called()

    @patch(
        "opencontractserver.tasks.embeddings_task.calculate_embeddings_for_annotation_batch.delay"
    )
    def test_reembed_includes_structural_annotations(self, mock_batch_delay):
        """Task includes structural annotations linked via StructuralAnnotationSet."""
        from opencontractserver.annotations.models import (
            Annotation,
            StructuralAnnotationSet,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        # Create structural annotation set and link it to a document
        sas = StructuralAnnotationSet.objects.create(
            content_hash="testhash123",
            creator=self.user,
        )
        doc = Document.objects.create(
            title="Structural Doc",
            creator=self.user,
            structural_annotation_set=sas,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        # Create a structural annotation (belongs to the set, not the doc directly)
        Annotation.objects.create(
            raw_text="Structural annotation",
            structural_set=sas,
            structural=True,
            creator=self.user,
        )
        # Also create a regular corpus annotation
        Annotation.objects.create(
            raw_text="Regular annotation",
            document=doc,
            corpus=self.corpus,
            creator=self.user,
        )

        from opencontractserver.tasks.corpus_tasks import reembed_corpus

        result = reembed_corpus(self.corpus.pk, "new.Embedder")

        # Both annotations should be found
        self.assertEqual(result["total_annotations"], 2)
        self.assertGreater(result["tasks_queued"], 0)

    @patch(
        "opencontractserver.tasks.embeddings_task.calculate_embeddings_for_annotation_batch.delay"
    )
    def test_reembed_caps_task_queue(self, mock_batch_delay):
        """Task respects MAX_REEMBED_TASKS_PER_RUN to prevent queue flooding."""
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import Document, DocumentPath

        doc = Document.objects.create(title="Test Doc", creator=self.user)
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        # Create enough annotations to exceed the cap when batch size = 1
        for i in range(5):
            Annotation.objects.create(
                raw_text=f"Annotation {i}",
                document=doc,
                corpus=self.corpus,
                creator=self.user,
            )

        from opencontractserver.tasks.corpus_tasks import reembed_corpus

        # Set a very low cap for testing
        with patch(
            "opencontractserver.constants.document_processing.MAX_REEMBED_TASKS_PER_RUN",
            2,
        ), patch(
            "opencontractserver.constants.document_processing.EMBEDDING_BATCH_SIZE", 1
        ):
            result = reembed_corpus(self.corpus.pk, "new.Embedder")

        self.assertEqual(result["tasks_queued"], 2)
        self.assertTrue(result["capped"])
        self.assertEqual(mock_batch_delay.call_count, 2)


# ---------------------------------------------------------------------------
# Concurrent re-embedding test (Critique #9)
# ---------------------------------------------------------------------------


class TestConcurrentReEmbedRejection(TestCase):
    """Test that concurrent re-embed operations on the same corpus are rejected."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="concurrent_test", password="testpass"
        )
        self.corpus = Corpus.objects.create(
            title="Concurrent Test",
            creator=self.user,
            preferred_embedder="old.Embedder",
        )
        self.factory = RequestFactory()

    def _execute_mutation(self, mutation_str, variables=None):
        from config.graphql.schema import schema
        from config.graphql.testing import Client as GrapheneClient

        request = self.factory.post("/graphql")
        request.user = self.user
        client = GrapheneClient(schema)
        return client.execute(mutation_str, variables=variables, context_value=request)

    @patch("opencontractserver.tasks.corpus_tasks.reembed_corpus.delay")
    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    def test_second_reembed_rejected_while_first_running(
        self, mock_get_component, mock_delay
    ):
        """The second re-embed attempt fails when the corpus is already locked."""
        from graphql_relay import to_global_id

        mock_get_component.return_value = type(
            "FakeEmbedder", (BaseEmbedder,), {"vector_size": 384}
        )

        global_id = to_global_id("CorpusType", self.corpus.pk)
        mutation = """
            mutation ReEmbed($corpusId: String!, $newEmbedder: String!) {
                reEmbedCorpus(corpusId: $corpusId, newEmbedder: $newEmbedder) {
                    ok
                    message
                }
            }
        """
        variables = {"corpusId": global_id, "newEmbedder": "new.Embedder"}

        # First request should succeed
        result1 = self._execute_mutation(mutation, variables=variables)
        data1 = result1.get("data", {}).get("reEmbedCorpus", {})
        self.assertTrue(data1.get("ok"), f"First re-embed failed: {data1}")

        # Corpus should now be locked
        self.corpus.refresh_from_db()
        self.assertTrue(self.corpus.backend_lock)

        # Second request should be rejected because corpus is locked
        result2 = self._execute_mutation(mutation, variables=variables)
        data2 = result2.get("data", {}).get("reEmbedCorpus", {})
        self.assertFalse(data2.get("ok"))
        self.assertIn("locked", data2.get("message", ""))


# ---------------------------------------------------------------------------
# System check tests
# ---------------------------------------------------------------------------


class TestEmbedderConsistencyCheck(TestCase):
    """Test the startup system check for default embedder changes."""

    def setUp(self):
        self.user = User.objects.create_user(username="checktest", password="testpass")

    def test_no_warning_when_embedders_match(self):
        """No warning when all corpuses match the default embedder."""
        from opencontractserver.corpuses.checks import (
            check_default_embedder_consistency,
        )

        Corpus.objects.create(
            title="Matching",
            creator=self.user,
            created_with_embedder=get_default_embedder_path(),
        )
        warnings = check_default_embedder_consistency(None)
        # Should not contain W002
        w002 = [w for w in warnings if w.id == "opencontracts.W002"]
        self.assertEqual(len(w002), 0)

    def test_warning_when_embedders_mismatch(self):
        """Warning when corpuses were created with a different embedder."""
        from opencontractserver.corpuses.checks import (
            check_default_embedder_consistency,
        )

        Corpus.objects.create(
            title="Mismatched",
            creator=self.user,
            preferred_embedder="some.other.Embedder",
            created_with_embedder="some.other.Embedder",
        )
        warnings = check_default_embedder_consistency(None)
        w002 = [w for w in warnings if w.id == "opencontracts.W002"]
        self.assertEqual(len(w002), 1)
        self.assertIn("1 corpus(es)", str(w002[0].msg))


# ---------------------------------------------------------------------------
# Fork with embedder override tests
# ---------------------------------------------------------------------------


class TestForkWithEmbedderOverride(TestCase):
    """Test that StartCorpusFork accepts and applies preferred_embedder override."""

    def setUp(self):
        self.user = User.objects.create_user(username="forktest", password="testpass")
        self.corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.user,
            preferred_embedder="original.Embedder",
        )
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        set_permissions_for_obj_to_user(
            self.user,
            self.corpus,
            [PermissionTypes.CRUD, PermissionTypes.PUBLISH, PermissionTypes.PERMISSION],
        )
        self.factory = RequestFactory()

    def _execute_mutation(self, mutation_str, variables=None):
        from config.graphql.schema import schema
        from config.graphql.testing import Client as GrapheneClient

        request = self.factory.post("/graphql")
        request.user = self.user
        client = GrapheneClient(schema)
        return client.execute(mutation_str, variables=variables, context_value=request)

    @patch("opencontractserver.tasks.fork_tasks.fork_corpus.si")
    def test_fork_with_embedder_override(self, mock_fork_si):
        """Forking with preferred_embedder sets the new embedder on the forked corpus."""
        from graphql_relay import to_global_id

        # Mock the celery task chain to prevent actual task execution
        mock_task = mock_fork_si.return_value
        mock_task.apply_async.return_value = None

        global_id = to_global_id("CorpusType", self.corpus.pk)
        mutation = """
            mutation ForkCorpus($corpusId: String!, $preferredEmbedder: String) {
                forkCorpus(corpusId: $corpusId, preferredEmbedder: $preferredEmbedder) {
                    ok
                    message
                    newCorpus {
                        id
                        preferredEmbedder
                    }
                }
            }
        """
        result = self._execute_mutation(
            mutation,
            variables={
                "corpusId": global_id,
                "preferredEmbedder": "new.fork.Embedder",
            },
        )
        data = result.get("data", {}).get("forkCorpus", {})
        self.assertTrue(data.get("ok"), f"Fork failed: {data}")

        # Check the forked corpus has the new embedder
        new_corpus_data = data.get("newCorpus", {})
        self.assertEqual(new_corpus_data.get("preferredEmbedder"), "new.fork.Embedder")

    @patch("opencontractserver.tasks.fork_tasks.fork_corpus.si")
    def test_fork_without_embedder_inherits_source(self, mock_fork_si):
        """Forking without preferred_embedder inherits from source corpus."""
        from graphql_relay import to_global_id

        mock_task = mock_fork_si.return_value
        mock_task.apply_async.return_value = None

        global_id = to_global_id("CorpusType", self.corpus.pk)
        mutation = """
            mutation ForkCorpus($corpusId: String!) {
                forkCorpus(corpusId: $corpusId) {
                    ok
                    newCorpus {
                        preferredEmbedder
                    }
                }
            }
        """
        result = self._execute_mutation(mutation, variables={"corpusId": global_id})
        data = result.get("data", {}).get("forkCorpus", {})
        self.assertTrue(data.get("ok"), f"Fork failed: {data}")

        new_corpus_data = data.get("newCorpus", {})
        self.assertEqual(new_corpus_data.get("preferredEmbedder"), "original.Embedder")


# ---------------------------------------------------------------------------
# Migration backfill test
# ---------------------------------------------------------------------------


class TestMigrationBackfill(TestCase):
    """Test that the migration backfill logic works correctly."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="migratetest", password="testpass"
        )

    def test_new_corpus_has_both_fields_populated(self):
        """New corpus has both preferred_embedder and created_with_embedder set."""
        corpus = Corpus.objects.create(title="New Corpus", creator=self.user)
        self.assertIsNotNone(corpus.preferred_embedder)
        self.assertIsNotNone(corpus.created_with_embedder)
        self.assertEqual(corpus.preferred_embedder, corpus.created_with_embedder)


# ---------------------------------------------------------------------------
# Resuming a capped re-embed
# ---------------------------------------------------------------------------


class TestReEmbedCorpusResume(TestCase):
    """``reEmbedCorpus`` must be able to finish what a capped run started.

    ``reembed_corpus`` writes ``preferred_embedder`` *before* queueing work and
    caps each dispatch at ``MAX_REEMBED_TASKS_PER_RUN``. A corpus larger than
    that cap therefore ends its first run already labelled with the new
    embedder while most of its annotations still carry the old one. A no-op
    guard that compares only the embedder path then refuses every retry --
    answering ``ok: true`` -- and the corpus stays half-migrated permanently,
    with the unembedded tail invisible to vector search and nothing surfacing
    the problem.
    """

    MUTATION = """
        mutation ReEmbed($corpusId: String!, $newEmbedder: String!) {
            reEmbedCorpus(corpusId: $corpusId, newEmbedder: $newEmbedder) {
                ok
                message
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="reembedresume", password="testpass"
        )
        self.corpus = Corpus.objects.create(
            title="Half Migrated",
            creator=self.user,
            preferred_embedder="new.Embedder",
        )
        self.factory = RequestFactory()

    def _execute(self, variables):
        """Run the mutation and actually fire its ``on_commit`` callbacks.

        The dispatch is registered with ``transaction.on_commit``, and
        ``TestCase`` wraps each test in a transaction it rolls back — so
        without ``captureOnCommitCallbacks`` the task is never called and a
        test asserting the dispatch fails against perfectly correct code.
        """
        from config.graphql.schema import schema
        from config.graphql.testing import Client as GrapheneClient

        request = self.factory.post("/graphql")
        request.user = self.user
        client = GrapheneClient(schema)
        with self.captureOnCommitCallbacks(execute=True):
            result = client.execute(
                self.MUTATION, variables=variables, context_value=request
            )
        return result

    def _add_unembedded_annotation(self):
        """Put one annotation in the corpus with no embedding of any kind."""
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import Document, DocumentPath

        document = Document.objects.create(
            title="Doc", description="d", creator=self.user
        )
        DocumentPath.objects.create(
            corpus=self.corpus,
            document=document,
            path="/documents/doc.txt",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        Annotation.objects.create(
            document=document,
            raw_text="unembedded text",
            creator=self.user,
        )

    @patch("opencontractserver.tasks.corpus_tasks.reembed_corpus.delay")
    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    def test_resumes_when_annotations_still_lack_the_embedder(
        self, mock_get_component, mock_delay
    ):
        from graphql_relay import to_global_id

        mock_get_component.return_value = type(
            "FakeEmbedder", (BaseEmbedder,), {"vector_size": 384}
        )
        self._add_unembedded_annotation()

        data = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
                "newEmbedder": "new.Embedder",
            }
        )["data"]["reEmbedCorpus"]

        self.assertTrue(data["ok"], data)
        self.assertIn("Resuming", data["message"])
        # The dispatch is the assertion that matters: without it the remaining
        # annotations are never embedded, whatever the message says.
        mock_delay.assert_called_once()

    @patch("opencontractserver.tasks.corpus_tasks.reembed_corpus.delay")
    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    def test_blank_text_annotations_do_not_block_completion(
        self, mock_get_component, mock_delay
    ):
        """An un-embeddable annotation must not make the corpus look unfinished.

        Real corpora carry a tail of blank ``raw_text`` rows (layout fragments)
        that the embedding pipeline skips and therefore can never embed. If the
        outstanding count included them, a fully-migrated corpus would report
        work remaining forever and re-dispatch on every call.
        """
        from graphql_relay import to_global_id

        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import Document, DocumentPath

        mock_get_component.return_value = type(
            "FakeEmbedder", (BaseEmbedder,), {"vector_size": 384}
        )
        document = Document.objects.create(
            title="Doc", description="d", creator=self.user
        )
        DocumentPath.objects.create(
            corpus=self.corpus,
            document=document,
            path="/documents/blank.txt",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        # A lone space and a form feed: real parser artefacts, and both blank
        # once stripped. SQL TRIM would miss the form feed, so this pins the
        # whitespace match rather than just the empty string.
        for blank in ("", " ", "\x0c"):
            Annotation.objects.create(
                document=document, raw_text=blank, creator=self.user
            )

        data = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
                "newEmbedder": "new.Embedder",
            }
        )["data"]["reEmbedCorpus"]

        self.assertIn("No re-embedding needed", data["message"])
        mock_delay.assert_not_called()

    @patch("opencontractserver.tasks.corpus_tasks.reembed_corpus.delay")
    @patch("opencontractserver.pipeline.utils.get_component_by_name")
    def test_still_a_noop_when_nothing_is_outstanding(
        self, mock_get_component, mock_delay
    ):
        """The original no-op behaviour survives for a fully-migrated corpus."""
        from graphql_relay import to_global_id

        mock_get_component.return_value = type(
            "FakeEmbedder", (BaseEmbedder,), {"vector_size": 384}
        )

        data = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
                "newEmbedder": "new.Embedder",
            }
        )["data"]["reEmbedCorpus"]

        self.assertTrue(data["ok"], data)
        self.assertIn("No re-embedding needed", data["message"])
        mock_delay.assert_not_called()
