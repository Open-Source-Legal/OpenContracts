"""
Regression tests for issue #2520: importing a file into a folder must not version
over an unrelated same-named document in a different folder.

The contract these tests pin:

- A different folder means a different document.
- Re-importing into the same folder is still a new version, including for documents
  stored at the legacy ``/documents/<name>`` path regardless of their folder.
- With no folder, nothing changes: ``folder=None`` means "keep the current folder",
  which is what lets callers update a document by name without restating its folder.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.document_imports.services import import_document_for_user
from opencontractserver.documents.models import DocumentPath
from opencontractserver.llms.tools.core_tools.text_document_import import (
    create_or_update_text_document,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

FILENAME = "summary.txt"
TEXT_TYPE = "text/plain"


class FolderImportTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="folderuser", password="12345678", is_usage_capped=False
        )
        self.corpus = Corpus.objects.create(title="Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.folder_a = self._folder("Folder_A")
        self.folder_b = self._folder("Folder_B")

    def _folder(self, name, parent=None):
        return CorpusFolder.objects.create(
            name=name, corpus=self.corpus, creator=self.user, parent=parent
        )

    def _import(self, content, folder=None, filename=FILENAME, **kwargs):
        return self.corpus.import_content(
            user=self.user,
            content=content,
            filename=filename,
            folder=folder,
            file_type=TEXT_TYPE,
            title=filename,
            **kwargs,
        )

    def _assert_independent(self, first, second):
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.version_tree_id, second.version_tree_id)
        for document in (first, second):
            self.assertTrue(
                DocumentPath.objects.filter(
                    document=document, is_current=True, is_deleted=False
                ).exists(),
                f"Document {document.pk} lost its active path",
            )


class TestImportContentFolderPaths(FolderImportTestBase):
    def test_same_filename_in_different_folders_stays_separate(self):
        first, first_status, _ = self._import(b"AAA", self.folder_a)
        second, second_status, _ = self._import(b"BBB", self.folder_b)

        self.assertEqual((first_status, second_status), ("created", "created"))
        self._assert_independent(first, second)
        self.assertEqual(self.folder_a.get_document_count(), 1)
        self.assertEqual(self.folder_b.get_document_count(), 1)

    def test_path_reflects_the_folder(self):
        parent = self._folder("Parent")
        child = self._folder("Child", parent=parent)

        _, _, path = self._import(b"AAA", child)

        self.assertEqual(path.path, f"/Parent/Child/{FILENAME}")
        self.assertEqual(path.folder_id, child.pk)

    def test_reimport_into_the_same_folder_is_a_new_version(self):
        first, _, _ = self._import(b"AAA", self.folder_a)
        second, status, path = self._import(b"BBB", self.folder_a)

        self.assertEqual(status, "updated")
        self.assertEqual(first.version_tree_id, second.version_tree_id)
        self.assertEqual(path.version_number, 2)
        self.assertEqual(self.folder_a.get_document_count(), 1)

    def test_reimport_versions_a_legacy_path_in_the_same_folder(self):
        legacy, _, _ = self._import(
            b"AAA", self.folder_a, path=f"/documents/{FILENAME}"
        )

        second, status, path = self._import(b"BBB", self.folder_a)

        self.assertEqual(status, "updated")
        self.assertEqual(legacy.version_tree_id, second.version_tree_id)
        self.assertEqual(path.path, f"/documents/{FILENAME}")
        self.assertEqual(self.folder_a.get_document_count(), 1)

    def test_reimport_prefers_the_folder_path_over_a_legacy_one(self):
        self._import(b"AAA", self.folder_a, path=f"/documents/{FILENAME}")
        current, _, _ = self._import(
            b"BBB", self.folder_a, path=f"/Folder_A/{FILENAME}"
        )

        second, status, path = self._import(b"CCC", self.folder_a)

        self.assertEqual(status, "updated")
        self.assertEqual(current.version_tree_id, second.version_tree_id)
        self.assertEqual(path.path, f"/Folder_A/{FILENAME}")

    def test_legacy_path_in_another_folder_is_left_alone(self):
        legacy, _, _ = self._import(
            b"AAA", self.folder_a, path=f"/documents/{FILENAME}"
        )

        second, status, _ = self._import(b"BBB", self.folder_b)

        self.assertEqual(status, "created")
        self._assert_independent(legacy, second)
        self.assertEqual(self.folder_a.get_document_count(), 1)

    def test_occupied_folder_path_is_disambiguated_not_versioned(self):
        """A document outside the folder can hold the folder's path explicitly."""
        occupant, _, _ = self._import(
            b"AAA", self.folder_b, path=f"/Folder_A/{FILENAME}"
        )

        second, status, path = self._import(b"BBB", self.folder_a)

        self.assertEqual(status, "created")
        self.assertEqual(path.path, "/Folder_A/summary_1.txt")
        self._assert_independent(occupant, second)

    def test_filename_cannot_escape_the_folder(self):
        _, _, path = self._import(b"AAA", self.folder_a, filename="../../etc/passwd")

        self.assertTrue(path.path.startswith("/Folder_A/"))
        self.assertEqual(path.path.count("/"), 2)

    def test_filename_wildcards_match_literally(self):
        self._import(b"AAA", self.folder_a, filename="summary.txt")

        _, status, _ = self._import(b"BBB", self.folder_a, filename="summ_ry.txt")

        self.assertEqual(status, "created")

    def test_import_without_a_folder_is_unchanged(self):
        first, _, path = self._import(b"AAA")
        second, status, _ = self._import(b"BBB")

        self.assertEqual(path.path, f"/documents/{FILENAME}")
        self.assertEqual(status, "updated")
        self.assertEqual(first.version_tree_id, second.version_tree_id)

    def test_foldered_and_unfoldered_imports_do_not_collide(self):
        first, _, _ = self._import(b"AAA")
        second, status, _ = self._import(b"BBB", self.folder_a)

        self.assertEqual(status, "created")
        self._assert_independent(first, second)


