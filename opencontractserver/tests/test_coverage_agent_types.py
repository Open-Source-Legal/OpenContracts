"""Coverage-focused tests for ``config/graphql/agent_types.py`` resolvers.

Targets resolver logic the graphene->strawberry port left without direct
test coverage: the ``CorpusActionType`` sub-connections (``executions``,
``createdAnnotations``, ``analyses``, ``extracts``, ``agentResults``), the
FK-visibility / enum / JSON-scalar field resolvers on
``CorpusActionExecutionType`` / ``AgentActionResultType`` /
``AgentConfigurationType``, the ``preAuthorizedTools`` resolver on
``CorpusActionTemplateType``, and the ``AgentConfigurationType`` node lookup
guard. See ``opencontractserver/tests/test_corpus_action_graphql.py`` and
``opencontractserver/tests/test_fk_visibility_traversal.py`` for the
established conventions this file follows.
"""

from __future__ import annotations

import datetime
import json

from django.test import TestCase
from django.utils import timezone
from graphql_relay import to_global_id

from config.graphql.agent_types import AgentConfigurationType
from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.agents.models import AgentActionResult, AgentConfiguration
from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import Annotation
from opencontractserver.conversations.models import Conversation
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTemplate,
    CorpusActionTrigger,
)
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


class _RequestContext:
    """Minimal GraphQL context exposing only the ``user`` attribute resolvers read."""

    def __init__(self, user):
        self.user = user


def _grant_crud(user, obj):
    set_permissions_for_obj_to_user(user, obj, [PermissionTypes.CRUD])


def _execute(user, query, variables=None):
    return Client(schema, context_value=_RequestContext(user)).execute(
        query, variables=variables
    )


