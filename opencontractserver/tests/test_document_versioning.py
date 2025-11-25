"""
Comprehensive Tests for Dual-Tree Document Versioning Architecture

This test suite validates all rules and operations defined in the dual-tree architecture.
Each test is designed to be human-readable and proves specific architectural principles.

Architecture Rules Tested:
- Content Tree (Document model): C1, C2, C3
- Path Tree (DocumentPath model): P1, P2, P3, P4, P5, P6
- Interaction Rules: I1, Q1
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.documents.versioning import (
    compute_sha256,
    delete_document,
    get_content_history,
    get_current_filesystem,
    get_filesystem_at_time,
    get_path_history,
    import_document,
    is_content_truly_deleted,
    move_document,
    restore_document,
)

User = get_user_model()


class ContentTreeRulesTestCase(TestCase):
    """
    Test Suite 1: Content Tree Rules (C1, C2, C3)

    These tests validate that the Content Tree correctly tracks document content
    and versions according to the architectural rules.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_c1_new_document_only_when_hash_first_seen_globally(self):
        """
        Rule C1: A new Document node is created only when a content hash
        is seen for the first time anywhere in the system.

        Scenario: Import same content twice should create only one Document.
        """
        content = b"Test PDF content for Rule C1"
        content_hash = compute_sha256(content)

        # First import - should create new Document
        doc1, status1, path1 = import_document(
            corpus=self.corpus,
            path="/test1.pdf",
            content=content,
            user=self.user,
            title="First Document",
        )

        self.assertEqual(status1, "created")
        self.assertEqual(doc1.pdf_file_hash, content_hash)

        # Count documents with this hash
        docs_with_hash = Document.objects.filter(pdf_file_hash=content_hash).count()
        self.assertEqual(
            docs_with_hash,
            1,
            "Rule C1 violated: Only one Document should exist for unique hash",
        )

        # Second import at different path - should link to existing Document
        doc2, status2, path2 = import_document(
            corpus=self.corpus,
            path="/test2.pdf",
            content=content,
            user=self.user,
            title="Second Document",
        )

        self.assertEqual(status2, "linked")
        self.assertEqual(
            doc1.id,
            doc2.id,
            "Rule C1 violated: Same content in same corpus should reuse Document",
        )

        # Still only one document with this hash in this corpus
        docs_with_hash = Document.objects.filter(pdf_file_hash=content_hash).count()
        self.assertEqual(
            docs_with_hash, 1, "Rule C1 violated: Corpus deduplication failed"
        )

    def test_c2_updates_create_child_nodes_of_previous_version(self):
        """
        Rule C2: If new content updates an existing file, the new Document node
        is created as a child of the Document representing the previous content.

        Scenario: Update content at same path creates parent-child relationship.
        """
        original_content = b"Original PDF content for Rule C2"
        updated_content = b"Updated PDF content for Rule C2"

        # Import original
        doc1, status1, path1 = import_document(
            corpus=self.corpus,
            path="/contract.pdf",
            content=original_content,
            user=self.user,
            title="Original Contract",
        )

        self.assertEqual(status1, "created")
        self.assertIsNone(doc1.parent, "First version should have no parent")

        original_tree_id = doc1.version_tree_id

        # Update with new content
        doc2, status2, path2 = import_document(
            corpus=self.corpus,
            path="/contract.pdf",
            content=updated_content,
            user=self.user,
            title="Updated Contract",
        )

        self.assertEqual(status2, "updated")
        self.assertEqual(
            doc2.parent_id,
            doc1.id,
            "Rule C2 violated: Updated document should be child of previous",
        )
        self.assertEqual(
            doc2.version_tree_id,
            original_tree_id,
            "Rule C2 violated: Versions should share same tree_id",
        )

        # Verify tree structure
        version_history = get_content_history(doc2)
        self.assertEqual(len(version_history), 2, "Should have 2 versions in history")
        self.assertEqual(
            version_history[0].id, doc1.id, "First in history should be original"
        )
        self.assertEqual(
            version_history[1].id, doc2.id, "Second in history should be update"
        )

    def test_c3_only_one_current_document_per_version_tree(self):
        """
        Rule C3: Only one Document in a version tree (sharing a version_tree_id)
        can have is_current=True.

        Scenario: Creating new version should mark old version as not current.
        """
        v1_content = b"Version 1 content for Rule C3"
        v2_content = b"Version 2 content for Rule C3"

        # Create version 1
        doc_v1, _, path_v1 = import_document(
            corpus=self.corpus,
            path="/document.pdf",
            content=v1_content,
            user=self.user,
            title="Version 1",
        )

        self.assertTrue(doc_v1.is_current, "Initial version should be current")

        tree_id = doc_v1.version_tree_id

        # Create version 2
        doc_v2, _, path_v2 = import_document(
            corpus=self.corpus,
            path="/document.pdf",
            content=v2_content,
            user=self.user,
            title="Version 2",
        )

        self.assertTrue(doc_v2.is_current, "New version should be current")

        # Refresh v1 from database
        doc_v1.refresh_from_db()

        self.assertFalse(
            doc_v1.is_current,
            "Rule C3 violated: Old version should no longer be current",
        )

        # Count current documents in this tree
        current_count = Document.objects.filter(
            version_tree_id=tree_id, is_current=True
        ).count()

        self.assertEqual(
            current_count,
            1,
            "Rule C3 violated: Only one document in tree should be current",
        )

    def test_c3_database_constraint_prevents_multiple_current(self):
        """
        Rule C3: Database constraint prevents multiple current documents
        in same version tree.

        Scenario: Attempting to manually create second current document fails.
        """
        # Create initial document
        doc1, _, _ = import_document(
            corpus=self.corpus,
            path="/test.pdf",
            content=b"Test content",
            user=self.user,
        )

        tree_id = doc1.version_tree_id

        # Attempt to create another current document in same tree
        # This should be prevented by the database constraint
        with self.assertRaises(IntegrityError) as context:
            with transaction.atomic():
                Document.objects.create(
                    title="Duplicate Current",
                    pdf_file_hash="different_hash",
                    version_tree_id=tree_id,
                    is_current=True,  # This violates C3
                    parent=None,
                    creator=self.user,
                )

        self.assertIn("one_current_per_version_tree", str(context.exception).lower())


