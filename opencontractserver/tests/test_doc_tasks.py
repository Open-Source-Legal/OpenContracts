#  Copyright (C) 2022  John Scrudato
import base64
import io
import logging
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from pypdf import PdfReader

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentProcessingStatus
from opencontractserver.tasks.doc_tasks import (
    _create_document_processed_notifications,
    _create_document_processing_failed_notification,
    _mark_document_failed,
    burn_doc_annotations,
    convert_doc_to_funsd,
    extract_thumbnail,
    retry_document_processing,
    set_doc_lock_state,
)
from opencontractserver.tests.fixtures import (
    SAMPLE_PAWLS_FILE_ONE_PATH,
    SAMPLE_PDF_FILE_ONE_PATH,
)
from opencontractserver.types.enums import LabelType

User = get_user_model()

logger = logging.getLogger(__name__)


class DocParserTestCase(TestCase):
    """
    Test case for document parsing tasks excluding thumbnail-related tests.
    """

    def setUp(self) -> None:
        """
        Set up the test user, documents, and corpus.
        """
        # Setup a test user
        with transaction.atomic():
            self.user = User.objects.create_user(username="bob", password="12345678")

        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_ONE_PATH.open("rb").read(), name="test.pdf"
        )
        pawls_file = ContentFile(
            SAMPLE_PAWLS_FILE_ONE_PATH.open("rb").read(), name="test.pawls"
        )

        with transaction.atomic():
            self.doc = Document.objects.create(
                creator=self.user,
                title="Test Doc",
                description="USC Title 1 - Chapter 1",
                custom_meta={},
                pdf_file=pdf_file,
                pawls_parse_file=pawls_file,
                backend_lock=True,
            )
            self.corpus = Corpus(
                title="Test", description="Some important stuff!", creator=self.user
            )
            self.corpus.save()

    def test_set_doc_lock_state(self) -> None:
        """
        Test setting the document lock state.
        """
        set_doc_lock_state.apply(kwargs={"locked": True, "doc_id": self.doc.id}).get()

        self.doc.refresh_from_db()
        self.assertTrue(self.doc.backend_lock)

    def test_burn_doc_annotations_doc_labels_only(self) -> None:
        """
        Test burning annotations with only doc-level labels (no text labels).
        Verifies the 5-tuple structure is returned correctly.
        """
        # NOTE(deferred): Only doc labels are exercised. Text-label burning
        # and substantive output validation (e.g. checking the resulting PDF
        # contains the expected highlight overlays) are not covered yet.
        label_lookups = {
            "text_labels": {},
            "doc_labels": {
                "test": {
                    "id": "1234",
                    "color": "red",
                    "description": "stuff happening",
                    "icon": "tag",
                    "text": "test",
                    "label_type": LabelType.DOC_TYPE_LABEL,
                }
            },
        }
        result = burn_doc_annotations.apply(
            args=(label_lookups, self.doc.id, self.corpus.id)
        ).get()
        self.assertEqual(len(result), 5)

    def test_burn_doc_annotations_with_text_labels(self) -> None:
        """
        Test burning annotations with text labels exercises the PDF highlight
        code path and produces valid annotated output.
        """
        # Create a text-level annotation label in the database
        text_label = AnnotationLabel.objects.create(
            text="Important Clause",
            creator=self.user,
            label_type=LabelType.TOKEN_LABEL,
            color="#FF5733",
            description="Highlights important clauses",
            icon="tag",
        )

        # Create a doc-level annotation label in the database
        doc_label = AnnotationLabel.objects.create(
            text="Contract",
            creator=self.user,
            label_type=LabelType.DOC_TYPE_LABEL,
            color="#33FF57",
            description="Marks document as a contract",
            icon="file",
        )

        # Create a text annotation on page 1 with bounding-box data.
        # The JSON keys are 1-based page number strings; bounds use
        # left/right/top/bottom matching BoundingBoxPythonType.
        Annotation.objects.create(
            raw_text="Development Agreement",
            annotation_label=text_label,
            annotation_type=LabelType.TOKEN_LABEL,
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            page=1,
            json={
                "1": {
                    "bounds": {
                        "left": 100,
                        "top": 100,
                        "right": 300,
                        "bottom": 120,
                    },
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                    "rawText": "Development Agreement",
                }
            },
        )

        # Create a doc-level annotation
        Annotation.objects.create(
            raw_text="Contract",
            annotation_label=doc_label,
            annotation_type=LabelType.DOC_TYPE_LABEL,
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
        )

        # Build label lookups referencing actual DB primary keys
        label_lookups = {
            "text_labels": {
                str(text_label.pk): {
                    "id": str(text_label.pk),
                    "color": "#FF5733",
                    "description": "Highlights important clauses",
                    "icon": "tag",
                    "text": "Important Clause",
                    "label_type": LabelType.TOKEN_LABEL,
                }
            },
            "doc_labels": {
                str(doc_label.pk): {
                    "id": str(doc_label.pk),
                    "color": "#33FF57",
                    "description": "Marks document as a contract",
                    "icon": "file",
                    "text": "Contract",
                    "label_type": LabelType.DOC_TYPE_LABEL,
                }
            },
        }

        result = burn_doc_annotations.apply(
            args=(label_lookups, self.doc.id, self.corpus.id)
        ).get()

        # Verify 5-tuple structure
        self.assertEqual(len(result), 5)
        filename, base64_pdf, doc_export, returned_text_labels, returned_doc_labels = (
            result
        )

        # Filename should be the PDF basename
        self.assertIsNotNone(filename)
        self.assertTrue(filename.endswith(".pdf"))

        # base64-encoded PDF should be non-empty (annotations were burned in)
        self.assertIsInstance(base64_pdf, str)
        self.assertGreater(len(base64_pdf), 0)

        # Decode and verify it's a valid PDF
        pdf_bytes = base64.b64decode(base64_pdf)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        self.assertGreater(len(reader.pages), 0)

        # The first page should contain our burned-in annotation
        first_page = reader.pages[0]
        annots = first_page.get("/Annots")
        self.assertIsNotNone(annots, "First page should have PDF annotations")
        self.assertGreater(len(annots), 0)

        # Find the annotation we added by its /Contents field, since the
        # sample PDF may already contain other annotations.
        highlight_annot = None
        for annot_ref in annots:
            annot_obj = annot_ref.get_object()
            if annot_obj.get("/Contents") == "Important Clause":
                highlight_annot = annot_obj
                break
        self.assertIsNotNone(
            highlight_annot,
            "Expected an annotation with /Contents 'Important Clause'",
        )
        self.assertEqual(highlight_annot["/Subtype"], "/Highlight")

        # doc_export should contain the expected annotation data
        self.assertIsNotNone(doc_export)
        self.assertIn("Contract", doc_export["doc_labels"])
        self.assertEqual(len(doc_export["labelled_text"]), 1)
        self.assertEqual(
            doc_export["labelled_text"][0]["rawText"], "Development Agreement"
        )
        self.assertEqual(
            doc_export["labelled_text"][0]["annotationLabel"], str(text_label.pk)
        )

        # Returned label dicts should match what was passed in
        self.assertIn(str(text_label.pk), returned_text_labels)
        self.assertIn(str(doc_label.pk), returned_doc_labels)

    def test_convert_doc_to_funsd(self) -> None:
        """
        Test converting a document to the FUNSD format.
        """
        AnnotationLabel.objects.create(
            text="TestLabel", creator=self.user, label_type="TOKEN_LABEL"
        )
        Annotation.objects.create(
            raw_text="Test annotation",
            annotation_label=AnnotationLabel.objects.first(),
            document=self.doc,
            corpus_id=self.corpus.id,
            creator=self.user,
            json={
                "0": {
                    "tokensJsons": [],
                    "rawText": "Test",
                    "bounds": {"x": 0, "y": 0, "width": 10, "height": 10},
                }
            },
        )

        result = convert_doc_to_funsd.apply(args=(self.user.id, self.doc.id, 1)).get()

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], self.doc.id)
        self.assertIsInstance(result[1], dict)
        self.assertIsInstance(result[2], list)


