"""Tests for the corpus file-management agent tools.

Covers ``search_corpus_documents`` (read-only), ``rename_document`` and
``delete_document`` (write + approval gated). The existing ``move_document``
tool is covered separately in ``test_move_document_tool.py``.
"""

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.tools.core_tools import (
    adelete_document,
    arename_document,
    asearch_corpus_documents,
    delete_document,
    rename_document,
    search_corpus_documents,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


def _add_doc(corpus, user, title, *, folder=None, file_type="application/pdf"):
    """Create a standalone document and add it to ``corpus`` as a file."""
    original = Document.objects.create(
        title=title, description="", creator=user, file_type=file_type
    )
    original.txt_extract_file.save("doc.txt", ContentFile(b"content"))
    corpus_doc, *_ = corpus.add_document(document=original, user=user, folder=folder)
    set_permissions_for_obj_to_user(user, corpus_doc, [PermissionTypes.CRUD])
    return corpus_doc


class TestSearchCorpusDocuments(TestCase):
    """Tests for the read-only ``search_corpus_documents`` tool."""

    def setUp(self):
        self.user = User.objects.create_user(username="searcher", password="pw")
        self.other_user = User.objects.create_user(username="other", password="pw")

        self.corpus = Corpus.objects.create(title="Files Corpus", creator=self.user)
        self.folder = CorpusFolder.objects.create(
            name="Legal", corpus=self.corpus, creator=self.user
        )

        self.contract = _add_doc(
            self.corpus, self.user, "Master Agreement.pdf", folder=self.folder
        )
        self.invoice = _add_doc(self.corpus, self.user, "Invoice 2024.pdf")

    def test_lists_all_documents_without_query(self):
        results = search_corpus_documents(
            corpus_id=self.corpus.id, user_id=self.user.id
        )
        ids = {row["document_id"] for row in results}
        self.assertEqual(ids, {self.contract.id, self.invoice.id})
        # Path / folder metadata is surfaced for the agent.
        by_id = {row["document_id"]: row for row in results}
        self.assertEqual(by_id[self.contract.id]["folder_name"], "Legal")
        self.assertIsNone(by_id[self.invoice.id]["folder_name"])
        self.assertFalse(by_id[self.invoice.id]["is_deleted"])

    def test_search_by_title_substring(self):
        results = search_corpus_documents(
            corpus_id=self.corpus.id, query="invoice", user_id=self.user.id
        )
        self.assertEqual([r["document_id"] for r in results], [self.invoice.id])

    def test_search_by_path_substring(self):
        # The contract's path is /documents/Master_Agreement.pdf: the space in
        # the original "Master Agreement.pdf" filename collapses to "_" via
        # sanitize_corpus_filename, so we search for the sanitised segment. If
        # that sanitisation rule changes, update this query to match.
        results = search_corpus_documents(
            corpus_id=self.corpus.id, query="Master_Agreement", user_id=self.user.id
        )
        self.assertEqual([r["document_id"] for r in results], [self.contract.id])

    def test_folder_filter(self):
        results = search_corpus_documents(
            corpus_id=self.corpus.id,
            folder_id=self.folder.id,
            user_id=self.user.id,
        )
        self.assertEqual([r["document_id"] for r in results], [self.contract.id])

    def test_excludes_deleted_by_default_and_includes_on_request(self):
        from opencontractserver.corpuses.services import DocumentLifecycleService

        ok, err = DocumentLifecycleService.soft_delete_document(
            user=self.user, document=self.invoice, corpus=self.corpus
        )
        self.assertTrue(ok, err)

        active = search_corpus_documents(corpus_id=self.corpus.id, user_id=self.user.id)
        self.assertEqual([r["document_id"] for r in active], [self.contract.id])

        with_trash = search_corpus_documents(
            corpus_id=self.corpus.id, include_deleted=True, user_id=self.user.id
        )
        trashed = {r["document_id"]: r for r in with_trash}
        self.assertIn(self.invoice.id, trashed)
        self.assertTrue(trashed[self.invoice.id]["is_deleted"])

    def test_limit_is_capped(self):
        results = search_corpus_documents(
            corpus_id=self.corpus.id, limit=1, user_id=self.user.id
        )
        self.assertEqual(len(results), 1)

    def test_inaccessible_corpus_raises(self):
        """A corpus the user cannot see raises the same error as not-found."""
        with self.assertRaises(ValueError) as ctx:
            search_corpus_documents(
                corpus_id=self.corpus.id, user_id=self.other_user.id
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_respects_document_level_visibility(self):
        """Corpus READ alone does not leak private documents (MIN semantic).

        other_user is granted READ on the corpus but NOT on either private
        document, so the search returns an empty list rather than exposing
        files they cannot see at the document level.
        """
        set_permissions_for_obj_to_user(
            self.other_user, self.corpus, [PermissionTypes.READ]
        )
        results = search_corpus_documents(
            corpus_id=self.corpus.id, user_id=self.other_user.id
        )
        self.assertEqual(results, [])


class TestRenameDocument(TestCase):
    """Tests for the ``rename_document`` tool (filename-only rename)."""

    def setUp(self):
        self.user = User.objects.create_user(username="renamer", password="pw")
        self.other_user = User.objects.create_user(username="other", password="pw")

        self.corpus = Corpus.objects.create(title="Rename Corpus", creator=self.user)
        self.folder = CorpusFolder.objects.create(
            name="Legal", corpus=self.corpus, creator=self.user
        )
        # Path becomes /documents/report.pdf (folder stored separately).
        self.doc = _add_doc(self.corpus, self.user, "report.pdf", folder=self.folder)

    def _current_path(self):
        return DocumentPath.objects.get(
            document=self.doc,
            corpus=self.corpus,
            is_current=True,
            is_deleted=False,
        )

    def test_rename_changes_filename_and_keeps_folder(self):
        result = rename_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_name="Quarter Summary",
            user_id=self.user.id,
        )
        self.assertEqual(result["status"], "renamed")
        # Spaces sanitised to underscores; original ".pdf" extension preserved.
        self.assertEqual(result["path"], "/documents/Quarter_Summary.pdf")

        path = self._current_path()
        self.assertEqual(path.path, "/documents/Quarter_Summary.pdf")
        # Rename does NOT move the document — folder is unchanged.
        self.assertEqual(path.folder_id, self.folder.id)

    def test_rename_with_explicit_extension(self):
        result = rename_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_name="summary.md",
            user_id=self.user.id,
        )
        self.assertEqual(result["path"], "/documents/summary.md")

    def test_rename_sanitizes_path_separators(self):
        """Slashes collapse to underscores — a rename can't traverse folders."""
        result = rename_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_name="a/b c.pdf",
            user_id=self.user.id,
        )
        self.assertEqual(result["path"], "/documents/a_b_c.pdf")

    def test_rename_to_same_name_is_noop(self):
        result = rename_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_name="report",  # extension preserved -> report.pdf == current
            user_id=self.user.id,
        )
        # A no-op rename reports "unchanged" (not "renamed") so the agent does
        # not retry believing the write silently failed.
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["path"], "/documents/report.pdf")

    def test_rename_disambiguates_on_conflict(self):
        """Renaming onto an occupied filename gets a numeric suffix."""
        _add_doc(self.corpus, self.user, "taken.pdf")
        result = rename_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_name="taken.pdf",
            user_id=self.user.id,
        )
        self.assertEqual(result["path"], "/documents/taken_1.pdf")

    def test_rename_inaccessible_corpus_raises(self):
        with self.assertRaises(ValueError) as ctx:
            rename_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                new_name="x",
                user_id=self.other_user.id,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_rename_nonexistent_document_raises(self):
        with self.assertRaises(ValueError) as ctx:
            rename_document(
                document_id=999999,
                corpus_id=self.corpus.id,
                new_name="x",
                user_id=self.user.id,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_rename_document_not_in_corpus_raises(self):
        other_corpus = Corpus.objects.create(title="Other", creator=self.user)
        with self.assertRaises(ValueError) as ctx:
            rename_document(
                document_id=self.doc.id,
                corpus_id=other_corpus.id,
                new_name="x",
                user_id=self.user.id,
            )
        self.assertIn("Rename failed", str(ctx.exception))

    def test_rename_no_write_permission_raises(self):
        set_permissions_for_obj_to_user(
            self.other_user, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.doc, [PermissionTypes.READ]
        )
        with self.assertRaises(ValueError) as ctx:
            rename_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                new_name="x",
                user_id=self.other_user.id,
            )
        self.assertIn("Rename failed", str(ctx.exception))
        self.assertIn("Permission denied", str(ctx.exception))

    def test_rename_missing_user_raises_permission_error(self):
        with self.assertRaises(PermissionError):
            rename_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                new_name="x",
                user_id=999999,
            )

    def test_rename_none_user_raises_permission_error(self):
        # The None guard is the distinct first branch (no user injected at all),
        # separate from the "user id not found" branch above.
        with self.assertRaises(PermissionError):
            rename_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                new_name="x",
                user_id=None,
            )

    def test_rename_all_special_chars_collapse_to_underscores(self):
        # Every disallowed char becomes "_" (it is never dropped), so a name
        # made entirely of special chars never collapses to empty — it yields
        # underscores, and the original ".pdf" extension is preserved. (The
        # "untitled" fallback in sanitize_corpus_filename is only reachable for
        # a truly empty name, which rename_document rejects up front.)
        result = rename_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_name="!!!!",
            user_id=self.user.id,
        )
        self.assertEqual(result["status"], "renamed")
        self.assertEqual(result["path"], "/documents/____.pdf")


