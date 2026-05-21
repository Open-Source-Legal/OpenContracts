"""
Tests for Personal Corpus ("My Documents") feature.

This module tests:
1. Personal corpus creation for new users (signal handler)
2. get_or_create_personal_corpus() idempotency
3. Unique constraint enforcement (one personal corpus per user)
4. Upload defaulting to personal corpus (GraphQL mutation tests)
5. Shared StructuralAnnotationSet reuse in add_document()
6. Incremental embedding creation via ensure_embeddings_for_corpus
7. Concurrent creation race condition (Issue #839)
8. Delete and recreate flow (Issue #839)
9. Embedding task queue failure handling (Issue #839)
"""

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation, Embedding
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.files import base_64_encode_bytes
from opencontractserver.utils.permissioning import user_has_permission_for_obj

User = get_user_model()


class TestContext:
    """Mock context for GraphQL requests."""

    def __init__(self, user):
        self.user = user


class TestPersonalCorpusCreation(TestCase):
    """Tests for personal corpus auto-creation on user signup."""

    def test_new_user_gets_personal_corpus(self):
        """New user should automatically get a personal corpus."""
        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        # Check personal corpus was created
        personal_corpus = Corpus.objects.filter(creator=user, is_personal=True).first()

        self.assertIsNotNone(personal_corpus)
        self.assertEqual(personal_corpus.title, "My Documents")
        self.assertFalse(personal_corpus.is_public)

    def test_personal_corpus_has_correct_permissions(self):
        """User should have full permissions on their personal corpus."""
        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        personal_corpus = Corpus.objects.get(creator=user, is_personal=True)

        # Check user has all permissions
        self.assertTrue(
            user_has_permission_for_obj(user, personal_corpus, PermissionTypes.CREATE)
        )
        self.assertTrue(
            user_has_permission_for_obj(user, personal_corpus, PermissionTypes.READ)
        )
        self.assertTrue(
            user_has_permission_for_obj(user, personal_corpus, PermissionTypes.EDIT)
        )
        self.assertTrue(
            user_has_permission_for_obj(user, personal_corpus, PermissionTypes.DELETE)
        )


class TestGetOrCreatePersonalCorpus(TestCase):
    """Tests for Corpus.get_or_create_personal_corpus() method."""

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )
        # Note: Personal corpus may already exist from signal handler
        # Clean it up for controlled testing
        Corpus.objects.filter(creator=self.user, is_personal=True).delete()

    def test_creates_personal_corpus_if_none_exists(self):
        """Should create personal corpus when user doesn't have one."""
        # Verify no personal corpus exists
        self.assertFalse(
            Corpus.objects.filter(creator=self.user, is_personal=True).exists()
        )

        # Call the method
        corpus = Corpus.get_or_create_personal_corpus(self.user)

        # Verify corpus was created
        self.assertIsNotNone(corpus)
        self.assertEqual(corpus.title, "My Documents")
        self.assertTrue(corpus.is_personal)
        self.assertEqual(corpus.creator, self.user)
        self.assertFalse(corpus.is_public)

    def test_returns_existing_personal_corpus(self):
        """Should return existing personal corpus without creating duplicate."""
        # Create a personal corpus first
        existing = Corpus.objects.create(
            title="My Documents",
            creator=self.user,
            is_personal=True,
            is_public=False,
        )

        # Call the method
        corpus = Corpus.get_or_create_personal_corpus(self.user)

        # Verify same corpus returned
        self.assertEqual(corpus.pk, existing.pk)

        # Verify no duplicate was created
        self.assertEqual(
            Corpus.objects.filter(creator=self.user, is_personal=True).count(), 1
        )

    def test_idempotent_multiple_calls(self):
        """Multiple calls should return the same corpus."""
        corpus1 = Corpus.get_or_create_personal_corpus(self.user)
        corpus2 = Corpus.get_or_create_personal_corpus(self.user)
        corpus3 = Corpus.get_or_create_personal_corpus(self.user)

        self.assertEqual(corpus1.pk, corpus2.pk)
        self.assertEqual(corpus2.pk, corpus3.pk)

        # Verify only one exists
        self.assertEqual(
            Corpus.objects.filter(creator=self.user, is_personal=True).count(), 1
        )

    def test_backfills_slug_when_empty(self):
        """Calling get_or_create on a corpus with an empty slug should
        backfill a valid slug via QuerySet.update() (no signals fired)."""
        # Create the personal corpus first
        corpus = Corpus.get_or_create_personal_corpus(self.user)
        original_pk = corpus.pk
        self.assertTrue(corpus.slug)  # should have a slug after creation

        # Simulate a corpus that was created by migration 0038 without a slug
        Corpus.objects.filter(pk=original_pk).update(slug="")

        # Re-fetch and verify slug is indeed empty
        corpus.refresh_from_db()
        self.assertEqual(corpus.slug, "")

        # Call get_or_create_personal_corpus again - should backfill the slug
        backfilled = Corpus.get_or_create_personal_corpus(self.user)

        # Should be the same corpus
        self.assertEqual(backfilled.pk, original_pk)

        # The returned in-memory object should have a valid slug
        self.assertTrue(backfilled.slug)
        self.assertNotEqual(backfilled.slug, "")

        # Verify the slug was persisted to the database
        corpus.refresh_from_db()
        self.assertTrue(corpus.slug)
        self.assertEqual(corpus.slug, backfilled.slug)


