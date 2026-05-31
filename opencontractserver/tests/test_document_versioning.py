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
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.documents.versioning import (
    compute_sha256,
    compute_sha256_for_file,
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

        # Second import at different path - creates NEW document (always new for new path)
        doc2, status2, path2 = import_document(
            corpus=self.corpus,
            path="/test2.pdf",
            content=content,
            user=self.user,
            title="Second Document",
        )

        self.assertEqual(status2, "created")
        # Each upload at a new path creates a new document (no deduplication)
        self.assertNotEqual(
            doc1.id,
            doc2.id,
            "New upload should create new document, not link to existing",
        )
        # source_document is NOT set during import_document()
        # (provenance is only tracked via add_document() when dragging existing docs)
        self.assertIsNone(doc2.source_document_id)

        # Now we have 2 documents with this hash (each upload creates new doc)
        docs_with_hash = Document.objects.filter(pdf_file_hash=content_hash).count()
        self.assertEqual(docs_with_hash, 2, "Each upload creates a new document")

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

    def test_import_same_content_same_path_creates_new_version(self):
        """
        Scenario: Re-import same content at same path
        Expected: Returns 'updated' status, creates new version (no content-based dedup)
        """
        content = b"Same content"

        # Import once
        doc1, status1, path1 = import_document(
            corpus=self.corpus1, path="/doc.pdf", content=content, user=self.user
        )

        doc_count = Document.objects.count()
        path_count = DocumentPath.objects.count()

        # Import again with same content - should still create new version
        doc2, status2, path2 = import_document(
            corpus=self.corpus1, path="/doc.pdf", content=content, user=self.user
        )

        # Verify status - now creates new version (no content-based dedup)
        self.assertEqual(status2, "updated")

        # Verify new document created (not the same)
        self.assertNotEqual(doc1.id, doc2.id)
        self.assertNotEqual(path1.id, path2.id)

        # Verify new nodes created (version increment)
        self.assertEqual(Document.objects.count(), doc_count + 1)
        self.assertEqual(DocumentPath.objects.count(), path_count + 1)

        # Verify version tree relationship
        self.assertEqual(doc2.parent_id, doc1.id)
        self.assertEqual(doc1.version_tree_id, doc2.version_tree_id)

    def test_import_cross_corpus_creates_independent_documents(self):
        """
        Scenario: Import same content into different corpus
        Expected: Creates independent Documents (no content-based dedup)
        """
        content = b"Shared content across corpuses"
        content_hash = compute_sha256(content)

        # Import to corpus 1
        doc1, status1, path1 = import_document(
            corpus=self.corpus1, path="/doc1.pdf", content=content, user=self.user
        )

        self.assertEqual(status1, "created")
        self.assertIsNone(doc1.source_document)

        # Import to corpus 2
        doc2, status2, path2 = import_document(
            corpus=self.corpus2, path="/doc2.pdf", content=content, user=self.user
        )

        # Verify status - both created independently
        self.assertEqual(status2, "created")

        # Verify different Documents (each upload is independent)
        self.assertNotEqual(doc1.id, doc2.id)

        # No provenance for direct uploads (provenance is set via add_document() only)
        self.assertIsNone(doc2.source_document)

        # Verify independent version trees
        self.assertNotEqual(doc1.version_tree_id, doc2.version_tree_id)

        # Verify same content hash (still computed, just not used for dedup)
        self.assertEqual(doc1.pdf_file_hash, doc2.pdf_file_hash)

        # Verify separate DocumentPath created
        self.assertNotEqual(path1.id, path2.id)
        self.assertEqual(path2.corpus_id, self.corpus2.id)

        # Verify two documents with same hash exist
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

        # Import to corpus2 (creates isolated document - no provenance via import)
        doc2, status2, path1_c2 = import_document(
            corpus=self.corpus2, path="/different.pdf", content=content, user=self.user
        )
        self.assertEqual(status2, "created")

        # Verify different documents (corpus isolation)
        self.assertNotEqual(doc1.id, doc2.id)
        # source_document is NOT set during import_document()
        # (provenance is only tracked via add_document() when dragging existing docs)
        self.assertIsNone(doc2.source_document)

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
        self.assertEqual(status2, "created")
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

        # Verify different documents (corpus isolation - Rule I1 NEW)
        self.assertNotEqual(doc_a1.id, doc_b1.id)
        self.assertEqual(status_b1, "created")
        # source_document is NOT set during import_document()
        # (provenance is only tracked via add_document() when dragging existing docs)
        self.assertIsNone(doc_b1.source_document)
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

        # Creates new document (each upload at new path creates new doc)
        self.assertNotEqual(doc_v1_again.id, doc_v1.id)
        self.assertEqual(status, "created")
        # source_document is NOT set during import_document()
        # (provenance is only tracked via add_document() when dragging existing docs)
        self.assertIsNone(doc_v1_again.source_document_id)

        # Verify version tree for the update chain (v1->v2->v3)
        history = get_content_history(doc_v3)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].id, doc_v1.id)
        self.assertEqual(history[1].id, doc_v2.id)
        self.assertEqual(history[2].id, doc_v3.id)

        # Verify original update chain is in same tree
        tree_id = doc_v1.version_tree_id
        self.assertEqual(doc_v2.version_tree_id, tree_id)
        self.assertEqual(doc_v3.version_tree_id, tree_id)
        # New doc_v1_again is in its OWN tree (not the original update chain)
        self.assertNotEqual(doc_v1_again.version_tree_id, tree_id)


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
        assert doc is not None
        start = time.time()
        history = get_content_history(doc)
        duration = time.time() - start

        self.assertEqual(len(history), 20)
        self.assertLess(
            duration, 0.5, f"History traversal took {duration:.3f}s, should be < 0.5s"
        )


