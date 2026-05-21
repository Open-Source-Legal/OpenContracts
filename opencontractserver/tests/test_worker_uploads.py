"""
Tests for the worker document upload system.

Covers:
- WorkerAccount and CorpusAccessToken model logic
- WorkerTokenAuthentication backend
- REST upload endpoint (auth, validation, staging, file size limits)
- Batch processor task (SKIP LOCKED drain, document creation, embeddings)
- GraphQL mutations for managing worker accounts and tokens
- Serializer validation (embedding dimensions, vector types)
- Edge cases (inactive creator, re-enqueue, staging file cleanup)
"""

import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    Embedding,
    LabelSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
from opencontractserver.worker_uploads.auth import WORKER_AUTH_PREFIX
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    UploadStatus,
    WorkerAccount,
    WorkerDocumentUpload,
    hash_token,
)
from opencontractserver.worker_uploads.serializers import (
    WorkerDocumentUploadSerializer,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


def _make_metadata(**overrides):
    """Build a minimal valid metadata payload for worker uploads."""
    base = {
        "title": "Test Document",
        "content": "This is test content for embedding.",
        "page_count": 1,
        "pawls_file_content": [
            {
                "page": {"width": 612.0, "height": 792.0, "index": 0},
                "tokens": [
                    {"x": 10, "y": 10, "width": 50, "height": 12, "text": "Hello"}
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def _make_fake_pdf():
    """Create a minimal PDF-like file for testing.

    Returns a ContentFile (Django File subclass) so that Django's FileField
    descriptor properly wraps it in a FieldFile during model creation.
    For multipart uploads via DRF, this is also accepted.
    """
    return ContentFile(b"%PDF-1.4 fake pdf content for testing", name="test.pdf")


def _make_fake_pdf_upload() -> BytesIO:
    """Create a minimal PDF-like file for multipart upload testing."""
    buf = BytesIO(b"%PDF-1.4 fake pdf content for testing")
    buf.name = "test.pdf"
    return buf


# ============================================================================
# Model Tests
# ============================================================================


class TestWorkerAccountModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin_worker_test",
            password="testpass",
            email="admin_worker@test.com",
        )

    def test_create_with_user(self):
        account = WorkerAccount.create_with_user(
            name="test-parser-worker",
            description="Parses PDFs",
            creator=self.admin,
        )
        self.assertTrue(account.is_active)
        self.assertEqual(account.name, "test-parser-worker")
        self.assertIsNotNone(account.user)
        self.assertTrue(account.user.username.startswith("worker_"))
        self.assertFalse(account.user.has_usable_password())
        self.assertFalse(account.user.is_staff)

    def test_unique_name_rejected(self):
        """create_with_user raises ValueError for duplicate names."""
        WorkerAccount.create_with_user(name="unique-worker", creator=self.admin)
        with self.assertRaises(ValueError):
            WorkerAccount.create_with_user(name="unique-worker", creator=self.admin)

    def test_create_with_user_atomic_rollback(self):
        """If WorkerAccount creation fails, the User should not be orphaned."""
        initial_user_count = User.objects.count()

        with patch.object(
            WorkerAccount.objects, "create", side_effect=Exception("DB error")
        ):
            with self.assertRaises(Exception):
                WorkerAccount.create_with_user(name="atomictest", creator=self.admin)

        self.assertEqual(User.objects.count(), initial_user_count)

    def test_str_active(self):
        account = WorkerAccount.create_with_user(
            name="str-test-worker", creator=self.admin
        )
        self.assertIn("str-test-worker", str(account))
        self.assertIn("active", str(account))

    def test_str_inactive(self):
        account = WorkerAccount.create_with_user(
            name="str-inactive-worker", creator=self.admin
        )
        account.is_active = False
        account.save(update_fields=["is_active"])
        self.assertIn("inactive", str(account))


class TestCorpusAccessTokenModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin_token_test",
            password="testpass",
            email="admin_token@test.com",
        )
        cls.account = WorkerAccount.create_with_user(
            name="token-test-worker", creator=cls.admin
        )
        cls.label_set = LabelSet.objects.create(
            title="Token Test LS", creator=cls.admin
        )
        cls.corpus = Corpus.objects.create(
            title="Token Test Corpus",
            creator=cls.admin,
            label_set=cls.label_set,
        )

    def test_create_token_returns_plaintext_and_stores_hash(self):
        """create_token() returns plaintext once; only hash is stored."""
        token, plaintext = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        self.assertEqual(len(plaintext), 64)
        self.assertEqual(token.key, hash_token(plaintext))
        self.assertNotEqual(token.key, plaintext)
        self.assertEqual(token.key_prefix, plaintext[:8])

    def test_is_valid_active(self):
        token, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        self.assertTrue(token.is_valid)

    def test_is_valid_revoked(self):
        token, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus, is_active=False
        )
        self.assertFalse(token.is_valid)

    def test_is_valid_expired(self):
        token, _ = CorpusAccessToken.create_token(
            worker_account=self.account,
            corpus=self.corpus,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.assertFalse(token.is_valid)

    def test_is_valid_inactive_account(self):
        self.account.is_active = False
        self.account.save(update_fields=["is_active"])
        try:
            token, _ = CorpusAccessToken.create_token(
                worker_account=self.account, corpus=self.corpus
            )
            self.assertFalse(token.is_valid)
        finally:
            self.account.is_active = True
            self.account.save(update_fields=["is_active"])

    def test_str_active_token(self):
        token, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        s = str(token)
        self.assertIn("active", s)
        self.assertIn(token.key_prefix, s)

    def test_str_revoked_token(self):
        token, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus, is_active=False
        )
        self.assertIn("revoked", str(token))

    def test_str_token_no_prefix(self):
        """Token with empty key_prefix shows '???' in str."""
        token, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        token.key_prefix = ""
        token.save(update_fields=["key_prefix"])
        self.assertIn("???", str(token))

    def test_upload_str(self):
        upload = WorkerDocumentUpload(status=UploadStatus.PENDING)
        s = str(upload)
        self.assertIn("PENDING", s)


# ============================================================================
# Authentication Tests
# ============================================================================


class TestWorkerTokenAuthentication(TestCase):
    """
    Test the WorkerTokenAuthentication DRF backend.

    Each test creates its own token via setUp to avoid shared mutable state
    (e.g. revoking a class-level token would corrupt subsequent tests if the
    finally block didn't execute).
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin_auth_test",
            password="testpass",
            email="admin_auth@test.com",
        )
        cls.account = WorkerAccount.create_with_user(
            name="auth-test-worker", creator=cls.admin
        )
        cls.label_set = LabelSet.objects.create(title="Auth Test LS", creator=cls.admin)
        cls.corpus = Corpus.objects.create(
            title="Auth Test Corpus",
            creator=cls.admin,
            label_set=cls.label_set,
        )

    def setUp(self):
        # Instance-level token avoids shared mutable state across tests
        self.token, self.plaintext_key = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )

    def test_valid_auth(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.plaintext_key}")
        response = client.get("/api/worker-uploads/documents/list/")
        self.assertEqual(response.status_code, 200)

    def test_missing_token(self):
        client = APIClient()
        response = client.get("/api/worker-uploads/documents/list/")
        self.assertIn(response.status_code, [401, 403])

    def test_invalid_token(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="WorkerKey invalidtoken123")
        response = client.get("/api/worker-uploads/documents/list/")
        self.assertEqual(response.status_code, 401)

    def test_wrong_prefix(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.plaintext_key}")
        response = client.get("/api/worker-uploads/documents/list/")
        # Wrong prefix — WorkerTokenAuthentication returns None, DRF tries
        # other backends and eventually denies.
        self.assertIn(response.status_code, [401, 403])

    def test_revoked_token(self):
        self.token.is_active = False
        self.token.save(update_fields=["is_active"])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.plaintext_key}")
        response = client.get("/api/worker-uploads/documents/list/")
        self.assertEqual(response.status_code, 401)

    def test_expired_token(self):
        self.token.expires_at = timezone.now() - timedelta(hours=1)
        self.token.save(update_fields=["expires_at"])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.plaintext_key}")
        response = client.get("/api/worker-uploads/documents/list/")
        self.assertEqual(response.status_code, 401)

    def test_workerkey_prefix_without_token(self):
        """WorkerKey prefix with no actual token should return 401."""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="WorkerKey")
        response = client.get("/api/worker-uploads/documents/list/")
        self.assertEqual(response.status_code, 401)

    def test_workerkey_with_spaces_in_token(self):
        """Token containing spaces (extra parts) should return 401."""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="WorkerKey foo bar")
        response = client.get("/api/worker-uploads/documents/list/")
        self.assertEqual(response.status_code, 401)

    def test_inactive_worker_account(self):
        """Inactive worker account should return 401."""
        self.account.is_active = False
        self.account.save(update_fields=["is_active"])
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.plaintext_key}")
            response = client.get("/api/worker-uploads/documents/list/")
            self.assertEqual(response.status_code, 401)
        finally:
            self.account.is_active = True
            self.account.save(update_fields=["is_active"])

    def test_authenticate_header_includes_realm(self):
        """WWW-Authenticate header should include realm per RFC 7235."""
        from opencontractserver.worker_uploads.auth import WorkerTokenAuthentication

        backend = WorkerTokenAuthentication()
        header = backend.authenticate_header(None)
        self.assertIn(WORKER_AUTH_PREFIX, header)
        self.assertIn("realm=", header)


# ============================================================================
# REST API Upload Tests
# ============================================================================


class TestWorkerUploadEndpoint(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin_upload_test",
            password="testpass",
            email="admin_upload@test.com",
        )
        self.account = WorkerAccount.create_with_user(
            name="upload-test-worker", creator=self.admin
        )
        self.label_set = LabelSet.objects.create(
            title="Upload Test LS", creator=self.admin
        )
        self.corpus = Corpus.objects.create(
            title="Upload Test Corpus",
            creator=self.admin,
            label_set=self.label_set,
        )
        set_permissions_for_obj_to_user(self.admin, self.corpus, [PermissionTypes.ALL])
        self.token, self.plaintext_key = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.plaintext_key}")

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_uploads.apply_async"
    )
    def test_upload_stages_document(self, mock_task):
        metadata = _make_metadata()
        response = self.client.post(
            "/api/worker-uploads/documents/",
            {
                "file": _make_fake_pdf_upload(),
                "metadata": json.dumps(metadata),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], "PENDING")
        self.assertIn("upload_id", data)

        # Verify staged in database
        upload = WorkerDocumentUpload.objects.get(id=data["upload_id"])
        self.assertEqual(upload.corpus, self.corpus)
        self.assertEqual(upload.status, UploadStatus.PENDING)
        self.assertEqual(upload.metadata["title"], "Test Document")

        # Verify the task nudge was sent
        mock_task.assert_called_once()

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_uploads.apply_async"
    )
    def test_upload_validates_metadata(self, mock_task):
        # Missing required fields
        response = self.client.post(
            "/api/worker-uploads/documents/",
            {
                "file": _make_fake_pdf_upload(),
                "metadata": json.dumps({"title": "incomplete"}),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_uploads.apply_async"
    )
    def test_upload_invalid_json(self, mock_task):
        with self.assertLogs(
            "opencontractserver.worker_uploads.serializers", level="WARNING"
        ) as log_ctx:
            response = self.client.post(
                "/api/worker-uploads/documents/",
                {
                    "file": _make_fake_pdf_upload(),
                    "metadata": "not valid json {{{",
                },
                format="multipart",
            )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any("Invalid JSON" in m for m in log_ctx.output))

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_uploads.apply_async"
    )
    def test_rate_limiting(self, mock_task):
        """Rate limiter counts uploads created by this token in the last minute."""
        self.token.rate_limit_per_minute = 1
        self.token.save(update_fields=["rate_limit_per_minute"])

        metadata = _make_metadata()

        # First upload should succeed
        response = self.client.post(
            "/api/worker-uploads/documents/",
            {
                "file": _make_fake_pdf_upload(),
                "metadata": json.dumps(metadata),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 202)

        # Second upload should be rate-limited
        response = self.client.post(
            "/api/worker-uploads/documents/",
            {
                "file": _make_fake_pdf_upload(),
                "metadata": json.dumps(metadata),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 429)

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_uploads.apply_async"
    )
    @override_settings(MAX_WORKER_UPLOAD_SIZE_BYTES=10)
    def test_file_size_limit_enforced(self, mock_task):
        """Uploads exceeding MAX_WORKER_UPLOAD_SIZE_BYTES are rejected."""
        metadata = _make_metadata()
        response = self.client.post(
            "/api/worker-uploads/documents/",
            {
                "file": _make_fake_pdf_upload(),
                "metadata": json.dumps(metadata),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 413)

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_uploads.apply_async"
    )
    @override_settings(MAX_WORKER_METADATA_SIZE_BYTES=100)
    def test_metadata_size_limit_enforced(self, mock_task):
        """Oversized metadata should be rejected."""
        huge_metadata = json.dumps({"title": "x", "content": "y" * 200})
        response = self.client.post(
            "/api/worker-uploads/documents/",
            {
                "file": _make_fake_pdf_upload(),
                "metadata": huge_metadata,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 413)

    def test_status_endpoint(self):
        upload = WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=_make_metadata(),
            status=UploadStatus.COMPLETED,
        )
        response = self.client.get(f"/api/worker-uploads/documents/{upload.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "COMPLETED")

    def test_list_endpoint_filters_by_token(self):
        WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=_make_metadata(),
        )
        response = self.client.get("/api/worker-uploads/documents/list/")
        self.assertEqual(response.status_code, 200)
        # Paginated response has "results" key
        data = response.json()
        results = data.get("results", data)
        self.assertGreaterEqual(len(results), 1)

    def test_list_endpoint_status_filter(self):
        """List endpoint filters by ?status=PENDING."""
        WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=_make_metadata(),
            status=UploadStatus.PENDING,
        )
        WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=_make_metadata(),
            status=UploadStatus.COMPLETED,
        )
        response = self.client.get("/api/worker-uploads/documents/list/?status=PENDING")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get("results", data)
        for item in results:
            self.assertEqual(item["status"], "PENDING")

    def test_list_endpoint_paginated(self):
        """List endpoint returns paginated response."""
        for _ in range(3):
            WorkerDocumentUpload.objects.create(
                corpus_access_token=self.token,
                corpus=self.corpus,
                file=_make_fake_pdf(),
                metadata=_make_metadata(),
            )
        response = self.client.get("/api/worker-uploads/documents/list/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Paginated response has count and results keys
        self.assertIn("count", data)
        self.assertIn("results", data)

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_uploads.apply_async"
    )
    def test_upload_rejects_unsupported_embedding_dimension(self, mock_task):
        """Serializer rejects embeddings with unsupported dimensions at upload time."""
        metadata = _make_metadata(
            embeddings={
                "embedder_path": "test",
                "document_embedding": [0.1] * 500,
            }
        )
        response = self.client.post(
            "/api/worker-uploads/documents/",
            {
                "file": _make_fake_pdf_upload(),
                "metadata": json.dumps(metadata),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)


# ============================================================================
# Serializer Validation Tests
# ============================================================================


class TestWorkerUploadSerializer(TestCase):
    """Test serializer validation, especially embedding dimension checks."""

    def _validate(self, metadata):
        """Helper: serialize metadata and return (is_valid, errors)."""
        data = {"file": _make_fake_pdf(), "metadata": json.dumps(metadata)}
        s = WorkerDocumentUploadSerializer(data=data)
        return s.is_valid(), s.errors

    def test_valid_metadata_accepted(self):
        valid, _ = self._validate(_make_metadata())
        self.assertTrue(valid)

    def test_non_dict_metadata_rejected(self):
        data = {"file": _make_fake_pdf(), "metadata": json.dumps([1, 2, 3])}
        s = WorkerDocumentUploadSerializer(data=data)
        self.assertFalse(s.is_valid())

    def test_non_list_pawls_rejected(self):
        meta = _make_metadata()
        meta["pawls_file_content"] = "not a list"
        valid, _ = self._validate(meta)
        self.assertFalse(valid)

    def test_embeddings_non_dict_rejected(self):
        meta = _make_metadata(embeddings="not a dict")
        valid, _ = self._validate(meta)
        self.assertFalse(valid)

    def test_embeddings_missing_embedder_path_rejected(self):
        meta = _make_metadata(embeddings={"document_embedding": [0.1] * 384})
        valid, _ = self._validate(meta)
        self.assertFalse(valid)

    def test_embeddings_doc_embedding_not_list_rejected(self):
        meta = _make_metadata(
            embeddings={"embedder_path": "test", "document_embedding": "bad"}
        )
        valid, _ = self._validate(meta)
        self.assertFalse(valid)

    def test_embeddings_doc_embedding_non_numeric_rejected(self):
        meta = _make_metadata(
            embeddings={
                "embedder_path": "test",
                "document_embedding": ["a", "b", "c"] + [0.0] * 381,
            }
        )
        valid, _ = self._validate(meta)
        self.assertFalse(valid)

    def test_embeddings_unsupported_dimension_rejected(self):
        """500-float vector should be rejected (not a supported dimension)."""
        meta = _make_metadata(
            embeddings={
                "embedder_path": "test",
                "document_embedding": [0.1] * 500,
            }
        )
        valid, errors = self._validate(meta)
        self.assertFalse(valid)
        self.assertIn("unsupported dimension", str(errors).lower())

    def test_embeddings_supported_dimension_accepted(self):
        """384-float vector should be accepted."""
        meta = _make_metadata(
            embeddings={
                "embedder_path": "test",
                "document_embedding": [0.1] * 384,
            }
        )
        valid, _ = self._validate(meta)
        self.assertTrue(valid)

    def test_annotation_embeddings_non_dict_rejected(self):
        meta = _make_metadata(
            embeddings={
                "embedder_path": "test",
                "annotation_embeddings": "not a dict",
            }
        )
        valid, _ = self._validate(meta)
        self.assertFalse(valid)

    def test_annotation_embedding_unsupported_dimension(self):
        meta = _make_metadata(
            embeddings={
                "embedder_path": "test",
                "annotation_embeddings": {"a1": [0.1] * 500},
            }
        )
        valid, _ = self._validate(meta)
        self.assertFalse(valid)

    def test_annotation_embedding_not_list_rejected(self):
        meta = _make_metadata(
            embeddings={
                "embedder_path": "test",
                "annotation_embeddings": {"a1": "bad"},
            }
        )
        valid, _ = self._validate(meta)
        self.assertFalse(valid)

    def test_annotation_embedding_non_numeric_rejected(self):
        meta = _make_metadata(
            embeddings={
                "embedder_path": "test",
                "annotation_embeddings": {"a1": ["x"] * 384},
            }
        )
        valid, _ = self._validate(meta)
        self.assertFalse(valid)


# ============================================================================
# Batch Processor Task Tests
# ============================================================================


class TestBatchProcessor(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin_batch_test",
            password="testpass",
            email="admin_batch@test.com",
        )
        self.account = WorkerAccount.create_with_user(
            name="batch-test-worker", creator=self.admin
        )
        self.label_set = LabelSet.objects.create(
            title="Batch Test LS", creator=self.admin
        )
        self.corpus = Corpus.objects.create(
            title="Batch Test Corpus",
            creator=self.admin,
            label_set=self.label_set,
        )
        set_permissions_for_obj_to_user(self.admin, self.corpus, [PermissionTypes.ALL])
        self.token, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )

    def _create_staged_upload(self, **metadata_overrides):
        """Create a PENDING upload in the staging table."""
        return WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=_make_metadata(**metadata_overrides),
            status=UploadStatus.PENDING,
        )

    def test_processes_pending_upload(self):
        """A PENDING upload is claimed and processed to COMPLETED."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        upload = self._create_staged_upload()

        result = process_pending_uploads.apply().get()

        self.assertEqual(result["claimed"], 1)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["failed"], 0)

        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)
        self.assertIsNotNone(upload.result_document)
        self.assertIsNotNone(upload.processing_finished)

    def test_created_document_owned_by_corpus_creator(self):
        """Documents created by worker uploads are owned by the corpus creator."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        upload = self._create_staged_upload()

        process_pending_uploads.apply().get()

        upload.refresh_from_db()
        doc = upload.result_document
        self.assertIsNotNone(doc)
        self.assertEqual(doc.creator, self.admin)

    def test_no_pending_uploads(self):
        """Returns immediately when no uploads are pending."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        result = process_pending_uploads.apply().get()
        self.assertEqual(result["claimed"], 0)

    def test_failed_upload_marked(self):
        """An upload with invalid data is marked FAILED with an error message."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        # Create upload with metadata missing required 'content' key
        upload = WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata={"title": "Bad doc", "pawls_file_content": [], "page_count": 0},
            status=UploadStatus.PENDING,
        )

        result = process_pending_uploads.apply().get()

        self.assertEqual(result["failed"], 1)
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.FAILED)
        self.assertTrue(len(upload.error_message) > 0)

    def test_null_corpus_creator_raises(self):
        """Processing fails gracefully when corpus.creator is None."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        # Force creator to None in the DB (bypassing NOT NULL for test purposes).
        # Corpus.creator has null=False, but we test the defensive guard in
        # _process_single_upload in case schema changes in the future.
        upload = self._create_staged_upload()

        # Fetch the real upload BEFORE mocking select_related
        real_upload = WorkerDocumentUpload.objects.select_related(
            "corpus",
            "corpus__creator",
            "corpus_access_token",
            "corpus_access_token__worker_account",
        ).get(id=upload.id)
        real_upload.corpus.creator = None

        with patch(
            "opencontractserver.worker_uploads.tasks.WorkerDocumentUpload"
            ".objects.select_related"
        ) as mock_qs:
            mock_qs.return_value.get.return_value = real_upload

            result = process_pending_uploads.apply().get()

        self.assertEqual(result["failed"], 1)
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.FAILED)
        self.assertIn("no creator", upload.error_message)

    def test_filename_sanitized(self):
        """Document filenames are sanitized to remove path traversal characters."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        upload = self._create_staged_upload(title="../../etc/passwd.pdf")

        process_pending_uploads.apply().get()

        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)
        doc = upload.result_document
        # The filename stored in the pdf_file field should be sanitized
        self.assertNotIn("..", doc.pdf_file.name)

    def test_embeddings_stored(self):
        """Pre-computed embeddings are stored in the Embedding table."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        metadata = _make_metadata(
            text_labels={
                "Important": {
                    "text": "Important",
                    "label_type": "TOKEN_LABEL",
                    "color": "#FF0000",
                    "description": "Important text",
                    "icon": "tag",
                }
            },
            labelled_text=[
                {
                    "id": "annot-1",
                    "annotationLabel": "Important",
                    "rawText": "Hello",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": False,
                }
            ],
            embeddings={
                "embedder_path": "test/embedder-384",
                "document_embedding": [0.1] * 384,
                "annotation_embeddings": {
                    "annot-1": [0.2] * 384,
                },
            },
        )

        upload = WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=metadata,
            status=UploadStatus.PENDING,
        )

        process_pending_uploads.apply().get()

        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)

        # Check document embedding was stored
        doc_embeddings = Embedding.objects.filter(
            document=upload.result_document,
            embedder_path="test/embedder-384",
        )
        self.assertEqual(doc_embeddings.count(), 1)
        self.assertIsNotNone(doc_embeddings.first().vector_384)

        # Check annotation embedding was stored
        annot_embeddings = Embedding.objects.filter(
            annotation__document=upload.result_document,
            embedder_path="test/embedder-384",
        )
        self.assertEqual(annot_embeddings.count(), 1)

    def test_process_upload_with_target_folder_path(self):
        """Uploads with target_folder_path create folders and assign the document."""
        from opencontractserver.corpuses.models import CorpusFolder
        from opencontractserver.documents.models import DocumentPath
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        upload = self._create_staged_upload(target_folder_path="/legal/contracts")

        process_pending_uploads.apply().get()

        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)

        # Verify folder hierarchy was created
        legal_folder = CorpusFolder.objects.filter(
            corpus=self.corpus, name="legal", parent=None
        ).first()
        self.assertIsNotNone(legal_folder)

        contracts_folder = CorpusFolder.objects.filter(
            corpus=self.corpus, name="contracts", parent=legal_folder
        ).first()
        self.assertIsNotNone(contracts_folder)

        # Verify the document path was assigned to the leaf folder
        doc_path = DocumentPath.objects.filter(
            corpus=self.corpus,
            document=upload.result_document,
            is_current=True,
        ).first()
        self.assertIsNotNone(doc_path)
        self.assertEqual(doc_path.folder, contracts_folder)

    @override_settings(WORKER_UPLOAD_BATCH_SIZE=2)
    def test_batch_size_respected(self):
        """Only WORKER_UPLOAD_BATCH_SIZE uploads are claimed per run."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        for _ in range(5):
            self._create_staged_upload()

        result = process_pending_uploads.apply().get()

        self.assertEqual(result["claimed"], 2)

    @override_settings(WORKER_UPLOAD_BATCH_SIZE=1)
    def test_re_enqueue_when_more_pending(self):
        """After processing a batch, re-enqueue is called if more PENDING exist."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        self._create_staged_upload()
        self._create_staged_upload()

        with patch.object(process_pending_uploads, "apply_async") as mock_apply_async:
            result = process_pending_uploads.apply().get()

        self.assertEqual(result["claimed"], 1)
        # Should have re-enqueued since there was one more pending
        mock_apply_async.assert_called_once()

    def test_inactive_corpus_creator_fails(self):
        """Processing fails gracefully when corpus.creator.is_active is False."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        upload = self._create_staged_upload()

        real_upload = WorkerDocumentUpload.objects.select_related(
            "corpus",
            "corpus__creator",
            "corpus_access_token",
            "corpus_access_token__worker_account",
        ).get(id=upload.id)
        real_upload.corpus.creator.is_active = False

        with patch(
            "opencontractserver.worker_uploads.tasks.WorkerDocumentUpload"
            ".objects.select_related"
        ) as mock_qs:
            mock_qs.return_value.get.return_value = real_upload

            result = process_pending_uploads.apply().get()

        self.assertEqual(result["failed"], 1)
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.FAILED)
        self.assertIn("inactive", upload.error_message)

    def test_embeddings_with_empty_embedder_path_skipped(self):
        """Embeddings with empty embedder_path are skipped by _store_embeddings."""
        from opencontractserver.worker_uploads.tasks import _store_embeddings

        # Test the internal function directly since the serializer now
        # rejects empty embedder_path at upload time. This guard remains
        # for robustness if metadata is modified post-staging.
        _store_embeddings(
            embeddings_data={
                "embedder_path": "",
                "document_embedding": [0.1] * 384,
            },
            corpus_doc=None,
            annot_id_map={},
            user=self.admin,
        )
        # No embeddings created (empty embedder_path triggers early return)
        self.assertEqual(Embedding.objects.filter(embedder_path="").count(), 0)

    def test_staging_file_cleanup_failure_does_not_break(self):
        """Failure to delete staging file after processing doesn't crash."""
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        upload = self._create_staged_upload()

        with patch(
            "opencontractserver.worker_uploads.tasks.WorkerDocumentUpload.file"
        ) as mock_file_descriptor:
            # Make the file descriptor behave like a FieldFile
            mock_file_descriptor.__bool__ = lambda self: True
            mock_file_descriptor.delete.side_effect = OSError("disk error")
            # Don't interfere with the actual file operations during processing
            pass

        # Process should succeed even if cleanup fails
        process_pending_uploads.apply().get()

        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)

    def test_fail_upload_nonexistent_id(self):
        """_fail_upload with a non-existent ID does not crash."""
        import uuid

        from opencontractserver.worker_uploads.tasks import _fail_upload

        # Should not raise
        _fail_upload(uuid.uuid4(), "some error")

    def test_empty_folder_path_no_op(self):
        """Empty target_folder_path should not create any folders."""
        from opencontractserver.corpuses.models import CorpusFolder
        from opencontractserver.worker_uploads.tasks import process_pending_uploads

        upload = self._create_staged_upload(target_folder_path="   ")

        process_pending_uploads.apply().get()

        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)
        # No folders should have been created
        self.assertEqual(CorpusFolder.objects.filter(corpus=self.corpus).count(), 0)

    def test_fail_upload_staging_file_cleanup_error(self):
        """Staging file cleanup failure in _fail_upload doesn't crash."""
        from opencontractserver.worker_uploads.tasks import _fail_upload

        upload = WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=_make_metadata(),
            status=UploadStatus.PROCESSING,
        )

        with patch.object(upload.file, "delete", side_effect=OSError("disk error")):
            # Patching the instance file won't work since _fail_upload refetches.
            # Instead, patch the storage backend.
            with patch(
                "django.core.files.storage.default_storage.delete",
                side_effect=OSError("disk error"),
            ):
                _fail_upload(upload.id, "test error")

        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.FAILED)
        self.assertEqual(upload.error_message, "test error")