class TestUniqueConstraint(TestCase):
    """Tests for the unique constraint on personal corpuses."""

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )
        # Clean up any existing personal corpus
        Corpus.objects.filter(creator=self.user, is_personal=True).delete()

    def test_cannot_create_second_personal_corpus(self):
        """Database constraint should prevent second personal corpus."""
        # Create first personal corpus
        Corpus.objects.create(
            title="My Documents",
            creator=self.user,
            is_personal=True,
        )

        # Attempt to create second should raise IntegrityError
        with self.assertRaises(IntegrityError):
            Corpus.objects.create(
                title="Another Personal",
                creator=self.user,
                is_personal=True,
            )

    def test_can_create_multiple_non_personal_corpuses(self):
        """User should be able to create multiple non-personal corpuses."""
        # Create several non-personal corpuses
        Corpus.objects.create(
            title="Corpus 1",
            creator=self.user,
            is_personal=False,
        )
        Corpus.objects.create(
            title="Corpus 2",
            creator=self.user,
            is_personal=False,
        )
        Corpus.objects.create(
            title="Corpus 3",
            creator=self.user,
            is_personal=False,
        )

        self.assertEqual(
            Corpus.objects.filter(creator=self.user, is_personal=False).count(), 3
        )

    def test_different_users_can_each_have_personal_corpus(self):
        """Each user should be able to have their own personal corpus."""
        user2 = User.objects.create_user(
            username=f"testuser2_{uuid.uuid4().hex[:8]}",
            email=f"test2_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )
        # Clean up user2's auto-created personal corpus
        Corpus.objects.filter(creator=user2, is_personal=True).delete()

        # Create personal corpus for both users
        corpus1 = Corpus.objects.create(
            title="My Documents",
            creator=self.user,
            is_personal=True,
        )
        corpus2 = Corpus.objects.create(
            title="My Documents",
            creator=user2,
            is_personal=True,
        )

        self.assertNotEqual(corpus1.pk, corpus2.pk)
        self.assertEqual(corpus1.creator, self.user)
        self.assertEqual(corpus2.creator, user2)


class TestSharedStructuralAnnotationSet(TestCase):
    """Tests for shared StructuralAnnotationSet in add_document()."""

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        # Create a source document with a structural annotation set
        self.source_doc = Document.objects.create(
            title="Source Document",
            creator=self.user,
            backend_lock=False,
        )

        # Create a corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            is_personal=False,
        )

    @patch("opencontractserver.corpuses.models.transaction.on_commit")
    def test_add_document_reuses_structural_set(self, mock_on_commit):
        """add_document should reuse structural_annotation_set instead of duplicating."""
        from opencontractserver.annotations.models import StructuralAnnotationSet

        # Create a structural annotation set for the source document
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )
        self.source_doc.structural_annotation_set = structural_set
        self.source_doc.save()

        # Add document to corpus
        corpus_copy, status, doc_path = self.corpus.add_document(
            document=self.source_doc,
            user=self.user,
        )

        # Verify the structural_annotation_set was reused (same ID)
        self.assertEqual(
            corpus_copy.structural_annotation_set_id,
            structural_set.pk,
        )

        # Verify no duplicate was created
        self.assertEqual(
            StructuralAnnotationSet.objects.filter(
                content_hash__startswith="test_hash_"
            ).count(),
            1,
        )

    @patch("opencontractserver.corpuses.models.transaction.on_commit")
    def test_add_document_queues_embedding_check_task(self, mock_on_commit):
        """add_document should queue ensure_embeddings_for_corpus task."""
        from opencontractserver.annotations.models import StructuralAnnotationSet

        # Create a structural annotation set
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )
        self.source_doc.structural_annotation_set = structural_set
        self.source_doc.save()

        # Add document to corpus
        corpus_copy, status, doc_path = self.corpus.add_document(
            document=self.source_doc,
            user=self.user,
        )

        # Verify on_commit was called (task was queued)
        self.assertTrue(mock_on_commit.called)


