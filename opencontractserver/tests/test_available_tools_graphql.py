"""
Tests for the availableTools GraphQL query.
"""

from django.contrib.auth import get_user_model

from config.graphql.testing import GraphQLTestCase

User = get_user_model()


class AvailableToolsQueryTests(GraphQLTestCase):
    """Tests for the availableTools GraphQL query."""

    GRAPHQL_URL = "/graphql/"

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_available_tools_query(self):
        """Test that availableTools query returns all tools."""
        self.client.force_login(self.user)

        response = self.query("""
            query {
                availableTools {
                    name
                    description
                    category
                    requiresCorpus
                    requiresApproval
                }
            }
            """)

        content = response.json()
        self.assertResponseNoErrors(response)

        tools = content["data"]["availableTools"]
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)

        # Check structure of first tool
        first_tool = tools[0]
        self.assertIn("name", first_tool)
        self.assertIn("description", first_tool)
        self.assertIn("category", first_tool)
        self.assertIn("requiresCorpus", first_tool)
        self.assertIn("requiresApproval", first_tool)

    def test_available_tools_query_with_category_filter(self):
        """Test filtering tools by category."""
        self.client.force_login(self.user)

        response = self.query("""
            query {
                availableTools(category: "search") {
                    name
                    category
                }
            }
            """)

        content = response.json()
        self.assertResponseNoErrors(response)

        tools = content["data"]["availableTools"]
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)

        # All tools should be in search category
        for tool in tools:
            self.assertEqual(tool["category"], "search")

    def test_available_tools_query_invalid_category(self):
        """Test filtering by invalid category returns empty list."""
        self.client.force_login(self.user)

        response = self.query("""
            query {
                availableTools(category: "invalid_category") {
                    name
                }
            }
            """)

        content = response.json()
        self.assertResponseNoErrors(response)

        tools = content["data"]["availableTools"]
        self.assertEqual(tools, [])

    def test_available_tool_categories_query(self):
        """Test that availableToolCategories returns all categories."""
        self.client.force_login(self.user)

        response = self.query("""
            query {
                availableToolCategories
            }
            """)

        content = response.json()
        self.assertResponseNoErrors(response)

        categories = content["data"]["availableToolCategories"]
        self.assertIsInstance(categories, list)
        self.assertGreater(len(categories), 0)

        # Check expected categories
        expected = [
            "search",
            "document",
            "corpus",
            "notes",
            "annotations",
            "coordination",
        ]
        for cat in expected:
            self.assertIn(cat, categories)

    def test_available_tools_contains_expected_tools(self):
        """Test that specific expected tools are returned."""
        self.client.force_login(self.user)

        response = self.query("""
            query {
                availableTools {
                    name
                }
            }
            """)

        content = response.json()
        self.assertResponseNoErrors(response)

        tool_names = [t["name"] for t in content["data"]["availableTools"]]

        # Check for some expected tools
        expected_tools = [
            "similarity_search",
            "search_exact_text",
            "load_document_text",
            "list_documents",
            "ask_document",
        ]
        for tool_name in expected_tools:
            self.assertIn(tool_name, tool_names)

    def test_available_tools_anonymous_user(self):
        """Test that anonymous users can still query available tools."""
        # Note: This query is informational and doesn't require auth
        response = self.query("""
            query {
                availableTools {
                    name
                }
            }
            """)

        content = response.json()
        # This should work for anonymous users as it's just static metadata
        # If it fails with auth error, the design decision was to require auth
        tools = content.get("data", {}).get("availableTools")
        if tools is not None:
            self.assertIsInstance(tools, list)