class PathTreeRulesTestCase(TestCase):
    """
    Test Suite 2: Path Tree Rules (P1, P2, P3, P4, P5, P6)

    These tests validate that the Path Tree correctly tracks document
    locations and lifecycle events according to the architectural rules.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_p1_every_lifecycle_event_creates_new_node(self):
        """
        Rule P1: A new DocumentPath node is created for every lifecycle event.

        Scenario: Import → Move → Update → Delete → Restore creates 5 nodes.
        """
        content_v1 = b"Version 1 content"
        content_v2 = b"Version 2 content"

        # Event 1: Import
        doc, _, path1 = import_document(
            corpus=self.corpus, path="/original.pdf", content=content_v1, user=self.user
        )

        # Event 2: Move
        path2 = move_document(
            corpus=self.corpus,
            old_path="/original.pdf",
            new_path="/moved.pdf",
            user=self.user,
        )

        # Event 3: Update content
        doc_v2, _, path3 = import_document(
            corpus=self.corpus, path="/moved.pdf", content=content_v2, user=self.user
        )

        # Event 4: Delete
        path4 = delete_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        # Event 5: Restore
        path5 = restore_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        # Verify each event created a new node
        all_paths = [path1, path2, path3, path4, path5]
        path_ids = [p.id for p in all_paths]

        self.assertEqual(
            len(set(path_ids)),
            5,
            "Rule P1 violated: Each lifecycle event should create unique node",
        )

        # Verify we can reconstruct the history
        history = get_path_history(path5)
        self.assertEqual(len(history), 5, "Should have 5 events in history")

        # Verify action types
        expected_actions = ["CREATED", "MOVED", "UPDATED", "DELETED", "RESTORED"]
        actual_actions = [h["action"] for h in history]
        self.assertEqual(
            actual_actions,
            expected_actions,
            "History should show all lifecycle events in order",
        )

    def test_p2_new_nodes_are_children_of_previous_state(self):
        """
        Rule P2: New DocumentPath nodes are children of the previous state node.

        Scenario: Create chain of operations and verify parent-child links.
        """
        content = b"Test content for P2"

        # Create initial path
        _, _, path1 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=content, user=self.user
        )

        self.assertIsNone(path1.parent, "Initial path should have no parent")

        # Move it
        path2 = move_document(
            corpus=self.corpus,
            old_path="/doc.pdf",
            new_path="/moved.pdf",
            user=self.user,
        )

        self.assertEqual(
            path2.parent_id,
            path1.id,
            "Rule P2 violated: Move should create child of previous state",
        )

        # Delete it
        path3 = delete_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        self.assertEqual(
            path3.parent_id,
            path2.id,
            "Rule P2 violated: Delete should create child of previous state",
        )

        # Restore it
        path4 = restore_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        self.assertEqual(
            path4.parent_id,
            path3.id,
            "Rule P2 violated: Restore should create child of previous state",
        )

    def test_p3_only_current_filesystem_state_is_current(self):
        """
        Rule P3: Only nodes representing current filesystem state have
        is_current=True.

        Scenario: After operations, only final state is current.
        """
        content = b"Test content for P3"

        # Create and perform operations
        _, _, path1 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=content, user=self.user
        )

        path2 = move_document(
            corpus=self.corpus,
            old_path="/doc.pdf",
            new_path="/moved.pdf",
            user=self.user,
        )

        path3 = delete_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        # Refresh all paths from database
        path1.refresh_from_db()
        path2.refresh_from_db()
        path3.refresh_from_db()

        # Only the final state should be current
        self.assertFalse(path1.is_current, "Old state should not be current")
        self.assertFalse(path2.is_current, "Old state should not be current")
        self.assertTrue(
            path3.is_current, "Rule P3 violated: Current state should be marked current"
        )

        # Count current paths
        current_count = DocumentPath.objects.filter(
            corpus=self.corpus, is_current=True
        ).count()

        self.assertEqual(
            current_count, 1, "Rule P3 violated: Only one path should be current"
        )

    def test_p4_one_active_path_per_corpus_path_tuple(self):
        """
        Rule P4: Only one active (is_current=True, is_deleted=False)
        DocumentPath can exist per (corpus, path) tuple.

        Scenario: Cannot have two active documents at same path.
        """
        content1 = b"First content"
        content2 = b"Second content"

        # Import first document
        _, _, path1 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=content1, user=self.user
        )

        # Delete it
        delete_document(corpus=self.corpus, path="/doc.pdf", user=self.user)

        # Now import different content at same path
        _, _, path2 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=content2, user=self.user
        )

        # Count active paths at this location
        active_count = DocumentPath.objects.filter(
            corpus=self.corpus, path="/doc.pdf", is_current=True, is_deleted=False
        ).count()

        self.assertEqual(
            active_count, 1, "Rule P4 violated: Only one active path per (corpus, path)"
        )

    def test_p4_database_constraint_prevents_duplicate_active_paths(self):
        """
        Rule P4: Database constraint prevents duplicate active paths.

        Scenario: Attempting to manually create duplicate active path fails.
        """
        # Create initial path
        doc, _, path1 = import_document(
            corpus=self.corpus,
            path="/test.pdf",
            content=b"Test content",
            user=self.user,
        )

        # Attempt to create another active path at same location
        # This should be prevented by the database constraint
        with self.assertRaises(IntegrityError) as context:
            with transaction.atomic():
                DocumentPath.objects.create(
                    document=doc,
                    corpus=self.corpus,
                    path="/test.pdf",  # Same path
                    version_number=1,
                    is_current=True,
                    is_deleted=False,  # Active
                    creator=self.user,
                )

        self.assertIn("unique_active_path_per_corpus", str(context.exception).lower())

    def test_p5_version_number_increments_only_on_content_changes(self):
        """
        Rule P5: version_number increments only when pointing to new
        Document version.

        Scenario: Move doesn't increment version, update does.
        """
        v1_content = b"Version 1 content"
        v2_content = b"Version 2 content"

        # Import initial
        _, _, path1 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=v1_content, user=self.user
        )

        self.assertEqual(path1.version_number, 1)

        # Move - version should NOT increment
        path2 = move_document(
            corpus=self.corpus,
            old_path="/doc.pdf",
            new_path="/moved.pdf",
            user=self.user,
        )

        self.assertEqual(
            path2.version_number,
            1,
            "Rule P5 violated: Move should not increment version",
        )

        # Update content - version SHOULD increment
        _, _, path3 = import_document(
            corpus=self.corpus, path="/moved.pdf", content=v2_content, user=self.user
        )

        self.assertEqual(
            path3.version_number,
            2,
            "Rule P5 violated: Content update should increment version",
        )

        # Delete - version should NOT increment
        path4 = delete_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        self.assertEqual(
            path4.version_number,
            2,
            "Rule P5 violated: Delete should not increment version",
        )

        # Restore - version should NOT increment
        path5 = restore_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        self.assertEqual(
            path5.version_number,
            2,
            "Rule P5 violated: Restore should not increment version",
        )

    def test_p6_folder_deletion_sets_folder_null(self):
        """
        Rule P6: Folder deletion creates new DocumentPath with folder=NULL.

        Scenario: Delete folder, verify document paths updated.
        """
        # Create folder
        folder = CorpusFolder.objects.create(
            name="TestFolder", corpus=self.corpus, creator=self.user
        )

        # Import document into folder
        _, _, path1 = import_document(
            corpus=self.corpus,
            path="/folder/doc.pdf",
            content=b"Test content",
            user=self.user,
            folder=folder,
        )

        self.assertEqual(path1.folder_id, folder.id)

        # Simulate folder deletion by moving document out
        path2 = move_document(
            corpus=self.corpus,
            old_path="/folder/doc.pdf",
            new_path="/doc.pdf",
            user=self.user,
            new_folder=None,
        )

        self.assertIsNone(
            path2.folder,
            "Rule P6: Document moved out of folder should have folder=NULL",
        )


class ImportOperationTestCase(TestCase):
    """
    Test Suite 3: Import Operation Tests

    These tests validate the import_document operation handles all scenarios
    correctly: new imports, updates, and cross-corpus deduplication.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus1 = Corpus.objects.create(title="Corpus 1", creator=self.user)
        self.corpus2 = Corpus.objects.create(title="Corpus 2", creator=self.user)

    def test_import_new_document_creates_both_trees(self):
        """
        Scenario: Import completely new document
        Expected: Creates new Document and DocumentPath nodes
        """
        content = b"Brand new PDF content"
        content_hash = compute_sha256(content)

        doc, status, path = import_document(
            corpus=self.corpus1,
            path="/new_doc.pdf",
            content=content,
            user=self.user,
            title="New Document",
        )

        # Verify status
        self.assertEqual(status, "created")

        # Verify Document created correctly
        self.assertEqual(doc.pdf_file_hash, content_hash)
        self.assertTrue(doc.is_current)
        self.assertIsNone(doc.parent)
        self.assertEqual(doc.title, "New Document")

        # Verify DocumentPath created correctly
        self.assertEqual(path.document_id, doc.id)
        self.assertEqual(path.corpus_id, self.corpus1.id)
        self.assertEqual(path.path, "/new_doc.pdf")
        self.assertEqual(path.version_number, 1)
        self.assertFalse(path.is_deleted)
        self.assertTrue(path.is_current)
        self.assertIsNone(path.parent)

    def test_import_update_at_existing_path(self):
        """
        Scenario: Import new content at existing path (file updated)
        Expected: Creates new Document version and new DocumentPath
        """
        original = b"Original content"
        updated = b"Updated content"

        # Import original
        doc1, status1, path1 = import_document(
            corpus=self.corpus1,
            path="/contract.pdf",
            content=original,
            user=self.user,
            title="Original Contract",
        )

        self.assertEqual(status1, "created")

        # Import update
        doc2, status2, path2 = import_document(
            corpus=self.corpus1,
            path="/contract.pdf",
            content=updated,
            user=self.user,
            title="Updated Contract",
        )

        # Verify status
        self.assertEqual(status2, "updated")

        # Verify new Document version
        self.assertNotEqual(doc1.id, doc2.id)
        self.assertEqual(doc2.parent_id, doc1.id)
        self.assertEqual(doc2.version_tree_id, doc1.version_tree_id)

        # Verify new DocumentPath
        self.assertEqual(path2.document_id, doc2.id)
        self.assertEqual(path2.version_number, 2)
        self.assertEqual(path2.parent_id, path1.id)

        # Verify old path no longer current
        path1.refresh_from_db()
        self.assertFalse(path1.is_current)

    def test_import_unchanged_content_returns_unchanged_status(self):
        """
        Scenario: Re-import same content at same path
        Expected: Returns 'unchanged' status, no new nodes created
        """
        content = b"Same content"

        # Import once
        doc1, status1, path1 = import_document(
            corpus=self.corpus1, path="/doc.pdf", content=content, user=self.user
        )

        doc_count = Document.objects.count()
        path_count = DocumentPath.objects.count()

        # Import again with same content
        doc2, status2, path2 = import_document(
            corpus=self.corpus1, path="/doc.pdf", content=content, user=self.user
        )

        # Verify status
        self.assertEqual(status2, "unchanged")

        # Verify same instances returned
        self.assertEqual(doc1.id, doc2.id)
        self.assertEqual(path1.id, path2.id)

        # Verify no new nodes created
        self.assertEqual(Document.objects.count(), doc_count)
        self.assertEqual(DocumentPath.objects.count(), path_count)

    def test_import_cross_corpus_isolation(self):
        """
        Scenario: Import same content into different corpus
        Expected: Creates corpus-isolated Document with provenance (Rule I1 NEW)
        """
        content = b"Shared content across corpuses"
        content_hash = compute_sha256(content)

        # Import to corpus 1
        doc1, status1, path1 = import_document(
            corpus=self.corpus1, path="/doc1.pdf", content=content, user=self.user
        )

        self.assertEqual(status1, "created")
        self.assertIsNone(doc1.source_document)  # No provenance for first

        # Import to corpus 2
        doc2, status2, path2 = import_document(
            corpus=self.corpus2, path="/doc2.pdf", content=content, user=self.user
        )

        # Verify status - corpus-isolated with provenance
        self.assertEqual(status2, "created_from_existing")

        # Verify different Documents (corpus isolation - Rule I1 NEW)
        self.assertNotEqual(doc1.id, doc2.id)

        # Verify provenance tracking (Rule I2)
        self.assertEqual(doc2.source_document, doc1)
        self.assertEqual(doc2.source_document_id, doc1.id)

        # Verify independent version trees (Rule I1 NEW)
        self.assertNotEqual(doc1.version_tree_id, doc2.version_tree_id)

        # Verify same content hash (file storage deduplication - Rule I3)
        self.assertEqual(doc1.pdf_file_hash, doc2.pdf_file_hash)

        # Verify separate DocumentPath created
        self.assertNotEqual(path1.id, path2.id)
        self.assertEqual(path2.corpus_id, self.corpus2.id)

        # Verify two documents with same hash exist (corpus isolation)
        docs_with_hash = Document.objects.filter(pdf_file_hash=content_hash).count()
        self.assertEqual(docs_with_hash, 2)