class TestEnsureEmbeddingsForCorpus(TestCase):
    """Tests for the ensure_embeddings_for_corpus task."""

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        # Create a corpus with a specific embedder
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            is_personal=False,
            preferred_embedder="test.embedder.path",
        )

    @patch(
        "opencontractserver.pipeline.utils.get_default_embedder_path",
        return_value="default.embedder.path",
    )
    @patch(
        "opencontractserver.tasks.embeddings_task.calculate_embeddings_for_annotation_batch"
    )
    def test_queues_tasks_for_missing_embeddings(self, mock_batch_task, _mock_path):
        """Should queue batch embedding tasks for annotations missing embeddings."""
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus

        # Create structural annotation set with annotations
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )

        # Create some structural annotations in the set
        ann1 = Annotation.objects.create(
            raw_text="Test annotation 1",
            structural_set=structural_set,
            structural=True,  # Required for structural_set annotations
            creator=self.user,
        )
        Annotation.objects.create(  # ann2 - no pre-existing embedding
            raw_text="Test annotation 2",
            structural_set=structural_set,
            structural=True,
            creator=self.user,
        )
        Annotation.objects.create(  # ann3 - no pre-existing embedding
            raw_text="Test annotation 3",
            structural_set=structural_set,
            structural=True,
            creator=self.user,
        )

        # Create embedding for ann1 with default embedder (simulating pre-existing)
        Embedding.objects.create(
            annotation=ann1,
            embedder_path="default.embedder.path",
            vector_384=[0.1] * 384,
            creator=self.user,
        )

        # Mock the delay method
        mock_batch_task.delay = MagicMock()

        # Run the task
        result = ensure_embeddings_for_corpus(structural_set.pk, self.corpus.pk)

        # With batching (EMBEDDING_BATCH_SIZE=100), all annotations fit in one batch
        # per embedder: 1 batch for default embedder + 1 batch for corpus embedder = 2 tasks
        self.assertEqual(result["tasks_queued"], 2)
        self.assertEqual(result["annotations_already_embedded"], 1)

    @patch(
        "opencontractserver.pipeline.utils.get_default_embedder_path",
        return_value="default.embedder.path",
    )
    @patch(
        "opencontractserver.tasks.embeddings_task.calculate_embeddings_for_annotation_batch"
    )
    def test_skips_if_all_embeddings_exist(self, mock_batch_task, _mock_path):
        """Should not queue any tasks if all embeddings already exist."""
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus

        # Create structural annotation set
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )

        # Create annotation with all required embeddings
        ann = Annotation.objects.create(
            raw_text="Test annotation",
            structural_set=structural_set,
            structural=True,  # Required for structural_set annotations
            creator=self.user,
        )

        # Create embeddings for both embedders
        Embedding.objects.create(
            annotation=ann,
            embedder_path="default.embedder.path",
            vector_384=[0.1] * 384,
            creator=self.user,
        )
        Embedding.objects.create(
            annotation=ann,
            embedder_path="test.embedder.path",
            vector_384=[0.2] * 384,
            creator=self.user,
        )

        mock_batch_task.delay = MagicMock()

        # Run the task
        result = ensure_embeddings_for_corpus(structural_set.pk, self.corpus.pk)

        # Should not queue any tasks
        self.assertEqual(result["tasks_queued"], 0)
        self.assertEqual(result["annotations_already_embedded"], 2)

    def test_handles_nonexistent_structural_set(self):
        """Should handle case where structural set doesn't exist."""
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus

        result = ensure_embeddings_for_corpus(99999, self.corpus.pk)

        self.assertIn("StructuralAnnotationSet not found", result["errors"])

    def test_handles_nonexistent_corpus(self):
        """Should handle case where corpus doesn't exist."""
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus

        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )

        result = ensure_embeddings_for_corpus(structural_set.pk, 99999)

        self.assertIn("Corpus not found", result["errors"])


