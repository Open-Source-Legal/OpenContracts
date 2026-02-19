"""
Tests for the workstation claim/complete protocol.

Tests the ClaimBulkIngestionBatch and CompleteBulkIngestionBatch mutations
that allow GPU workstations to pull processing work and submit results.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from graphene.test import Client as GrapheneClient

from config.graphql.schema import schema
from opencontractserver.bulk_ingestion.models import (
    BulkIngestionItem,
    BulkIngestionItemStatus,
    BulkIngestionJob,
    BulkIngestionJobStatus,
    IngestionSourceType,
    ParsingStrategy,
)
from opencontractserver.bulk_ingestion.tasks import release_expired_claims
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class ClaimBulkIngestionBatchTest(TestCase):
    """Tests for the ClaimBulkIngestionBatch mutation."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="testuser",
            password="testpass",
            is_usage_capped=False,
        )
        self.other_user = User.objects.create_user(
            username="otheruser",
            password="testpass",
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        self.job = BulkIngestionJob.objects.create(
            corpus=self.corpus,
            creator=self.user,
            source_type=IngestionSourceType.STORAGE_PREFIX,
            source_config={"backend": "s3", "prefix": "test/"},
            parsing_strategy=ParsingStrategy.FULL,
            status=BulkIngestionJobStatus.PROCESSING,
            total_items=5,
        )
        set_permissions_for_obj_to_user(self.user, self.job, [PermissionTypes.ALL])

        # Create pending items
        self.items = []
        for i in range(5):
            item = BulkIngestionItem.objects.create(
                job=self.job,
                external_id=f"doc_{i:04d}",
                staged_path=f"test/doc_{i:04d}.pdf",
                status=BulkIngestionItemStatus.PENDING,
            )
            self.items.append(item)

        self.client = GrapheneClient(schema, context_value=TestContext(self.user))

    CLAIM_MUTATION = """
        mutation ClaimBatch($jobId: ID!, $batchSize: Int, $workstationId: String) {
            claimBulkIngestionBatch(
                jobId: $jobId,
                batchSize: $batchSize,
                workstationId: $workstationId
            ) {
                ok
                message
                items {
                    id
                    externalId
                    stagedPath
                    sourceUrl
                    fileType
                }
            }
        }
    """

    def test_claim_items(self):
        """Claiming items transitions them from pending to parsing."""
        result = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "batchSize": 3,
                "workstationId": "gpu-workstation-01",
            },
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["items"]), 3)

        # Verify item fields
        for item in data["items"]:
            self.assertIn("doc_", item["externalId"])
            self.assertIn("test/", item["stagedPath"])

        # Verify DB state
        claimed = BulkIngestionItem.objects.filter(job=self.job, status="parsing")
        self.assertEqual(claimed.count(), 3)
        for item in claimed:
            self.assertIsNotNone(item.claimed_at)
            self.assertEqual(item.claimed_by, "gpu-workstation-01")

        # Verify remaining items are still pending
        pending = BulkIngestionItem.objects.filter(job=self.job, status="pending")
        self.assertEqual(pending.count(), 2)

    def test_claim_all_items(self):
        """Claiming more than available returns only available items."""
        result = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "batchSize": 100,
            },
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["items"]), 5)

    def test_claim_empty_job(self):
        """Claiming from a job with no pending items returns empty list."""
        # Mark all items as completed
        BulkIngestionItem.objects.filter(job=self.job).update(status="completed")

        result = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={"jobId": str(self.job.id)},
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["items"]), 0)
        self.assertIn("No items available", data["message"])

    def test_claim_nonexistent_job(self):
        """Claiming from a non-existent job returns error."""
        result = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={"jobId": "999999"},
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_claim_other_users_job(self):
        """Cannot claim items from another user's job."""
        other_client = GrapheneClient(
            schema, context_value=TestContext(self.other_user)
        )

        result = other_client.execute(
            self.CLAIM_MUTATION,
            variable_values={"jobId": str(self.job.id)},
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_claim_terminal_job(self):
        """Cannot claim items from a completed/cancelled job."""
        self.job.status = BulkIngestionJobStatus.COMPLETED
        self.job.save(update_fields=["status"])

        result = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={"jobId": str(self.job.id)},
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertFalse(data["ok"])
        self.assertIn("terminal state", data["message"])

    def test_claim_batch_size_clamped(self):
        """Batch size is clamped to max."""
        result = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "batchSize": 10000,
            },
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertTrue(data["ok"])
        # Only 5 items available, all claimed
        self.assertEqual(len(data["items"]), 5)

    def test_sequential_claims_dont_overlap(self):
        """Two sequential claims return different items."""
        result1 = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "batchSize": 2,
                "workstationId": "ws-1",
            },
        )
        result2 = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "batchSize": 2,
                "workstationId": "ws-2",
            },
        )

        items1 = result1["data"]["claimBulkIngestionBatch"]["items"]
        items2 = result2["data"]["claimBulkIngestionBatch"]["items"]

        self.assertEqual(len(items1), 2)
        self.assertEqual(len(items2), 2)

        ids1 = {item["id"] for item in items1}
        ids2 = {item["id"] for item in items2}
        self.assertEqual(len(ids1 & ids2), 0, "Claims should not overlap")

    def test_default_workstation_id(self):
        """Claiming without workstation_id uses empty string."""
        result = self.client.execute(
            self.CLAIM_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "batchSize": 1,
            },
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertTrue(data["ok"])

        item = BulkIngestionItem.objects.get(job=self.job, status="parsing")
        self.assertEqual(item.claimed_by, "")


