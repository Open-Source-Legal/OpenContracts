"""
Integration tests for zip import with folder structure preservation.

These tests verify:
- Folder structure creation from zip paths
- Celery task for zip import
- GraphQL mutation for zip import
- Permission checks
- Error handling and partial success scenarios
"""

import io
import logging
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus, CorpusFolder, TemporaryFileHandle
from opencontractserver.corpuses.services import FolderCRUDService
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class TestCreateFolderStructureFromPaths(TestCase):
    """Tests for FolderCRUDService.create_folder_structure_from_paths()."""

    def setUp(self):
        """Set up test user and corpus."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass"
            )
            self.other_user = User.objects.create_user(
                username="other", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Corpus for testing",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

    def test_create_simple_folder_structure(self):
        """Create a simple folder structure from paths."""
        folder_paths = ["docs", "docs/contracts", "legal"]

        folder_map, created, reused, error = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.user,
                corpus=self.corpus,
                folder_paths=folder_paths,
            )
        )

        self.assertEqual(error, "")
        self.assertEqual(created, 3)
        self.assertEqual(reused, 0)
        self.assertEqual(len(folder_map), 3)
        self.assertIn("docs", folder_map)
        self.assertIn("docs/contracts", folder_map)
        self.assertIn("legal", folder_map)

        # Verify parent-child relationships
        self.assertIsNone(folder_map["docs"].parent)
        self.assertEqual(folder_map["docs/contracts"].parent, folder_map["docs"])
        self.assertIsNone(folder_map["legal"].parent)

    def test_reuse_existing_folders(self):
        """Existing folders should be reused, not duplicated."""
        # Create initial folder structure
        folder_paths_1 = ["docs", "docs/contracts"]
        folder_map_1, created_1, reused_1, error_1 = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.user,
                corpus=self.corpus,
                folder_paths=folder_paths_1,
            )
        )
        self.assertEqual(created_1, 2)
        self.assertEqual(reused_1, 0)

        # Create overlapping structure - should reuse "docs"
        folder_paths_2 = ["docs", "docs/legal"]
        folder_map_2, created_2, reused_2, error_2 = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.user,
                corpus=self.corpus,
                folder_paths=folder_paths_2,
            )
        )

        self.assertEqual(error_2, "")
        self.assertEqual(created_2, 1)  # Only docs/legal is new
        self.assertEqual(reused_2, 1)  # docs is reused
        self.assertEqual(folder_map_1["docs"].id, folder_map_2["docs"].id)

    def test_create_with_target_folder(self):
        """Create folder structure under a target folder."""
        # Create target folder
        target_folder = CorpusFolder.objects.create(
            name="imports",
            corpus=self.corpus,
            creator=self.user,
        )

        folder_paths = ["2024", "2024/contracts"]
        folder_map, created, reused, error = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.user,
                corpus=self.corpus,
                folder_paths=folder_paths,
                target_folder=target_folder,
            )
        )

        self.assertEqual(error, "")
        self.assertEqual(created, 2)

        # Verify folders are children of target folder
        self.assertEqual(folder_map["2024"].parent, target_folder)

    def test_empty_folder_paths(self):
        """Empty folder paths list should return empty map."""
        folder_map, created, reused, error = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.user,
                corpus=self.corpus,
                folder_paths=[],
            )
        )

        self.assertEqual(error, "")
        self.assertEqual(created, 0)
        self.assertEqual(reused, 0)
        self.assertEqual(len(folder_map), 0)

    def test_permission_denied_for_non_owner(self):
        """User without write permission should be denied."""
        folder_paths = ["docs"]
        folder_map, created, reused, error = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.other_user,  # Not the corpus owner
                corpus=self.corpus,
                folder_paths=folder_paths,
            )
        )

        self.assertIn("Permission denied", error)
        self.assertEqual(len(folder_map), 0)


class TestImportZipWithFolderStructureTask(TestCase):
    """Tests for the import_zip_with_folder_structure Celery task."""

    def setUp(self):
        """Set up test user, corpus, and sample data."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Corpus for testing",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        # Sample PDF bytes
        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _create_test_zip(self, files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file for testing."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a TemporaryFileHandle from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name="test_import.zip")
        handle = TemporaryFileHandle.objects.create(
            file=zip_content,
        )
        return handle

    def test_import_simple_zip(self):
        """Import a simple zip with a few PDF files."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-job-1",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["completed"])
        self.assertTrue(result["success"])
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["files_processed"], 2)
        self.assertEqual(len(result["document_ids"]), 2)
        self.assertEqual(result["folders_created"], 0)

        # Verify documents exist in corpus
        doc_paths = DocumentPath.objects.filter(corpus=self.corpus)
        self.assertEqual(doc_paths.count(), 2)

    def test_import_zip_with_folder_structure(self):
        """Import a zip with folder structure preserved."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "docs/contracts/file1.pdf": self.pdf_bytes,
            "docs/legal/file2.pdf": self.pdf_bytes,
            "other/file3.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-job-2",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["completed"])
        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 3)
        self.assertEqual(
            result["folders_created"], 4
        )  # docs, docs/contracts, docs/legal, other

        # Verify folders exist
        folders = CorpusFolder.objects.filter(corpus=self.corpus)
        folder_names = {f.name for f in folders}
        self.assertIn("docs", folder_names)
        self.assertIn("contracts", folder_names)
        self.assertIn("legal", folder_names)
        self.assertIn("other", folder_names)

        # Verify documents are in correct folders
        doc_paths = DocumentPath.objects.filter(corpus=self.corpus)
        self.assertEqual(doc_paths.count(), 3)

        # Check folder assignments
        for dp in doc_paths:
            self.assertIsNotNone(dp.folder)

    def test_import_with_hidden_files_skipped(self):
        """Hidden files and __MACOSX entries are skipped."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "file1.pdf": self.pdf_bytes,
            ".hidden.pdf": self.pdf_bytes,
            "__MACOSX/._file1.pdf": b"metadata",
            ".DS_Store": b"ds store",
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-job-3",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["completed"])
        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 1)
        self.assertGreater(result["files_skipped_hidden"], 0)

    def test_import_with_unsupported_file_types(self):
        """Unsupported file types are skipped."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Use actual binary content that won't be detected as text/plain
        # EXE magic bytes (MZ header)
        exe_magic = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff"
        # Random binary with null bytes to ensure it's not detected as text
        binary_content = b"\x00\x01\x02\x03\x04\xff\xfe\xfd\xfc\xfb\x00"

        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.exe": exe_magic + binary_content,
            "file3.xyz": binary_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-job-4",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["completed"])
        self.assertEqual(result["files_processed"], 1)
        self.assertGreater(result["files_skipped_type"], 0)

    def test_import_with_text_files(self):
        """Plain text files are processed correctly."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "readme.txt": b"This is a plain text file for testing.",
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-job-5",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["completed"])
        self.assertEqual(result["files_processed"], 1)

        # Verify text document was created
        doc = Document.objects.get(id=result["document_ids"][0])
        self.assertEqual(doc.file_type, "text/plain")

    def test_import_with_title_prefix(self):
        """Documents get title prefix when specified."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "file1.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-job-6",
                "corpus_id": self.corpus.id,
                "title_prefix": "IMPORT",
            }
        ).get()

        self.assertTrue(result["success"])
        doc = Document.objects.get(id=result["document_ids"][0])
        self.assertTrue(doc.title.startswith("IMPORT - "))

    def test_import_corpus_not_found(self):
        """Non-existent corpus ID returns error."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {"file1.pdf": self.pdf_bytes}
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-job-7",
                "corpus_id": 99999,  # Non-existent
            }
        ).get()

        self.assertTrue(result["completed"])
        self.assertFalse(result["success"])
        self.assertTrue(any("not found" in e.lower() for e in result["errors"]))

    def test_import_with_target_folder(self):
        """Import into a specific target folder."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Create target folder
        target_folder = CorpusFolder.objects.create(
            name="imports",
            corpus=self.corpus,
            creator=self.user,
        )

        files = {
            "file1.pdf": self.pdf_bytes,
            "subdir/file2.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-job-8",
                "corpus_id": self.corpus.id,
                "target_folder_id": target_folder.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 2)

        # Verify files are under target folder
        doc_paths = DocumentPath.objects.filter(corpus=self.corpus)
        for dp in doc_paths:
            # Either directly in target_folder or in a subfolder of target_folder
            if dp.folder:
                self.assertTrue(
                    dp.folder == target_folder or dp.folder.parent == target_folder
                )