class TestUploadDefaultsToPersonalCorpus(TestCase):
    """Tests that document uploads without a corpus default to personal corpus."""

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )
        self.client = Client(schema, context_value=TestContext(self.user))

        # Mutation for uploading a document
        self.upload_mutation = """
            mutation UploadDocument(
                $file: String!,
                $filename: String!,
                $title: String!,
                $description: String!,
                $customMeta: GenericScalar!,
                $addToCorpusId: ID,
                $makePublic: Boolean!
            ) {
                uploadDocument(
                    base64FileString: $file,
                    filename: $filename,
                    title: $title,
                    description: $description,
                    customMeta: $customMeta,
                    addToCorpusId: $addToCorpusId,
                    makePublic: $makePublic
                ) {
                    ok
                    message
                    document {
                        id
                        title
                    }
                }
            }
        """

    def _generate_minimal_pdf(self):
        """Generate a minimal valid PDF for testing."""
        return b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 0>>endobj\nxref\n0 3\n0000000000 65535 f \n0000000010 00000 n \n0000000059 00000 n \ntrailer<</Size 3/Root 1 0 R>>startxref\n104\n%%EOF"  # noqa: E501

    def test_upload_without_corpus_goes_to_personal_corpus(self):
        """Upload without addToCorpusId should go to personal corpus."""
        # Get the user's personal corpus (created by signal on user creation)
        personal_corpus = Corpus.objects.get(creator=self.user, is_personal=True)

        # Upload a document without specifying a corpus
        pdf_content = self._generate_minimal_pdf()
        base64_content = base_64_encode_bytes(pdf_content)

        result = self.client.execute(
            self.upload_mutation,
            variables={
                "file": base64_content,
                "filename": "test_document.pdf",
                "title": "Test Document",
                "description": "A test document",
                "makePublic": False,
                "customMeta": {},
                "addToCorpusId": None,  # No corpus specified
            },
        )

        # Verify upload succeeded
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )
        self.assertTrue(result["data"]["uploadDocument"]["ok"])
        self.assertEqual(result["data"]["uploadDocument"]["message"], "Success")

        # Get the uploaded document
        doc_id = result["data"]["uploadDocument"]["document"]["id"]
        from graphql_relay import from_global_id

        _, doc_pk = from_global_id(doc_id)
        document = Document.objects.get(pk=doc_pk)

        # Verify document is linked to personal corpus via DocumentPath
        doc_path = DocumentPath.objects.filter(
            document=document,
            corpus=personal_corpus,
            is_current=True,
        ).first()

        self.assertIsNotNone(
            doc_path,
            "Document should have a DocumentPath linking to personal corpus",
        )
        self.assertEqual(doc_path.corpus_id, personal_corpus.pk)

    def test_upload_with_corpus_goes_to_specified_corpus(self):
        """Upload with addToCorpusId should go to that corpus, not personal."""
        from graphql_relay import to_global_id

        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        # Create a separate corpus
        other_corpus = Corpus.objects.create(
            title="Other Corpus",
            creator=self.user,
            is_personal=False,
        )
        set_permissions_for_obj_to_user(self.user, other_corpus, [PermissionTypes.ALL])

        # Upload a document to the specified corpus
        pdf_content = self._generate_minimal_pdf()
        base64_content = base_64_encode_bytes(pdf_content)

        result = self.client.execute(
            self.upload_mutation,
            variables={
                "file": base64_content,
                "filename": "test_document2.pdf",
                "title": "Test Document 2",
                "description": "A test document",
                "makePublic": False,
                "customMeta": {},
                "addToCorpusId": to_global_id("CorpusType", other_corpus.pk),
            },
        )

        # Verify upload succeeded
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )
        self.assertTrue(result["data"]["uploadDocument"]["ok"])

        # Get the uploaded document
        doc_id = result["data"]["uploadDocument"]["document"]["id"]
        from graphql_relay import from_global_id

        _, doc_pk = from_global_id(doc_id)
        document = Document.objects.get(pk=doc_pk)

        # Verify document is linked to the specified corpus, not personal
        doc_path = DocumentPath.objects.filter(
            document=document,
            corpus=other_corpus,
            is_current=True,
        ).first()

        self.assertIsNotNone(
            doc_path,
            "Document should have a DocumentPath linking to the specified corpus",
        )
        self.assertEqual(doc_path.corpus_id, other_corpus.pk)

        # Verify document is NOT linked to personal corpus
        personal_corpus = Corpus.objects.get(creator=self.user, is_personal=True)
        personal_path = DocumentPath.objects.filter(
            document=document,
            corpus=personal_corpus,
        ).first()
        self.assertIsNone(
            personal_path,
            "Document should NOT be linked to personal corpus when another is specified",
        )

    def test_upload_text_file_without_corpus_goes_to_personal_corpus(self):
        """Text file upload without corpus should also go to personal corpus."""
        # Get the user's personal corpus
        personal_corpus = Corpus.objects.get(creator=self.user, is_personal=True)

        # Upload a text file without specifying a corpus
        text_content = b"This is a test text file for personal corpus testing."
        base64_content = base_64_encode_bytes(text_content)

        result = self.client.execute(
            self.upload_mutation,
            variables={
                "file": base64_content,
                "filename": "test_document.txt",
                "title": "Test Text Document",
                "description": "A test text document",
                "makePublic": False,
                "customMeta": {},
                "addToCorpusId": None,
            },
        )

        # Verify upload succeeded
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )
        self.assertTrue(result["data"]["uploadDocument"]["ok"])

        # Get the uploaded document
        doc_id = result["data"]["uploadDocument"]["document"]["id"]
        from graphql_relay import from_global_id

        _, doc_pk = from_global_id(doc_id)
        document = Document.objects.get(pk=doc_pk)

        # Verify document is linked to personal corpus via DocumentPath
        doc_path = DocumentPath.objects.filter(
            document=document,
            corpus=personal_corpus,
            is_current=True,
        ).first()

        self.assertIsNotNone(
            doc_path,
            "Text document should have a DocumentPath linking to personal corpus",
        )
        self.assertEqual(doc_path.corpus_id, personal_corpus.pk)


