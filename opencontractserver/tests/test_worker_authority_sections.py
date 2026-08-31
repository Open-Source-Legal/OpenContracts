"""
Tests for the authority-section batch push endpoint and its drain task.

Covers:
- POST /api/worker-uploads/authority-sections/ (auth, validation, caps,
  rate limiting, staging)
- Status endpoint token scoping (no cross-token existence oracle)
- Drain task: bootstrap into the token corpus, equivalence upsert outcomes,
  failure isolation, idempotent re-push, revoked-token batches, the
  per-invocation batch cap + self re-enqueue, and drain-time token
  re-validation (revocation/capability loss stops staged batches)
"""

from typing import Any, ClassVar
from unittest.mock import PropertyMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    UploadStatus,
    WorkerAccount,
    WorkerAuthoritySectionBatch,
)

User = get_user_model()

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/worker-uploads/authority-sections/"


def _make_payload(**overrides):
    """Minimal valid authority-section payload."""
    base = {
        "sections": [
            {
                "key": "hr:119-1",
                "heading": "H.R. 1 — Test Bill (IH)",
                "text": "Be it enacted by the Senate and House of Representatives...",
                "source_url": "https://www.govinfo.gov/bulkdata/BILLS/119/1/hr/BILLS-119hr1ih.xml",
                "metadata": {"congress": 119, "bill_number": 1},
            }
        ],
        "equivalences": [
            {
                "from_key": "hr:1",
                "to_key": "hr:119-1",
                "note": "unqualified -> current congress",
            }
        ],
    }
    base.update(overrides)
    return base


class SectionBatchTestBase(TestCase):
    owner: ClassVar[Any]
    corpus: ClassVar[Corpus]
    account: ClassVar[WorkerAccount]

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="corpus-owner", password="irrelevant"
        )
        cls.corpus = Corpus.objects.create(title="Bills Corpus", creator=cls.owner)
        cls.account = WorkerAccount.create_with_user(name="bill-feed")

    def setUp(self):
        self.token, self.plaintext = CorpusAccessToken.create_token(
            worker_account=self.account,
            corpus=self.corpus,
            can_push_authority_sections=True,
        )
        self.client_api = APIClient()
        self.client_api.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.plaintext}")


