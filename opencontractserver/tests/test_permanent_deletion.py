"""
Tests for permanent document deletion in OpenContracts.

This module tests the permanent deletion (empty trash) functionality including:
- Core deletion logic in versioning.py
- Service layer methods on DocumentLifecycleService (corpuses/services/lifecycle.py)
- GraphQL mutations for permanent deletion and empty trash
- Permission checks
- Cascade cleanup of related data
- Rule Q1 (Document cleanup when no references exist)

Architecture context:
- Soft delete: Creates DocumentPath(is_deleted=True, is_current=True)
- Permanent delete: Removes all DocumentPath history and related data
- Rule Q1: Document is deleted when no active paths point to it
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.corpuses.services import DocumentLifecycleService
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentSummaryRevision,
)
from opencontractserver.documents.versioning import (
    delete_document,
    has_references_in_other_corpuses,
    import_document,
    permanently_delete_all_in_trash,
    permanently_delete_document,
    restore_document,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    """Simple mock context for GraphQL tests."""

    def __init__(self, user):
        self.user = user


class TestPermanentDeletionCore(TestCase):
    """Test core permanent deletion logic in versioning.py."""

    def setUp(self):
        """Create test data for each test."""
        self.user = User.objects.create_user(
            username="perm_delete_tester",
            password="testpass123",
            email="permdelete@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Permanent Delete Test Corpus",
            creator=self.user,
        )

        # Create and soft-delete a document
        self.doc, _, self.path = import_document(
            corpus=self.corpus,
            path="/test_doc.pdf",
            content=b"Test content for permanent deletion",
            user=self.user,
            title="Test Document",
        )

        # Soft delete the document (delete_document takes path string)
        delete_document(self.corpus, "/test_doc.pdf", self.user)

    def test_permanently_delete_removes_all_document_paths_in_corpus(self):
        """Test that permanent deletion removes ALL DocumentPath records."""
        # Verify document is soft-deleted
        self.assertTrue(
            DocumentPath.objects.filter(
                document=self.doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=True,
            ).exists()
        )

        # Count paths before deletion
        doc_id = self.doc.id
        path_count_before = DocumentPath.objects.filter(
            document_id=doc_id,
            corpus=self.corpus,
        ).count()
        self.assertGreater(path_count_before, 0)

        # Permanently delete
        success, message = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success, f"Permanent deletion failed: {message}")

        # Verify all paths are gone
        path_count_after = DocumentPath.objects.filter(
            document_id=doc_id,
            corpus=self.corpus,
        ).count()
        self.assertEqual(path_count_after, 0)

    def test_permanently_delete_removes_all_paths_including_historical(self):
        """Test that all path records are removed, including historical ones."""
        # Create a document and verify initial path exists
        user = User.objects.create_user(
            username="history_tester",
            password="test123",
            email="history@test.com",
        )
        corpus = Corpus.objects.create(title="History Test Corpus", creator=user)

        # Import document
        doc, _, _ = import_document(
            corpus=corpus,
            path="/history_doc.pdf",
            content=b"History test content",
            user=user,
            title="History Document",
        )

        # Create additional historical path record manually
        # (simulating version history that exists in some scenarios)
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/history_doc.pdf",
            version_number=0,
            is_current=False,
            is_deleted=False,
            creator=user,
        )

        # Count all paths (should have at least 2 now)
        total_paths = DocumentPath.objects.filter(document=doc, corpus=corpus).count()
        self.assertGreaterEqual(total_paths, 2, "Should have multiple path records")

        # Soft delete - use the document's current path
        current_path = DocumentPath.objects.get(
            document=doc, corpus=corpus, is_current=True, is_deleted=False
        )
        delete_document(corpus, current_path.path, user)

        # Permanently delete
        doc_id = doc.id
        success, _ = permanently_delete_document(corpus, doc, user)
        self.assertTrue(success)

        # All paths should be gone (including historical)
        remaining_paths = DocumentPath.objects.filter(
            document_id=doc_id, corpus=corpus
        ).count()
        self.assertEqual(remaining_paths, 0)

    def test_permanently_delete_only_affects_target_corpus(self):
        """Test that deletion in one corpus doesn't affect other corpuses."""
        # Create second corpus with same document
        corpus2 = Corpus.objects.create(
            title="Second Corpus",
            creator=self.user,
        )

        # Import same content to second corpus (creates separate Document per corpus isolation)
        doc2, _, _ = import_document(
            corpus=corpus2,
            path="/test_doc.pdf",
            content=b"Test content for permanent deletion",  # Same content
            user=self.user,
            title="Test Document Copy",
        )

        # Verify doc2 has paths in corpus2
        paths_in_corpus2_before = DocumentPath.objects.filter(
            document=doc2,
            corpus=corpus2,
        ).count()
        self.assertGreater(paths_in_corpus2_before, 0)

        # Permanently delete from first corpus (self.doc is already soft-deleted in setUp)
        success, _ = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success)

        # Verify doc2 still has paths in corpus2
        paths_in_corpus2_after = DocumentPath.objects.filter(
            document=doc2,
            corpus=corpus2,
        ).count()
        self.assertEqual(paths_in_corpus2_before, paths_in_corpus2_after)

    def test_permanently_delete_requires_document_to_be_soft_deleted(self):
        """Test that permanent deletion fails for non-deleted documents."""
        # Create a non-deleted document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/active_doc.pdf",
            content=b"Active document content",
            user=self.user,
            title="Active Document",
        )

        # Try to permanently delete without soft-deleting first
        success, message = permanently_delete_document(self.corpus, doc, self.user)
        self.assertFalse(success)
        self.assertIn("not in trash", message.lower())

    def test_permanently_delete_non_deleted_document_fails(self):
        """Test that attempting to permanently delete a non-deleted document returns error."""
        # Restore the soft-deleted document (restore_document takes path string)
        restore_document(self.corpus, "/test_doc.pdf", self.user)

        # Try to permanently delete
        success, message = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertFalse(success)
        self.assertIn("not in trash", message.lower())


