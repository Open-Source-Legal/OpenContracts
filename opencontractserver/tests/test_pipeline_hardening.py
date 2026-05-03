"""
Tests for pipeline hardening: graceful transient failure handling.

These tests verify:
1. DocumentParsingError exception with is_transient flag
2. _mark_document_failed helper function
3. retry_document_processing task
4. Document processing status transitions
5. GraphQL RetryDocumentProcessing mutation
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.documents.models import Document, DocumentProcessingStatus
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.tasks.doc_tasks import (
    _mark_document_failed,
    retry_document_processing,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestDocumentParsingError(TestCase):
    """Tests for the DocumentParsingError exception class."""

    def test_transient_error_default(self):
        """Test that is_transient defaults to True."""
        error = DocumentParsingError("Test error")
        self.assertTrue(error.is_transient)
        self.assertEqual(str(error), "Test error")

    def test_transient_error_explicit_true(self):
        """Test explicit is_transient=True."""
        error = DocumentParsingError("Network timeout", is_transient=True)
        self.assertTrue(error.is_transient)

    def test_permanent_error(self):
        """Test is_transient=False for permanent errors."""
        error = DocumentParsingError("Invalid file format", is_transient=False)
        self.assertFalse(error.is_transient)

    def test_error_inheritance(self):
        """Test that DocumentParsingError is a proper Exception subclass."""
        error = DocumentParsingError("Test")
        self.assertIsInstance(error, Exception)


class TestMarkDocumentFailed(TestCase):
    """Tests for the _mark_document_failed helper function."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="12345678"
            )

        self.doc = Document.objects.create(
            title="Test Document",
            description="Test Description",
            file_type="application/pdf",
            creator=self.user,
            backend_lock=True,
            processing_status=DocumentProcessingStatus.PROCESSING,
        )

    def test_marks_document_as_failed(self):
        """Test that _mark_document_failed sets status to FAILED."""
        _mark_document_failed(self.doc, "Test error", create_notification=False)
        self.doc.refresh_from_db()

        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.FAILED)

    def test_keeps_document_locked(self):
        """Test that _mark_document_failed keeps backend_lock=True."""
        _mark_document_failed(self.doc, "Test error", create_notification=False)
        self.doc.refresh_from_db()

        self.assertTrue(self.doc.backend_lock)

    def test_stores_error_message(self):
        """Test that error message is stored."""
        error_msg = "Parser service returned 500 error"
        _mark_document_failed(self.doc, error_msg, create_notification=False)
        self.doc.refresh_from_db()

        self.assertEqual(self.doc.processing_error, error_msg)

    def test_stores_traceback(self):
        """Test that traceback is stored."""
        error_msg = "Test error"
        traceback_str = "Traceback (most recent call last):\n  File ..."
        _mark_document_failed(
            self.doc, error_msg, traceback_str, create_notification=False
        )
        self.doc.refresh_from_db()

        self.assertEqual(self.doc.processing_error_traceback, traceback_str)

    def test_truncates_long_error_message(self):
        """Test that very long error messages are truncated."""
        long_error = "x" * 10000  # Exceeds MAX_ERROR_LENGTH
        _mark_document_failed(self.doc, long_error, create_notification=False)
        self.doc.refresh_from_db()

        self.assertLessEqual(len(self.doc.processing_error), 5000)

    def test_truncates_long_traceback(self):
        """Test that very long tracebacks are truncated."""
        long_traceback = "x" * 20000  # Exceeds MAX_TRACEBACK_LENGTH
        _mark_document_failed(
            self.doc, "error", long_traceback, create_notification=False
        )
        self.doc.refresh_from_db()

        self.assertLessEqual(len(self.doc.processing_error_traceback), 10000)

    def test_sets_processing_finished(self):
        """Test that processing_finished timestamp is set."""
        _mark_document_failed(self.doc, "Test error", create_notification=False)
        self.doc.refresh_from_db()

        self.assertIsNotNone(self.doc.processing_finished)

    def test_creates_failure_notification(self):
        """Test that a failure notification is created when requested."""
        # Delete any existing notifications
        Notification.objects.filter(recipient=self.user).delete()

        _mark_document_failed(self.doc, "Test error", create_notification=True)

        notification = Notification.objects.filter(
            recipient=self.user,
            notification_type=NotificationTypeChoices.DOCUMENT_PROCESSING_FAILED,
        ).first()

        self.assertIsNotNone(notification)
        self.assertEqual(notification.data["document_id"], self.doc.id)

    def test_no_notification_when_disabled(self):
        """Test that no notification is created when create_notification=False."""
        # Delete any existing notifications
        Notification.objects.filter(recipient=self.user).delete()

        _mark_document_failed(self.doc, "Test error", create_notification=False)

        notification_count = Notification.objects.filter(
            recipient=self.user,
            notification_type=NotificationTypeChoices.DOCUMENT_PROCESSING_FAILED,
        ).count()

        self.assertEqual(notification_count, 0)


