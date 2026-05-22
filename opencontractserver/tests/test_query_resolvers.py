"""
Tests for GraphQL query resolvers added in Issue #580 (thread search UI).

This test suite covers:
- Corpus folder query resolvers
- Deleted documents query resolver
- Mention search resolvers
- User messages resolver
"""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
)
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.utils.permissioning import (
    PermissionTypes,
    set_permissions_for_obj_to_user,
)

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class CorpusFolderQueryResolverTest(TestCase):
    """Test corpus folder query resolvers."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="folder_test_user", password="testpassword"
        )
        self.other_user = User.objects.create_user(
            username="other_folder_user", password="testpassword"
        )

        # Create corpus
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=self.corpus,
            permissions=[PermissionTypes.ALL],
        )

        # Create folder hierarchy
        self.root_folder = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="Root Folder",
            description="Root folder description",
            creator=self.user,
        )

        self.child_folder = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="Child Folder",
            parent=self.root_folder,
            creator=self.user,
        )

        self.client = Client(schema, context_value=TestContext(self.user))

    def test_resolve_corpus_folders(self):
        """Test resolve_corpus_folders returns all folders in a corpus."""
        query = """
            query GetCorpusFolders($corpusId: ID!) {
                corpusFolders(corpusId: $corpusId) {
                    id
                    name
                    description
                }
            }
        """

        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        result = self.client.execute(
            query,
            variables={"corpusId": corpus_global_id},
        )

        self.assertIsNone(result.get("errors"))
        folders = result["data"]["corpusFolders"]

        # Should return both folders
        self.assertEqual(len(folders), 2)

        folder_names = {folder["name"] for folder in folders}
        self.assertIn("Root Folder", folder_names)
        self.assertIn("Child Folder", folder_names)

    def test_resolve_corpus_folders_permission_filtering(self):
        """Test that corpus_folders only returns folders user can access."""
        # Create another corpus the user can't access
        other_corpus = Corpus.objects.create(
            title="Other Corpus", creator=self.other_user
        )
        set_permissions_for_obj_to_user(
            user_val=self.other_user,
            instance=other_corpus,
            permissions=[PermissionTypes.ALL],
        )

        # Create folder in other corpus
        CorpusFolder.objects.create(
            corpus=other_corpus,
            name="Inaccessible Folder",
            creator=self.other_user,
        )

        query = """
            query GetCorpusFolders($corpusId: ID!) {
                corpusFolders(corpusId: $corpusId) {
                    id
                    name
                }
            }
        """

        other_corpus_global_id = to_global_id("CorpusType", other_corpus.id)

        result = self.client.execute(
            query,
            variables={"corpusId": other_corpus_global_id},
        )

        # Should return empty list (no permission)
        self.assertIsNone(result.get("errors"))
        folders = result["data"]["corpusFolders"]
        self.assertEqual(len(folders), 0)

    def test_resolve_corpus_folder_by_id(self):
        """Test resolve_corpus_folder returns single folder by ID."""
        query = """
            query GetCorpusFolder($id: ID!) {
                corpusFolder(id: $id) {
                    id
                    name
                    description
                }
            }
        """

        folder_global_id = to_global_id("CorpusFolderType", self.root_folder.id)

        result = self.client.execute(
            query,
            variables={"id": folder_global_id},
        )

        self.assertIsNone(result.get("errors"))
        folder = result["data"]["corpusFolder"]

        self.assertIsNotNone(folder)
        self.assertEqual(folder["name"], "Root Folder")
        self.assertEqual(folder["description"], "Root folder description")

    def test_resolve_corpus_folder_not_found(self):
        """Test resolve_corpus_folder returns None for non-existent folder."""
        query = """
            query GetCorpusFolder($id: ID!) {
                corpusFolder(id: $id) {
                    id
                    name
                }
            }
        """

        # Use non-existent ID
        fake_global_id = to_global_id("CorpusFolderType", 99999)

        result = self.client.execute(
            query,
            variables={"id": fake_global_id},
        )

        self.assertIsNone(result.get("errors"))
        folder = result["data"]["corpusFolder"]
        self.assertIsNone(folder)


class DeletedDocumentsQueryResolverTest(TestCase):
    """Test deleted_documents_in_corpus query resolver."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="deleted_docs_user", password="testpassword"
        )

        # Create corpus
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=self.corpus,
            permissions=[PermissionTypes.ALL],
        )

        # Create documents
        pdf_file1 = ContentFile(b"%PDF-1.4 test pdf 1", name="doc1.pdf")
        self.doc1 = Document.objects.create(
            creator=self.user,
            title="Active Document",
            pdf_file=pdf_file1,
            backend_lock=True,
        )

        pdf_file2 = ContentFile(b"%PDF-1.4 test pdf 2", name="doc2.pdf")
        self.doc2 = Document.objects.create(
            creator=self.user,
            title="Deleted Document",
            pdf_file=pdf_file2,
            backend_lock=True,
        )

        # Add documents to corpus via DocumentPath
        self.path1 = DocumentPath.objects.create(
            corpus=self.corpus,
            document=self.doc1,
            path="/doc1.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=self.user,
        )

        self.path2 = DocumentPath.objects.create(
            corpus=self.corpus,
            document=self.doc2,
            path="/doc2.pdf",
            is_current=True,
            is_deleted=True,  # Soft deleted
            version_number=1,
            creator=self.user,
        )

        self.client = Client(schema, context_value=TestContext(self.user))

    def test_resolve_deleted_documents_in_corpus(self):
        """Test resolve_deleted_documents_in_corpus returns only soft-deleted docs."""
        query = """
            query GetDeletedDocuments($corpusId: ID!) {
                deletedDocumentsInCorpus(corpusId: $corpusId) {
                    id
                    document {
                        id
                        title
                    }
                    isDeleted
                    isCurrent
                }
            }
        """

        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        result = self.client.execute(
            query,
            variables={"corpusId": corpus_global_id},
        )

        self.assertIsNone(result.get("errors"))
        deleted_paths = result["data"]["deletedDocumentsInCorpus"]

        # Should return only the deleted document
        self.assertEqual(len(deleted_paths), 1)
        self.assertEqual(deleted_paths[0]["document"]["title"], "Deleted Document")
        self.assertTrue(deleted_paths[0]["isDeleted"])
        self.assertTrue(deleted_paths[0]["isCurrent"])

    def test_resolve_deleted_documents_no_permission(self):
        """Test deleted_documents_in_corpus returns empty for no corpus permission."""
        # Create corpus without permission
        other_corpus = Corpus.objects.create(title="Other Corpus", creator=self.user)

        query = """
            query GetDeletedDocuments($corpusId: ID!) {
                deletedDocumentsInCorpus(corpusId: $corpusId) {
                    id
                }
            }
        """

        # Remove all permissions from corpus
        other_corpus_global_id = to_global_id("CorpusType", other_corpus.id)

        # Create new client without corpus access
        other_user = User.objects.create_user(
            username="no_access_user", password="testpassword"
        )
        no_access_client = Client(schema, context_value=TestContext(other_user))

        result = no_access_client.execute(
            query,
            variables={"corpusId": other_corpus_global_id},
        )

        # Should return empty list
        self.assertIsNone(result.get("errors"))
        deleted_paths = result["data"]["deletedDocumentsInCorpus"]
        self.assertEqual(len(deleted_paths), 0)


