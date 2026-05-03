"""
Tests for job completion notification creation (Issue #624).

Tests cover the notification helper functions in:
- doc_tasks.py: _create_document_processed_notifications
- export_tasks.py: _create_export_notification
- extract_orchestrator_tasks.py: mark_extract_complete notification
- analyzer/views.py: _create_analysis_notification
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from opencontractserver.corpuses.models import Corpus
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)

User = get_user_model()


@override_settings(USE_AUTH0=False)
class DocumentProcessedNotificationTests(TestCase):
    """Tests for _create_document_processed_notifications in doc_tasks.py."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@test.com", password="testpass"
        )

    @patch("opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket")
    def test_notification_created_for_document_creator(self, mock_broadcast):
        """Notification should be created for the document creator."""
        from opencontractserver.tasks.doc_tasks import (
            _create_document_processed_notifications,
        )

        document = MagicMock()
        document.id = 1
        document.title = "Test Document"
        document.description = "Test Description"
        document.page_count = 10
        document.file_type = "application/pdf"
        document.creator = self.user

        _create_document_processed_notifications(document, [])

        # Should create notification
        self.assertEqual(Notification.objects.count(), 1)
        notification = Notification.objects.first()
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(
            notification.notification_type, NotificationTypeChoices.DOCUMENT_PROCESSED
        )
        self.assertEqual(notification.data["document_title"], "Test Document")

        # Should broadcast
        mock_broadcast.assert_called_once()

    @patch("opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket")
    def test_notification_for_corpus_owner(self, mock_broadcast):
        """Notification should be created for corpus owners."""
        from opencontractserver.tasks.doc_tasks import (
            _create_document_processed_notifications,
        )

        document = MagicMock()
        document.id = 1
        document.title = "Test Document"
        document.description = None
        document.page_count = 5
        document.file_type = "application/pdf"
        document.creator = self.user

        corpus_data = [{"corpus__creator_id": self.other_user.id}]

        _create_document_processed_notifications(document, corpus_data)

        # Should create notifications for both document creator and corpus owner
        self.assertEqual(Notification.objects.count(), 2)
        recipients = set(Notification.objects.values_list("recipient_id", flat=True))
        self.assertEqual(recipients, {self.user.id, self.other_user.id})

    @patch("opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket")
    def test_title_fallback_to_description(self, mock_broadcast):
        """Document title should fall back to description if title is empty."""
        from opencontractserver.tasks.doc_tasks import (
            _create_document_processed_notifications,
        )

        document = MagicMock()
        document.id = 1
        document.title = ""  # Empty title
        long_desc = "A" * 60  # 60 character description
        document.description = long_desc
        document.page_count = 1
        document.file_type = "text/plain"
        document.creator = self.user

        _create_document_processed_notifications(document, [])

        notification = Notification.objects.first()
        # Should use first 50 chars of description
        self.assertEqual(notification.data["document_title"], "A" * 50)

    @patch("opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket")
    def test_title_fallback_to_untitled(self, mock_broadcast):
        """Document title should fall back to 'Untitled' if no title or description."""
        from opencontractserver.tasks.doc_tasks import (
            _create_document_processed_notifications,
        )

        document = MagicMock()
        document.id = 1
        document.title = None
        document.description = None
        document.page_count = 1
        document.file_type = "text/plain"
        document.creator = self.user

        _create_document_processed_notifications(document, [])

        notification = Notification.objects.first()
        self.assertEqual(notification.data["document_title"], "Untitled")

    @patch("opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket")
    def test_nonexistent_corpus_creator_handled(self, mock_broadcast):
        """Non-existent corpus creator IDs should be handled gracefully."""
        from opencontractserver.tasks.doc_tasks import (
            _create_document_processed_notifications,
        )

        document = MagicMock()
        document.id = 1
        document.title = "Test"
        document.description = None
        document.page_count = 1
        document.file_type = "text/plain"
        document.creator = self.user

        # Non-existent user ID
        corpus_data = [{"corpus__creator_id": 99999}]

        # Should not raise, should create notification for document creator only
        _create_document_processed_notifications(document, corpus_data)

        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.first().recipient, self.user)

    @patch("opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket")
    def test_no_creator_no_notification(self, mock_broadcast):
        """No notification if document has no creator."""
        from opencontractserver.tasks.doc_tasks import (
            _create_document_processed_notifications,
        )

        document = MagicMock()
        document.id = 1
        document.title = "Test"
        document.description = None
        document.page_count = 1
        document.file_type = "text/plain"
        document.creator = None  # No creator

        _create_document_processed_notifications(document, [])

        self.assertEqual(Notification.objects.count(), 0)
        mock_broadcast.assert_not_called()

    @patch(
        "opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket",
        side_effect=Exception("Broadcast error"),
    )
    def test_broadcast_exception_handled(self, mock_broadcast):
        """Exceptions during notification creation should be handled gracefully."""
        from opencontractserver.tasks.doc_tasks import (
            _create_document_processed_notifications,
        )

        document = MagicMock()
        document.id = 1
        document.title = "Test"
        document.description = None
        document.page_count = 1
        document.file_type = "text/plain"
        document.creator = self.user

        # Should not raise
        _create_document_processed_notifications(document, [])

        # Notification was created before broadcast failed
        self.assertEqual(Notification.objects.count(), 1)