class TestImportServiceFolderPaths(FolderImportTestBase):
    """The single-document upload service is the path the bug was reported through."""

    def _upload(self, content, folder):
        result = import_document_for_user(
            user=self.user,
            file_bytes=content,
            filename=FILENAME,
            title=FILENAME,
            description="",
            add_to_corpus_id=str(self.corpus.pk),
            add_to_folder_id=str(folder.pk),
        )
        self.assertIsNone(result.error)
        return result

    def test_same_filename_in_different_folders_stays_separate(self):
        first = self._upload(b"first plain text body", self.folder_a)
        second = self._upload(b"second plain text body", self.folder_b)

        self.assertEqual((first.status, second.status), ("created", "created"))
        self._assert_independent(first.document, second.document)
        self.assertEqual(self.folder_a.get_document_count(), 1)
        self.assertEqual(self.folder_b.get_document_count(), 1)


class TestTextDocumentToolFolderPaths(FolderImportTestBase):
    """The agent tool derives its own path, so it needs the same protection."""

    def _write(self, content, folder=None, title="Notes"):
        return create_or_update_text_document(
            corpus_id=self.corpus.pk,
            title=title,
            content=content,
            author_id=self.user.pk,
            folder_id=folder.pk if folder else None,
        )

    def test_same_title_in_different_folders_stays_separate(self):
        first = self._write("AAA", self.folder_a)
        second = self._write("BBB", self.folder_b)

        self.assertEqual((first["status"], second["status"]), ("created", "created"))
        self.assertNotEqual(first["document_id"], second["document_id"])
        self.assertEqual(self.folder_a.get_document_count(), 1)
        self.assertEqual(self.folder_b.get_document_count(), 1)

    def test_same_title_in_the_same_folder_is_a_new_version(self):
        self._write("AAA", self.folder_a)
        second = self._write("BBB", self.folder_a)

        self.assertEqual(second["status"], "updated")
        self.assertEqual(second["version_number"], 2)

    def test_update_by_title_without_a_folder_is_unchanged(self):
        """An agent updating by title needn't restate where the document lives."""
        self.corpus.import_content(
            user=self.user,
            content=b"AAA",
            path="/documents/Notes",
            folder=self.folder_a,
            file_type=TEXT_TYPE,
            title="Notes",
        )

        result = self._write("BBB")

        self.assertEqual(result["status"], "updated")
        self.assertEqual(self.folder_a.get_document_count(), 1)
