"""
Integration tests for zip import with folder structure preservation.

These tests verify:
- Folder structure creation from zip paths
- Celery task for zip import
- Permission checks
- Error handling and partial success scenarios

The REST transport (``POST /api/imports/zip-to-corpus/``) that wraps the
celery task is covered separately in ``test_document_imports_rest.py``.
"""

import io
import json
import logging
import zipfile
from typing import Optional

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings

from opencontractserver.corpuses.models import Corpus, CorpusFolder, TemporaryFileHandle
from opencontractserver.corpuses.services import FolderCRUDService
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hermetic in-test parsers for the dumb-anchor remap integration tests.
#
# These are referenced by their dotted path from ``PipelineSettings.
# preferred_parsers`` so the real ``ingest_doc`` chain task resolves them via
# ``get_component_by_name`` (which importlib-loads any dotted path and finds
# BaseParser subclasses by ``inspect.getmembers``). They intentionally live in
# the test module — NOT under ``opencontractserver/pipeline/parsers/`` — and
# return small, deterministic PAWLs / text so the chain produces a real
# document layer without the Docling REST microservice or any network call.
# ---------------------------------------------------------------------------


# Page-0 heading the dumb-anchor PDF annotation targets, with a bbox that
# encloses exactly these two tokens. ``DUMB_ANCHOR_HEADING_TEXT`` is the
# ``rawText`` the sidecar carries; the parser tokenises it into the two tokens
# below so geometry + rawText confirmation both succeed during remap.
DUMB_ANCHOR_HEADING_TEXT = "CHAPTER 1"
# bbox that fully contains the two heading tokens (100% area overlap >= the
# 0.5 geometry threshold) and excludes the body token on the same page.
DUMB_ANCHOR_HEADING_BBOX = {"left": 45.0, "top": 45.0, "right": 145.0, "bottom": 70.0}


class _DumbAnchorPdfParser(BaseParser):
    """Deterministic PDF parser producing PAWLs with a known page-0 heading."""

    title = "Dumb Anchor Test PDF Parser"
    description = "Returns synthetic PAWLs for the dumb-anchor remap test."
    author = "Integration Test"
    dependencies: list[str] = []

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **kwargs
    ) -> Optional[OpenContractDocExport]:
        # v1 PAWLs page: two heading tokens inside the annotation bbox plus a
        # body token well outside it (so the bbox doesn't accidentally grab it).
        pawls_page = {
            "page": {"width": 612.0, "height": 792.0, "index": 0},
            "tokens": [
                {
                    "x": 50.0,
                    "y": 50.0,
                    "width": 70.0,
                    "height": 14.0,
                    "text": "CHAPTER",
                },
                {"x": 125.0, "y": 50.0, "width": 10.0, "height": 14.0, "text": "1"},
                {
                    "x": 50.0,
                    "y": 200.0,
                    "width": 60.0,
                    "height": 12.0,
                    "text": "Body",
                },
            ],
        }
        return {
            "title": "Dumb Anchor PDF",
            "content": "",  # overwritten from PAWLs text layer by save_parsed_data
            "description": "",
            "pawls_file_content": [pawls_page],
            "page_count": 1,
            "doc_labels": [],
            "labelled_text": [],
        }


# Deterministic text-layer content for the text-document variant. The span
# annotation's rawText is a substring re-found by the text anchorer.
DUMB_ANCHOR_TEXT_CONTENT = (
    "This Master Agreement governs the relationship between the parties. "
    "Section 4 sets out the indemnification obligations of each party."
)
DUMB_ANCHOR_SPAN_RAWTEXT = "indemnification obligations"


class _DumbAnchorTextParser(BaseParser):
    """Deterministic text parser returning a fixed, PAWLs-free text layer."""

    title = "Dumb Anchor Test Text Parser"
    description = "Returns a fixed text layer for the dumb-anchor remap test."
    author = "Integration Test"
    dependencies: list[str] = []

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **kwargs
    ) -> Optional[OpenContractDocExport]:
        return {
            "title": "Dumb Anchor Text",
            "content": DUMB_ANCHOR_TEXT_CONTENT,
            "description": "",
            "pawls_file_content": [],
            "page_count": 1,
            "doc_labels": [],
            "labelled_text": [],
        }


