"""
Tests for agent configuration system in OpenContracts.

This module tests Issue #634: Backend: Configurable Agent/Bot Profiles

Tests cover:
1. Creating agent configurations (global and corpus-specific)
2. Agent configuration visibility and permissions
3. Scope validation (global vs corpus-specific)
4. GraphQL mutations and queries
5. Permission checks for agent management
6. ChatMessage agent_configuration relationship
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestAgentConfigurationModel(TestCase):
    """Test AgentConfiguration model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.admin_user = User.objects.create_user(
            username="agentmodel_admin",
            password="testpass123",
            email="agentmodel_admin@test.com",
            is_superuser=True,
        )

        cls.normal_user = User.objects.create_user(
            username="agentmodel_normal",
            password="testpass123",
            email="agentmodel_normal@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Agent Corpus",
            description="A corpus for testing agents",
            creator=cls.admin_user,
            is_public=False,  # Not public so we can test permissions
        )

        # Give normal_user access to the corpus
        set_permissions_for_obj_to_user(
            cls.normal_user, cls.corpus, [PermissionTypes.READ]
        )

    def test_create_global_agent(self):
        """Test creating a global agent configuration."""
        agent = AgentConfiguration.objects.create(
            name="Global Assistant",
            description="A helpful global assistant",
            system_instructions="You are a helpful assistant.",
            scope="GLOBAL",
            available_tools=["search", "summarize"],
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        self.assertEqual(agent.name, "Global Assistant")
        self.assertEqual(agent.scope, "GLOBAL")
        self.assertIsNone(agent.corpus)
        self.assertEqual(len(agent.available_tools), 2)
        self.assertTrue(agent.is_active)

    def test_create_corpus_agent(self):
        """Test creating a corpus-specific agent configuration."""
        agent = AgentConfiguration.objects.create(
            name="Corpus Expert",
            description="Expert in this corpus",
            system_instructions="You are an expert on this corpus.",
            scope="CORPUS",
            corpus=self.corpus,
            available_tools=["query", "analyze"],
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        self.assertEqual(agent.scope, "CORPUS")
        self.assertEqual(agent.corpus, self.corpus)
        self.assertTrue(agent.is_active)

    def test_corpus_agent_without_corpus_validation(self):
        """Test that corpus agents must have a corpus."""
        agent = AgentConfiguration(
            name="Invalid Agent",
            description="Should fail",
            system_instructions="Test",
            scope="CORPUS",
            corpus=None,  # Missing corpus
            creator=self.admin_user,
        )

        with self.assertRaises(ValidationError) as cm:
            agent.full_clean()

        self.assertIn("corpus", str(cm.exception).lower())

    def test_global_agent_with_corpus_validation(self):
        """Test that global agents cannot have a corpus."""
        agent = AgentConfiguration(
            name="Invalid Global Agent",
            description="Should fail",
            system_instructions="Test",
            scope="GLOBAL",
            corpus=self.corpus,  # Should not have corpus
            creator=self.admin_user,
        )

        with self.assertRaises(ValidationError) as cm:
            agent.full_clean()

        self.assertIn("corpus", str(cm.exception).lower())

    def test_agent_tools_configuration(self):
        """Test agent with tool configurations."""
        agent = AgentConfiguration.objects.create(
            name="Tool User",
            description="Agent with specific tools",
            system_instructions="Use tools wisely",
            scope="GLOBAL",
            available_tools=["search", "calculate", "summarize"],
            permission_required_tools=["delete", "modify"],
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        self.assertEqual(len(agent.available_tools), 3)
        self.assertEqual(len(agent.permission_required_tools), 2)
        self.assertIn("search", agent.available_tools)
        self.assertIn("delete", agent.permission_required_tools)

    def test_agent_badge_configuration(self):
        """Test agent with badge display configuration."""
        badge_config = {
            "icon": "Bot",
            "color": "#4A5568",
            "label": "AI Assistant",
        }

        agent = AgentConfiguration.objects.create(
            name="Badged Agent",
            description="Agent with badge config",
            system_instructions="I have a badge",
            scope="GLOBAL",
            badge_config=badge_config,
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        self.assertEqual(agent.badge_config["icon"], "Bot")
        self.assertEqual(agent.badge_config["color"], "#4A5568")

    def test_agent_string_representation(self):
        """Test agent string representation."""
        global_agent = AgentConfiguration.objects.create(
            name="Global Agent",
            description="Test",
            system_instructions="Test",
            scope="GLOBAL",
            creator=self.admin_user,
        )

        corpus_agent = AgentConfiguration.objects.create(
            name="Corpus Agent",
            description="Test",
            system_instructions="Test",
            scope="CORPUS",
            corpus=self.corpus,
            creator=self.admin_user,
        )

        self.assertIn("Global", str(global_agent))
        self.assertIn(self.corpus.title, str(corpus_agent))

    def test_agent_visible_to_user_global(self):
        """Test global agents are visible to all authenticated users."""
        global_agent = AgentConfiguration.objects.create(
            name="Public Agent",
            description="Visible to all",
            system_instructions="Test",
            scope="GLOBAL",
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        # Admin should see it
        visible_to_admin = AgentConfiguration.objects.visible_to_user(self.admin_user)
        self.assertIn(global_agent, visible_to_admin)

        # Normal user should also see it
        visible_to_normal = AgentConfiguration.objects.visible_to_user(self.normal_user)
        self.assertIn(global_agent, visible_to_normal)

    def test_agent_visible_to_user_corpus(self):
        """Test corpus agents are only visible to users with corpus access."""
        corpus_agent = AgentConfiguration.objects.create(
            name="Corpus Agent",
            description="Only for corpus users",
            system_instructions="Test",
            scope="CORPUS",
            corpus=self.corpus,
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        # Admin should see it (creator)
        visible_to_admin = AgentConfiguration.objects.visible_to_user(self.admin_user)
        self.assertIn(corpus_agent, visible_to_admin)

        # Normal user with corpus access should see it
        visible_to_normal = AgentConfiguration.objects.visible_to_user(self.normal_user)
        self.assertIn(corpus_agent, visible_to_normal)

        # User without corpus access should NOT see it
        other_user = User.objects.create_user(
            username="agentmodel_other",
            password="testpass123",
            email="agentmodel_other@test.com",
        )
        visible_to_other = AgentConfiguration.objects.visible_to_user(other_user)
        self.assertNotIn(corpus_agent, visible_to_other)

    def test_inactive_agent_not_visible(self):
        """Test inactive agents are not visible to non-superusers."""
        inactive_agent = AgentConfiguration.objects.create(
            name="Inactive Agent",
            description="Not active",
            system_instructions="Test",
            scope="GLOBAL",
            creator=self.admin_user,
            is_public=True,
            is_active=False,  # Inactive
        )

        # Superuser should see all agents
        visible_to_admin = AgentConfiguration.objects.visible_to_user(self.admin_user)
        self.assertIn(inactive_agent, visible_to_admin)

        # Normal user should NOT see inactive agent
        visible_to_normal = AgentConfiguration.objects.visible_to_user(self.normal_user)
        self.assertNotIn(inactive_agent, visible_to_normal)


class TestChatMessageAgentRelationship(TestCase):
    """Test ChatMessage agent_configuration relationship."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="chattest_user",
            password="testpass123",
            email="chattest_user@test.com",
        )

        cls.agent = AgentConfiguration.objects.create(
            name="Test Agent",
            description="For testing chat messages",
            system_instructions="Test",
            scope="GLOBAL",
            creator=cls.user,
            is_public=True,
            is_active=True,
        )

    def test_chat_message_with_agent(self):
        """Test creating a chat message with an agent configuration."""
        conversation = Conversation.objects.create(
            creator=self.user,
            title="Test Conversation",
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            creator=self.user,
            content="Hello, agent!",
            msg_type="USER",
        )

        agent_response = ChatMessage.objects.create(
            conversation=conversation,
            creator=self.user,
            content="Hello, human!",
            msg_type="LLM",
            agent_configuration=self.agent,
        )

        self.assertIsNone(message.agent_configuration)
        self.assertEqual(agent_response.agent_configuration, self.agent)

    def test_agent_deletion_sets_null(self):
        """Test that deleting an agent sets agent_configuration to null in messages."""
        conversation = Conversation.objects.create(
            creator=self.user,
            title="Test Conversation",
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            creator=self.user,
            content="Agent message",
            msg_type="LLM",
            agent_configuration=self.agent,
        )

        self.agent.delete()

        # Refresh message from database
        message.refresh_from_db()
        self.assertIsNone(message.agent_configuration)


class TestAgentConfigurationGraphQL(TestCase):
    """Test AgentConfiguration GraphQL mutations and queries."""

    def setUp(self):
        """Set up test client and users."""
        self.client = Client(schema)

        self.admin_user = User.objects.create_user(
            username="graphql_admin",
            password="testpass123",
            email="graphql_admin@test.com",
            is_superuser=True,
        )

        self.normal_user = User.objects.create_user(
            username="graphql_normal",
            password="testpass123",
            email="graphql_normal@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="For testing",
            creator=self.admin_user,
            is_public=True,
        )

        # Give normal user access to corpus
        set_permissions_for_obj_to_user(
            self.normal_user, self.corpus, [PermissionTypes.CRUD]
        )

    def test_query_agents(self):
        """Test querying agent configurations."""
        # Create test agents
        AgentConfiguration.objects.create(
            name="Global Agent",
            description="Test",
            system_instructions="Test",
            scope="GLOBAL",
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        AgentConfiguration.objects.create(
            name="Corpus Agent",
            description="Test",
            system_instructions="Test",
            scope="CORPUS",
            corpus=self.corpus,
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        query = """
            query {
                agents {
                    edges {
                        node {
                            id
                            name
                            scope
                        }
                    }
                }
            }
        """

        # Admin should see both
        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.admin_user})()
        )
        self.assertIsNone(result.get("errors"))
        agents = result["data"]["agents"]["edges"]
        self.assertEqual(len(agents), 2)

    def test_create_global_agent_mutation(self):
        """Test creating a global agent via GraphQL mutation."""
        mutation = """
            mutation {
                createAgentConfiguration(
                    name: "New Global Agent"
                    description: "Created via GraphQL"
                    systemInstructions: "You are a helpful assistant"
                    scope: "GLOBAL"
                    availableTools: ["search", "summarize"]
                    isPublic: true
                ) {
                    ok
                    message
                    agent {
                        id
                        name
                        scope
                        availableTools
                    }
                }
            }
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.admin_user})()
        )
        self.assertIsNone(result.get("errors"))
        if not result["data"]["createAgentConfiguration"]["ok"]:
            print(
                f"Global Agent Error: {result['data']['createAgentConfiguration']['message']}"
            )
        self.assertTrue(result["data"]["createAgentConfiguration"]["ok"])
        agent_data = result["data"]["createAgentConfiguration"]["agent"]
        self.assertEqual(agent_data["name"], "New Global Agent")
        self.assertEqual(agent_data["scope"], "GLOBAL")
        # Verify tools are present (GraphQL may serialize differently)
        self.assertIsNotNone(agent_data["availableTools"])

    def test_create_corpus_agent_mutation(self):
        """Test creating a corpus-specific agent via GraphQL mutation."""
        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                createAgentConfiguration(
                    name: "Corpus Agent"
                    description: "For a specific corpus"
                    systemInstructions: "You are a corpus expert"
                    scope: "CORPUS"
                    corpusId: "{corpus_gid}"
                    isPublic: true
                ) {{
                    ok
                    message
                    agent {{
                        id
                        name
                        scope
                        corpus {{
                            id
                        }}
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.admin_user})()
        )
        self.assertIsNone(result.get("errors"))
        if not result["data"]["createAgentConfiguration"]["ok"]:
            print(
                f"Corpus Agent Error: {result['data']['createAgentConfiguration']['message']}"
            )
        self.assertTrue(result["data"]["createAgentConfiguration"]["ok"])
        agent_data = result["data"]["createAgentConfiguration"]["agent"]
        self.assertEqual(agent_data["scope"], "CORPUS")
        self.assertIsNotNone(agent_data["corpus"])

    def test_update_agent_mutation(self):
        """Test updating an agent via GraphQL mutation."""
        agent = AgentConfiguration.objects.create(
            name="Original Name",
            description="Original description",
            system_instructions="Original instructions",
            scope="GLOBAL",
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        # Give admin CRUD permissions
        set_permissions_for_obj_to_user(self.admin_user, agent, [PermissionTypes.CRUD])

        agent_gid = to_global_id("AgentConfigurationType", agent.id)

        mutation = f"""
            mutation {{
                updateAgentConfiguration(
                    agentId: "{agent_gid}"
                    name: "Updated Name"
                    description: "Updated description"
                ) {{
                    ok
                    message
                    agent {{
                        id
                        name
                        description
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.admin_user})()
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateAgentConfiguration"]["ok"])
        agent_data = result["data"]["updateAgentConfiguration"]["agent"]
        self.assertEqual(agent_data["name"], "Updated Name")
        self.assertEqual(agent_data["description"], "Updated description")

    def test_delete_agent_mutation(self):
        """Test deleting an agent via GraphQL mutation."""
        agent = AgentConfiguration.objects.create(
            name="To Delete",
            description="Will be deleted",
            system_instructions="Test",
            scope="GLOBAL",
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        # Give admin CRUD permissions
        set_permissions_for_obj_to_user(self.admin_user, agent, [PermissionTypes.CRUD])

        agent_gid = to_global_id("AgentConfigurationType", agent.id)

        mutation = f"""
            mutation {{
                deleteAgentConfiguration(
                    agentId: "{agent_gid}"
                ) {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.admin_user})()
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteAgentConfiguration"]["ok"])

        # Verify agent was deleted
        with self.assertRaises(AgentConfiguration.DoesNotExist):
            AgentConfiguration.objects.get(id=agent.id)

    def test_create_global_agent_requires_superuser(self):
        """Test that only superusers can create global agents."""
        mutation = """
            mutation {
                createAgentConfiguration(
                    name: "Unauthorized"
                    description: "Should fail"
                    systemInstructions: "Test"
                    scope: "GLOBAL"
                    isPublic: true
                ) {
                    ok
                    message
                    agent {
                        id
                    }
                }
            }
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.normal_user})()
        )
        # Should have an error or ok=False
        if result.get("errors"):
            self.assertIn("superuser", str(result["errors"]).lower())
        else:
            self.assertFalse(result["data"]["createAgentConfiguration"]["ok"])
            self.assertIn(
                "superuser",
                result["data"]["createAgentConfiguration"]["message"].lower(),
            )

    def test_create_corpus_agent_requires_corpus_permission(self):
        """Test that users need corpus permissions to create corpus agents."""
        # Create a corpus the normal user doesn't have access to
        other_corpus = Corpus.objects.create(
            title="Other Corpus",
            description="No access",
            creator=self.admin_user,
            is_public=False,
        )

        corpus_gid = to_global_id("CorpusType", other_corpus.id)

        mutation = f"""
            mutation {{
                createAgentConfiguration(
                    name: "Unauthorized Corpus Agent"
                    description: "Should fail"
                    systemInstructions: "Test"
                    scope: "CORPUS"
                    corpusId: "{corpus_gid}"
                    isPublic: true
                ) {{
                    ok
                    message
                    agent {{
                        id
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.normal_user})()
        )
        # Should fail with "Corpus not found" to prevent IDOR enumeration
        if result.get("errors"):
            error_msg = str(result["errors"]).lower()
            self.assertTrue("corpus not found" in error_msg or "not found" in error_msg)
        else:
            self.assertFalse(result["data"]["createAgentConfiguration"]["ok"])
            msg = result["data"]["createAgentConfiguration"]["message"].lower()
            self.assertTrue("corpus not found" in msg or "not found" in msg)

    def test_filter_agents_by_corpus(self):
        """Test filtering agents by corpus."""
        # Create agents for different corpuses
        AgentConfiguration.objects.create(
            name="Corpus 1 Agent",
            description="Test",
            system_instructions="Test",
            scope="CORPUS",
            corpus=self.corpus,
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        other_corpus = Corpus.objects.create(
            title="Other Corpus",
            description="Test",
            creator=self.admin_user,
            is_public=True,
        )

        AgentConfiguration.objects.create(
            name="Corpus 2 Agent",
            description="Test",
            system_instructions="Test",
            scope="CORPUS",
            corpus=other_corpus,
            creator=self.admin_user,
            is_public=True,
            is_active=True,
        )

        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        query = f"""
            query {{
                agents(corpusId: "{corpus_gid}") {{
                    edges {{
                        node {{
                            id
                            name
                            corpus {{
                                id
                            }}
                        }}
                    }}
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.admin_user})()
        )
        self.assertIsNone(result.get("errors"))
        agents = result["data"]["agents"]["edges"]

        # Should only see agents for the specified corpus
        agent_names = [agent["node"]["name"] for agent in agents]
        self.assertIn("Corpus 1 Agent", agent_names)
        self.assertNotIn("Corpus 2 Agent", agent_names)
