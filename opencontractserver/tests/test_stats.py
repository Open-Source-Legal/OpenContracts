from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.feedback.models import UserFeedback

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class CorpusStatsTestCase(TestCase):
    def setUp(self):
        # Create users
        self.owner = User.objects.create_user(username="owner", password="password")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="password"
        )
        self.regular_user = User.objects.create_user(
            username="regular", password="password"
        )
        self.anonymous_user = AnonymousUser()

        # Create GraphQL clients
        self.owner_client = Client(schema, context_value=TestContext(self.owner))
        self.collaborator_client = Client(
            schema, context_value=TestContext(self.collaborator)
        )
        self.regular_client = Client(
            schema, context_value=TestContext(self.regular_user)
        )
        self.anonymous_client = Client(
            schema, context_value=TestContext(self.anonymous_user)
        )

        # Create a public corpus with related public objects
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )

        # Create a private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )

        # Create public documents
        for i in range(5):
            doc = Document.objects.create(
                title=f"Public Doc {i}", creator=self.owner, is_public=True
            )
            # Store the versioned document returned by add_document()
            doc, _, _ = self.public_corpus.add_document(document=doc, user=self.owner)

            # Create public annotations for each document
            for j in range(2):
                annotation = Annotation.objects.create(
                    document=doc,
                    creator=self.owner,
                    is_public=True,
                    corpus=self.public_corpus,
                )

                # Create a comment (UserFeedback) for each annotation
                UserFeedback.objects.create(
                    creator=self.owner, commented_annotation=annotation, is_public=True
                )

        # Create analyzer
        self.analyzer = Analyzer.objects.create(
            id="Task-Based Analyzer",
            description="Test Task Analyzer",
            task_name="test_task",
            creator=self.owner,
            manifest={},
        )

        # Create public analyses
        for i in range(3):
            Analysis.objects.create(
                creator=self.owner,
                analyzed_corpus=self.public_corpus,
                is_public=True,
                analyzer=self.analyzer,
            )

        self.fieldset = Fieldset.objects.create(
            name="TestFieldset",
            description="Test description",
            creator=self.owner,
        )

        # Create public extracts
        for i in range(2):
            Extract.objects.create(
                creator=self.owner,
                corpus=self.public_corpus,
                is_public=True,
                fieldset=self.fieldset,
            )

    def test_public_corpus_stats_query(self):
        query = """
        query($id: ID!) {
          corpusStats(corpusId: $id) {
            totalDocs
            totalAnnotations
            totalComments
            totalAnalyses
            totalExtracts
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", self.public_corpus.id)}

        expected_stats = {
            "totalDocs": 5,
            "totalAnnotations": 10,  # 2 annotations per document
            "totalComments": 10,  # 1 comment per annotation
            "totalAnalyses": 3,
            "totalExtracts": 2,
        }

        # Test for all user types
        for client in [
            self.owner_client,
            self.collaborator_client,
            self.regular_client,
            self.anonymous_client,
        ]:
            result = client.execute(query, variable_values=variables)
            self.assertIsNotNone(result.get("data"))
            stats = result["data"]["corpusStats"]
            self.assertEqual(stats, expected_stats)

    def test_private_corpus_stats_query(self):
        query = """
        query($id: ID!) {
          corpusStats(corpusId: $id) {
            totalDocs
            totalAnnotations
            totalComments
            totalAnalyses
            totalExtracts
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", self.private_corpus.id)}

        # Test for owner (should see stats)
        result = self.owner_client.execute(query, variable_values=variables)
        self.assertIsNotNone(result.get("data"))
        stats = result["data"]["corpusStats"]
        self.assertIsNotNone(stats)

        # Test for other user types (should not see stats)
        for client in [
            self.collaborator_client,
            self.regular_client,
            self.anonymous_client,
        ]:
            result = client.execute(query, variable_values=variables)
            self.assertEqual(
                {
                    "totalDocs": 0,
                    "totalAnnotations": 0,
                    "totalComments": 0,
                    "totalAnalyses": 0,
                    "totalExtracts": 0,
                },
                result["data"]["corpusStats"],
            )

    def test_nonexistent_corpus_stats_query(self):
        query = """
        query($id: ID!) {
          corpusStats(corpusId: $id) {
            totalDocs
            totalAnnotations
            totalComments
            totalAnalyses
            totalExtracts
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", 9999)}  # Non-existent ID

        # Test for all user types
        for client in [
            self.owner_client,
            self.collaborator_client,
            self.regular_client,
            self.anonymous_client,
        ]:
            result = client.execute(query, variable_values=variables)
            self.assertEqual(
                {
                    "totalDocs": 0,
                    "totalAnnotations": 0,
                    "totalComments": 0,
                    "totalAnalyses": 0,
                    "totalExtracts": 0,
                },
                result["data"]["corpusStats"],
            )