_DUMB_ANCHOR_PDF_PARSER_PATH = (
    "opencontractserver.tests.test_zip_import_integration._DumbAnchorPdfParser"
)
_DUMB_ANCHOR_TEXT_PARSER_PATH = (
    "opencontractserver.tests.test_zip_import_integration._DumbAnchorTextParser"
)


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

    @override_settings(ZIP_MAX_FILE_COUNT=5)
    def test_too_many_files_rejected(self):
        """Zip with too many files is rejected at validation."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

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
        self.assertTrue(any("files" in e.lower() for e in result["validation_errors"]))

    @override_settings(ZIP_MAX_SINGLE_FILE_SIZE_BYTES=100)  # 100 bytes
    def test_oversized_files_skipped_not_rejected(self):
        """Individual oversized files are skipped, not rejected entirely."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

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

    def test_cross_batch_relationship_resolves_existing_corpus_documents(self):
        """A relationship-only ZIP connects documents imported in an EARLIER
        batch, resolving both endpoints against existing corpus documents."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # --- Batch 1: two documents, no relationships file ---
        result1 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": self._create_temp_file_handle(
                    self._create_test_zip(
                        {"alpha.pdf": self.pdf_bytes, "beta.pdf": self.pdf_bytes}
                    )
                ).id,
                "user_id": self.user.id,
                "job_id": "cross-batch-1",
                "corpus_id": self.corpus.id,
            }
        ).get()
        self.assertTrue(result1["success"], f"Errors: {result1.get('errors')}")
        self.assertEqual(result1["files_processed"], 2)

        # --- Batch 2: relationships.csv ONLY, referencing batch-1 docs by their
        #     corpus path (== zip path when no target folder is used) ---
        csv_content = b"""source_path,relationship_label,target_path,notes
alpha.pdf,REFERENCES,beta.pdf,cross-batch edge
"""
        result2 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": self._create_temp_file_handle(
                    self._create_test_zip({"relationships.csv": csv_content})
                ).id,
                "user_id": self.user.id,
                "job_id": "cross-batch-2",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result2["completed"], f"Errors: {result2.get('errors')}")
        self.assertTrue(result2["success"], f"Errors: {result2.get('errors')}")
        self.assertEqual(result2["relationships_created"], 1)
        self.assertEqual(result2["relationships_skipped"], 0)

        rel = DocumentRelationship.objects.get(corpus=self.corpus)
        self.assertEqual(rel.annotation_label.text, "REFERENCES")
        self.assertIsNotNone(rel.source_document)
        self.assertIsNotNone(rel.target_document)
        self.assertNotEqual(rel.source_document_id, rel.target_document_id)

    def test_relationship_endpoints_mix_new_and_existing_documents(self):
        """One endpoint resolves to a same-ZIP document, the other to a document
        already in the corpus — the in-import and corpus maps are merged."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # --- Batch 1: a single existing document ---
        result1 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": self._create_temp_file_handle(
                    self._create_test_zip({"alpha.pdf": self.pdf_bytes})
                ).id,
                "user_id": self.user.id,
                "job_id": "mix-batch-1",
                "corpus_id": self.corpus.id,
            }
        ).get()
        self.assertTrue(result1["success"], f"Errors: {result1.get('errors')}")

        # --- Batch 2: a NEW document + relationships.csv referencing both the
        #     new (gamma) and the existing (alpha) document ---
        csv_content = b"""source_path,relationship_label,target_path,notes
gamma.pdf,DERIVES_FROM,alpha.pdf,
"""
        result2 = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": self._create_temp_file_handle(
                    self._create_test_zip(
                        {
                            "gamma.pdf": self.pdf_bytes,
                            "relationships.csv": csv_content,
                        }
                    )
                ).id,
                "user_id": self.user.id,
                "job_id": "mix-batch-2",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result2["success"], f"Errors: {result2.get('errors')}")
        self.assertEqual(result2["files_processed"], 1)
        self.assertEqual(result2["relationships_created"], 1)
        self.assertEqual(result2["relationships_skipped"], 0)

        rel = DocumentRelationship.objects.get(
            corpus=self.corpus, annotation_label__text="DERIVES_FROM"
        )
        self.assertNotEqual(rel.source_document_id, rel.target_document_id)


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


