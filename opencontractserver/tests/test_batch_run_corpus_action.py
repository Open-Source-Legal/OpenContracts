"""Tests for the StartCorpusActionBatchRun mutation and the
``CorpusActionService.batch_run_on_corpus`` service method that backs it.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone
from graphene_django.utils.testing import GraphQLTestCase
from graphql_relay import to_global_id

from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTrigger,
)
from opencontractserver.corpuses.services import CorpusActionService
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


# Path used to mock the Celery dispatcher — the service imports it inline
# from ``opencontractserver.tasks.agent_tasks`` so we patch it at the source.
RUN_AGENT_TASK_PATH = "opencontractserver.tasks.agent_tasks.run_agent_corpus_action"


START_BATCH_RUN_MUTATION = """
    mutation StartCorpusActionBatchRun($corpusActionId: ID!) {
        startCorpusActionBatchRun(corpusActionId: $corpusActionId) {
            ok
            message
            queuedCount
            skippedAlreadyRunCount
            totalActiveDocuments
            executions {
                id
                status
            }
        }
    }
"""


def _add_doc_to_corpus(corpus: Corpus, doc: Document, user) -> DocumentPath:
    """Attach a document to a corpus via an active DocumentPath."""
    return DocumentPath.objects.create(
        document=doc,
        corpus=corpus,
        path=f"/documents/doc_{doc.pk}",
        version_number=1,
        is_current=True,
        is_deleted=False,
        creator=user,
    )


class _BatchRunFixtureMixin:
    """Common corpus / docs / action setup for both the service tests and the
    GraphQL tests below — keeps the fixture-build copy-paste in one place."""

    def _build_fixture(self):
        self.owner = User.objects.create_superuser(
            username="batch-owner", password="ownerpass", email="owner@test.com"
        )
        self.collaborator = User.objects.create_user(
            username="batch-collab", password="collabpass"
        )
        self.outsider = User.objects.create_user(
            username="batch-outsider", password="outsiderpass"
        )

        self.corpus = Corpus.objects.create(
            title="Batch Run Corpus", creator=self.owner
        )

        # Collaborator gets UPDATE on the corpus — the new mutation gate.
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.UPDATE]
        )

        # Five active docs in the corpus.
        self.docs = []
        for i in range(5):
            doc = Document.objects.create(title=f"Batch Doc {i}", creator=self.owner)
            _add_doc_to_corpus(self.corpus, doc, self.owner)
            self.docs.append(doc)

        # Lightweight agent action (task_instructions only — no agent_config).
        self.agent_action = CorpusAction.objects.create(
            corpus=self.corpus,
            name="Generate Descriptions",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            task_instructions="Read this document and update its description.",
            creator=self.owner,
        )

        # Fieldset action — negative-case fixture.
        from opencontractserver.extracts.models import Column, Fieldset

        self.fieldset = Fieldset.objects.create(
            name="Batch Test Fieldset", creator=self.owner
        )
        Column.objects.create(
            fieldset=self.fieldset,
            name="Col",
            query="q",
            output_type="str",
            creator=self.owner,
        )
        self.fieldset_action = CorpusAction.objects.create(
            corpus=self.corpus,
            name="Batch Test Fieldset Action",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            fieldset=self.fieldset,
            creator=self.owner,
        )


class CorpusActionBatchRunServiceTests(_BatchRunFixtureMixin, TransactionTestCase):
    """Service-layer tests for ``CorpusActionService.batch_run_on_corpus``.

    ``TransactionTestCase`` is required so the ``transaction.on_commit`` hook
    inside the service fires — that's how we verify the Celery dispatcher
    gets called once per eligible document.
    """

    def setUp(self):
        self._build_fixture()

    def test_collaborator_with_update_can_batch_run(self):
        """Non-superuser with corpus UPDATE can batch-run the action."""
        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.collaborator, action_id=self.agent_action.id
            )

        self.assertTrue(result.ok, result.error)
        summary = result.value
        assert summary is not None
        self.assertEqual(summary.queued_count, 5)
        self.assertEqual(summary.skipped_already_run_count, 0)
        self.assertEqual(summary.total_active_documents, 5)
        self.assertEqual(len(summary.executions), 5)

        # Every execution row has the manual_batch trigger.
        for execution in summary.executions:
            self.assertEqual(execution.trigger, CorpusActionTrigger.MANUAL_BATCH.value)
            self.assertEqual(execution.status, CorpusActionExecution.Status.QUEUED)
            self.assertEqual(
                execution.action_type, CorpusActionExecution.ActionType.AGENT
            )
            self.assertEqual(execution.corpus_id, self.corpus.id)
            self.assertEqual(execution.creator_id, self.collaborator.id)

        # Celery dispatcher fired exactly once per execution row.
        self.assertEqual(mock_task.delay.call_count, 5)

    def test_outsider_without_update_rejected(self):
        """A user without corpus UPDATE gets an IDOR-safe not-found error.

        Same message as the action-does-not-exist branch so attackers
        cannot enumerate existing actions by probing for differential
        errors.
        """
        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.outsider, action_id=self.agent_action.id
            )
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error.lower())
        mock_task.delay.assert_not_called()
        self.assertFalse(CorpusActionExecution.objects.exists())

    def test_nonexistent_action_returns_same_not_found(self):
        """Service returns the same generic error for missing actions
        (paired with ``test_outsider_without_update_rejected`` to pin the
        IDOR-safe equivalence)."""
        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=999999
            )
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error.lower())
        mock_task.delay.assert_not_called()

    def test_rejects_fieldset_action(self):
        """Fieldset actions must be refused at the service layer."""
        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=self.fieldset_action.id
            )
        self.assertFalse(result.ok)
        self.assertIn("agent", result.error.lower())
        mock_task.delay.assert_not_called()

    def test_rejects_disabled_action(self):
        """A disabled action cannot be batch-run."""
        self.agent_action.disabled = True
        self.agent_action.save()
        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=self.agent_action.id
            )
        self.assertFalse(result.ok)
        self.assertIn("disabled", result.error.lower())
        mock_task.delay.assert_not_called()

    def test_skips_already_completed_docs(self):
        """Documents that already have a COMPLETED execution are not re-queued."""
        # Mark the first two docs as already-completed for this action.
        for doc in self.docs[:2]:
            CorpusActionExecution.objects.create(
                corpus_action_id=self.agent_action.id,
                document=doc,
                corpus=self.corpus,
                action_type=CorpusActionExecution.ActionType.AGENT,
                status=CorpusActionExecution.Status.COMPLETED,
                trigger=CorpusActionTrigger.ADD_DOCUMENT,
                queued_at=timezone.now(),
                creator=self.owner,
            )

        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=self.agent_action.id
            )

        self.assertTrue(result.ok, result.error)
        summary = result.value
        assert summary is not None
        self.assertEqual(summary.queued_count, 3)
        self.assertEqual(summary.skipped_already_run_count, 2)
        self.assertEqual(summary.total_active_documents, 5)
        self.assertEqual(mock_task.delay.call_count, 3)

        # The fresh executions cover only the three never-run docs.
        queued_doc_ids = {e.document_id for e in summary.executions}
        already_run_doc_ids = {doc.id for doc in self.docs[:2]}
        self.assertTrue(queued_doc_ids.isdisjoint(already_run_doc_ids))

    def test_failed_executions_are_re_queued(self):
        """FAILED executions are not in the skip set — the batch button retries them."""
        CorpusActionExecution.objects.create(
            corpus_action_id=self.agent_action.id,
            document=self.docs[0],
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.FAILED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.owner,
        )

        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=self.agent_action.id
            )

        self.assertTrue(result.ok)
        summary = result.value
        assert summary is not None
        self.assertEqual(summary.queued_count, 5)
        self.assertEqual(summary.skipped_already_run_count, 0)
        self.assertEqual(mock_task.delay.call_count, 5)

    def test_running_executions_are_skipped(self):
        """In-flight (QUEUED / RUNNING) executions are skipped — no double-dispatch."""
        CorpusActionExecution.objects.create(
            corpus_action_id=self.agent_action.id,
            document=self.docs[0],
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.RUNNING,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.owner,
        )
        CorpusActionExecution.objects.create(
            corpus_action_id=self.agent_action.id,
            document=self.docs[1],
            corpus=self.corpus,
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.QUEUED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.owner,
        )

        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=self.agent_action.id
            )

        self.assertTrue(result.ok)
        summary = result.value
        assert summary is not None
        self.assertEqual(summary.queued_count, 3)
        self.assertEqual(summary.skipped_already_run_count, 2)
        self.assertEqual(mock_task.delay.call_count, 3)

    def test_all_docs_already_completed_returns_zero(self):
        """When every active doc has been run, queued_count is 0."""
        for doc in self.docs:
            CorpusActionExecution.objects.create(
                corpus_action_id=self.agent_action.id,
                document=doc,
                corpus=self.corpus,
                action_type=CorpusActionExecution.ActionType.AGENT,
                status=CorpusActionExecution.Status.COMPLETED,
                trigger=CorpusActionTrigger.ADD_DOCUMENT,
                queued_at=timezone.now(),
                creator=self.owner,
            )

        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=self.agent_action.id
            )

        self.assertTrue(result.ok)
        summary = result.value
        assert summary is not None
        self.assertEqual(summary.queued_count, 0)
        self.assertEqual(summary.skipped_already_run_count, 5)
        self.assertEqual(len(summary.executions), 0)
        mock_task.delay.assert_not_called()

    def test_soft_deleted_doc_path_is_excluded(self):
        """Documents whose only DocumentPath is soft-deleted are NOT processed."""
        # Soft-delete the first doc's only path.
        DocumentPath.objects.filter(document=self.docs[0]).update(is_deleted=True)

        with patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=self.agent_action.id
            )

        self.assertTrue(result.ok)
        summary = result.value
        assert summary is not None
        self.assertEqual(summary.total_active_documents, 4)
        self.assertEqual(summary.queued_count, 4)
        self.assertEqual(mock_task.delay.call_count, 4)

    def test_over_cap_rejected(self):
        """A would-be batch larger than BATCH_RUN_MAX_DOCS is refused.

        Patches the cap to a tiny number on the service module so we don't
        have to create 200+ Document rows in test setup. The constant is
        re-bound into the service module's namespace by the ``from``
        import at the top of ``corpus_actions.py``, so the patch must
        target that module-local name (not the constants module).
        """
        with patch(
            "opencontractserver.corpuses.services.corpus_actions.BATCH_RUN_MAX_DOCS",
            3,
        ), patch(RUN_AGENT_TASK_PATH) as mock_task:
            result = CorpusActionService.batch_run_on_corpus(
                user=self.owner, action_id=self.agent_action.id
            )

        self.assertFalse(result.ok)
        self.assertIn("cap", result.error.lower())
        mock_task.delay.assert_not_called()
        self.assertFalse(CorpusActionExecution.objects.exists())


class StartCorpusActionBatchRunGraphQLTests(_BatchRunFixtureMixin, GraphQLTestCase):
    """End-to-end GraphQL tests for the StartCorpusActionBatchRun mutation."""

    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        self._build_fixture()

    def test_happy_path(self):
        """Owner submits the mutation; receives counts and queued executions."""
        self.client.force_login(self.owner)
        with patch(RUN_AGENT_TASK_PATH):
            response = self.query(
                START_BATCH_RUN_MUTATION,
                variables={
                    "corpusActionId": to_global_id(
                        "CorpusActionType", self.agent_action.id
                    ),
                },
            )
        content = response.json()
        self.assertNotIn("errors", content, content)
        data = content["data"]["startCorpusActionBatchRun"]
        self.assertTrue(data["ok"], data["message"])
        self.assertEqual(data["queuedCount"], 5)
        self.assertEqual(data["skippedAlreadyRunCount"], 0)
        self.assertEqual(data["totalActiveDocuments"], 5)
        self.assertEqual(len(data["executions"]), 5)
        for execution in data["executions"]:
            self.assertEqual(execution["status"], "QUEUED")

    def test_collaborator_with_update_succeeds(self):
        """A non-superuser with corpus UPDATE can submit the mutation."""
        self.client.force_login(self.collaborator)
        with patch(RUN_AGENT_TASK_PATH):
            response = self.query(
                START_BATCH_RUN_MUTATION,
                variables={
                    "corpusActionId": to_global_id(
                        "CorpusActionType", self.agent_action.id
                    ),
                },
            )
        data = response.json()["data"]["startCorpusActionBatchRun"]
        self.assertTrue(data["ok"], data["message"])
        self.assertEqual(data["queuedCount"], 5)

    def test_outsider_rejected(self):
        """A user without corpus UPDATE cannot see the action (IDOR-safe denial)."""
        self.client.force_login(self.outsider)
        with patch(RUN_AGENT_TASK_PATH):
            response = self.query(
                START_BATCH_RUN_MUTATION,
                variables={
                    "corpusActionId": to_global_id(
                        "CorpusActionType", self.agent_action.id
                    ),
                },
            )
        content = response.json()
        data = content["data"]["startCorpusActionBatchRun"]
        self.assertFalse(data["ok"])
        # ``get_or_none`` returns None for either "not found" or "no READ" —
        # the message just says the action wasn't found.
        self.assertIn("not found", data["message"].lower())

    def test_rejects_fieldset_action(self):
        """Fieldset actions are refused with an explanatory message."""
        self.client.force_login(self.owner)
        with patch(RUN_AGENT_TASK_PATH):
            response = self.query(
                START_BATCH_RUN_MUTATION,
                variables={
                    "corpusActionId": to_global_id(
                        "CorpusActionType", self.fieldset_action.id
                    ),
                },
            )
        data = response.json()["data"]["startCorpusActionBatchRun"]
        self.assertFalse(data["ok"])
        self.assertIn("agent", data["message"].lower())

    def test_nonexistent_action_returns_not_found(self):
        """A nonexistent action ID returns a generic not-found error."""
        self.client.force_login(self.owner)
        response = self.query(
            START_BATCH_RUN_MUTATION,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", 999999),
            },
        )
        data = response.json()["data"]["startCorpusActionBatchRun"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())