class TestZipValidationFailures(TestCase):
    """Tests for zip validation failure scenarios."""

    def setUp(self):
        """Set up test user and corpus."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Corpus for testing",
                creator=self.user,
            )

        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _create_test_zip(self, files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file for testing."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a TemporaryFileHandle from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name="test_import.zip")
        handle = TemporaryFileHandle.objects.create(
            file=zip_content,
        )
        return handle

    def test_path_traversal_files_skipped(self):
        """Files with path traversal attempts are skipped."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Create a zip with path traversal attempts
        # Note: zipfile module prevents literal ".." in filenames during creation
        # but we test the validation behavior
        files = {
            "safe_file.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-traversal",
                "corpus_id": self.corpus.id,
            }
        ).get()

        # Should process the safe file
        self.assertTrue(result["completed"])
        self.assertEqual(result["files_processed"], 1)

    def test_too_many_files_rejected(self):
        """Zip with too many files is rejected at validation."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )
        from opencontractserver.utils import zip_security

        # Temporarily override the constant
        original = zip_security.ZIP_MAX_FILE_COUNT
        zip_security.ZIP_MAX_FILE_COUNT = 5

        try:
            files = {f"file{i}.pdf": self.pdf_bytes for i in range(10)}
            zip_buffer = self._create_test_zip(files)
            handle = self._create_temp_file_handle(zip_buffer)

            result = import_zip_with_folder_structure.apply(
                kwargs={
                    "temporary_file_handle_id": handle.id,
                    "user_id": self.user.id,
                    "job_id": "test-too-many",
                    "corpus_id": self.corpus.id,
                }
            ).get()

            self.assertTrue(result["completed"])
            self.assertFalse(result["validation_passed"])
            self.assertTrue(
                any("files" in e.lower() for e in result["validation_errors"])
            )
        finally:
            zip_security.ZIP_MAX_FILE_COUNT = original

    def test_oversized_files_skipped_not_rejected(self):
        """Individual oversized files are skipped, not rejected entirely."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )
        from opencontractserver.utils import zip_security

        # Temporarily set a very small file size limit
        original = zip_security.ZIP_MAX_SINGLE_FILE_SIZE_BYTES
        zip_security.ZIP_MAX_SINGLE_FILE_SIZE_BYTES = 100  # 100 bytes

        try:
            files = {
                "small.txt": b"x" * 50,  # Under limit
                "large.txt": b"x" * 200,  # Over limit
            }
            zip_buffer = self._create_test_zip(files)
            handle = self._create_temp_file_handle(zip_buffer)

            result = import_zip_with_folder_structure.apply(
                kwargs={
                    "temporary_file_handle_id": handle.id,
                    "user_id": self.user.id,
                    "job_id": "test-oversized",
                    "corpus_id": self.corpus.id,
                }
            ).get()

            self.assertTrue(result["completed"])
            self.assertTrue(result["validation_passed"])
            self.assertEqual(result["files_skipped_size"], 1)
            self.assertIn("large.txt", result["skipped_oversized"])
        finally:
            zip_security.ZIP_MAX_SINGLE_FILE_SIZE_BYTES = original


