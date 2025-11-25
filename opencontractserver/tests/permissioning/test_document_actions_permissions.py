"""
Tests for Document Actions Permission System

These tests verify that document_corpus_actions follows the least-privilege model.
This ensures proper permission inheritance from documents and corpuses.

Permission Model:
- Document permissions are primary
- Corpus permissions are secondary
- Effective permission = MIN(document_permission, corpus_permission)

Issue: Permission audit remediation
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.documents.models import Document
from opencontractserver.documents.query_optimizer import DocumentActionsQueryOptimizer
from opencontractserver.extracts.models import Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestDocumentActionsPermissions(TestCase):
    """Tests for document actions with proper permission inheritance."""

    def setUp(self):
        """Create test scenario with document, corpus, and corpus actions."""
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="testpass123",
        )
        self.reader = User.objects.create_user(
            username="reader",
            email="reader@example.com",
            password="testpass123",
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
        )

        # Create corpus and document
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.owner,
            is_public=False,
        )

        # Give reader READ permission on both corpus and document
        set_permissions_for_obj_to_user(
            self.reader,
            self.corpus,
            [PermissionTypes.READ],
        )
        set_permissions_for_obj_to_user(
            self.reader,
            self.document,
            [PermissionTypes.READ],
        )

        # Create a fieldset for corpus action
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test Fieldset Description",
            creator=self.owner,
        )

        # Create a corpus action
        self.corpus_action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger="add_document",
            creator=self.owner,
        )

    def test_owner_can_see_document_actions(self):
        """
        GIVEN: A document and corpus owner with full permissions
        WHEN: Owner queries for document actions
        THEN: Corpus actions should be visible
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.owner,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        self.assertIn(
            self.corpus_action,
            actions["corpus_actions"],
            "Owner should see corpus actions",
        )

    def test_reader_with_permission_can_see_corpus_actions(self):
        """
        GIVEN: A user (reader) with explicit READ permission on document AND corpus
        WHEN: Reader queries for document actions
        THEN: Reader should see corpus actions they have permission to access
        """
        # Give reader read permission on corpus action
        set_permissions_for_obj_to_user(
            self.reader,
            self.corpus_action,
            [PermissionTypes.READ],
        )

        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.reader,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        self.assertIn(
            self.corpus_action,
            actions["corpus_actions"],
            "Reader with explicit permission should see corpus actions",
        )

    def test_outsider_cannot_see_any_document_actions(self):
        """
        GIVEN: A user (outsider) with NO permissions on document or corpus
        WHEN: Outsider queries for document actions
        THEN: All actions should be empty (permission denied)
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.outsider,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        self.assertEqual(
            actions["corpus_actions"],
            [],
            "Outsider should NOT see any corpus actions",
        )
        self.assertEqual(
            actions["extracts"],
            [],
            "Outsider should NOT see any extracts",
        )
        self.assertEqual(
            actions["analysis_rows"],
            [],
            "Outsider should NOT see any analysis rows",
        )


class TestDocumentActionsWithoutCorpus(TestCase):
    """Tests for document actions without corpus context."""

    def setUp(self):
        """Create scenario for document-only queries."""
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="testpass123",
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="testpass123",
        )

        # Create document without corpus association
        self.document = Document.objects.create(
            title="Standalone Document",
            creator=self.owner,
            is_public=False,
        )

    def test_document_actions_without_corpus_returns_empty_corpus_actions(self):
        """
        GIVEN: A document query without corpus_id
        WHEN: Querying for document actions
        THEN: corpus_actions should be empty (no corpus context)
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.owner,
            document_id=self.document.id,
            corpus_id=None,
        )

        self.assertEqual(
            actions["corpus_actions"],
            [],
            "Corpus actions should be empty when no corpus context",
        )

    def test_document_without_permission_returns_empty(self):
        """
        GIVEN: A user without permission to the document
        WHEN: Querying for document actions
        THEN: All fields should be empty
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.viewer,
            document_id=self.document.id,
            corpus_id=None,
        )

        self.assertEqual(
            actions["corpus_actions"],
            [],
            "Should return empty corpus_actions",
        )
        self.assertEqual(
            actions["extracts"],
            [],
            "Should return empty extracts",
        )
        self.assertEqual(
            actions["analysis_rows"],
            [],
            "Should return empty analysis_rows",
        )


class TestDocumentActionsIDORProtection(TestCase):
    """Tests for IDOR protection in document actions."""

    def setUp(self):
        """Create scenario for IDOR testing."""
        self.user_a = User.objects.create_user(
            username="user_a",
            email="a@example.com",
            password="testpass123",
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="b@example.com",
            password="testpass123",
        )

        # User A's private document
        self.private_document = Document.objects.create(
            title="Private Document",
            creator=self.user_a,
            is_public=False,
        )

    def test_cannot_enumerate_private_documents(self):
        """
        GIVEN: User B who does NOT have permission to User A's document
        WHEN: User B queries for document actions on User A's document
        THEN: Empty results should be returned (same as if document didn't exist)
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.user_b,
            document_id=self.private_document.id,
            corpus_id=None,
        )

        # Should return empty dict, not error with "permission denied"
        self.assertEqual(actions["extracts"], [])
        self.assertEqual(actions["corpus_actions"], [])
        self.assertEqual(actions["analysis_rows"], [])

    def test_nonexistent_document_returns_empty(self):
        """
        GIVEN: A non-existent document ID
        WHEN: Querying for document actions
        THEN: Empty results should be returned
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.user_a,
            document_id=999999,  # Non-existent
            corpus_id=None,
        )

        self.assertEqual(actions["extracts"], [])
        self.assertEqual(actions["corpus_actions"], [])
        self.assertEqual(actions["analysis_rows"], [])


class TestDocumentActionsAnonymousUser(TestCase):
    """Tests for anonymous user access to document actions."""

    def setUp(self):
        """Create public and private documents."""
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="testpass123",
        )

        self.public_document = Document.objects.create(
            title="Public Document",
            creator=self.owner,
            is_public=True,
        )
        self.private_document = Document.objects.create(
            title="Private Document",
            creator=self.owner,
            is_public=False,
        )

        self.public_corpus = Corpus.objects.create(
            title="Public Corpus",
            creator=self.owner,
            is_public=True,
        )

    def test_anonymous_can_access_public_document_actions(self):
        """
        GIVEN: A public document
        WHEN: An anonymous user queries for document actions
        THEN: Should not get permission denied (document is accessible)
        """
        anonymous = AnonymousUser()
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=anonymous,
            document_id=self.public_document.id,
            corpus_id=self.public_corpus.id,
        )

        # Should not fail - just may have empty results if no actions exist
        self.assertIsInstance(actions, dict)
        self.assertIn("corpus_actions", actions)
        self.assertIn("extracts", actions)
        self.assertIn("analysis_rows", actions)

    def test_anonymous_cannot_access_private_document_actions(self):
        """
        GIVEN: A private document
        WHEN: An anonymous user queries for document actions
        THEN: Empty results should be returned
        """
        anonymous = AnonymousUser()
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=anonymous,
            document_id=self.private_document.id,
            corpus_id=None,
        )

        self.assertEqual(actions["corpus_actions"], [])
        self.assertEqual(actions["extracts"], [])
        self.assertEqual(actions["analysis_rows"], [])


class TestDocumentActionsCorpusPermission(TestCase):
    """Tests for corpus permission requirements."""

    def setUp(self):
        """Create scenario with corpus permission requirements."""
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="testpass123",
        )
        self.doc_only_user = User.objects.create_user(
            username="doconly",
            email="doconly@example.com",
            password="testpass123",
        )

        # Create corpus and document
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.owner,
            is_public=False,
        )

        # Give doc_only_user permission ONLY on document, not corpus
        set_permissions_for_obj_to_user(
            self.doc_only_user,
            self.document,
            [PermissionTypes.READ],
        )
        # Explicitly NOT giving corpus permission

    def test_user_with_only_document_permission_cannot_see_corpus_actions(self):
        """
        GIVEN: A user with READ permission on document but NOT corpus
        WHEN: User queries for document actions with corpus_id
        THEN: Should return empty results (corpus permission required)
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.doc_only_user,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        # Should return empty because corpus permission is required
        self.assertEqual(
            actions["corpus_actions"],
            [],
            "User without corpus permission should NOT see corpus actions",
        )


class TestDocumentActionsSuperuser(TestCase):
    """Tests for superuser access to document actions."""

    def setUp(self):
        """Create scenario for superuser testing."""
        import uuid

        self.superuser = User.objects.create_superuser(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            password="adminpass123",
        )
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="testpass123",
        )

        # Create private corpus and document
        self.corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.document = Document.objects.create(
            title="Private Document",
            creator=self.owner,
            is_public=False,
        )

        # Create fieldset and corpus action
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            creator=self.owner,
        )
        self.corpus_action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger="add_document",
            creator=self.owner,
        )

    def test_superuser_can_see_all_document_actions(self):
        """
        GIVEN: A superuser
        WHEN: Querying for document actions on private document/corpus
        THEN: All actions should be visible
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.superuser,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        self.assertIn(
            self.corpus_action,
            actions["corpus_actions"],
            "Superuser should see all corpus actions",
        )