class TestPermanentDeletionCascadeCleanup(TestCase):
    """Test that permanent deletion properly cleans up related data."""

    def setUp(self):
        """Create test data with annotations and relationships."""
        self.user = User.objects.create_user(
            username="cascade_tester",
            password="testpass123",
            email="cascade@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Cascade Test Corpus",
            creator=self.user,
        )

        # Create annotation label
        self.label = AnnotationLabel.objects.create(
            text="Test Label",
            creator=self.user,
        )

        # Import document
        self.doc, _, _ = import_document(
            corpus=self.corpus,
            path="/cascade_doc.pdf",
            content=b"Cascade test content",
            user=self.user,
            title="Cascade Document",
        )

    def test_permanently_delete_removes_user_annotations(self):
        """Test that user annotations are deleted."""
        # Create user annotations (non-structural)
        annotation1 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Test annotation 1",
            page=1,
            json={},
        )
        annotation2 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Test annotation 2",
            page=1,
            json={},
        )

        # Verify annotations exist
        self.assertEqual(
            Annotation.objects.filter(
                document=self.doc, structural_set__isnull=True
            ).count(),
            2,
        )

        # Soft delete then permanent delete
        delete_document(self.corpus, "/cascade_doc.pdf", self.user)
        success, _ = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success)

        # Verify annotations are gone
        self.assertEqual(
            Annotation.objects.filter(id__in=[annotation1.id, annotation2.id]).count(),
            0,
        )

    def test_permanently_delete_removes_relationships_with_annotations(self):
        """Test that relationships involving deleted annotations are removed."""
        # Create annotations
        source_annotation = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Source annotation",
            page=1,
            json={},
        )
        target_annotation = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Target annotation",
            page=1,
            json={},
        )

        # Create relationship label
        rel_label = AnnotationLabel.objects.create(
            text="Related To",
            label_type="RELATIONSHIP_LABEL",
            creator=self.user,
        )

        # Create relationship
        relationship = Relationship.objects.create(
            relationship_label=rel_label,
            corpus=self.corpus,
            document=self.doc,
            creator=self.user,
        )
        relationship.source_annotations.add(source_annotation)
        relationship.target_annotations.add(target_annotation)

        # Verify relationship exists
        self.assertTrue(Relationship.objects.filter(id=relationship.id).exists())

        # Soft delete then permanent delete
        delete_document(self.corpus, "/cascade_doc.pdf", self.user)
        success, _ = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success)

        # Verify relationship is gone
        self.assertFalse(Relationship.objects.filter(id=relationship.id).exists())

    def test_permanently_delete_removes_document_summary_revisions(self):
        """Test that DocumentSummaryRevision records are deleted."""
        # Create summary revisions using correct field names
        revision1 = DocumentSummaryRevision.objects.create(
            document=self.doc,
            corpus=self.corpus,
            author=self.user,
            version=1,
            diff="Initial summary",
            snapshot="Summary content v1",
        )
        revision2 = DocumentSummaryRevision.objects.create(
            document=self.doc,
            corpus=self.corpus,
            author=self.user,
            version=2,
            diff="Updated summary",
            snapshot="Summary content v2",
        )

        # Verify revisions exist
        self.assertEqual(
            DocumentSummaryRevision.objects.filter(
                document=self.doc,
                corpus=self.corpus,
            ).count(),
            2,
        )

        # Soft delete then permanent delete
        delete_document(self.corpus, "/cascade_doc.pdf", self.user)
        success, _ = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success)

        # Verify revisions are gone
        self.assertEqual(
            DocumentSummaryRevision.objects.filter(
                id__in=[revision1.id, revision2.id]
            ).count(),
            0,
        )

    def test_permanently_delete_preserves_structural_annotations(self):
        """Test that structural annotations (in StructuralAnnotationSet) are preserved."""
        from opencontractserver.annotations.models import StructuralAnnotationSet

        # Create structural annotation set
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash="test_hash_123",
            creator=self.user,
        )

        # Create structural annotation (belongs to set, not document directly)
        # Note: structural=True is required by DB constraint when structural_set is set
        structural_annotation = Annotation.objects.create(
            structural_set=structural_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Structural annotation",
            page=1,
            json={},
            structural=True,
        )

        # Soft delete then permanent delete the document
        delete_document(self.corpus, "/cascade_doc.pdf", self.user)
        success, _ = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success)

        # Verify structural annotation still exists
        self.assertTrue(Annotation.objects.filter(id=structural_annotation.id).exists())

    def test_permanently_delete_preserves_structural_annotation_set(self):
        """Test that StructuralAnnotationSet is preserved after document deletion."""
        from opencontractserver.annotations.models import StructuralAnnotationSet

        # Create structural annotation set
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash="test_hash_456",
            creator=self.user,
        )

        # Soft delete then permanent delete
        delete_document(self.corpus, "/cascade_doc.pdf", self.user)
        success, _ = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success)

        # Verify structural set still exists
        self.assertTrue(
            StructuralAnnotationSet.objects.filter(id=structural_set.id).exists()
        )