class MarkDocumentFailedTestCase(TestCase):
    """Tests for _mark_document_failed and related notification functions."""

    def setUp(self):
        self.user = User.objects.create_user(username="failtest", password="12345678")
        self.doc = Document.objects.create(
            creator=self.user,
            title="Test Fail Doc",
            backend_lock=True,
            processing_status=DocumentProcessingStatus.PROCESSING,
        )

    def test_mark_document_failed_sets_status(self):
        """Test that _mark_document_failed sets the correct status and error."""
        _mark_document_failed(
            self.doc, "Test error message", "Traceback here", create_notification=False
        )
        self.doc.refresh_from_db()

        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertEqual(self.doc.processing_error, "Test error message")
        self.assertEqual(self.doc.processing_error_traceback, "Traceback here")
        self.assertIsNotNone(self.doc.processing_finished)

    def test_mark_document_failed_truncates_long_error(self):
        """Test that long error messages are truncated."""
        from opencontractserver.constants import MAX_PROCESSING_ERROR_LENGTH

        long_error = "X" * (MAX_PROCESSING_ERROR_LENGTH + 100)
        _mark_document_failed(self.doc, long_error, "", create_notification=False)
        self.doc.refresh_from_db()

        self.assertEqual(len(self.doc.processing_error), MAX_PROCESSING_ERROR_LENGTH)

    @patch("opencontractserver.tasks.doc_tasks.Notification.objects.create")
    def test_create_failed_notification_exception_handling(self, mock_create):
        """Test that notification creation errors are logged but don't raise."""
        mock_create.side_effect = Exception("DB error")

        # Should not raise - just log the error
        _create_document_processing_failed_notification(self.doc, "Test error")
        mock_create.assert_called_once()

    def test_create_failed_notification_no_creator(self):
        """Test that no notification is created when document has no creator."""
        # Create a mock document with no creator
        mock_doc = MagicMock()
        mock_doc.creator = None

        # Should return early without creating notification
        with patch(
            "opencontractserver.tasks.doc_tasks.Notification.objects.create"
        ) as mock_create:
            _create_document_processing_failed_notification(mock_doc, "Test error")
            mock_create.assert_not_called()

    def test_create_failed_notification_uses_description_fallback(self):
        """Test that description is used as title fallback."""
        # Create a mock document with empty title but with description (longer than 50 chars)
        mock_doc = MagicMock()
        mock_doc.creator = self.user
        mock_doc.title = ""
        # Description longer than 50 chars to test truncation
        mock_doc.description = (
            "A very long description that exceeds the fifty character limit easily"
        )
        mock_doc.id = self.doc.id
        mock_doc.file_type = "application/pdf"

        with patch(
            "opencontractserver.tasks.doc_tasks.Notification.objects.create"
        ) as mock_create:
            mock_create.return_value = MagicMock()
            with patch(
                "opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket"
            ):
                _create_document_processing_failed_notification(mock_doc, "Test error")

            call_kwargs = mock_create.call_args.kwargs
            # Should use first 50 chars of description
            self.assertEqual(
                call_kwargs["data"]["document_title"],
                "A very long description that exceeds the fifty cha",
            )

    def test_create_failed_notification_uses_untitled_fallback(self):
        """Test that 'Untitled' is used when no title or description."""
        # Create a mock document with no title or description
        mock_doc = MagicMock()
        mock_doc.creator = self.user
        mock_doc.title = ""
        mock_doc.description = ""
        mock_doc.id = self.doc.id
        mock_doc.file_type = "application/pdf"

        with patch(
            "opencontractserver.tasks.doc_tasks.Notification.objects.create"
        ) as mock_create:
            mock_create.return_value = MagicMock()
            with patch(
                "opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket"
            ):
                _create_document_processing_failed_notification(mock_doc, "Test error")

            call_kwargs = mock_create.call_args.kwargs
            self.assertEqual(call_kwargs["data"]["document_title"], "Untitled")


