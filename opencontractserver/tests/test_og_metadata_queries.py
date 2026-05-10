"""
Tests for Open Graph (OG) Metadata GraphQL Queries.

This module tests the public OG metadata queries used by the Cloudflare Worker
for social media link previews (PR #701).

Tests cover:
1. ogCorpusMetadata - Public corpus metadata retrieval
2. ogDocumentMetadata - Public standalone document metadata retrieval
3. ogDocumentInCorpusMetadata - Public document in corpus context metadata
4. ogThreadMetadata - Public discussion thread metadata
5. ogExtractMetadata - Public data extract metadata
6. Public/private filtering (only is_public=True entities return data)
7. Non-existent entity handling (returns None, not error)
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Extract, Fieldset

User = get_user_model()


class OGCorpusMetadataTestCase(TestCase):
    """Tests for ogCorpusMetadata GraphQL query."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for corpus OG metadata tests."""
        cls.user = User.objects.create_user(
            username="og_test_user",
            password="testpass123",
            email="og@test.com",
        )

        # Public corpus
        cls.public_corpus = Corpus.objects.create(
            title="Public Test Corpus",
            description="A public corpus for OG metadata testing",
            creator=cls.user,
            is_public=True,
        )

        # Private corpus
        cls.private_corpus = Corpus.objects.create(
            title="Private Test Corpus",
            description="A private corpus that should not be returned",
            creator=cls.user,
            is_public=False,
        )

        # Add some documents to public corpus
        for i in range(3):
            doc = Document.objects.create(
                title=f"Test Doc {i}",
                creator=cls.user,
                is_public=True,
            )
            cls.public_corpus.add_document(document=doc, user=cls.user)

    def setUp(self):
        """Set up test client with request context."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        # For OG queries, we simulate anonymous access
        self.request.user = None
        self.client = Client(schema, context_value=self.request)

    def test_public_corpus_returns_metadata(self):
        """Test that public corpus returns OG metadata."""
        query = """
            query GetOGCorpusMetadata($userSlug: String!, $corpusSlug: String!) {
                ogCorpusMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug) {
                    title
                    description
                    documentCount
                    creatorName
                    isPublic
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.public_corpus.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogCorpusMetadata"]
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Public Test Corpus")
        self.assertEqual(data["description"], "A public corpus for OG metadata testing")
        self.assertEqual(data["documentCount"], 3)
        # ``creatorName`` now surfaces the public slug, not the username.
        # Underscores in the username are normalised to hyphens by the
        # slug sanitizer (see ``opencontractserver.shared.slug_utils``).
        self.assertEqual(data["creatorName"], self.user.slug)
        self.assertTrue(data["isPublic"])

    def test_private_corpus_returns_none(self):
        """Test that private corpus returns None (not an error)."""
        query = """
            query GetOGCorpusMetadata($userSlug: String!, $corpusSlug: String!) {
                ogCorpusMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug) {
                    title
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.private_corpus.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ogCorpusMetadata"])

    def test_nonexistent_corpus_returns_none(self):
        """Test that non-existent corpus returns None (not an error)."""
        query = """
            query GetOGCorpusMetadata($userSlug: String!, $corpusSlug: String!) {
                ogCorpusMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug) {
                    title
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": "nonexistent-corpus",
            },
        )

        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ogCorpusMetadata"])

    def test_nonexistent_user_returns_none(self):
        """Test that non-existent user returns None (not an error)."""
        query = """
            query GetOGCorpusMetadata($userSlug: String!, $corpusSlug: String!) {
                ogCorpusMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug) {
                    title
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": "nonexistent-user",
                "corpusSlug": self.public_corpus.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ogCorpusMetadata"])


class OGDocumentMetadataTestCase(TestCase):
    """Tests for ogDocumentMetadata GraphQL query (standalone documents)."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for document OG metadata tests."""
        cls.user = User.objects.create_user(
            username="og_doc_user",
            password="testpass123",
            email="og_doc@test.com",
        )

        # Public document
        cls.public_doc = Document.objects.create(
            title="Public Test Document",
            description="A public document for OG metadata testing",
            creator=cls.user,
            is_public=True,
        )

        # Private document
        cls.private_doc = Document.objects.create(
            title="Private Test Document",
            description="A private document that should not be returned",
            creator=cls.user,
            is_public=False,
        )

    def setUp(self):
        """Set up test client with request context."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = None
        self.client = Client(schema, context_value=self.request)

    def test_public_document_returns_metadata(self):
        """Test that public document returns OG metadata."""
        query = """
            query GetOGDocumentMetadata($userSlug: String!, $documentSlug: String!) {
                ogDocumentMetadata(userSlug: $userSlug, documentSlug: $documentSlug) {
                    title
                    description
                    creatorName
                    isPublic
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "documentSlug": self.public_doc.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogDocumentMetadata"]
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Public Test Document")
        self.assertEqual(
            data["description"], "A public document for OG metadata testing"
        )
        # ``creatorName`` is the public slug (see OG_metadata privacy fix).
        self.assertEqual(data["creatorName"], self.user.slug)
        self.assertTrue(data["isPublic"])

    def test_private_document_returns_none(self):
        """Test that private document returns None."""
        query = """
            query GetOGDocumentMetadata($userSlug: String!, $documentSlug: String!) {
                ogDocumentMetadata(userSlug: $userSlug, documentSlug: $documentSlug) {
                    title
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "documentSlug": self.private_doc.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ogDocumentMetadata"])


class OGDocumentInCorpusMetadataTestCase(TestCase):
    """Tests for ogDocumentInCorpusMetadata GraphQL query."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for document in corpus OG metadata tests."""
        cls.user = User.objects.create_user(
            username="og_doc_corpus_user",
            password="testpass123",
            email="og_doc_corpus@test.com",
        )

        # Public corpus with public document
        cls.public_corpus = Corpus.objects.create(
            title="Public Corpus",
            description="Corpus for analyzing legal contracts",
            creator=cls.user,
            is_public=True,
        )
        original_public_doc = Document.objects.create(
            title="Public Doc in Corpus",
            description="Document in public corpus",
            creator=cls.user,
            is_public=True,
        )
        # add_document creates a corpus-isolated copy - capture it
        cls.public_doc, _, _ = cls.public_corpus.add_document(
            document=original_public_doc, user=cls.user
        )

        # Public corpus with private document
        original_private_doc = Document.objects.create(
            title="Private Doc in Corpus",
            description="Private document in public corpus",
            creator=cls.user,
            is_public=False,
        )
        cls.private_doc, _, _ = cls.public_corpus.add_document(
            document=original_private_doc, user=cls.user
        )

        # Private corpus
        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=cls.user,
            is_public=False,
        )

    def setUp(self):
        """Set up test client with request context."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = None
        self.client = Client(schema, context_value=self.request)

    def test_public_doc_in_public_corpus_returns_metadata(self):
        """Test that public doc in public corpus returns metadata
        including corpus description for social tag context."""
        query = """
            query GetOGDocInCorpus(
                $userSlug: String!,
                $corpusSlug: String!,
                $documentSlug: String!
            ) {
                ogDocumentInCorpusMetadata(
                    userSlug: $userSlug,
                    corpusSlug: $corpusSlug,
                    documentSlug: $documentSlug
                ) {
                    title
                    description
                    corpusTitle
                    corpusDescription
                    creatorName
                    isPublic
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.public_corpus.slug,
                "documentSlug": self.public_doc.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogDocumentInCorpusMetadata"]
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Public Doc in Corpus")
        self.assertEqual(data["corpusTitle"], "Public Corpus")
        self.assertEqual(
            data["corpusDescription"], "Corpus for analyzing legal contracts"
        )
        # ``creatorName`` is the public slug (see OG_metadata privacy fix).
        self.assertEqual(data["creatorName"], self.user.slug)

    def test_doc_added_as_private_to_public_corpus_inherits_public(self):
        """Test that a document added to a public corpus inherits is_public=True
        and returns OG metadata. Under the relaxed permission model, documents
        in public corpuses are always public."""
        query = """
            query GetOGDocInCorpus(
                $userSlug: String!,
                $corpusSlug: String!,
                $documentSlug: String!
            ) {
                ogDocumentInCorpusMetadata(
                    userSlug: $userSlug,
                    corpusSlug: $corpusSlug,
                    documentSlug: $documentSlug
                ) {
                    title
                    description
                    creatorName
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.public_corpus.slug,
                "documentSlug": self.private_doc.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogDocumentInCorpusMetadata"]
        self.assertIsNotNone(
            data,
            "Document in public corpus should be public and return OG metadata",
        )
        self.assertEqual(data["title"], "Private Doc in Corpus")
        # ``creatorName`` is the public slug (see OG_metadata privacy fix).
        self.assertEqual(data["creatorName"], self.user.slug)

    def test_doc_in_private_corpus_returns_none(self):
        """Test that any doc in private corpus returns None."""
        query = """
            query GetOGDocInCorpus(
                $userSlug: String!,
                $corpusSlug: String!,
                $documentSlug: String!
            ) {
                ogDocumentInCorpusMetadata(
                    userSlug: $userSlug,
                    corpusSlug: $corpusSlug,
                    documentSlug: $documentSlug
                ) {
                    title
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.private_corpus.slug,
                "documentSlug": "any-doc",
            },
        )

        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ogDocumentInCorpusMetadata"])


class OGThreadMetadataTestCase(TestCase):
    """Tests for ogThreadMetadata GraphQL query."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for thread OG metadata tests."""
        cls.user = User.objects.create_user(
            username="og_thread_user",
            password="testpass123",
            email="og_thread@test.com",
        )

        # Public corpus with thread
        cls.public_corpus = Corpus.objects.create(
            title="Public Corpus with Thread",
            creator=cls.user,
            is_public=True,
        )

        cls.thread = Conversation.objects.create(
            title="Test Discussion Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=cls.user,
            chat_with_corpus=cls.public_corpus,
        )

        # Add some messages
        for i in range(5):
            ChatMessage.objects.create(
                conversation=cls.thread,
                msg_type="HUMAN",
                content=f"Test message {i}",
                creator=cls.user,
            )

        # Private corpus
        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=cls.user,
            is_public=False,
        )

        cls.private_thread = Conversation.objects.create(
            title="Private Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=cls.user,
            chat_with_corpus=cls.private_corpus,
        )

    def setUp(self):
        """Set up test client with request context."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = None
        self.client = Client(schema, context_value=self.request)

    def test_thread_in_public_corpus_returns_metadata(self):
        """Test that thread in public corpus returns metadata."""
        query = """
            query GetOGThreadMetadata(
                $userSlug: String!,
                $corpusSlug: String!,
                $threadId: String!
            ) {
                ogThreadMetadata(
                    userSlug: $userSlug,
                    corpusSlug: $corpusSlug,
                    threadId: $threadId
                ) {
                    title
                    corpusTitle
                    messageCount
                    creatorName
                    isPublic
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.public_corpus.slug,
                "threadId": str(self.thread.pk),
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogThreadMetadata"]
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Test Discussion Thread")
        self.assertEqual(data["corpusTitle"], "Public Corpus with Thread")
        self.assertEqual(data["messageCount"], 5)
        # ``creatorName`` is the public slug (see OG_metadata privacy fix).
        self.assertEqual(data["creatorName"], self.user.slug)

    def test_thread_in_public_corpus_with_relay_id(self):
        """Test that thread query works with GraphQL Relay global ID."""
        query = """
            query GetOGThreadMetadata(
                $userSlug: String!,
                $corpusSlug: String!,
                $threadId: String!
            ) {
                ogThreadMetadata(
                    userSlug: $userSlug,
                    corpusSlug: $corpusSlug,
                    threadId: $threadId
                ) {
                    title
                    messageCount
                }
            }
        """
        global_id = to_global_id("ConversationType", self.thread.pk)
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.public_corpus.slug,
                "threadId": global_id,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogThreadMetadata"]
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Test Discussion Thread")
        self.assertEqual(data["messageCount"], 5)

    def test_thread_in_private_corpus_returns_none(self):
        """Test that thread in private corpus returns None."""
        query = """
            query GetOGThreadMetadata(
                $userSlug: String!,
                $corpusSlug: String!,
                $threadId: String!
            ) {
                ogThreadMetadata(
                    userSlug: $userSlug,
                    corpusSlug: $corpusSlug,
                    threadId: $threadId
                ) {
                    title
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.private_corpus.slug,
                "threadId": str(self.private_thread.pk),
            },
        )

        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ogThreadMetadata"])


class OGExtractMetadataTestCase(TestCase):
    """Tests for ogExtractMetadata GraphQL query."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for extract OG metadata tests."""
        cls.user = User.objects.create_user(
            username="og_extract_user",
            password="testpass123",
            email="og_extract@test.com",
        )

        # Public corpus with extract
        cls.public_corpus = Corpus.objects.create(
            title="Public Corpus with Extract",
            creator=cls.user,
            is_public=True,
        )

        cls.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="A fieldset for testing",
            creator=cls.user,
        )

        cls.extract = Extract.objects.create(
            name="Test Data Extract",
            corpus=cls.public_corpus,
            fieldset=cls.fieldset,
            creator=cls.user,
        )

        # Private corpus with extract
        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=cls.user,
            is_public=False,
        )

        cls.private_extract = Extract.objects.create(
            name="Private Extract",
            corpus=cls.private_corpus,
            fieldset=cls.fieldset,
            creator=cls.user,
        )

    def setUp(self):
        """Set up test client with request context."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = None
        self.client = Client(schema, context_value=self.request)

    def test_extract_in_public_corpus_returns_metadata(self):
        """Test that extract in public corpus returns metadata."""
        query = """
            query GetOGExtractMetadata($extractId: String!) {
                ogExtractMetadata(extractId: $extractId) {
                    name
                    corpusTitle
                    fieldsetName
                    creatorName
                    isPublic
                }
            }
        """
        result = self.client.execute(
            query,
            variables={"extractId": str(self.extract.pk)},
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogExtractMetadata"]
        self.assertIsNotNone(data)
        self.assertEqual(data["name"], "Test Data Extract")
        self.assertEqual(data["corpusTitle"], "Public Corpus with Extract")
        self.assertEqual(data["fieldsetName"], "Test Fieldset")
        # ``creatorName`` is the public slug (see OG_metadata privacy fix).
        self.assertEqual(data["creatorName"], self.user.slug)

    def test_extract_in_public_corpus_with_relay_id(self):
        """Test that extract query works with GraphQL Relay global ID."""
        query = """
            query GetOGExtractMetadata($extractId: String!) {
                ogExtractMetadata(extractId: $extractId) {
                    name
                    corpusTitle
                }
            }
        """
        global_id = to_global_id("ExtractType", self.extract.pk)
        result = self.client.execute(
            query,
            variables={"extractId": global_id},
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogExtractMetadata"]
        self.assertIsNotNone(data)
        self.assertEqual(data["name"], "Test Data Extract")

    def test_extract_in_private_corpus_returns_none(self):
        """Test that extract in private corpus returns None."""
        query = """
            query GetOGExtractMetadata($extractId: String!) {
                ogExtractMetadata(extractId: $extractId) {
                    name
                }
            }
        """
        result = self.client.execute(
            query,
            variables={"extractId": str(self.private_extract.pk)},
        )

        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ogExtractMetadata"])

    def test_nonexistent_extract_returns_none(self):
        """Test that non-existent extract returns None."""
        query = """
            query GetOGExtractMetadata($extractId: String!) {
                ogExtractMetadata(extractId: $extractId) {
                    name
                }
            }
        """
        result = self.client.execute(
            query,
            variables={"extractId": "99999"},
        )

        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ogExtractMetadata"])


class OGMetadataEmptyDescriptionTestCase(TestCase):
    """Test that OG metadata handles empty descriptions correctly."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="og_empty_desc_user",
            password="testpass123",
        )

        # Corpus with empty description
        cls.corpus_empty_desc = Corpus.objects.create(
            title="Corpus Empty Description",
            description="",
            creator=cls.user,
            is_public=True,
        )

        # Document with empty description
        cls.doc_empty_desc = Document.objects.create(
            title="Doc Empty Description",
            description="",
            creator=cls.user,
            is_public=True,
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = None
        self.client = Client(schema, context_value=self.request)

    def test_corpus_with_empty_description(self):
        """Test corpus with empty description returns empty string."""
        query = """
            query GetOGCorpusMetadata($userSlug: String!, $corpusSlug: String!) {
                ogCorpusMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug) {
                    title
                    description
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.corpus_empty_desc.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogCorpusMetadata"]
        self.assertEqual(data["description"], "")

    def test_document_with_empty_description(self):
        """Test document with empty description returns empty string."""
        query = """
            query GetOGDocumentMetadata($userSlug: String!, $documentSlug: String!) {
                ogDocumentMetadata(userSlug: $userSlug, documentSlug: $documentSlug) {
                    title
                    description
                }
            }
        """
        result = self.client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "documentSlug": self.doc_empty_desc.slug,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["ogDocumentMetadata"]
        self.assertEqual(data["description"], "")