class TestRuleQ1DocumentCleanup(TestCase):
    """Test Rule Q1: Document deleted when no other corpus references it."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="rule_q1_tester",
            password="testpass123",
            email="ruleq1@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Rule Q1 Test Corpus",
            creator=self.user,
        )

    def test_document_deleted_when_no_other_corpus_references(self):
        """Test that Document is deleted when it has no remaining paths."""
        # Create document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/lonely_doc.pdf",
            content=b"Document with no other references",
            user=self.user,
            title="Lonely Document",
        )
        doc_id = doc.id

        # Soft delete then permanent delete
        delete_document(self.corpus, "/lonely_doc.pdf", self.user)
        success, _ = permanently_delete_document(self.corpus, doc, self.user)
        self.assertTrue(success)

        # Verify Document itself is deleted
        self.assertFalse(Document.objects.filter(id=doc_id).exists())

    def test_document_preserved_when_other_corpus_has_reference(self):
        """Test that Document is preserved when another corpus references it."""
        # Create document in first corpus
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/shared_doc.pdf",
            content=b"Document shared across corpuses",
            user=self.user,
            title="Shared Document",
        )
        doc_id = doc.id

        # Create second corpus and add reference to same document
        # Note: Due to corpus isolation, we need to manually create a path
        # to simulate a document being referenced from another corpus
        corpus2 = Corpus.objects.create(
            title="Second Corpus",
            creator=self.user,
        )

        # Create a path in corpus2 pointing to the same document
        # This simulates the document being shared
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus2,
            path="/shared_doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Verify has_references_in_other_corpuses
        self.assertTrue(has_references_in_other_corpuses(doc, self.corpus))

        # Soft delete then permanent delete from first corpus
        delete_document(self.corpus, "/shared_doc.pdf", self.user)
        success, _ = permanently_delete_document(self.corpus, doc, self.user)
        self.assertTrue(success)

        # Verify Document is still preserved (referenced by corpus2)
        self.assertTrue(Document.objects.filter(id=doc_id).exists())

        # But paths in first corpus are gone
        self.assertFalse(
            DocumentPath.objects.filter(document_id=doc_id, corpus=self.corpus).exists()
        )

    def test_document_preserved_when_standalone_path_exists(self):
        """Test Document preserved when any path exists in any corpus."""
        # Create document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/preserved_doc.pdf",
            content=b"Document to be preserved",
            user=self.user,
            title="Preserved Document",
        )

        # Create additional standalone corpus with reference
        corpus2 = Corpus.objects.create(
            title="Standalone Corpus",
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus2,
            path="/standalone_copy.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Delete from original corpus
        delete_document(self.corpus, "/preserved_doc.pdf", self.user)
        success, _ = permanently_delete_document(self.corpus, doc, self.user)
        self.assertTrue(success)

        # Document should still exist
        doc.refresh_from_db()  # Should not raise DoesNotExist
        self.assertIsNotNone(doc.id)


class TestEmptyTrashBulk(TestCase):
    """Test bulk empty trash functionality."""

    def setUp(self):
        """Create test data with multiple documents."""
        self.user = User.objects.create_user(
            username="empty_trash_tester",
            password="testpass123",
            email="emptytrash@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Empty Trash Test Corpus",
            creator=self.user,
        )

    def test_empty_trash_deletes_all_soft_deleted_documents(self):
        """Test that empty trash deletes all soft-deleted documents."""
        # Create and soft-delete multiple documents
        for i in range(5):
            import_document(
                corpus=self.corpus,
                path=f"/trash_doc_{i}.pdf",
                content=f"Trash content {i}".encode(),
                user=self.user,
                title=f"Trash Document {i}",
            )
            delete_document(self.corpus, f"/trash_doc_{i}.pdf", self.user)

        # Verify 5 soft-deleted documents
        deleted_count = DocumentPath.objects.filter(
            corpus=self.corpus,
            is_current=True,
            is_deleted=True,
        ).count()
        self.assertEqual(deleted_count, 5)

        # Empty trash
        count, errors = permanently_delete_all_in_trash(self.corpus, self.user)
        self.assertEqual(count, 5)
        self.assertEqual(len(errors), 0)

        # Verify no soft-deleted documents remain
        remaining_deleted = DocumentPath.objects.filter(
            corpus=self.corpus,
            is_current=True,
            is_deleted=True,
        ).count()
        self.assertEqual(remaining_deleted, 0)

    def test_empty_trash_preserves_non_deleted_documents(self):
        """Test that empty trash doesn't affect active documents."""
        # Create active document
        active_doc, _, _ = import_document(
            corpus=self.corpus,
            path="/active_doc.pdf",
            content=b"Active document content",
            user=self.user,
            title="Active Document",
        )

        # Create and soft-delete another document
        import_document(
            corpus=self.corpus,
            path="/trash_doc.pdf",
            content=b"Trash document content",
            user=self.user,
            title="Trash Document",
        )
        delete_document(self.corpus, "/trash_doc.pdf", self.user)

        # Empty trash
        count, errors = permanently_delete_all_in_trash(self.corpus, self.user)
        self.assertEqual(count, 1)

        # Verify active document still exists with active path
        self.assertTrue(
            DocumentPath.objects.filter(
                document=active_doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=False,
            ).exists()
        )

    def test_empty_trash_returns_correct_count(self):
        """Test that empty trash returns accurate deletion count."""
        # Create 3 documents, delete 2
        for i in range(3):
            import_document(
                corpus=self.corpus,
                path=f"/count_doc_{i}.pdf",
                content=f"Count content {i}".encode(),
                user=self.user,
                title=f"Count Document {i}",
            )

        # Delete first two
        delete_document(self.corpus, "/count_doc_0.pdf", self.user)
        delete_document(self.corpus, "/count_doc_1.pdf", self.user)

        # Empty trash
        count, errors = permanently_delete_all_in_trash(self.corpus, self.user)
        self.assertEqual(count, 2)
        self.assertEqual(len(errors), 0)

    def test_empty_trash_on_empty_trash_returns_zero(self):
        """Test that empty trash on already empty trash returns 0."""
        # Don't create any documents

        # Empty trash
        count, errors = permanently_delete_all_in_trash(self.corpus, self.user)
        self.assertEqual(count, 0)
        self.assertEqual(len(errors), 0)


