"""
Tests for orphaned document migration command.

This test file covers the migrate_orphaned_documents management command which:
1. Finds documents with no active DocumentPath records (orphans)
2. Creates "My Documents" corpuses for users with edit access
3. Creates "Shared With Me" corpuses for users with read-only access
4. Links orphaned documents to appropriate corpuses via DocumentPath
5. Cleans up non-default embeddings
"""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from guardian.shortcuts import assign_perm

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentUserObjectPermission,
)

User = get_user_model()


class TestFindOrphanedDocuments(TestCase):
    """Test finding orphaned documents."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create a document with a corpus (not orphaned)
        self.corpus = Corpus.objects.create(
            title="Test Corpus", description="Test corpus", creator=self.user
        )

        self.doc_with_corpus = Document.objects.create(
            title="Document With Corpus",
            description="Has a corpus",
            creator=self.user,
        )
        self.doc_with_corpus.pdf_file.save(
            "test.pdf", ContentFile(b"Test PDF content")
        )

        # Create DocumentPath for doc_with_corpus
        DocumentPath.objects.create(
            document=self.doc_with_corpus,
            corpus=self.corpus,
            path="/test/document.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Create orphaned document (no DocumentPath)
        self.orphan_doc = Document.objects.create(
            title="Orphaned Document",
            description="No corpus",
            creator=self.user,
        )
        self.orphan_doc.pdf_file.save("orphan.pdf", ContentFile(b"Orphan PDF content"))

    def test_find_orphaned_documents(self):
        """Test that orphaned documents are correctly identified."""
        # Import the command to use its internal method
        from opencontractserver.documents.management.commands.migrate_orphaned_documents import (
            Command,
        )

        cmd = Command()
        orphans = cmd._find_orphaned_documents()

        self.assertEqual(orphans.count(), 1)
        self.assertEqual(orphans.first(), self.orphan_doc)

    def test_document_with_deleted_path_is_orphan(self):
        """Test that document with only deleted paths is considered orphan."""
        # Create another document
        doc_deleted_path = Document.objects.create(
            title="Document With Deleted Path",
            description="Path was deleted",
            creator=self.user,
        )

        # Create a deleted DocumentPath
        DocumentPath.objects.create(
            document=doc_deleted_path,
            corpus=self.corpus,
            path="/deleted/document.pdf",
            version_number=1,
            is_current=True,
            is_deleted=True,  # Deleted!
            creator=self.user,
        )

        from opencontractserver.documents.management.commands.migrate_orphaned_documents import (
            Command,
        )

        cmd = Command()
        orphans = cmd._find_orphaned_documents()

        # Should find both orphans
        self.assertEqual(orphans.count(), 2)
        orphan_ids = set(orphans.values_list("id", flat=True))
        self.assertIn(self.orphan_doc.id, orphan_ids)
        self.assertIn(doc_deleted_path.id, orphan_ids)


class TestOrphanMigrationCreatesMyDocuments(TransactionTestCase):
    """Test migration creates 'My Documents' corpus for document creators."""

    def setUp(self):
        """Set up test data with orphaned document."""
        self.user_a = User.objects.create_user(
            username="user_a", email="usera@example.com", password="testpass123"
        )

        # Create orphaned document owned by user_a
        self.orphan_doc = Document.objects.create(
            title="Orphan Owned by A",
            description="No corpus",
            creator=self.user_a,
        )
        self.orphan_doc.pdf_file.save("orphan.pdf", ContentFile(b"Orphan PDF content"))

    def test_migration_creates_my_documents_corpus(self):
        """Test that migration creates 'My Documents' corpus for creator."""
        out = StringIO()
        call_command("migrate_orphaned_documents", stdout=out)

        # Verify 'My Documents' corpus was created
        my_docs = Corpus.objects.filter(
            creator=self.user_a, title="My Documents", is_system_corpus=True
        )
        self.assertEqual(my_docs.count(), 1)

        corpus = my_docs.first()
        self.assertTrue(corpus.is_system_corpus)
        self.assertFalse(corpus.is_public)

    def test_migration_creates_document_path(self):
        """Test that migration creates DocumentPath linking doc to corpus."""
        call_command("migrate_orphaned_documents")

        # Find the created corpus
        my_docs = Corpus.objects.get(
            creator=self.user_a, title="My Documents", is_system_corpus=True
        )

        # Verify DocumentPath was created
        path = DocumentPath.objects.filter(
            document=self.orphan_doc, corpus=my_docs, is_current=True, is_deleted=False
        )
        self.assertEqual(path.count(), 1)

    def test_migration_dry_run_makes_no_changes(self):
        """Test that dry-run mode doesn't create anything."""
        out = StringIO()
        call_command("migrate_orphaned_documents", "--dry-run", stdout=out)

        # Verify no corpus was created
        my_docs = Corpus.objects.filter(
            creator=self.user_a, title="My Documents", is_system_corpus=True
        )
        self.assertEqual(my_docs.count(), 0)

        # Verify no DocumentPath was created
        paths = DocumentPath.objects.filter(document=self.orphan_doc)
        self.assertEqual(paths.count(), 0)

        # Check output mentions dry run
        output = out.getvalue()
        self.assertIn("DRY-RUN", output)

    def test_migration_idempotent(self):
        """Test that running migration twice doesn't create duplicates."""
        call_command("migrate_orphaned_documents")
        call_command("migrate_orphaned_documents")

        # Should still have only one corpus
        my_docs = Corpus.objects.filter(
            creator=self.user_a, title="My Documents", is_system_corpus=True
        )
        self.assertEqual(my_docs.count(), 1)

        # Should still have only one path
        corpus = my_docs.first()
        paths = DocumentPath.objects.filter(
            document=self.orphan_doc, corpus=corpus, is_current=True, is_deleted=False
        )
        self.assertEqual(paths.count(), 1)


