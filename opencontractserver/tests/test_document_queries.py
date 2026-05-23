from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus, CorpusFolder
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
            query GetDocumentSummary($docId: ID, $corpusId: ID!) {
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
            query GetDocumentSummary($docId: ID, $corpusId: ID!) {
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


class DocumentFolderFilterQueryTestCase(TestCase):
    """Folder filtering on the ``documents`` connection must be descendant-aware.

    Reproduces the imported-corpus bug where every document is nested inside
    leaf folders: selecting a parent folder (or the corpus root) must surface
    the documents nested beneath it, otherwise the corpus appears empty.
    """

    QUERY = """
        query Docs($corpusId: String, $folderId: String) {
          documents(inCorpusWithId: $corpusId, inFolderId: $folderId) {
            edges { node { title } }
          }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(username="folderuser", password="secret")
        self.client = Client(schema, context_value=TestContext(self.user))

        self.corpus = Corpus.objects.create(title="Folder Corpus", creator=self.user)

        # parent -> child folder hierarchy; documents live only in the leaf.
        self.parent_folder = CorpusFolder.objects.create(
            corpus=self.corpus, name="Parent", creator=self.user
        )
        self.child_folder = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="Child",
            creator=self.user,
            parent=self.parent_folder,
        )

        # One document at corpus root, two nested in the leaf folder.
        root_doc = Document.objects.create(creator=self.user, title="Root Doc")
        leaf_doc_a = Document.objects.create(creator=self.user, title="Leaf Doc A")
        leaf_doc_b = Document.objects.create(creator=self.user, title="Leaf Doc B")
        self.corpus.add_document(document=root_doc, user=self.user)
        self.corpus.add_document(
            document=leaf_doc_a, user=self.user, folder=self.child_folder
        )
        self.corpus.add_document(
            document=leaf_doc_b, user=self.user, folder=self.child_folder
        )

        self.corpus_gid = to_global_id("CorpusType", self.corpus.id)
        self.parent_gid = to_global_id("CorpusFolderType", self.parent_folder.id)
        self.child_gid = to_global_id("CorpusFolderType", self.child_folder.id)

    def _titles(self, folder_id):
        result = self.client.execute(
            self.QUERY,
            variables={"corpusId": self.corpus_gid, "folderId": folder_id},
        )
        self.assertIsNone(result.get("errors"))
        return sorted(
            edge["node"]["title"] for edge in result["data"]["documents"]["edges"]
        )

    def test_parent_folder_includes_descendant_documents(self):
        """A parent folder with no direct documents still shows nested docs."""
        self.assertEqual(self._titles(self.parent_gid), ["Leaf Doc A", "Leaf Doc B"])

    def test_leaf_folder_returns_its_documents(self):
        """Selecting the leaf folder returns the documents directly inside it."""
        self.assertEqual(self._titles(self.child_gid), ["Leaf Doc A", "Leaf Doc B"])

    def test_root_returns_all_corpus_documents(self):
        """The corpus root (no folder selected) shows every document, foldered
        or not — otherwise a corpus whose docs are all foldered looks empty."""
        self.assertEqual(
            self._titles("__root__"),
            ["Leaf Doc A", "Leaf Doc B", "Root Doc"],
        )

    def test_cross_corpus_folder_returns_empty(self):
        """A folder from a different corpus must not leak documents through.

        ``in_folder`` validates that the folder belongs to the corpus named
        in ``inCorpusWithId``; mismatches are scoped to no rows rather than
        silently intersecting two corpora.
        """
        other_corpus = Corpus.objects.create(title="Other Corpus", creator=self.user)
        other_folder = CorpusFolder.objects.create(
            corpus=other_corpus, name="Other", creator=self.user
        )
        other_gid = to_global_id("CorpusFolderType", other_folder.id)
        self.assertEqual(self._titles(other_gid), [])

    def test_malformed_folder_id_returns_empty(self):
        """A folder id that cannot be decoded must produce zero rows, not a 500."""
        self.assertEqual(self._titles("not-a-global-id"), [])

    def test_root_without_corpus_returns_empty(self):
        """``__root__`` is only meaningful within a corpus context.

        Without ``inCorpusWithId`` the sentinel would otherwise pass the
        queryset through unchanged — every visible document, not "root
        documents" — which is a silent semantic change for any external
        client that calls ``documents(inFolderId: "__root__")`` alone.
        The filter defensively returns no documents in that case.
        """
        query = """
            query Docs($folderId: String) {
              documents(inFolderId: $folderId) {
                edges { node { title } }
              }
            }
        """
        result = self.client.execute(query, variables={"folderId": "__root__"})
        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["documents"]["edges"], [])