class TestPermanentDeletionPermissions(TestCase):
    """Test permission checks for permanent deletion."""

    def setUp(self):
        """Create test data with different users."""
        self.owner = User.objects.create_user(
            username="perm_owner",
            password="testpass123",
            email="permowner@test.com",
        )

        self.other_user = User.objects.create_user(
            username="perm_other",
            password="testpass123",
            email="permother@test.com",
        )

        self.superuser = User.objects.create_superuser(
            username="perm_superuser",
            password="testpass123",
            email="permsuperuser@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Permission Test Corpus",
            creator=self.owner,
        )

        # Create and soft-delete a document
        self.doc, _, _ = import_document(
            corpus=self.corpus,
            path="/perm_test_doc.pdf",
            content=b"Permission test content",
            user=self.owner,
            title="Permission Test Document",
        )
        delete_document(self.corpus, "/perm_test_doc.pdf", self.owner)

    def test_permanent_delete_requires_delete_permission(self):
        """Test that DELETE permission is required for permanent deletion."""
        # Grant only READ permission to other_user
        set_permissions_for_obj_to_user(
            self.other_user,
            self.corpus,
            [PermissionTypes.READ],
        )

        # Try to permanently delete via service layer
        success, message = DocumentLifecycleService.permanently_delete_document(
            self.other_user, self.doc, self.corpus
        )
        self.assertFalse(success)
        self.assertIn("permission denied", message.lower())

    def test_permanent_delete_denied_without_permission(self):
        """Test that users without any permission cannot permanently delete."""
        # other_user has no permissions on corpus

        success, message = DocumentLifecycleService.permanently_delete_document(
            self.other_user, self.doc, self.corpus
        )
        self.assertFalse(success)
        self.assertIn("permission denied", message.lower())

    def test_permanent_delete_allowed_for_corpus_creator(self):
        """Test that corpus creator can permanently delete."""
        success, message = DocumentLifecycleService.permanently_delete_document(
            self.owner, self.doc, self.corpus
        )
        self.assertTrue(success)

    def test_permanent_delete_allowed_for_superuser(self):
        """Test that superuser can permanently delete any document."""
        success, message = DocumentLifecycleService.permanently_delete_document(
            self.superuser, self.doc, self.corpus
        )
        self.assertTrue(success)

    def test_empty_trash_requires_delete_permission(self):
        """Test that DELETE permission is required for empty trash."""
        # Grant only READ permission
        set_permissions_for_obj_to_user(
            self.other_user,
            self.corpus,
            [PermissionTypes.READ],
        )

        count, message = DocumentLifecycleService.empty_trash(
            self.other_user, self.corpus
        )
        self.assertEqual(count, 0)
        self.assertIn("permission denied", message.lower())

    def test_user_with_delete_permission_can_permanently_delete(self):
        """Test that user with DELETE permission can permanently delete."""
        # Grant DELETE permission to other_user
        set_permissions_for_obj_to_user(
            self.other_user,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.DELETE],
        )

        # Need to create a new doc since previous test might have deleted it
        doc2, _, _ = import_document(
            corpus=self.corpus,
            path="/perm_test_doc_2.pdf",
            content=b"Permission test content 2",
            user=self.owner,
            title="Permission Test Document 2",
        )
        delete_document(self.corpus, "/perm_test_doc_2.pdf", self.owner)

        success, message = DocumentLifecycleService.permanently_delete_document(
            self.other_user, doc2, self.corpus
        )
        self.assertTrue(success, f"Expected success but got: {message}")


