"""Receipt recovery tested against real PostgreSQL transactions and HTTP views."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import patch
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.tests.test_worker_uploads import _make_metadata
from opencontractserver.users.models import User
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    WorkerAccount,
    WorkerDocumentUpload,
)
from opencontractserver.worker_uploads.tasks import (
    _fail_upload,
    _process_single_upload,
    process_pending_uploads,
    recover_stalled_uploads,
)
from opencontractserver.worker_uploads.upload_recovery import stage_upload


@override_settings(WORKER_UPLOAD_BATCH_SIZE=10, WORKER_UPLOAD_STALE_MINUTES=1)
class UploadRecoveryTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="recovery-owner")
        self.corpus = Corpus.objects.create(title="Recovery", creator=self.owner)
        self.worker = WorkerAccount.create_with_user(
            name="recovery-worker", creator=self.owner
        )
        self.token, self.secret = CorpusAccessToken.create_token(
            worker_account=self.worker, corpus=self.corpus
        )
        self.client = self.client_for(self.secret)
        self.nudge = patch(
            "opencontractserver.worker_uploads.views.process_pending_uploads.apply_async"
        ).start()
        self.addCleanup(patch.stopall)
        patch(
            "opencontractserver.tasks.doc_tasks.extract_thumbnail.apply_async"
        ).start()

    def client_for(self, secret):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {secret}")
        return client

    def post(
        self, *, key="source-1", source=b"original source", metadata=None, client=None
    ):
        headers = {"HTTP_IDEMPOTENCY_KEY": key} if key is not None else {}
        return (client or self.client).post(
            "/api/worker-uploads/documents/",
            {
                "file": ContentFile(source, name="source.txt"),
                "metadata": json.dumps(
                    metadata or _make_metadata(file_type="text/plain")
                ),
            },
            format="multipart",
            **headers,
        )

    def stage(self):
        response = self.post()
        self.assertEqual(response.status_code, 202, response.json())
        return WorkerDocumentUpload.objects.get(pk=response.json()["upload_id"])

    def claim(self, upload):
        fence = uuid4()
        WorkerDocumentUpload.objects.filter(pk=upload.pk).update(
            status="PROCESSING",
            processing_token=fence,
            processing_attempts=1,
            processing_started=timezone.now(),
        )
        return fence

    def test_concurrent_posts_and_lost_response_return_one_receipt_and_document(self):
        barrier = Barrier(2)

        def submit():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = self.post(client=self.client_for(self.secret))
                return response.status_code, response.json()["upload_id"]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual([r[0] for r in replies], [202, 202])
        self.assertEqual(replies[0][1], replies[1][1])
        # A caller that lost both responses can resolve its durable key.
        lookup = self.client.get("/api/worker-uploads/documents/by-key/source-1/")
        self.assertEqual(lookup.json()["upload_id"], replies[0][1])
        self.assertEqual(WorkerDocumentUpload.objects.count(), 1)
        process_pending_uploads()
        self.assertEqual(
            DocumentPath.objects.filter(corpus=self.corpus, is_current=True).count(), 1
        )
        self.assertEqual(self.post().json()["upload_id"], replies[0][1])

    def test_source_or_semantic_metadata_changes_conflict_but_json_key_order_does_not(
        self,
    ):
        upload = self.stage()
        metadata = _make_metadata(file_type="text/plain")
        reordered = dict(reversed(list(metadata.items())))
        self.assertEqual(
            self.post(metadata=reordered).json()["upload_id"], str(upload.pk)
        )
        for kwargs in (
            {"source": b"changed"},
            {"metadata": {**metadata, "title": "changed"}},
            {"metadata": {**metadata, "preparation_identity": "new-model"}},
        ):
            with self.subTest(change=kwargs):
                response = self.post(**kwargs)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["error"], "idempotency_conflict")
        self.assertEqual(WorkerDocumentUpload.objects.count(), 1)

    def test_legacy_posts_keep_creating_independent_receipts(self):
        self.assertNotEqual(
            self.post(key=None).json()["upload_id"],
            self.post(key=None).json()["upload_id"],
        )

    def test_replacement_token_can_lookup_status_and_retry_after_original_is_deleted(
        self,
    ):
        upload = self.stage()
        _fail_upload(upload.pk, "temporary")
        replacement, secret = CorpusAccessToken.create_token(
            worker_account=self.worker, corpus=self.corpus
        )
        self.token.delete()
        client = self.client_for(secret)
        self.assertEqual(
            client.get(f"/api/worker-uploads/documents/{upload.pk}/").status_code, 200
        )
        self.assertEqual(
            client.get("/api/worker-uploads/documents/by-key/source-1/").json()[
                "upload_id"
            ],
            str(upload.pk),
        )
        self.assertEqual(
            client.post(
                f"/api/worker-uploads/documents/{upload.pk}/retry/"
            ).status_code,
            202,
        )
        upload.refresh_from_db()
        self.assertEqual(upload.corpus_access_token_id, replacement.pk)
        process_pending_uploads()
        upload.refresh_from_db()
        self.assertEqual(upload.status, "COMPLETED")

    def test_other_worker_or_corpus_cannot_observe_or_retry_receipt_and_revoked_token_is_rejected(
        self,
    ):
        upload = self.stage()
        other = WorkerAccount.create_with_user(name="other-worker", creator=self.owner)
        other_corpus = Corpus.objects.create(title="Other corpus", creator=self.owner)
        for worker, corpus in ((other, self.corpus), (self.worker, other_corpus)):
            _, secret = CorpusAccessToken.create_token(
                worker_account=worker, corpus=corpus
            )
            client = self.client_for(secret)
            self.assertFalse(
                client.get("/api/worker-uploads/documents/by-key/source-1/").json()[
                    "found"
                ]
            )
            self.assertEqual(
                client.get(f"/api/worker-uploads/documents/{upload.pk}/").status_code,
                404,
            )
            self.assertEqual(
                client.post(
                    f"/api/worker-uploads/documents/{upload.pk}/retry/"
                ).status_code,
                404,
            )
        self.token.is_active = False
        self.token.save(update_fields=["is_active"])
        self.assertEqual(
            self.client.get(
                "/api/worker-uploads/documents/by-key/source-1/"
            ).status_code,
            401,
        )

    def test_crash_before_commit_keeps_source_and_rolls_back_documents_then_redelivery_is_harmless(
        self,
    ):
        upload = self.stage()
        fence = self.claim(upload)
        with patch(
            "opencontractserver.worker_uploads.tasks.create_structural_annotation_set",
            side_effect=RuntimeError("before commit"),
        ):
            with self.assertRaisesRegex(RuntimeError, "before commit"):
                _process_single_upload(upload.pk, fence)
        self.assertEqual(Document.objects.count(), 0)
        self.assertTrue(upload.file.storage.exists(upload.file.name))
        self.assertTrue(_process_single_upload(upload.pk, fence))
        document_count = Document.objects.count()
        # Models committed, but the worker lost its acknowledgement.
        self.assertFalse(_process_single_upload(upload.pk, fence))
        _fail_upload(upload.pk, "late failure", fence)
        upload.refresh_from_db()
        self.assertEqual(upload.status, "COMPLETED")
        self.assertEqual(Document.objects.count(), document_count)
        self.assertEqual(
            DocumentPath.objects.filter(corpus=self.corpus, is_current=True).count(), 1
        )

    def test_recovery_skips_a_live_transaction_even_when_its_start_time_is_stale(self):
        upload = self.stage()
        fence = self.claim(upload)
        WorkerDocumentUpload.objects.filter(pk=upload.pk).update(
            processing_started=timezone.now() - timedelta(minutes=5)
        )
        locked, release = Event(), Event()

        def hold_transaction():
            close_old_connections()
            try:
                with transaction.atomic():
                    WorkerDocumentUpload.objects.select_for_update().get(pk=upload.pk)
                    locked.set()
                    if not release.wait(timeout=10):
                        raise RuntimeError("test did not release transaction")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(hold_transaction)
            try:
                self.assertTrue(locked.wait(timeout=10))
                self.assertEqual(recover_stalled_uploads()["recovered"], 0)
            finally:
                release.set()
            future.result(timeout=10)
        self.assertEqual(recover_stalled_uploads()["recovered"], 1)
        self.assertFalse(_process_single_upload(upload.pk, fence))
        _fail_upload(upload.pk, "stale delivery", fence)
        upload.refresh_from_db()
        self.assertEqual(upload.status, "PENDING")
        process_pending_uploads()
        upload.refresh_from_db()
        self.assertEqual(upload.status, "COMPLETED")
        self.assertEqual(upload.processing_attempts, 2)
        self.assertEqual(upload.error_history[0]["message"], "processing_abandoned")

    def test_failed_attempts_reuse_source_and_stop_after_three_with_error_history(self):
        upload = self.stage()
        original_name, original_metadata = upload.file.name, upload.metadata
        with patch(
            "opencontractserver.worker_uploads.tasks._prepare_labels",
            side_effect=RuntimeError("temporary dependency"),
        ):
            for attempt in range(1, 4):
                process_pending_uploads()
                upload.refresh_from_db()
                self.assertEqual(upload.processing_attempts, attempt)
                self.assertEqual(upload.status, "FAILED")
                self.assertEqual(upload.file.name, original_name)
                self.assertEqual(upload.metadata, original_metadata)
                self.assertTrue(upload.file.storage.exists(original_name))
                response = self.client.post(
                    f"/api/worker-uploads/documents/{upload.pk}/retry/"
                )
                self.assertEqual(response.status_code, 409 if attempt == 3 else 202)
        self.assertEqual(response.json()["error"], "retry_exhausted")
        self.assertEqual([e["attempt"] for e in upload.error_history], [1, 2, 3])
        self.assertEqual(Document.objects.count(), 0)

    def test_crash_during_admission_does_not_publish_receipt(self):
        with self.assertRaisesRegex(RuntimeError, "before commit"):
            with transaction.atomic():
                stage_upload(
                    self.token,
                    ContentFile(b"source", name="source.txt"),
                    _make_metadata(),
                    "interrupted",
                )
                raise RuntimeError("before commit")
        lookup = self.client.get("/api/worker-uploads/documents/by-key/interrupted/")
        self.assertEqual(
            lookup.json(),
            {"schema_version": 1, "client_key": "interrupted", "found": False},
        )
        self.assertEqual(self.post(key="interrupted").status_code, 202)

    def test_stale_attempt_exhaustion_is_terminal_and_recovery_scan_is_bounded(self):
        first = self.stage()
        second = WorkerDocumentUpload.objects.get(
            pk=self.post(key="source-2").json()["upload_id"]
        )
        WorkerDocumentUpload.objects.filter(pk__in=[first.pk, second.pk]).update(
            status="PROCESSING",
            processing_attempts=3,
            processing_started=timezone.now() - timedelta(minutes=5),
            processing_token=uuid4(),
        )
        with override_settings(WORKER_UPLOAD_BATCH_SIZE=1):
            self.assertEqual(recover_stalled_uploads()["recovered"], 1)
        self.assertEqual(
            WorkerDocumentUpload.objects.filter(status="PROCESSING").count(), 1
        )
        self.assertEqual(
            WorkerDocumentUpload.objects.filter(status="FAILED").count(), 1
        )
        recover_stalled_uploads()
        first.refresh_from_db()
        self.assertIsNotNone(first.processing_finished)
        self.assertEqual(
            self.client.post(f"/api/worker-uploads/documents/{first.pk}/retry/").json()[
                "error"
            ],
            "retry_exhausted",
        )
        self.assertEqual(process_pending_uploads()["claimed"], 0)

    def test_replay_returns_existing_receipt_even_after_new_upload_rate_limit_is_reached(
        self,
    ):
        self.token.rate_limit_per_minute = 1
        self.token.save(update_fields=["rate_limit_per_minute"])
        first = self.post()
        self.assertEqual(self.post().json()["upload_id"], first.json()["upload_id"])
        self.assertEqual(self.post(key="different-source").status_code, 429)