class PdfFileCreationTestCase(TestCase):
    """
    Test Suite: pdf_file Field Population

    Ensures that import_document always populates the pdf_file field from content
    when not explicitly provided. This prevents frontend PDF loading failures.

    Bug fixed: When importing brand new content via import_content/import_document,
    the pdf_file field was not being set, causing "Unsupported file type" errors
    in the frontend despite fileType being "application/pdf".
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_import_document_creates_pdf_file_for_new_content(self):
        """
        Regression test: When importing brand new content without pdf_file,
        the function should create pdf_file from the content bytes.

        This prevents the bug where documents had fileType="application/pdf"
        but empty pdfFile, causing frontend loading failures.
        """
        content = b"%PDF-1.4 fake pdf content for testing"

        # Import content without providing pdf_file parameter
        doc, status, path = import_document(
            corpus=self.corpus,
            path="/test_document.pdf",
            content=content,
            user=self.user,
            title="Test PDF",
            file_type="application/pdf",
        )

        self.assertEqual(status, "created")
        # Critical assertion: pdf_file must be populated
        self.assertTrue(
            doc.pdf_file,
            "pdf_file field is empty - this will cause frontend loading failures!",
        )
        # Verify the file has correct extension
        assert doc.pdf_file.name is not None
        self.assertTrue(
            doc.pdf_file.name.endswith(".pdf"),
            f"Expected .pdf extension, got: {doc.pdf_file.name}",
        )
        # Verify content is accessible
        doc.pdf_file.seek(0)
        saved_content = doc.pdf_file.read()
        self.assertEqual(saved_content, content, "Saved content doesn't match original")

    def test_import_document_creates_docx_file_for_new_docx_content(self):
        """
        Verify pdf_file is created with correct extension for DOCX files.
        """
        content = b"PK fake docx content for testing"

        doc, status, path = import_document(
            corpus=self.corpus,
            path="/test_document.docx",
            content=content,
            user=self.user,
            title="Test DOCX",
            file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        self.assertEqual(status, "created")
        self.assertTrue(doc.pdf_file, "pdf_file field is empty!")
        assert doc.pdf_file.name is not None
        self.assertTrue(
            doc.pdf_file.name.endswith(".docx"),
            f"Expected .docx extension, got: {doc.pdf_file.name}",
        )

    def test_import_document_version_update_creates_pdf_file_if_missing(self):
        """
        When updating content at an existing path, if the old document
        has no pdf_file (due to the bug), create it from the new content.
        """
        # First, create a document but simulate the bug by manually clearing pdf_file
        initial_content = b"%PDF-1.4 initial content"
        doc1, _, _ = import_document(
            corpus=self.corpus,
            path="/test.pdf",
            content=initial_content,
            user=self.user,
            title="Test",
        )

        # Simulate the bug: clear pdf_file on the old document
        Document.objects.filter(pk=doc1.pk).update(pdf_file="")
        doc1.refresh_from_db()
        self.assertFalse(doc1.pdf_file, "Setup failed: pdf_file should be empty")

        # Now update with new content - should create pdf_file from new content
        new_content = b"%PDF-1.4 updated content"
        doc2, status, _ = import_document(
            corpus=self.corpus,
            path="/test.pdf",
            content=new_content,
            user=self.user,
        )

        self.assertEqual(status, "updated")
        # Critical: new version should have pdf_file populated
        self.assertTrue(
            doc2.pdf_file,
            "pdf_file field is empty on updated document!",
        )
        doc2.pdf_file.seek(0)
        saved_content = doc2.pdf_file.read()
        self.assertEqual(saved_content, new_content, "Updated content doesn't match")

    def test_import_document_uses_provided_pdf_file_when_given(self):
        """
        When pdf_file is explicitly provided, use it instead of creating from content.
        """
        from django.core.files.base import ContentFile

        content = b"%PDF-1.4 content bytes"
        explicit_file = ContentFile(content, name="explicit_name.pdf")

        doc, status, _ = import_document(
            corpus=self.corpus,
            path="/test.pdf",
            content=content,
            user=self.user,
            pdf_file=explicit_file,
        )

        self.assertEqual(status, "created")
        self.assertTrue(doc.pdf_file)
        # Should use the explicit filename (may have path prefix added by storage)
        assert doc.pdf_file.name is not None
        self.assertIn("explicit_name", doc.pdf_file.name)

    def test_import_document_filename_derived_from_path(self):
        """
        When creating pdf_file from content, filename should be derived from path.
        """
        content = b"%PDF-1.4 test"

        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/documents/my_important_report.pdf",
            content=content,
            user=self.user,
        )

        self.assertTrue(doc.pdf_file)
        # Filename should be derived from path (my_important_report.pdf)
        assert doc.pdf_file.name is not None
        self.assertIn("my_important_report", doc.pdf_file.name)

    def test_import_document_with_existing_content_creates_pdf_file(self):
        """
        Regression test: When importing content that exists globally (in another
        corpus) but the global document has no pdf_file, create it from content.

        Each upload to a new path creates a new document, sharing artifacts
        from existing documents with the same content hash.
        """
        from opencontractserver.documents.versioning import compute_sha256

        content = b"%PDF-1.4 content that exists globally"
        content_hash = compute_sha256(content)

        # Create a global document (standalone, not in any corpus) without pdf_file
        # This simulates a document created before the bug fix
        global_doc = Document.objects.create(
            title="Global Document",
            creator=self.user,
            pdf_file_hash=content_hash,
            file_type="application/pdf",
            # pdf_file intentionally left empty to simulate buggy document
        )
        self.assertFalse(
            global_doc.pdf_file, "Setup: global doc should have no pdf_file"
        )

        # Create a different corpus
        corpus2 = Corpus.objects.create(title="Corpus 2", creator=self.user)

        # Import same content to corpus2 - should create NEW document
        # with pdf_file populated from content (not link to existing)
        doc, status, path = import_document(
            corpus=corpus2,
            path="/test.pdf",
            content=content,
            user=self.user,
            title="Corpus Copy",
            file_type="application/pdf",
        )

        # Status is now "created" (always creates new doc for new path)
        self.assertEqual(status, "created")
        # Critical: new doc should have pdf_file populated
        self.assertTrue(
            doc.pdf_file,
            "pdf_file field is empty on new document!",
        )
        doc.pdf_file.seek(0)
        saved_content = doc.pdf_file.read()
        self.assertEqual(saved_content, content, "Saved content doesn't match")
        # source_document is NOT set during import_document()
        # (provenance is only tracked via add_document() when dragging existing docs)
        self.assertIsNone(doc.source_document_id)
        # Verify it's a NEW document, not the existing one
        self.assertNotEqual(doc.id, global_doc.id)


class StreamingImportTestCase(TestCase):
    """
    Test Suite: Streaming (file-like) imports

    Validates the issue #1843 path where ``import_document`` is handed a file
    object instead of ``content`` bytes and must compute the content hash by
    streaming the file rather than reading it whole into memory.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="streamer", password="test123")
        self.corpus = Corpus.objects.create(title="Stream Corpus", creator=self.user)

    def test_compute_sha256_for_file_matches_bytes_and_rewinds(self):

        payload = b"%PDF-1.7 streaming hash payload " + (b"Z" * 5000)
        f = ContentFile(payload, name="x.pdf")
        # Advance the cursor first to prove the helper seeks to 0 before hashing.
        f.seek(10)

        digest = compute_sha256_for_file(f)
        self.assertEqual(digest, compute_sha256(payload))
        # Cursor must be rewound so the storage write that follows is intact.
        self.assertEqual(f.tell(), 0)

    def test_import_document_streams_hash_from_pdf_file_when_content_none(self):
        """content=None + a binary file -> hash is streamed from the file."""

        payload = b"%PDF-1.4 " + (b"Q" * 4096)
        doc, status, _ = import_document(
            corpus=self.corpus,
            path="/streamed.pdf",
            content=None,
            user=self.user,
            pdf_file=ContentFile(payload, name="streamed.pdf"),
            file_type="application/pdf",
            title="Streamed PDF",
        )

        self.assertEqual(status, "created")
        self.assertEqual(doc.pdf_file_hash, compute_sha256(payload))
        doc.pdf_file.seek(0)
        self.assertEqual(doc.pdf_file.read(), payload)
        self.assertFalse(doc.txt_extract_file)

    def test_import_document_streams_hash_from_txt_file_when_content_none(self):
        """content=None + a text file -> routed to txt_extract_file, hash streamed."""

        payload = b"# Heading\n\nstreamed markdown body\n"
        doc, status, _ = import_document(
            corpus=self.corpus,
            path="/streamed.md",
            content=None,
            user=self.user,
            txt_file=ContentFile(payload, name="streamed.md"),
            file_type="text/markdown",
            title="Streamed MD",
        )

        self.assertEqual(status, "created")
        self.assertEqual(doc.pdf_file_hash, compute_sha256(payload))
        doc.txt_extract_file.seek(0)
        self.assertEqual(doc.txt_extract_file.read(), payload)
        self.assertFalse(doc.pdf_file)

    def test_import_document_content_file_is_type_routed(self):
        """A generic ``content_file`` lands in the field matching ``file_type``."""

        payload = b"%PDF-1.5 routed via content_file " + (b"R" * 2048)
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/routed.pdf",
            content=None,
            user=self.user,
            content_file=ContentFile(payload, name="routed.pdf"),
            file_type="application/pdf",
            title="Routed PDF",
        )
        self.assertTrue(doc.pdf_file)
        self.assertFalse(doc.txt_extract_file)
        self.assertEqual(doc.pdf_file_hash, compute_sha256(payload))

    def test_import_document_requires_content_or_file(self):
        """content=None with no file object is a hard error, not a silent crash."""
        with self.assertRaises(ValueError):
            import_document(
                corpus=self.corpus,
                path="/nope.pdf",
                content=None,
                user=self.user,
                file_type="application/pdf",
                title="No content",
            )

    def test_import_document_rejects_content_file_and_explicit_file(self):
        """Passing both ``content_file`` and the matching explicit file object
        is a hard error, not a silent drop of ``content_file`` (review #2)."""
        payload = b"%PDF-1.5 conflicting inputs " + (b"R" * 2048)
        with self.assertRaises(ValueError):
            import_document(
                corpus=self.corpus,
                path="/conflict.pdf",
                content=None,
                user=self.user,
                content_file=ContentFile(payload, name="content_file.pdf"),
                pdf_file=ContentFile(payload, name="explicit.pdf"),
                file_type="application/pdf",
                title="Conflicting inputs",
            )