class CreateDocumentProcessedNotificationsTestCase(TestCase):
    """Tests for _create_document_processed_notifications."""

    def setUp(self):
        self.user = User.objects.create_user(username="notiftest", password="12345678")
        self.corpus_owner = User.objects.create_user(
            username="corpusowner", password="12345678"
        )
        self.doc = Document.objects.create(
            creator=self.user,
            title="Processed Doc",
            backend_lock=False,
            processing_status=DocumentProcessingStatus.COMPLETED,
        )

    @patch("opencontractserver.tasks.doc_tasks.Notification.objects.create")
    @patch("opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket")
    def test_creates_notifications_for_creator_and_corpus_owners(
        self, mock_broadcast, mock_create
    ):
        """Test notifications are created for both doc creator and corpus owners."""
        mock_create.return_value = MagicMock()

        corpus_data = [
            {"corpus_id": 1, "corpus__creator_id": self.corpus_owner.id},
        ]

        _create_document_processed_notifications(self.doc, corpus_data)

        # Should create notifications for both users
        self.assertEqual(mock_create.call_count, 2)

    @patch("opencontractserver.tasks.doc_tasks.Notification.objects.create")
    def test_handles_notification_creation_error(self, mock_create):
        """Test that notification creation errors don't propagate."""
        mock_create.side_effect = Exception("DB error")

        # Should not raise
        _create_document_processed_notifications(self.doc, [])

    def test_no_creator_still_notifies_corpus_owners(self):
        """Test that corpus owners get notified even if doc has no creator."""
        corpus_data = [
            {"corpus_id": 1, "corpus__creator_id": self.corpus_owner.id},
        ]

        # Create a mock document with no creator
        mock_doc = MagicMock()
        mock_doc.creator = None
        mock_doc.title = "Test Doc"
        mock_doc.description = ""
        mock_doc.id = self.doc.id
        mock_doc.file_type = "application/pdf"

        with patch(
            "opencontractserver.tasks.doc_tasks.Notification.objects.create"
        ) as mock_create:
            mock_create.return_value = MagicMock()
            with patch(
                "opencontractserver.tasks.doc_tasks.broadcast_notification_via_websocket"
            ):
                _create_document_processed_notifications(mock_doc, corpus_data)

            # Should only notify corpus owner
            self.assertEqual(mock_create.call_count, 1)