class CorpusActionSubConnectionsTestCase(TestCase):
    """``CorpusActionType.executions/createdAnnotations/analyses/extracts/
    agentResults`` — connection resolvers with graphene-parity filter-arg
    wiring — plus the ``myPermissions``/``isPublished``/``objectSharedWith``
    trio.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="subconn_owner", password="testpass"
        )
        self.corpus = Corpus.objects.create(title="Subconn Corpus", creator=self.user)
        _grant_crud(self.user, self.corpus)

        self.fieldset = Fieldset.objects.create(
            name="Subconn Fieldset", description="", creator=self.user
        )
        _grant_crud(self.user, self.fieldset)

        self.analyzer = Analyzer.objects.create(
            id="Subconn Analyzer",
            description="",
            creator=self.user,
            task_name="totally.not.a.real.task",
        )

        # Deliberately NOT permission-granted (relies on creator visibility):
        # config.graphql.core.permissions.resolve_object_shared_with carries a
        # documented graphene-parity quirk that raises when a guardian
        # per-user permission row actually exists on the queried object, so
        # this instance is left with only creator-based visibility.
        self.corpus_action = CorpusAction.objects.create(
            name="Subconn Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        self.document = Document.objects.create(
            title="Subconn Doc", creator=self.user, is_public=False
        )
        _grant_crud(self.user, self.document)

        self.annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            corpus_action=self.corpus_action,
            creator=self.user,
            raw_text="subconn coverage annotation",
            is_public=True,
        )

        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer, corpus_action=self.corpus_action, creator=self.user
        )

        self.extract = Extract.objects.create(
            name="Subconn Extract",
            fieldset=self.fieldset,
            corpus_action=self.corpus_action,
            creator=self.user,
        )

        self.execution = CorpusActionExecution.objects.create(
            corpus_action=self.corpus_action,
            corpus=self.corpus,
            document=self.document,
            action_type=CorpusActionExecution.ActionType.FIELDSET,
            status=CorpusActionExecution.Status.COMPLETED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.user,
        )

        self.agent_result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )

    QUERY = """
        query ($corpusId: ID) {
            corpusActions(corpusId: $corpusId) {
                edges {
                    node {
                        myPermissions
                        isPublished
                        objectSharedWith
                        executions(status: COMPLETED, actionType: FIELDSET) {
                            totalCount
                            edges { node { id status actionType } }
                        }
                        createdAnnotations(structural: false) {
                            totalCount
                            edges { node { id } }
                        }
                        analyses {
                            totalCount
                            edges { node { id } }
                        }
                        extracts {
                            totalCount
                            edges { node { id } }
                        }
                        agentResults(status: COMPLETED) {
                            totalCount
                            edges { node { id } }
                        }
                    }
                }
            }
        }
    """

    def test_sub_connections_and_permission_fields(self):
        result = _execute(
            self.user,
            self.QUERY,
            {"corpusId": to_global_id("CorpusType", self.corpus.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["corpusActions"]["edges"][0]["node"]

        self.assertEqual(node["executions"]["totalCount"], 1)
        execution_node = node["executions"]["edges"][0]["node"]
        self.assertEqual(execution_node["status"], "COMPLETED")
        self.assertEqual(execution_node["actionType"], "FIELDSET")

        self.assertEqual(node["createdAnnotations"]["totalCount"], 1)
        self.assertEqual(node["analyses"]["totalCount"], 1)
        self.assertEqual(node["extracts"]["totalCount"], 1)
        self.assertEqual(node["agentResults"]["totalCount"], 1)

        # Creator-owned, never explicitly shared: deterministic empty/False.
        self.assertEqual(node["myPermissions"], [])
        self.assertIs(node["isPublished"], False)
        self.assertEqual(node["objectSharedWith"], [])

    def test_executions_filter_excludes_non_matching_status(self):
        result = _execute(
            self.user,
            """
            query ($corpusId: ID) {
                corpusActions(corpusId: $corpusId) {
                    edges { node { executions(status: FAILED) { totalCount } } }
                }
            }
            """,
            {"corpusId": to_global_id("CorpusType", self.corpus.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["corpusActions"]["edges"][0]["node"]
        self.assertEqual(node["executions"]["totalCount"], 0)

    def test_agent_results_filter_excludes_non_matching_status(self):
        result = _execute(
            self.user,
            """
            query ($corpusId: ID) {
                corpusActions(corpusId: $corpusId) {
                    edges { node { agentResults(status: FAILED) { totalCount } } }
                }
            }
            """,
            {"corpusId": to_global_id("CorpusType", self.corpus.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["corpusActions"]["edges"][0]["node"]
        self.assertEqual(node["agentResults"]["totalCount"], 0)


class CorpusActionExecutionFieldResolverTestCase(TestCase):
    """``CorpusActionExecutionType`` field resolvers: FK visibility, enum
    coercion, JSON scalar resolution, computed durations, and the
    permission-annotation trio.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="cae_owner", password="pw")

        self.corpus = Corpus.objects.create(title="CAE Corpus", creator=self.owner)
        _grant_crud(self.owner, self.corpus)

        self.fieldset = Fieldset.objects.create(
            name="CAE Fieldset", description="", creator=self.owner
        )
        _grant_crud(self.owner, self.fieldset)

        self.corpus_action = CorpusAction.objects.create(
            name="CAE Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.owner,
        )

        self.visible_document = Document.objects.create(
            title="CAE Visible Doc", creator=self.owner, is_public=True
        )
        self.conversation = Conversation.objects.create(
            title="CAE Conversation", creator=self.owner, is_public=True
        )

        started = timezone.now()
        self.queued_at = started - datetime.timedelta(seconds=5)
        self.completed_at = started + datetime.timedelta(seconds=42)

        self.execution = CorpusActionExecution.objects.create(
            corpus_action=self.corpus_action,
            corpus=self.corpus,
            document=self.visible_document,
            conversation=self.conversation,
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.FAILED,
            trigger=CorpusActionTrigger.NEW_MESSAGE,
            queued_at=self.queued_at,
            started_at=started,
            completed_at=self.completed_at,
            affected_objects=[{"type": "annotation", "id": 1}],
            execution_metadata={"model": "gpt-4"},
            error_message="boom",
            error_traceback="Traceback (most recent call last): ...",
            creator=self.owner,
        )

    FIELDS_QUERY = """
        query ($corpusActionId: ID) {
            corpusActionExecutions(corpusActionId: $corpusActionId, status: "failed") {
                edges {
                    node {
                        document { id }
                        conversation { id }
                        actionType
                        status
                        trigger
                        affectedObjects
                        executionMetadata
                        errorMessage
                        errorTraceback
                        durationSeconds
                        waitTimeSeconds
                        myPermissions
                        isPublished
                        objectSharedWith
                    }
                }
            }
        }
    """

    def test_execution_fields_resolve_for_owner(self):
        result = _execute(
            self.owner,
            self.FIELDS_QUERY,
            {"corpusActionId": to_global_id("CorpusActionType", self.corpus_action.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["corpusActionExecutions"]["edges"][0]["node"]

        self.assertEqual(
            node["document"]["id"],
            to_global_id("DocumentType", self.visible_document.id),
        )
        self.assertEqual(
            node["conversation"]["id"],
            to_global_id("ConversationType", self.conversation.id),
        )
        self.assertEqual(node["actionType"], "AGENT")
        self.assertEqual(node["status"], "FAILED")
        self.assertEqual(node["trigger"], "NEW_MESSAGE")
        self.assertEqual(
            [json.loads(item) for item in node["affectedObjects"]],
            [{"type": "annotation", "id": 1}],
        )
        self.assertEqual(json.loads(node["executionMetadata"]), {"model": "gpt-4"})
        self.assertEqual(node["errorMessage"], "boom")
        self.assertEqual(
            node["errorTraceback"], "Traceback (most recent call last): ..."
        )
        self.assertEqual(node["durationSeconds"], 42.0)
        self.assertEqual(node["waitTimeSeconds"], 5.0)

        # Creator-owned, never explicitly shared: deterministic empty/False.
        self.assertEqual(node["myPermissions"], [])
        self.assertIs(node["isPublished"], False)
        self.assertEqual(node["objectSharedWith"], [])

    def test_document_and_conversation_hidden_when_target_not_visible(self):
        """A FK pointing at another user's private row must resolve to
        ``null`` rather than leaking the target's fields (mirrors
        ``test_fk_visibility_traversal.py`` at the full-schema level for
        this specific type's ``document``/``conversation`` wiring).
        """
        stranger = User.objects.create_user(username="cae_stranger", password="pw")
        stranger_doc = Document.objects.create(
            title="Stranger Doc", creator=stranger, is_public=False
        )
        stranger_conversation = Conversation.objects.create(
            title="Stranger Conversation", creator=stranger, is_public=False
        )

        CorpusActionExecution.objects.create(
            corpus_action=self.corpus_action,
            corpus=self.corpus,
            document=stranger_doc,
            conversation=stranger_conversation,
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.SKIPPED,
            trigger=CorpusActionTrigger.NEW_THREAD,
            queued_at=timezone.now(),
            creator=self.owner,
        )

        result = _execute(
            self.owner,
            """
            query ($corpusActionId: ID) {
                corpusActionExecutions(corpusActionId: $corpusActionId, status: "skipped") {
                    edges { node { document { id } conversation { id } } }
                }
            }
            """,
            {"corpusActionId": to_global_id("CorpusActionType", self.corpus_action.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["corpusActionExecutions"]["edges"][0]["node"]
        self.assertIsNone(
            node["document"], "another user's private document leaked via the FK"
        )
        self.assertIsNone(
            node["conversation"],
            "another user's private conversation leaked via the FK",
        )


class AgentConfigurationFieldResolverTestCase(TestCase):
    """``AgentConfigurationType`` scalar field resolvers, the mention-format
    helper's both branches, and the ``get_node`` singular-lookup guard.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="agentcfg_owner", password="pw")
        self.corpus = Corpus.objects.create(title="AgentCfg Corpus", creator=self.user)
        _grant_crud(self.user, self.corpus)

        self.agent = AgentConfiguration.objects.create(
            name="Coverage Agent",
            slug="coverage-agent",
            description="A test agent",
            system_instructions="Be helpful",
            scope=AgentConfiguration.SCOPE_CORPUS,
            corpus=self.corpus,
            preferred_llm="anthropic:claude-haiku-4-5",
            avatar_url="https://example.com/avatar.png",
            is_active=True,
            creator=self.user,
        )

    FIELDS_QUERY = """
        query ($id: ID!) {
            agent(id: $id) {
                systemInstructions
                preferredLlm
                avatarUrl
                mentionFormat
                corpus { id }
                myPermissions
                isPublished
                objectSharedWith
            }
        }
    """

    def test_agent_field_resolvers(self):
        result = _execute(
            self.user,
            self.FIELDS_QUERY,
            {"id": to_global_id("AgentConfigurationType", self.agent.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["agent"]

        self.assertEqual(node["systemInstructions"], "Be helpful")
        self.assertEqual(node["preferredLlm"], "anthropic:claude-haiku-4-5")
        self.assertEqual(node["avatarUrl"], "https://example.com/avatar.png")
        self.assertEqual(node["mentionFormat"], "@agent:coverage-agent")
        self.assertEqual(
            node["corpus"]["id"], to_global_id("CorpusType", self.corpus.id)
        )
        # Creator-owned, never explicitly shared: deterministic empty/False.
        self.assertEqual(node["myPermissions"], [])
        self.assertIs(node["isPublished"], False)
        self.assertEqual(node["objectSharedWith"], [])

    def test_mention_format_is_none_without_a_slug(self):
        AgentConfiguration.objects.filter(pk=self.agent.pk).update(slug="")

        result = _execute(
            self.user,
            "query ($id: ID!) { agent(id: $id) { mentionFormat } }",
            {"id": to_global_id("AgentConfigurationType", self.agent.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        self.assertIsNone(result["data"]["agent"]["mentionFormat"])

    def test_get_node_hook_guards_against_a_null_pk(self):
        """Direct call to ``_get_node_AgentConfigurationType``'s defensive
        ``pk is None`` guard (aliased onto the type as ``get_node`` by
        ``config.graphql.core.relay.register_type`` — see
        ``test_doc_annotations_prefetch_n_plus_one.py`` for the same direct-
        call pattern against another type's ``get_node`` hook).

        Unreachable via the served schema: the ``agent(id: ID!)`` argument is
        non-null and ``graphql_relay.from_global_id`` never returns ``None``
        for the pk half (a malformed id decodes to ``""``, not ``None``), so
        this pins the guard clause itself rather than a query-level scenario.
        """
        info = type("Info", (), {"context": _RequestContext(self.user)})()
        # ``get_node`` is installed onto the class at runtime by
        # ``register_type``'s aliasing (not statically declared) — see
        # ``test_doc_annotations_prefetch_n_plus_one.py`` for the same
        # mypy-invisible-but-real attribute accessed the same way.
        self.assertIsNone(AgentConfigurationType.get_node(info, None))  # type: ignore[attr-defined]


class AgentActionResultFieldResolverTestCase(TestCase):
    """``AgentActionResultType`` field resolvers: FK visibility, enum
    coercion, JSON scalar resolution, the ``executionRecord`` connection, and
    the permission-annotation trio.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="aar_owner", password="pw")

        self.corpus = Corpus.objects.create(title="AAR Corpus", creator=self.owner)
        _grant_crud(self.owner, self.corpus)

        self.fieldset = Fieldset.objects.create(
            name="AAR Fieldset", description="", creator=self.owner
        )
        _grant_crud(self.owner, self.fieldset)

        self.corpus_action = CorpusAction.objects.create(
            name="AAR Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.owner,
        )

        self.document = Document.objects.create(
            title="AAR Doc", creator=self.owner, is_public=True
        )
        self.conversation = Conversation.objects.create(
            title="AAR Conversation", creator=self.owner, is_public=True
        )
        self.triggering_conversation = Conversation.objects.create(
            title="AAR Triggering Conversation", creator=self.owner, is_public=True
        )

        started = timezone.now()
        self.completed_at = started + datetime.timedelta(seconds=17)

        self.agent_result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            conversation=self.conversation,
            triggering_conversation=self.triggering_conversation,
            status=AgentActionResult.Status.COMPLETED,
            started_at=started,
            completed_at=self.completed_at,
            agent_response="Done.",
            tools_executed=[{"name": "search_annotations"}],
            execution_metadata={"tokens": 10},
            creator=self.owner,
        )

        self.execution_record = CorpusActionExecution.objects.create(
            corpus_action=self.corpus_action,
            corpus=self.corpus,
            document=self.document,
            agent_result=self.agent_result,
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.COMPLETED,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            queued_at=timezone.now(),
            creator=self.owner,
        )

    FIELDS_QUERY = """
        query ($corpusActionId: ID) {
            agentActionResults(corpusActionId: $corpusActionId, status: "completed") {
                edges {
                    node {
                        document { id }
                        conversation { id }
                        triggeringConversation { id }
                        status
                        agentResponse
                        toolsExecuted
                        errorMessage
                        executionMetadata
                        durationSeconds
                        myPermissions
                        isPublished
                        objectSharedWith
                        executionRecord(status: COMPLETED, actionType: AGENT) {
                            totalCount
                            edges { node { id } }
                        }
                    }
                }
            }
        }
    """

    def test_agent_action_result_fields_resolve_for_owner(self):
        result = _execute(
            self.owner,
            self.FIELDS_QUERY,
            {"corpusActionId": to_global_id("CorpusActionType", self.corpus_action.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["agentActionResults"]["edges"][0]["node"]

        self.assertEqual(
            node["document"]["id"], to_global_id("DocumentType", self.document.id)
        )
        self.assertEqual(
            node["conversation"]["id"],
            to_global_id("ConversationType", self.conversation.id),
        )
        self.assertEqual(
            node["triggeringConversation"]["id"],
            to_global_id("ConversationType", self.triggering_conversation.id),
        )
        self.assertEqual(node["status"], "COMPLETED")
        self.assertEqual(node["agentResponse"], "Done.")
        self.assertEqual(
            [json.loads(item) for item in node["toolsExecuted"]],
            [{"name": "search_annotations"}],
        )
        self.assertEqual(node["errorMessage"], "")
        self.assertEqual(json.loads(node["executionMetadata"]), {"tokens": 10})
        self.assertEqual(node["durationSeconds"], 17.0)

        # Creator-owned, never explicitly shared: deterministic empty/False.
        self.assertEqual(node["myPermissions"], [])
        self.assertIs(node["isPublished"], False)
        self.assertEqual(node["objectSharedWith"], [])

        self.assertEqual(node["executionRecord"]["totalCount"], 1)
        self.assertEqual(
            node["executionRecord"]["edges"][0]["node"]["id"],
            to_global_id("CorpusActionExecutionType", self.execution_record.id),
        )

    def test_execution_record_filter_excludes_non_matching_status(self):
        result = _execute(
            self.owner,
            """
            query ($corpusActionId: ID) {
                agentActionResults(corpusActionId: $corpusActionId, status: "completed") {
                    edges { node { executionRecord(status: FAILED) { totalCount } } }
                }
            }
            """,
            {"corpusActionId": to_global_id("CorpusActionType", self.corpus_action.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["agentActionResults"]["edges"][0]["node"]
        self.assertEqual(node["executionRecord"]["totalCount"], 0)

    def test_triggering_conversation_hidden_when_target_not_visible(self):
        """The ``triggeringConversation`` FK must not leak another user's
        private conversation (distinct call site from ``conversation`` above:
        a different ``fk_id_attr``, ``"triggering_conversation_id"``)."""
        stranger = User.objects.create_user(username="aar_stranger", password="pw")
        stranger_conversation = Conversation.objects.create(
            title="Stranger Conversation", creator=stranger, is_public=False
        )

        AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=None,
            triggering_conversation=stranger_conversation,
            status=AgentActionResult.Status.PENDING,
            creator=self.owner,
        )

        result = _execute(
            self.owner,
            """
            query ($corpusActionId: ID) {
                agentActionResults(corpusActionId: $corpusActionId, status: "pending") {
                    edges { node { triggeringConversation { id } } }
                }
            }
            """,
            {"corpusActionId": to_global_id("CorpusActionType", self.corpus_action.id)},
        )
        self.assertIsNone(result.get("errors"), result)
        node = result["data"]["agentActionResults"]["edges"][0]["node"]
        self.assertIsNone(
            node["triggeringConversation"],
            "another user's private conversation leaked via triggeringConversation",
        )


class CorpusActionTemplateFieldResolverTestCase(TestCase):
    """``CorpusActionTemplateType.preAuthorizedTools`` resolver."""

    def setUp(self):
        self.user = User.objects.create_user(username="tmpl_owner", password="pw")
        CorpusActionTemplate.objects.all().delete()
        self.template = CorpusActionTemplate.objects.create(
            name="Coverage Template",
            description="desc",
            task_instructions="Do the thing.",
            pre_authorized_tools=["search_annotations", "update_document_description"],
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            is_active=True,
            creator=self.user,
        )

    def test_pre_authorized_tools_field_resolves(self):
        result = _execute(
            self.user,
            """
            query {
                corpusActionTemplates(isActive: true) {
                    edges { node { preAuthorizedTools } }
                }
            }
            """,
        )
        self.assertIsNone(result.get("errors"), result)
        edges = result["data"]["corpusActionTemplates"]["edges"]
        self.assertEqual(
            edges[0]["node"]["preAuthorizedTools"],
            ["search_annotations", "update_document_description"],
        )