class TestRetryDocumentProcessing(TestCase):
    """Tests for the retry_document_processing task."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="12345678"
            )

        self.doc = Document.objects.create(
            title="Test Document",
            description="Test Description",
            file_type="application/pdf",
            creator=self.user,
            backend_lock=True,
            processing_status=DocumentProcessingStatus.FAILED,
            processing_error="Previous error",
            processing_error_traceback="Previous traceback",
        )
        # T-7 (#1463) defense-in-depth requires explicit guardian UPDATE
        # permission for retries; production upload mutations grant CRUD
        # to the uploader, so we mirror that here.
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])

        # Create a mock PDF file for the document
        pdf_content = b"%PDF-1.7\n%%EOF\n"
        self.doc.pdf_file.save("test.pdf", ContentFile(pdf_content))

    @patch("celery.chain")
    def test_resets_failed_document_state(self, mock_chain):
        """Test that retry_document_processing resets the document state."""
        mock_chain_instance = MagicMock()
        mock_chain.return_value = mock_chain_instance

        result = retry_document_processing(user_id=self.user.id, doc_id=self.doc.id)

        self.doc.refresh_from_db()

        self.assertEqual(result["status"], "queued")
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.PENDING)
        self.assertEqual(self.doc.processing_error, "")
        self.assertEqual(self.doc.processing_error_traceback, "")
        self.assertIsNotNone(self.doc.processing_started)
        self.assertIsNone(self.doc.processing_finished)

    @patch("celery.chain")
    def test_triggers_pipeline_chain(self, mock_chain):
        """Test that retry_document_processing triggers the processing pipeline."""
        mock_chain_instance = MagicMock()
        mock_chain.return_value = mock_chain_instance

        retry_document_processing(user_id=self.user.id, doc_id=self.doc.id)

        mock_chain.assert_called_once()
        mock_chain_instance.apply_async.assert_called_once()

    def test_rejects_non_failed_document(self):
        """Test that retry_document_processing rejects documents not in FAILED state."""
        self.doc.processing_status = DocumentProcessingStatus.COMPLETED
        self.doc.save()

        result = retry_document_processing(user_id=self.user.id, doc_id=self.doc.id)

        self.assertEqual(result["status"], "error")
        self.assertIn("not in failed state", result["message"])

    def test_handles_nonexistent_document(self):
        """Test that retry_document_processing handles nonexistent documents."""
        result = retry_document_processing(user_id=self.user.id, doc_id=99999)

        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["message"])


class TestDocumentProcessingStatusTransitions(TestCase):
    """Tests for document processing status transitions."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="12345678"
            )

        self.doc = Document.objects.create(
            title="Test Document",
            description="Test Description",
            file_type="application/pdf",
            creator=self.user,
        )

    def test_default_status_is_pending(self):
        """Test that new documents have PENDING status."""
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.PENDING)

    def test_status_choices_are_valid(self):
        """Test that all status choices are valid."""
        valid_statuses = [choice[0] for choice in DocumentProcessingStatus.choices]

        self.assertIn("pending", valid_statuses)
        self.assertIn("processing", valid_statuses)
        self.assertIn("completed", valid_statuses)
        self.assertIn("failed", valid_statuses)

    def test_processing_error_field_defaults(self):
        """Test that processing error fields default to empty strings."""
        self.assertEqual(self.doc.processing_error, "")
        self.assertEqual(self.doc.processing_error_traceback, "")