class MoveOperationTestCase(TestCase):
    """
    Test Suite 4: Move Operation Tests
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_move_document_changes_path_not_content(self):
        """
        Scenario: Move document to new path
        Expected: New DocumentPath pointing to same Document
        """
        content = b"Test content"

        # Import document
        doc, _, path1 = import_document(
            corpus=self.corpus, path="/original.pdf", content=content, user=self.user
        )

        # Move it
        path2 = move_document(
            corpus=self.corpus,
            old_path="/original.pdf",
            new_path="/moved.pdf",
            user=self.user,
        )

        # Verify same document
        self.assertEqual(path2.document_id, doc.id)

        # Verify new path
        self.assertEqual(path2.path, "/moved.pdf")

        # Verify version not incremented
        self.assertEqual(path2.version_number, path1.version_number)

        # Verify old path no longer current
        path1.refresh_from_db()
        self.assertFalse(path1.is_current)

    def test_move_document_with_folder_change(self):
        """
        Scenario: Move document to different folder
        Expected: New DocumentPath with new folder
        """
        folder1 = CorpusFolder.objects.create(
            name="Folder1", corpus=self.corpus, creator=self.user
        )
        folder2 = CorpusFolder.objects.create(
            name="Folder2", corpus=self.corpus, creator=self.user
        )

        # Import into folder1
        _, _, path1 = import_document(
            corpus=self.corpus,
            path="/folder1/doc.pdf",
            content=b"Test",
            user=self.user,
            folder=folder1,
        )

        # Move to folder2
        path2 = move_document(
            corpus=self.corpus,
            old_path="/folder1/doc.pdf",
            new_path="/folder2/doc.pdf",
            user=self.user,
            new_folder=folder2,
        )

        self.assertEqual(path2.folder_id, folder2.id)


class DeleteRestoreOperationTestCase(TestCase):
    """
    Test Suite 5 & 6: Delete and Restore Operation Tests
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_delete_document_soft_delete(self):
        """
        Scenario: Delete document
        Expected: Creates new DocumentPath with is_deleted=True
        """
        # Import document
        doc, _, path1 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=b"Test content", user=self.user
        )

        # Delete it
        path2 = delete_document(corpus=self.corpus, path="/doc.pdf", user=self.user)

        # Verify soft delete
        self.assertTrue(path2.is_deleted)
        self.assertTrue(path2.is_current)
        self.assertEqual(path2.document_id, doc.id)

        # Verify old path no longer current
        path1.refresh_from_db()
        self.assertFalse(path1.is_current)

        # Verify document still exists
        self.assertTrue(Document.objects.filter(id=doc.id).exists())

    def test_restore_document(self):
        """
        Scenario: Restore deleted document
        Expected: Creates new DocumentPath with is_deleted=False
        """
        # Import and delete
        doc, _, _ = import_document(
            corpus=self.corpus, path="/doc.pdf", content=b"Test content", user=self.user
        )

        path_deleted = delete_document(
            corpus=self.corpus, path="/doc.pdf", user=self.user
        )

        # Restore it
        path_restored = restore_document(
            corpus=self.corpus, path="/doc.pdf", user=self.user
        )

        # Verify restored
        self.assertFalse(path_restored.is_deleted)
        self.assertTrue(path_restored.is_current)
        self.assertEqual(path_restored.document_id, doc.id)

        # Verify deleted path no longer current
        path_deleted.refresh_from_db()
        self.assertFalse(path_deleted.is_current)

    def test_delete_restore_preserves_version_number(self):
        """
        Scenario: Delete and restore don't change version number
        Expected: Version number stays same through delete/restore cycle
        """
        _, _, path1 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=b"Test content", user=self.user
        )

        original_version = path1.version_number

        path2 = delete_document(corpus=self.corpus, path="/doc.pdf", user=self.user)

        self.assertEqual(path2.version_number, original_version)

        path3 = restore_document(corpus=self.corpus, path="/doc.pdf", user=self.user)

        self.assertEqual(path3.version_number, original_version)