class TestDeleteDocument(TestCase):
    """Tests for the ``delete_document`` tool (soft-delete to corpus trash)."""

    def setUp(self):
        self.user = User.objects.create_user(username="deleter", password="pw")
        self.other_user = User.objects.create_user(username="other", password="pw")

        self.corpus = Corpus.objects.create(title="Delete Corpus", creator=self.user)
        self.doc = _add_doc(self.corpus, self.user, "disposable.pdf")

    def test_delete_soft_deletes_document(self):
        result = delete_document(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            user_id=self.user.id,
        )
        self.assertEqual(result["status"], "deleted")

        # The active path is gone; a current soft-deleted path exists (trash).
        self.assertFalse(
            DocumentPath.objects.filter(
                document=self.doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=False,
            ).exists()
        )
        self.assertTrue(
            DocumentPath.objects.filter(
                document=self.doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=True,
            ).exists()
        )

    def test_delete_inaccessible_corpus_raises(self):
        with self.assertRaises(ValueError) as ctx:
            delete_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                user_id=self.other_user.id,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_delete_nonexistent_document_raises(self):
        with self.assertRaises(ValueError) as ctx:
            delete_document(
                document_id=999999,
                corpus_id=self.corpus.id,
                user_id=self.user.id,
            )
        self.assertIn("does not exist or is not accessible", str(ctx.exception))

    def test_delete_no_delete_permission_raises(self):
        """READ-only access is not enough to delete — service rejects it."""
        set_permissions_for_obj_to_user(
            self.other_user, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.doc, [PermissionTypes.READ]
        )
        with self.assertRaises(ValueError) as ctx:
            delete_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                user_id=self.other_user.id,
            )
        self.assertIn("Delete failed", str(ctx.exception))
        self.assertIn("Permission denied", str(ctx.exception))

    def test_delete_missing_user_raises_permission_error(self):
        with self.assertRaises(PermissionError):
            delete_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                user_id=999999,
            )

    def test_delete_none_user_raises_permission_error(self):
        # The None guard is the distinct first branch (no user injected at all).
        with self.assertRaises(PermissionError):
            delete_document(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                user_id=None,
            )


