"""
Comprehensive tests for Issue #654: DocumentPath as single source of truth.

This test file covers:
1. New Corpus methods (add_document, remove_document, _get_active_documents, document_count)
2. DocumentPathType request-level caching

Note: Backward compatibility layer has been removed. All corpus-document
relationships must now use DocumentPath-based methods.
"""

from django.contrib.auth.models import AnonymousUser
from django.core.files.base import ContentFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.users.models import User


class TestCorpusDocumentMethods(TestCase):
    """Test the new explicit Corpus methods for document management."""

    def setUp(self):
        """Set up test data."""
        # Clean up any existing DocumentPath records from previous tests
        DocumentPath.objects.all().delete()

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus", description="Test corpus", creator=self.user
        )

        self.document = Document.objects.create(
            title="Test Document",
            description="A test document",
            creator=self.user,
            pdf_file_hash="testhash",
        )
        self.document.pdf_file.save("test.pdf", ContentFile(b"Test PDF content"))

    def test_add_document_creates_path(self):
        """Test that add_document creates DocumentPath record."""
        doc, status, path = self.corpus.add_document(
            document=self.document, user=self.user
        )

        # Status should be 'added' for new corpus-isolated copy
        self.assertEqual(status, "added")
        # Document is corpus-isolated copy (different ID)
        self.assertNotEqual(doc.id, self.document.id)
        # Content is the same (hash matches)
        self.assertEqual(doc.pdf_file_hash, self.document.pdf_file_hash)
        # Provenance tracked via source_document
        self.assertEqual(doc.source_document, self.document)
        self.assertIsInstance(path, DocumentPath)
        self.assertEqual(path.corpus, self.corpus)
        self.assertEqual(path.document, doc)  # Points to isolated copy
        self.assertTrue(path.is_current)
        self.assertFalse(path.is_deleted)

    def test_add_document_with_custom_path(self):
        """Test add_document with custom path."""
        doc, status, path = self.corpus.add_document(
            document=self.document, path="/custom/path/document.pdf", user=self.user
        )

        self.assertEqual(path.path, "/custom/path/document.pdf")

    def test_add_document_auto_generates_path(self):
        """Test that add_document auto-generates path from title."""
        doc, status, path = self.corpus.add_document(
            document=self.document, user=self.user
        )

        self.assertIn("Test_Document", path.path)

    def test_add_document_requires_user(self):
        """Test that add_document requires user for audit trail."""
        with self.assertRaises(ValueError) as cm:
            self.corpus.add_document(document=self.document, user=None)

        self.assertIn("User is required", str(cm.exception))

    def test_remove_document_by_document(self):
        """Test removing document by document object."""
        # First add the document
        doc, status, path = self.corpus.add_document(
            document=self.document, user=self.user
        )

        # Verify it was added
        self.assertIsNotNone(path)
        active_paths = DocumentPath.objects.filter(
            corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertGreater(
            active_paths.count(), 0, "No active paths found after add_document"
        )

        # Then remove it - use the actual document that was added (might be versioned)
        deleted_paths = self.corpus.remove_document(document=doc, user=self.user)

        self.assertGreater(len(deleted_paths), 0, "No paths were deleted")
        self.assertTrue(deleted_paths[0].is_deleted)

        # Document should no longer be in corpus
        self.assertEqual(self.corpus._get_active_documents().count(), 0)

    def test_remove_document_by_path(self):
        """Test removing document by path."""
        # Add document with known path
        doc, status, path_record = self.corpus.add_document(
            document=self.document, path="/test/document.pdf", user=self.user
        )

        # Remove by path
        deleted_paths = self.corpus.remove_document(
            path="/test/document.pdf", user=self.user
        )

        self.assertEqual(len(deleted_paths), 1)
        self.assertTrue(deleted_paths[0].is_deleted)

    def test_remove_document_requires_user(self):
        """Test that remove_document requires user."""
        with self.assertRaises(ValueError) as cm:
            self.corpus.remove_document(document=self.document, user=None)

        self.assertIn("User is required", str(cm.exception))

    def test_remove_document_requires_document_or_path(self):
        """Test that remove_document requires either document or path."""
        with self.assertRaises(ValueError) as cm:
            self.corpus.remove_document(user=self.user)

        self.assertIn("Either document or path must be provided", str(cm.exception))

    def test_active_documents_returns_active_documents(self):
        """Test that _get_active_documents returns only active documents."""
        # Add two documents
        doc2 = Document.objects.create(
            title="Document 2", creator=self.user, pdf_file_hash="hash2"
        )
        doc2.pdf_file.save("doc2.pdf", ContentFile(b"Content 2"))

        doc1_added, _, _ = self.corpus.add_document(
            document=self.document, user=self.user
        )
        doc2_added, _, _ = self.corpus.add_document(document=doc2, user=self.user)

        # Should have 2 documents (or more if there are leftovers)
        docs_before = self.corpus._get_active_documents()
        initial_count = docs_before.count()
        self.assertGreaterEqual(initial_count, 2)

        # Remove one - use the actual document returned from add_document
        removed = self.corpus.remove_document(document=doc1_added, user=self.user)
        self.assertGreater(len(removed), 0, "Should have removed at least one path")

        # Should have one less document
        docs_after = self.corpus._get_active_documents()
        self.assertEqual(docs_after.count(), initial_count - 1)

    def test_document_count(self):
        """Test document_count method.

        Re-adding the same source document without an explicit path
        auto-generates the same ``/documents/<title>`` path on each call.
        Per the H1 disambiguation fix, ``add_document`` is NOT a versioning
        entry point: a colliding path is disambiguated
        (``Test_Document`` -> ``Test_Document_1``) and BOTH documents stay
        active, so the count increases on every add.
        """
        # Initial count should be 0 (we clean up in setUp)
        initial_count = self.corpus.document_count()

        # Add document - creates corpus-isolated copy
        corpus_doc, status, path = self.corpus.add_document(
            document=self.document, user=self.user
        )
        self.assertEqual(status, "added")
        self.assertEqual(self.corpus.document_count(), initial_count + 1)

        # Add same source document again without explicit path - both adds
        # auto-generate /documents/Test_Document, so the second is
        # disambiguated to a distinct path instead of superseding the first.
        # Both remain active and the count increases.
        corpus_doc2, status2, path2 = self.corpus.add_document(
            document=self.document, user=self.user
        )
        self.assertEqual(status2, "added")
        self.assertNotEqual(path.path, path2.path)
        self.assertEqual(self.corpus.document_count(), initial_count + 2)

        # Removing the second (disambiguated) document leaves the first active
        self.corpus.remove_document(document=corpus_doc2, user=self.user)
        self.assertEqual(self.corpus.document_count(), initial_count + 1)

        # Removing the first as well returns to the initial count
        self.corpus.remove_document(document=corpus_doc, user=self.user)
        self.assertEqual(self.corpus.document_count(), initial_count)

    def test_add_document_with_folder(self):
        """Test adding document to a specific folder."""
        from opencontractserver.corpuses.models import CorpusFolder

        folder = CorpusFolder.objects.create(
            name="Test Folder", corpus=self.corpus, creator=self.user
        )

        doc, status, path = self.corpus.add_document(
            document=self.document, user=self.user, folder=folder
        )

        self.assertEqual(path.folder, folder)

    def test_active_documents_excludes_deleted(self):
        """Test that _get_active_documents excludes soft-deleted documents."""
        # Add document
        doc, status, path = self.corpus.add_document(
            document=self.document, user=self.user
        )

        # Should be visible
        self.assertIn(doc, self.corpus._get_active_documents())

        # Soft-delete via remove_document
        self.corpus.remove_document(document=doc, user=self.user)

        # Should not be visible
        self.assertNotIn(doc, self.corpus._get_active_documents())

        # But DocumentPath should still exist (soft-deleted)
        deleted_path = DocumentPath.objects.filter(
            corpus=self.corpus, document=doc, is_deleted=True
        )
        self.assertTrue(deleted_path.exists())

    def test_active_documents_filtering(self):
        """Test that _get_active_documents returns a filterable queryset."""
        # Add multiple documents
        doc2 = Document.objects.create(
            title="Another Document", creator=self.user, pdf_file_hash="hash2"
        )
        doc2.pdf_file.save("doc2.pdf", ContentFile(b"Content 2"))

        self.corpus.add_document(document=self.document, user=self.user)
        self.corpus.add_document(document=doc2, user=self.user)

        # Filter by title
        filtered = self.corpus._get_active_documents().filter(title="Test Document")
        self.assertEqual(filtered.count(), 1)

        # Exclude by title
        excluded = self.corpus._get_active_documents().exclude(title="Test Document")
        self.assertEqual(excluded.count(), 1)

    def test_corpus_isolation_with_provenance(self):
        """Test that add_document creates corpus-isolated copy with provenance tracking."""
        original_id = self.document.id
        original_title = self.document.title
        original_hash = self.document.pdf_file_hash

        returned_doc, status, path = self.corpus.add_document(
            document=self.document, user=self.user
        )

        # Should be a NEW corpus-isolated copy
        self.assertNotEqual(returned_doc.id, original_id)
        self.assertIsNot(returned_doc, self.document)  # Different object
        # But same content
        self.assertEqual(returned_doc.title, original_title)
        self.assertEqual(returned_doc.pdf_file_hash, original_hash)
        # Provenance tracked
        self.assertEqual(returned_doc.source_document, self.document)
        self.assertEqual(returned_doc.source_document_id, original_id)
        # Independent version tree
        self.assertNotEqual(returned_doc.version_tree_id, self.document.version_tree_id)

    def test_same_document_multiple_paths(self):
        """Test that same content can exist at multiple paths in same corpus."""
        # Add at first path - creates corpus-isolated copy
        doc1, status1, path1 = self.corpus.add_document(
            document=self.document, path="/path/one.pdf", user=self.user
        )
        self.assertEqual(status1, "added")
        self.assertNotEqual(doc1.id, self.document.id)  # Corpus-isolated copy

        # Add at second path - no content-based dedup, creates another copy
        doc2, status2, path2 = self.corpus.add_document(
            document=self.document, path="/path/two.pdf", user=self.user
        )
        self.assertEqual(status2, "added")

        # Each add creates a separate corpus-isolated document
        self.assertNotEqual(doc1.id, doc2.id)
        self.assertNotEqual(doc1.id, self.document.id)  # Not the original
        self.assertNotEqual(doc2.id, self.document.id)  # Not the original

        # Different path records
        self.assertNotEqual(path1.id, path2.id)
        self.assertEqual(path1.path, "/path/one.pdf")
        self.assertEqual(path2.path, "/path/two.pdf")

        # Both documents appear in get_documents()
        docs = list(self.corpus._get_active_documents())
        self.assertEqual(len(docs), 2)
        doc_ids = {d.id for d in docs}
        self.assertEqual(doc_ids, {doc1.id, doc2.id})

    def test_add_document_at_same_path_disambiguates(self):
        """Adding at an already-occupied explicit path disambiguates.

        Per the H1 fix, ``add_document`` is not a versioning entry point. A
        second add at the same path does NOT supersede the first or create a
        new version of it — it disambiguates to a sibling path and both
        documents stay active as independent root content trees.
        (``import_content`` remains the path-versioning surface.)
        """
        # First add - creates corpus-isolated copy
        doc1, status1, path1 = self.corpus.add_document(
            document=self.document, path="/same/path.pdf", user=self.user
        )
        self.assertEqual(status1, "added")
        self.assertNotEqual(doc1.id, self.document.id)  # Isolated copy
        self.assertEqual(path1.version_number, 1)

        # Second add at same path - disambiguated, not versioned
        doc2, status2, path2 = self.corpus.add_document(
            document=self.document, path="/same/path.pdf", user=self.user
        )
        self.assertEqual(status2, "added")

        # Different corpus-isolated documents
        self.assertNotEqual(doc1.id, doc2.id)

        # Second path is a disambiguated independent root (not a version)
        self.assertNotEqual(path1.id, path2.id)
        self.assertEqual(path1.path, "/same/path.pdf")
        self.assertEqual(path2.path, "/same/path_1.pdf")
        self.assertEqual(path2.version_number, 1)
        self.assertIsNone(path2.parent_id)

        # Both paths remain current/active — the first is NOT superseded
        path1.refresh_from_db()
        self.assertTrue(path1.is_current)
        self.assertTrue(path2.is_current)

    def test_add_document_at_occupied_path_disambiguates(self):
        """Adding a different document at an occupied path disambiguates.

        Per the H1 fix, the occupant is NOT replaced/superseded; the new
        document is placed at a disambiguated sibling path and both remain
        active.
        """
        doc2 = Document.objects.create(
            title="Another Document", creator=self.user, pdf_file_hash="hash2"
        )
        doc2.pdf_file.save("doc2.pdf", ContentFile(b"Content 2"))

        # Add first document at path - creates corpus-isolated copy
        doc1_ret, status1, path1 = self.corpus.add_document(
            document=self.document, path="/shared/path.pdf", user=self.user
        )
        self.assertEqual(status1, "added")
        self.assertEqual(path1.version_number, 1)
        self.assertNotEqual(doc1_ret.id, self.document.id)  # Isolated copy

        # Add second document at same path - disambiguated to a sibling
        doc2_ret, status2, path2 = self.corpus.add_document(
            document=doc2, path="/shared/path.pdf", user=self.user
        )
        self.assertEqual(status2, "added")
        self.assertEqual(path2.version_number, 1)
        self.assertIsNone(path2.parent_id)
        self.assertEqual(path1.path, "/shared/path.pdf")
        self.assertEqual(path2.path, "/shared/path_1.pdf")
        self.assertNotEqual(doc2_ret.id, doc2.id)  # Isolated copy

        # Both paths remain current — the occupant is NOT superseded
        path1.refresh_from_db()
        self.assertTrue(path1.is_current)
        self.assertTrue(path2.is_current)

        # get_documents should return BOTH disambiguated documents
        docs = list(self.corpus._get_active_documents())
        self.assertEqual(len(docs), 2)
        self.assertEqual({d.id for d in docs}, {doc1_ret.id, doc2_ret.id})

    def test_import_content_creates_new_document(self):
        """Test import_content creates new document."""
        content = b"Brand new PDF content"

        doc, status, path = self.corpus.import_content(
            content=content, path="/imported/doc.pdf", user=self.user, title="Imported"
        )

        self.assertEqual(status, "created")
        self.assertIsNotNone(doc.id)
        self.assertEqual(doc.title, "Imported")
        self.assertEqual(path.path, "/imported/doc.pdf")

    def test_import_content_corpus_isolation(self):
        """Test import_content creates independent documents (no content-based dedup)."""
        content = b"Same content for deduplication test"

        # Import to first corpus
        doc1, status1, path1 = self.corpus.import_content(
            content=content, path="/first.pdf", user=self.user, title="First"
        )
        self.assertEqual(status1, "created")
        self.assertIsNone(doc1.source_document)

        # Create second corpus
        corpus2 = Corpus.objects.create(title="Second Corpus", creator=self.user)

        # Import same content to second corpus - no dedup, creates independent doc
        doc2, status2, path2 = corpus2.import_content(
            content=content, path="/second.pdf", user=self.user, title="Second"
        )

        # No content-based deduplication - each import is independent
        self.assertEqual(status2, "created")
        self.assertNotEqual(doc1.id, doc2.id)  # Different documents
        self.assertIsNone(doc2.source_document)  # No provenance for uploads
        self.assertEqual(doc1.pdf_file_hash, doc2.pdf_file_hash)  # Same content hash
        self.assertNotEqual(
            doc1.version_tree_id, doc2.version_tree_id
        )  # Independent version trees

    def test_add_document_requires_document_object(self):
        """Test that add_document requires a document object."""
        with self.assertRaises(ValueError) as cm:
            self.corpus.add_document(document=None, user=self.user)

        self.assertIn("Document is required", str(cm.exception))

    def test_import_content_requires_content(self):
        """Test that import_content requires content bytes."""
        with self.assertRaises(ValueError) as cm:
            self.corpus.import_content(content=None, user=self.user)

        self.assertIn("Content is required", str(cm.exception))


class TestDocumentPathTypeCaching(TestCase):
    """Test request-level caching in DocumentPathType._get_visible_corpus_ids."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cacheuser", email="cache@example.com", password="testpass123"
        )

    def _make_info(self, user):
        """Create a mock GraphQL info object with a context that supports attr caching."""

        # One class plays both roles in the GraphQL ``info.context.user`` chain:
        # the outer ``info`` (whose ``.context`` is read) and the inner context
        # object (whose ``.user`` is read). Hence both attributes are declared
        # even though any given instance only populates one.
        class MockContext:
            user: User
            context: "MockContext"

        ctx = MockContext()
        ctx.user = user
        info = MockContext()
        info.context = ctx
        return info

    def test_cache_returns_same_result_on_repeated_calls(self):
        """Verify that repeated calls return cached result without re-querying."""
        from config.graphql.graphene_types import DocumentPathType

        info = self._make_info(self.user)

        result1 = DocumentPathType._get_visible_corpus_ids(info)
        result2 = DocumentPathType._get_visible_corpus_ids(info)

        self.assertEqual(result1, result2)
        self.assertIs(result1, result2)  # Same object reference = cache hit

    def test_cache_executes_query_only_once(self):
        """Verify the visibility query is only executed once per request context."""
        from config.graphql.graphene_types import DocumentPathType

        info = self._make_info(self.user)

        # First call should execute at least one query
        with CaptureQueriesContext(connection) as first_call:
            DocumentPathType._get_visible_corpus_ids(info)
        self.assertGreater(len(first_call), 0)

        # Subsequent calls should execute zero queries (cached)
        with CaptureQueriesContext(connection) as cached_calls:
            DocumentPathType._get_visible_corpus_ids(info)
            DocumentPathType._get_visible_corpus_ids(info)
        self.assertEqual(len(cached_calls), 0)

    def test_cache_scoped_per_user(self):
        """Verify different users get separate cache entries."""
        from config.graphql.graphene_types import DocumentPathType

        user2 = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass123"
        )

        # Shared context simulates two users in same request (e.g., impersonation)
        info = self._make_info(self.user)
        result1 = DocumentPathType._get_visible_corpus_ids(info)

        info2 = self._make_info(user2)
        result2 = DocumentPathType._get_visible_corpus_ids(info2)

        # Different contexts, different cache entries
        self.assertIsNot(result1, result2)

    def test_cache_handles_anonymous_user(self):
        """Verify anonymous users don't cause cache key collisions."""
        from config.graphql.graphene_types import DocumentPathType

        anon = AnonymousUser()
        info = self._make_info(anon)

        result = DocumentPathType._get_visible_corpus_ids(info)
        self.assertIsInstance(result, set)