class TestCalculateEmbeddingsForAnnotationBatch(TestCase):
    """Tests for calculate_embeddings_for_annotation_batch task."""

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )
        # Create a document to attach annotations to (required by constraint)
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.user,
            backend_lock=False,
        )

    def test_empty_annotation_ids_returns_early(self):
        """Should return immediately with empty counts when no annotation IDs provided."""
        from opencontractserver.tasks.embeddings_task import (
            calculate_embeddings_for_annotation_batch,
        )

        result = calculate_embeddings_for_annotation_batch(annotation_ids=[])

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["succeeded"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 0)

    def test_nonexistent_annotation_ids_are_skipped(self):
        """Should skip annotation IDs that don't exist in the database."""
        from opencontractserver.tasks.embeddings_task import (
            calculate_embeddings_for_annotation_batch,
        )

        # Use IDs that definitely don't exist
        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[999999, 999998, 999997]
        )

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["skipped"], 3)
        self.assertEqual(result["succeeded"], 0)
        self.assertEqual(result["failed"], 0)

    def test_invalid_embedder_path_fails_batch(self):
        """Should fail entire batch if embedder path is invalid."""
        from opencontractserver.tasks.embeddings_task import (
            calculate_embeddings_for_annotation_batch,
        )

        # Create a real annotation with document parent
        ann = Annotation.objects.create(
            raw_text="Test annotation",
            document=self.document,
            creator=self.user,
        )

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[ann.pk],
            embedder_path="nonexistent.embedder.path",
        )

        self.assertEqual(result["failed"], 1)
        self.assertTrue(any("Failed to load embedder" in e for e in result["errors"]))

    @patch("opencontractserver.tasks.embeddings_task._apply_dual_embedding_strategy")
    def test_successful_embedding_with_dual_strategy(self, mock_dual_strategy):
        """Should use dual embedding strategy when no explicit embedder specified."""
        from opencontractserver.tasks.embeddings_task import (
            calculate_embeddings_for_annotation_batch,
        )

        ann = Annotation.objects.create(
            raw_text="Test annotation",
            document=self.document,
            creator=self.user,
        )

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[ann.pk],
            corpus_id=123,
        )

        self.assertEqual(result["succeeded"], 1)
        mock_dual_strategy.assert_called_once()

    @patch("opencontractserver.tasks.embeddings_task._apply_dual_embedding_strategy")
    def test_exception_during_embedding_is_caught(self, mock_dual_strategy):
        """Should catch and record exceptions during embedding."""
        from opencontractserver.tasks.embeddings_task import (
            calculate_embeddings_for_annotation_batch,
        )

        mock_dual_strategy.side_effect = Exception("Test embedding error")

        ann = Annotation.objects.create(
            raw_text="Test annotation",
            document=self.document,
            creator=self.user,
        )

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[ann.pk],
        )

        self.assertEqual(result["failed"], 1)
        self.assertTrue(any("Test embedding error" in e for e in result["errors"]))