class TestCorpusFileToolsAsync(TransactionTestCase):
    """Async smoke tests for the a-prefixed wrappers.

    Uses TransactionTestCase because async_to_sync runs the coroutine in a
    separate thread that cannot see uncommitted data from TestCase's
    in-transaction wrapper.
    """

    def setUp(self):
        # ``disable_document_processing_signals`` (conftest, session-scoped,
        # autouse) already disconnects ``process_doc_on_create_atomic`` for the
        # whole run, so committing documents here won't dispatch celery tasks
        # against absent media. Do NOT disconnect/reconnect locally: a
        # ``finally: post_save.connect(...)`` leaves the signal CONNECTED for
        # every later test sharing this xdist worker, breaking unrelated
        # TransactionTestCase tests (e.g. EmbeddingManagerConcurrentTest).
        self.user = User.objects.create_user(username="async_files", password="pw")
        self.corpus = Corpus.objects.create(title="Async Files", creator=self.user)
        self.doc = _add_doc(self.corpus, self.user, "async.pdf")

    def test_async_search_rename_delete(self):
        found = async_to_sync(asearch_corpus_documents)(
            corpus_id=self.corpus.id, user_id=self.user.id
        )
        self.assertEqual([r["document_id"] for r in found], [self.doc.id])

        renamed = async_to_sync(arename_document)(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_name="renamed",
            user_id=self.user.id,
        )
        self.assertEqual(renamed["path"], "/documents/renamed.pdf")

        deleted = async_to_sync(adelete_document)(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            user_id=self.user.id,
        )
        self.assertEqual(deleted["status"], "deleted")