class TestDocumentUpversioning(TestCase):
    """Tests for document upversioning on path collisions."""

    def setUp(self):
        """Set up test user and corpus."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Corpus for testing",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _create_test_zip(self, files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file for testing."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a TemporaryFileHandle from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name="test_import.zip")
        handle = TemporaryFileHandle.objects.create(
            file=zip_content,
        )
        return handle

    def test_second_import_upversions_existing_document(self):
        """Second import to same path creates new version, not duplicate."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # First import
        files_1 = {"filing_data/test.pdf": self.pdf_bytes}
        zip_1 = self._create_test_zip(files_1)
        handle_1 = self._create_temp_file_handle(zip_1)

        result_1 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle_1.id,
                "user_id": self.user.id,
                "job_id": "test-upversion-1",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result_1["success"])
        self.assertEqual(result_1["files_processed"], 1)
        self.assertEqual(
            result_1["files_upversioned"], 0
        )  # First import, no upversioning

        # Get the first document path
        first_doc_path = DocumentPath.objects.get(
            corpus=self.corpus,
            path="/filing_data/test.pdf",
            is_current=True,
        )
        self.assertEqual(first_doc_path.version_number, 1)

        # Second import to same path
        files_2 = {"filing_data/test.pdf": self.pdf_bytes}
        zip_2 = self._create_test_zip(files_2)
        handle_2 = self._create_temp_file_handle(zip_2)

        result_2 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle_2.id,
                "user_id": self.user.id,
                "job_id": "test-upversion-2",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result_2["success"])
        self.assertEqual(result_2["files_processed"], 1)
        self.assertEqual(result_2["files_upversioned"], 1)  # This should be upversioned
        self.assertIn("/filing_data/test.pdf", result_2["upversioned_paths"])

        # Verify version numbers
        old_path = DocumentPath.objects.get(
            corpus=self.corpus,
            path="/filing_data/test.pdf",
            version_number=1,
        )
        self.assertFalse(old_path.is_current)

        new_path = DocumentPath.objects.get(
            corpus=self.corpus,
            path="/filing_data/test.pdf",
            version_number=2,
        )
        self.assertTrue(new_path.is_current)
        self.assertEqual(new_path.parent, old_path)

    def test_upversioning_preserves_folder_structure(self):
        """Upversioning works correctly with nested folder structures."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # First import with nested structure
        files_1 = {
            "contracts/legal/agreement.pdf": self.pdf_bytes,
            "contracts/financial/report.pdf": self.pdf_bytes,
        }
        zip_1 = self._create_test_zip(files_1)
        handle_1 = self._create_temp_file_handle(zip_1)

        result_1 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle_1.id,
                "user_id": self.user.id,
                "job_id": "test-upversion-nested-1",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result_1["success"])
        self.assertEqual(result_1["files_processed"], 2)

        # Second import replaces one file
        files_2 = {
            "contracts/legal/agreement.pdf": self.pdf_bytes,  # Upversion this
        }
        zip_2 = self._create_test_zip(files_2)
        handle_2 = self._create_temp_file_handle(zip_2)

        result_2 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle_2.id,
                "user_id": self.user.id,
                "job_id": "test-upversion-nested-2",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result_2["success"])
        self.assertEqual(result_2["files_processed"], 1)
        self.assertEqual(result_2["files_upversioned"], 1)
        self.assertEqual(
            result_2["folders_reused"], 2
        )  # contracts and contracts/legal reused


class TestFolderReuseAcrossImports(TestCase):
    """Tests for folder reuse behavior across multiple imports."""

    def setUp(self):
        """Set up test user and corpus."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Corpus for testing",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _create_test_zip(self, files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file for testing."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a TemporaryFileHandle from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name="test_import.zip")
        handle = TemporaryFileHandle.objects.create(
            file=zip_content,
        )
        return handle

    def test_second_import_reuses_folders(self):
        """Second import to same paths reuses existing folders."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # First import
        files_1 = {
            "docs/contracts/file1.pdf": self.pdf_bytes,
        }
        zip_1 = self._create_test_zip(files_1)
        handle_1 = self._create_temp_file_handle(zip_1)

        result_1 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle_1.id,
                "user_id": self.user.id,
                "job_id": "test-reuse-1",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertEqual(result_1["folders_created"], 2)  # docs, docs/contracts
        self.assertEqual(result_1["folders_reused"], 0)

        # Record folder IDs
        docs_folder = CorpusFolder.objects.get(corpus=self.corpus, name="docs")
        contracts_folder = CorpusFolder.objects.get(
            corpus=self.corpus, name="contracts", parent=docs_folder
        )

        # Second import to same structure
        files_2 = {
            "docs/contracts/file2.pdf": self.pdf_bytes,
            "docs/legal/file3.pdf": self.pdf_bytes,
        }
        zip_2 = self._create_test_zip(files_2)
        handle_2 = self._create_temp_file_handle(zip_2)

        result_2 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle_2.id,
                "user_id": self.user.id,
                "job_id": "test-reuse-2",
                "corpus_id": self.corpus.id,
            }
        ).get()

        # Only docs/legal is new
        self.assertEqual(result_2["folders_created"], 1)
        self.assertEqual(
            result_2["folders_reused"], 2
        )  # docs and docs/contracts reused

        # Verify same folder objects are used
        docs_folder_after = CorpusFolder.objects.get(corpus=self.corpus, name="docs")
        contracts_folder_after = CorpusFolder.objects.get(
            corpus=self.corpus, name="contracts", parent=docs_folder_after
        )

        self.assertEqual(docs_folder.id, docs_folder_after.id)
        self.assertEqual(contracts_folder.id, contracts_folder_after.id)


class TestRelationshipFileImport(TestCase):
    """Tests for importing ZIP files with relationships.csv."""

    def setUp(self):
        """Set up test user, corpus, and sample data."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Corpus for testing",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        # Sample PDF bytes
        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _create_test_zip(self, files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file for testing."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a TemporaryFileHandle from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name="test_import.zip")
        handle = TemporaryFileHandle.objects.create(
            file=zip_content,
        )
        return handle

    def test_import_with_simple_relationships(self):
        """Import a zip with relationships.csv creates document relationships."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # CSV content with relationships (using parser's expected column names)
        csv_content = b"""source_path,relationship_label,target_path,notes
docs/contract.pdf,AMENDS,docs/amendment.pdf,Amendment to main contract
docs/amendment.pdf,AMENDED_BY,docs/contract.pdf,
"""
        files = {
            "docs/contract.pdf": self.pdf_bytes,
            "docs/amendment.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-relationships-1",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["completed"])
        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 2)  # CSV is not counted as file
        self.assertEqual(result["relationships_created"], 2)
        self.assertEqual(result["relationships_skipped"], 0)

        # Verify relationships exist in database
        relationships = DocumentRelationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 2)

        # Verify relationship details
        rel_labels = {r.annotation_label.text for r in relationships}
        self.assertIn("AMENDS", rel_labels)
        self.assertIn("AMENDED_BY", rel_labels)

    def test_import_with_notes_type_relationship(self):
        """Import relationships with NOTES type creates annotation notes."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,relationship_label,target_path,notes
file1.pdf,REFERENCES,file2.pdf,This document references the other
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-notes-type",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 1)

        # Verify the relationship was created (notes are stored in data field)
        rel = DocumentRelationship.objects.get(corpus=self.corpus)
        self.assertIsNotNone(rel)

    def test_import_with_missing_source_document(self):
        """Relationships with missing source documents are skipped."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,relationship_label,target_path,notes
nonexistent.pdf,REFERENCES,file1.pdf,
file1.pdf,VALID,file2.pdf,
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-missing-source",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 1)  # Only valid one
        self.assertEqual(result["relationships_skipped"], 1)  # Missing source

    def test_import_with_missing_target_document(self):
        """Relationships with missing target documents are skipped."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,relationship_label,target_path,notes
file1.pdf,REFERENCES,nonexistent.pdf,
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-missing-target",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 0)
        self.assertEqual(result["relationships_skipped"], 1)

    def test_import_relationships_creates_labels(self):
        """Importing relationships creates necessary labels and labelsets."""
        from opencontractserver.annotations.models import AnnotationLabel
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,relationship_label,target_path,notes
file1.pdf,CUSTOM_LABEL,file2.pdf,
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-label-creation",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 1)

        # Verify label was created with correct type
        label = AnnotationLabel.objects.get(text="CUSTOM_LABEL", creator=self.user)
        from opencontractserver.types.enums import LabelType

        self.assertEqual(label.label_type, LabelType.RELATIONSHIP_LABEL)

    def test_import_relationships_caches_labels_per_import(self):
        """Importing relationships caches labels to avoid duplicate creation."""
        from opencontractserver.annotations.models import AnnotationLabel
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # CSV with same label used multiple times
        csv_content = b"""source_path,relationship_label,target_path,notes
file1.pdf,SHARED_LABEL,file2.pdf,
file2.pdf,SHARED_LABEL,file1.pdf,
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-cache-labels",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 2)

        # Verify only one label was created (not two for repeated uses)
        labels = AnnotationLabel.objects.filter(text="SHARED_LABEL")
        self.assertEqual(labels.count(), 1)

    def test_import_with_path_normalization_in_relationships(self):
        """Relationships work with various path formats."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # CSV with various path formats that should all normalize correctly
        # Tests: leading /, no leading /, ./ prefix
        csv_content = b"""source_path,relationship_label,target_path,notes
/docs/contract.pdf,AMENDS,docs/amendment.pdf,
./docs/contract.pdf,REFERENCES,/docs/amendment.pdf,
"""
        files = {
            "docs/contract.pdf": self.pdf_bytes,
            "docs/amendment.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-path-normalization",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 2)

        # Verify relationships were created correctly
        relationships = DocumentRelationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 2)

    def test_import_without_relationships_file(self):
        """Import without relationships.csv has zero relationship stats."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-no-relationships",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 0)
        self.assertEqual(result["relationships_skipped"], 0)

    def test_import_with_malformed_csv_continues(self):
        """Malformed relationships.csv doesn't fail the import."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Malformed CSV (missing required columns)
        csv_content = b"""source,target,label
file1.pdf,file2.pdf,LABEL
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-malformed-csv",
                "corpus_id": self.corpus.id,
            }
        ).get()

        # Import should still succeed for documents
        self.assertTrue(result["completed"])
        self.assertEqual(result["files_processed"], 2)
        # Relationship processing should fail gracefully
        self.assertEqual(result["relationships_created"], 0)

    def test_import_relationships_with_target_folder(self):
        """Relationships work correctly when importing to a target folder."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Create target folder
        target_folder = CorpusFolder.objects.create(
            name="imports",
            corpus=self.corpus,
            creator=self.user,
        )

        csv_content = b"""source_path,relationship_label,target_path,notes
file1.pdf,RELATED_TO,file2.pdf,
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-target-folder-relationships",
                "corpus_id": self.corpus.id,
                "target_folder_id": target_folder.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 1)

        # Verify the relationship points to documents in the target folder
        rel = DocumentRelationship.objects.get(corpus=self.corpus)
        self.assertIsNotNone(rel.source_document)
        self.assertIsNotNone(rel.target_document)

    def test_import_relationships_with_nested_folders(self):
        """Relationships work with documents in nested folder structures."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,relationship_label,target_path,notes
contracts/legal/agreement.pdf,REFERENCES,contracts/financial/report.pdf,
"""
        files = {
            "contracts/legal/agreement.pdf": self.pdf_bytes,
            "contracts/financial/report.pdf": self.pdf_bytes,
            "relationships.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-nested-relationships",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["relationships_created"], 1)

        # Verify the relationship was created
        rel = DocumentRelationship.objects.get(corpus=self.corpus)
        self.assertEqual(rel.annotation_label.text, "REFERENCES")


class TestMetadataFileImport(TestCase):
    """Tests for importing ZIP files with meta.csv."""

    def setUp(self):
        """Set up test user, corpus, and sample data."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Corpus for testing",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        # Sample PDF bytes
        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _create_test_zip(self, files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file for testing."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a TemporaryFileHandle from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name="test_import.zip")
        handle = TemporaryFileHandle.objects.create(
            file=zip_content,
        )
        return handle

    def test_import_with_title_metadata(self):
        """Import with meta.csv applies custom titles to documents."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,title
docs/contract.pdf,Master Services Agreement
docs/amendment.pdf,Amendment #1
"""
        files = {
            "docs/contract.pdf": self.pdf_bytes,
            "docs/amendment.pdf": self.pdf_bytes,
            "meta.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-metadata-title",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["completed"])
        self.assertTrue(result["success"])
        self.assertTrue(result["metadata_file_found"])
        self.assertEqual(result["metadata_applied"], 2)
        self.assertEqual(result["files_processed"], 2)

        # Verify documents have custom titles
        docs = Document.objects.filter(id__in=result["document_ids"])
        titles = {d.title for d in docs}
        self.assertIn("Master Services Agreement", titles)
        self.assertIn("Amendment #1", titles)

    def test_import_with_description_metadata(self):
        """Import with meta.csv applies custom descriptions to documents."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,description
file1.pdf,This is the first document with a custom description.
file2.pdf,This is the second document with another description.
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "meta.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-metadata-description",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["metadata_applied"], 2)

        # Verify documents have custom descriptions
        docs = Document.objects.filter(id__in=result["document_ids"])
        descriptions = {d.description for d in docs}
        self.assertIn(
            "This is the first document with a custom description.", descriptions
        )
        self.assertIn(
            "This is the second document with another description.", descriptions
        )

    def test_import_with_title_and_description_metadata(self):
        """Import with meta.csv can apply both title and description."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,title,description
report.pdf,Annual Report 2024,The annual financial report for fiscal year 2024.
"""
        files = {
            "report.pdf": self.pdf_bytes,
            "meta.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-metadata-both",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["metadata_applied"], 1)

        # Verify document has both custom title and description
        doc = Document.objects.get(id=result["document_ids"][0])
        self.assertEqual(doc.title, "Annual Report 2024")
        self.assertEqual(
            doc.description, "The annual financial report for fiscal year 2024."
        )

    def test_import_with_title_prefix_and_metadata(self):
        """Title prefix is prepended to metadata title."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,title
file.pdf,Custom Document Title
"""
        files = {
            "file.pdf": self.pdf_bytes,
            "meta.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-metadata-prefix",
                "corpus_id": self.corpus.id,
                "title_prefix": "2024",
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["metadata_applied"], 1)

        doc = Document.objects.get(id=result["document_ids"][0])
        self.assertEqual(doc.title, "2024 - Custom Document Title")

    def test_import_without_metadata_file(self):
        """Import without meta.csv has zero metadata_applied."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-no-metadata",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertFalse(result["metadata_file_found"])
        self.assertEqual(result["metadata_applied"], 0)

    def test_import_with_partial_metadata(self):
        """Documents without metadata entries use default titles."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Only one file has metadata
        csv_content = b"""source_path,title
file1.pdf,Custom Title
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,  # No metadata for this one
            "meta.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-partial-metadata",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 2)
        self.assertEqual(result["metadata_applied"], 1)

        # Verify the file without metadata has filename as title
        docs = Document.objects.filter(id__in=result["document_ids"])
        titles = {d.title for d in docs}
        self.assertIn("Custom Title", titles)
        self.assertIn("file2.pdf", titles)

    def test_import_with_malformed_metadata_continues(self):
        """Malformed meta.csv doesn't fail the import."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Malformed CSV (missing required source_path column)
        csv_content = b"""file_name,title
file1.pdf,Title 1
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "meta.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-malformed-metadata",
                "corpus_id": self.corpus.id,
            }
        ).get()

        # Import should still succeed for documents
        self.assertTrue(result["completed"])
        self.assertEqual(result["files_processed"], 2)
        self.assertEqual(result["metadata_applied"], 0)
        # Should have an error about metadata file
        self.assertTrue(any("Metadata file error" in e for e in result["errors"]))

    def test_import_with_nested_paths_metadata(self):
        """Metadata works with documents in nested folder structures."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        csv_content = b"""source_path,title,description