class TestOrphanMigrationWithSharedDocuments(TransactionTestCase):
    """Test migration handles shared documents correctly."""

    def setUp(self):
        """Set up test data with shared orphaned documents."""
        self.user_a = User.objects.create_user(
            username="user_a", email="usera@example.com", password="testpass123"
        )
        self.user_b = User.objects.create_user(
            username="user_b", email="userb@example.com", password="testpass123"
        )
        self.user_c = User.objects.create_user(
            username="user_c", email="userc@example.com", password="testpass123"
        )

        # Create orphaned document owned by user_a, shared read-only with user_b
        self.orphan_shared_readonly = Document.objects.create(
            title="Orphan Shared Read-Only",
            description="Shared with B read-only",
            creator=self.user_a,
        )
        self.orphan_shared_readonly.pdf_file.save(
            "shared_ro.pdf", ContentFile(b"Shared RO content")
        )
        assign_perm("view_document", self.user_b, self.orphan_shared_readonly)

        # Create orphaned document owned by user_a, shared with edit to user_c
        self.orphan_shared_edit = Document.objects.create(
            title="Orphan Shared Edit",
            description="Shared with C for edit",
            creator=self.user_a,
        )
        self.orphan_shared_edit.pdf_file.save(
            "shared_edit.pdf", ContentFile(b"Shared Edit content")
        )
        assign_perm("change_document", self.user_c, self.orphan_shared_edit)

    def test_migration_creates_shared_with_me_for_readonly(self):
        """Test that read-only shared docs go to 'Shared With Me' corpus."""
        call_command("migrate_orphaned_documents")

        # User B should have 'Shared With Me' corpus
        shared_corpus = Corpus.objects.filter(
            creator=self.user_b, title="Shared With Me", is_system_corpus=True
        )
        self.assertEqual(shared_corpus.count(), 1)

        corpus = shared_corpus.first()
        self.assertTrue(corpus.is_system_corpus)

        # Document should be linked to it
        path = DocumentPath.objects.filter(
            document=self.orphan_shared_readonly,
            corpus=corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(path.count(), 1)

    def test_migration_creates_my_documents_for_edit_shared(self):
        """Test that edit-shared docs go to 'My Documents' corpus."""
        call_command("migrate_orphaned_documents")

        # User C should have 'My Documents' corpus (has edit rights)
        my_docs = Corpus.objects.filter(
            creator=self.user_c, title="My Documents", is_system_corpus=True
        )
        self.assertEqual(my_docs.count(), 1)

        corpus = my_docs.first()

        # Document should be linked to it
        path = DocumentPath.objects.filter(
            document=self.orphan_shared_edit,
            corpus=corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(path.count(), 1)

    def test_creator_also_gets_document(self):
        """Test that creator also gets the document in their 'My Documents'."""
        call_command("migrate_orphaned_documents")

        # User A (creator) should have both docs in 'My Documents'
        my_docs = Corpus.objects.get(
            creator=self.user_a, title="My Documents", is_system_corpus=True
        )

        paths = DocumentPath.objects.filter(
            corpus=my_docs, is_current=True, is_deleted=False
        )
        doc_ids = set(paths.values_list("document_id", flat=True))

        self.assertIn(self.orphan_shared_readonly.id, doc_ids)
        self.assertIn(self.orphan_shared_edit.id, doc_ids)

    def test_user_with_both_permissions_gets_my_documents_only(self):
        """Test that user with both view and change gets 'My Documents' only."""
        # Give user_b both view and change permissions
        assign_perm("change_document", self.user_b, self.orphan_shared_readonly)

        call_command("migrate_orphaned_documents")

        # User B should have 'My Documents' (edit trumps read-only)
        my_docs = Corpus.objects.filter(
            creator=self.user_b, title="My Documents", is_system_corpus=True
        )
        self.assertEqual(my_docs.count(), 1)

        # User B should NOT have 'Shared With Me' for this document
        # (they have edit access, so it goes to My Documents)
        my_docs_corpus = my_docs.first()
        path_in_my_docs = DocumentPath.objects.filter(
            document=self.orphan_shared_readonly,
            corpus=my_docs_corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(path_in_my_docs.count(), 1)


class TestOrphanMigrationEmbeddingCleanup(TransactionTestCase):
    """Test migration cleans up non-default embeddings."""

    def setUp(self):
        """Set up test data with orphaned document and embeddings."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.orphan_doc = Document.objects.create(
            title="Orphan With Embeddings",
            description="Has embeddings",
            creator=self.user,
        )
        self.orphan_doc.pdf_file.save("orphan.pdf", ContentFile(b"Orphan PDF content"))

    @override_settings(
        DEFAULT_EMBEDDER="opencontractserver.pipeline.embedders.default.DefaultEmbedder"
    )
    def test_migration_deletes_non_default_embeddings(self):
        """Test that non-default embeddings are deleted."""
        from opencontractserver.annotations.models import Embedding

        # Create embeddings - one default, one non-default
        Embedding.objects.create(
            document=self.orphan_doc,
            embedder_path="opencontractserver.pipeline.embedders.default.DefaultEmbedder",
            vector_384=[0.1] * 384,
        )
        Embedding.objects.create(
            document=self.orphan_doc,
            embedder_path="some.other.Embedder",
            vector_384=[0.2] * 384,
        )

        self.assertEqual(Embedding.objects.filter(document=self.orphan_doc).count(), 2)

        call_command("migrate_orphaned_documents")

        # Only default embedding should remain
        embeddings = Embedding.objects.filter(document=self.orphan_doc)
        self.assertEqual(embeddings.count(), 1)
        self.assertEqual(
            embeddings.first().embedder_path,
            "opencontractserver.pipeline.embedders.default.DefaultEmbedder",
        )

    def test_migration_skip_embedding_cleanup_flag(self):
        """Test --skip-embedding-cleanup flag works."""
        from opencontractserver.annotations.models import Embedding

        # Create non-default embedding
        Embedding.objects.create(
            document=self.orphan_doc,
            embedder_path="some.other.Embedder",
            vector_384=[0.2] * 384,
        )

        call_command("migrate_orphaned_documents", "--skip-embedding-cleanup")

        # Embedding should still exist
        embeddings = Embedding.objects.filter(document=self.orphan_doc)
        self.assertEqual(embeddings.count(), 1)


class TestOrphanMigrationPathGeneration(TransactionTestCase):
    """Test DocumentPath generation during migration."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_path_generated_from_title(self):
        """Test that path is generated from document title."""
        doc = Document.objects.create(
            title="My Important Document",
            description="Test",
            creator=self.user,
        )
        doc.pdf_file.save("test.pdf", ContentFile(b"content"))

        call_command("migrate_orphaned_documents")

        corpus = Corpus.objects.get(
            creator=self.user, title="My Documents", is_system_corpus=True
        )
        path = DocumentPath.objects.get(
            document=doc, corpus=corpus, is_current=True, is_deleted=False
        )

        self.assertIn("My_Important_Document", path.path)
        self.assertTrue(path.path.startswith("/migrated/"))

    def test_path_uses_id_when_no_title(self):
        """Test that path uses document ID when title is empty."""
        doc = Document.objects.create(
            title="",
            description="No title",
            creator=self.user,
        )
        doc.pdf_file.save("test.pdf", ContentFile(b"content"))

        call_command("migrate_orphaned_documents")

        corpus = Corpus.objects.get(
            creator=self.user, title="My Documents", is_system_corpus=True
        )
        path = DocumentPath.objects.get(
            document=doc, corpus=corpus, is_current=True, is_deleted=False
        )

        self.assertIn(f"document_{doc.pk}", path.path)

    def test_path_conflict_resolution(self):
        """Test that conflicting paths are resolved with suffix."""
        # Create two documents with same title
        doc1 = Document.objects.create(
            title="Same Title",
            description="First",
            creator=self.user,
        )
        doc1.pdf_file.save("test1.pdf", ContentFile(b"content1"))

        doc2 = Document.objects.create(
            title="Same Title",
            description="Second",
            creator=self.user,
        )
        doc2.pdf_file.save("test2.pdf", ContentFile(b"content2"))

        call_command("migrate_orphaned_documents")

        corpus = Corpus.objects.get(
            creator=self.user, title="My Documents", is_system_corpus=True
        )
        paths = DocumentPath.objects.filter(
            corpus=corpus, is_current=True, is_deleted=False
        )

        # Both should have paths
        self.assertEqual(paths.count(), 2)

        # Paths should be different
        path_values = list(paths.values_list("path", flat=True))
        self.assertNotEqual(path_values[0], path_values[1])


class TestOrphanMigrationNoOrphans(TestCase):
    """Test migration behavior when there are no orphans."""

    def setUp(self):
        """Set up test data with no orphans."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create a document WITH a corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", description="Test", creator=self.user
        )

        self.doc = Document.objects.create(
            title="Non-Orphan Document",
            description="Has corpus",
            creator=self.user,
        )
        self.doc.pdf_file.save("test.pdf", ContentFile(b"content"))

        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

    def test_migration_with_no_orphans(self):
        """Test that migration handles no orphans gracefully."""
        out = StringIO()
        call_command("migrate_orphaned_documents", stdout=out)

        output = out.getvalue()
        self.assertIn("No orphaned documents found", output)

        # No system corpuses should be created
        system_corpuses = Corpus.objects.filter(is_system_corpus=True)
        self.assertEqual(system_corpuses.count(), 0)


class TestDocumentCorpusConstraints(TransactionTestCase):
    """Test the document-corpus constraints enforced by GraphQL mutations."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create a corpus with a document
        self.corpus = Corpus.objects.create(
            title="Test Corpus", description="Test", creator=self.user
        )

        self.doc = Document.objects.create(
            title="Test Document",
            description="Has corpus",
            creator=self.user,
        )
        self.doc.pdf_file.save("test.pdf", ContentFile(b"content"))

        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

    def test_cannot_delete_system_corpus(self):
        """Test that system corpuses cannot be deleted."""
        # Create a system corpus
        system_corpus = Corpus.objects.create(
            title="My Documents",
            description="System corpus",
            creator=self.user,
            is_system_corpus=True,
        )

        # Attempting to delete should raise PermissionError
        from config.graphql.mutations import DeleteCorpusMutation
        from graphql_relay import to_global_id
        from unittest.mock import MagicMock

        info = MagicMock()
        info.context.user = self.user

        with self.assertRaises(PermissionError) as context:
            DeleteCorpusMutation.mutate(
                None, info, id=to_global_id("CorpusType", system_corpus.pk)
            )

        self.assertIn("System corpuses cannot be deleted", str(context.exception))

    def test_cannot_delete_corpus_with_documents(self):
        """Test that corpuses with documents cannot be deleted."""
        from config.graphql.mutations import DeleteCorpusMutation
        from graphql_relay import to_global_id
        from unittest.mock import MagicMock
        from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
        from opencontractserver.types.enums import PermissionTypes

        # Give user delete permission
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        info = MagicMock()
        info.context.user = self.user

        with self.assertRaises(PermissionError) as context:
            DeleteCorpusMutation.mutate(
                None, info, id=to_global_id("CorpusType", self.corpus.pk)
            )

        self.assertIn("Cannot delete corpus containing documents", str(context.exception))


class TestRemoveFromLastCorpusConstraint(TransactionTestCase):
    """Test that documents cannot be removed from their last corpus."""

    def setUp(self):
        """Set up test data with document in only one corpus."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.corpus = Corpus.objects.create(
            title="Only Corpus", description="Test", creator=self.user
        )

        self.doc = Document.objects.create(
            title="Test Document",
            description="In only one corpus",
            creator=self.user,
        )
        self.doc.pdf_file.save("test.pdf", ContentFile(b"content"))

        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

    def test_cannot_remove_from_last_corpus(self):
        """Test that removing document from last corpus fails."""
        from config.graphql.mutations import RemoveDocumentsFromCorpus
        from graphql_relay import to_global_id
        from unittest.mock import MagicMock

        info = MagicMock()
        info.context.user = self.user

        result = RemoveDocumentsFromCorpus.mutate(
            None,
            info,
            corpus_id=to_global_id("CorpusType", self.corpus.pk),
            document_ids_to_remove=[to_global_id("DocumentType", self.doc.pk)],
        )

        self.assertFalse(result.ok)
        self.assertIn("Cannot remove document from its last corpus", result.message)

    def test_can_remove_from_corpus_if_in_multiple(self):
        """Test that document can be removed if it's in multiple corpuses."""
        from opencontractserver.corpuses.folder_service import DocumentFolderService
        from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
        from opencontractserver.types.enums import PermissionTypes

        # Create second corpus and add document
        corpus2 = Corpus.objects.create(
            title="Second Corpus", description="Test", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, corpus2, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        DocumentPath.objects.create(
            document=self.doc,
            corpus=corpus2,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        from config.graphql.mutations import RemoveDocumentsFromCorpus
        from graphql_relay import to_global_id
        from unittest.mock import MagicMock

        info = MagicMock()
        info.context.user = self.user

        # Should succeed since doc is in corpus2 as well
        result = RemoveDocumentsFromCorpus.mutate(
            None,
            info,
            corpus_id=to_global_id("CorpusType", self.corpus.pk),
            document_ids_to_remove=[to_global_id("DocumentType", self.doc.pk)],
        )

        self.assertTrue(result.ok)
