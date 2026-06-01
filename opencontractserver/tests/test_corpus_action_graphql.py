from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.analyzer.models import Analyzer
from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.extracts.models import Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


class TestContext:
    def __init__(self, user):
        self.user = user


class CorpusActionMutationTestCase(TestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", description="Test Description", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        # Create test fieldset
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset", description="Test Description", creator=self.user
        )
        set_permissions_for_obj_to_user(
            self.user, self.fieldset, [PermissionTypes.CRUD]
        )

        # Create test analyzer
        self.analyzer = Analyzer.objects.create(
            id="Test Analyzer",
            description="Test Description",
            creator=self.user,
            task_name="totally.not.a.real.task",
        )

        # Create test agent configuration
        self.agent_config = AgentConfiguration.objects.create(
            name="Test Agent Config",
            description="Test agent configuration",
            system_instructions="You are a helpful assistant",
            is_active=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.agent_config, [PermissionTypes.CRUD]
        )

    def test_create_corpus_action_with_fieldset(self):
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $name: String,
                $trigger: String!,
                $fieldsetId: ID,
                $disabled: Boolean,
                $runOnAllCorpuses: Boolean
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    name: $name,
                    trigger: $trigger,
                    fieldsetId: $fieldsetId,
                    disabled: $disabled,
                    runOnAllCorpuses: $runOnAllCorpuses
                ) {
                    ok
                    message
                    obj {
                        id
                        name
                        trigger
                        disabled
                        runOnAllCorpuses
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "name": "Test Action",
            "trigger": "add_document",
            "fieldsetId": to_global_id("FieldsetType", self.fieldset.id),
            "disabled": False,
            "runOnAllCorpuses": False,
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["createCorpusAction"]["message"],
            "Successfully created corpus action",
        )
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["name"], "Test Action"
        )
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["trigger"], "ADD_DOCUMENT"
        )

    def test_create_corpus_action_with_analyzer(self):
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $name: String,
                $trigger: String!,
                $analyzerId: ID,
                $disabled: Boolean,
                $runOnAllCorpuses: Boolean
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    name: $name,
                    trigger: $trigger,
                    analyzerId: $analyzerId,
                    disabled: $disabled,
                    runOnAllCorpuses: $runOnAllCorpuses
                ) {
                    ok
                    message
                    obj {
                        id
                        name
                        trigger
                        disabled
                        runOnAllCorpuses
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "name": "Test Analyzer Action",
            "trigger": "edit_document",
            "analyzerId": to_global_id("AnalyzerType", self.analyzer.id),
            "disabled": False,
            "runOnAllCorpuses": False,
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["name"], "Test Analyzer Action"
        )
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["trigger"], "EDIT_DOCUMENT"
        )

    def test_create_corpus_action_validation_error(self):
        """Test that providing both fieldset and analyzer IDs fails"""
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $fieldsetId: ID,
                $analyzerId: ID,
                $trigger: String!
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    fieldsetId: $fieldsetId,
                    analyzerId: $analyzerId,
                    trigger: $trigger
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "fieldsetId": to_global_id("FieldsetType", self.fieldset.id),
            "analyzerId": to_global_id("AnalyzerType", self.analyzer.id),
            "trigger": "add_document",
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["createCorpusAction"]["message"],
            "Only one of fieldset_id, analyzer_id, "
            "agent_config_id, or create_agent_inline can be provided",
        )

    def test_delete_corpus_action(self):
        # First create a corpus action
        corpus_action = CorpusAction.objects.create(
            name="Action to Delete",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger="add_document",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, corpus_action, [PermissionTypes.CRUD]
        )
        action_id = to_global_id("CorpusActionType", corpus_action.id)

        mutation = """
            mutation DeleteCorpusAction($id: String!) {
                deleteCorpusAction(id: $id) {
                    ok
                    message
                }
            }
        """

        variables = {"id": action_id}

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteCorpusAction"]["ok"])
        self.assertEqual(result["data"]["deleteCorpusAction"]["message"], "Success!")

        # Verify the action was actually deleted
        with self.assertRaises(CorpusAction.DoesNotExist):
            CorpusAction.objects.get(id=corpus_action.id)

    def test_query_corpus_actions(self):
        # Create some test actions
        action1 = CorpusAction.objects.create(
            name="Test Action 1",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger="add_document",
            creator=self.user,
        )
        action2 = CorpusAction.objects.create(
            name="Test Action 2",
            corpus=self.corpus,
            analyzer=self.analyzer,
            trigger="edit_document",
            disabled=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, action1, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(self.user, action2, [PermissionTypes.CRUD])

        query = """
            query GetCorpusActions($corpusId: ID, $trigger: String, $disabled: Boolean) {
                corpusActions(corpusId: $corpusId, trigger: $trigger, disabled: $disabled) {
                    edges {
                        node {
                            id
                            name
                            trigger
                            disabled
                            runOnAllCorpuses
                        }
                    }
                }
            }
        """

        # Test filtering by corpus
        variables: dict[str, object] = {
            "corpusId": to_global_id("CorpusType", self.corpus.id)
        }
        result = self.graphene_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(len(result["data"]["corpusActions"]["edges"]), 2)

        # Test filtering by trigger
        variables["trigger"] = "add_document"
        result = self.graphene_client.execute(query, variables=variables)
        self.assertEqual(len(result["data"]["corpusActions"]["edges"]), 1)
        self.assertEqual(
            result["data"]["corpusActions"]["edges"][0]["node"]["name"], "Test Action 1"
        )

        # Test filtering by disabled status
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "disabled": True,
        }
        result = self.graphene_client.execute(query, variables=variables)
        self.assertEqual(len(result["data"]["corpusActions"]["edges"]), 1)
        self.assertEqual(
            result["data"]["corpusActions"]["edges"][0]["node"]["name"], "Test Action 2"
        )

    def test_create_corpus_action_with_agent_config(self):
        """Test creating a corpus action with an agent configuration."""
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $name: String,
                $trigger: String!,
                $agentConfigId: ID,
                $taskInstructions: String,
                $preAuthorizedTools: [String],
                $disabled: Boolean
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    name: $name,
                    trigger: $trigger,
                    agentConfigId: $agentConfigId,
                    taskInstructions: $taskInstructions,
                    preAuthorizedTools: $preAuthorizedTools,
                    disabled: $disabled
                ) {
                    ok
                    message
                    obj {
                        id
                        name
                        trigger
                        disabled
                        taskInstructions
                        preAuthorizedTools
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "name": "Test Agent Action",
            "trigger": "add_document",
            "agentConfigId": to_global_id(
                "AgentConfigurationType", self.agent_config.id
            ),
            "taskInstructions": "Summarize this document and update its description",
            "preAuthorizedTools": ["update_document_description", "search_annotations"],
            "disabled": False,
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["createCorpusAction"]["message"],
            "Successfully created corpus action",
        )
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["name"], "Test Agent Action"
        )
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["trigger"], "ADD_DOCUMENT"
        )
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["taskInstructions"],
            "Summarize this document and update its description",
        )
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["preAuthorizedTools"],
            ["update_document_description", "search_annotations"],
        )

    def test_create_corpus_action_with_agent_config_missing_prompt(self):
        """Test that creating an agent action without a prompt fails."""
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $trigger: String!,
                $agentConfigId: ID
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    trigger: $trigger,
                    agentConfigId: $agentConfigId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "trigger": "add_document",
            "agentConfigId": to_global_id(
                "AgentConfigurationType", self.agent_config.id
            ),
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["createCorpusAction"]["message"],
            "task_instructions is required for agent actions",
        )

    def test_create_corpus_action_with_agent_and_fieldset_fails(self):
        """Test that providing both agent_config and fieldset fails."""
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $trigger: String!,
                $agentConfigId: ID,
                $taskInstructions: String,
                $fieldsetId: ID
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    trigger: $trigger,
                    agentConfigId: $agentConfigId,
                    taskInstructions: $taskInstructions,
                    fieldsetId: $fieldsetId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "trigger": "add_document",
            "agentConfigId": to_global_id(
                "AgentConfigurationType", self.agent_config.id
            ),
            "taskInstructions": "Test prompt",
            "fieldsetId": to_global_id("FieldsetType", self.fieldset.id),
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["createCorpusAction"]["message"],
            "Only one of fieldset_id, analyzer_id, "
            "agent_config_id, or create_agent_inline can be provided",
        )

    def test_create_lightweight_agent_with_task_instructions_only(self):
        """Test creating a corpus action with only task_instructions (no agent_config)."""
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $trigger: String!,
                $taskInstructions: String
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    trigger: $trigger,
                    taskInstructions: $taskInstructions
                ) {
                    ok
                    message
                    obj {
                        id
                        taskInstructions
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "trigger": "add_document",
            "taskInstructions": "Summarize this document concisely.",
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["createCorpusAction"]["obj"]["taskInstructions"],
            "Summarize this document concisely.",
        )

    def test_create_action_with_no_action_type_fails(self):
        """Test that providing no action type at all fails."""
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $trigger: String!
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    trigger: $trigger
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "trigger": "add_document",
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpusAction"]["ok"])
        self.assertIn("Provide one of", result["data"]["createCorpusAction"]["message"])

    def test_create_action_task_instructions_on_fieldset_rejected(self):
        """Test that task_instructions cannot be set on fieldset actions."""
        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $trigger: String!,
                $fieldsetId: ID,
                $taskInstructions: String
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    trigger: $trigger,
                    fieldsetId: $fieldsetId,
                    taskInstructions: $taskInstructions
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "trigger": "add_document",
            "fieldsetId": to_global_id("FieldsetType", self.fieldset.id),
            "taskInstructions": "Should not be allowed",
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpusAction"]["ok"])
        self.assertIn(
            "task_instructions cannot be set",
            result["data"]["createCorpusAction"]["message"],
        )

    def test_create_action_inactive_agent_config_rejected(self):
        """Test that an inactive agent configuration is rejected.

        visible_to_user() filters out inactive configs, so the mutation
        sees DoesNotExist rather than reaching the explicit is_active check.
        """
        inactive_config = AgentConfiguration.objects.create(
            name="Inactive Agent",
            description="An inactive agent",
            system_instructions="Test",
            is_active=False,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, inactive_config, [PermissionTypes.CRUD]
        )

        mutation = """
            mutation CreateCorpusAction(
                $corpusId: ID!,
                $trigger: String!,
                $agentConfigId: ID,
                $taskInstructions: String
            ) {
                createCorpusAction(
                    corpusId: $corpusId,
                    trigger: $trigger,
                    agentConfigId: $agentConfigId,
                    taskInstructions: $taskInstructions
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "trigger": "add_document",
            "agentConfigId": to_global_id("AgentConfigurationType", inactive_config.id),
            "taskInstructions": "Test prompt",
        }

        result = self.graphene_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpusAction"]["ok"])
        self.assertIn(
            "not found",
            result["data"]["createCorpusAction"]["message"].lower(),
        )


class UpdateCorpusActionMutationTestCase(TestCase):
    """Tests for the UpdateCorpusAction GraphQL mutation."""

    UPDATE_MUTATION = """
        mutation UpdateCorpusAction(
            $id: ID!,
            $name: String,
            $trigger: String,
            $fieldsetId: ID,
            $analyzerId: ID,
            $agentConfigId: ID,
            $taskInstructions: String,
            $preAuthorizedTools: [String],
            $disabled: Boolean,
            $runOnAllCorpuses: Boolean
        ) {
            updateCorpusAction(
                id: $id,
                name: $name,
                trigger: $trigger,
                fieldsetId: $fieldsetId,
                analyzerId: $analyzerId,
                agentConfigId: $agentConfigId,
                taskInstructions: $taskInstructions,
                preAuthorizedTools: $preAuthorizedTools,
                disabled: $disabled,
                runOnAllCorpuses: $runOnAllCorpuses
            ) {
                ok
                message
                obj {
                    id
                    name
                    trigger
                    disabled
                    runOnAllCorpuses
                    taskInstructions
                    preAuthorizedTools
                }
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", password="testpassword"
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        self.corpus = Corpus.objects.create(
            title="Test Corpus", description="Test Description", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset", description="Test Description", creator=self.user
        )
        set_permissions_for_obj_to_user(
            self.user, self.fieldset, [PermissionTypes.CRUD]
        )

        self.analyzer = Analyzer.objects.create(
            id="Test Analyzer",
            description="Test Description",
            creator=self.user,
            task_name="totally.not.a.real.task",
        )

        self.agent_config = AgentConfiguration.objects.create(
            name="Test Agent Config",
            description="Test agent configuration",
            system_instructions="You are a helpful assistant",
            is_active=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.agent_config, [PermissionTypes.CRUD]
        )

        # Create a fieldset-based action to update
        self.fieldset_action = CorpusAction.objects.create(
            name="Fieldset Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger="add_document",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.fieldset_action, [PermissionTypes.CRUD]
        )

        # Create an agent-based action to update
        self.agent_action = CorpusAction.objects.create(
            name="Agent Action",
            corpus=self.corpus,
            agent_config=self.agent_config,
            task_instructions="Original instructions",
            trigger="add_document",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.agent_action, [PermissionTypes.CRUD]
        )

    def test_update_simple_fields(self):
        """Test updating name, trigger, disabled, and run_on_all_corpuses."""
        variables = {
            "id": to_global_id("CorpusActionType", self.fieldset_action.id),
            "name": "Updated Name",
            "trigger": "edit_document",
            "disabled": True,
            "runOnAllCorpuses": True,
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpusAction"]["ok"])
        obj = result["data"]["updateCorpusAction"]["obj"]
        self.assertEqual(obj["name"], "Updated Name")
        self.assertEqual(obj["trigger"], "EDIT_DOCUMENT")
        self.assertTrue(obj["disabled"])
        self.assertTrue(obj["runOnAllCorpuses"])

    def test_update_task_instructions_on_agent_action(self):
        """Test updating task_instructions on an agent-based action."""
        variables = {
            "id": to_global_id("CorpusActionType", self.agent_action.id),
            "taskInstructions": "New instructions for the agent",
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["updateCorpusAction"]["obj"]["taskInstructions"],
            "New instructions for the agent",
        )

    def test_update_pre_authorized_tools_on_agent_action(self):
        """Test updating pre_authorized_tools on an agent-based action."""
        variables = {
            "id": to_global_id("CorpusActionType", self.agent_action.id),
            "preAuthorizedTools": ["tool_one", "tool_two"],
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpusAction"]["ok"])
        self.assertEqual(
            result["data"]["updateCorpusAction"]["obj"]["preAuthorizedTools"],
            ["tool_one", "tool_two"],
        )

    def test_switch_from_fieldset_to_analyzer(self):
        """Test switching action type from fieldset to analyzer."""
        variables = {
            "id": to_global_id("CorpusActionType", self.fieldset_action.id),
            "analyzerId": to_global_id("AnalyzerType", self.analyzer.id),
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpusAction"]["ok"])
        # Verify the switch cleared agent fields
        self.fieldset_action.refresh_from_db()
        self.assertIsNone(self.fieldset_action.fieldset)
        self.assertEqual(self.fieldset_action.analyzer, self.analyzer)
        self.assertIsNone(self.fieldset_action.agent_config)
        self.assertEqual(self.fieldset_action.task_instructions, "")

    def test_switch_from_fieldset_to_agent(self):
        """Test switching action type from fieldset to agent config."""
        variables = {
            "id": to_global_id("CorpusActionType", self.fieldset_action.id),
            "agentConfigId": to_global_id(
                "AgentConfigurationType", self.agent_config.id
            ),
            "taskInstructions": "New agent task",
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpusAction"]["ok"])
        self.fieldset_action.refresh_from_db()
        self.assertIsNone(self.fieldset_action.fieldset)
        self.assertEqual(self.fieldset_action.agent_config, self.agent_config)
        self.assertEqual(self.fieldset_action.task_instructions, "New agent task")

    def test_switch_from_agent_to_fieldset(self):
        """Test switching from agent to fieldset clears agent fields."""
        variables = {
            "id": to_global_id("CorpusActionType", self.agent_action.id),
            "fieldsetId": to_global_id("FieldsetType", self.fieldset.id),
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpusAction"]["ok"])
        self.agent_action.refresh_from_db()
        self.assertEqual(self.agent_action.fieldset, self.fieldset)
        self.assertIsNone(self.agent_action.agent_config)
        self.assertEqual(self.agent_action.task_instructions, "")
        self.assertEqual(self.agent_action.pre_authorized_tools, [])

    def test_task_instructions_on_non_agent_action_rejected(self):
        """Test that setting task_instructions on a fieldset action is rejected."""
        variables = {
            "id": to_global_id("CorpusActionType", self.fieldset_action.id),
            "taskInstructions": "Should not be allowed",
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpusAction"]["ok"])
        self.assertIn(
            "task_instructions can only be set on agent-based actions",
            result["data"]["updateCorpusAction"]["message"],
        )

    def test_inactive_agent_config_rejected(self):
        """Test that switching to an inactive agent config is rejected.

        visible_to_user() filters out inactive configs, so the mutation
        sees DoesNotExist rather than reaching the explicit is_active check.
        """
        inactive_config = AgentConfiguration.objects.create(
            name="Inactive Agent",
            description="Inactive",
            system_instructions="Test",
            is_active=False,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, inactive_config, [PermissionTypes.CRUD]
        )

        variables = {
            "id": to_global_id("CorpusActionType", self.fieldset_action.id),
            "agentConfigId": to_global_id("AgentConfigurationType", inactive_config.id),
            "taskInstructions": "Test",
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpusAction"]["ok"])
        self.assertIn(
            "not found",
            result["data"]["updateCorpusAction"]["message"].lower(),
        )

    def test_update_by_non_creator_rejected(self):
        """Test that a non-creator cannot update the action."""
        # Create action owned by other_user but visible to self.user
        other_action = CorpusAction.objects.create(
            name="Other Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger="add_document",
            creator=self.other_user,
        )
        set_permissions_for_obj_to_user(self.user, other_action, [PermissionTypes.CRUD])

        variables = {
            "id": to_global_id("CorpusActionType", other_action.id),
            "name": "Hijacked Name",
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpusAction"]["ok"])
        self.assertIn(
            "only update your own",
            result["data"]["updateCorpusAction"]["message"],
        )

    def test_update_nonexistent_action(self):
        """Test updating a non-existent action returns proper error."""
        variables = {
            "id": to_global_id("CorpusActionType", 99999),
            "name": "Nope",
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpusAction"]["ok"])
        self.assertIn(
            "not found",
            result["data"]["updateCorpusAction"]["message"].lower(),
        )

    def test_update_nonexistent_fieldset_id(self):
        """Test switching to a non-existent fieldset returns proper error."""
        variables = {
            "id": to_global_id("CorpusActionType", self.agent_action.id),
            "fieldsetId": to_global_id("FieldsetType", 99999),
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpusAction"]["ok"])
        self.assertIn(
            "not found",
            result["data"]["updateCorpusAction"]["message"].lower(),
        )

    def test_update_nonexistent_analyzer_id(self):
        """Test switching to a non-existent analyzer returns proper error."""
        variables = {
            "id": to_global_id("CorpusActionType", self.agent_action.id),
            "analyzerId": to_global_id("AnalyzerType", "nonexistent-id"),
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpusAction"]["ok"])
        self.assertIn(
            "not found",
            result["data"]["updateCorpusAction"]["message"].lower(),
        )

    def test_update_nonexistent_agent_config_id(self):
        """Test switching to a non-existent agent config returns proper error."""
        variables = {
            "id": to_global_id("CorpusActionType", self.fieldset_action.id),
            "agentConfigId": to_global_id("AgentConfigurationType", 99999),
            "taskInstructions": "Test",
        }

        result = self.graphene_client.execute(self.UPDATE_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpusAction"]["ok"])
        self.assertIn(
            "not found",
            result["data"]["updateCorpusAction"]["message"].lower(),
        )