class MentionSearchResolverTest(TestCase):
    """Test mention search query resolvers."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="mention_test_user",
            password="testpassword",
            email="mention@test.com",
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Machine Learning Corpus",
            description="A corpus about ML",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=self.corpus,
            permissions=[PermissionTypes.ALL],
        )

        # Create document
        pdf_file = ContentFile(b"%PDF-1.4 test pdf", name="mention_test.pdf")
        self.doc = Document.objects.create(
            creator=self.user,
            title="Neural Networks Paper",
            description="Paper about neural networks",
            pdf_file=pdf_file,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=self.doc,
            permissions=[PermissionTypes.ALL],
        )

        # Create annotation
        self.label = AnnotationLabel.objects.create(
            text="Important Finding",
            creator=self.user,
        )
        self.annotation = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="This is an important finding about deep learning",
            creator=self.user,
        )

        self.client = Client(schema, context_value=TestContext(self.user))

    def test_search_corpuses_for_mention(self):
        """Test search_corpuses_for_mention with text search."""
        query = """
            query SearchCorpusesForMention($textSearch: String) {
                searchCorpusesForMention(textSearch: $textSearch) {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"textSearch": "Machine"},
        )

        self.assertIsNone(result.get("errors"))
        corpuses = result["data"]["searchCorpusesForMention"]["edges"]

        # Should find the ML corpus
        self.assertGreaterEqual(len(corpuses), 1)
        corpus_titles = {corpus["node"]["title"] for corpus in corpuses}
        self.assertIn("Machine Learning Corpus", corpus_titles)

    def test_search_documents_for_mention(self):
        """Test search_documents_for_mention with text search."""
        query = """
            query SearchDocumentsForMention($textSearch: String) {
                searchDocumentsForMention(textSearch: $textSearch) {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"textSearch": "Neural"},
        )

        self.assertIsNone(result.get("errors"))
        documents = result["data"]["searchDocumentsForMention"]["edges"]

        # Should find the neural networks paper
        self.assertGreaterEqual(len(documents), 1)
        doc_titles = {doc["node"]["title"] for doc in documents}
        self.assertIn("Neural Networks Paper", doc_titles)

    def test_search_annotations_for_mention(self):
        """Test search_annotations_for_mention with text search."""
        query = """
            query SearchAnnotationsForMention($textSearch: String) {
                searchAnnotationsForMention(textSearch: $textSearch) {
                    edges {
                        node {
                            id
                            rawText
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"textSearch": "deep learning"},
        )

        self.assertIsNone(result.get("errors"))
        annotations = result["data"]["searchAnnotationsForMention"]["edges"]

        # Should find the annotation
        self.assertGreaterEqual(len(annotations), 1)
        raw_texts = {ann["node"]["rawText"] for ann in annotations}
        self.assertIn("This is an important finding about deep learning", raw_texts)

    def test_search_annotations_for_mention_by_label(self):
        """Test search_annotations_for_mention by label text."""
        query = """
            query SearchAnnotationsForMention($textSearch: String) {
                searchAnnotationsForMention(textSearch: $textSearch) {
                    edges {
                        node {
                            id
                            rawText
                            annotationLabel {
                                text
                            }
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={
                "textSearch": "Important",  # Search by label text
            },
        )

        self.assertIsNone(result.get("errors"))
        annotations = result["data"]["searchAnnotationsForMention"]["edges"]

        # Should find the annotation with "Important Finding" label
        self.assertGreaterEqual(len(annotations), 1)
        labels = {ann["node"]["annotationLabel"]["text"] for ann in annotations}
        self.assertIn("Important Finding", labels)

    def test_search_annotations_matches_partial_words(self):
        """Search must match mid-word fragments, not just whole stemmed words.

        Full-text search alone misses "bitrat" inside "Arbitration" — FTS only
        matches whole, stemmed lexemes. The raw_text icontains clause
        (pg_trgm-backed) catches the substring. annotation_label is left null
        so only the raw_text matcher can satisfy the query.
        """
        Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=None,
            raw_text="Arbitration shall resolve all disputes",
            creator=self.user,
        )
        query = """
            query SearchAnnotationsForMention($textSearch: String) {
                searchAnnotationsForMention(textSearch: $textSearch) {
                    edges {
                        node {
                            id
                            rawText
                        }
                    }
                }
            }
        """
        result = self.client.execute(query, variables={"textSearch": "bitrat"})

        self.assertIsNone(result.get("errors"))
        raw_texts = {
            edge["node"]["rawText"]
            for edge in result["data"]["searchAnnotationsForMention"]["edges"]
        }
        self.assertIn("Arbitration shall resolve all disputes", raw_texts)

    def test_search_users_for_mention(self):
        """Test search_users_for_mention with text search."""
        query = """
            query SearchUsersForMention($textSearch: String) {
                searchUsersForMention(textSearch: $textSearch) {
                    edges {
                        node {
                            id
                            username
                            email
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"textSearch": "mention"},
        )

        self.assertIsNone(result.get("errors"))
        users = result["data"]["searchUsersForMention"]["edges"]

        # Should find the user
        self.assertGreaterEqual(len(users), 1)
        usernames = {user["node"]["username"] for user in users}
        self.assertIn("mention_test_user", usernames)

    def test_search_documents_for_mention_with_corpus_filter(self):
        """
        Test search_documents_for_mention with corpus_id filter.

        Issue #741: Ensures document search is scoped to specific corpus
        to prevent cross-corpus document references in AI agent contexts.
        """
        # Create a second corpus with a different document
        corpus2 = Corpus.objects.create(
            title="Other Corpus",
            description="A different corpus",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=corpus2,
            permissions=[PermissionTypes.ALL],
        )

        # Create a second document
        pdf_file2 = ContentFile(b"%PDF-1.4 test pdf 2", name="other_doc.pdf")
        doc2 = Document.objects.create(
            creator=self.user,
            title="Other Neural Paper",
            description="Another paper about neural networks",
            pdf_file=pdf_file2,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=doc2,
            permissions=[PermissionTypes.ALL],
        )

        # Add documents to corpuses via DocumentPath
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            path="/mention_test.pdf",
            version_number=1,
            is_current=True,
        )
        DocumentPath.objects.create(
            document=doc2,
            corpus=corpus2,
            creator=self.user,
            path="/other_doc.pdf",
            version_number=1,
            is_current=True,
        )

        query = """
            query SearchDocumentsForMention($textSearch: String, $corpusId: ID) {
                searchDocumentsForMention(textSearch: $textSearch, corpusId: $corpusId) {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
        """

        # Test without corpus filter - should find both documents
        result = self.client.execute(
            query,
            variables={"textSearch": "Neural"},
        )

        self.assertIsNone(result.get("errors"))
        documents = result["data"]["searchDocumentsForMention"]["edges"]
        doc_titles = {doc["node"]["title"] for doc in documents}
        self.assertIn("Neural Networks Paper", doc_titles)
        self.assertIn("Other Neural Paper", doc_titles)

        # Test with corpus filter - should only find document in that corpus
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)
        result = self.client.execute(
            query,
            variables={"textSearch": "Neural", "corpusId": corpus_global_id},
        )

        self.assertIsNone(result.get("errors"))
        documents = result["data"]["searchDocumentsForMention"]["edges"]
        doc_titles = {doc["node"]["title"] for doc in documents}

        # Should find the document in corpus1
        self.assertIn("Neural Networks Paper", doc_titles)
        # Should NOT find the document in corpus2
        self.assertNotIn("Other Neural Paper", doc_titles)

        # Test with corpus2 filter
        corpus2_global_id = to_global_id("CorpusType", corpus2.id)
        result = self.client.execute(
            query,
            variables={"textSearch": "Neural", "corpusId": corpus2_global_id},
        )

        self.assertIsNone(result.get("errors"))
        documents = result["data"]["searchDocumentsForMention"]["edges"]
        doc_titles = {doc["node"]["title"] for doc in documents}

        # Should NOT find the document in corpus1
        self.assertNotIn("Neural Networks Paper", doc_titles)
        # Should find the document in corpus2
        self.assertIn("Other Neural Paper", doc_titles)


class UserMessagesQueryResolverTest(TestCase):
    """Test user_messages query resolver."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="message_test_user", password="testpassword"
        )
        self.other_user = User.objects.create_user(
            username="other_message_user", password="testpassword"
        )

        # Create corpus
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Create conversation
        self.conversation = Conversation.objects.create(
            title="Test Conversation",
            chat_with_corpus=self.corpus,
            creator=self.user,
            conversation_type="thread",
        )

        # Create messages
        self.message1 = ChatMessage.objects.create(
            conversation=self.conversation,
            creator=self.user,
            content="First message",
            msg_type="HUMAN",
        )

        self.message2 = ChatMessage.objects.create(
            conversation=self.conversation,
            creator=self.user,
            content="Second message",
            msg_type="HUMAN",
        )

        self.message3 = ChatMessage.objects.create(
            conversation=self.conversation,
            creator=self.other_user,
            content="Other user message",
            msg_type="HUMAN",
        )

        self.client = Client(schema, context_value=TestContext(self.user))

    def test_resolve_user_messages(self):
        """Test resolve_user_messages returns messages by creator."""
        query = """
            query GetUserMessages($creatorId: ID!) {
                userMessages(creatorId: $creatorId) {
                    id
                    content
                }
            }
        """

        user_global_id = to_global_id("UserType", self.user.id)

        result = self.client.execute(
            query,
            variables={"creatorId": user_global_id},
        )

        self.assertIsNone(result.get("errors"))
        messages = result["data"]["userMessages"]

        # Should return only user's messages (first=10 default)
        self.assertEqual(len(messages), 2)
        message_contents = {msg["content"] for msg in messages}
        self.assertIn("First message", message_contents)
        self.assertIn("Second message", message_contents)
        self.assertNotIn("Other user message", message_contents)

    def test_resolve_user_messages_with_first_limit(self):
        """Test resolve_user_messages with first parameter."""
        query = """
            query GetUserMessages($creatorId: ID!, $first: Int) {
                userMessages(creatorId: $creatorId, first: $first) {
                    id
                    content
                }
            }
        """

        user_global_id = to_global_id("UserType", self.user.id)

        result = self.client.execute(
            query,
            variables={
                "creatorId": user_global_id,
                "first": 1,
            },
        )

        self.assertIsNone(result.get("errors"))
        messages = result["data"]["userMessages"]

        # Should return only 1 message
        self.assertEqual(len(messages), 1)

    def test_resolve_user_messages_with_msg_type_filter(self):
        """Test resolve_user_messages with msg_type filter."""
        # Create an LLM message
        ChatMessage.objects.create(
            conversation=self.conversation,
            creator=self.user,
            content="LLM response",
            msg_type="LLM",
        )

        query = """
            query GetUserMessages($creatorId: ID!, $msgType: String) {
                userMessages(creatorId: $creatorId, msgType: $msgType) {
                    id
                    content
                    msgType
                }
            }
        """

        user_global_id = to_global_id("UserType", self.user.id)

        result = self.client.execute(
            query,
            variables={
                "creatorId": user_global_id,
                "msgType": "LLM",
            },
        )

        self.assertIsNone(result.get("errors"))
        messages = result["data"]["userMessages"]

        # Should return only LLM messages
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "LLM response")
        self.assertEqual(messages[0]["msgType"], "LLM")

    def test_resolve_user_messages_with_order_by(self):
        """Test resolve_user_messages with order_by parameter."""
        query = """
            query GetUserMessages($creatorId: ID!, $orderBy: String) {
                userMessages(creatorId: $creatorId, orderBy: $orderBy) {
                    id
                    content
                }
            }
        """

        user_global_id = to_global_id("UserType", self.user.id)

        result = self.client.execute(
            query,
            variables={
                "creatorId": user_global_id,
                "orderBy": "created",
            },
        )

        self.assertIsNone(result.get("errors"))
        messages = result["data"]["userMessages"]

        # Should return messages ordered by created (ascending)
        self.assertEqual(len(messages), 2)
        # First message should be the oldest
        self.assertEqual(messages[0]["content"], "First message")


class LabelsetFilterCaseSensitivityTest(TestCase):
    """LabelsetFilter must match Title-Cased labelsets from a lowercase query.

    Mirrors the corpus / conversation fixes from PR #1755 — both the
    custom ``textSearch`` filter and the Meta-generated ``title_Contains``
    GraphQL argument must use ILIKE so the Discover labelset search box
    is not case-sensitive.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="lsuser", password="secret")
        self.client = Client(schema, context_value=TestContext(self.user))
        self.labelset = LabelSet.objects.create(
            title="Merger Agreement Labels",
            description="Labels for M&A diligence",
            creator=self.user,
        )

    def _ids(self, response):
        return {
            edge["node"]["title"] for edge in response["data"]["labelsets"]["edges"]
        }

    def test_text_search_is_case_insensitive(self):
        query = """
            query Labelsets($textSearch: String) {
                labelsets(textSearch: $textSearch) {
                    edges { node { title } }
                }
            }
        """
        result = self.client.execute(query, variables={"textSearch": "merger"})
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), {"Merger Agreement Labels"})

    def test_title_contains_is_case_insensitive(self):
        # The Meta-generated ``title_Contains`` GraphQL argument must also use
        # ILIKE so callers passing it directly (instead of textSearch) get
        # case-insensitive matching.
        query = """
            query Labelsets($titleContains: String) {
                labelsets(title_Contains: $titleContains) {
                    edges { node { title } }
                }
            }
        """
        result = self.client.execute(query, variables={"titleContains": "merger"})
        self.assertIsNone(result.get("errors"))
        self.assertEqual(self._ids(result), {"Merger Agreement Labels"})
