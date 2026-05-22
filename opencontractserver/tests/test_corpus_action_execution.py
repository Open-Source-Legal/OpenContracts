"""
Tests for CorpusActionExecution model, QuerySet, and Manager.

Tests cover:
- Model lifecycle methods (mark_started, mark_completed, mark_failed, mark_skipped)
- Bulk operations (bulk_queue)
- QuerySet methods (for_corpus, for_document, by_type, pending, failed, recent, etc.)
- Computed properties (duration_seconds, wait_time_seconds)
- Permission filtering (visible_to_user)
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.analyzer.models import Analyzer
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTrigger,
)
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Fieldset
from opencontractserver.types.enums import PermissionTypes

User = get_user_model()


class CorpusActionExecutionModelTestCase(TestCase):
    """Test model lifecycle methods."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)
        self.action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.user,
        )

    def create_execution(self, **kwargs):
        """Helper to create execution with defaults."""
        defaults = {
            "corpus_action": self.action,
            "document": self.document,
            "corpus": self.corpus,
            "action_type": CorpusActionExecution.ActionType.FIELDSET,
            "trigger": CorpusActionTrigger.ADD_DOCUMENT,
            "queued_at": timezone.now(),
            "creator": self.user,
        }
        defaults.update(kwargs)
        return CorpusActionExecution.objects.create(**defaults)

    # --- mark_started() ---

    def test_mark_started_sets_status_and_timestamp(self):
        """mark_started() transitions to RUNNING with timestamp."""
        execution = self.create_execution()
        self.assertEqual(execution.status, CorpusActionExecution.Status.QUEUED)
        self.assertIsNone(execution.started_at)

        execution.mark_started()

        execution.refresh_from_db()
        self.assertEqual(execution.status, CorpusActionExecution.Status.RUNNING)
        self.assertIsNotNone(execution.started_at)

    def test_mark_started_with_save_false(self):
        """mark_started(save=False) updates instance without DB write."""
        execution = self.create_execution()

        execution.mark_started(save=False)

        self.assertEqual(execution.status, CorpusActionExecution.Status.RUNNING)
        # Verify NOT saved to DB
        execution.refresh_from_db()
        self.assertEqual(execution.status, CorpusActionExecution.Status.QUEUED)

    # --- mark_completed() ---

    def test_mark_completed_sets_status_and_timestamp(self):
        """mark_completed() transitions to COMPLETED with timestamp."""
        execution = self.create_execution()
        execution.mark_started()

        execution.mark_completed()

        execution.refresh_from_db()
        self.assertEqual(execution.status, CorpusActionExecution.Status.COMPLETED)
        self.assertIsNotNone(execution.completed_at)

    def test_mark_completed_with_affected_objects(self):
        """mark_completed() stores affected objects list."""
        execution = self.create_execution()
        execution.mark_started()

        affected = [
            {"type": "extract", "id": 1},
            {"type": "datacell", "id": 2, "column_name": "parties"},
        ]
        execution.mark_completed(affected_objects=affected)

        execution.refresh_from_db()
        self.assertEqual(len(execution.affected_objects), 2)
        self.assertEqual(execution.affected_objects[0]["type"], "extract")
        self.assertEqual(execution.affected_objects[1]["column_name"], "parties")

    def test_mark_completed_with_metadata(self):
        """mark_completed() merges execution metadata."""
        execution = self.create_execution()
        execution.execution_metadata = {"existing": "value"}
        execution.save()
        execution.mark_started()

        execution.mark_completed(metadata={"model": "gpt-4", "tokens": 1500})

        execution.refresh_from_db()
        self.assertEqual(execution.execution_metadata["existing"], "value")
        self.assertEqual(execution.execution_metadata["model"], "gpt-4")
        self.assertEqual(execution.execution_metadata["tokens"], 1500)

    # --- mark_failed() ---

    def test_mark_failed_sets_status_and_error(self):
        """mark_failed() transitions to FAILED with error details."""
        execution = self.create_execution()
        execution.mark_started()

        execution.mark_failed("Connection timeout", "Traceback: ...")

        execution.refresh_from_db()
        self.assertEqual(execution.status, CorpusActionExecution.Status.FAILED)
        self.assertIsNotNone(execution.completed_at)
        self.assertEqual(execution.error_message, "Connection timeout")
        self.assertEqual(execution.error_traceback, "Traceback: ...")

    def test_mark_failed_truncates_long_error_message(self):
        """mark_failed() truncates error_message to 5000 chars."""
        execution = self.create_execution()
        execution.mark_started()

        long_error = "x" * 10000
        execution.mark_failed(long_error)

        execution.refresh_from_db()
        self.assertEqual(len(execution.error_message), 5000)

    def test_mark_failed_truncates_long_traceback(self):
        """mark_failed() truncates error_traceback to 10000 chars."""
        execution = self.create_execution()
        execution.mark_started()

        long_traceback = "y" * 20000
        execution.mark_failed("Error", long_traceback)

        execution.refresh_from_db()
        self.assertEqual(len(execution.error_traceback), 10000)

    # --- mark_skipped() ---

    def test_mark_skipped_sets_status(self):
        """mark_skipped() transitions to SKIPPED."""
        execution = self.create_execution()

        execution.mark_skipped()

        execution.refresh_from_db()
        self.assertEqual(execution.status, CorpusActionExecution.Status.SKIPPED)
        self.assertIsNotNone(execution.completed_at)

    def test_mark_skipped_stores_reason_in_metadata(self):
        """mark_skipped() stores skip reason in execution_metadata."""
        execution = self.create_execution()

        execution.mark_skipped(reason="Already processed in previous run")

        execution.refresh_from_db()
        self.assertEqual(
            execution.execution_metadata["skip_reason"],
            "Already processed in previous run",
        )

    # --- add_affected_object() ---

    def test_add_affected_object_appends_to_list(self):
        """add_affected_object() appends to affected_objects list."""
        execution = self.create_execution()
        execution.affected_objects = []

        execution.add_affected_object("extract", 1)
        execution.add_affected_object("datacell", 2, column_name="parties")

        self.assertEqual(len(execution.affected_objects), 2)
        self.assertEqual(execution.affected_objects[0], {"type": "extract", "id": 1})
        self.assertEqual(
            execution.affected_objects[1],
            {"type": "datacell", "id": 2, "column_name": "parties"},
        )

    def test_add_affected_object_handles_none_list(self):
        """add_affected_object() initializes list if None."""
        execution = self.create_execution()
        execution.affected_objects = None

        execution.add_affected_object("annotation", 5)

        self.assertEqual(execution.affected_objects, [{"type": "annotation", "id": 5}])