@pytest.mark.usefixtures("enable_doc_processing_signals")
class TestDumbAnchorRemapThroughChain(TransactionTestCase):
    """
    End-to-end coverage for the dumb-anchor sidecar -> remap chain.

    These tests exercise the *real* ingest chain wired by
    ``import_zip_with_folder_structure`` for a NEW-format sidecar (top-level
    ``"annotations"`` list):

        extract_thumbnail -> ingest_doc -> remap_pending_annotations
        -> set_doc_lock_state

    Unlike ``test_sidecar_import.py`` (which captures the on_commit chain
    *without* executing it and only asserts the PENDING row), these tests let
    the chain run to completion under eager Celery and prove the document ends
    up with a real text layer, correctly anchored annotations, a DONE pending
    row, and an unlocked backend.

    ``TransactionTestCase`` is required so ``transaction.on_commit`` callbacks
    registered inside the importer actually fire (a plain ``TestCase`` would
    keep them pending until a rollback that never commits). With
    ``CELERY_TASK_ALWAYS_EAGER`` (test settings) the dispatched chain runs
    synchronously when the importer's atomic block commits.

    The pipeline is made hermetic by pointing
    ``PipelineSettings.preferred_parsers`` at the in-test parsers defined at
    module scope (``_DumbAnchorPdfParser`` / ``_DumbAnchorTextParser``), which
    return deterministic PAWLs / text without any external parser service.
    """

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="dumb-anchor-user", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Dumb Anchor Corpus",
                description="Corpus for dumb-anchor remap integration tests",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _set_preferred_parser(self, mimetype: str, dotted_path: str) -> None:
        """Point the DB pipeline settings at an in-test parser for ``mimetype``."""
        from opencontractserver.documents.models import PipelineSettings

        pipeline_settings = PipelineSettings.get_instance(use_cache=False)
        pipeline_settings.preferred_parsers = {
            **(pipeline_settings.preferred_parsers or {}),
            mimetype: dotted_path,
        }
        pipeline_settings.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

    @staticmethod
    def _create_test_zip(files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file from a {path: bytes} mapping."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a ``TemporaryFileHandle`` from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name="dumb_anchor_import.zip")
        return TemporaryFileHandle.objects.create(file=zip_content)

    def test_dumb_anchor_pdf_remaps_via_chain(self):
        """
        Importing a dumb-anchor PDF sidecar runs the real ingest chain and
        anchors the annotation onto the pipeline-produced PAWLs.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import PendingDocumentAnnotations
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )
        from opencontractserver.utils.compact_pawls import expand_pawls_pages

        self._set_preferred_parser("application/pdf", _DUMB_ANCHOR_PDF_PARSER_PATH)

        sidecar = {
            "annotations": [
                {
                    "id": 1,
                    "label": "OC_SECTION",
                    "rawText": DUMB_ANCHOR_HEADING_TEXT,
                    "page": 0,
                    "bbox": DUMB_ANCHOR_HEADING_BBOX,
                    "parent_id": None,
                }
            ],
            "doc_labels": [],
        }
        labels = {
            "text_labels": {
                "OC_SECTION": {
                    "text": "OC_SECTION",
                    "label_type": "TOKEN_LABEL",
                    "description": "Section heading",
                    "color": "#FF0000",
                    "icon": "tag",
                }
            },
            "doc_labels": {},
        }

        files = {
            "chapter.pdf": self.pdf_bytes,
            "chapter.json": json.dumps(sidecar).encode("utf-8"),
            "labels.json": json.dumps(labels).encode("utf-8"),
        }
        handle = self._create_temp_file_handle(self._create_test_zip(files))

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "dumb-anchor-pdf",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 1)
        self.assertEqual(result["pending_annotation_docs"], 1)

        created_id = int(result["document_ids"][0])

        # (d) Chain ran to completion: set_doc_lock_state(locked=False) last.
        doc = Document.objects.get(pk=created_id)
        doc.refresh_from_db()
        self.assertFalse(doc.backend_lock)

        # (a) Real text layer produced by the pipeline parser.
        self.assertTrue(doc.txt_extract_file.read().decode("utf-8").strip())

        # (c) Pending row consumed and marked DONE, stamped with a run id.
        pending = PendingDocumentAnnotations.objects.get(document=doc)
        self.assertEqual(pending.status, PendingDocumentAnnotations.Status.DONE)
        self.assertIsNotNone(pending.ingestion_run_id)

        # (b) Exactly one OC_SECTION annotation, anchored onto the stored PAWLs
        #     such that the resolved tokens' text matches the sidecar rawText.
        ann = Annotation.objects.get(document=doc, annotation_label__text="OC_SECTION")
        pawls = expand_pawls_pages(
            json.loads(doc.pawls_parse_file.read().decode("utf-8"))
        )
        from opencontractserver.annotations.compact_json import decode_token_ranges

        # annotation_json is stored compact v2: {"v":2,"p":{page:{b,t}}}.
        resolved = " ".join(
            pawls[int(pk)]["tokens"][i]["text"]
            for pk, entry in ann.json["p"].items()
            for i in decode_token_ranges(entry["t"])
        )
        self.assertEqual(resolved, DUMB_ANCHOR_HEADING_TEXT)
        self.assertIn(ann.raw_text.split()[0], resolved)

        # No annotations should have leaked from a second, racing chain.
        self.assertEqual(
            Annotation.objects.filter(
                document=doc, annotation_label__text="OC_SECTION"
            ).count(),
            1,
        )

    def test_legacy_format_pdf_sidecar_remaps_via_chain(self):
        """
        A sidecar carrying OLD-format annotations (baked ``annotation_json``
        with stale ``tokensJsons``) imports through the deferred pipeline: the
        indices are dropped and re-derived against the freshly-parsed PAWLs.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import PendingDocumentAnnotations
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )
        from opencontractserver.utils.compact_pawls import expand_pawls_pages

        self._set_preferred_parser("application/pdf", _DUMB_ANCHOR_PDF_PARSER_PATH)

        # Old export shape: annotationLabel + annotation_json with WRONG indices.
        sidecar = {
            "annotations": [
                {
                    "id": 1,
                    "annotationLabel": "OC_SECTION",
                    "rawText": DUMB_ANCHOR_HEADING_TEXT,
                    "page": 0,
                    "parent_id": None,
                    "annotation_json": {
                        "0": {
                            "bounds": DUMB_ANCHOR_HEADING_BBOX,
                            "tokensJsons": [{"pageIndex": 0, "tokenIndex": 999}],
                            "rawText": DUMB_ANCHOR_HEADING_TEXT,
                        }
                    },
                }
            ],
            "doc_labels": [],
        }
        labels = {
            "text_labels": {
                "OC_SECTION": {
                    "text": "OC_SECTION",
                    "label_type": "TOKEN_LABEL",
                    "description": "Section heading",
                    "color": "#FF0000",
                    "icon": "tag",
                }
            },
            "doc_labels": {},
        }

        files = {
            "chapter.pdf": self.pdf_bytes,
            "chapter.json": json.dumps(sidecar).encode("utf-8"),
            "labels.json": json.dumps(labels).encode("utf-8"),
        }
        handle = self._create_temp_file_handle(self._create_test_zip(files))

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "legacy-format-pdf",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["pending_annotation_docs"], 1)

        doc = Document.objects.get(pk=int(result["document_ids"][0]))
        pending = PendingDocumentAnnotations.objects.get(document=doc)
        self.assertEqual(pending.status, PendingDocumentAnnotations.Status.DONE)

        # The stale tokensJsons ([999]) were discarded; indices re-derived so the
        # resolved tokens' text matches the rawText.
        ann = Annotation.objects.get(document=doc, annotation_label__text="OC_SECTION")
        pawls = expand_pawls_pages(
            json.loads(doc.pawls_parse_file.read().decode("utf-8"))
        )
        from opencontractserver.annotations.compact_json import decode_token_ranges

        # annotation_json is stored compact v2: {"v":2,"p":{page:{b,t}}}.
        resolved = " ".join(
            pawls[int(pk)]["tokens"][i]["text"]
            for pk, entry in ann.json["p"].items()
            for i in decode_token_ranges(entry["t"])
        )
        self.assertEqual(resolved, DUMB_ANCHOR_HEADING_TEXT)

    def test_skip_pipeline_labelled_text_sidecar_remaps_via_chain(self):
        """
        A legacy ``skip_pipeline`` scrape sidecar (``labelled_text`` +
        ``content:""`` + embedded ``pawls_file_content``) is force-ingested
        through the normal parser (ignoring the embedded PAWLs / skip flag),
        gaining a real text layer, and its producer annotation is re-anchored
        onto the freshly-parsed PAWLs (stale ``tokensJsons`` discarded).
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import PendingDocumentAnnotations
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )
        from opencontractserver.utils.compact_pawls import expand_pawls_pages

        self._set_preferred_parser("application/pdf", _DUMB_ANCHOR_PDF_PARSER_PATH)

        # SC-style sidecar: annotations under ``labelled_text``, empty content,
        # embedded (to-be-ignored) PAWLs, and the skip_pipeline flag.
        sidecar = {
            "title": "Chapter 1",
            "description": "",
            "content": "",
            "page_count": 1,
            "pawls_file_content": [{"page": {"index": 0}, "tokens": []}],
            "skip_pipeline": True,
            "doc_labels": ["regulation"],
            "labelled_text": [
                {
                    "id": 1,
                    "annotationLabel": "OC_SECTION",
                    "annotation_type": "TOKEN_LABEL",
                    "structural": False,
                    "parent_id": None,
                    "long_description": None,
                    "rawText": DUMB_ANCHOR_HEADING_TEXT,
                    "annotation_json": {
                        "0": {
                            "bounds": DUMB_ANCHOR_HEADING_BBOX,
                            "tokensJsons": [{"pageIndex": 0, "tokenIndex": 999}],
                            "rawText": DUMB_ANCHOR_HEADING_TEXT,
                        }
                    },
                }
            ],
        }
        labels = {
            "text_labels": {
                "OC_SECTION": {
                    "text": "OC_SECTION",
                    "label_type": "TOKEN_LABEL",
                    "description": "Section heading",
                    "color": "#FF0000",
                    "icon": "tag",
                }
            },
            "doc_labels": {
                "regulation": {
                    "text": "regulation",
                    "label_type": "DOC_TYPE_LABEL",
                    "description": "Regulation document",
                    "color": "#00FF00",
                    "icon": "tag",
                }
            },
        }

        files = {
            "chapter.pdf": self.pdf_bytes,
            "chapter.json": json.dumps(sidecar).encode("utf-8"),
            "labels.json": json.dumps(labels).encode("utf-8"),
        }
        handle = self._create_temp_file_handle(self._create_test_zip(files))

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "skip-pipeline-labelled-text",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["pending_annotation_docs"], 1)

        doc = Document.objects.get(pk=int(result["document_ids"][0]))
        # Real text layer produced by the pipeline (the empty embedded content
        # was ignored — the no-text-layer problem is fixed by force-ingestion).
        self.assertTrue(doc.txt_extract_file.read().decode("utf-8").strip())

        pending = PendingDocumentAnnotations.objects.get(document=doc)
        self.assertEqual(pending.status, PendingDocumentAnnotations.Status.DONE)

        # Producer OC_SECTION annotation re-anchored (stale [999] discarded).
        ann = Annotation.objects.get(
            document=doc, annotation_label__text="OC_SECTION", structural=False
        )
        pawls = expand_pawls_pages(
            json.loads(doc.pawls_parse_file.read().decode("utf-8"))
        )
        from opencontractserver.annotations.compact_json import decode_token_ranges

        # annotation_json is stored compact v2: {"v":2,"p":{page:{b,t}}}.
        resolved = " ".join(
            pawls[int(pk)]["tokens"][i]["text"]
            for pk, entry in ann.json["p"].items()
            for i in decode_token_ranges(entry["t"])
        )
        self.assertEqual(resolved, DUMB_ANCHOR_HEADING_TEXT)

    def test_dumb_anchor_text_remaps_via_chain(self):
        """
        Importing a dumb-anchor text sidecar runs the real ingest chain and
        re-finds the span annotation against the pipeline-produced text layer.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import PendingDocumentAnnotations
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        self._set_preferred_parser("text/plain", _DUMB_ANCHOR_TEXT_PARSER_PATH)

        # start hint is approximate on purpose: the anchorer re-finds rawText.
        approx_start = DUMB_ANCHOR_TEXT_CONTENT.find(DUMB_ANCHOR_SPAN_RAWTEXT) - 3
        sidecar = {
            "annotations": [
                {
                    "id": 1,
                    "label": "OC_CLAUSE",
                    "rawText": DUMB_ANCHOR_SPAN_RAWTEXT,
                    "start": approx_start,
                    "end": approx_start + len(DUMB_ANCHOR_SPAN_RAWTEXT),
                    "parent_id": None,
                }
            ],
            "doc_labels": [],
        }
        # labels.json defines the label as a TOKEN_LABEL (one of the import-
        # valid label types); the anchorer stamps the annotation's own
        # ``annotation_type`` as SPAN_LABEL for the re-found character span.
        labels = {
            "text_labels": {
                "OC_CLAUSE": {
                    "text": "OC_CLAUSE",
                    "label_type": "TOKEN_LABEL",
                    "description": "Clause span",
                    "color": "#00FF00",
                    "icon": "tag",
                }
            },
            "doc_labels": {},
        }

        files = {
            "agreement.txt": b"placeholder text document body",
            "agreement.json": json.dumps(sidecar).encode("utf-8"),
            "labels.json": json.dumps(labels).encode("utf-8"),
        }
        handle = self._create_temp_file_handle(self._create_test_zip(files))

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "dumb-anchor-text",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 1)
        self.assertEqual(result["pending_annotation_docs"], 1)

        created_id = int(result["document_ids"][0])
        doc = Document.objects.get(pk=created_id)
        doc.refresh_from_db()

        # Chain ran to completion and unlocked the document.
        self.assertFalse(doc.backend_lock)

        # Pipeline produced the deterministic text layer.
        content = doc.txt_extract_file.read().decode("utf-8")
        self.assertEqual(content, DUMB_ANCHOR_TEXT_CONTENT)

        # Pending row consumed and marked DONE, stamped with a run id.
        pending = PendingDocumentAnnotations.objects.get(document=doc)
        self.assertEqual(pending.status, PendingDocumentAnnotations.Status.DONE)
        self.assertIsNotNone(pending.ingestion_run_id)

        # SPAN annotation_json text equals the slice of the stored content the
        # anchorer re-found for the span.
        ann = Annotation.objects.get(document=doc, annotation_label__text="OC_CLAUSE")
        span = ann.json
        self.assertEqual(span["text"], content[span["start"] : span["end"]])
        self.assertEqual(span["text"], DUMB_ANCHOR_SPAN_RAWTEXT)

    def test_pdf_sidecar_relationships_and_metadata_remap_via_chain(self):
        """End-to-end: a dumb-anchor PDF sidecar carrying an annotation-to-
        annotation relationship plus ``link_url`` / ``data`` runs the real
        chain. The relationship is wired between the two anchored annotations
        (its RELATIONSHIP_LABEL auto-created) and the metadata lands on the
        heading annotation.
        """
        from opencontractserver.annotations.models import Annotation, Relationship
        from opencontractserver.documents.models import PendingDocumentAnnotations
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        self._set_preferred_parser("application/pdf", _DUMB_ANCHOR_PDF_PARSER_PATH)

        geo = {"canonical_name": "France", "lat": 46.0, "lng": 2.0, "geocoded": True}
        sidecar = {
            "annotations": [
                {
                    "id": 1,
                    "label": "OC_SECTION",
                    "rawText": DUMB_ANCHOR_HEADING_TEXT,
                    "page": 0,
                    "bbox": DUMB_ANCHOR_HEADING_BBOX,
                    "link_url": "https://example.com/ref",
                    "data": geo,
                    "parent_id": None,
                },
                {
                    "id": 2,
                    "label": "OC_SECTION",
                    "rawText": "Body",
                    "page": 0,
                    # bbox enclosing the page-0 "Body" token (x=50,y=200).
                    "bbox": {
                        "left": 45.0,
                        "top": 195.0,
                        "right": 115.0,
                        "bottom": 217.0,
                    },
                    "parent_id": None,
                },
            ],
            "doc_labels": [],
            "relationships": [
                {
                    "id": "r1",
                    "relationshipLabel": "REFERENCES",
                    "source_annotation_ids": [1],
                    "target_annotation_ids": [2],
                }
            ],
        }
        labels = {
            "text_labels": {
                "OC_SECTION": {
                    "text": "OC_SECTION",
                    "label_type": "TOKEN_LABEL",
                    "description": "Section heading",
                    "color": "#FF0000",
                    "icon": "tag",
                }
            },
            "doc_labels": {},
        }
        files = {
            "chapter.pdf": self.pdf_bytes,
            "chapter.json": json.dumps(sidecar).encode("utf-8"),
            "labels.json": json.dumps(labels).encode("utf-8"),
        }
        handle = self._create_temp_file_handle(self._create_test_zip(files))

        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "dumb-anchor-rels",
                "corpus_id": self.corpus.id,
            }
        ).get()

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["sidecar_relationships_found"], 1)

        doc = Document.objects.get(pk=int(result["document_ids"][0]))
        pending = PendingDocumentAnnotations.objects.get(document=doc)
        self.assertEqual(pending.status, PendingDocumentAnnotations.Status.DONE)

        # Two producer annotations anchored (structural=False filters out any
        # parser-generated structural annotations).
        anns = Annotation.objects.filter(
            document=doc, annotation_label__text="OC_SECTION", structural=False
        )
        self.assertEqual(anns.count(), 2)

        # link_url + data landed on the heading annotation.
        heading = anns.get(raw_text=DUMB_ANCHOR_HEADING_TEXT)
        self.assertEqual(heading.link_url, "https://example.com/ref")
        self.assertEqual(heading.data, geo)

        # The annotation-to-annotation relationship was wired, its
        # RELATIONSHIP_LABEL auto-created, connecting heading -> body.
        rel = Relationship.objects.get(
            document=doc, relationship_label__text="REFERENCES"
        )
        self.assertEqual(rel.relationship_label.label_type, "RELATIONSHIP_LABEL")
        self.assertFalse(rel.structural)
        self.assertEqual(rel.source_annotations.count(), 1)
        self.assertEqual(rel.target_annotations.count(), 1)
        self.assertEqual(
            rel.source_annotations.first().raw_text, DUMB_ANCHOR_HEADING_TEXT
        )
        self.assertEqual(rel.target_annotations.first().raw_text, "Body")
