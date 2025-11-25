from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

User = get_user_model()


class TestContext:
    """Minimal context object expected by the GraphQL resolvers (only `user`)."""

    def __init__(self, user):
        self.user = user


class DocumentQueryTestCase(TestCase):
    """Test suite for document-level markdown summary GraphQL resolvers."""

    def setUp(self):
        # Create a regular user and GraphQL client
        self.user = User.objects.create_user(username="testuser", password="secret")
        self.client = Client(schema, context_value=TestContext(self.user))

        # Create a corpus and document owned by our user
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.document = Document.objects.create(
            creator=self.user,
            title="Test Document",
            description="Testing summaries",
        )
        # Add document to corpus for completeness
        self.corpus.add_document(document=self.document, user=self.user)

        # Add two summary versions for this document within the corpus
        self.document.update_summary(
            new_content="First summary version.",
            author=self.user,
            corpus=self.corpus,
        )
        self.document.update_summary(
            new_content="Second summary version.",
            author=self.user,
            corpus=self.corpus,
        )

        # Store global Relay IDs for later use
        self.document_gid = to_global_id("DocumentType", self.document.id)
        self.corpus_gid = to_global_id("CorpusType", self.corpus.id)

    def test_document_summary_queries(self):
        """Ensure summaryContent, currentSummaryVersion and summaryRevisions work as expected."""

        query = """
            query GetDocumentSummary($docId: String, $corpusId: ID!) {
              document(id: $docId) {
                id
                summaryContent(corpusId: $corpusId)
                currentSummaryVersion(corpusId: $corpusId)
                summaryRevisions(corpusId: $corpusId) {
                  version
                  snapshot
                }
              }
            }
        """

        variables = {"docId": self.document_gid, "corpusId": self.corpus_gid}
        result = self.client.execute(query, variables=variables)

        # The query should execute without errors
        self.assertIsNone(result.get("errors"))

        doc_data = result["data"]["document"]

        # Validate latest content and version
        self.assertEqual(doc_data["summaryContent"], "Second summary version.")
        self.assertEqual(doc_data["currentSummaryVersion"], 2)

        # Validate the revision list (expect 2 versions in ascending order)
        revisions = doc_data["summaryRevisions"]
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0]["version"], 1)
        self.assertEqual(revisions[0]["snapshot"], "First summary version.")
        self.assertEqual(revisions[1]["version"], 2)
        self.assertEqual(revisions[1]["snapshot"], "Second summary version.")

    def test_document_summary_queries_no_summary(self):
        """When no summary exists for the corpus, default values should be returned."""

        # Create another document without any summary
        unsummarised_doc = Document.objects.create(
            creator=self.user, title="No Summary", description="No summary yet"
        )
        self.corpus.add_document(document=unsummarised_doc, user=self.user)
        unsummarised_doc_gid = to_global_id("DocumentType", unsummarised_doc.id)

        query = """
            query GetDocumentSummary($docId: String, $corpusId: ID!) {
              document(id: $docId) {
                id
                summaryContent(corpusId: $corpusId)
                currentSummaryVersion(corpusId: $corpusId)
                summaryRevisions(corpusId: $corpusId) {
                  version
                }
              }
            }
        """

        variables = {"docId": unsummarised_doc_gid, "corpusId": self.corpus_gid}
        result = self.client.execute(query, variables=variables)

        self.assertIsNone(result.get("errors"))

        doc_data = result["data"]["document"]
        self.assertEqual(doc_data["summaryContent"], "")
        self.assertEqual(doc_data["currentSummaryVersion"], 0)
        self.assertEqual(doc_data["summaryRevisions"], [])