class TestDoclingParserExceptions(TestCase):
    """Tests for Docling parser exception handling."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="12345678"
            )

        self.doc = Document.objects.create(
            title="Test Document",
            description="Test Description",
            file_type="application/pdf",
            creator=self.user,
        )

        # Create a mock PDF file
        pdf_content = b"%PDF-1.7\n%%EOF\n"
        self.doc.pdf_file.save("test.pdf", ContentFile(pdf_content))

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage")
    def test_timeout_raises_transient_error(
        self, mock_storage, mock_post, _mock_page_count
    ):
        """Test that timeout errors raise transient DocumentParsingError."""
        from requests.exceptions import Timeout

        from opencontractserver.pipeline.parsers.docling_parser_rest import (
            DoclingParser,
        )

        mock_post.side_effect = Timeout("Connection timed out")
        mock_storage.open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=b"%PDF-1.7\n%%EOF\n"))
        )
        mock_storage.open.return_value.__exit__ = MagicMock(return_value=False)

        parser = DoclingParser()
        parser.chunk_retry_limit = 0

        with self.assertRaises(DocumentParsingError) as context:
            parser.parse_document(self.user.id, self.doc.id)

        self.assertTrue(context.exception.is_transient)

    @patch(
        "opencontractserver.pipeline.base.chunked_parser.get_pdf_page_count",
        return_value=1,
    )
    @patch("opencontractserver.pipeline.parsers.docling_parser_rest.requests.post")
    @patch("opencontractserver.pipeline.base.chunked_parser.default_storage")
    def test_connection_error_raises_transient_error(
        self, mock_storage, mock_post, _mock_page_count
    ):
        """Test that connection errors raise transient DocumentParsingError."""
        from requests.exceptions import ConnectionError

        from opencontractserver.pipeline.parsers.docling_parser_rest import (
            DoclingParser,
        )

        mock_post.side_effect = ConnectionError("Failed to connect")
        mock_storage.open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=b"%PDF-1.7\n%%EOF\n"))
        )
        mock_storage.open.return_value.__exit__ = MagicMock(return_value=False)

        parser = DoclingParser()
        parser.chunk_retry_limit = 0

        with self.assertRaises(DocumentParsingError) as context:
            parser.parse_document(self.user.id, self.doc.id)

        self.assertTrue(context.exception.is_transient)


class TestSetDocLockStateWithFailedDocuments(TestCase):
    """Tests for set_doc_lock_state behavior with failed documents."""

    def setUp(self):
        """Set up test environment."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="12345678"
            )

        self.doc = Document.objects.create(
            title="Test Document",
            description="Test Description",
            file_type="application/pdf",
            creator=self.user,
            backend_lock=True,
            processing_status=DocumentProcessingStatus.FAILED,
        )

    def test_keeps_failed_document_locked(self):
        """Test that set_doc_lock_state keeps failed documents locked."""
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        # Try to unlock the failed document
        set_doc_lock_state(locked=False, doc_id=self.doc.id)

        self.doc.refresh_from_db()

        # Document should still be locked and in FAILED state
        self.assertTrue(self.doc.backend_lock)
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.FAILED)

    def test_unlocks_completed_document(self):
        """Test that set_doc_lock_state unlocks completed documents."""
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        # Set document to processing status (simulating successful parsing)
        self.doc.processing_status = DocumentProcessingStatus.PROCESSING
        self.doc.save()

        # Unlock the document
        set_doc_lock_state(locked=False, doc_id=self.doc.id)

        self.doc.refresh_from_db()

        # Document should be unlocked and in COMPLETED state
        self.assertFalse(self.doc.backend_lock)
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.COMPLETED)
