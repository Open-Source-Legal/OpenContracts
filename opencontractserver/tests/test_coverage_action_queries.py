"""GraphQL-level coverage tests for ``config/graphql/action_queries.py``.

The four resolvers exercised here (``agentActionResults``,
``corpusActionExecutions``, ``corpusActionTrailStats``,
``documentCorpusActions``) had zero prior GraphQL-level coverage: their
underlying services are unit-tested elsewhere (see
``test_service_layer_phase5_behavioral.py`` for
``AgentActionResultService`` and ``permissioning/test_document_actions_permissions.py``
for ``DocumentActionsService``), but nothing had ever driven a real query
through the resolver glue in ``action_queries.py`` itself -- the
``from_global_id``/``int()`` argument parsing, the per-filter
defense-in-depth visibility checks, and the ``strip_unset`` + connection
wiring in the ``q_*`` entry points.
"""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.utils import timezone
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.agents.models import AgentActionResult
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
)
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


class TestContext:
    """Minimal context object -- resolvers only read ``.user`` off ``info.context``."""

    def __init__(self, user):
        self.user = user


def _grant_crud(user, obj) -> None:
    set_permissions_for_obj_to_user(user, obj, [PermissionTypes.CRUD])


class AgentActionResultsQueryTestCase(TestCase):
    """Covers ``_resolve_Query_agent_action_results`` / ``q_agent_action_results``."""

    QUERY = """
        query AgentActionResults(
            $corpusActionId: ID, $documentId: ID, $status: String
        ) {
            agentActionResults(
                corpusActionId: $corpusActionId
                documentId: $documentId
                status: $status
            ) {
                edges { node { id } }
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(username="aar_user", password="pw")
        self.client_ = Client(schema, context_value=TestContext(self.user))

        self.corpus = Corpus.objects.create(title="AAR Corpus", creator=self.user)
        _grant_crud(self.user, self.corpus)

        self.action = CorpusAction.objects.create(
            name="AAR Action",
            corpus=self.corpus,
            trigger="add_document",
            task_instructions="Summarize the document",
            creator=self.user,
        )
        _grant_crud(self.user, self.action)

        self.doc1 = Document.objects.create(title="AAR Doc 1", creator=self.user)
        self.doc2 = Document.objects.create(title="AAR Doc 2", creator=self.user)

        self.result_completed = AgentActionResult.objects.create(
            corpus_action=self.action,
            document=self.doc1,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )
        self.result_failed = AgentActionResult.objects.create(
            corpus_action=self.action,
            document=self.doc2,
            status=AgentActionResult.Status.FAILED,
            creator=self.user,
        )

    def _ids(self, result):
        return {
            edge["node"]["id"] for edge in result["data"]["agentActionResults"]["edges"]
        }

    def test_no_filters_returns_all_visible_results(self):
        result = self.client_.execute(self.QUERY, variables={})
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            self._ids(result),
            {
                to_global_id("AgentActionResultType", self.result_completed.id),
                to_global_id("AgentActionResultType", self.result_failed.id),
            },
        )

    def test_filter_by_document_id(self):
        result = self.client_.execute(
            self.QUERY,
            variables={"documentId": to_global_id("DocumentType", self.doc2.id)},
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            self._ids(result),
            {to_global_id("AgentActionResultType", self.result_failed.id)},
        )

    def test_filter_by_status(self):
        result = self.client_.execute(self.QUERY, variables={"status": "completed"})
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            self._ids(result),
            {to_global_id("AgentActionResultType", self.result_completed.id)},
        )

    def test_filter_by_visible_corpus_action_id(self):
        result = self.client_.execute(
            self.QUERY,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", self.action.id)
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            self._ids(result),
            {
                to_global_id("AgentActionResultType", self.result_completed.id),
                to_global_id("AgentActionResultType", self.result_failed.id),
            },
        )

    def test_filter_by_invisible_corpus_action_id_returns_empty(self):
        """Defense-in-depth: corpus_action_id filter with no CorpusAction visibility.

        The referenced action belongs to a private corpus owned by another
        user, with no permission grant, so the resolver's own visibility
        check (not just the underlying service's) must short-circuit to
        an empty connection.
        """
        outsider = User.objects.create_user(username="aar_outsider", password="pw")
        hidden_corpus = Corpus.objects.create(
            title="Hidden AAR Corpus", creator=outsider, is_public=False
        )
        hidden_action = CorpusAction.objects.create(
            name="Hidden AAR Action",
            corpus=hidden_corpus,
            trigger="add_document",
            task_instructions="Hidden",
            creator=outsider,
        )
        AgentActionResult.objects.create(
            corpus_action=hidden_action,
            status=AgentActionResult.Status.COMPLETED,
            creator=outsider,
        )

        result = self.client_.execute(
            self.QUERY,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", hidden_action.id)
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), set())


class CorpusActionExecutionsQueryTestCase(TestCase):
    """Covers ``_resolve_Query_corpus_action_executions`` / ``q_corpus_action_executions``."""

    QUERY = """
        query Executions(
            $corpusId: ID, $documentId: ID, $corpusActionId: ID,
            $status: String, $actionType: String, $since: DateTime
        ) {
            corpusActionExecutions(
                corpusId: $corpusId
                documentId: $documentId
                corpusActionId: $corpusActionId
                status: $status
                actionType: $actionType
                since: $since
            ) {
                edges { node { id } }
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(username="cae_user", password="pw")
        self.client_ = Client(schema, context_value=TestContext(self.user))

        self.corpus = Corpus.objects.create(title="CAE Corpus", creator=self.user)
        self.action = CorpusAction.objects.create(
            name="CAE Action",
            corpus=self.corpus,
            trigger="add_document",
            task_instructions="Do it",
            creator=self.user,
        )
        self.doc1 = Document.objects.create(title="CAE Doc 1", creator=self.user)
        self.doc2 = Document.objects.create(title="CAE Doc 2", creator=self.user)

        now = timezone.now()
        self.exec_completed = self._make_execution(
            document=self.doc1,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.COMPLETED,
            queued_at=now - datetime.timedelta(hours=3),
        )
        self.exec_failed = self._make_execution(
            document=self.doc2,
            action_type=CorpusActionExecution.ActionType.ANALYZER,
            status=CorpusActionExecution.Status.FAILED,
            queued_at=now - datetime.timedelta(hours=1),
        )
        self.since_cutoff = now - datetime.timedelta(hours=2)

        self.outsider = User.objects.create_user(username="cae_outsider", password="pw")

    def _make_execution(self, *, document, action_type, status, queued_at, corpus=None):
        return CorpusActionExecution.objects.create(
            corpus_action=self.action,
            document=document,
            corpus=corpus or self.corpus,
            action_type=action_type,
            status=status,
            queued_at=queued_at,
            trigger="add_document",
            creator=self.user,
        )

    def _ids(self, result):
        return {
            edge["node"]["id"]
            for edge in result["data"]["corpusActionExecutions"]["edges"]
        }

    def _exec_gid(self, execution):
        return to_global_id("CorpusActionExecutionType", execution.id)

    def test_no_filters_returns_all_visible(self):
        result = self.client_.execute(self.QUERY, variables={})
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            self._ids(result),
            {self._exec_gid(self.exec_completed), self._exec_gid(self.exec_failed)},
        )

    def test_filter_by_visible_corpus_id(self):
        result = self.client_.execute(
            self.QUERY,
            variables={"corpusId": to_global_id("CorpusType", self.corpus.id)},
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            self._ids(result),
            {self._exec_gid(self.exec_completed), self._exec_gid(self.exec_failed)},
        )

    def test_filter_by_invisible_corpus_id_returns_empty(self):
        hidden_corpus = Corpus.objects.create(
            title="Hidden CAE Corpus", creator=self.outsider, is_public=False
        )
        result = self.client_.execute(
            self.QUERY,
            variables={"corpusId": to_global_id("CorpusType", hidden_corpus.id)},
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), set())

    def test_filter_by_visible_document_id(self):
        result = self.client_.execute(
            self.QUERY,
            variables={"documentId": to_global_id("DocumentType", self.doc1.id)},
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), {self._exec_gid(self.exec_completed)})

    def test_filter_by_invisible_document_id_returns_empty(self):
        """Corpus + corpus_action ARE visible; only the document is not."""
        hidden_document = Document.objects.create(
            title="Hidden CAE Doc", creator=self.outsider, is_public=False
        )
        hidden_doc_execution = self._make_execution(
            document=hidden_document,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.QUEUED,
            queued_at=timezone.now(),
        )
        result = self.client_.execute(
            self.QUERY,
            variables={"documentId": to_global_id("DocumentType", hidden_document.id)},
        )
        self.assertIsNone(result.get("errors"))
        self.assertNotIn(self._exec_gid(hidden_doc_execution), self._ids(result))
        self.assertEqual(self._ids(result), set())

    def test_filter_by_visible_corpus_action_id(self):
        result = self.client_.execute(
            self.QUERY,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", self.action.id)
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            self._ids(result),
            {self._exec_gid(self.exec_completed), self._exec_gid(self.exec_failed)},
        )

    def test_filter_by_invisible_corpus_action_id_returns_empty(self):
        """Corpus IS visible; only the referenced corpus_action is not."""
        hidden_action = CorpusAction.objects.create(
            name="Hidden CAE Action",
            corpus=self.corpus,
            trigger="add_document",
            task_instructions="Hidden",
            creator=self.outsider,
        )
        result = self.client_.execute(
            self.QUERY,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", hidden_action.id)
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), set())

    def test_filter_by_status(self):
        result = self.client_.execute(self.QUERY, variables={"status": "failed"})
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), {self._exec_gid(self.exec_failed)})

    def test_filter_by_action_type(self):
        result = self.client_.execute(self.QUERY, variables={"actionType": "analyzer"})
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), {self._exec_gid(self.exec_failed)})

    def test_filter_by_since(self):
        result = self.client_.execute(
            self.QUERY, variables={"since": self.since_cutoff.isoformat()}
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), {self._exec_gid(self.exec_failed)})