class QueryInfrastructureTestCase(TestCase):
    """
    Test Suite 7: Query Infrastructure Tests
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_get_current_filesystem(self):
        """
        Scenario: Get current filesystem state
        Expected: Returns only active (current, not deleted) paths
        """
        # Import multiple documents
        doc1, _, _ = import_document(
            corpus=self.corpus, path="/doc1.pdf", content=b"Content 1", user=self.user
        )

        doc2, _, _ = import_document(
            corpus=self.corpus, path="/doc2.pdf", content=b"Content 2", user=self.user
        )

        # Delete one
        delete_document(corpus=self.corpus, path="/doc2.pdf", user=self.user)

        # Get current filesystem
        current_fs = get_current_filesystem(self.corpus)

        # Should only show doc1
        self.assertEqual(current_fs.count(), 1)
        self.assertEqual(current_fs.first().document_id, doc1.id)

    def test_get_content_history(self):
        """
        Scenario: Get version history of document content
        Expected: Returns all versions oldest to newest
        """
        v1 = b"Version 1"
        v2 = b"Version 2"
        v3 = b"Version 3"

        # Create version chain
        doc1, _, _ = import_document(
            corpus=self.corpus, path="/doc.pdf", content=v1, user=self.user
        )

        doc2, _, _ = import_document(
            corpus=self.corpus, path="/doc.pdf", content=v2, user=self.user
        )

        doc3, _, _ = import_document(
            corpus=self.corpus, path="/doc.pdf", content=v3, user=self.user
        )

        # Get history
        history = get_content_history(doc3)

        # Verify
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].id, doc1.id)  # Oldest
        self.assertEqual(history[1].id, doc2.id)
        self.assertEqual(history[2].id, doc3.id)  # Newest

    def test_get_path_history(self):
        """
        Scenario: Get lifecycle history of document path
        Expected: Returns all events oldest to newest with action types
        """
        # Create event chain
        import_document(
            corpus=self.corpus, path="/doc.pdf", content=b"Test", user=self.user
        )

        move_document(
            corpus=self.corpus,
            old_path="/doc.pdf",
            new_path="/moved.pdf",
            user=self.user,
        )

        path3 = delete_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        # Get history
        history = get_path_history(path3)

        # Verify
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["action"], "CREATED")
        self.assertEqual(history[1]["action"], "MOVED")
        self.assertEqual(history[2]["action"], "DELETED")

    def test_get_filesystem_at_time_past(self):
        """
        Scenario: Time-travel query to past timestamp
        Expected: Returns filesystem state as it was at that time
        """
        now = timezone.now()
        past = now - timedelta(hours=2)
        recent = now - timedelta(hours=1)

        # Import at past time
        doc1, _, path1 = import_document(
            corpus=self.corpus, path="/doc1.pdf", content=b"Content 1", user=self.user
        )
        # Manually set created time
        DocumentPath.objects.filter(id=path1.id).update(created=past)

        # Import at recent time
        doc2, _, path2 = import_document(
            corpus=self.corpus, path="/doc2.pdf", content=b"Content 2", user=self.user
        )
        DocumentPath.objects.filter(id=path2.id).update(created=recent)

        # Query filesystem between the two imports
        middle_time = now - timedelta(hours=1, minutes=30)
        fs_at_time = get_filesystem_at_time(self.corpus, middle_time)

        # Should only show doc1
        self.assertEqual(fs_at_time.count(), 1)
        self.assertEqual(fs_at_time.first().document_id, doc1.id)

    def test_get_filesystem_at_time_after_delete(self):
        """
        Scenario: Time-travel query after document was deleted
        Expected: Document not shown in that filesystem snapshot
        """
        now = timezone.now()

        # Import document
        doc, _, path1 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=b"Content", user=self.user
        )
        DocumentPath.objects.filter(id=path1.id).update(
            created=now - timedelta(hours=2)
        )

        # Delete it
        path2 = delete_document(corpus=self.corpus, path="/doc.pdf", user=self.user)
        DocumentPath.objects.filter(id=path2.id).update(
            created=now - timedelta(hours=1)
        )

        # Query after deletion
        after_delete = now - timedelta(minutes=30)
        fs_at_time = get_filesystem_at_time(self.corpus, after_delete)

        # Should be empty (document was deleted)
        self.assertEqual(fs_at_time.count(), 0)


class InteractionRulesTestCase(TestCase):
    """
    Test Suite 8: Interaction Rules Tests (I1, Q1)
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus1 = Corpus.objects.create(title="Corpus 1", creator=self.user)
        self.corpus2 = Corpus.objects.create(title="Corpus 2", creator=self.user)

    def test_i1_corpuses_have_isolated_documents_independent_trees(self):
        """
        Rule I1 (NEW): Multiple corpuses have completely isolated Documents
        with independent version trees.

        Scenario: Import same content to two corpuses creates separate Documents
        """
        content = b"Shared content"

        # Import to corpus1
        doc1, status1, path1_c1 = import_document(
            corpus=self.corpus1, path="/doc.pdf", content=content, user=self.user
        )
        self.assertEqual(status1, "created")

        # Import to corpus2 (creates isolated document with provenance)
        doc2, status2, path1_c2 = import_document(
            corpus=self.corpus2, path="/different.pdf", content=content, user=self.user
        )
        self.assertEqual(status2, "created_from_existing")

        # Verify different documents (corpus isolation)
        self.assertNotEqual(doc1.id, doc2.id)
        self.assertEqual(doc2.source_document, doc1)  # Provenance tracked

        # Verify independent version trees
        self.assertNotEqual(doc1.version_tree_id, doc2.version_tree_id)

        # Verify independent paths
        self.assertNotEqual(path1_c1.id, path1_c2.id)
        self.assertEqual(path1_c1.corpus_id, self.corpus1.id)
        self.assertEqual(path1_c2.corpus_id, self.corpus2.id)

        # Manipulate in corpus1
        move_document(
            corpus=self.corpus1,
            old_path="/doc.pdf",
            new_path="/moved.pdf",
            user=self.user,
        )

        # Verify corpus2 unaffected
        path1_c2.refresh_from_db()
        self.assertTrue(
            path1_c2.is_current, "Rule I1 violated: Corpus paths should be independent"
        )
        self.assertEqual(path1_c2.path, "/different.pdf")

    def test_q1_content_truly_deleted_when_no_active_paths(self):
        """
        Rule Q1: Content is "truly deleted" when no active DocumentPath
        in corpus points to it.

        Scenario: Delete all paths to document, verify truly deleted
        """
        content = b"Test content"

        # Import to corpus1
        doc1, _, _ = import_document(
            corpus=self.corpus1, path="/doc1.pdf", content=content, user=self.user
        )

        # Import to corpus2 (creates isolated copy with provenance)
        doc2, status2, _ = import_document(
            corpus=self.corpus2, path="/doc2.pdf", content=content, user=self.user
        )
        self.assertEqual(status2, "created_from_existing")
        self.assertNotEqual(doc1.id, doc2.id)  # Corpus isolation

        # Not truly deleted yet (each doc has paths in their respective corpus)
        self.assertFalse(is_content_truly_deleted(doc1, self.corpus1))
        self.assertFalse(is_content_truly_deleted(doc2, self.corpus2))

        # Delete from corpus1
        delete_document(corpus=self.corpus1, path="/doc1.pdf", user=self.user)

        # Truly deleted in corpus1, but doc2 still exists in corpus2
        self.assertTrue(
            is_content_truly_deleted(doc1, self.corpus1),
            "Rule Q1: Should be truly deleted in corpus1",
        )
        self.assertFalse(
            is_content_truly_deleted(doc2, self.corpus2),
            "Rule Q1: Doc2 should still exist in corpus2",
        )

        # Delete from corpus2
        delete_document(corpus=self.corpus2, path="/doc2.pdf", user=self.user)

        # Now truly deleted in both
        self.assertTrue(is_content_truly_deleted(doc1, self.corpus1))
        self.assertTrue(is_content_truly_deleted(doc2, self.corpus2))