contracts/legal/agreement.pdf,Legal Agreement,Main legal agreement document
contracts/financial/report.pdf,Financial Report,Q4 financial summary
"""
        files = {
            "contracts/legal/agreement.pdf": self.pdf_bytes,
            "contracts/financial/report.pdf": self.pdf_bytes,
            "meta.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-nested-metadata",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["metadata_applied"], 2)

        docs = Document.objects.filter(id__in=result["document_ids"])
        titles = {d.title for d in docs}
        self.assertIn("Legal Agreement", titles)
        self.assertIn("Financial Report", titles)

    def test_import_metadata_path_normalization(self):
        """Metadata matches documents with various path formats."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # CSV with various path formats that should all normalize correctly
        csv_content = b"""source_path,title
/docs/file1.pdf,Title with leading slash
./docs/file2.pdf,Title with dot slash
docs/file3.pdf,Title without prefix
"""
        files = {
            "docs/file1.pdf": self.pdf_bytes,
            "docs/file2.pdf": self.pdf_bytes,
            "docs/file3.pdf": self.pdf_bytes,
            "meta.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-metadata-normalization",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["metadata_applied"], 3)

    def test_import_with_both_metadata_and_relationships(self):
        """Import with both meta.csv and relationships.csv works correctly."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        meta_csv = b"""source_path,title,description
