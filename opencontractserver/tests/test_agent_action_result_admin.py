"""
Tests for AgentActionResult admin configuration.
"""

import logging
from datetime import timedelta
from unittest.mock import Mock

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from opencontractserver.agents.admin import AgentActionResultAdmin
from opencontractserver.agents.models import AgentActionResult, AgentConfiguration
from opencontractserver.corpuses.models import Corpus, CorpusAction, CorpusActionTrigger
from opencontractserver.documents.models import Document
from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class TestAgentActionResultAdmin(TestCase):
    """
    Tests for the AgentActionResult admin configuration.
    """

    superuser: User
    corpus: Corpus
    document: Document
    agent_config: AgentConfiguration
    corpus_action: CorpusAction
    result_pending: AgentActionResult
    result_completed: AgentActionResult
    result_failed: AgentActionResult

    @classmethod
    def setUpTestData(cls):
        # Create superuser
        cls.superuser = User.objects.create_superuser(
            username="agent_admin_test",
            email="agentadmin@example.com",
            password="adminpass123",
        )

        # Create corpus
        cls.corpus = Corpus.objects.create(
            title="Test Corpus for Agent Admin",
            creator=cls.superuser,
        )

        # Create document
        cls.document = Document.objects.create(
            title="Test Document for Agent Admin",
            creator=cls.superuser,
        )
        cls.corpus.add_document(document=cls.document, user=cls.superuser)

        # Create agent configuration
        cls.agent_config = AgentConfiguration.objects.create(
            name="Test Agent Config",
            description="Test agent configuration for admin tests",
            system_instructions="You are a test agent.",
            available_tools=["search", "summarize"],
            scope="CORPUS",  # Must be uppercase
            corpus=cls.corpus,
            creator=cls.superuser,
        )

        # Create corpus action with agent
        cls.corpus_action = CorpusAction.objects.create(
            name="Test Agent Action",
            corpus=cls.corpus,
            agent_config=cls.agent_config,
            task_instructions="Summarize this document",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=cls.superuser,
        )

        # Create agent action results with different statuses
        now = timezone.now()

        cls.result_pending = AgentActionResult.objects.create(
            corpus_action=cls.corpus_action,
            document=cls.document,
            status=AgentActionResult.Status.PENDING,
            creator=cls.superuser,
        )

        cls.result_completed = AgentActionResult.objects.create(
            corpus_action=cls.corpus_action,
            document=Document.objects.create(
                title="Another Document",
                creator=cls.superuser,
            ),
            status=AgentActionResult.Status.COMPLETED,
            started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=3),
            agent_response="This is a summary of the document.",
            tools_executed=[
                {"name": "search", "args": {"query": "test"}, "result": "found"},
                {"name": "summarize", "args": {}, "result": "summary created"},
            ],
            execution_metadata={"model": "gpt-4", "tokens_used": 500},
            creator=cls.superuser,
        )

        cls.result_failed = AgentActionResult.objects.create(
            corpus_action=cls.corpus_action,
            document=Document.objects.create(
                title="Failed Document",
                creator=cls.superuser,
            ),
            status=AgentActionResult.Status.FAILED,
            started_at=now - timedelta(minutes=10),
            completed_at=now - timedelta(minutes=9),
            error_message="Agent failed to process document",
            creator=cls.superuser,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username="agent_admin_test", password="adminpass123")
        # ModelAdmin only needs the AdminSite for URL reversing, which these
        # unit tests don't exercise; ``None`` is the standard test stand-in.
        self.admin = AgentActionResultAdmin(AgentActionResult, None)  # type: ignore[arg-type]

    def test_changelist_view(self):
        """Test that the changelist view loads successfully."""
        url = reverse("admin:agents_agentactionresult_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check that results appear
        self.assertContains(response, "Test Agent Action")

    def test_change_view(self):
        """Test that the change view loads successfully."""
        url = reverse(
            "admin:agents_agentactionresult_change",
            args=[self.result_completed.pk],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_search(self):
        """Test search functionality."""
        url = reverse("admin:agents_agentactionresult_changelist")
        response = self.client.get(url, data={"q": "Test Agent Action"})
        self.assertEqual(response.status_code, 200)

    def test_filter_by_status(self):
        """Test filtering by status."""
        url = reverse("admin:agents_agentactionresult_changelist")
        response = self.client.get(url, data={"status__exact": "completed"})
        self.assertEqual(response.status_code, 200)

    def test_status_badge_pending(self):
        """Test status badge for pending status."""
        result = self.admin.status_badge(self.result_pending)
        self.assertIn("#6c757d", result)  # gray color
        self.assertIn("Pending", result)

    def test_status_badge_completed(self):
        """Test status badge for completed status."""
        result = self.admin.status_badge(self.result_completed)
        self.assertIn("#28a745", result)  # green color
        self.assertIn("Completed", result)

    def test_status_badge_failed(self):
        """Test status badge for failed status."""
        result = self.admin.status_badge(self.result_failed)
        self.assertIn("#dc3545", result)  # red color
        self.assertIn("Failed", result)

    def test_status_badge_running(self):
        """Test status badge for running status."""
        result = Mock()
        result.status = "running"
        result.get_status_display = lambda: "Running"
        badge = self.admin.status_badge(result)
        self.assertIn("#007bff", badge)  # blue color
        self.assertIn("Running", badge)

    def test_corpus_action_link(self):
        """Test corpus action link generation."""
        result = self.admin.corpus_action_link(self.result_completed)
        self.assertIn(
            f"/admin/corpuses/corpusaction/{self.corpus_action.pk}/change/", result
        )
        self.assertIn("Test Agent Action", result)

    def test_corpus_action_link_truncation(self):
        """Test that long action names are truncated."""
        long_name_action = Mock()
        long_name_action.name = "A" * 40  # 40 character name
        long_name_action.pk = 999
        result_mock = Mock(
            corpus_action=long_name_action,
            corpus_action_id=999,
        )
        result = self.admin.corpus_action_link(result_mock)
        self.assertIn("...", result)

    def test_corpus_action_link_no_action(self):
        """Test corpus action link when action is None."""
        result = Mock(corpus_action=None)
        link = self.admin.corpus_action_link(result)
        self.assertEqual(link, "-")

    def test_document_link(self):
        """Test document link generation."""
        result = self.admin.document_link(self.result_completed)
        self.assertIn("/admin/documents/document/", result)
        self.assertIn("Another Document", result)

    def test_document_link_truncation(self):
        """Test that long document titles are truncated."""
        long_title_doc = Mock()
        long_title_doc.title = "B" * 50  # 50 character title
        long_title_doc.pk = 888
        result_mock = Mock(
            document=long_title_doc,
            document_id=888,
        )
        result = self.admin.document_link(result_mock)
        self.assertIn("...", result)

    def test_document_link_no_document(self):
        """Test document link when document is None."""
        result = Mock(document=None)
        link = self.admin.document_link(result)
        self.assertEqual(link, "-")

    def test_tools_count_with_tools(self):
        """Test tools count display with tools."""
        result = self.admin.tools_count(self.result_completed)
        self.assertIn("2", result)  # 2 tools executed
        self.assertIn("#17a2b8", result)  # cyan badge color

    def test_tools_count_no_tools(self):
        """Test tools count display with no tools."""
        result = self.admin.tools_count(self.result_pending)
        self.assertEqual(result, "0")

    def test_duration_display_milliseconds(self):
        """Test duration display for sub-second durations."""
        result = Mock()
        result.duration_seconds = 0.25
        display = self.admin.duration_display(result)
        self.assertEqual(display, "250ms")

    def test_duration_display_seconds(self):
        """Test duration display for second-level durations."""
        result = Mock()
        result.duration_seconds = 45.3
        display = self.admin.duration_display(result)
        self.assertEqual(display, "45.3s")

    def test_duration_display_minutes(self):
        """Test duration display for minute-level durations."""
        result = Mock()
        result.duration_seconds = 185.0  # 3 min 5 sec
        display = self.admin.duration_display(result)
        self.assertEqual(display, "3m 5s")

    def test_duration_display_none(self):
        """Test duration display when duration is None."""
        result = Mock()
        result.duration_seconds = None
        display = self.admin.duration_display(result)
        self.assertEqual(display, "-")

    def test_agent_response_display(self):
        """Test agent response display."""
        result = self.admin.agent_response_display(self.result_completed)
        self.assertIn("<pre", result)
        self.assertIn("This is a summary of the document.", result)

    def test_agent_response_display_truncation(self):
        """Test that very long responses are truncated."""
        result = Mock()
        result.agent_response = "X" * 6000  # 6000 character response
        display = self.admin.agent_response_display(result)
        self.assertIn("... [truncated]", display)

    def test_agent_response_display_empty(self):
        """Test agent response display when empty."""
        result = Mock()
        result.agent_response = ""
        display = self.admin.agent_response_display(result)
        self.assertEqual(display, "No response")

    def test_tools_executed_display(self):
        """Test tools executed display."""
        result = self.admin.tools_executed_display(self.result_completed)
        self.assertIn("<pre>", result)
        self.assertIn("search", result)
        self.assertIn("summarize", result)

    def test_tools_executed_display_empty(self):
        """Test tools executed display when empty."""
        result = Mock()
        result.tools_executed = []
        display = self.admin.tools_executed_display(result)
        self.assertEqual(display, "None")

    def test_tools_executed_display_truncation(self):
        """Test that very large tool lists are truncated."""
        result = Mock()
        result.tools_executed = [
            {"name": f"tool_{i}", "data": "X" * 500} for i in range(50)
        ]
        display = self.admin.tools_executed_display(result)
        self.assertIn("... [truncated]", display)

    def test_execution_metadata_display(self):
        """Test execution metadata display."""
        result = self.admin.execution_metadata_display(self.result_completed)
        self.assertIn("<pre>", result)
        self.assertIn("gpt-4", result)
        self.assertIn("500", result)

    def test_execution_metadata_display_empty(self):
        """Test execution metadata display when empty."""
        result = Mock()
        result.execution_metadata = {}
        display = self.admin.execution_metadata_display(result)
        self.assertEqual(display, "None")

    def test_date_hierarchy(self):
        """Test that date hierarchy works."""
        url = reverse("admin:agents_agentactionresult_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_error_details_visible_on_failed_result(self):
        """Test that error details are visible for failed results."""
        url = reverse(
            "admin:agents_agentactionresult_change",
            args=[self.result_failed.pk],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agent failed to process document")

    def test_agent_configuration_changelist(self):
        """Test that agent configuration changelist works."""
        url = reverse("admin:agents_agentconfiguration_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Agent Config")

    def test_agent_configuration_change_view(self):
        """Test that agent configuration change view works."""
        url = reverse(
            "admin:agents_agentconfiguration_change",
            args=[self.agent_config.pk],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Agent Config")