class CorpusActionExecutionBulkOpsTestCase(TestCase):
    """Test bulk_queue and bulk update operations."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)
        self.analyzer = Analyzer.objects.create(
            description="Test Analyzer", creator=self.user, task_name="not.a.real.task"
        )
        self.agent_config = AgentConfiguration.objects.create(
            name="Test Agent",
            description="Test agent",
            system_instructions="You are helpful",
            is_active=True,
            creator=self.user,
        )
        self.action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        self.documents = [
            Document.objects.create(title=f"Doc {i}", creator=self.user)
            for i in range(5)
        ]

    def test_bulk_queue_creates_records(self):
        """bulk_queue() creates execution records efficiently."""
        doc_ids = [d.id for d in self.documents]

        executions = CorpusActionExecution.bulk_queue(
            corpus_action=self.action,
            document_ids=doc_ids,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            user_id=self.user.id,
        )

        self.assertEqual(len(executions), 5)
        self.assertTrue(
            all(e.status == CorpusActionExecution.Status.QUEUED for e in executions)
        )

    def test_bulk_queue_sets_correct_action_type_fieldset(self):
        """bulk_queue() detects fieldset action type."""
        executions = CorpusActionExecution.bulk_queue(
            corpus_action=self.action,
            document_ids=[self.documents[0].id],
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            user_id=self.user.id,
        )

        self.assertEqual(
            executions[0].action_type, CorpusActionExecution.ActionType.FIELDSET
        )

    def test_bulk_queue_sets_correct_action_type_analyzer(self):
        """bulk_queue() detects analyzer action type."""
        analyzer_action = CorpusAction.objects.create(
            name="Analyzer Action",
            corpus=self.corpus,
            analyzer=self.analyzer,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        executions = CorpusActionExecution.bulk_queue(
            corpus_action=analyzer_action,
            document_ids=[self.documents[0].id],
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            user_id=self.user.id,
        )

        self.assertEqual(
            executions[0].action_type, CorpusActionExecution.ActionType.ANALYZER
        )

    def test_bulk_queue_sets_correct_action_type_agent(self):
        """bulk_queue() detects agent action type."""
        agent_action = CorpusAction.objects.create(
            name="Agent Action",
            corpus=self.corpus,
            agent_config=self.agent_config,
            task_instructions="Summarize this document",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        executions = CorpusActionExecution.bulk_queue(
            corpus_action=agent_action,
            document_ids=[self.documents[0].id],
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            user_id=self.user.id,
        )

        self.assertEqual(
            executions[0].action_type, CorpusActionExecution.ActionType.AGENT
        )

    def test_bulk_queue_sets_denormalized_corpus_id(self):
        """bulk_queue() sets denormalized corpus_id for fast queries."""
        executions = CorpusActionExecution.bulk_queue(
            corpus_action=self.action,
            document_ids=[self.documents[0].id],
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            user_id=self.user.id,
        )

        self.assertEqual(executions[0].corpus_id, self.corpus.id)

    def test_bulk_queue_sets_creator(self):
        """bulk_queue() sets creator_id from user_id param."""
        executions = CorpusActionExecution.bulk_queue(
            corpus_action=self.action,
            document_ids=[self.documents[0].id],
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            user_id=self.user.id,
        )

        self.assertEqual(executions[0].creator_id, self.user.id)


class CorpusActionExecutionQuerySetTestCase(TestCase):
    """Test custom QuerySet methods."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus1 = Corpus.objects.create(title="Corpus 1", creator=self.user)
        self.corpus2 = Corpus.objects.create(title="Corpus 2", creator=self.user)
        self.document = Document.objects.create(title="Test Doc", creator=self.user)
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)
        self.action1 = CorpusAction.objects.create(
            name="Action 1",
            corpus=self.corpus1,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

    def create_execution(self, corpus, status="queued", action_type=None, **kwargs):
        """Helper to create execution with specified status."""
        action = (
            CorpusAction.objects.filter(corpus=corpus).first()
            if CorpusAction.objects.filter(corpus=corpus).exists()
            else self.action1
        )
        if action_type is None:
            action_type = CorpusActionExecution.ActionType.FIELDSET
        exec_obj = CorpusActionExecution.objects.create(
            corpus_action=action,
            document=self.document,
            corpus=corpus,
            action_type=action_type,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.user,
            **kwargs,
        )
        if status != "queued":
            exec_obj.status = status
            exec_obj.save()
        return exec_obj

    # --- for_corpus() ---

    def test_for_corpus_filters_by_corpus_id(self):
        """for_corpus() returns only executions for that corpus."""
        exec1 = self.create_execution(self.corpus1)
        exec2 = self.create_execution(self.corpus2)

        result = list(CorpusActionExecution.objects.for_corpus(self.corpus1.id))

        self.assertIn(exec1, result)
        self.assertNotIn(exec2, result)

    # --- for_document() ---

    def test_for_document_filters_by_document_id(self):
        """for_document() returns executions for that document."""
        doc2 = Document.objects.create(title="Doc 2", creator=self.user)
        exec1 = self.create_execution(self.corpus1)
        exec2 = CorpusActionExecution.objects.create(
            corpus_action=self.action1,
            document=doc2,
            corpus=self.corpus1,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.user,
        )

        result = list(CorpusActionExecution.objects.for_document(self.document.id))

        self.assertIn(exec1, result)
        self.assertNotIn(exec2, result)

    # --- by_type() ---

    def test_by_type_filters_by_action_type(self):
        """by_type() filters by action type."""
        exec_fieldset = self.create_execution(self.corpus1)
        exec_agent = self.create_execution(
            self.corpus1, action_type=CorpusActionExecution.ActionType.AGENT
        )

        result = list(
            CorpusActionExecution.objects.by_type(
                CorpusActionExecution.ActionType.FIELDSET
            )
        )

        self.assertIn(exec_fieldset, result)
        self.assertNotIn(exec_agent, result)

    # --- pending() ---

    def test_pending_returns_queued_and_running(self):
        """pending() returns QUEUED and RUNNING executions."""
        exec_queued = self.create_execution(self.corpus1, status="queued")
        exec_running = self.create_execution(self.corpus1, status="running")
        exec_completed = self.create_execution(self.corpus1, status="completed")
        exec_failed = self.create_execution(self.corpus1, status="failed")

        result = list(CorpusActionExecution.objects.pending())

        self.assertIn(exec_queued, result)
        self.assertIn(exec_running, result)
        self.assertNotIn(exec_completed, result)
        self.assertNotIn(exec_failed, result)

    # --- failed() ---

    def test_failed_returns_only_failed(self):
        """failed() returns only FAILED executions."""
        exec_failed = self.create_execution(self.corpus1, status="failed")
        exec_completed = self.create_execution(self.corpus1, status="completed")

        result = list(CorpusActionExecution.objects.failed())

        self.assertIn(exec_failed, result)
        self.assertNotIn(exec_completed, result)

    # --- recent() ---

    def test_recent_filters_by_time_window(self):
        """recent() returns executions within time window."""
        now = timezone.now()
        recent_exec = self.create_execution(self.corpus1)

        # Create old execution
        old_exec = self.create_execution(self.corpus1)
        old_exec.queued_at = now - timedelta(hours=48)
        old_exec.save()

        result = list(CorpusActionExecution.objects.recent(hours=24))

        self.assertIn(recent_exec, result)
        self.assertNotIn(old_exec, result)

    # --- with_stats() ---

    def test_with_stats_annotates_duration(self):
        """with_stats() adds duration annotation."""
        exec_obj = self.create_execution(self.corpus1)
        exec_obj.started_at = timezone.now()
        exec_obj.completed_at = exec_obj.started_at + timedelta(seconds=30)
        exec_obj.save()

        result = (
            CorpusActionExecution.objects.filter(id=exec_obj.id).with_stats().first()
        )

        self.assertIsNotNone(result.duration)
        self.assertEqual(result.duration.total_seconds(), 30)

    def test_with_stats_annotates_wait_time(self):
        """with_stats() adds wait_time annotation."""
        exec_obj = self.create_execution(self.corpus1)
        exec_obj.started_at = exec_obj.queued_at + timedelta(seconds=5)
        exec_obj.save()

        result = (
            CorpusActionExecution.objects.filter(id=exec_obj.id).with_stats().first()
        )

        self.assertIsNotNone(result.wait_time)
        self.assertEqual(result.wait_time.total_seconds(), 5)

    # --- summary_by_status() ---

    def test_summary_by_status_returns_counts(self):
        """summary_by_status() returns status counts dict."""
        self.create_execution(self.corpus1, status="queued")
        self.create_execution(self.corpus1, status="queued")
        self.create_execution(self.corpus1, status="completed")
        self.create_execution(self.corpus1, status="failed")

        result = CorpusActionExecution.objects.for_corpus(
            self.corpus1.id
        ).summary_by_status()

        self.assertEqual(result["queued"], 2)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["failed"], 1)

    # --- Chaining ---

    def test_queryset_methods_chain(self):
        """QuerySet methods can be chained together."""
        self.create_execution(self.corpus1, status="failed")

        result = (
            CorpusActionExecution.objects.for_corpus(self.corpus1.id)
            .failed()
            .recent(hours=24)
        )

        self.assertEqual(result.count(), 1)