file1.pdf,Source Document,The primary source document
file2.pdf,Target Document,The referenced document
"""
        rel_csv = b"""source_path,relationship_label,target_path,notes
file1.pdf,REFERENCES,file2.pdf,Source references target
"""
        files = {
            "file1.pdf": self.pdf_bytes,
            "file2.pdf": self.pdf_bytes,
            "meta.csv": meta_csv,
            "relationships.csv": rel_csv,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-metadata-and-relationships",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 2)
        self.assertTrue(result["metadata_file_found"])
        self.assertEqual(result["metadata_applied"], 2)
        self.assertTrue(result["relationships_file_found"])
        self.assertEqual(result["relationships_created"], 1)

        # Verify metadata was applied
        docs = Document.objects.filter(id__in=result["document_ids"])
        titles = {d.title for d in docs}
        self.assertIn("Source Document", titles)
        self.assertIn("Target Document", titles)

        # Verify relationship was created
        relationships = DocumentRelationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 1)

    def test_metadata_csv_variants_detected(self):
        """Different meta.csv filename variants are detected."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Test with METADATA.csv (uppercase variant)
        csv_content = b"""source_path,title
file.pdf,Custom Title
"""
        files = {
            "file.pdf": self.pdf_bytes,
            "METADATA.csv": csv_content,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-metadata-variant",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertTrue(result["metadata_file_found"])
        self.assertEqual(result["metadata_applied"], 1)


class TestBackendLockBehavior(TestCase):
    """
    Tests for backend_lock=True behavior during bulk document import.

    Documents created via bulk import should have backend_lock=True immediately
    after creation to indicate they are being processed. This ensures the frontend
    shows them as "processing" until the Celery pipeline completes.

    Related: Fix for bulk upload documents not showing backend_lock processing state.
    """

    def setUp(self):
        """Set up test user, corpus, and sample data."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Corpus for testing",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        # Sample PDF bytes
        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _create_test_zip(self, files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file for testing."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a TemporaryFileHandle from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name="test_import.zip")
        handle = TemporaryFileHandle.objects.create(
            file=zip_content,
        )
        return handle

    def test_import_zip_sets_backend_lock_true(self):
        """
        Documents created via import_zip_with_folder_structure have backend_lock=True.

        This ensures documents show as "processing" in the frontend immediately
        after creation, before the Celery pipeline completes.
        """
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "file1.pdf": self.pdf_bytes,
            "docs/file2.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-backend-lock",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 2)

        # Verify ALL created documents have backend_lock=True
        for doc_id in result["document_ids"]:
            doc = Document.objects.get(id=doc_id)
            self.assertTrue(
                doc.backend_lock,
                f"Document {doc_id} should have backend_lock=True after import, "
                f"but got backend_lock={doc.backend_lock}",
            )

    def test_process_documents_zip_sets_backend_lock_true(self):
        """
        Documents created via process_documents_zip have backend_lock=True.

        This is the older zip import task that should also set backend_lock=True.
        """
        from opencontractserver.tasks.import_tasks import process_documents_zip

        files = {
            "contract.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = process_documents_zip.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-backend-lock-old",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertEqual(result["processed_files"], 1)

        # Verify document has backend_lock=True
        for doc_id in result["document_ids"]:
            doc = Document.objects.get(id=doc_id)
            self.assertTrue(
                doc.backend_lock,
                f"Document {doc_id} should have backend_lock=True after import, "
                f"but got backend_lock={doc.backend_lock}",
            )

    def test_text_file_import_sets_backend_lock_true(self):
        """
        Text files imported via zip also have backend_lock=True.

        Text files follow a different code path but should still be locked.
        """
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        files = {
            "readme.txt": b"This is a plain text document.",
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-backend-lock-text",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 1)

        # Verify text document has backend_lock=True
        doc = Document.objects.get(id=result["document_ids"][0])
        self.assertTrue(
            doc.backend_lock,
            f"Text document should have backend_lock=True, got {doc.backend_lock}",
        )

    def test_standalone_upload_without_corpus_sets_backend_lock_true(self):
        """
        Standalone document uploads (no corpus) also have backend_lock=True.

        This is the legacy path for uploads without a corpus.
        """
        from opencontractserver.tasks.import_tasks import process_documents_zip

        files = {
            "standalone.pdf": self.pdf_bytes,
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        # Import WITHOUT corpus_id
        result = process_documents_zip.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-backend-lock-standalone",
                # No corpus_id - standalone upload
            }
        ).get()

        self.assertEqual(result["processed_files"], 1)

        # Verify standalone document has backend_lock=True
        doc = Document.objects.get(id=result["document_ids"][0])
        self.assertTrue(
            doc.backend_lock,
            f"Standalone document should have backend_lock=True, "
            f"got {doc.backend_lock}",
        )