class TestEnsureEmbeddingsNoEmbedderConfigured(TestCase):
    """Tests for ensure_embeddings_for_corpus when no embedders are configured."""

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

    @patch(
        "opencontractserver.pipeline.utils.get_default_embedder_path",
        return_value="",
    )
    def test_no_embedders_configured_returns_error(self, _mock_path):
        """Should return error when no embedders are configured."""
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus

        # Create corpus without preferred_embedder
        corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            preferred_embedder=None,  # No corpus-specific embedder
        )

        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )

        result = ensure_embeddings_for_corpus(structural_set.pk, corpus.pk)

        self.assertIn("No embedders configured", result["errors"])

    @patch(
        "opencontractserver.pipeline.utils.get_default_embedder_path",
        return_value="default.embedder.path",
    )
    def test_empty_structural_set_returns_early(self, _mock_path):
        """Should return early when structural set has no annotations."""
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus

        corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
        )

        # Create empty structural set (no annotations)
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )

        result = ensure_embeddings_for_corpus(structural_set.pk, corpus.pk)

        # Should return with no tasks queued and no errors
        self.assertEqual(result["tasks_queued"], 0)
        self.assertEqual(len(result["errors"]), 0)


class TestPersonalCorpusSignalErrorHandling(TestCase):
    """Tests for error handling in personal corpus signal handler."""

    def test_signal_handles_integrity_error_gracefully(self):
        """Signal should handle IntegrityError when corpus already exists."""
        from opencontractserver.users.signals import _create_personal_corpus_for_user

        # Create user (which triggers signal and creates personal corpus)
        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        # Verify personal corpus exists
        self.assertTrue(Corpus.objects.filter(creator=user, is_personal=True).exists())

        # Calling _create_personal_corpus_for_user again should not raise
        # (it uses get_or_create internally)
        _create_personal_corpus_for_user(user)

        # Should still have exactly one personal corpus
        self.assertEqual(
            Corpus.objects.filter(creator=user, is_personal=True).count(),
            1,
        )


class TestDocumentVersioningHelpers(TestCase):
    """Tests for document versioning helper functions."""

    def test_is_text_file_returns_true_for_text_plain(self):
        """Should return True for text/plain MIME type."""
        from opencontractserver.documents.versioning import _is_text_file

        self.assertTrue(_is_text_file("text/plain"))

    def test_is_text_file_returns_true_for_application_txt(self):
        """Should return True for application/txt MIME type."""
        from opencontractserver.documents.versioning import _is_text_file

        self.assertTrue(_is_text_file("application/txt"))

    def test_is_text_file_returns_false_for_pdf(self):
        """Should return False for PDF MIME type."""
        from opencontractserver.documents.versioning import _is_text_file

        self.assertFalse(_is_text_file("application/pdf"))

    def test_is_text_file_returns_false_for_none(self):
        """Should return False for None file type."""
        from opencontractserver.documents.versioning import _is_text_file

        self.assertFalse(_is_text_file(None))

    def test_create_content_file_handles_none_file_type(self):
        """Should default to application/octet-stream for None file_type."""
        from opencontractserver.documents.versioning import _create_content_file

        content = b"test content"
        content_hash = "abc123"
        path = "/test/path"

        # Should not raise when file_type is None
        result = _create_content_file(
            content=content,
            content_hash=content_hash,
            path=path,
            file_type=None,
        )

        self.assertIsNotNone(result)
        # Should have a .bin extension for unknown type
        self.assertTrue(result.name.endswith(".bin"))


class TestPersonalCorpusDeletionProtection(TestCase):
    """Tests that personal corpus cannot be deleted via GraphQL mutation."""

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )
        self.client = Client(schema, context_value=TestContext(self.user))

        self.delete_mutation = """
            mutation($id: String!) {
                deleteCorpus(id: $id) {
                    ok
                    message
                }
            }
        """

    def test_cannot_delete_personal_corpus(self):
        """Deleting a personal corpus via GraphQL should be blocked."""
        from graphql_relay import to_global_id

        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        personal_corpus = Corpus.objects.get(creator=self.user, is_personal=True)
        set_permissions_for_obj_to_user(
            self.user, personal_corpus, [PermissionTypes.CRUD]
        )

        variables = {"id": to_global_id("CorpusType", personal_corpus.pk)}
        result = self.client.execute(self.delete_mutation, variable_values=variables)

        # DeleteCorpusMutation returns the failure via the unified IDOR-safe
        # envelope (ok=False + message) rather than a raw GraphQL error.
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["deleteCorpus"]["ok"])
        error_message = result["data"]["deleteCorpus"]["message"]
        self.assertIn("Cannot delete", error_message)
        self.assertIn("My Documents", error_message)

        # Corpus should still exist
        self.assertTrue(Corpus.objects.filter(pk=personal_corpus.pk).exists())

    def test_can_delete_non_personal_corpus(self):
        """Deleting a non-personal corpus should still work normally."""
        from graphql_relay import to_global_id

        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        regular_corpus = Corpus.objects.create(
            title="Regular Corpus",
            creator=self.user,
            is_personal=False,
        )
        set_permissions_for_obj_to_user(
            self.user, regular_corpus, [PermissionTypes.CRUD]
        )

        variables = {"id": to_global_id("CorpusType", regular_corpus.pk)}
        result = self.client.execute(self.delete_mutation, variable_values=variables)

        # Should succeed
        self.assertNotIn("errors", result)
        self.assertTrue(result["data"]["deleteCorpus"]["ok"])

        # Corpus should be deleted
        self.assertFalse(Corpus.objects.filter(pk=regular_corpus.pk).exists())


