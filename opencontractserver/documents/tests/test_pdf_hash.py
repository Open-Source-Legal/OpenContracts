"""
Tests for PDF file hash functionality in Document model.
"""

import hashlib
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from opencontractserver.documents.models import Document

User = get_user_model()


class DocumentPDFHashTestCase(TestCase):
    """Test cases for PDF hash computation and management."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create a simple PDF-like bytes content for testing
        self.pdf_content = b"%PDF-1.4\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>endobj\n"
        self.pdf_hash = hashlib.sha256(self.pdf_content).hexdigest()

    def test_document_has_pdf_file_hash_field(self):
        """Test that Document model has pdf_file_hash field."""
        document = Document.objects.create(title="Test Document", creator=self.user)
        self.assertTrue(hasattr(document, "pdf_file_hash"))
        self.assertIsNone(document.pdf_file_hash)

    def test_compute_pdf_hash_with_no_file(self):
        """Test compute_pdf_hash returns None when no PDF file exists."""
        document = Document.objects.create(title="Test Document", creator=self.user)
        self.assertIsNone(document.compute_pdf_hash())

    def test_compute_pdf_hash_with_file(self):
        """Test compute_pdf_hash correctly computes SHA-256 hash."""
        pdf_file = SimpleUploadedFile(
            "test.pdf", self.pdf_content, content_type="application/pdf"
        )

        document = Document.objects.create(
            title="Test Document", creator=self.user, pdf_file=pdf_file
        )

        computed_hash = document.compute_pdf_hash()
        self.assertEqual(computed_hash, self.pdf_hash)
        self.assertEqual(len(computed_hash), 64)  # SHA-256 produces 64 hex chars

    def test_update_pdf_hash_updates_field(self):
        """Test update_pdf_hash updates the hash field when PDF changes."""
        pdf_file = SimpleUploadedFile(
            "test.pdf", self.pdf_content, content_type="application/pdf"
        )

        document = Document.objects.create(
            title="Test Document", creator=self.user, pdf_file=pdf_file
        )

        # Initially no hash
        self.assertIsNone(document.pdf_file_hash)

        # Update hash
        result = document.update_pdf_hash()
        self.assertTrue(result)

        # Reload from database to verify save
        document.refresh_from_db()
        self.assertEqual(document.pdf_file_hash, self.pdf_hash)

    def test_update_pdf_hash_no_change(self):
        """Test update_pdf_hash returns False when hash hasn't changed."""
        pdf_file = SimpleUploadedFile(
            "test.pdf", self.pdf_content, content_type="application/pdf"
        )

        document = Document.objects.create(
            title="Test Document",
            creator=self.user,
            pdf_file=pdf_file,
            pdf_file_hash=self.pdf_hash,  # Pre-set the correct hash
        )

        # Update hash - should return False as no change
        result = document.update_pdf_hash()
        self.assertFalse(result)

    def test_compute_pdf_hash_handles_large_files(self):
        """Test that compute_pdf_hash handles large files efficiently via chunking."""
        # Create a mock file that simulates a large PDF
        large_content = b"%PDF-1.4\n" + b"0" * (16 * 1024)  # 16KB of data
        expected_hash = hashlib.sha256(large_content).hexdigest()

        # Mock the chunks method to verify it's being called
        mock_file = MagicMock()
        mock_file.chunks.return_value = [
            large_content[i : i + 8192] for i in range(0, len(large_content), 8192)
        ]

        document = Document.objects.create(title="Test Document", creator=self.user)
        document.pdf_file = mock_file

        computed_hash = document.compute_pdf_hash()
        self.assertEqual(computed_hash, expected_hash)
        mock_file.chunks.assert_called_once_with(chunk_size=8192)

    def test_pdf_file_hash_field_indexed(self):
        """Test that pdf_file_hash field is indexed for efficient lookups."""
        # This is more of a migration test, but we can verify the field properties
        field = Document._meta.get_field("pdf_file_hash")
        self.assertTrue(field.db_index)
        self.assertEqual(field.max_length, 64)
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