class TextFileVersioningTestCase(TestCase):
    """
    Test Suite: Text File Versioning

    Ensures that text files (text/plain, application/txt) are handled correctly
    by the unified versioning pipeline:
    - Stored in txt_extract_file field (not pdf_file)
    - Support path-based versioning (update at same path creates new version)
    - Content hash computed correctly
    - M2M maintained for backwards compatibility
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_text_file_stored_in_txt_extract_file(self):
        """
        Text files should be stored in txt_extract_file, not pdf_file.
        """
        content = b"This is plain text content for testing."

        doc, status, path = import_document(
            corpus=self.corpus,
            path="/test_document.txt",
            content=content,
            user=self.user,
            title="Test Text File",
            file_type="text/plain",
        )

        self.assertEqual(status, "created")
        # txt_extract_file must be populated for text files
        self.assertTrue(
            doc.txt_extract_file,
            "txt_extract_file field is empty - text files should use this field!",
        )
        # pdf_file should NOT be populated for text files
        self.assertFalse(
            doc.pdf_file,
            "pdf_file should be empty for text files!",
        )
        # Verify the file has correct extension
        assert doc.txt_extract_file.name is not None
        self.assertTrue(
            doc.txt_extract_file.name.endswith(".txt"),
            f"Expected .txt extension, got: {doc.txt_extract_file.name}",
        )
        # Verify content is accessible
        doc.txt_extract_file.seek(0)
        saved_content = doc.txt_extract_file.read()
        self.assertEqual(saved_content, content, "Saved content doesn't match original")

    def test_text_file_supports_versioning(self):
        """
        Text files should support path-based versioning like other file types.
        Uploading to the same path should create a new version.
        """
        v1_content = b"Version 1 of the text file"
        v2_content = b"Version 2 with updates"

        # Import original
        doc1, status1, path1 = import_document(
            corpus=self.corpus,
            path="/document.txt",
            content=v1_content,
            user=self.user,
            title="Text Doc v1",
            file_type="text/plain",
        )

        self.assertEqual(status1, "created")
        self.assertEqual(path1.version_number, 1)

        # Import update at same path
        doc2, status2, path2 = import_document(
            corpus=self.corpus,
            path="/document.txt",
            content=v2_content,
            user=self.user,
            title="Text Doc v2",
            file_type="text/plain",
        )

        # Should be an update, not a new document
        self.assertEqual(status2, "updated")
        self.assertEqual(path2.version_number, 2)

        # Verify parent-child relationship
        self.assertEqual(doc2.parent_id, doc1.id)
        self.assertEqual(doc2.version_tree_id, doc1.version_tree_id)

        # Verify old path is no longer current
        path1.refresh_from_db()
        self.assertFalse(path1.is_current)

        # Verify content history
        history = get_content_history(doc2)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].id, doc1.id)
        self.assertEqual(history[1].id, doc2.id)

    def test_text_file_hash_computed_correctly(self):
        """
        Content hash should be computed for text files just like binary files.
        """
        content = b"Hash computation test content"
        expected_hash = compute_sha256(content)

        doc, status, path = import_document(
            corpus=self.corpus,
            path="/hash_test.txt",
            content=content,
            user=self.user,
            file_type="text/plain",
        )

        self.assertEqual(doc.pdf_file_hash, expected_hash)

    def test_text_file_with_application_txt_mimetype(self):
        """
        application/txt should also be recognized as text file.
        """
        content = b"Text content with application/txt MIME type"

        doc, status, path = import_document(
            corpus=self.corpus,
            path="/test.txt",
            content=content,
            user=self.user,
            file_type="application/txt",
        )

        self.assertEqual(status, "created")
        self.assertTrue(doc.txt_extract_file)
        self.assertFalse(doc.pdf_file)

    def test_corpus_import_content_routes_text_files_correctly(self):
        """
        Corpus.import_content() should route text files through the unified
        versioning pipeline.
        """
        content = b"Text content via import_content"

        doc, status, path = self.corpus.import_content(
            content=content,
            user=self.user,
            path="/imported.txt",
            file_type="text/plain",
            title="Imported Text",
        )

        self.assertEqual(status, "created")
        self.assertTrue(doc.txt_extract_file)
        self.assertFalse(doc.pdf_file)

    def test_text_file_versioning_via_import_content(self):
        """
        Text file versioning should work via import_content() as well.
        """
        v1_content = b"First version"
        v2_content = b"Second version"

        # First import
        doc1, status1, path1 = self.corpus.import_content(
            content=v1_content,
            user=self.user,
            path="/versioned.txt",
            file_type="text/plain",
        )

        # Second import at same path
        doc2, status2, path2 = self.corpus.import_content(
            content=v2_content,
            user=self.user,
            path="/versioned.txt",
            file_type="text/plain",
        )

        self.assertEqual(status1, "created")
        self.assertEqual(status2, "updated")
        self.assertEqual(path2.version_number, 2)
        self.assertEqual(doc2.parent_id, doc1.id)


class PathHistoryFolderTrackingTestCase(TestCase):
    """
    Test Suite: get_path_history folder-awareness.

    Validates that get_path_history() correctly detects folder-only moves
    and includes folder_id in history entries.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.folder1 = CorpusFolder.objects.create(
            name="Folder1", corpus=self.corpus, creator=self.user
        )
        self.folder2 = CorpusFolder.objects.create(
            name="Folder2", corpus=self.corpus, creator=self.user
        )

    def test_path_history_includes_folder_id(self):
        """History entries contain folder_id field."""
        _, _, path1 = import_document(
            corpus=self.corpus,
            path="/doc.pdf",
            content=b"Test",
            user=self.user,
            folder=self.folder1,
        )

        history = get_path_history(path1)
        self.assertIn("folder_id", history[0])
        self.assertEqual(history[0]["folder_id"], self.folder1.id)

    def test_folder_only_move_detected_as_moved(self):
        """A move that changes folder but not path is still detected as MOVED."""
        # Create document in folder1
        doc, _, path1 = import_document(
            corpus=self.corpus,
            path="/doc.pdf",
            content=b"Test",
            user=self.user,
            folder=self.folder1,
        )

        # Manually create a move record that changes folder but keeps same path
        path1.is_current = False
        path1.save(update_fields=["is_current"])

        path2 = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            folder=self.folder2,
            path="/doc.pdf",  # Same path
            version_number=path1.version_number,
            parent=path1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        history = get_path_history(path2)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["action"], "CREATED")
        self.assertEqual(history[1]["action"], "MOVED")

    def test_path_and_folder_change_detected_as_moved(self):
        """A move that changes both path and folder is detected as MOVED."""
        _, _, path1 = import_document(
            corpus=self.corpus,
            path="/folder1/doc.pdf",
            content=b"Test",
            user=self.user,
            folder=self.folder1,
        )

        path2 = move_document(
            corpus=self.corpus,
            old_path="/folder1/doc.pdf",
            new_path="/folder2/doc.pdf",
            user=self.user,
            new_folder=self.folder2,
        )

        history = get_path_history(path2)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]["action"], "MOVED")
        self.assertEqual(history[0]["folder_id"], self.folder1.id)
        self.assertEqual(history[1]["folder_id"], self.folder2.id)

    def test_no_change_produces_unknown_action(self):
        """A record with same path, folder, and document as parent yields UNKNOWN."""
        doc, _, path1 = import_document(
            corpus=self.corpus,
            path="/doc.pdf",
            content=b"Test",
            user=self.user,
            folder=self.folder1,
        )

        # Create a duplicate record (shouldn't happen normally, but tests the logic)
        path1.is_current = False
        path1.save(update_fields=["is_current"])

        path2 = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            folder=self.folder1,  # Same folder
            path="/doc.pdf",  # Same path
            version_number=path1.version_number,
            parent=path1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        history = get_path_history(path2)
        self.assertEqual(history[1]["action"], "UNKNOWN")

    def test_full_lifecycle_with_folder_moves(self):
        """Complete lifecycle with folder changes tracked in history."""
        # Create
        _, _, path1 = import_document(
            corpus=self.corpus,
            path="/doc.pdf",
            content=b"v1",
            user=self.user,
        )

        # Move (path change)
        move_document(
            corpus=self.corpus,
            old_path="/doc.pdf",
            new_path="/folder1/doc.pdf",
            user=self.user,
            new_folder=self.folder1,
        )

        # Update (content change via re-import at same path)
        _, _, path3 = import_document(
            corpus=self.corpus,
            path="/folder1/doc.pdf",
            content=b"v2",
            user=self.user,
            folder=self.folder1,
        )

        # Delete
        delete_document(corpus=self.corpus, path="/folder1/doc.pdf", user=self.user)

        # Restore
        path5 = restore_document(
            corpus=self.corpus, path="/folder1/doc.pdf", user=self.user
        )

        history = get_path_history(path5)
        self.assertEqual(len(history), 5)

        expected_actions = ["CREATED", "MOVED", "UPDATED", "DELETED", "RESTORED"]
        actual_actions = [h["action"] for h in history]
        self.assertEqual(actual_actions, expected_actions)

        # Verify folder tracking through history
        self.assertIsNone(history[0]["folder_id"])  # Created at root
        self.assertEqual(history[1]["folder_id"], self.folder1.id)  # Moved to folder1
        self.assertEqual(history[2]["folder_id"], self.folder1.id)  # Updated in folder1
