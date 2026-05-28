"""Tests for the create_or_update_text_document agent tool.

The tool is intentionally scoped to text-based formats (text/plain,
text/markdown, application/txt) and exercises the dual-tree versioning
architecture: first call at a given title creates a fresh document,
subsequent calls with the same title version-up the existing document.
"""

from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.tools.core_tools import (
    acreate_or_update_text_document,
    aupload_text_document,
    create_or_update_text_document,
    upload_text_document,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestCreateOrUpdateTextDocument(TestCase):
    """Sync tests for create_or_update_text_document.

    Document processing signals are disabled session-wide by the
    ``disable_document_processing_signals`` autouse fixture in
    ``conftest.py``, so this class doesn't need its own disconnect.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="author", password="pw")
        self.other_user = User.objects.create_user(username="other", password="pw")

        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.folder = CorpusFolder.objects.create(
            name="My Folder", corpus=self.corpus, creator=self.user
        )

    def test_create_new_document_at_corpus_root(self):
        """First call with a new title creates a fresh document at corpus root."""
        result = create_or_update_text_document(
            corpus_id=self.corpus.id,
            title="My Notes",
            content="Hello world",
            author_id=self.user.id,
        )

        self.assertEqual(result["status"], "created")
        self.assertEqual(result["corpus_id"], self.corpus.id)
        self.assertEqual(result["version_number"], 1)
        self.assertEqual(result["file_type"], "text/plain")
        self.assertEqual(result["byte_count"], len(b"Hello world"))
        self.assertIn("/documents/My_Notes", result["path"])

        doc = Document.objects.get(pk=result["document_id"])
        self.assertEqual(doc.title, "My Notes")
        self.assertEqual(doc.file_type, "text/plain")
        self.assertEqual(doc.creator_id, self.user.id)
        self.assertEqual(doc.txt_extract_file.read(), b"Hello world")

        # DocumentPath created at corpus root (no folder)
        path = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertIsNone(path.folder_id)
        self.assertEqual(path.version_number, 1)

    def test_create_new_document_in_folder(self):
        """When folder_id is provided the document lives in that folder."""
        result = create_or_update_text_document(
            corpus_id=self.corpus.id,
            title="Folder Doc",
            content="Inside folder",
            author_id=self.user.id,
            folder_id=self.folder.id,
        )

        self.assertEqual(result["status"], "created")
        path = DocumentPath.objects.get(
            document_id=result["document_id"],
            corpus=self.corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(path.folder_id, self.folder.id)

    def test_second_call_same_title_version_ups(self):
        """A second call with the same title creates a new version (v2)."""
        first = create_or_update_text_document(
            corpus_id=self.corpus.id,
            title="Versioned",
            content="version one",
            author_id=self.user.id,
        )
        self.assertEqual(first["status"], "created")
        self.assertEqual(first["version_number"], 1)

        second = create_or_update_text_document(
            corpus_id=self.corpus.id,
            title="Versioned",
            content="version two",
            author_id=self.user.id,
        )

        self.assertEqual(second["status"], "updated")
        self.assertEqual(second["version_number"], 2)
        # New document row (versioning creates a child Document in the same tree)
        self.assertNotEqual(second["document_id"], first["document_id"])

        # The new doc is the current one in the version tree
        new_doc = Document.objects.get(pk=second["document_id"])
        old_doc = Document.objects.get(pk=first["document_id"])
        self.assertEqual(new_doc.version_tree_id, old_doc.version_tree_id)
        self.assertTrue(new_doc.is_current)
        # Refresh old doc — should no longer be current
        old_doc.refresh_from_db()
        self.assertFalse(old_doc.is_current)
        self.assertEqual(new_doc.txt_extract_file.read(), b"version two")

        # Only one active path remains at the derived path
        active = DocumentPath.objects.filter(
            corpus=self.corpus,
            path=second["path"],
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(active.count(), 1)
        active_path = active.first()
        assert active_path is not None
        self.assertEqual(active_path.document_id, second["document_id"])

    def test_markdown_file_type_supported(self):
        """text/markdown is an accepted file_type."""
        result = create_or_update_text_document(
            corpus_id=self.corpus.id,
            title="Readme",
            content="# Title\n\nBody",
            author_id=self.user.id,
            file_type="text/markdown",
        )
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["file_type"], "text/markdown")
        doc = Document.objects.get(pk=result["document_id"])
        self.assertEqual(doc.file_type, "text/markdown")

    def test_pdf_file_type_rejected(self):
        """Binary formats are out of scope for the initial release."""
        with self.assertRaises(ValueError) as ctx:
            create_or_update_text_document(
                corpus_id=self.corpus.id,
                title="Spec",
                content="not really a pdf",
                author_id=self.user.id,
                file_type="application/pdf",
            )
        self.assertIn("Unsupported file_type", str(ctx.exception))

    def test_empty_title_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            create_or_update_text_document(
                corpus_id=self.corpus.id,
                title="   ",
                content="anything",
                author_id=self.user.id,
            )
        self.assertIn("title", str(ctx.exception))

    def test_none_content_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            create_or_update_text_document(
                corpus_id=self.corpus.id,
                title="OK title",
                content=None,
                author_id=self.user.id,
            )
        self.assertIn("content", str(ctx.exception))

    def test_empty_string_content_rejected(self):
        """Empty / whitespace-only content must be rejected (no 0-byte docs)."""
        for empty in ("", "   ", "\n\t"):
            with self.assertRaises(ValueError) as ctx:
                create_or_update_text_document(
                    corpus_id=self.corpus.id,
                    title="OK title",
                    content=empty,
                    author_id=self.user.id,
                )
            self.assertIn("content", str(ctx.exception))

    def test_oversize_content_rejected(self):
        """Content larger than MAX_FILE_UPLOAD_SIZE_BYTES is rejected pre-encoding."""
        # Patch the module's reference so the test doesn't have to allocate
        # gigabytes of bytes to trigger the cap.
        with patch(
            "opencontractserver.llms.tools.core_tools."
            "text_document_import.MAX_FILE_UPLOAD_SIZE_BYTES",
            16,
        ):
            with self.assertRaises(ValueError) as ctx:
                create_or_update_text_document(
                    corpus_id=self.corpus.id,
                    title="Big",
                    content="x" * 32,
                    author_id=self.user.id,
                )
            self.assertIn("maximum upload size", str(ctx.exception).lower())

    def test_quota_exceeded_rejected(self):
        """A user over the upload quota gets a ValueError before any DB write."""
        with patch(
            "opencontractserver.documents.document_service."
            "DocumentService.check_user_upload_quota",
            return_value=(False, "Your usage is capped at 10 documents."),
        ):
            with self.assertRaises(ValueError) as ctx:
                create_or_update_text_document(
                    corpus_id=self.corpus.id,
                    title="Over Cap",
                    content="some text",
                    author_id=self.user.id,
                )
            self.assertIn("capped", str(ctx.exception))

    def test_upload_text_document_alias_works(self):
        """The upload_text_document alias delegates to the same implementation."""
        result = upload_text_document(
            corpus_id=self.corpus.id,
            title="Via Alias",
            content="aliased",
            author_id=self.user.id,
        )
        self.assertEqual(result["status"], "created")
        doc = Document.objects.get(pk=result["document_id"])
        self.assertEqual(doc.txt_extract_file.read(), b"aliased")

    def test_nonexistent_user_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            create_or_update_text_document(
                corpus_id=self.corpus.id,
                title="X",
                content="y",
                author_id=999999,
            )
        self.assertIn("does not exist", str(ctx.exception))

    def test_inaccessible_corpus_rejected(self):
        """IDOR: a corpus belonging to another user surfaces as not-found."""
        private_corpus = Corpus.objects.create(title="Private", creator=self.other_user)
        with self.assertRaises(ValueError) as ctx:
            create_or_update_text_document(
                corpus_id=private_corpus.id,
                title="X",
                content="y",
                author_id=self.user.id,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_read_only_corpus_rejected(self):
        """A user with only READ on the corpus cannot create or version docs."""
        shared_corpus = Corpus.objects.create(title="Shared", creator=self.other_user)
        set_permissions_for_obj_to_user(
            self.user, shared_corpus, [PermissionTypes.READ]
        )
        with self.assertRaises(PermissionError) as ctx:
            create_or_update_text_document(
                corpus_id=shared_corpus.id,
                title="X",
                content="y",
                author_id=self.user.id,
            )
        self.assertIn("Permission denied", str(ctx.exception))

    def test_folder_in_other_corpus_rejected(self):
        """A folder belonging to a different corpus surfaces as not-found."""
        other_corpus = Corpus.objects.create(title="Other", creator=self.user)
        other_folder = CorpusFolder.objects.create(
            name="Other Folder", corpus=other_corpus, creator=self.user
        )
        with self.assertRaises(ValueError) as ctx:
            create_or_update_text_document(
                corpus_id=self.corpus.id,
                title="X",
                content="y",
                author_id=self.user.id,
                folder_id=other_folder.id,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_path_derivation_collapses_unsafe_chars(self):
        """Path sanitisation matches Corpus.add_document so equal titles hit same path."""
        result = create_or_update_text_document(
            corpus_id=self.corpus.id,
            title="Contract / Draft #3",
            content="x",
            author_id=self.user.id,
        )
        # Each non-alphanumeric char collapses to a single ``_``: ``" / "``
        # becomes ``___`` (space, ``/``, space) and ``" #"`` becomes ``__``
        # (space, ``#``).
        self.assertEqual(result["path"], "/documents/Contract___Draft__3")


class TestCreateOrUpdateTextDocumentAsync(TransactionTestCase):
    """Async smoke test for acreate_or_update_text_document.

    Uses TransactionTestCase because async_to_sync runs the coroutine in a
    separate thread that cannot see uncommitted data from TestCase's
    in-transaction wrapper. Document processing signals are disabled
    session-wide by the ``disable_document_processing_signals`` autouse
    fixture in ``conftest.py``.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="async_author", password="pw")
        self.corpus = Corpus.objects.create(title="Async Corpus", creator=self.user)

    def test_async_wrapper_creates_document(self):
        result = async_to_sync(acreate_or_update_text_document)(
            corpus_id=self.corpus.id,
            title="From Async",
            content="async content",
            author_id=self.user.id,
        )

        self.assertEqual(result["status"], "created")
        self.assertEqual(result["version_number"], 1)
        doc = Document.objects.get(pk=result["document_id"])
        self.assertEqual(doc.txt_extract_file.read(), b"async content")

    def test_async_alias_routes_to_same_implementation(self):
        """The aupload_text_document alias is callable end-to-end."""
        result = async_to_sync(aupload_text_document)(
            corpus_id=self.corpus.id,
            title="Async Alias",
            content="async aliased",
            author_id=self.user.id,
        )
        self.assertEqual(result["status"], "created")
        doc = Document.objects.get(pk=result["document_id"])
        self.assertEqual(doc.txt_extract_file.read(), b"async aliased")
