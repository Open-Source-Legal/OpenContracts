"""
Tests for CorpusActionExecution admin configuration.
"""

import logging
from datetime import timedelta
from unittest.mock import Mock

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from opencontractserver.corpuses.admin import CorpusActionExecutionAdmin
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTrigger,
)
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Fieldset
from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class TestCorpusActionExecutionAdmin(TestCase):
    """
    Tests for the CorpusActionExecution admin configuration.
    """

    superuser: User
    corpus: Corpus
    document: Document
    fieldset: Fieldset
    corpus_action: CorpusAction
    execution_queued: CorpusActionExecution
    execution_completed: CorpusActionExecution
    execution_failed: CorpusActionExecution

    @classmethod
    def setUpTestData(cls):
        # Create superuser
        cls.superuser = User.objects.create_superuser(
            username="admin_test",
            email="admin@example.com",
            password="adminpass123",
        )

        # Create corpus (keep title short to avoid truncation in tests)
        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=cls.superuser,
        )

        # Create document
        cls.document = Document.objects.create(
            title="Test Document for Admin",
            creator=cls.superuser,
        )
        cls.corpus.add_document(document=cls.document, user=cls.superuser)

        # Create fieldset for corpus action
        cls.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test fieldset for admin tests",
            creator=cls.superuser,
        )

        # Create corpus action
        cls.corpus_action = CorpusAction.objects.create(
            name="Test Action",
            corpus=cls.corpus,
            fieldset=cls.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=cls.superuser,
        )

        # Create executions with different statuses
        now = timezone.now()

        cls.execution_queued = CorpusActionExecution.objects.create(
            corpus_action=cls.corpus_action,
            document=cls.document,
            corpus=cls.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.QUEUED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now,
            creator=cls.superuser,
        )

        cls.execution_completed = CorpusActionExecution.objects.create(
            corpus_action=cls.corpus_action,
            document=cls.document,
            corpus=cls.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.COMPLETED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now - timedelta(minutes=5),
            started_at=now - timedelta(minutes=4),
            completed_at=now - timedelta(minutes=3),
            affected_objects=[
                {"type": "extract", "id": 1},
                {"type": "datacell", "id": 2, "column_name": "parties"},
            ],
            creator=cls.superuser,
        )

        cls.execution_failed = CorpusActionExecution.objects.create(
            corpus_action=cls.corpus_action,
            document=cls.document,
            corpus=cls.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.FAILED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now - timedelta(minutes=10),
            started_at=now - timedelta(minutes=9),
            completed_at=now - timedelta(minutes=8),
            error_message="Test error message",
            error_traceback="Traceback: test traceback",
            creator=cls.superuser,
        )

    admin: CorpusActionExecutionAdmin

    def setUp(self):
        self.client = Client()
        self.client.login(username="admin_test", password="adminpass123")
        # admin_site is unused by the display methods under test; None is an
        # intentional, runtime-safe test stand-in for the AdminSite argument.
        self.admin = CorpusActionExecutionAdmin(
            CorpusActionExecution, None  # type: ignore[arg-type]
        )

    def test_changelist_view(self):
        """Test that the changelist view loads successfully."""
        url = reverse("admin:corpuses_corpusactionexecution_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check that executions appear - the CorpusAction __str__ includes "CorpusAction for"
        self.assertContains(response, "CorpusAction for")

    def test_change_view(self):
        """Test that the change view loads successfully."""
        url = reverse(
            "admin:corpuses_corpusactionexecution_change",
            args=[self.execution_completed.pk],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_search(self):
        """Test search functionality."""
        url = reverse("admin:corpuses_corpusactionexecution_changelist")
        response = self.client.get(url, data={"q": "Test Action"})
        self.assertEqual(response.status_code, 200)

    def test_filter_by_status(self):
        """Test filtering by status."""
        url = reverse("admin:corpuses_corpusactionexecution_changelist")
        response = self.client.get(url, data={"status__exact": "completed"})
        self.assertEqual(response.status_code, 200)

    def test_filter_by_action_type(self):
        """Test filtering by action type."""
        url = reverse("admin:corpuses_corpusactionexecution_changelist")
        response = self.client.get(url, data={"action_type__exact": "fieldset"})
        self.assertEqual(response.status_code, 200)

    def test_status_badge_queued(self):
        """Test status badge for queued status."""
        result = self.admin.status_badge(self.execution_queued)
        self.assertIn("#6c757d", result)  # gray color
        self.assertIn("Queued", result)

    def test_status_badge_completed(self):
        """Test status badge for completed status."""
        result = self.admin.status_badge(self.execution_completed)
        self.assertIn("#28a745", result)  # green color
        self.assertIn("Completed", result)

    def test_status_badge_failed(self):
        """Test status badge for failed status."""
        result = self.admin.status_badge(self.execution_failed)
        self.assertIn("#dc3545", result)  # red color
        self.assertIn("Failed", result)

    def test_document_link(self):
        """Test document link generation."""
        result = self.admin.document_link(self.execution_completed)
        self.assertIn(f"/admin/documents/document/{self.document.pk}/change/", result)
        self.assertIn("Test Document for Admin", result)

    def test_document_link_truncation(self):
        """Test that long document titles are truncated."""
        long_title_doc = Document.objects.create(
            title="A" * 50,  # 50 character title
            creator=self.superuser,
        )
        execution = Mock(
            document=long_title_doc,
            document_id=long_title_doc.pk,
        )
        result = self.admin.document_link(execution)
        self.assertIn("...", result)

    def test_document_link_no_document(self):
        """Test document link when document is None."""
        execution = Mock(document=None)
        result = self.admin.document_link(execution)
        self.assertEqual(result, "-")

    def test_corpus_link(self):
        """Test corpus link generation."""
        result = self.admin.corpus_link(self.execution_completed)
        self.assertIn(f"/admin/corpuses/corpus/{self.corpus.pk}/change/", result)
        self.assertIn("Test Corpus", result)

    def test_corpus_link_no_corpus(self):
        """Test corpus link when corpus is None."""
        execution = Mock(corpus=None)
        result = self.admin.corpus_link(execution)
        self.assertEqual(result, "-")

    def test_duration_display_milliseconds(self):
        """Test duration display for sub-second durations."""
        execution = Mock()
        execution.duration_seconds = 0.5
        result = self.admin.duration_display(execution)
        self.assertEqual(result, "500ms")

    def test_duration_display_seconds(self):
        """Test duration display for second-level durations."""
        execution = Mock()
        execution.duration_seconds = 30.5
        result = self.admin.duration_display(execution)
        self.assertEqual(result, "30.5s")

    def test_duration_display_minutes(self):
        """Test duration display for minute-level durations."""
        execution = Mock()
        execution.duration_seconds = 125.5  # 2 min 5.5 sec
        result = self.admin.duration_display(execution)
        self.assertEqual(result, "2m 6s")

    def test_duration_display_none(self):
        """Test duration display when duration is None."""
        execution = Mock()
        execution.duration_seconds = None
        result = self.admin.duration_display(execution)
        self.assertEqual(result, "-")

    def test_wait_time_display(self):
        """Test wait time display."""
        execution = Mock()
        execution.wait_time_seconds = 5.0
        result = self.admin.wait_time_display(execution)
        self.assertEqual(result, "5.0s")

    def test_wait_time_display_none(self):
        """Test wait time display when wait time is None."""
        execution = Mock()
        execution.wait_time_seconds = None
        result = self.admin.wait_time_display(execution)
        self.assertEqual(result, "-")

    def test_affected_objects_display(self):
        """Test affected objects display."""
        result = self.admin.affected_objects_display(self.execution_completed)
        self.assertIn("<pre>", result)
        self.assertIn("extract", result)
        self.assertIn("datacell", result)

    def test_affected_objects_display_empty(self):
        """Test affected objects display when empty."""
        result = self.admin.affected_objects_display(self.execution_queued)
        self.assertEqual(result, "None")

    def test_execution_metadata_display(self):
        """Test execution metadata display."""
        execution = Mock()
        execution.execution_metadata = {"model": "gpt-4", "tokens_used": 1500}
        result = self.admin.execution_metadata_display(execution)
        self.assertIn("<pre>", result)
        self.assertIn("gpt-4", result)
        self.assertIn("1500", result)

    def test_execution_metadata_display_empty(self):
        """Test execution metadata display when empty."""
        execution = Mock()
        execution.execution_metadata = {}
        result = self.admin.execution_metadata_display(execution)
        self.assertEqual(result, "None")

    def test_date_hierarchy(self):
        """Test that date hierarchy works."""
        url = reverse("admin:corpuses_corpusactionexecution_changelist")
        # Access with date drill-down
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Date hierarchy should be present in the response
        self.assertContains(response, "queued_at")

    def test_error_details_visible_on_failed_execution(self):
        """Test that error details are visible for failed executions."""
        url = reverse(
            "admin:corpuses_corpusactionexecution_change",
            args=[self.execution_failed.pk],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test error message")
