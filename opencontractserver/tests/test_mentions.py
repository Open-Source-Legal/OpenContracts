"""
Tests for @ mention functionality in chat messages.

Verifies:
1. Mention parsing with regex patterns
2. Permission enforcement (mentions to inaccessible resources ignored)
3. Three mention formats: @corpus:slug, @document:slug, @corpus:slug/document:slug
4. Search query permission filtering
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client as GrapheneClient
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class MentionParsingTestCase(TestCase):
    """Test @ mention parsing in chat messages."""

    @mock.patch("opencontractserver.documents.signals.calculate_embedding_for_doc_text")
    def setUp(self, mock_embedding_task):
        """Create test users, corpuses, and documents."""
        # Create users
        self.user1 = User.objects.create_user(
            username="user1", password="test", slug="user1"
        )
        self.user2 = User.objects.create_user(
            username="user2", password="test", slug="user2"
        )

        # Create corpuses
        self.corpus1 = Corpus.objects.create(
            title="Legal Corpus",
            description="Legal documents",
            creator=self.user1,
            slug="legal-corpus",
        )
        self.corpus2 = Corpus.objects.create(
            title="Private Corpus",
            description="Private documents",
            creator=self.user2,
            slug="private-corpus",
        )

        # Create documents
        self.doc1 = Document.objects.create(
            title="Contract Template",
            description="Standard contract",
            creator=self.user1,
            slug="contract-template",
            backend_lock=True,  # Skip signal handlers
        )
        self.corpus1.documents.add(self.doc1)

        self.doc2 = Document.objects.create(
            title="Private Doc",
            description="Private document",
            creator=self.user2,
            slug="private-doc",
            backend_lock=True,  # Skip signal handlers
        )
        self.corpus2.documents.add(self.doc2)

        # Create conversation and message
        self.conversation = Conversation.objects.create(
            title="Test Thread", creator=self.user1, conversation_type="THREAD"
        )

        # Set permissions
        set_permissions_for_obj_to_user(
            self.user1, self.corpus1, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )
        set_permissions_for_obj_to_user(
            self.user1, self.doc1, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )
        set_permissions_for_obj_to_user(
            self.user2, self.corpus2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )
        set_permissions_for_obj_to_user(
            self.user2, self.doc2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Create GraphQL client
        self.client = GrapheneClient(schema)

    def test_corpus_mention_parsing(self):
        """Test parsing @corpus:slug mentions."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="Check out @corpus:legal-corpus for examples",
        )

        query = """
            query GetMessage($id: ID!) {
                chatMessage(id: $id) {
                    id
                    content
                    mentionedResources {
                        type
                        slug
                        title
                        url
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        mentioned = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentioned), 1)
        self.assertEqual(mentioned[0]["type"], "corpus")
        self.assertEqual(mentioned[0]["slug"], "legal-corpus")
        self.assertEqual(mentioned[0]["title"], "Legal Corpus")
        self.assertIn("/c/user1/legal-corpus", mentioned[0]["url"])

    def test_document_mention_parsing(self):
        """Test parsing @document:slug mentions."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="Review @document:contract-template before signing",
        )

        query = """
            query GetMessage($id: ID!) {
                chatMessage(id: $id) {
                    id
                    mentionedResources {
                        type
                        slug
                        title
                        url
                        corpus {
                            slug
                            title
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        mentioned = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentioned), 1)
        self.assertEqual(mentioned[0]["type"], "document")
        self.assertEqual(mentioned[0]["slug"], "contract-template")
        self.assertEqual(mentioned[0]["title"], "Contract Template")
        # Should include corpus context
        self.assertIsNotNone(mentioned[0]["corpus"])
        self.assertEqual(mentioned[0]["corpus"]["slug"], "legal-corpus")

    def test_corpus_document_mention_parsing(self):
        """Test parsing @corpus:slug/document:slug mentions."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="See @corpus:legal-corpus/document:contract-template",
        )

        query = """
            query GetMessage($id: ID!) {
                chatMessage(id: $id) {
                    id
                    mentionedResources {
                        type
                        slug
                        url
                        corpus {
                            slug
                            title
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        mentioned = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentioned), 1)
        self.assertEqual(mentioned[0]["type"], "document")
        self.assertEqual(mentioned[0]["slug"], "contract-template")
        self.assertIn("/d/user1/legal-corpus/contract-template", mentioned[0]["url"])
        self.assertEqual(mentioned[0]["corpus"]["slug"], "legal-corpus")

    def test_permission_enforcement_corpus(self):
        """Test that mentions to inaccessible corpuses are ignored."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="Check @corpus:legal-corpus and @corpus:private-corpus",
        )

        query = """
            query GetMessage($id: ID!) {
                chatMessage(id: $id) {
                    id
                    mentionedResources {
                        type
                        slug
                    }
                }
            }
        """

        # User1 should only see legal-corpus, not private-corpus
        result = self.client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        mentioned = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentioned), 1)
        self.assertEqual(mentioned[0]["slug"], "legal-corpus")

        # User2 should only see private-corpus
        result = self.client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": self.user2})(),
        )

        self.assertIsNone(result.get("errors"))
        mentioned = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentioned), 1)
        self.assertEqual(mentioned[0]["slug"], "private-corpus")

    def test_permission_enforcement_document(self):
        """Test that mentions to inaccessible documents are ignored."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="Check @document:contract-template and @document:private-doc",
        )

        query = """
            query GetMessage($id: ID!) {
                chatMessage(id: $id) {
                    id
                    mentionedResources {
                        type
                        slug
                    }
                }
            }
        """

        # User1 should only see contract-template
        result = self.client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        mentioned = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentioned), 1)
        self.assertEqual(mentioned[0]["slug"], "contract-template")

    def test_multiple_mentions(self):
        """Test parsing multiple mentions in one message."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content=(
                "Compare @corpus:legal-corpus with "
                "@corpus:legal-corpus/document:contract-template "
                "and review @document:contract-template"
            ),
        )

        query = """
            query GetMessage($id: ID!) {
                chatMessage(id: $id) {
                    id
                    mentionedResources {
                        type
                        slug
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        mentioned = result["data"]["chatMessage"]["mentionedResources"]
        # Should have: corpus, corpus/doc, doc (3 mentions)
        self.assertEqual(len(mentioned), 3)
        types = [m["type"] for m in mentioned]
        self.assertEqual(types.count("corpus"), 1)
        self.assertEqual(types.count("document"), 2)

    def test_no_mentions(self):
        """Test message with no mentions."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="Just a regular message with no mentions",
        )

        query = """
            query GetMessage($id: ID!) {
                chatMessage(id: $id) {
                    id
                    mentionedResources {
                        type
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        mentioned = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentioned), 0)


class MentionSearchTestCase(TestCase):
    """Test search queries for mention autocomplete."""

    @mock.patch("opencontractserver.documents.signals.calculate_embedding_for_doc_text")
    def setUp(self, mock_embedding_task):
        """Create test users, corpuses, and documents."""
        self.user1 = User.objects.create_user(
            username="user1", password="test", slug="user1"
        )
        self.user2 = User.objects.create_user(
            username="user2", password="test", slug="user2"
        )

        # Create corpuses
        self.corpus1 = Corpus.objects.create(
            title="Legal Contracts", creator=self.user1, slug="legal-contracts"
        )
        self.corpus2 = Corpus.objects.create(
            title="Private Files", creator=self.user2, slug="private-files"
        )

        # Create documents
        self.doc1 = Document.objects.create(
            title="Employment Contract",
            creator=self.user1,
            slug="employment-contract",
            backend_lock=True,  # Skip signal handlers
        )
        self.doc2 = Document.objects.create(
            title="Private Document",
            creator=self.user2,
            slug="private-document",
            backend_lock=True,  # Skip signal handlers
        )

        # Set permissions
        set_permissions_for_obj_to_user(
            self.user1, self.corpus1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(self.user1, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            self.user2, self.corpus2, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(self.user2, self.doc2, [PermissionTypes.READ])

        self.client = GrapheneClient(schema)

    def test_search_corpuses_for_mention(self):
        """Test searching corpuses for mention autocomplete."""
        query = """
            query SearchCorpuses($textSearch: String!) {
                searchCorpusesForMention(textSearch: $textSearch) {
                    edges {
                        node {
                            id
                            slug
                            title
                        }
                    }
                }
            }
        """

        # User1 searches for "legal"
        result = self.client.execute(
            query,
            variables={"textSearch": "legal"},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["searchCorpusesForMention"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["node"]["slug"], "legal-contracts")

        # User1 should NOT see user2's private corpus
        result = self.client.execute(
            query,
            variables={"textSearch": "private"},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["searchCorpusesForMention"]["edges"]
        self.assertEqual(len(edges), 0)

    def test_search_documents_for_mention(self):
        """Test searching documents for mention autocomplete."""
        query = """
            query SearchDocuments($textSearch: String!) {
                searchDocumentsForMention(textSearch: $textSearch) {
                    edges {
                        node {
                            id
                            slug
                            title
                            creator {
                                slug
                            }
                        }
                    }
                }
            }
        """

        # User1 searches for "contract"
        result = self.client.execute(
            query,
            variables={"textSearch": "contract"},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["searchDocumentsForMention"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["node"]["slug"], "employment-contract")

        # User1 should NOT see user2's private document
        result = self.client.execute(
            query,
            variables={"textSearch": "private"},
            context_value=type("Request", (), {"user": self.user1})(),
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["searchDocumentsForMention"]["edges"]
        self.assertEqual(len(edges), 0)

    def test_search_empty_query(self):
        """Test search with no query returns user's recent resources."""
        query = """
            query SearchCorpuses {
                searchCorpusesForMention {
                    edges {
                        node {
                            id
                            slug
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user1})()
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["searchCorpusesForMention"]["edges"]
        # Should return user's accessible corpuses (just corpus1)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["node"]["slug"], "legal-contracts")