class TestPermanentDeletionGraphQL(TestCase):
    """Test GraphQL mutations for permanent deletion."""

    def setUp(self):
        """Create test data for GraphQL tests."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="graphql_perm_delete",
            password="testpass123",
            email="graphqlpermdelete@test.com",
        )

        self.other_user = User.objects.create_user(
            username="graphql_other",
            password="testpass123",
            email="graphqlother@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="GraphQL Permanent Delete Test Corpus",
            creator=self.user,
        )

    def test_permanently_delete_document_mutation_success(self):
        """Test successful permanent deletion via GraphQL."""
        # Create and soft-delete document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/graphql_delete_doc.pdf",
            content=b"GraphQL deletion test content",
            user=self.user,
            title="GraphQL Delete Document",
        )
        delete_document(self.corpus, "/graphql_delete_doc.pdf", self.user)

        doc_id = to_global_id("DocumentType", doc.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                permanentlyDeleteDocument(documentId: "{doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(mutation, context_value=TestContext(self.user))

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["permanentlyDeleteDocument"]["ok"])

        # Verify document is gone
        self.assertFalse(
            DocumentPath.objects.filter(document=doc, corpus=self.corpus).exists()
        )

    def test_permanently_delete_document_mutation_not_found(self):
        """Test permanent deletion of non-existent document."""
        fake_doc_id = to_global_id("DocumentType", 99999)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                permanentlyDeleteDocument(documentId: "{fake_doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(mutation, context_value=TestContext(self.user))

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["permanentlyDeleteDocument"]["ok"])
        self.assertIn(
            "not found", result["data"]["permanentlyDeleteDocument"]["message"].lower()
        )

    def test_permanently_delete_document_mutation_not_deleted(self):
        """Test permanent deletion of non-soft-deleted document fails."""
        # Create document but don't soft-delete
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/active_graphql_doc.pdf",
            content=b"Active GraphQL document",
            user=self.user,
            title="Active GraphQL Document",
        )

        doc_id = to_global_id("DocumentType", doc.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                permanentlyDeleteDocument(documentId: "{doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(mutation, context_value=TestContext(self.user))

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["permanentlyDeleteDocument"]["ok"])
        self.assertIn(
            "not in trash",
            result["data"]["permanentlyDeleteDocument"]["message"].lower(),
        )

    def test_permanently_delete_document_mutation_permission_denied(self):
        """Test permanent deletion without permission fails."""
        # Create and soft-delete document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/no_perm_doc.pdf",
            content=b"No permission document",
            user=self.user,
            title="No Permission Document",
        )
        delete_document(self.corpus, "/no_perm_doc.pdf", self.user)

        doc_id = to_global_id("DocumentType", doc.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                permanentlyDeleteDocument(documentId: "{doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        # Execute as other_user who has no permission
        result = self.client.execute(
            mutation, context_value=TestContext(self.other_user)
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["permanentlyDeleteDocument"]["ok"])
        self.assertIn(
            "permission", result["data"]["permanentlyDeleteDocument"]["message"].lower()
        )

    def test_empty_trash_mutation_success(self):
        """Test successful empty trash via GraphQL."""
        # Create and soft-delete multiple documents
        for i in range(3):
            import_document(
                corpus=self.corpus,
                path=f"/empty_trash_doc_{i}.pdf",
                content=f"Empty trash content {i}".encode(),
                user=self.user,
                title=f"Empty Trash Document {i}",
            )
            delete_document(self.corpus, f"/empty_trash_doc_{i}.pdf", self.user)

        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                emptyTrash(corpusId: "{corpus_id}") {{
                    ok
                    message
                    deletedCount
                }}
            }}
        """

        result = self.client.execute(mutation, context_value=TestContext(self.user))

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["emptyTrash"]["ok"])
        self.assertEqual(result["data"]["emptyTrash"]["deletedCount"], 3)

        # Verify trash is empty
        deleted_count = DocumentPath.objects.filter(
            corpus=self.corpus,
            is_current=True,
            is_deleted=True,
        ).count()
        self.assertEqual(deleted_count, 0)

    def test_empty_trash_mutation_permission_denied(self):
        """Test empty trash without permission fails."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                emptyTrash(corpusId: "{corpus_id}") {{
                    ok
                    message
                    deletedCount
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=TestContext(self.other_user)
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["emptyTrash"]["ok"])
        self.assertEqual(result["data"]["emptyTrash"]["deletedCount"], 0)


class TestPermanentDeletionEdgeCases(TestCase):
    """Test edge cases for permanent deletion."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="edge_case_tester",
            password="testpass123",
            email="edgecase@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Edge Case Test Corpus",
            creator=self.user,
        )

    def test_permanently_delete_document_with_multiple_versions(self):
        """Test permanent deletion of document with version history."""
        # Create document v1
        import_document(
            corpus=self.corpus,
            path="/versioned_doc.pdf",
            content=b"Version 1 content",
            user=self.user,
            title="Versioned Document v1",
        )

        # Update to v2 (creates new Document as child)
        doc_v2, status, _ = import_document(
            corpus=self.corpus,
            path="/versioned_doc.pdf",
            content=b"Version 2 content",
            user=self.user,
            title="Versioned Document v2",
        )
        self.assertEqual(status, "updated")

        # Soft delete
        delete_document(self.corpus, "/versioned_doc.pdf", self.user)

        # Permanently delete
        doc_v2_id = doc_v2.id
        success, message = permanently_delete_document(self.corpus, doc_v2, self.user)
        self.assertTrue(success, f"Failed: {message}")

        # Verify all paths are gone
        self.assertFalse(
            DocumentPath.objects.filter(
                corpus=self.corpus, document_id=doc_v2_id
            ).exists()
        )

    def test_permanently_delete_document_in_folder(self):
        """Test permanent deletion of document that exists in a folder."""
        # Create folder
        folder = CorpusFolder.objects.create(
            name="Test Folder",
            corpus=self.corpus,
            creator=self.user,
        )

        # Create document in folder
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/folder_doc.pdf",
            content=b"Document in folder content",
            user=self.user,
            title="Document in Folder",
            folder=folder,
        )

        # Verify document exists in folder
        current_path = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertEqual(current_path.folder, folder)

        # Soft delete then permanently delete
        doc_id = doc.id
        delete_document(self.corpus, current_path.path, self.user)
        success, message = permanently_delete_document(self.corpus, doc, self.user)
        self.assertTrue(success, f"Failed: {message}")

        # All paths should be gone
        remaining = DocumentPath.objects.filter(
            document_id=doc_id, corpus=self.corpus
        ).count()
        self.assertEqual(remaining, 0)

        # Document should be gone too (Rule Q1)
        self.assertFalse(Document.objects.filter(id=doc_id).exists())

    def test_permanently_delete_preserves_other_documents_in_corpus(self):
        """Test that permanent deletion doesn't affect other documents."""
        # Create two documents
        doc1, _, _ = import_document(
            corpus=self.corpus,
            path="/doc1.pdf",
            content=b"Document 1 content",
            user=self.user,
            title="Document 1",
        )
        doc2, _, _ = import_document(
            corpus=self.corpus,
            path="/doc2.pdf",
            content=b"Document 2 content",
            user=self.user,
            title="Document 2",
        )

        # Soft delete only doc1
        delete_document(self.corpus, "/doc1.pdf", self.user)

        # Permanently delete doc1
        success, _ = permanently_delete_document(self.corpus, doc1, self.user)
        self.assertTrue(success)

        # Verify doc2 still exists with active path
        self.assertTrue(
            DocumentPath.objects.filter(
                document=doc2,
                corpus=self.corpus,
                is_current=True,
                is_deleted=False,
            ).exists()
        )