class ReleaseExpiredClaimsTest(TestCase):
    """Tests for the expired claim release mechanism."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="testuser",
            password="testpass",
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=self.user,
        )
        self.job = BulkIngestionJob.objects.create(
            corpus=self.corpus,
            creator=self.user,
            source_type=IngestionSourceType.STORAGE_PREFIX,
            source_config={},
            status=BulkIngestionJobStatus.PROCESSING,
            total_items=3,
        )

    @override_settings(BULK_INGESTION_CLAIM_TTL_SECONDS=3600)
    def test_expired_claims_released(self):
        """Items with expired claims are released back to pending."""
        # Create items claimed 2 hours ago (expired with 1h TTL)
        expired_time = timezone.now() - timedelta(hours=2)
        for i in range(2):
            BulkIngestionItem.objects.create(
                job=self.job,
                external_id=f"expired_{i}",
                status="parsing",
                claimed_at=expired_time,
                claimed_by="ws-crashed",
            )

        # Create a recent claim (not expired)
        BulkIngestionItem.objects.create(
            job=self.job,
            external_id="recent",
            status="parsing",
            claimed_at=timezone.now() - timedelta(minutes=5),
            claimed_by="ws-active",
        )

        released = release_expired_claims(self.job.id)
        self.assertEqual(released, 2)

        # Verify expired items are pending again
        expired_items = BulkIngestionItem.objects.filter(
            job=self.job, external_id__startswith="expired_"
        )
        for item in expired_items:
            self.assertEqual(item.status, "pending")
            self.assertIsNone(item.claimed_at)
            self.assertEqual(item.claimed_by, "")

        # Verify recent claim is untouched
        recent = BulkIngestionItem.objects.get(job=self.job, external_id="recent")
        self.assertEqual(recent.status, "parsing")
        self.assertEqual(recent.claimed_by, "ws-active")

    def test_no_expired_claims(self):
        """No release when all claims are fresh."""
        BulkIngestionItem.objects.create(
            job=self.job,
            external_id="fresh",
            status="parsing",
            claimed_at=timezone.now(),
            claimed_by="ws-1",
        )

        released = release_expired_claims(self.job.id)
        self.assertEqual(released, 0)

    def test_claim_releases_expired_before_claiming(self):
        """ClaimBulkIngestionBatch releases expired claims first."""
        # Create an expired claim
        expired_time = timezone.now() - timedelta(hours=2)
        BulkIngestionItem.objects.create(
            job=self.job,
            external_id="was_claimed",
            status="parsing",
            claimed_at=expired_time,
            claimed_by="ws-old",
        )

        client = GrapheneClient(schema, context_value=TestContext(self.user))

        result = client.execute(
            ClaimBulkIngestionBatchTest.CLAIM_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "batchSize": 10,
            },
        )

        data = result["data"]["claimBulkIngestionBatch"]
        self.assertTrue(data["ok"])
        # The expired item should now be available and claimed
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["externalId"], "was_claimed")


class CompleteBulkIngestionBatchTest(TestCase):
    """Tests for the CompleteBulkIngestionBatch mutation."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="testuser",
            password="testpass",
        )
        self.other_user = User.objects.create_user(
            username="otheruser",
            password="testpass",
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        self.job = BulkIngestionJob.objects.create(
            corpus=self.corpus,
            creator=self.user,
            source_type=IngestionSourceType.PRE_PARSED,
            source_config={},
            parsing_strategy=ParsingStrategy.PRE_PARSED,
            status=BulkIngestionJobStatus.PROCESSING,
            total_items=5,
        )
        set_permissions_for_obj_to_user(self.user, self.job, [PermissionTypes.ALL])

        self.client = GrapheneClient(schema, context_value=TestContext(self.user))

    COMPLETE_MUTATION = """
        mutation CompleteBatch($jobId: ID!, $resultsPath: String!) {
            completeBulkIngestionBatch(
                jobId: $jobId,
                resultsPath: $resultsPath
            ) {
                ok
                message
            }
        }
    """

    @patch("opencontractserver.bulk_ingestion.tasks.batch_import_preparsed.delay")
    def test_submit_results(self, mock_delay):
        """Submitting results dispatches the import task."""
        result = self.client.execute(
            self.COMPLETE_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "resultsPath": "s3://bucket/results/batch_001.jsonl",
            },
        )

        data = result["data"]["completeBulkIngestionBatch"]
        self.assertTrue(data["ok"])
        self.assertIn("submitted", data["message"])

        # Verify Celery task was dispatched
        mock_delay.assert_called_once_with(
            self.job.id, "s3://bucket/results/batch_001.jsonl", 0
        )

    @patch("opencontractserver.bulk_ingestion.tasks.batch_import_preparsed.delay")
    def test_submit_transitions_created_to_importing(self, mock_delay):
        """Submitting to a CREATED job transitions it to IMPORTING."""
        self.job.status = BulkIngestionJobStatus.CREATED
        self.job.save(update_fields=["status"])

        self.client.execute(
            self.COMPLETE_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "resultsPath": "results.jsonl",
            },
        )

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, BulkIngestionJobStatus.IMPORTING)
        self.assertIsNotNone(self.job.started_at)

    def test_submit_nonexistent_job(self):
        """Submitting to a non-existent job returns error."""
        result = self.client.execute(
            self.COMPLETE_MUTATION,
            variable_values={
                "jobId": "999999",
                "resultsPath": "results.jsonl",
            },
        )

        data = result["data"]["completeBulkIngestionBatch"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_submit_other_users_job(self):
        """Cannot submit results to another user's job."""
        other_client = GrapheneClient(
            schema, context_value=TestContext(self.other_user)
        )

        result = other_client.execute(
            self.COMPLETE_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "resultsPath": "results.jsonl",
            },
        )

        data = result["data"]["completeBulkIngestionBatch"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_submit_terminal_job(self):
        """Cannot submit results to a completed job."""
        self.job.status = BulkIngestionJobStatus.COMPLETED
        self.job.save(update_fields=["status"])

        result = self.client.execute(
            self.COMPLETE_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "resultsPath": "results.jsonl",
            },
        )

        data = result["data"]["completeBulkIngestionBatch"]
        self.assertFalse(data["ok"])
        self.assertIn("terminal state", data["message"])

    def test_submit_empty_path(self):
        """Submitting with empty results_path returns error."""
        result = self.client.execute(
            self.COMPLETE_MUTATION,
            variable_values={
                "jobId": str(self.job.id),
                "resultsPath": "   ",
            },
        )

        data = result["data"]["completeBulkIngestionBatch"]
        self.assertFalse(data["ok"])
        self.assertIn("required", data["message"])
