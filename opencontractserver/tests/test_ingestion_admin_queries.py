"""Tests for the superuser ingestion-monitor GraphQL queries.

Covers the four admin diagnostics listings wired in
``config/graphql/ingestion_admin_queries.py`` and their service layer:
superuser gating, the projected shapes, and the computed fields
(``elapsed_seconds``, per-run ``percent_failed``, chunked-session progress).
"""

import uuid
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.document_imports.models import (
    ChunkedUploadKind,
    ChunkedUploadPart,
    ChunkedUploadSession,
    ChunkedUploadStatus,
)
from opencontractserver.documents.models import (
    Document,
    DocumentProcessingStatus,
    PendingCorpusImport,
    PendingDocumentAnnotations,
)
from opencontractserver.users.models import User
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    UploadStatus,
    WorkerAccount,
    WorkerDocumentUpload,
)


class TestContext:
    """Minimal request-context stand-in for graphene's test Client."""

    def __init__(self, user):
        self.user = user


class IngestionAdminQueryTestCase(TestCase):
    # Class-level annotations for attributes populated in setUpTestData so
    # mypy resolves the cross-method `self.<attr>` accesses (issue #1479).
    admin: User
    regular: User
    failed_doc: Document
    completed_doc: Document
    corpus: Corpus
    worker_account: WorkerAccount
    token: CorpusAccessToken
    worker_upload: WorkerDocumentUpload
    run_id: uuid.UUID
    pci: PendingCorpusImport
    session: ChunkedUploadSession
    export_session: ChunkedUploadSession

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="ingestadmin", email="admin@example.com", password="pw"
        )
        cls.regular = User.objects.create_user(
            username="regular", email="regular@example.com", password="pw"
        )

        # --- Documents (panel 1) ---
        start = timezone.now() - timedelta(seconds=30)
        cls.failed_doc = Document.objects.create(
            creator=cls.regular,
            title="Broken Contract.pdf",
            file_type="application/pdf",
            page_count=12,
            processing_status=DocumentProcessingStatus.FAILED,
            processing_error="Parser exploded on page 3",
            processing_started=start,
            processing_finished=start + timedelta(seconds=5),
        )
        cls.completed_doc = Document.objects.create(
            creator=cls.admin,
            title="Good Doc.pdf",
            file_type="application/pdf",
            processing_status=DocumentProcessingStatus.COMPLETED,
            processing_started=start,
            processing_finished=start + timedelta(seconds=2),
        )

        # --- Worker upload queue (panel 1) ---
        # auto_branding_enabled=False so corpus creation never auto-creates a
        # Readme.CAML Document, keeping the document-count assertions exact.
        cls.corpus = Corpus.objects.create(
            title="Pipeline Corpus",
            creator=cls.admin,
            auto_branding_enabled=False,
        )
        cls.worker_account = WorkerAccount.create_with_user(
            name="Pipeline Bot", creator=cls.admin
        )
        cls.token, _ = CorpusAccessToken.create_token(
            worker_account=cls.worker_account, corpus=cls.corpus
        )
        cls.worker_upload = WorkerDocumentUpload.objects.create(
            corpus=cls.corpus,
            corpus_access_token=cls.token,
            status=UploadStatus.FAILED,
            error_message="bad mime type",
        )

        # --- Corpus-export import run (panel 2) with 1 done / 1 failed / 1 pending ---
        cls.run_id = uuid.uuid4()
        cls.pci = PendingCorpusImport.objects.create(
            import_run_id=cls.run_id,
            corpus=cls.corpus,
            creator=cls.admin,
            status=PendingCorpusImport.Status.DONE,
            expected_doc_count=3,
        )
        for status in (
            PendingDocumentAnnotations.Status.DONE,
            PendingDocumentAnnotations.Status.FAILED,
            PendingDocumentAnnotations.Status.PENDING,
        ):
            PendingDocumentAnnotations.objects.create(
                document=cls.completed_doc,
                corpus=cls.corpus,
                creator=cls.admin,
                ingestion_run_id=cls.run_id,
                status=status,
            )

        # --- Bulk document-zip import session (panel 2) ---
        cls.session = ChunkedUploadSession.objects.create(
            creator=cls.regular,
            kind=ChunkedUploadKind.DOCUMENTS_ZIP,
            filename="batch.zip",
            total_size=1000,
            chunk_size=500,
            total_chunks=2,
            status=ChunkedUploadStatus.PENDING,
            metadata={"corpus_id": "Q29ycHVzOjE="},
        )
        ChunkedUploadPart.objects.create(session=cls.session, index=0, size=500)
        # A CORPUS_EXPORT-kind session must NOT appear in the bulk list (it is
        # represented by PendingCorpusImport instead).
        cls.export_session = ChunkedUploadSession.objects.create(
            creator=cls.regular,
            kind=ChunkedUploadKind.CORPUS_EXPORT,
            filename="export.zip",
            total_size=10,
            chunk_size=10,
            total_chunks=1,
            status=ChunkedUploadStatus.PENDING,
        )

    def _execute(self, query, user):
        return schema.execute(query, context_value=TestContext(user))

    # ------------------------------------------------------------------ #
    # Gating
    # ------------------------------------------------------------------ #

    def test_regular_user_denied_all_admin_queries(self):
        queries = {
            "adminDocumentIngestion": "{ adminDocumentIngestion { totalCount } }",
            "adminWorkerUploads": "{ adminWorkerUploads { totalCount } }",
            "adminCorpusImports": "{ adminCorpusImports { totalCount } }",
            "adminBulkImportSessions": "{ adminBulkImportSessions { totalCount } }",
        }
        for field, query in queries.items():
            result = self._execute(query, self.regular)
            self.assertIsNotNone(result.errors, f"{field} should error for non-admin")
            self.assertIsNone((result.data or {}).get(field))

    def test_anonymous_denied(self):
        result = self._execute(
            "{ adminDocumentIngestion { totalCount } }", AnonymousUser()
        )
        self.assertIsNotNone(result.errors)

    # ------------------------------------------------------------------ #
    # Document ingestion
    # ------------------------------------------------------------------ #

    def test_admin_document_ingestion_shape_and_elapsed(self):
        query = """
        {
          adminDocumentIngestion(status: "failed") {
            totalCount
            items {
              title
              creatorUsername
              creatorEmail
              fileType
              pageCount
              processingStatus
              processingError
              elapsedSeconds
            }
          }
        }
        """
        result = self._execute(query, self.admin)
        self.assertIsNone(result.errors)
        payload = result.data["adminDocumentIngestion"]
        self.assertEqual(payload["totalCount"], 1)
        item = payload["items"][0]
        self.assertEqual(item["title"], "Broken Contract.pdf")
        self.assertEqual(item["creatorUsername"], "regular")
        self.assertEqual(item["creatorEmail"], "regular@example.com")
        self.assertEqual(item["processingStatus"], "failed")
        self.assertEqual(item["processingError"], "Parser exploded on page 3")
        self.assertEqual(item["pageCount"], 12)
        # 5-second window between started/finished.
        self.assertAlmostEqual(item["elapsedSeconds"], 5.0, delta=1.0)

    def test_admin_document_ingestion_unfiltered_sees_all(self):
        result = self._execute("{ adminDocumentIngestion { totalCount } }", self.admin)
        self.assertIsNone(result.errors)
        self.assertEqual(result.data["adminDocumentIngestion"]["totalCount"], 2)

    def test_admin_document_ingestion_elapsed_for_in_flight_doc(self):
        """In-flight docs (``processing_finished=None``) report ``now - started``."""
        Document.objects.create(
            creator=self.regular,
            title="In Flight.pdf",
            file_type="application/pdf",
            processing_status=DocumentProcessingStatus.PROCESSING,
            processing_started=timezone.now() - timedelta(seconds=10),
            processing_finished=None,
        )
        query = """
        {
          adminDocumentIngestion(status: "processing") {
            totalCount
            items { title elapsedSeconds }
          }
        }
        """
        result = self._execute(query, self.admin)
        self.assertIsNone(result.errors)
        payload = result.data["adminDocumentIngestion"]
        self.assertEqual(payload["totalCount"], 1)
        item = payload["items"][0]
        self.assertEqual(item["title"], "In Flight.pdf")
        # Open-ended elapsed measured against "now"; ~10s and still climbing.
        self.assertGreaterEqual(item["elapsedSeconds"], 9.0)

    # ------------------------------------------------------------------ #
    # Worker uploads
    # ------------------------------------------------------------------ #

    def test_admin_worker_uploads(self):
        query = """
        {
          adminWorkerUploads {
            totalCount
            items {
              status
              errorMessage
              corpusTitle
              workerAccountName
            }
          }
        }
        """
        result = self._execute(query, self.admin)
        self.assertIsNone(result.errors)
        payload = result.data["adminWorkerUploads"]
        self.assertEqual(payload["totalCount"], 1)
        item = payload["items"][0]
        self.assertEqual(item["status"], "FAILED")
        self.assertEqual(item["errorMessage"], "bad mime type")
        self.assertEqual(item["corpusTitle"], "Pipeline Corpus")
        self.assertEqual(item["workerAccountName"], "Pipeline Bot")

    # ------------------------------------------------------------------ #
    # Corpus imports (percent failed)
    # ------------------------------------------------------------------ #

    def test_admin_corpus_imports_percent_failed(self):
        query = """
        {
          adminCorpusImports {
            totalCount
            items {
              corpusTitle
              status
              expectedDocCount
              totalCountDocs
              doneCount
              failedCount
              pendingCount
              percentFailed
            }
          }
        }
        """
        result = self._execute(query, self.admin)
        self.assertIsNone(result.errors)
        payload = result.data["adminCorpusImports"]
        self.assertEqual(payload["totalCount"], 1)
        item = payload["items"][0]
        self.assertEqual(item["corpusTitle"], "Pipeline Corpus")
        self.assertEqual(item["status"], "done")
        self.assertEqual(item["totalCountDocs"], 3)
        self.assertEqual(item["doneCount"], 1)
        self.assertEqual(item["failedCount"], 1)
        self.assertEqual(item["pendingCount"], 1)
        self.assertAlmostEqual(item["percentFailed"], 100.0 / 3.0, places=2)

    # ------------------------------------------------------------------ #
    # Bulk import sessions
    # ------------------------------------------------------------------ #

    def test_admin_bulk_import_sessions_progress_and_kind_filter(self):
        query = """
        {
          adminBulkImportSessions {
            totalCount
            items {
              filename
              kind
              status
              totalSize
              receivedSize
              receivedParts
              totalChunks
              percentComplete
              targetCorpusId
            }
          }
        }
        """
        result = self._execute(query, self.admin)
        self.assertIsNone(result.errors)
        payload = result.data["adminBulkImportSessions"]
        # Only the DOCUMENTS_ZIP session — the CORPUS_EXPORT one is excluded.
        self.assertEqual(payload["totalCount"], 1)
        item = payload["items"][0]
        self.assertEqual(item["filename"], "batch.zip")
        self.assertEqual(item["kind"], "documents_zip")
        self.assertEqual(item["totalSize"], 1000.0)
        self.assertEqual(item["receivedSize"], 500.0)
        self.assertEqual(item["receivedParts"], 1)
        self.assertEqual(item["totalChunks"], 2)
        self.assertAlmostEqual(item["percentComplete"], 50.0, places=2)
        self.assertEqual(item["targetCorpusId"], "Q29ycHVzOjE=")
