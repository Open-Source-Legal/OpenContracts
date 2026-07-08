"""
Tests for GraphQL conversation/thread mutations.

Tests the GraphQL mutations for creating and managing threads and messages:
- CreateThreadMutation
- CreateThreadMessageMutation
- ReplyToMessageMutation
- DeleteConversationMutation
- DeleteMessageMutation
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class ConversationMutationsTestCase(TestCase):
    """Test GraphQL mutations for conversations and threads."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="conversation_testuser",
            email="conversation_test@example.com",
            password="testpass123",
        )
        self.other_user = User.objects.create_user(
            username="conversation_otheruser",
            email="conversation_other@example.com",
            password="testpass123",
        )

        # Create a corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test corpus for threads",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        # Create a document for document-linked thread tests
        self.document = Document.objects.create(
            title="Test Document",
            description="Test document for threads",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.document, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        # Create GraphQL client
        self.graphene_client = Client(schema)

    def _execute_with_user(self, query, user, variables=None):
        """Execute a GraphQL query with a specific user context."""

        # Mock request object with user
        class MockRequest:
            def __init__(self, user):
                self.user = user
                self.META = {}

        context_value = MockRequest(user)
        return self.graphene_client.execute(
            query, variables=variables, context_value=context_value
        )

    def test_create_thread_mutation(self):
        """Test creating a new thread."""
        mutation = """
            mutation CreateThread($corpusId: String!, $title: String!, $initialMessage: String!) {
                createThread(corpusId: $corpusId, title: $title, initialMessage: $initialMessage) {
                    ok
                    message
                    obj {
                        id
                        title
                        conversationType
                    }
                }
            }
        """

        # Get corpus global ID
        from graphql_relay import to_global_id

        corpus_id = to_global_id("CorpusType", self.corpus.id)

        variables = {
            "corpusId": corpus_id,
            "title": "Test Thread",
            "initialMessage": "This is the first message",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Thread created successfully")
        self.assertIsNotNone(data["obj"])
        self.assertEqual(data["obj"]["title"], "Test Thread")
        self.assertEqual(data["obj"]["conversationType"], "THREAD")

        # Verify conversation was created in database
        conversation = Conversation.objects.get(title="Test Thread")
        self.assertEqual(conversation.conversation_type, "thread")
        self.assertEqual(conversation.creator, self.user)
        self.assertEqual(conversation.chat_with_corpus, self.corpus)

        # Verify initial message was created
        messages = ChatMessage.objects.filter(conversation=conversation)
        self.assertEqual(messages.count(), 1)
        first_message = messages.first()
        assert first_message is not None
        self.assertEqual(first_message.content, "This is the first message")

    def test_create_thread_without_permission(self):
        """Test creating a thread without corpus permission."""
        mutation = """
            mutation CreateThread($corpusId: String!, $title: String!, $initialMessage: String!) {
                createThread(corpusId: $corpusId, title: $title, initialMessage: $initialMessage) {
                    ok
                    message
                    obj {
                        id
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        corpus_id = to_global_id("CorpusType", self.corpus.id)

        variables = {
            "corpusId": corpus_id,
            "title": "Unauthorized Thread",
            "initialMessage": "Should fail",
        }

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertFalse(data["ok"])
        self.assertIn("permission", data["message"].lower())

    def test_create_thread_message_mutation(self):
        """Test posting a message to a thread."""
        # Create a thread first
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        mutation = """
            mutation CreateThreadMessage($conversationId: String!, $content: String!) {
                createThreadMessage(conversationId: $conversationId, content: $content) {
                    ok
                    message
                    obj {
                        id
                        content
                        msgType
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        conversation_id = to_global_id("ConversationType", conversation.id)

        variables = {
            "conversationId": conversation_id,
            "content": "This is a new message",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThreadMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Message posted successfully")
        self.assertEqual(data["obj"]["content"], "This is a new message")
        self.assertEqual(data["obj"]["msgType"], "HUMAN")

        # Verify message was created in database
        message = ChatMessage.objects.get(content="This is a new message")
        self.assertEqual(message.conversation, conversation)
        self.assertEqual(message.creator, self.user)

    def test_create_message_in_locked_thread(self):
        """Test posting a message to a locked thread (should fail)."""
        conversation = Conversation.objects.create(
            title="Locked Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
            is_locked=True,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        mutation = """
            mutation CreateThreadMessage($conversationId: String!, $content: String!) {
                createThreadMessage(conversationId: $conversationId, content: $content) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        conversation_id = to_global_id("ConversationType", conversation.id)

        variables = {
            "conversationId": conversation_id,
            "content": "Should fail",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThreadMessage"]
        self.assertFalse(data["ok"])
        # User with permission sees the locked status (IDOR protection still applies
        # for users without permission who get generic "cannot post" message)
        self.assertIn("locked", data["message"].lower())

    def test_reply_to_message_mutation(self):
        """Test creating a nested reply to a message."""
        # Create conversation and parent message
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        parent_message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Parent message",
            creator=self.user,
        )

        mutation = """
            mutation ReplyToMessage($parentMessageId: String!, $content: String!) {
                replyToMessage(parentMessageId: $parentMessageId, content: $content) {
                    ok
                    message
                    obj {
                        id
                        content
                        parentMessage {
                            id
                            content
                        }
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        parent_id = to_global_id("MessageType", parent_message.id)

        variables = {
            "parentMessageId": parent_id,
            "content": "This is a reply",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["replyToMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Reply posted successfully")
        self.assertEqual(data["obj"]["content"], "This is a reply")
        self.assertEqual(data["obj"]["parentMessage"]["content"], "Parent message")

        # Verify reply was created in database
        reply = ChatMessage.objects.get(content="This is a reply")
        self.assertEqual(reply.parent_message, parent_message)
        self.assertEqual(reply.conversation, conversation)

    def test_delete_conversation_mutation(self):
        """Test soft deleting a conversation."""
        conversation = Conversation.objects.create(
            title="Thread to Delete",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.DELETE]
        )

        mutation = """
            mutation DeleteConversation($conversationId: String!) {
                deleteConversation(conversationId: $conversationId) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        conversation_id = to_global_id("ConversationType", conversation.id)

        variables = {"conversationId": conversation_id}

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteConversation"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Conversation deleted successfully")

        # Verify conversation was soft deleted
        conversation.refresh_from_db()
        self.assertIsNotNone(conversation.deleted_at)

    def test_delete_message_mutation(self):
        """Test soft deleting a message."""
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Message to delete",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, message, [PermissionTypes.CRUD, PermissionTypes.DELETE]
        )

        mutation = """
            mutation DeleteMessage($messageId: ID!) {
                deleteMessage(messageId: $messageId) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        variables = {"messageId": message_id}

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Message deleted successfully")

        # Verify message was soft deleted
        message.refresh_from_db()
        self.assertIsNotNone(message.deleted_at)

    def test_nested_replies(self):
        """Test creating multiple levels of nested replies."""
        # Create conversation
        conversation = Conversation.objects.create(
            title="Nested Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        # Create parent message
        parent = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Level 0",
            creator=self.user,
        )

        # Create first level reply
        reply1 = ChatMessage.objects.create(
            conversation=conversation,
            parent_message=parent,
            msg_type="HUMAN",
            content="Level 1",
            creator=self.user,
        )

        # Create second level reply
        reply2 = ChatMessage.objects.create(
            conversation=conversation,
            parent_message=reply1,
            msg_type="HUMAN",
            content="Level 2",
            creator=self.user,
        )

        # Verify relationships
        self.assertEqual(reply1.parent_message, parent)
        self.assertEqual(reply2.parent_message, reply1)
        self.assertEqual(parent.replies.count(), 1)
        self.assertEqual(reply1.replies.count(), 1)
        self.assertEqual(reply2.replies.count(), 0)

    # =========================================================================
    # Issue #677: Document-linked thread tests
    # =========================================================================

    def test_create_thread_with_document_only(self):
        """Test creating a thread linked to a document only (no corpus)."""
        mutation = """
            mutation CreateThread($documentId: String, $title: String!, $initialMessage: String!) {
                createThread(documentId: $documentId, title: $title, initialMessage: $initialMessage) {
                    ok
                    message
                    obj {
                        id
                        title
                        conversationType
                        chatWithDocument {
                            id
                            title
                        }
                        chatWithCorpus {
                            id
                        }
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        document_id = to_global_id("DocumentType", self.document.id)

        variables = {
            "documentId": document_id,
            "title": "Document Thread",
            "initialMessage": "Discussion about this document",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Thread created successfully")
        self.assertIsNotNone(data["obj"])
        self.assertEqual(data["obj"]["title"], "Document Thread")
        self.assertEqual(data["obj"]["conversationType"], "THREAD")

        # Verify document is linked and corpus is not
        self.assertIsNotNone(data["obj"]["chatWithDocument"])
        self.assertEqual(data["obj"]["chatWithDocument"]["title"], "Test Document")
        self.assertIsNone(data["obj"]["chatWithCorpus"])

        # Verify in database
        conversation = Conversation.objects.get(title="Document Thread")
        self.assertEqual(conversation.chat_with_document, self.document)
        self.assertIsNone(conversation.chat_with_corpus)

    def test_create_thread_with_both_corpus_and_document(self):
        """Test creating a thread linked to BOTH corpus AND document (doc-in-corpus)."""
        mutation = """
            mutation CreateThread(
                $corpusId: String, $documentId: String, $title: String!, $initialMessage: String!
            ) {
                createThread(
                    corpusId: $corpusId
                    documentId: $documentId
                    title: $title
                    initialMessage: $initialMessage
                ) {
                    ok
                    message
                    obj {
                        id
                        title
                        conversationType
                        chatWithDocument {
                            id
                            title
                        }
                        chatWithCorpus {
                            id
                            title
                        }
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        corpus_id = to_global_id("CorpusType", self.corpus.id)
        document_id = to_global_id("DocumentType", self.document.id)

        variables = {
            "corpusId": corpus_id,
            "documentId": document_id,
            "title": "Doc-in-Corpus Thread",
            "initialMessage": "Discussion about this document within the corpus",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Thread created successfully")
        self.assertIsNotNone(data["obj"])
        self.assertEqual(data["obj"]["title"], "Doc-in-Corpus Thread")

        # Verify BOTH document AND corpus are linked
        self.assertIsNotNone(data["obj"]["chatWithDocument"])
        self.assertEqual(data["obj"]["chatWithDocument"]["title"], "Test Document")
        self.assertIsNotNone(data["obj"]["chatWithCorpus"])
        self.assertEqual(data["obj"]["chatWithCorpus"]["title"], "Test Corpus")

        # Verify in database
        conversation = Conversation.objects.get(title="Doc-in-Corpus Thread")
        self.assertEqual(conversation.chat_with_document, self.document)
        self.assertEqual(conversation.chat_with_corpus, self.corpus)
        self.assertEqual(conversation.conversation_type, "thread")

    def test_create_thread_without_any_context(self):
        """Test creating a thread without corpus or document (should fail)."""
        mutation = """
            mutation CreateThread($title: String!, $initialMessage: String!) {
                createThread(title: $title, initialMessage: $initialMessage) {
                    ok
                    message
                    obj {
                        id
                    }
                }
            }
        """

        variables = {
            "title": "Orphan Thread",
            "initialMessage": "Should fail",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertFalse(data["ok"])
        self.assertIn("corpus_id or document_id", data["message"].lower())

    def test_can_moderate_dual_context_thread(self):
        """Test can_moderate() with both corpus and document set."""
        # Create a thread with both contexts
        conversation = Conversation.objects.create(
            title="Dual Context Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            chat_with_document=self.document,
            creator=self.other_user,  # Not the corpus/doc owner
        )

        # Corpus owner (self.user) can moderate
        self.assertTrue(conversation.can_moderate(self.user))

        # Create another user who owns a different document
        document_owner = User.objects.create_user(
            username="doc_owner",
            email="doc_owner@example.com",
            password="testpass123",
        )
        new_document = Document.objects.create(
            title="Another Document",
            description="Owned by different user",
            creator=document_owner,
        )

        # Thread with new_document - document owner can moderate
        conversation2 = Conversation.objects.create(
            title="Doc Owner Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            chat_with_document=new_document,
            creator=self.other_user,
        )

        # Document owner can moderate
        self.assertTrue(conversation2.can_moderate(document_owner))

        # Other user who doesn't own corpus or document cannot moderate
        random_user = User.objects.create_user(
            username="random_user",
            email="random@example.com",
            password="testpass123",
        )
        self.assertFalse(conversation2.can_moderate(random_user))

    def test_thread_type_allows_both_fields(self):
        """Test that THREAD type allows both chat_with_corpus and chat_with_document."""
        # This should NOT raise a ValidationError
        conversation = Conversation(
            title="Both Fields Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            chat_with_document=self.document,
            creator=self.user,
        )
        # clean() should pass for THREAD type
        conversation.clean()
        conversation.save()

        # Verify both fields are set
        self.assertIsNotNone(conversation.chat_with_corpus)
        self.assertIsNotNone(conversation.chat_with_document)

    def test_chat_type_rejects_both_fields(self):
        """Test that CHAT type still enforces mutual exclusivity."""
        from django.core.exceptions import ValidationError

        conversation = Conversation(
            title="Both Fields Chat",
            conversation_type="chat",  # CHAT type, not THREAD
            chat_with_corpus=self.corpus,
            chat_with_document=self.document,
            creator=self.user,
        )

        # clean() should raise ValidationError for CHAT type
        with self.assertRaises(ValidationError):
            conversation.clean()

    # =========================================================================
    # Issue #686: UpdateMessageMutation tests
    # =========================================================================

    def test_update_message_mutation(self):
        """Test updating a message with proper permissions."""
        # Create a thread and message
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Original content",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, message, [PermissionTypes.CRUD])

        mutation = """
            mutation UpdateMessage($messageId: ID!, $content: String!) {
                updateMessage(messageId: $messageId, content: $content) {
                    ok
                    message
                    obj {
                        id
                        content
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        variables = {
            "messageId": message_id,
            "content": "Updated content",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Message updated successfully")
        self.assertEqual(data["obj"]["content"], "Updated content")

        # Verify message was updated in database
        message.refresh_from_db()
        self.assertEqual(message.content, "Updated content")

    def test_update_message_without_permission(self):
        """Test that users without CRUD permission cannot edit messages (IDOR prevention)."""
        # Create a thread and message owned by user
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Original content",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, message, [PermissionTypes.CRUD])

        mutation = """
            mutation UpdateMessage($messageId: ID!, $content: String!) {
                updateMessage(messageId: $messageId, content: $content) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        variables = {
            "messageId": message_id,
            "content": "Hacked content",
        }

        # other_user has no permission
        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertFalse(data["ok"])
        # IDOR prevention: same message whether object doesn't exist or no permission
        self.assertIn("permission", data["message"].lower())

        # Verify message was NOT updated
        message.refresh_from_db()
        self.assertEqual(message.content, "Original content")

    def test_update_message_moderator_can_edit(self):
        """Test that moderators (corpus/document owners) can edit any message in their thread."""
        # Create a thread owned by user (who is the corpus owner)
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,  # self.user owns this corpus
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.other_user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        # Message created by other_user
        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Message by other user",
            creator=self.other_user,
        )
        set_permissions_for_obj_to_user(
            self.other_user, message, [PermissionTypes.CRUD]
        )

        mutation = """
            mutation UpdateMessage($messageId: ID!, $content: String!) {
                updateMessage(messageId: $messageId, content: $content) {
                    ok
                    message
                    obj {
                        content
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        variables = {
            "messageId": message_id,
            "content": "Moderator edited",
        }

        # self.user is moderator (corpus owner)
        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["obj"]["content"], "Moderator edited")

    def test_update_message_locked_conversation(self):
        """Test that messages in locked conversations cannot be edited."""
        conversation = Conversation.objects.create(
            title="Locked Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
            is_locked=True,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Message in locked thread",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, message, [PermissionTypes.CRUD])

        mutation = """
            mutation UpdateMessage($messageId: ID!, $content: String!) {
                updateMessage(messageId: $messageId, content: $content) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        variables = {
            "messageId": message_id,
            "content": "Should fail",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("locked", data["message"].lower())

    def test_update_message_deleted_message(self):
        """Test that deleted messages cannot be edited."""
        from django.utils import timezone

        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Deleted message",
            creator=self.user,
            deleted_at=timezone.now(),  # Soft deleted
        )
        set_permissions_for_obj_to_user(self.user, message, [PermissionTypes.CRUD])

        mutation = """
            mutation UpdateMessage($messageId: ID!, $content: String!) {
                updateMessage(messageId: $messageId, content: $content) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        variables = {
            "messageId": message_id,
            "content": "Should fail",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("deleted", data["message"].lower())

    def test_update_message_empty_content(self):
        """Test that empty message content is rejected."""
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Original content",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, message, [PermissionTypes.CRUD])

        mutation = """
            mutation UpdateMessage($messageId: ID!, $content: String!) {
                updateMessage(messageId: $messageId, content: $content) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        # Test empty string
        variables = {
            "messageId": message_id,
            "content": "",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("empty", data["message"].lower())

        # Test whitespace-only string
        variables["content"] = "   "
        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("empty", data["message"].lower())

    def test_update_message_reparses_mentions(self):
        """
        Test that editing a message re-parses @mentions and links agents.

        When a message is updated with new mention syntax, the mutation should:
        1. Clear existing mentioned agents
        2. Parse the new content for mentions
        3. Link any mentioned agents found
        4. Trigger agent responses if agents were mentioned
        """
        from unittest.mock import patch

        from opencontractserver.agents.models import AgentConfiguration

        # Create a thread
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        # Create a global agent that can be mentioned
        agent = AgentConfiguration.objects.create(
            name="Test Agent",
            slug="test-agent",
            scope="GLOBAL",
            description="Test agent for mention parsing",
            is_active=True,
            is_public=True,
            creator=self.user,
        )

        # Create message without mentions
        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Original content without mentions",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, message, [PermissionTypes.CRUD])

        # Verify no agents linked initially
        self.assertEqual(message.mentioned_agents.count(), 0)

        mutation = """
            mutation UpdateMessage($messageId: ID!, $content: String!) {
                updateMessage(messageId: $messageId, content: $content) {
                    ok
                    message
                    obj {
                        id
                        content
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        # Update message with @agent mention (using markdown link format)
        variables = {
            "messageId": message_id,
            "content": "Updated content with [@test-agent](/agents/test-agent)",
        }

        # Mock the Celery task to verify it was called
        with patch(
            "config.graphql.conversation_mutations.trigger_agent_responses_for_message"
        ) as mock_task:
            result = self._execute_with_user(mutation, self.user, variables)

            self.assertIsNone(result.get("errors"))
            data = result["data"]["updateMessage"]
            self.assertTrue(data["ok"])
            self.assertEqual(data["message"], "Message updated successfully")

            # Verify agent was linked
            message.refresh_from_db()
            self.assertEqual(message.mentioned_agents.count(), 1)
            self.assertEqual(message.mentioned_agents.first(), agent)

            # Verify Celery task was called to trigger agent response
            # (agent was mentioned, so task should be triggered)
            mock_task.delay.assert_called_once()

    def test_update_message_preserves_parent_relationship(self):
        """
        Test that editing a reply message preserves its parent_message relationship.

        When a message that is a reply (has parent_message set) is edited, the
        parent_message field should remain unchanged. This ensures that thread
        structure is preserved when users edit their replies.

        Part of Issue #686 code review feedback.
        """
        # Create a thread
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        # Create parent message
        parent_message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Parent message content",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, parent_message, [PermissionTypes.CRUD]
        )

        # Create reply message
        reply_message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Original reply content",
            creator=self.user,
            parent_message=parent_message,
        )
        set_permissions_for_obj_to_user(
            self.user, reply_message, [PermissionTypes.CRUD]
        )

        # Verify parent relationship is set
        self.assertEqual(reply_message.parent_message, parent_message)

        from graphql_relay import to_global_id

        mutation = """
            mutation UpdateMessage($messageId: ID!, $content: String!) {
                updateMessage(messageId: $messageId, content: $content) {
                    ok
                    message
                    obj {
                        id
                        content
                    }
                }
            }
        """

        variables = {
            "messageId": to_global_id("MessageType", reply_message.pk),
            "content": "Updated reply content",
        }

        # Execute mutation
        result = self._execute_with_user(mutation, self.user, variables)

        # Assert no errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Assert mutation was successful
        data = result["data"]["updateMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Message updated successfully")

        # Verify content was updated
        reply_message.refresh_from_db()
        self.assertEqual(reply_message.content, "Updated reply content")

        # CRITICAL: Verify parent_message relationship is preserved
        self.assertEqual(
            reply_message.parent_message,
            parent_message,
            "Parent message relationship should be preserved after editing",
        )


class DualContextThreadAccessControlTestCase(TestCase):
    """
    Test the AND logic for dual-context thread access.

    When a thread is linked to BOTH a corpus AND a document, the user must have
    access to BOTH resources. This is different from moderation (which uses OR
    logic - either owner can moderate).

    These tests verify the permission boundary cases:
    - User with corpus-only permission cannot access dual-context thread
    - User with document-only permission cannot access dual-context thread
    - User with both permissions can access dual-context thread
    - Public corpus + private document = denied
    - Private corpus + public document = denied
    """

    def setUp(self):
        """Create users, corpus, and document with specific permission setups."""
        # Create test users
        self.corpus_owner = User.objects.create_user(
            username="corpus_owner",
            email="corpus_owner@example.com",
            password="testpass123",
        )
        self.document_owner = User.objects.create_user(
            username="document_owner",
            email="document_owner@example.com",
            password="testpass123",
        )
        self.user_with_both = User.objects.create_user(
            username="user_with_both",
            email="both@example.com",
            password="testpass123",
        )
        self.user_with_neither = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
        )

        # Create a private corpus (corpus_owner is creator)
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            description="Only accessible to specific users",
            creator=self.corpus_owner,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.corpus_owner, self.private_corpus, [PermissionTypes.CRUD]
        )

        # Create a private document (document_owner is creator)
        self.private_document = Document.objects.create(
            title="Private Document",
            description="Only accessible to specific users",
            creator=self.document_owner,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.document_owner, self.private_document, [PermissionTypes.CRUD]
        )

        # Give user_with_both access to both resources
        set_permissions_for_obj_to_user(
            self.user_with_both, self.private_corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user_with_both, self.private_document, [PermissionTypes.READ]
        )

        # Create the dual-context thread (linked to both corpus and document)
        self.dual_context_thread = Conversation.objects.create(
            title="Discussion about document in corpus",
            conversation_type="thread",
            chat_with_corpus=self.private_corpus,
            chat_with_document=self.private_document,
            creator=self.corpus_owner,
        )

    def _check_websocket_access(self, user):
        """
        Simulate the WebSocket access check logic.

        This mirrors the logic in thread_updates.py:_can_access_conversation()
        """
        conversation = self.dual_context_thread

        # Creator always has access
        if conversation.creator_id == user.pk:
            return True

        # Superuser always has access
        if user.is_superuser:
            return True

        has_corpus_access = True  # Default if no corpus context
        has_document_access = True  # Default if no document context

        # Check corpus access
        if conversation.chat_with_corpus:
            has_corpus_access = (
                Corpus.objects.visible_to_user(user)
                .filter(pk=conversation.chat_with_corpus_id)
                .exists()
            )

        # Check document access
        if conversation.chat_with_document:
            has_document_access = (
                Document.objects.visible_to_user(user)
                .filter(pk=conversation.chat_with_document_id)
                .exists()
            )

        # AND logic for dual-context threads
        if conversation.chat_with_corpus and conversation.chat_with_document:
            return has_corpus_access and has_document_access
        elif conversation.chat_with_corpus:
            return has_corpus_access
        elif conversation.chat_with_document:
            return has_document_access

        return False

    def test_user_with_corpus_only_permission_denied(self):
        """
        User who can access the corpus but NOT the document should be DENIED.

        Scenario: Alice has read access to "Engineering Corpus" but no access
        to "Confidential Contract.pdf". When she tries to view a thread about
        that document within the corpus, she should be denied.
        """
        # Give corpus_owner explicit document access (they're the corpus owner)
        # but user_with_corpus_only has only corpus access
        user_with_corpus_only = User.objects.create_user(
            username="corpus_only",
            email="corpus_only@example.com",
            password="testpass123",
        )
        set_permissions_for_obj_to_user(
            user_with_corpus_only, self.private_corpus, [PermissionTypes.READ]
        )
        # No document permission granted

        access_granted = self._check_websocket_access(user_with_corpus_only)

        self.assertFalse(
            access_granted,
            "User with corpus-only permission should NOT access dual-context thread",
        )

    def test_user_with_document_only_permission_denied(self):
        """
        User who can access the document but NOT the corpus should be DENIED.

        Scenario: Bob has access to "Contract.pdf" on his personal drive, but
        not to the "Legal Team Corpus" where it's being discussed. He should
        not be able to see the corpus-level discussion thread.
        """
        user_with_document_only = User.objects.create_user(
            username="document_only",
            email="document_only@example.com",
            password="testpass123",
        )
        set_permissions_for_obj_to_user(
            user_with_document_only, self.private_document, [PermissionTypes.READ]
        )
        # No corpus permission granted

        access_granted = self._check_websocket_access(user_with_document_only)

        self.assertFalse(
            access_granted,
            "User with document-only permission should NOT access dual-context thread",
        )

    def test_user_with_both_permissions_granted(self):
        """
        User who can access BOTH corpus AND document should be GRANTED access.

        Scenario: Carol is a team member with access to both the "Project Corpus"
        and the specific "Requirements.pdf" being discussed. She should be able
        to participate in the thread.
        """
        access_granted = self._check_websocket_access(self.user_with_both)

        self.assertTrue(
            access_granted,
            "User with both corpus AND document permission should access dual-context thread",
        )

    def test_user_with_no_permissions_denied(self):
        """
        User with access to neither resource should be DENIED.

        Scenario: Dave is an external contractor with no access to any internal
        resources. He should not see any threads.
        """
        access_granted = self._check_websocket_access(self.user_with_neither)

        self.assertFalse(
            access_granted,
            "User with no permissions should NOT access dual-context thread",
        )

    def test_public_corpus_private_document_denied(self):
        """
        Public corpus + private document = DENIED for users without document access.

        Scenario: The "Open Research Corpus" is public, but "Proprietary Data.pdf"
        within it is restricted. Random users should not be able to see discussions
        about the proprietary document, even though they can browse the corpus.
        """
        # Make corpus public
        public_corpus = Corpus.objects.create(
            title="Public Research Corpus",
            description="Anyone can view",
            creator=self.corpus_owner,
            is_public=True,
        )

        # Document stays private
        private_doc_in_public_corpus = Document.objects.create(
            title="Proprietary Data",
            description="Restricted access",
            creator=self.document_owner,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.document_owner, private_doc_in_public_corpus, [PermissionTypes.CRUD]
        )

        # Create thread linking both (we create this to ensure the scenario is valid,
        # even though we test the underlying permission logic directly)
        Conversation.objects.create(
            title="Discussion about proprietary data",
            conversation_type="thread",
            chat_with_corpus=public_corpus,
            chat_with_document=private_doc_in_public_corpus,
            creator=self.corpus_owner,
        )

        # Random user can see public corpus but not private document
        random_user = User.objects.create_user(
            username="random_public",
            email="random@example.com",
            password="testpass123",
        )

        # Check access (using the thread we just created)
        has_corpus_access = (
            Corpus.objects.visible_to_user(random_user)
            .filter(pk=public_corpus.pk)
            .exists()
        )
        has_document_access = (
            Document.objects.visible_to_user(random_user)
            .filter(pk=private_doc_in_public_corpus.pk)
            .exists()
        )

        self.assertTrue(has_corpus_access, "Random user should see public corpus")
        self.assertFalse(
            has_document_access, "Random user should NOT see private document"
        )

        # AND logic means access denied
        combined_access = has_corpus_access and has_document_access
        self.assertFalse(
            combined_access,
            "Public corpus + private document should DENY access to dual-context thread",
        )

    def test_private_corpus_public_document_denied(self):
        """
        Private corpus + public document = DENIED for users without corpus access.

        Scenario: "Internal Strategy Corpus" is private, but it contains a link
        to a "Public Announcement.pdf". Even though the document is public,
        discussions within the private corpus context should be restricted.
        """
        # Corpus stays private
        private_corpus = Corpus.objects.create(
            title="Internal Strategy Corpus",
            description="Team members only",
            creator=self.corpus_owner,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.corpus_owner, private_corpus, [PermissionTypes.CRUD]
        )

        # Make document public
        public_document = Document.objects.create(
            title="Public Announcement",
            description="Anyone can view",
            creator=self.document_owner,
            is_public=True,
        )

        # Create thread linking both (we create this to ensure the scenario is valid,
        # even though we test the underlying permission logic directly)
        Conversation.objects.create(
            title="Internal discussion about public announcement",
            conversation_type="thread",
            chat_with_corpus=private_corpus,
            chat_with_document=public_document,
            creator=self.corpus_owner,
        )

        # Random user can see public document but not private corpus
        random_user = User.objects.create_user(
            username="random_private",
            email="random2@example.com",
            password="testpass123",
        )

        has_corpus_access = (
            Corpus.objects.visible_to_user(random_user)
            .filter(pk=private_corpus.pk)
            .exists()
        )
        has_document_access = (
            Document.objects.visible_to_user(random_user)
            .filter(pk=public_document.pk)
            .exists()
        )

        self.assertFalse(has_corpus_access, "Random user should NOT see private corpus")
        self.assertTrue(has_document_access, "Random user should see public document")

        # AND logic means access denied
        combined_access = has_corpus_access and has_document_access
        self.assertFalse(
            combined_access,
            "Private corpus + public document should DENY access to dual-context thread",
        )

    def test_thread_creator_always_has_access(self):
        """
        Thread creator should always have access, regardless of other permissions.

        Scenario: Admin creates a thread linking resources. Even if the admin's
        explicit permissions are later revoked, they should still access their
        own thread as the creator.
        """
        access_granted = self._check_websocket_access(self.corpus_owner)

        self.assertTrue(
            access_granted,
            "Thread creator should always have access to their own thread",
        )