@override_settings(USE_AUTH0=False)
class AnalysisNotificationTests(TestCase):
    """Tests for _create_analysis_notification in analyzer/views.py."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass"
        )

    @patch("opencontractserver.analyzer.views.broadcast_notification_via_websocket")
    def test_analysis_complete_notification(self, mock_broadcast):
        """ANALYSIS_COMPLETE notification should be created on success."""
        from opencontractserver.analyzer.views import _create_analysis_notification

        analysis = MagicMock()
        analysis.id = 1
        analysis.creator = self.user
        analysis.analyzer = MagicMock()
        analysis.analyzer.id = "test-analyzer"
        analysis.analyzed_corpus = MagicMock()
        analysis.analyzed_corpus.title = "Test Corpus"

        _create_analysis_notification(analysis, success=True)

        notification = Notification.objects.first()
        self.assertEqual(
            notification.notification_type, NotificationTypeChoices.ANALYSIS_COMPLETE
        )
        self.assertEqual(notification.data["status"], "completed")
        mock_broadcast.assert_called_once()

    @patch("opencontractserver.analyzer.views.broadcast_notification_via_websocket")
    def test_analysis_failed_notification(self, mock_broadcast):
        """ANALYSIS_FAILED notification should be created on failure."""
        from opencontractserver.analyzer.views import _create_analysis_notification

        analysis = MagicMock()
        analysis.id = 1
        analysis.creator = self.user
        analysis.analyzer = MagicMock()
        analysis.analyzer.id = "test-analyzer"
        analysis.analyzed_corpus = MagicMock()
        analysis.analyzed_corpus.title = "Test Corpus"

        _create_analysis_notification(analysis, success=False)

        notification = Notification.objects.first()
        self.assertEqual(
            notification.notification_type, NotificationTypeChoices.ANALYSIS_FAILED
        )
        self.assertEqual(notification.data["status"], "failed")

    @patch("opencontractserver.analyzer.views.broadcast_notification_via_websocket")
    def test_no_creator_no_notification(self, mock_broadcast):
        """No notification if analysis has no creator."""
        from opencontractserver.analyzer.views import _create_analysis_notification

        analysis = MagicMock()
        analysis.id = 1
        analysis.creator = None  # No creator

        _create_analysis_notification(analysis, success=True)

        self.assertEqual(Notification.objects.count(), 0)
        mock_broadcast.assert_not_called()

    @patch(
        "opencontractserver.analyzer.views.broadcast_notification_via_websocket",
        side_effect=Exception("Broadcast error"),
    )
    def test_exception_handled(self, mock_broadcast):
        """Exceptions should be handled gracefully."""
        from opencontractserver.analyzer.views import _create_analysis_notification

        analysis = MagicMock()
        analysis.id = 1
        analysis.creator = self.user
        analysis.analyzer = None
        analysis.analyzed_corpus = None

        # Should not raise
        _create_analysis_notification(analysis, success=True)


@override_settings(USE_AUTH0=False)
class ExportNotificationTests(TestCase):
    """Tests for _create_export_notification in export_tasks.py."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass"
        )

    @patch("opencontractserver.tasks.export_tasks.broadcast_notification_via_websocket")
    def test_export_notification_created(self, mock_broadcast):
        """EXPORT_COMPLETE notification should be created."""
        from opencontractserver.tasks.export_tasks import _create_export_notification

        export = MagicMock()
        export.id = 1
        export.name = "Test Export"
        export.format = "OPEN_CONTRACTS"
        export.creator = self.user

        _create_export_notification(export, "Test Corpus")

        notification = Notification.objects.first()
        self.assertEqual(
            notification.notification_type, NotificationTypeChoices.EXPORT_COMPLETE
        )
        self.assertEqual(notification.data["corpus_name"], "Test Corpus")
        mock_broadcast.assert_called_once()

    @patch("opencontractserver.tasks.export_tasks.broadcast_notification_via_websocket")
    def test_no_creator_no_notification(self, mock_broadcast):
        """No notification if export has no creator."""
        from opencontractserver.tasks.export_tasks import _create_export_notification

        export = MagicMock()
        export.id = 1
        export.name = "Test Export"
        export.format = "OPEN_CONTRACTS"
        export.creator = None  # No creator

        _create_export_notification(export, "Test Corpus")

        self.assertEqual(Notification.objects.count(), 0)
        mock_broadcast.assert_not_called()

    @patch(
        "opencontractserver.tasks.export_tasks.broadcast_notification_via_websocket",
        side_effect=Exception("Broadcast error"),
    )
    def test_exception_handled(self, mock_broadcast):
        """Exceptions should be handled gracefully."""
        from opencontractserver.tasks.export_tasks import _create_export_notification

        export = MagicMock()
        export.id = 1
        export.name = "Test Export"
        export.format = "OPEN_CONTRACTS"
        export.creator = self.user

        # Should not raise
        _create_export_notification(export, "Test Corpus")


