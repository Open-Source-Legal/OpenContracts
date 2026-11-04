"""
Regression tests for issue #2516: ``reconcile_stuck_documents`` failing healthy
documents during a deep ingest backlog.

Two distinct defects, each paired with a test that the sweep's real job --
reclaiming documents whose chain actually died -- still works:

1. The stale clock started at upload, so a document that merely waited in the
   queue was reclaimed minutes after ``ingest_doc`` finally picked it up.
2. ``remap_pending_annotations`` and ``set_doc_lock_state`` re-queue behind the
   whole ``doc_parse`` backlog, so a parsed document can still outlive the window.
   Its late unlock used to refuse the sweep's FAILED and strand it permanently.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from opencontractserver.constants.document_processing import (
    STUCK_DOCUMENT_SWEEP_ERROR_PREFIX,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentProcessingStatus,
)
from opencontractserver.tasks.doc_tasks import (
    _mark_document_failed,
    ingest_doc,
    reconcile_stuck_documents,
    set_doc_lock_state,
)

User = get_user_model()

# Comfortably past the default DOCUMENT_PROCESSING_STALE_MINUTES (30).
STALE_MINUTES = 120


class StuckDocumentTestBase(TestCase):
    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="sweepuser", password="12345678"
            )

    def _make_doc(self, *, status, started_minutes_ago=STALE_MINUTES):
        doc = Document.objects.create(
            title="Doc", file_type="application/pdf", creator=self.user
        )
        # Set the fields directly so processing signals stay out of the picture
        # and processing_started is controlled precisely.
        Document.objects.filter(pk=doc.pk).update(
            processing_status=status,
            backend_lock=True,
            processing_started=timezone.now() - timedelta(minutes=started_minutes_ago),
        )
        doc.refresh_from_db()
        return doc


class TestIngestStartRestartsStaleClock(StuckDocumentTestBase):
    """The stale window measures processing, not time spent queued."""

    def _run_ingest(self, doc, retries=0):
        with patch(
            "opencontractserver.tasks.doc_tasks._resolve_parser_for_ingest",
            return_value=("parser", MagicMock(), {}),
        ):
            result = ingest_doc.apply(
                kwargs={"user_id": self.user.pk, "doc_id": doc.pk}, retries=retries
            )
        self.assertEqual(result.get()["status"], "success")
        doc.refresh_from_db()

    def test_document_queued_past_the_window_survives_the_sweep(self):
        doc = self._make_doc(status=DocumentProcessingStatus.PENDING)

        self._run_ingest(doc)
        result = reconcile_stuck_documents()

        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.PROCESSING)
        self.assertEqual(result["reconciled"], 0)

    def test_first_attempt_stamps_processing_started(self):
        doc = self._make_doc(status=DocumentProcessingStatus.PENDING)
        before = timezone.now()

        self._run_ingest(doc)

        self.assertGreaterEqual(doc.processing_started, before)

    def test_redelivery_does_not_reset_the_clock(self):
        """CELERY_TASK_REJECT_ON_WORKER_LOST redelivers with retries == 0.

        A document that OOM-kills its worker comes back with the same
        ``retries`` as a first attempt. Restarting the clock there would keep
        it inside the window on every crash, so the sweep could never reclaim it.
        """
        doc = self._make_doc(status=DocumentProcessingStatus.PROCESSING)
        original_start = doc.processing_started

        self._run_ingest(doc, retries=0)

        self.assertEqual(doc.processing_started, original_start)
        self.assertEqual(reconcile_stuck_documents()["reconciled"], 1)
        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.FAILED)

    def test_celery_retry_does_not_reset_the_clock(self):
        doc = self._make_doc(status=DocumentProcessingStatus.PROCESSING)
        original_start = doc.processing_started

        self._run_ingest(doc, retries=1)

        self.assertEqual(doc.processing_started, original_start)


class TestLateUnlockRecoversSweptDocument(StuckDocumentTestBase):
    """Only a sweep verdict can be overturned, and only by a finished chain."""

    def _sweep(self, doc):
        self.assertEqual(reconcile_stuck_documents()["reconciled"], 1)
        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertTrue(
            doc.processing_error.startswith(STUCK_DOCUMENT_SWEEP_ERROR_PREFIX)
        )

    def test_late_unlock_completes_a_swept_document(self):
        doc = self._make_doc(status=DocumentProcessingStatus.PROCESSING)
        self._sweep(doc)

        set_doc_lock_state(locked=False, doc_id=doc.pk)

        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.COMPLETED)
        self.assertFalse(doc.backend_lock)
        self.assertEqual(doc.processing_error, "")
        self.assertEqual(doc.processing_error_traceback, "")

    def test_late_unlock_fires_corpus_actions_once(self):
        """The sweep never fired them, so recovery is the document's only trigger."""
        doc = self._make_doc(status=DocumentProcessingStatus.PROCESSING)
        corpus = Corpus.objects.create(title="Corpus", creator=self.user)
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/documents/doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        self._sweep(doc)

        with patch(
            "opencontractserver.tasks.corpus_tasks.process_corpus_action.delay"
        ) as dispatch, self.captureOnCommitCallbacks(execute=True):
            set_doc_lock_state(locked=False, doc_id=doc.pk)

        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(dispatch.call_args.kwargs["document_ids"], [doc.pk])

    def test_genuine_failure_stays_failed_and_locked(self):
        doc = self._make_doc(status=DocumentProcessingStatus.PROCESSING)
        _mark_document_failed(doc, "Docling returned 500", create_notification=False)

        set_doc_lock_state(locked=False, doc_id=doc.pk)

        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertTrue(doc.backend_lock)
        self.assertEqual(doc.processing_error, "Docling returned 500")

    def test_error_quoting_the_sweep_message_is_not_a_sweep_verdict(self):
        """Parser errors can echo arbitrary text, so match the prefix only."""
        doc = self._make_doc(status=DocumentProcessingStatus.PROCESSING)
        quoted = f"Parser said: {STUCK_DOCUMENT_SWEEP_ERROR_PREFIX}"
        _mark_document_failed(doc, quoted, create_notification=False)

        set_doc_lock_state(locked=False, doc_id=doc.pk)

        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertTrue(doc.backend_lock)
        self.assertEqual(doc.processing_error, quoted)

    def test_swept_document_whose_chain_died_stays_failed(self):
        """No late unlock arrives for a dead chain: the sweep's verdict stands."""
        doc = self._make_doc(status=DocumentProcessingStatus.PROCESSING)
        self._sweep(doc)

        self.assertEqual(reconcile_stuck_documents()["reconciled"], 0)

        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertTrue(doc.backend_lock)
