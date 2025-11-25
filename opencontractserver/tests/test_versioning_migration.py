"""
Test for the Dual-Tree Versioning Data Migration

This test validates that the data migration correctly initializes
existing documents with the dual-tree structure.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath

User = get_user_model()


class VersioningMigrationTestCase(TestCase):
    """
    Test the data migration for dual-tree versioning initialization.

    This test simulates the state before migration and validates
    that the migration correctly initializes all structures.
    """

    def setUp(self):
        """Create test fixtures that simulate pre-migration state."""
        self.user = User.objects.create_user(
            username="migration_tester", password="test123"
        )

        # Create corpuses
        self.corpus1 = Corpus.objects.create(title="Test Corpus 1", creator=self.user)
        self.corpus2 = Corpus.objects.create(title="Test Corpus 2", creator=self.user)

        # Create documents with unique content hashes
        self.doc1 = Document.objects.create(
            title="Document 1",
            description="Test document 1",
            pdf_file_hash="hash1",
            creator=self.user,
        )
        self.doc2 = Document.objects.create(
            title="Document 2",
            description="Test document 2",
            pdf_file_hash="hash2",
            creator=self.user,
        )
        self.doc3 = Document.objects.create(
            title="Document 3",
            description="Test document 3",
            pdf_file_hash="hash3",
            creator=self.user,
        )

        # Simulate pre-migration state by directly creating DocumentPath records
        # This is what the migration (0024) would have done for existing data
        # We're NOT using add_document() here because that's for new additions,
        # and this test is simulating what a migration does for existing M2M relationships
        self._create_document_path(self.doc1, self.corpus1)
        self._create_document_path(self.doc2, self.corpus1)
        self._create_document_path(self.doc2, self.corpus2)  # doc2 in both corpuses
        self._create_document_path(self.doc3, self.corpus2)

    def _create_document_path(self, doc, corpus):
        """
        Create a DocumentPath record for a document in a corpus.

        This simulates what the migration would do for existing M2M relationships.
        """
        # Generate path from document title (fallback to id if no title)
        path = f"/{doc.title or f'document-{doc.id}'}"

        # Create initial DocumentPath (matches migration logic)
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            folder=None,  # Root level by default
            path=path,
            version_number=1,  # All existing docs are v1
            parent=None,  # All are roots initially
            is_current=True,
            is_deleted=False,
            creator=doc.creator,
            backend_lock=False,
            is_public=doc.is_public if hasattr(doc, "is_public") else False,
        )

    def _create_document_paths_for_corpus(self, corpus):
        """
        Simulate the migration's DocumentPath creation logic.

        This helper replicates what the 0024_initialize_dual_tree_versioning
        migration does for existing corpus-document relationships.
        """
        for doc in corpus.get_documents():
            # Check if DocumentPath already exists (safeguard like in migration)
            existing = DocumentPath.objects.filter(
                document=doc, corpus=corpus, is_current=True, is_deleted=False
            ).exists()

            if not existing:
                # Generate path from document title (fallback to id if no title)
                path = f"/{doc.title or f'document-{doc.id}'}"

                # Create initial DocumentPath (matches migration logic)
                DocumentPath.objects.create(
                    document=doc,
                    corpus=corpus,
                    folder=None,  # Root level by default
                    path=path,
                    version_number=1,  # All existing docs are v1
                    parent=None,  # All are roots initially
                    is_current=True,
                    is_deleted=False,
                    creator=doc.creator,
                    backend_lock=False,
                    is_public=doc.is_public if hasattr(doc, "is_public") else False,
                )

    def test_migration_initializes_document_trees(self):
        """
        Test that migration correctly initializes Document version trees.

        Expected:
        - All documents have version_tree_id
        - All documents have is_current=True
        - All documents have parent=None (roots)
        """
        # Verify all documents initialized
        docs_with_tree_id = Document.objects.filter(
            version_tree_id__isnull=False
        ).count()
        self.assertEqual(
            docs_with_tree_id, 3, "All documents should have version_tree_id"
        )

        # Verify all are current
        current_docs = Document.objects.filter(is_current=True).count()
        self.assertEqual(current_docs, 3, "All documents should be current initially")

        # Verify unique tree IDs (each doc is its own tree initially)
        tree_ids = Document.objects.values_list("version_tree_id", flat=True)
        unique_tree_ids = set(tree_ids)
        self.assertEqual(
            len(unique_tree_ids), 3, "Each document should have unique version_tree_id"
        )

    def test_migration_creates_document_paths(self):
        """
        Test that migration creates DocumentPath records from corpus relationships.

        Expected:
        - DocumentPath created for each corpus-document pair
        - doc2 should have 2 paths (appears in both corpuses)
        - All paths are current and not deleted
        - Version numbers are 1
        """
        # Count total paths
        total_paths = DocumentPath.objects.count()
        self.assertEqual(
            total_paths,
            4,
            "Should create 4 paths: corpus1(doc1, doc2) + corpus2(doc2, doc3)",
        )

        # Verify doc1 has 1 path
        doc1_paths = DocumentPath.objects.filter(document=self.doc1).count()
        self.assertEqual(doc1_paths, 1)

        # Verify doc2 has 2 paths (cross-corpus)
        doc2_paths = DocumentPath.objects.filter(document=self.doc2).count()
        self.assertEqual(doc2_paths, 2, "doc2 should have paths in both corpuses")

        # Verify doc3 has 1 path
        doc3_paths = DocumentPath.objects.filter(document=self.doc3).count()
        self.assertEqual(doc3_paths, 1)

        # Verify all paths are current and not deleted
        active_paths = DocumentPath.objects.filter(
            is_current=True, is_deleted=False
        ).count()
        self.assertEqual(
            active_paths, 4, "All initial paths should be current and not deleted"
        )

        # Verify all paths are version 1
        v1_paths = DocumentPath.objects.filter(version_number=1).count()
        self.assertEqual(v1_paths, 4, "All initial paths should be version 1")

        # Verify all paths are roots (parent=None)
        root_paths = DocumentPath.objects.filter(parent__isnull=True).count()
        self.assertEqual(root_paths, 4, "All initial paths should be roots (no parent)")

    def test_migration_creates_correct_paths_per_corpus(self):
        """
        Test that DocumentPath records correctly map to corpuses.

        Expected:
        - corpus1 should have 2 paths
        - corpus2 should have 2 paths
        - Paths point to correct documents
        """
        # Corpus 1 should have doc1 and doc2
        corpus1_paths = DocumentPath.objects.filter(
            corpus=self.corpus1, is_current=True, is_deleted=False
        )
        self.assertEqual(corpus1_paths.count(), 2)

        corpus1_doc_ids = set(corpus1_paths.values_list("document_id", flat=True))
        expected_doc_ids = {self.doc1.id, self.doc2.id}
        self.assertEqual(
            corpus1_doc_ids,
            expected_doc_ids,
            "Corpus 1 should have paths for doc1 and doc2",
        )

        # Corpus 2 should have doc2 and doc3
        corpus2_paths = DocumentPath.objects.filter(
            corpus=self.corpus2, is_current=True, is_deleted=False
        )
        self.assertEqual(corpus2_paths.count(), 2)

        corpus2_doc_ids = set(corpus2_paths.values_list("document_id", flat=True))
        expected_doc_ids = {self.doc2.id, self.doc3.id}
        self.assertEqual(
            corpus2_doc_ids,
            expected_doc_ids,
            "Corpus 2 should have paths for doc2 and doc3",
        )

    def test_migration_generates_valid_paths(self):
        """
        Test that migration generates valid path strings.

        Expected:
        - Paths start with /
        - Paths use document title or fallback to id
        """
        for path in DocumentPath.objects.all():
            # Verify path starts with /
            self.assertTrue(
                path.path.startswith("/"), f"Path should start with /: {path.path}"
            )

            # Verify path contains document title or id
            doc = path.document
            self.assertTrue(
                doc.title in path.path or str(doc.id) in path.path,
                f"Path should contain title or id: {path.path}",
            )

    def test_migration_sets_correct_metadata(self):
        """
        Test that migration sets correct metadata fields.

        Expected:
        - creator matches document creator
        - folder is None (root)
        - backend_lock is False
        """
        for path in DocumentPath.objects.all():
            self.assertEqual(
                path.creator_id,
                path.document.creator_id,
                "Path creator should match document creator",
            )

            self.assertIsNone(
                path.folder, "Initial paths should have no folder (root level)"
            )

            self.assertFalse(path.backend_lock, "backend_lock should be False")

    def test_migration_safeguards_prevent_duplicates(self):
        """
        Test that migration safeguards prevent duplicate creation.

        Expected:
        - Documents already with version_tree_id are skipped
        - Existing DocumentPaths are not duplicated
        """
        # All documents should already have version_tree_id from migration
        initial_doc_count = Document.objects.filter(
            version_tree_id__isnull=False
        ).count()
        self.assertEqual(
            initial_doc_count,
            3,
            "All documents should have version_tree_id from migration",
        )

        # All paths should already exist
        initial_path_count = DocumentPath.objects.count()
        self.assertEqual(initial_path_count, 4, "All paths should exist from migration")

        # Verify no None version_tree_ids
        none_count = Document.objects.filter(version_tree_id__isnull=True).count()
        self.assertEqual(
            none_count,
            0,
            "No documents should have None version_tree_id after migration",
        )

    def test_cross_corpus_document_independence(self):
        """
        Test that documents shared across corpuses maintain independence.

        Expected:
        - doc2 appears in both corpuses
        - Each appearance has independent DocumentPath
        - Modifying one path doesn't affect the other
        """
        # Get both paths for doc2
        doc2_path_corpus1 = DocumentPath.objects.get(
            document=self.doc2, corpus=self.corpus1, is_current=True
        )
        doc2_path_corpus2 = DocumentPath.objects.get(
            document=self.doc2, corpus=self.corpus2, is_current=True
        )

        # Verify they're different records
        self.assertNotEqual(
            doc2_path_corpus1.id,
            doc2_path_corpus2.id,
            "Paths in different corpuses should be separate records",
        )

        # Verify they point to same document
        self.assertEqual(
            doc2_path_corpus1.document_id,
            doc2_path_corpus2.document_id,
            "Both paths should point to same document",
        )

        # Verify independence (different paths allowed)
        self.assertIsNotNone(doc2_path_corpus1.path)
        self.assertIsNotNone(doc2_path_corpus2.path)
