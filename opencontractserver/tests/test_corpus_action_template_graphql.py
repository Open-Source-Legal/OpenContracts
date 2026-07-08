from django.contrib.auth import get_user_model
from graphql_relay import to_global_id

from config.graphql.testing import GraphQLTestCase
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusActionTemplate,
    CorpusActionTrigger,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusActionTemplateGraphQLTest(GraphQLTestCase):
    GRAPHQL_URL = "/graphql/"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="gqluser", password="testpass")
        CorpusActionTemplate.objects.all().delete()

    def setUp(self):
        self.client.login(username="gqluser", password="testpass")
        CorpusActionTemplate.objects.all().delete()

    def test_query_active_templates(self):
        CorpusActionTemplate.objects.create(
            name="GQL Template",
            description="Test template",
            task_instructions="Do something.",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            sort_order=10,
            is_active=True,
            creator=self.user,
        )
        CorpusActionTemplate.objects.create(
            name="Inactive Template",
            task_instructions="Inactive.",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            is_active=False,
            creator=self.user,
        )

        response = self.query("""
            query {
                corpusActionTemplates(isActive: true) {
                    edges {
                        node {
                            name
                            description
                            trigger
                            sortOrder
                            isActive
                        }
                    }
                }
            }
            """)
        self.assertResponseNoErrors(response)
        content = response.json()
        edges = content["data"]["corpusActionTemplates"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["node"]["name"], "GQL Template")
        self.assertEqual(edges[0]["node"]["trigger"], "ADD_DOCUMENT")

    def test_unauthenticated_returns_error(self):
        self.client.logout()
        response = self.query("""
            query {
                corpusActionTemplates {
                    edges { node { name } }
                }
            }
            """)
        content = response.json()
        self.assertTrue(len(content.get("errors", [])) > 0)


class AddTemplateToCorpusMutationTest(GraphQLTestCase):
    GRAPHQL_URL = "/graphql/"

    ADD_TEMPLATE_MUTATION = """
        mutation AddTemplateToCorpus($templateId: ID!, $corpusId: ID!) {
            addTemplateToCorpus(templateId: $templateId, corpusId: $corpusId) {
                ok
                message
                obj {
                    id
                    name
                    sourceTemplate {
                        id
                        name
                    }
                }
            }
        }
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="addtpluser", password="testpass")

    def setUp(self):
        self.client.login(username="addtpluser", password="testpass")
        self.template = CorpusActionTemplate.objects.create(
            name="Test Template",
            description="A test template",
            task_instructions="Do the thing.",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            is_active=True,
            creator=self.user,
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

    def tearDown(self):
        Corpus.objects.filter(creator=self.user).delete()
        CorpusActionTemplate.objects.filter(creator=self.user).delete()

    def test_add_template_to_corpus(self):
        response = self.query(
            self.ADD_TEMPLATE_MUTATION,
            variables={
                "templateId": to_global_id(
                    "CorpusActionTemplateType", self.template.pk
                ),
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
            },
        )
        self.assertResponseNoErrors(response)
        content = response.json()
        data = content["data"]["addTemplateToCorpus"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["obj"]["name"], self.template.name)
        self.assertEqual(data["obj"]["sourceTemplate"]["name"], self.template.name)

    def test_duplicate_template_rejected(self):
        variables = {
            "templateId": to_global_id("CorpusActionTemplateType", self.template.pk),
            "corpusId": to_global_id("CorpusType", self.corpus.pk),
        }
        # First call should succeed
        response = self.query(self.ADD_TEMPLATE_MUTATION, variables=variables)
        self.assertResponseNoErrors(response)
        first_data = response.json()["data"]["addTemplateToCorpus"]
        self.assertTrue(first_data["ok"])

        # Second call should be rejected as duplicate
        response = self.query(self.ADD_TEMPLATE_MUTATION, variables=variables)
        self.assertResponseNoErrors(response)
        second_data = response.json()["data"]["addTemplateToCorpus"]
        self.assertFalse(second_data["ok"])
        self.assertIn("already been added", second_data["message"])

    def test_inactive_template_rejected(self):
        self.template.is_active = False
        self.template.save()

        response = self.query(
            self.ADD_TEMPLATE_MUTATION,
            variables={
                "templateId": to_global_id(
                    "CorpusActionTemplateType", self.template.pk
                ),
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
            },
        )
        self.assertResponseNoErrors(response)
        data = response.json()["data"]["addTemplateToCorpus"]
        self.assertFalse(data["ok"])

    def test_unauthenticated_rejected(self):
        self.client.logout()
        response = self.query(
            self.ADD_TEMPLATE_MUTATION,
            variables={
                "templateId": to_global_id(
                    "CorpusActionTemplateType", self.template.pk
                ),
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
            },
        )
        content = response.json()
        self.assertTrue(len(content.get("errors", [])) > 0)