class TestPermanentDeletionIntegration(TestCase):
    """Integration tests for full document lifecycle with permanent deletion."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="integration_tester",
            password="testpass123",
            email="integration@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Integration Test Corpus",
            creator=self.user,
        )

    def test_full_lifecycle_create_delete_restore_permanent_delete(self):
        """Test full document lifecycle: create -> delete -> restore -> delete -> permanent delete."""
        # Create document
        doc, _, path = import_document(
            corpus=self.corpus,
            path="/lifecycle_doc.pdf",
            content=b"Lifecycle test content",
            user=self.user,
            title="Lifecycle Document",
        )
        doc_id = doc.id

        # Verify active
        self.assertTrue(
            DocumentPath.objects.filter(
                document=doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=False,
            ).exists()
        )

        # Soft delete
        delete_document(self.corpus, "/lifecycle_doc.pdf", self.user)
        self.assertTrue(
            DocumentPath.objects.filter(
                document=doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=True,
            ).exists()
        )

        # Restore
        restore_document(self.corpus, "/lifecycle_doc.pdf", self.user)
        self.assertTrue(
            DocumentPath.objects.filter(
                document=doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=False,
            ).exists()
        )

        # Soft delete again
        delete_document(self.corpus, "/lifecycle_doc.pdf", self.user)

        # Permanently delete
        success, message = permanently_delete_document(self.corpus, doc, self.user)
        self.assertTrue(success, f"Failed: {message}")

        # Verify completely gone
        self.assertFalse(DocumentPath.objects.filter(document_id=doc_id).exists())
        self.assertFalse(Document.objects.filter(id=doc_id).exists())

    def test_empty_trash_after_mixed_operations(self):
        """Test empty trash with documents in various states."""
        # Doc 1: Soft-deleted
        doc1, _, _ = import_document(
            corpus=self.corpus,
            path="/mixed_doc_1.pdf",
            content=b"Mixed doc 1",
            user=self.user,
            title="Mixed Document 1",
        )
        delete_document(self.corpus, "/mixed_doc_1.pdf", self.user)

        # Doc 2: Deleted then restored (active)
        doc2, _, _ = import_document(
            corpus=self.corpus,
            path="/mixed_doc_2.pdf",
            content=b"Mixed doc 2",
            user=self.user,
            title="Mixed Document 2",
        )
        delete_document(self.corpus, "/mixed_doc_2.pdf", self.user)
        restore_document(self.corpus, "/mixed_doc_2.pdf", self.user)

        # Doc 3: Soft-deleted
        doc3, _, _ = import_document(
            corpus=self.corpus,
            path="/mixed_doc_3.pdf",
            content=b"Mixed doc 3",
            user=self.user,
            title="Mixed Document 3",
        )
        delete_document(self.corpus, "/mixed_doc_3.pdf", self.user)

        # Doc 4: Never deleted (active)
        doc4, _, _ = import_document(
            corpus=self.corpus,
            path="/mixed_doc_4.pdf",
            content=b"Mixed doc 4",
            user=self.user,
            title="Mixed Document 4",
        )

        # Empty trash - should delete doc1 and doc3 only
        count, errors = permanently_delete_all_in_trash(self.corpus, self.user)
        self.assertEqual(count, 2)
        self.assertEqual(len(errors), 0)

        # Verify doc2 and doc4 still exist with active paths
        for doc in [doc2, doc4]:
            self.assertTrue(
                DocumentPath.objects.filter(
                    document=doc,
                    corpus=self.corpus,
                    is_current=True,
                    is_deleted=False,
                ).exists(),
                f"Document {doc.title} should still be active",
            )

        # Verify doc1 and doc3 are gone
        for doc in [doc1, doc3]:
            self.assertFalse(
                DocumentPath.objects.filter(
                    document=doc,
                    corpus=self.corpus,
                ).exists(),
                f"Document {doc.title} should be permanently deleted",
            )