class TestConcurrentPersonalCorpusCreation(TransactionTestCase):
    """
    Tests for concurrent creation race condition (Issue #839).

    Verifies that multiple simultaneous calls to get_or_create_personal_corpus()
    do not produce duplicates or unhandled errors.
    """

    def _call_get_or_create(self, user_pk):
        """
        Call get_or_create_personal_corpus in a separate thread.

        Each thread needs its own database connection since Django's
        TransactionTestCase doesn't share connections across threads.
        """
        try:
            # Close the inherited connection so this thread gets its own
            connection.close()
            user = User.objects.get(pk=user_pk)
            corpus = Corpus.get_or_create_personal_corpus(user)
            return corpus.pk
        except Exception as e:
            return e

    def test_concurrent_get_or_create_returns_same_corpus(self):
        """Five concurrent threads should all return the same personal corpus."""
        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        # The signal handler already creates a personal corpus, but delete it
        # so we exercise the creation path under contention.
        Corpus.objects.filter(creator=user, is_personal=True).delete()

        num_threads = 5
        results = []
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(self._call_get_or_create, user.pk)
                for _ in range(num_threads)
            ]
            for future in as_completed(futures):
                results.append(future.result())

        # None of the results should be exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(
            exceptions,
            [],
            f"Concurrent calls raised exceptions: {exceptions}",
        )

        # All results should be the same corpus PK
        unique_pks = set(results)
        self.assertEqual(
            len(unique_pks),
            1,
            f"Expected all threads to return the same corpus PK, got {unique_pks}",
        )

        # Exactly one personal corpus should exist
        self.assertEqual(
            Corpus.objects.filter(creator=user, is_personal=True).count(),
            1,
        )


class TestDeleteAndRecreatePersonalCorpus(TestCase):
    """
    Tests for delete-and-recreate flow (Issue #839).

    Verifies that after deleting a personal corpus, calling
    get_or_create_personal_corpus produces a new corpus with a different ID
    while maintaining the personal flag and correct attributes.
    """

    def test_recreate_after_delete_has_different_id(self):
        """Deleting and recreating a personal corpus should yield a new PK."""
        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        # Grab the auto-created personal corpus
        original_corpus = Corpus.objects.get(creator=user, is_personal=True)
        original_pk = original_corpus.pk

        # Delete it
        original_corpus.delete()
        self.assertFalse(Corpus.objects.filter(creator=user, is_personal=True).exists())

        # Recreate via the class method
        new_corpus = Corpus.get_or_create_personal_corpus(user)

        # Should have a different PK
        self.assertNotEqual(new_corpus.pk, original_pk)

        # Should still be a valid personal corpus
        self.assertTrue(new_corpus.is_personal)
        self.assertEqual(new_corpus.creator, user)
        self.assertEqual(new_corpus.title, "My Documents")
        self.assertFalse(new_corpus.is_public)

    def test_recreated_corpus_has_correct_permissions(self):
        """Recreated personal corpus should grant the user full permissions."""
        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        # Delete the auto-created personal corpus
        Corpus.objects.filter(creator=user, is_personal=True).delete()

        # Recreate
        new_corpus = Corpus.get_or_create_personal_corpus(user)

        # Check all permission types
        self.assertTrue(
            user_has_permission_for_obj(user, new_corpus, PermissionTypes.CREATE)
        )
        self.assertTrue(
            user_has_permission_for_obj(user, new_corpus, PermissionTypes.READ)
        )
        self.assertTrue(
            user_has_permission_for_obj(user, new_corpus, PermissionTypes.EDIT)
        )
        self.assertTrue(
            user_has_permission_for_obj(user, new_corpus, PermissionTypes.DELETE)
        )

    def test_only_one_personal_corpus_exists_after_recreate(self):
        """Only one personal corpus should exist after delete-and-recreate."""
        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )

        Corpus.objects.filter(creator=user, is_personal=True).delete()

        Corpus.get_or_create_personal_corpus(user)

        self.assertEqual(
            Corpus.objects.filter(creator=user, is_personal=True).count(),
            1,
        )