class CorpusActionTrailStatsQueryTestCase(TestCase):
    """Covers ``_resolve_Query_corpus_action_trail_stats`` / ``q_corpus_action_trail_stats``."""

    QUERY = """
        query Stats($corpusId: ID!, $since: DateTime) {
            corpusActionTrailStats(corpusId: $corpusId, since: $since) {
                totalExecutions
                completed
                failed
                running
                queued
                skipped
                avgDurationSeconds
                fieldsetCount
                analyzerCount
                agentCount
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(username="stats_user", password="pw")
        self.client_ = Client(schema, context_value=TestContext(self.user))

        self.corpus = Corpus.objects.create(title="Stats Corpus", creator=self.user)
        self.action = CorpusAction.objects.create(
            name="Stats Action",
            corpus=self.corpus,
            trigger="add_document",
            task_instructions="Go",
            creator=self.user,
        )

        now = timezone.now()
        self.duration = datetime.timedelta(minutes=10)
        self._make_execution(
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.COMPLETED,
            queued_at=now - datetime.timedelta(hours=3),
            started_at=now - datetime.timedelta(hours=3),
            completed_at=now - datetime.timedelta(hours=3) + self.duration,
        )
        self._make_execution(
            action_type=CorpusActionExecution.ActionType.ANALYZER,
            status=CorpusActionExecution.Status.FAILED,
            queued_at=now - datetime.timedelta(hours=2),
        )
        self._make_execution(
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.RUNNING,
            queued_at=now - datetime.timedelta(hours=1),
            started_at=now - datetime.timedelta(hours=1),
        )
        self._make_execution(
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.QUEUED,
            queued_at=now - datetime.timedelta(minutes=30),
        )
        self._make_execution(
            action_type=CorpusActionExecution.ActionType.ANALYZER,
            status=CorpusActionExecution.Status.SKIPPED,
            queued_at=now - datetime.timedelta(minutes=15),
        )
        self.since_cutoff = now - datetime.timedelta(minutes=90)

        self.outsider = User.objects.create_user(
            username="stats_outsider", password="pw"
        )
        self.hidden_corpus = Corpus.objects.create(
            title="Hidden Stats Corpus", creator=self.outsider, is_public=False
        )

    def _make_execution(self, **kwargs):
        return CorpusActionExecution.objects.create(
            corpus_action=self.action,
            corpus=self.corpus,
            trigger="add_document",
            creator=self.user,
            **kwargs,
        )

    def test_stats_for_visible_corpus(self):
        result = self.client_.execute(
            self.QUERY,
            variables={"corpusId": to_global_id("CorpusType", self.corpus.id)},
        )
        self.assertIsNone(result.get("errors"))
        stats = result["data"]["corpusActionTrailStats"]
        self.assertEqual(stats["totalExecutions"], 5)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["running"], 1)
        self.assertEqual(stats["queued"], 1)
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["fieldsetCount"], 2)
        self.assertEqual(stats["analyzerCount"], 2)
        self.assertEqual(stats["agentCount"], 1)
        self.assertAlmostEqual(
            stats["avgDurationSeconds"], self.duration.total_seconds()
        )

    def test_stats_since_filters_older_executions(self):
        result = self.client_.execute(
            self.QUERY,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "since": self.since_cutoff.isoformat(),
            },
        )
        self.assertIsNone(result.get("errors"))
        stats = result["data"]["corpusActionTrailStats"]
        # Only the running/queued/skipped executions fall within the window.
        self.assertEqual(stats["totalExecutions"], 3)
        self.assertEqual(stats["completed"], 0)
        self.assertIsNone(stats["avgDurationSeconds"])

    def test_stats_for_invisible_corpus_returns_zeroed_stats(self):
        result = self.client_.execute(
            self.QUERY,
            variables={"corpusId": to_global_id("CorpusType", self.hidden_corpus.id)},
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            result["data"]["corpusActionTrailStats"],
            {
                "totalExecutions": 0,
                "completed": 0,
                "failed": 0,
                "running": 0,
                "queued": 0,
                "skipped": 0,
                "avgDurationSeconds": None,
                "fieldsetCount": 0,
                "analyzerCount": 0,
                "agentCount": 0,
            },
        )


class DocumentCorpusActionsQueryTestCase(TestCase):
    """Covers ``_resolve_Query_document_corpus_actions`` / ``q_document_corpus_actions``."""

    QUERY = """
        query DocActions($documentId: ID!, $corpusId: ID) {
            documentCorpusActions(documentId: $documentId, corpusId: $corpusId) {
                corpusActions { id name }
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(username="dca_user", password="pw")
        self.client_ = Client(schema, context_value=TestContext(self.user))

        self.corpus = Corpus.objects.create(title="DCA Corpus", creator=self.user)
        self.document = Document.objects.create(title="DCA Doc", creator=self.user)
        self.fieldset = Fieldset.objects.create(
            name="DCA Fieldset", description="Test Description", creator=self.user
        )
        self.action = CorpusAction.objects.create(
            name="DCA Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger="add_document",
            creator=self.user,
        )

    def test_with_corpus_id_returns_corpus_actions(self):
        result = self.client_.execute(
            self.QUERY,
            variables={
                "documentId": to_global_id("DocumentType", self.document.id),
                "corpusId": to_global_id("CorpusType", self.corpus.id),
            },
        )
        self.assertIsNone(result.get("errors"))
        actions = result["data"]["documentCorpusActions"]["corpusActions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["name"], "DCA Action")

    def test_without_corpus_id_returns_empty_corpus_actions(self):
        result = self.client_.execute(
            self.QUERY,
            variables={"documentId": to_global_id("DocumentType", self.document.id)},
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["documentCorpusActions"]["corpusActions"], [])

    def test_empty_document_id_raises_error(self):
        result = self.client_.execute(self.QUERY, variables={"documentId": ""})
        self.assertIsNotNone(result.get("errors"))
        self.assertIn("documentId is required", result["errors"][0]["message"])