class TestSectionBatchEndpoint(SectionBatchTestBase):
    @patch(
        "opencontractserver.worker_uploads.views.process_pending_section_batches.apply_async"
    )
    def test_post_valid_payload_stages_batch_and_returns_202(self, mock_nudge):
        response = self.client_api.post(ENDPOINT, _make_payload(), format="json")
        assert response.status_code == 202, response.content
        batch = WorkerAuthoritySectionBatch.objects.get(id=response.data["id"])
        assert batch.status == UploadStatus.PENDING
        assert batch.corpus_id == self.corpus.id
        assert batch.corpus_access_token_id == self.token.id
        assert batch.payload["sections"][0]["key"] == "hr:119-1"
        mock_nudge.assert_called_once()

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_section_batches.apply_async"
    )
    def test_post_invalid_section_spec_is_rejected_400(self, mock_nudge):
        payload = _make_payload(sections=[{"key": "hr:119-1", "heading": "no text"}])
        response = self.client_api.post(ENDPOINT, payload, format="json")
        assert response.status_code == 400
        assert "sections[0]" in str(response.data)
        assert not WorkerAuthoritySectionBatch.objects.exists()
        mock_nudge.assert_not_called()

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_section_batches.apply_async"
    )
    def test_post_invalid_equivalence_key_is_rejected_400(self, mock_nudge):
        payload = _make_payload(
            equivalences=[{"from_key": "not a key!!", "to_key": "hr:119-1"}]
        )
        response = self.client_api.post(ENDPOINT, payload, format="json")
        assert response.status_code == 400
        assert "equivalences[0]" in str(response.data)
        mock_nudge.assert_not_called()

    @override_settings(MAX_AUTHORITY_SECTION_PAYLOAD_BYTES=100)
    @patch(
        "opencontractserver.worker_uploads.views.process_pending_section_batches.apply_async"
    )
    def test_post_oversized_payload_is_rejected_413(self, mock_nudge):
        response = self.client_api.post(ENDPOINT, _make_payload(), format="json")
        assert response.status_code == 413
        mock_nudge.assert_not_called()

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_section_batches.apply_async"
    )
    def test_post_non_string_equivalence_note_is_rejected_400(self, mock_nudge):
        """A non-string note must 400 at push, not fail the whole batch at drain."""
        payload = _make_payload()
        payload["equivalences"][0]["note"] = {"not": "a string"}
        response = self.client_api.post(ENDPOINT, payload, format="json")
        assert response.status_code == 400, response.content
        assert not WorkerAuthoritySectionBatch.objects.exists()

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_section_batches.apply_async"
    )
    def test_post_normalizes_equivalence_keys_into_stored_payload(self, mock_nudge):
        payload = _make_payload()
        payload["equivalences"][0]["from_key"] = "  hr:1  "
        payload["equivalences"][0]["to_key"] = "hr:119-1\n"
        response = self.client_api.post(ENDPOINT, payload, format="json")
        assert response.status_code == 202, response.content
        batch = WorkerAuthoritySectionBatch.objects.get(id=response.data["id"])
        assert batch.payload["equivalences"][0]["from_key"] == "hr:1"
        assert batch.payload["equivalences"][0]["to_key"] == "hr:119-1"

    @override_settings(MAX_AUTHORITY_SECTION_PAYLOAD_BYTES=64)
    def test_oversized_payload_rejected_on_declared_length_without_buffering(self):
        """The Content-Length early-out must fire BEFORE request.body is read.

        Reading request.body buffers the whole request into memory bounded
        only by DATA_UPLOAD_MAX_MEMORY_SIZE, which is orders of magnitude
        above this endpoint's own cap.
        """
        with patch(
            "django.http.request.HttpRequest.body",
            new_callable=PropertyMock,
            side_effect=AssertionError("request.body was read before the cap"),
        ):
            response = self.client_api.post(ENDPOINT, _make_payload(), format="json")
        assert response.status_code == 413, response.content
        assert not WorkerAuthoritySectionBatch.objects.exists()

    def test_post_without_token_is_401(self):
        response = APIClient().post(ENDPOINT, _make_payload(), format="json")
        assert response.status_code == 401

    def test_post_without_capability_is_403(self):
        # A plain document-upload token (the pre-existing kind) must NOT gain
        # the authority-section capability silently.
        _, plaintext = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {plaintext}")
        response = client.post(ENDPOINT, _make_payload(), format="json")
        assert response.status_code == 403

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_section_batches.apply_async"
    )
    def test_status_endpoint_scopes_to_own_token(self, mock_nudge):
        response = self.client_api.post(ENDPOINT, _make_payload(), format="json")
        batch_id = response.data["id"]

        own = self.client_api.get(f"{ENDPOINT}{batch_id}/")
        assert own.status_code == 200
        assert own.data["status"] == UploadStatus.PENDING

        other_account = WorkerAccount.create_with_user(name="other-feed")
        _, other_plaintext = CorpusAccessToken.create_token(
            worker_account=other_account, corpus=self.corpus
        )
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {other_plaintext}")
        assert other_client.get(f"{ENDPOINT}{batch_id}/").status_code == 404

    @patch(
        "opencontractserver.worker_uploads.views.process_pending_section_batches.apply_async"
    )
    def test_rate_limit_counts_section_batches(self, mock_nudge):
        limited_token, limited_plaintext = CorpusAccessToken.create_token(
            worker_account=self.account,
            corpus=self.corpus,
            rate_limit_per_minute=1,
            can_push_authority_sections=True,
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {limited_plaintext}")
        assert client.post(ENDPOINT, _make_payload(), format="json").status_code == 202
        second = client.post(ENDPOINT, _make_payload(), format="json")
        assert second.status_code == 429
        assert second["Retry-After"] == "60"


class TestSectionBatchDrain(SectionBatchTestBase):
    def _stage(self, payload=None, token=None):
        return WorkerAuthoritySectionBatch.objects.create(
            corpus_access_token=token or self.token,
            corpus=self.corpus,
            payload=payload or _make_payload(),
            status=UploadStatus.PENDING,
        )

    def _drain(self):
        from opencontractserver.worker_uploads.tasks import (
            process_pending_section_batches,
        )

        return process_pending_section_batches.apply().get()

    def test_drain_bootstraps_sections_into_token_corpus(self):
        payload = _make_payload()
        payload["sections"].append(
            {
                "key": "hr:119-2",
                "heading": "H.R. 2 — Second Test Bill (IH)",
                "text": "Section 1861 of the Social Security Act is amended...",
            }
        )
        self._stage(payload)
        result = self._drain()
        assert result["completed"] == 1

        batch = WorkerAuthoritySectionBatch.objects.get()
        assert batch.status == UploadStatus.COMPLETED, batch.error_message
        assert batch.report["bootstrap"]["documents_created"] == 2
        assert Document.objects.filter(title="H.R. 1 — Test Bill (IH)").exists()
        assert Document.objects.filter(title="H.R. 2 — Second Test Bill (IH)").exists()

    def test_drain_upserts_equivalences_with_worker_source(self):
        self._stage()
        self._drain()
        batch = WorkerAuthoritySectionBatch.objects.get()
        assert batch.report["equivalences"]["created"] == 1
        row = AuthorityKeyEquivalence.objects.get(from_key="hr:1", to_key="hr:119-1")
        assert row.source == "worker:bill-feed"

    def test_drain_marks_failed_on_bad_payload_without_stalling_queue(self):
        bad = self._stage(payload={"sections": [{"key": "hr:119-9"}]})
        good = self._stage()
        result = self._drain()
        assert result == {"completed": 1, "failed": 1}
        bad.refresh_from_db()
        good.refresh_from_db()
        assert bad.status == UploadStatus.FAILED
        assert "sections[0]" in bad.error_message
        assert good.status == UploadStatus.COMPLETED

    def test_drain_is_idempotent_on_unchanged_text(self):
        self._stage()
        self._drain()
        self._stage()
        self._drain()
        second = WorkerAuthoritySectionBatch.objects.order_by("created").last()
        assert second is not None
        assert second.status == UploadStatus.COMPLETED
        assert second.report["bootstrap"]["documents_skipped"] == 1
        assert Document.objects.filter(title="H.R. 1 — Test Bill (IH)").count() == 1

    @override_settings(WORKER_AUTHORITY_SECTION_BATCH_CAP=2)
    @patch(
        "opencontractserver.worker_uploads.tasks."
        "process_pending_section_batches.apply_async"
    )
    def test_drain_caps_batches_per_run_and_reenqueues(self, mock_reenqueue):
        """One execution must not drain an unbounded backlog."""
        for _ in range(3):
            self._stage()

        result = self._drain()

        assert result["completed"] == 2
        assert (
            WorkerAuthoritySectionBatch.objects.filter(
                status=UploadStatus.PENDING
            ).count()
            == 1
        )
        mock_reenqueue.assert_called_once_with(
            queue="worker_uploads", countdown=1, ignore_result=True
        )

    @patch(
        "opencontractserver.worker_uploads.tasks."
        "process_pending_section_batches.apply_async"
    )
    def test_drain_does_not_reenqueue_when_queue_is_empty(self, mock_reenqueue):
        self._stage()
        self._drain()
        mock_reenqueue.assert_not_called()

    def test_drain_fails_batch_when_token_revoked_after_push(self):
        """Revoking a token must stop batches staged before the revocation."""
        batch = self._stage()
        self.token.is_active = False
        self.token.save(update_fields=["is_active"])

        result = self._drain()

        assert result["failed"] == 1
        batch.refresh_from_db()
        assert batch.status == UploadStatus.FAILED
        assert "revoked or expired" in batch.error_message
        assert not Document.objects.exists()

    def test_drain_fails_batch_when_capability_revoked_after_push(self):
        batch = self._stage()
        self.token.can_push_authority_sections = False
        self.token.save(update_fields=["can_push_authority_sections"])

        result = self._drain()

        assert result["failed"] == 1
        batch.refresh_from_db()
        assert batch.status == UploadStatus.FAILED
        assert "capability" in batch.error_message
        assert not Document.objects.exists()

    def test_drain_keeps_bootstrap_report_when_equivalence_upsert_fails(self):
        """Documents were really created — a later equivalence failure must
        not leave the batch reporting nothing about them."""
        batch = self._stage()
        with patch(
            "opencontractserver.enrichment.services."
            "authority_equivalence_ingest.upsert_equivalence",
            side_effect=RuntimeError("equivalence table exploded"),
        ):
            result = self._drain()

        assert result["failed"] == 1
        batch.refresh_from_db()
        assert batch.status == UploadStatus.FAILED
        assert "equivalence table exploded" in batch.error_message
        # The bootstrap half of the report survived.
        assert batch.report["bootstrap"]["documents_created"] == 1
        assert "equivalences" not in batch.report
        assert Document.objects.filter(title="H.R. 1 — Test Bill (IH)").exists()

    def test_drain_fails_cleanly_when_token_deleted(self):
        batch = self._stage()
        batch.corpus_access_token = None
        batch.save(update_fields=["corpus_access_token"])
        result = self._drain()
        assert result["failed"] == 1
        batch.refresh_from_db()
        assert batch.status == UploadStatus.FAILED
        assert "token" in batch.error_message.lower()