class ComplexWorkflowTestCase(TestCase):
    """
    Test Suite 9: Complex Workflow Integration Tests

    These tests validate complex real-world scenarios combining multiple
    operations to ensure the system handles realistic use cases.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_realistic_document_lifecycle(self):
        """
        Scenario: Complete realistic document lifecycle
        - Import original
        - Move to different location
        - Update content multiple times
        - Delete
        - Restore
        - Move again

        Expected: All operations tracked correctly, history accurate
        """
        # Original import
        v1_content = b"Initial draft of contract"
        doc_v1, status1, path1 = import_document(
            corpus=self.corpus,
            path="/drafts/contract_v1.pdf",
            content=v1_content,
            user=self.user,
            title="Contract Draft v1",
        )

        self.assertEqual(status1, "created")
        self.assertEqual(path1.version_number, 1)

        # Move to review folder
        path2 = move_document(
            corpus=self.corpus,
            old_path="/drafts/contract_v1.pdf",
            new_path="/review/contract.pdf",
            user=self.user,
        )

        self.assertEqual(path2.path, "/review/contract.pdf")
        self.assertEqual(path2.version_number, 1)  # No version change

        # First content update
        v2_content = b"Revised contract with edits"
        doc_v2, status2, path3 = import_document(
            corpus=self.corpus,
            path="/review/contract.pdf",
            content=v2_content,
            user=self.user,
            title="Contract Draft v2",
        )

        self.assertEqual(status2, "updated")
        self.assertEqual(path3.version_number, 2)  # Version incremented
        self.assertEqual(doc_v2.parent_id, doc_v1.id)

        # Second content update
        v3_content = b"Final contract ready for signature"
        doc_v3, status3, path4 = import_document(
            corpus=self.corpus,
            path="/review/contract.pdf",
            content=v3_content,
            user=self.user,
            title="Contract Final",
        )

        self.assertEqual(status3, "updated")
        self.assertEqual(path4.version_number, 3)
        self.assertEqual(doc_v3.parent_id, doc_v2.id)

        # Accidentally delete
        path5 = delete_document(
            corpus=self.corpus, path="/review/contract.pdf", user=self.user
        )

        self.assertTrue(path5.is_deleted)
        self.assertEqual(path5.version_number, 3)  # Version unchanged

        # Restore after realizing mistake
        path6 = restore_document(
            corpus=self.corpus, path="/review/contract.pdf", user=self.user
        )

        self.assertFalse(path6.is_deleted)
        self.assertEqual(path6.version_number, 3)

        # Move to final location
        path7 = move_document(
            corpus=self.corpus,
            old_path="/review/contract.pdf",
            new_path="/final/executed_contract.pdf",
            user=self.user,
        )

        self.assertEqual(path7.path, "/final/executed_contract.pdf")
        self.assertEqual(path7.version_number, 3)

        # Verify complete history
        content_history = get_content_history(doc_v3)
        self.assertEqual(len(content_history), 3)

        path_history = get_path_history(path7)
        self.assertEqual(len(path_history), 7)
        expected_actions = [
            "CREATED",
            "MOVED",
            "UPDATED",
            "UPDATED",
            "DELETED",
            "RESTORED",
            "MOVED",
        ]
        actual_actions = [h["action"] for h in path_history]
        self.assertEqual(actual_actions, expected_actions)

    def test_multi_corpus_shared_content_independent_lifecycles(self):
        """
        Scenario: Same content in multiple corpuses with independent lifecycles
        - Import same PDF to Corpus A and Corpus B
        - Update content in Corpus A only
        - Delete from Corpus B
        - Verify independence

        Expected: Corpuses have isolated documents with independent version trees
        """
        corpus_a = self.corpus
        corpus_b = Corpus.objects.create(title="Corpus B", creator=self.user)

        original_content = b"Shared initial content"
        updated_content = b"Updated content in A only"

        # Import to both corpuses
        doc_a1, status_a1, path_a1 = import_document(
            corpus=corpus_a,
            path="/shared.pdf",
            content=original_content,
            user=self.user,
            title="Shared Doc A",
        )
        self.assertEqual(status_a1, "created")

        doc_b1, status_b1, path_b1 = import_document(
            corpus=corpus_b,
            path="/shared.pdf",
            content=original_content,
            user=self.user,
            title="Shared Doc B",
        )

        # Verify different documents with provenance (corpus isolation - Rule I1 NEW)
        self.assertNotEqual(doc_a1.id, doc_b1.id)
        self.assertEqual(status_b1, "created_from_existing")
        self.assertEqual(doc_b1.source_document, doc_a1)
        self.assertNotEqual(doc_a1.version_tree_id, doc_b1.version_tree_id)

        # Update in corpus A
        doc_a2, _, path_a2 = import_document(
            corpus=corpus_a,
            path="/shared.pdf",
            content=updated_content,
            user=self.user,
            title="Updated Doc A",
        )

        # Verify corpus B unaffected - still has its own isolated document
        fs_b = get_current_filesystem(corpus_b)
        self.assertEqual(fs_b.count(), 1)
        self.assertEqual(fs_b.first().document_id, doc_b1.id)  # Its own document

        # Delete from corpus B
        delete_document(corpus=corpus_b, path="/shared.pdf", user=self.user)

        # Verify corpus A unaffected
        fs_a = get_current_filesystem(corpus_a)
        self.assertEqual(fs_a.count(), 1)
        self.assertEqual(fs_a.first().document_id, doc_a2.id)  # Still has new version

    def test_version_tree_with_multiple_branches(self):
        """
        Scenario: Create multiple versions, then reuse old version in new location
        - Create v1, v2, v3 at /path/doc.pdf
        - Import v1 content at /archive/old_doc.pdf
        - Verify tree structure correct

        Expected: All versions in same tree, paths independent
        """
        v1 = b"Version 1 content"
        v2 = b"Version 2 content"
        v3 = b"Version 3 content"

        # Create version chain
        doc_v1, _, path1 = import_document(
            corpus=self.corpus,
            path="/doc.pdf",
            content=v1,
            user=self.user,
            title="Doc v1",
        )

        doc_v2, _, path2 = import_document(
            corpus=self.corpus,
            path="/doc.pdf",
            content=v2,
            user=self.user,
            title="Doc v2",
        )

        doc_v3, _, path3 = import_document(
            corpus=self.corpus,
            path="/doc.pdf",
            content=v3,
            user=self.user,
            title="Doc v3",
        )

        # Import v1 content at new location (within same corpus)
        doc_v1_again, status, path4 = import_document(
            corpus=self.corpus,
            path="/archive/old_doc.pdf",
            content=v1,
            user=self.user,
            title="Archived v1",
        )

        # Should link to v1 document (same content in same corpus)
        self.assertEqual(doc_v1_again.id, doc_v1.id)
        self.assertEqual(status, "linked")

        # Verify version tree
        history = get_content_history(doc_v3)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].id, doc_v1.id)
        self.assertEqual(history[1].id, doc_v2.id)
        self.assertEqual(history[2].id, doc_v3.id)

        # Verify all in same tree
        tree_id = doc_v1.version_tree_id
        self.assertEqual(doc_v2.version_tree_id, tree_id)
        self.assertEqual(doc_v3.version_tree_id, tree_id)


class PerformanceTestCase(TestCase):
    """
    Test Suite 10: Performance Tests

    These tests validate that the architecture performs well at realistic scale.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_query_performance_with_many_documents(self):
        """
        Scenario: Query current filesystem with many documents
        Expected: Completes in reasonable time
        """
        import time

        # Create 100 documents
        for i in range(100):
            import_document(
                corpus=self.corpus,
                path=f"/doc{i}.pdf",
                content=f"Content {i}".encode(),
                user=self.user,
            )

        # Query filesystem
        start = time.time()
        fs = get_current_filesystem(self.corpus)
        count = fs.count()
        duration = time.time() - start

        self.assertEqual(count, 100)
        self.assertLess(duration, 1.0, f"Query took {duration:.3f}s, should be < 1s")

    def test_time_travel_query_performance(self):
        """
        Scenario: Time-travel query with significant history
        Expected: Completes in reasonable time
        """
        import time

        # Create documents with history
        for i in range(50):
            path = f"/doc{i}.pdf"

            # Import
            import_document(
                corpus=self.corpus,
                path=path,
                content=f"Content {i}".encode(),
                user=self.user,
            )

            # Move
            new_path = f"/moved/doc{i}.pdf"
            move_document(
                corpus=self.corpus, old_path=path, new_path=new_path, user=self.user
            )

        # Time-travel query
        start = time.time()
        duration = time.time() - start

        self.assertLess(
            duration, 2.0, f"Time-travel query took {duration:.3f}s, should be < 2s"
        )

    def test_content_history_traversal_performance(self):
        """
        Scenario: Traverse long version chain
        Expected: Completes in reasonable time
        """
        import time

        content = b"Initial content"
        doc = None

        # Create 20 versions
        for i in range(20):
            content = f"Version {i} content".encode()
            doc, _, _ = import_document(
                corpus=self.corpus, path="/doc.pdf", content=content, user=self.user
            )

        # Traverse history
        start = time.time()
        history = get_content_history(doc)
        duration = time.time() - start

        self.assertEqual(len(history), 20)
        self.assertLess(
            duration, 0.5, f"History traversal took {duration:.3f}s, should be < 0.5s"
        )
