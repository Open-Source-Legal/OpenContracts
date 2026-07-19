"""Tests for the RunCorpusAction mutation."""

from django.contrib.auth import get_user_model
from graphql_relay import to_global_id

from config.graphql.testing import GraphQLTestCase
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
)
from opencontractserver.documents.models import Document, DocumentPath

User = get_user_model()

RUN_CORPUS_ACTION_MUTATION = """
    mutation RunCorpusAction($corpusActionId: ID!, $documentId: ID!) {
        runCorpusAction(corpusActionId: $corpusActionId, documentId: $documentId) {
            ok
            message
            obj {
                id
                status
            }
        }
    }
"""


class TestRunCorpusAction(GraphQLTestCase):
    """Test the RunCorpusAction mutation."""

    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="rca-superuser", password="adminpass", email="rca@test.com"
        )
        self.regular_user = User.objects.create_user(
            username="rca-regular", password="regularpass"
        )
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.superuser)
        self.document = Document.objects.create(
            title="Test Doc", creator=self.superuser
        )
        # Add document to corpus via DocumentPath
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            path=f"/documents/doc_{self.document.pk}",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.superuser,
        )

        # Create an agent-based corpus action (lightweight — task_instructions only)
        self.action = CorpusAction.objects.create(
            corpus=self.corpus,
            name="Test Agent Action",
            trigger="add_document",
            task_instructions="Summarize this document.",
            creator=self.superuser,
        )

        # Create a non-agent action (fieldset-based) for negative testing
        from opencontractserver.extracts.models import Column, Fieldset

        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset", creator=self.superuser
        )
        Column.objects.create(
            fieldset=self.fieldset,
            name="Col",
            query="q",
            output_type="str",
            creator=self.superuser,
        )
        self.fieldset_action = CorpusAction.objects.create(
            corpus=self.corpus,
            name="Test Fieldset Action",
            trigger="add_document",
            fieldset=self.fieldset,
            creator=self.superuser,
        )

    def test_superuser_can_run_agent_action(self):
        """Superuser can manually trigger an agent action on a document."""
        self.client.force_login(self.superuser)
        response = self.query(
            RUN_CORPUS_ACTION_MUTATION,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", self.action.id),
                "documentId": to_global_id("DocumentType", self.document.id),
            },
        )
        content = response.json()
        data = content["data"]["runCorpusAction"]
        self.assertTrue(data["ok"])

        # Verify obj is returned with correct status
        self.assertIsNotNone(data["obj"])
        self.assertEqual(data["obj"]["status"], "QUEUED")

        # Verify execution record was created
        execution = CorpusActionExecution.objects.get()
        self.assertEqual(execution.status, CorpusActionExecution.Status.QUEUED)
        self.assertEqual(execution.corpus_action_id, self.action.id)
        self.assertEqual(execution.document_id, self.document.id)

    def test_regular_user_rejected(self):
        """Non-superuser gets permission denied."""
        self.client.force_login(self.regular_user)
        response = self.query(
            RUN_CORPUS_ACTION_MUTATION,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", self.action.id),
                "documentId": to_global_id("DocumentType", self.document.id),
            },
        )
        content = response.json()
        # user_passes_test returns error when non-superuser
        self.assertIn("errors", content)

    def test_rejects_non_agent_action(self):
        """Fieldset/analyzer actions are rejected."""
        self.client.force_login(self.superuser)
        response = self.query(
            RUN_CORPUS_ACTION_MUTATION,
            variables={
                "corpusActionId": to_global_id(
                    "CorpusActionType", self.fieldset_action.id
                ),
                "documentId": to_global_id("DocumentType", self.document.id),
            },
        )
        content = response.json()
        data = content["data"]["runCorpusAction"]
        self.assertFalse(data["ok"])
        self.assertIn("agent", data["message"].lower())

    def test_rejects_document_not_in_corpus(self):
        """Document must belong to the action's corpus."""
        other_doc = Document.objects.create(title="Other Doc", creator=self.superuser)
        self.client.force_login(self.superuser)
        response = self.query(
            RUN_CORPUS_ACTION_MUTATION,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", self.action.id),
                "documentId": to_global_id("DocumentType", other_doc.id),
            },
        )
        content = response.json()
        data = content["data"]["runCorpusAction"]
        self.assertFalse(data["ok"])
        self.assertIn("not in", data["message"].lower())

    def test_rejects_nonexistent_action(self):
        """Nonexistent action ID returns error."""
        self.client.force_login(self.superuser)
        response = self.query(
            RUN_CORPUS_ACTION_MUTATION,
            variables={
                "corpusActionId": to_global_id("CorpusActionType", 99999),
                "documentId": to_global_id("DocumentType", self.document.id),
            },
        )
        content = response.json()
        data = content["data"]["runCorpusAction"]
        self.assertFalse(data["ok"])


class TestInlineAgentCreationForDocumentTriggers(GraphQLTestCase):
    """Verify that create_agent_inline works for document triggers (add_document, edit_document)."""

    GRAPHQL_URL = "/graphql/"

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="inline-test-admin",
            password="adminpass",
            email="inline@test.com",
        )
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_inline_agent_creation_for_add_document_trigger(self):
        """create_agent_inline=True works for add_document trigger."""
        from opencontractserver.agents.models import AgentConfiguration

        self.client.force_login(self.user)
        response = self.query(
            """
            mutation CreateCorpusAction(
                $corpusId: ID!
                $trigger: String!
                $name: String
                $taskInstructions: String
                $createAgentInline: Boolean
                $inlineAgentName: String
                $inlineAgentInstructions: String
                $inlineAgentTools: [String]
            ) {
                createCorpusAction(
                    corpusId: $corpusId
                    trigger: $trigger
                    name: $name
                    taskInstructions: $taskInstructions
                    createAgentInline: $createAgentInline
                    inlineAgentName: $inlineAgentName
                    inlineAgentInstructions: $inlineAgentInstructions
                    inlineAgentTools: $inlineAgentTools
                ) {
                    ok
                    message
                    obj {
                        id
                        name
                        trigger
                        agentConfig { id name }
                        taskInstructions
                    }
                }
            }
            """,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "trigger": "add_document",
                "name": "Auto Summarizer",
                "taskInstructions": "Summarize the document and update its description.",
                "createAgentInline": True,
                "inlineAgentName": "Doc Summarizer Agent",
                "inlineAgentInstructions": "You are a document processing agent.",
                "inlineAgentTools": [
                    "load_document_txt_extract",
                    "update_document_description",
                ],
            },
        )
        content = response.json()
        data = content["data"]["createCorpusAction"]
        self.assertTrue(data["ok"], f"Mutation failed: {data['message']}")
        self.assertEqual(data["obj"]["trigger"], "ADD_DOCUMENT")
        self.assertIsNotNone(data["obj"]["agentConfig"])
        self.assertEqual(data["obj"]["agentConfig"]["name"], "Doc Summarizer Agent")
        self.assertEqual(
            data["obj"]["taskInstructions"],
            "Summarize the document and update its description.",
        )

        # Verify the agent was created with correct attributes
        agent = AgentConfiguration.objects.get(name="Doc Summarizer Agent")
        self.assertEqual(agent.scope, "CORPUS")
        self.assertEqual(agent.corpus_id, self.corpus.id)
        self.assertEqual(
            agent.available_tools,
            [
                "load_document_txt_extract",
                "update_document_description",
            ],
        )