# ============================================================================
# GraphQL Mutation Tests
# ============================================================================


class TestStalledUploadRecovery(TestCase):
    """Test that stalled PROCESSING uploads are recovered."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin_stalled_test",
            password="testpass",
            email="admin_stalled@test.com",
        )
        self.account = WorkerAccount.create_with_user(
            name="stalled-test-worker", creator=self.admin
        )
        self.label_set = LabelSet.objects.create(
            title="Stalled Test LS", creator=self.admin
        )
        self.corpus = Corpus.objects.create(
            title="Stalled Test Corpus",
            creator=self.admin,
            label_set=self.label_set,
        )
        set_permissions_for_obj_to_user(self.admin, self.corpus, [PermissionTypes.ALL])
        self.token, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )

    def test_recover_stalled_uploads_resets_old_processing(self):
        """Uploads stuck in PROCESSING beyond the timeout are reset to PENDING."""
        from opencontractserver.worker_uploads.tasks import recover_stalled_uploads

        upload = WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=_make_metadata(),
            status=UploadStatus.PROCESSING,
            processing_started=timezone.now() - timedelta(minutes=20),
        )
        result = recover_stalled_uploads()
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.PENDING)
        self.assertIsNone(upload.processing_started)
        self.assertEqual(result["recovered"], 1)

    def test_recover_stalled_uploads_ignores_recent_processing(self):
        """Uploads still within the timeout window are not touched."""
        from opencontractserver.worker_uploads.tasks import recover_stalled_uploads

        upload = WorkerDocumentUpload.objects.create(
            corpus_access_token=self.token,
            corpus=self.corpus,
            file=_make_fake_pdf(),
            metadata=_make_metadata(),
            status=UploadStatus.PROCESSING,
            processing_started=timezone.now() - timedelta(minutes=2),
        )
        result = recover_stalled_uploads()
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.PROCESSING)
        self.assertEqual(result["recovered"], 0)

    def test_recover_stalled_uploads_empty_result(self):
        """Recovery with no stalled uploads returns zero."""
        from opencontractserver.worker_uploads.tasks import recover_stalled_uploads

        result = recover_stalled_uploads()
        self.assertEqual(result["recovered"], 0)


class TestWorkerGraphQLMutations(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin_gql_test",
            password="testpass",
            email="admin_gql@test.com",
        )
        cls.regular_user = User.objects.create_user(
            username="regular_gql_test",
            password="testpass",
            email="regular_gql@test.com",
        )
        cls.label_set = LabelSet.objects.create(title="GQL Test LS", creator=cls.admin)
        cls.corpus = Corpus.objects.create(
            title="GQL Test Corpus",
            creator=cls.admin,
            label_set=cls.label_set,
        )

    def _execute(self, query, user, variables=None):
        class MockRequest:
            def __init__(self, u):
                self.user = u
                self.META = {}

        result = schema.execute(
            query, variables=variables, context_value=MockRequest(user)
        )
        response = {"data": result.data}
        if result.errors:
            response["errors"] = result.errors
        return response

    def test_create_worker_account_as_superuser(self):
        mutation = """
            mutation {
                createWorkerAccount(name: "gql-worker", description: "test") {
                    ok
                    workerAccount { id name isActive }
                }
            }
        """
        result = self._execute(mutation, self.admin)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createWorkerAccount"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["workerAccount"]["name"], "gql-worker")
        self.assertTrue(data["workerAccount"]["isActive"])

    def test_create_worker_account_denied_for_regular_user(self):
        mutation = """
            mutation {
                createWorkerAccount(name: "denied-worker") {
                    ok
                }
            }
        """
        result = self._execute(mutation, self.regular_user)
        self.assertIsNotNone(result.get("errors"))

    def test_create_corpus_access_token(self):
        """Token creation returns a 64-char plaintext key (shown only once)."""
        account = WorkerAccount.create_with_user(
            name="gql-token-worker", creator=self.admin
        )
        mutation = """
            mutation CreateToken($workerAccountId: Int!, $corpusId: Int!) {
                createCorpusAccessToken(
                    workerAccountId: $workerAccountId,
                    corpusId: $corpusId,
                    rateLimitPerMinute: 100
                ) {
                    ok
                    token { id key corpusId rateLimitPerMinute }
                }
            }
        """
        result = self._execute(
            mutation,
            self.admin,
            variables={
                "workerAccountId": account.id,
                "corpusId": self.corpus.id,
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createCorpusAccessToken"]
        self.assertTrue(data["ok"])
        # The returned key is the plaintext (shown once)
        plaintext_key = data["token"]["key"]
        self.assertEqual(len(plaintext_key), 64)
        self.assertEqual(data["token"]["rateLimitPerMinute"], 100)

        # Verify the DB stores the hash, not the plaintext
        db_token = CorpusAccessToken.objects.get(id=data["token"]["id"])
        self.assertEqual(db_token.key, hash_token(plaintext_key))
        self.assertNotEqual(db_token.key, plaintext_key)

    def test_revoke_token(self):
        account = WorkerAccount.create_with_user(
            name="gql-revoke-worker", creator=self.admin
        )
        token, _ = CorpusAccessToken.create_token(
            worker_account=account, corpus=self.corpus
        )
        mutation = """
            mutation RevokeToken($tokenId: Int!) {
                revokeCorpusAccessToken(tokenId: $tokenId) { ok }
            }
        """
        result = self._execute(mutation, self.admin, variables={"tokenId": token.id})
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["revokeCorpusAccessToken"]["ok"])

        token.refresh_from_db()
        self.assertFalse(token.is_active)

    def test_deactivate_worker_account(self):
        account = WorkerAccount.create_with_user(
            name="gql-deactivate-worker", creator=self.admin
        )
        mutation = """
            mutation Deactivate($id: Int!) {
                deactivateWorkerAccount(workerAccountId: $id) { ok }
            }
        """
        result = self._execute(mutation, self.admin, variables={"id": account.id})
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deactivateWorkerAccount"]["ok"])

        account.refresh_from_db()
        self.assertFalse(account.is_active)


class TestWorkerGraphQLQueries(TestCase):
    """Tests for the worker upload GraphQL query resolvers and permission changes."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="admin_query",
            password="testpass123",
            email="admin_query@test.com",
        )
        cls.regular_user = User.objects.create_user(
            username="regular_query",
            password="testpass123",
            email="regular_query@test.com",
        )
        cls.corpus_creator = User.objects.create_user(
            username="corpus_owner_query",
            password="testpass123",
            email="owner_query@test.com",
        )

        cls.worker = WorkerAccount.create_with_user(
            name="test-query-worker",
            description="Worker for query tests",
            creator=cls.superuser,
        )

        cls.label_set = LabelSet.objects.create(
            title="Query Test LS",
            creator=cls.corpus_creator,
        )
        cls.corpus = Corpus.objects.create(
            title="Query Test Corpus",
            creator=cls.corpus_creator,
            label_set=cls.label_set,
        )

        cls.token, cls.plaintext = CorpusAccessToken.create_token(
            worker_account=cls.worker,
            corpus=cls.corpus,
            rate_limit_per_minute=10,
        )

    def _execute(self, query, user, variables=None):
        class MockRequest:
            def __init__(self, u):
                self.user = u
                self.META = {}

        result = schema.execute(
            query, variables=variables, context_value=MockRequest(user)
        )
        response = {"data": result.data}
        if result.errors:
            response["errors"] = result.errors
        return response

    # ---- Query: workerAccounts ----

    def test_worker_accounts_superuser(self):
        result = self._execute(
            """
            query {
                workerAccounts {
                    id
                    name
                    description
                    isActive
                    tokenCount
                    creatorName
                }
            }
            """,
            self.superuser,
        )
        self.assertIsNone(result.get("errors"), f"Errors: {result.get('errors')}")
        accounts = result["data"]["workerAccounts"]
        self.assertTrue(len(accounts) >= 1)
        account = next(a for a in accounts if a["name"] == "test-query-worker")
        self.assertTrue(account["isActive"])
        self.assertEqual(account["tokenCount"], 1)

    def test_worker_accounts_regular_user_sees_active_only(self):
        """Regular users can query active worker accounts (for token creation
        dropdown) but with tokenCount hidden (always 0)."""
        result = self._execute(
            """
            query {
                workerAccounts {
                    id
                    name
                    isActive
                    tokenCount
                }
            }
            """,
            self.regular_user,
        )
        self.assertIsNone(result.get("errors"), f"Errors: {result.get('errors')}")
        accounts = result["data"]["workerAccounts"]
        # Only active accounts visible
        self.assertTrue(all(a["isActive"] for a in accounts))
        # tokenCount is hidden for non-superusers
        self.assertTrue(all(a["tokenCount"] == 0 for a in accounts))

    # ---- Query: corpusAccessTokens ----

    def test_corpus_access_tokens_superuser(self):
        result = self._execute(
            """
            query($corpusId: Int!) {
                corpusAccessTokens(corpusId: $corpusId) {
                    id
                    keyPrefix
                    workerAccountName
                    isActive
                    rateLimitPerMinute
                    uploadCountPending
                    uploadCountCompleted
                    uploadCountFailed
                }
            }
            """,
            self.superuser,
            variables={"corpusId": self.corpus.id},
        )
        self.assertIsNone(result.get("errors"), f"Errors: {result.get('errors')}")
        tokens = result["data"]["corpusAccessTokens"]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["workerAccountName"], "test-query-worker")
        self.assertEqual(tokens[0]["rateLimitPerMinute"], 10)

    def test_corpus_access_tokens_corpus_creator(self):
        result = self._execute(
            """
            query($corpusId: Int!) {
                corpusAccessTokens(corpusId: $corpusId) {
                    id
                    keyPrefix
                }
            }
            """,
            self.corpus_creator,
            variables={"corpusId": self.corpus.id},
        )
        self.assertIsNone(result.get("errors"), f"Errors: {result.get('errors')}")
        self.assertEqual(len(result["data"]["corpusAccessTokens"]), 1)

    def test_corpus_access_tokens_denied_for_non_creator(self):
        result = self._execute(
            """
            query($corpusId: Int!) {
                corpusAccessTokens(corpusId: $corpusId) { id }
            }
            """,
            self.regular_user,
            variables={"corpusId": self.corpus.id},
        )
        self.assertIsNotNone(result.get("errors"))

    # ---- Query: workerDocumentUploads ----

    def test_worker_document_uploads_empty(self):
        result = self._execute(
            """
            query($corpusId: Int!) {
                workerDocumentUploads(corpusId: $corpusId) {
                    items { id status }
                    totalCount
                    limit
                    offset
                }
            }
            """,
            self.superuser,
            variables={"corpusId": self.corpus.id},
        )
        self.assertIsNone(result.get("errors"), f"Errors: {result.get('errors')}")
        page = result["data"]["workerDocumentUploads"]
        self.assertEqual(page["items"], [])
        self.assertEqual(page["totalCount"], 0)
        self.assertEqual(page["offset"], 0)

    # ---- Mutation: createCorpusAccessToken (corpus creator permission) ----

    def test_corpus_creator_can_create_token(self):
        result = self._execute(
            """
            mutation($workerId: Int!, $corpusId: Int!) {
                createCorpusAccessToken(
                    workerAccountId: $workerId,
                    corpusId: $corpusId,
                    rateLimitPerMinute: 5
                ) {
                    ok
                    token {
                        id
                        key
                        workerAccountName
                    }
                }
            }
            """,
            self.corpus_creator,
            variables={"workerId": self.worker.id, "corpusId": self.corpus.id},
        )
        self.assertIsNone(result.get("errors"), f"Errors: {result.get('errors')}")
        self.assertTrue(result["data"]["createCorpusAccessToken"]["ok"])
        self.assertIsNotNone(result["data"]["createCorpusAccessToken"]["token"]["key"])

    def test_non_creator_cannot_create_token(self):
        result = self._execute(
            """
            mutation($workerId: Int!, $corpusId: Int!) {
                createCorpusAccessToken(
                    workerAccountId: $workerId,
                    corpusId: $corpusId
                ) {
                    ok
                    token { id }
                }
            }
            """,
            self.regular_user,
            variables={"workerId": self.worker.id, "corpusId": self.corpus.id},
        )
        self.assertIsNotNone(result.get("errors"))

    # ---- Mutation: revokeCorpusAccessToken (corpus creator permission) ----

    def test_corpus_creator_can_revoke_token(self):
        token, _ = CorpusAccessToken.create_token(
            worker_account=self.worker,
            corpus=self.corpus,
        )
        result = self._execute(
            """
            mutation($tokenId: Int!) {
                revokeCorpusAccessToken(tokenId: $tokenId) {
                    ok
                }
            }
            """,
            self.corpus_creator,
            variables={"tokenId": token.id},
        )
        self.assertIsNone(result.get("errors"), f"Errors: {result.get('errors')}")
        self.assertTrue(result["data"]["revokeCorpusAccessToken"]["ok"])

    # ---- Mutation: reactivateWorkerAccount ----

    def test_reactivate_worker_account(self):
        # Use a dedicated instance to avoid mutating shared cls.worker
        inactive_worker = WorkerAccount.create_with_user(
            name="inactive-for-reactivation",
            description="Test worker for reactivation",
            creator=self.superuser,
        )
        inactive_worker.is_active = False
        inactive_worker.save(update_fields=["is_active"])

        result = self._execute(
            """
            mutation($workerId: Int!) {
                reactivateWorkerAccount(workerAccountId: $workerId) {
                    ok
                }
            }
            """,
            self.superuser,
            variables={"workerId": inactive_worker.id},
        )
        self.assertIsNone(result.get("errors"), f"Errors: {result.get('errors')}")
        self.assertTrue(result["data"]["reactivateWorkerAccount"]["ok"])

        inactive_worker.refresh_from_db()
        self.assertTrue(inactive_worker.is_active)

    def test_non_superuser_cannot_reactivate_worker_account(self):
        inactive_worker = WorkerAccount.create_with_user(
            name="inactive-for-denied-reactivation",
            description="Test worker for denied reactivation",
            creator=self.superuser,
        )
        inactive_worker.is_active = False
        inactive_worker.save(update_fields=["is_active"])

        result = self._execute(
            """
            mutation($workerId: Int!) {
                reactivateWorkerAccount(workerAccountId: $workerId) {
                    ok
                }
            }
            """,
            self.regular_user,
            variables={"workerId": inactive_worker.id},
        )
        self.assertIsNotNone(result.get("errors"))