class CorpusActionExecutionPropertiesTestCase(TestCase):
    """Test computed property methods."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.document = Document.objects.create(title="Test Doc", creator=self.user)
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)
        self.action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

    def create_execution(self):
        return CorpusActionExecution.objects.create(
            corpus_action=self.action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.user,
        )

    def test_duration_seconds_when_completed(self):
        """duration_seconds returns seconds between started and completed."""
        exec_obj = self.create_execution()
        exec_obj.started_at = timezone.now()
        exec_obj.completed_at = exec_obj.started_at + timedelta(
            seconds=45, milliseconds=500
        )

        self.assertAlmostEqual(exec_obj.duration_seconds, 45.5, places=1)

    def test_duration_seconds_when_not_completed(self):
        """duration_seconds returns None if not completed."""
        exec_obj = self.create_execution()
        exec_obj.started_at = timezone.now()

        self.assertIsNone(exec_obj.duration_seconds)

    def test_duration_seconds_when_not_started(self):
        """duration_seconds returns None if not started."""
        exec_obj = self.create_execution()

        self.assertIsNone(exec_obj.duration_seconds)

    def test_wait_time_seconds_when_started(self):
        """wait_time_seconds returns seconds in queue."""
        exec_obj = self.create_execution()
        exec_obj.started_at = exec_obj.queued_at + timedelta(seconds=10)

        self.assertAlmostEqual(exec_obj.wait_time_seconds, 10, places=1)

    def test_wait_time_seconds_when_not_started(self):
        """wait_time_seconds returns None if not started."""
        exec_obj = self.create_execution()

        self.assertIsNone(exec_obj.wait_time_seconds)

    def test_str_representation(self):
        """__str__ returns readable format."""
        exec_obj = self.create_execution()

        result = str(exec_obj)

        self.assertIn("fieldset", result)
        self.assertIn(self.action.name, result)
        self.assertIn("queued", result)


class CorpusActionExecutionPermissionsTestCase(TestCase):
    """Test visible_to_user() permission filtering."""

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass")
        self.other_user = User.objects.create_user(
            username="other", password="testpass"
        )
        self.superuser = User.objects.create_superuser(
            username="corpus_exec_superuser", password="testpass"
        )

        # Owner's private corpus and execution
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset", creator=self.owner
        )
        self.private_action = CorpusAction.objects.create(
            name="Private Action",
            corpus=self.private_corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.owner,
        )
        self.document = Document.objects.create(title="Test Doc", creator=self.owner)
        self.private_exec = CorpusActionExecution.objects.create(
            corpus_action=self.private_action,
            document=self.document,
            corpus=self.private_corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.owner,
        )

        # Public corpus and execution
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        self.public_action = CorpusAction.objects.create(
            name="Public Action",
            corpus=self.public_corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.owner,
        )
        self.public_exec = CorpusActionExecution.objects.create(
            corpus_action=self.public_action,
            document=self.document,
            corpus=self.public_corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.owner,
            is_public=True,
        )

    def test_superuser_sees_all(self):
        """Superuser can see all executions."""
        result = CorpusActionExecution.objects.visible_to_user(self.superuser)

        self.assertIn(self.private_exec, result)
        self.assertIn(self.public_exec, result)

    def test_owner_sees_own_private(self):
        """Owner can see their own private executions."""
        result = CorpusActionExecution.objects.visible_to_user(self.owner)

        self.assertIn(self.private_exec, result)
        self.assertIn(self.public_exec, result)

    def test_other_user_sees_only_public(self):
        """Other users can only see public executions."""
        result = list(CorpusActionExecution.objects.visible_to_user(self.other_user))

        # Other user cannot see private exec (they didn't create it)
        self.assertNotIn(self.private_exec, result)
        self.assertIn(self.public_exec, result)

    def test_anonymous_sees_only_public(self):
        """Anonymous users can only see public executions."""
        result = list(CorpusActionExecution.objects.visible_to_user(None))

        self.assertNotIn(self.private_exec, result)
        self.assertIn(self.public_exec, result)

    def test_visible_to_user_chains_with_queryset_methods(self):
        """visible_to_user() returns custom QuerySet for chaining."""
        result = (
            CorpusActionExecution.objects.visible_to_user(self.owner)
            .for_corpus(self.private_corpus.id)
            .pending()
        )

        # Should return CorpusActionExecutionQuerySet with custom methods
        self.assertTrue(hasattr(result, "for_corpus"))
        self.assertTrue(hasattr(result, "pending"))


class CorpusActionExecutionGroupVisibilityTest(TestCase):
    """Regression coverage for issue #1731 — the un-overridden
    ``BaseVisibilityManager.visible_to_user`` body must honour *group*
    object-permissions, not just *user* ones.

    ``CorpusActionExecution`` is the model the issue calls out as reaching
    that body un-tuned: ``CorpusActionExecutionManager.visible_to_user``
    only re-wraps ``super().visible_to_user(...)`` in a custom QuerySet.
    ``Manager.user_can`` resolves group grants (``_default_user_can`` runs
    with ``include_group_permissions=True``), so before the fix a user
    whose sole READ grant on an execution was via a group passed
    ``user_can(READ)`` yet was excluded from ``visible_to_user`` — the
    same filter/check drift #1714 closed for the ``shared/QuerySets.py``
    bodies.
    """

    def setUp(self):
        from django.contrib.auth.models import Group
        from guardian.shortcuts import assign_perm

        self.owner = User.objects.create_user(username="cae_grp_owner", password="x")
        # ``group_user``'s ONLY path to the execution below is group
        # membership — no creator status, no direct user grant, nothing
        # public. This isolates the group-permission code path.
        self.group_user = User.objects.create_user(
            username="cae_grp_member", password="x"
        )
        self.stranger = User.objects.create_user(
            username="cae_grp_stranger", password="x"
        )

        self.group = Group.objects.create(name="cae_visibility_test_group")
        self.group_user.groups.add(self.group)

        self.corpus = Corpus.objects.create(
            title="CAE Group Corpus", creator=self.owner, is_public=False
        )
        self.fieldset = Fieldset.objects.create(
            name="CAE Group Fieldset", creator=self.owner
        )
        self.action = CorpusAction.objects.create(
            name="CAE Group Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.owner,
        )
        self.document = Document.objects.create(
            title="CAE Group Doc", creator=self.owner
        )

        # Private execution, READ-shared with the group ONLY.
        self.group_exec = CorpusActionExecution.objects.create(
            corpus_action=self.action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.owner,
        )
        assign_perm("read_corpusactionexecution", self.group, self.group_exec)

        # Control: a private execution not shared with the group at all.
        self.unshared_exec = CorpusActionExecution.objects.create(
            corpus_action=self.action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.owner,
        )

    def test_group_grant_appears_in_visible_to_user(self):
        """An execution READ-granted to the user's group is included in
        ``CorpusActionExecution.objects.visible_to_user`` (issue #1731)."""
        visible_ids = set(
            CorpusActionExecution.objects.visible_to_user(self.group_user).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(self.group_exec.pk, visible_ids)
        # Control: an execution not shared with the group stays hidden.
        self.assertNotIn(self.unshared_exec.pk, visible_ids)

    def test_group_filter_check_equivalence(self):
        """``user_can(READ)`` and ``visible_to_user(...).exists()`` agree
        for a group-shared user — the invariant the drift broke."""
        check = self.group_exec.user_can(self.group_user, PermissionTypes.READ)
        in_filter = (
            CorpusActionExecution.objects.visible_to_user(self.group_user)
            .filter(pk=self.group_exec.pk)
            .exists()
        )
        self.assertTrue(check, "user_can must honour the group-level READ grant")
        self.assertTrue(in_filter, "visible_to_user must honour the group grant")
        self.assertEqual(check, in_filter)

    def test_group_read_grant_does_not_widen_to_writes(self):
        """SECURITY: a group READ grant authorizes READ but never
        UPDATE/DELETE — the read/write asymmetry must hold."""
        self.assertTrue(self.group_exec.user_can(self.group_user, PermissionTypes.READ))
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                self.group_exec.user_can(self.group_user, perm),
                f"group READ grant silently widened to {perm} — leak!",
            )

    def test_stranger_without_group_membership_stays_excluded(self):
        """A user who is NOT in the group sees none of the group-shared
        executions — the fix must not widen visibility beyond members."""
        in_filter = (
            CorpusActionExecution.objects.visible_to_user(self.stranger)
            .filter(pk=self.group_exec.pk)
            .exists()
        )
        self.assertFalse(in_filter, "non-member saw the group-shared execution — leak!")
        self.assertFalse(self.group_exec.user_can(self.stranger, PermissionTypes.READ))

    def test_visible_to_user_degrades_when_guardian_tables_missing(self):
        """DEFENSIVE: if the guardian ``*userobjectpermission`` /
        ``*groupobjectpermission`` tables cannot be resolved, the
        ``BaseVisibilityManager.visible_to_user`` body falls back
        gracefully instead of raising — each ``except LookupError`` branch
        zeroes out its own permitted-id set. Splitting the user- and
        group-table lookups into separate ``try`` blocks means a missing
        group table never discards already-resolved user grants.
        """
        from unittest.mock import patch

        from django.apps import apps

        real_get_model = apps.get_model

        def fake_get_model(app_label, model_name=None, *args, **kwargs):
            name = model_name if model_name is not None else app_label
            if "userobjectpermission" in name or "groupobjectpermission" in name:
                raise LookupError(f"simulated missing table: {name}")
            return real_get_model(app_label, model_name, *args, **kwargs)

        with patch.object(apps, "get_model", side_effect=fake_get_model):
            # Must not raise — the except LookupError branches handle the
            # missing tables.
            visible_ids = set(
                CorpusActionExecution.objects.visible_to_user(
                    self.group_user
                ).values_list("pk", flat=True)
            )

        # With guardian resolution unavailable, the group-only user loses
        # access to the execution reachable solely via the group grant —
        # visibility degrades to creator/public, never crashes.
        self.assertNotIn(self.group_exec.pk, visible_ids)


class PackageActionTrailTestCase(TestCase):
    """Test package_action_trail export function."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)
        self.analyzer = Analyzer.objects.create(
            description="Test Analyzer", creator=self.user, task_name="test.task"
        )
        self.agent_config = AgentConfiguration.objects.create(
            name="Test Agent",
            description="Test agent config",
            system_instructions="Test instructions",
            is_active=True,
            creator=self.user,
        )
        self.document = Document.objects.create(title="Test Doc", creator=self.user)

    def test_package_action_trail_with_fieldset_action(self):
        """package_action_trail exports fieldset actions correctly."""
        from opencontractserver.utils.export_v2 import package_action_trail

        CorpusAction.objects.create(
            name="Fieldset Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        result = package_action_trail(self.corpus, include_executions=False)

        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["name"], "Fieldset Action")
        self.assertEqual(result["actions"][0]["action_type"], "fieldset")
        self.assertEqual(result["actions"][0]["fieldset_id"], str(self.fieldset.id))
        self.assertIsNone(result["actions"][0]["analyzer_id"])

    def test_package_action_trail_with_analyzer_action(self):
        """package_action_trail exports analyzer actions correctly."""
        from opencontractserver.utils.export_v2 import package_action_trail

        CorpusAction.objects.create(
            name="Analyzer Action",
            corpus=self.corpus,
            analyzer=self.analyzer,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        result = package_action_trail(self.corpus, include_executions=False)

        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["action_type"], "analyzer")
        self.assertIsNotNone(result["actions"][0]["analyzer_id"])

    def test_package_action_trail_with_agent_action(self):
        """package_action_trail exports agent actions correctly."""
        from opencontractserver.utils.export_v2 import package_action_trail

        CorpusAction.objects.create(
            name="Agent Action",
            corpus=self.corpus,
            agent_config=self.agent_config,
            task_instructions="Summarize this document",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        result = package_action_trail(self.corpus, include_executions=False)

        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["action_type"], "agent")
        self.assertEqual(
            result["actions"][0]["task_instructions"], "Summarize this document"
        )

    def test_package_action_trail_with_executions(self):
        """package_action_trail includes execution records."""
        from opencontractserver.utils.export_v2 import package_action_trail

        action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        # Create execution records
        now = timezone.now()
        CorpusActionExecution.objects.create(
            corpus_action=action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.COMPLETED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now - timedelta(hours=1),
            started_at=now - timedelta(minutes=30),
            completed_at=now,
            creator=self.user,
        )

        result = package_action_trail(self.corpus, include_executions=True)

        self.assertEqual(len(result["executions"]), 1)
        self.assertEqual(result["executions"][0]["action_name"], "Test Action")
        self.assertEqual(result["executions"][0]["status"], "completed")
        self.assertIsNotNone(result["executions"][0]["queued_at"])
        self.assertIsNotNone(result["executions"][0]["started_at"])
        self.assertIsNotNone(result["executions"][0]["completed_at"])

    def test_package_action_trail_with_since_filter(self):
        """package_action_trail filters by since datetime."""
        from opencontractserver.utils.export_v2 import package_action_trail

        action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        now = timezone.now()

        # Old execution (should be filtered out)
        CorpusActionExecution.objects.create(
            corpus_action=action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now - timedelta(days=10),
            creator=self.user,
        )

        # Recent execution (should be included)
        recent_exec = CorpusActionExecution.objects.create(
            corpus_action=action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now - timedelta(hours=1),
            creator=self.user,
        )

        result = package_action_trail(
            self.corpus, include_executions=True, since=now - timedelta(days=1)
        )

        self.assertEqual(len(result["executions"]), 1)
        self.assertEqual(result["executions"][0]["id"], str(recent_exec.id))

    def test_package_action_trail_with_execution_limit(self):
        """package_action_trail respects execution_limit."""
        from opencontractserver.utils.export_v2 import package_action_trail

        action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        now = timezone.now()

        # Create multiple executions
        for i in range(5):
            CorpusActionExecution.objects.create(
                corpus_action=action,
                document=self.document,
                corpus=self.corpus,
                action_type=CorpusActionExecution.ActionType.FIELDSET,
                trigger=CorpusActionTrigger.ADD_DOCUMENT,
                queued_at=now - timedelta(hours=i),
                creator=self.user,
            )

        result = package_action_trail(
            self.corpus, include_executions=True, execution_limit=3
        )

        self.assertEqual(len(result["executions"]), 3)

    def test_package_action_trail_stats(self):
        """package_action_trail returns correct stats."""
        from opencontractserver.utils.export_v2 import package_action_trail

        action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        now = timezone.now()

        # Create executions with different statuses
        CorpusActionExecution.objects.create(
            corpus_action=action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.COMPLETED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now,
            creator=self.user,
        )
        CorpusActionExecution.objects.create(
            corpus_action=action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.FAILED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now,
            creator=self.user,
        )

        result = package_action_trail(self.corpus, include_executions=True)

        self.assertEqual(result["stats"]["total_executions"], 2)
        self.assertEqual(result["stats"]["completed"], 1)
        self.assertEqual(result["stats"]["failed"], 1)
        self.assertEqual(result["stats"]["exported_count"], 2)

    def test_package_action_trail_no_executions(self):
        """package_action_trail with include_executions=False."""
        from opencontractserver.utils.export_v2 import package_action_trail

        action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        # Create an execution that should NOT be exported
        CorpusActionExecution.objects.create(
            corpus_action=action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.user,
        )

        result = package_action_trail(self.corpus, include_executions=False)

        self.assertEqual(len(result["executions"]), 0)
        # Stats should still be calculated
        self.assertEqual(result["stats"]["total_executions"], 1)


class ManagerMethodsTestCase(TestCase):
    """Test manager methods that delegate to QuerySet."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)
        self.action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        self.document = Document.objects.create(title="Test Doc", creator=self.user)

    def test_manager_recent_method(self):
        """Manager.recent() delegates to QuerySet."""
        now = timezone.now()

        # Create a recent execution
        recent_exec = CorpusActionExecution.objects.create(
            corpus_action=self.action,
            document=self.document,
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=now - timedelta(hours=1),
            creator=self.user,
        )

        result = list(CorpusActionExecution.objects.recent(hours=24))

        self.assertIn(recent_exec, result)