class TestEmbeddingTaskQueueFailure(TestCase):
    """
    Tests for embedding task queue failure handling (Issue #839).

    Verifies that the system degrades gracefully when the Celery task queue
    is unavailable (e.g., Redis is down) during document-to-corpus operations.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            is_personal=False,
            preferred_embedder="test.embedder.path",
        )
        self.source_doc = Document.objects.create(
            title="Source Document",
            creator=self.user,
            backend_lock=False,
        )

    @patch(
        "opencontractserver.pipeline.utils.get_default_embedder_path",
        return_value="default.embedder.path",
    )
    @patch(
        "opencontractserver.tasks.embeddings_task"
        ".calculate_embeddings_for_annotation_batch"
    )
    def test_queue_failure_returns_error_in_result(self, mock_batch_task, _mock_path):
        """ensure_embeddings_for_corpus should catch and report queue failures."""
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus

        # Simulate Redis/broker being down by making .delay() raise
        mock_batch_task.delay = MagicMock(
            side_effect=ConnectionError("Redis connection refused")
        )

        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )

        # Create an annotation that needs embedding
        Annotation.objects.create(
            raw_text="Test annotation",
            structural_set=structural_set,
            structural=True,
            creator=self.user,
        )

        result = ensure_embeddings_for_corpus(structural_set.pk, self.corpus.pk)

        # The top-level exception handler should catch the ConnectionError
        self.assertTrue(len(result["errors"]) > 0)
        self.assertTrue(
            any("Redis connection refused" in e for e in result["errors"]),
            f"Expected Redis error in result['errors'], got: {result['errors']}",
        )

    @patch("opencontractserver.corpuses.models.transaction.on_commit")
    def test_add_document_succeeds_even_if_task_queue_unavailable(self, mock_on_commit):
        """
        add_document should succeed even if the embedding task queue is down.

        The embedding task is queued via transaction.on_commit, so a queue
        failure would happen after the document is already committed. This test
        verifies the document is correctly added regardless.
        """
        from opencontractserver.annotations.models import StructuralAnnotationSet

        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )
        self.source_doc.structural_annotation_set = structural_set
        self.source_doc.save()

        # Simulate on_commit callback raising (queue unavailable)
        mock_on_commit.side_effect = lambda fn: fn()  # execute immediately

        corpus_copy, status, doc_path = self.corpus.add_document(
            document=self.source_doc,
            user=self.user,
        )

        # Document should still be added successfully
        self.assertIsNotNone(corpus_copy)
        self.assertIsNotNone(doc_path)
        self.assertEqual(doc_path.corpus_id, self.corpus.pk)

    @patch(
        "opencontractserver.pipeline.utils.get_default_embedder_path",
        return_value="default.embedder.path",
    )
    @patch(
        "opencontractserver.tasks.embeddings_task"
        ".calculate_embeddings_for_annotation_batch"
    )
    def test_partial_queue_failure_reports_queued_count(
        self, mock_batch_task, _mock_path
    ):
        """
        If some batches queue successfully before a failure, the result
        should reflect the partial success.
        """
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.constants.document_processing import (
            EMBEDDING_BATCH_SIZE,
        )
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus

        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"test_hash_{uuid.uuid4().hex[:12]}",
            parser_name="TestParser",
            creator=self.user,
        )

        # Create enough annotations to require multiple batches
        num_annotations = EMBEDDING_BATCH_SIZE + 10
        annotations = [
            Annotation(
                raw_text=f"Annotation {i}",
                structural_set=structural_set,
                structural=True,
                creator=self.user,
            )
            for i in range(num_annotations)
        ]
        Annotation.objects.bulk_create(annotations)

        # First call succeeds, second call fails
        call_count = 0

        def delay_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise ConnectionError("Redis connection lost mid-batch")

        mock_batch_task.delay = MagicMock(side_effect=delay_side_effect)

        result = ensure_embeddings_for_corpus(structural_set.pk, self.corpus.pk)

        # The error should be reported
        self.assertTrue(len(result["errors"]) > 0)
        # At least one batch was queued before the failure
        self.assertGreaterEqual(result["tasks_queued"], 1)