class SetDocLockStateTestCase(TestCase):
    """Tests for set_doc_lock_state edge cases."""

    def setUp(self):
        self.user = User.objects.create_user(username="locktest", password="12345678")
        self.doc = Document.objects.create(
            creator=self.user,
            title="Lock Test Doc",
            backend_lock=True,
            processing_status=DocumentProcessingStatus.PROCESSING,
        )

    def test_unlock_failed_document_keeps_locked(self):
        """Test that unlocking a FAILED document keeps it locked."""
        self.doc.processing_status = DocumentProcessingStatus.FAILED
        self.doc.save()

        set_doc_lock_state.apply(kwargs={"locked": False, "doc_id": self.doc.id}).get()

        self.doc.refresh_from_db()
        # Document should remain locked since it failed
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.FAILED)

    def test_unlock_successful_sets_completed(self):
        """Test that unlocking a processing document sets status to COMPLETED."""
        set_doc_lock_state.apply(kwargs={"locked": False, "doc_id": self.doc.id}).get()

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.COMPLETED)
        self.assertFalse(self.doc.backend_lock)


class ExtractThumbnailTestCase(TestCase):
    """Tests for extract_thumbnail task edge cases."""

    def setUp(self):
        self.user = User.objects.create_user(username="thumbtest", password="12345678")
        self.doc = Document.objects.create(
            creator=self.user,
            title="Thumbnail Test Doc",
            file_type="application/pdf",
        )

    def test_extract_thumbnail_nonexistent_document(self):
        """Test extract_thumbnail handles nonexistent document."""
        # Should not raise, just return early
        result = extract_thumbnail.apply(kwargs={"doc_id": 99999}).get()
        self.assertIsNone(result)

    @patch("opencontractserver.tasks.doc_tasks.get_components_by_mimetype")
    def test_extract_thumbnail_no_thumbnailer(self, mock_get_components):
        """Test extract_thumbnail handles missing thumbnailer."""
        mock_get_components.return_value = {"thumbnailers": []}

        # Should not raise, just log error and return
        result = extract_thumbnail.apply(kwargs={"doc_id": self.doc.id}).get()
        self.assertIsNone(result)

    @patch("opencontractserver.tasks.doc_tasks.get_components_by_mimetype")
    def test_extract_thumbnail_generation_failure(self, mock_get_components):
        """Test extract_thumbnail handles failed thumbnail generation."""
        mock_thumbnailer = MagicMock()
        mock_thumbnailer.__name__ = "MockThumbnailer"
        mock_thumbnailer.return_value.generate_thumbnail.return_value = None
        mock_get_components.return_value = {"thumbnailers": [mock_thumbnailer]}

        # Should not raise
        result = extract_thumbnail.apply(kwargs={"doc_id": self.doc.id}).get()
        self.assertIsNone(result)


class RetryDocumentProcessingTestCase(TestCase):
    """Tests for retry_document_processing task."""

    def setUp(self):
        self.user = User.objects.create_user(username="retrytest", password="12345678")
        self.doc = Document.objects.create(
            creator=self.user,
            title="Retry Test Doc",
            processing_status=DocumentProcessingStatus.FAILED,
            processing_error="Previous error",
            backend_lock=True,
        )

    def test_retry_nonexistent_document(self):
        """Test retry_document_processing handles nonexistent document."""
        result = retry_document_processing.apply(args=(self.user.id, 99999)).get()

        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["message"])

    def test_retry_non_failed_document(self):
        """Test retry_document_processing rejects non-failed documents."""
        self.doc.processing_status = DocumentProcessingStatus.COMPLETED
        self.doc.save()

        result = retry_document_processing.apply(args=(self.user.id, self.doc.id)).get()

        self.assertEqual(result["status"], "error")
        self.assertIn("not in failed state", result["message"])

    @patch("celery.chain")
    def test_retry_failed_document_success(self, mock_chain):
        """Test retry_document_processing queues reprocessing for failed doc."""
        mock_chain.return_value.apply_async = MagicMock()

        result = retry_document_processing.apply(args=(self.user.id, self.doc.id)).get()

        self.assertEqual(result["status"], "queued")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.PENDING)
        self.assertEqual(self.doc.processing_error, "")
        mock_chain.assert_called_once()
