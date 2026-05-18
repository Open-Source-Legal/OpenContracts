from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.tools.core_tools import amove_document, move_document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestMoveDocument(TestCase):
    """Tests for the move_document agent tool (intra-corpus folder move)."""

    def setUp(self):
        self.user = User.objects.create_user(username="mover", password="pw")
        self.other_user = User.objects.create_user(username="other", password="pw")

        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Create folders
        self.folder_a = CorpusFolder.objects.create(
            name="Folder A", corpus=self.corpus, creator=self.user
        )
        self.folder_b = CorpusFolder.objects.create(
            name="Folder B", corpus=self.corpus, creator=self.user
        )

        # Create a document and add it to the corpus (in folder_a)
        self.original_doc = Document.objects.create(
            title="Test Doc",
            description="A test document",
            creator=self.user,
        )
        self.original_doc.txt_extract_file.save(
            "test.txt", ContentFile(b"Test content")
        )

        self.doc, *_ = self.corpus.add_document(
            document=self.original_doc,
            user=self.user,
            folder=self.folder_a,
        )
        # NOTE: Document-level permission grant is not what's being tested here.
        # move_document delegates to CorpusObjsService.move_document_to_folder,
        # which checks corpus-level write permission.  self.user passes that check
        # because they are the corpus creator.  We still grant document CRUD for
        # completeness, but the move succeeds due to corpus ownership.
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])

    def test_move_to_folder(self):
        """Moving a document to another folder updates its path."""
        result = move_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            author_id=self.user.id,
            target_folder_id=self.folder_b.id,
        )

        self.assertEqual(result["status"], "moved")
        self.assertEqual(result["document_id"], self.doc.id)
        self.assertEqual(result["target_folder_id"], self.folder_b.id)

        # Verify the path was updated
        path = DocumentPath.objects.get(
            document=self.doc,
            corpus=self.corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(path.folder_id, self.folder_b.id)

    def test_move_to_root(self):
        """Moving a document with target_folder_id=None goes to corpus root."""
        result = move_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            author_id=self.user.id,
            target_folder_id=None,
        )

        self.assertEqual(result["status"], "moved")
        self.assertIsNone(result["target_folder_id"])

        path = DocumentPath.objects.get(
            document=self.doc,
            corpus=self.corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertIsNone(path.folder_id)

    def test_move_nonexistent_document_raises(self):
        """Moving a nonexistent document raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            move_document(
                document_id=999999,
                corpus_id=self.corpus.id,
                author_id=self.user.id,
                target_folder_id=self.folder_b.id,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_move_nonexistent_folder_raises(self):
        """Moving to a nonexistent folder raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            move_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                author_id=self.user.id,
                target_folder_id=999999,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_move_inaccessible_folder_raises(self):
        """Moving to a folder the user cannot see raises the same error as not-found.

        IDOR prevention: a folder in another user's private corpus produces
        the same "does not exist or is not accessible" message as a truly
        nonexistent folder, preventing enumeration of folder IDs.
        """
        private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.other_user
        )
        hidden_folder = CorpusFolder.objects.create(
            name="Hidden Folder", corpus=private_corpus, creator=self.other_user
        )

        with self.assertRaises(ValueError) as ctx:
            move_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                author_id=self.user.id,
                target_folder_id=hidden_folder.id,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_move_folder_wrong_corpus_raises(self):
        """Moving to a folder in a different corpus raises ValueError."""
        other_corpus = Corpus.objects.create(title="Other Corpus", creator=self.user)
        wrong_folder = CorpusFolder.objects.create(
            name="Wrong Folder", corpus=other_corpus, creator=self.user
        )

        with self.assertRaises(ValueError) as ctx:
            move_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                author_id=self.user.id,
                target_folder_id=wrong_folder.id,
            )
        # Early cross-corpus check rejects with the same generic message
        # used for non-existent/inaccessible folders (IDOR prevention).
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_move_to_corpus_where_doc_not_member_raises(self):
        """Moving a document into a corpus it doesn't belong to fails.

        private_corpus is owned by other_user, so self.user cannot see it
        via visible_to_user(). The tool rejects the request at the corpus
        lookup stage with a generic "does not exist or is not accessible"
        message (IDOR prevention — same error whether the corpus truly
        doesn't exist or is simply not visible to the caller).
        """
        private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.other_user
        )

        with self.assertRaises(ValueError) as ctx:
            move_document(
                document_id=self.doc.id,
                corpus_id=private_corpus.id,
                author_id=self.user.id,
                target_folder_id=None,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_move_document_not_in_corpus_raises(self):
        """Moving a document that isn't in the corpus raises ValueError."""
        other_corpus = Corpus.objects.create(title="Other Corpus", creator=self.user)

        with self.assertRaises(ValueError) as ctx:
            move_document(
                document_id=self.doc.id,
                corpus_id=other_corpus.id,
                author_id=self.user.id,
                target_folder_id=None,
            )
        self.assertIn("Move failed", str(ctx.exception))

    def test_invalid_author_id_raises(self):
        """Passing a nonexistent user ID raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            move_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                author_id=999999,
                target_folder_id=None,
            )
        self.assertIn("does not exist", str(ctx.exception))

    def test_move_no_write_permission_raises(self):
        """A user with read-only corpus access cannot move documents.

        Grants other_user READ permission on both the corpus and the document
        so visibility checks pass, but does NOT grant corpus write permission.
        CorpusObjsService.move_document_to_folder rejects the move because
        other_user is not the corpus creator, not a superuser, and has no
        explicit UPDATE/CRUD permission on the corpus.
        """
        # Grant read-only access so visible_to_user() includes these objects
        set_permissions_for_obj_to_user(
            self.other_user, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.doc, [PermissionTypes.READ]
        )

        with self.assertRaises(ValueError) as ctx:
            move_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                author_id=self.other_user.id,
                target_folder_id=self.folder_b.id,
            )
        self.assertIn("Move failed", str(ctx.exception))
        self.assertIn("Permission denied", str(ctx.exception))


class TestMoveDocumentAsync(TransactionTestCase):
    """Async smoke test for amove_document.

    Uses TransactionTestCase because async_to_sync runs the coroutine in a
    separate thread that cannot see uncommitted data from TestCase's
    in-transaction wrapper.
    """

    def setUp(self):
        # Disconnect the document processing signal for the entire setUp.
        # TransactionTestCase commits data, so on_commit callbacks fire
        # synchronously — the celery tasks fail because there's no real
        # PDF/media to process.  We reconnect in finally.
        from django.db.models.signals import post_save

        from opencontractserver.documents.signals import (
            DOC_CREATE_UID,
            process_doc_on_create_atomic,
        )

        try:
            post_save.disconnect(
                process_doc_on_create_atomic,
                sender=Document,
                dispatch_uid=DOC_CREATE_UID,
            )
            self.user = User.objects.create_user(username="async_mover", password="pw")
            self.corpus = Corpus.objects.create(title="Async Corpus", creator=self.user)
            self.folder_a = CorpusFolder.objects.create(
                name="Folder A", corpus=self.corpus, creator=self.user
            )
            self.folder_b = CorpusFolder.objects.create(
                name="Folder B", corpus=self.corpus, creator=self.user
            )

            original_doc = Document.objects.create(
                title="Async Doc", description="async test", creator=self.user
            )
            original_doc.txt_extract_file.save("test.txt", ContentFile(b"content"))

            self.doc, *_ = self.corpus.add_document(
                document=original_doc, user=self.user, folder=self.folder_a
            )
            set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])
        finally:
            post_save.connect(
                process_doc_on_create_atomic,
                sender=Document,
                dispatch_uid=DOC_CREATE_UID,
            )

    def test_amove_document_async_wrapper(self):
        """Smoke test: amove_document (async) produces the same result as the sync version."""
        result = async_to_sync(amove_document)(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            author_id=self.user.id,
            target_folder_id=self.folder_b.id,
        )

        self.assertEqual(result["status"], "moved")
        self.assertEqual(result["document_id"], self.doc.id)
        self.assertEqual(result["target_folder_id"], self.folder_b.id)