@override_settings(USE_AUTH0=False, CELERY_TASK_ALWAYS_EAGER=True)
class ExtractNotificationTests(TestCase):
    """Tests for extract completion notification in extract_orchestrator_tasks.py."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass"
        )
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)

    @patch(
        "opencontractserver.tasks.extract_orchestrator_tasks.broadcast_notification_via_websocket"
    )
    def test_extract_complete_notification(self, mock_broadcast):
        """EXTRACT_COMPLETE notification should be created."""
        from opencontractserver.tasks.extract_orchestrator_tasks import (
            mark_extract_complete,
        )

        extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.user,
        )

        mark_extract_complete(extract.id)

        notification = Notification.objects.filter(
            notification_type=NotificationTypeChoices.EXTRACT_COMPLETE
        ).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.data["extract_name"], "Test Extract")
        mock_broadcast.assert_called_once()

    @patch(
        "opencontractserver.tasks.extract_orchestrator_tasks.broadcast_notification_via_websocket"
    )
    @patch("opencontractserver.tasks.extract_orchestrator_tasks.Extract")
    def test_extract_no_creator_no_notification(
        self, mock_extract_model, mock_broadcast
    ):
        """No notification if extract has no creator."""
        # Mock the extract to have no creator
        mock_extract = MagicMock()
        mock_extract.id = 999
        mock_extract.name = "Test Extract"
        mock_extract.creator = None  # No creator
        mock_extract.documents.count.return_value = 5
        mock_extract.fieldset = None
        mock_extract_model.objects.get.return_value = mock_extract

        from opencontractserver.tasks.extract_orchestrator_tasks import (
            mark_extract_complete,
        )

        mark_extract_complete(999)

        # Should not create extract notification
        mock_broadcast.assert_not_called()
        # Extract should still be marked as finished
        mock_extract.save.assert_called()

    @patch(
        "opencontractserver.tasks.extract_orchestrator_tasks.broadcast_notification_via_websocket",
        side_effect=Exception("Broadcast error"),
    )
    def test_exception_handled(self, mock_broadcast):
        """Exceptions should be handled gracefully."""
        from opencontractserver.tasks.extract_orchestrator_tasks import (
            mark_extract_complete,
        )

        extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.user,
        )

        # Should not raise
        mark_extract_complete(extract.id)

        # Extract should still be marked as finished
        extract.refresh_from_db()
        self.assertIsNotNone(extract.finished)
